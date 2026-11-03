"""Three precommitted seeds, four true-model arms each, reset-aware gate v1.

prepare is local only. run requires a new explicit 12-call authorization.
Each seed freezes all four arms before its fresh holdout. All twelve prompts
are fixed before any call and no intermediate result can alter later prompts.
"""
import argparse
import hashlib
from pathlib import Path
import shutil

import research17_loop as loop
import research30_ablation as trial
import research31_gate as gate
import research28_valid_runtime as extension

ROOT=loop.ROOT
read,dump=loop.read,loop.dump
SEEDS=(3113,3119,3121)
BASE=ROOT/'deliverables/research30_ablation_prepare_20261020_r02'


def snapshot(out):
    trial.snapshot(out)
    for source in (Path(__file__),Path(gate.__file__)):
        shutil.copy2(source,out/'source_snapshot'/source.name)
    dump(out/'source_snapshot/hashes.json',{p.name:hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (out/'source_snapshot').iterdir() if p.is_file() and p.name!='hashes.json'})


def prepare(out,validation):
    assert read(validation/'outcome.json')['status']=='gate_validated_on_recorded_scope'
    out.mkdir(parents=True,exist_ok=False)
    baseline=read(BASE/'core/history/result.json')
    assert baseline['healthy'] and all(baseline['counts'][k]==0 for k in ('misses','unknown','false_positives'))
    previews={}
    for seed in SEEDS:
        folder=out/f's{seed}'
        loop.prepare(folder);snapshot(folder)
        for name in ('shared_initial.json','history_cases.json'):
            shutil.copy2(BASE/name,folder/name)
        # Reuse measured history without copying native command records or
        # pretending to have executed the baseline again during preparation.
        for rel in ('core/history/result.json','core/history/case_0/ledger.json'):
            target=folder/rel;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(BASE/rel,target)
        dump(folder/'history_reuse.json',dict(source=str(BASE/'core/history/result.json'),
            sha256=hashlib.sha256((BASE/'core/history/result.json').read_bytes()).hexdigest(),
            original_native_cost_shared=True,new_preparation_history_executions=0))
        selected=trial.select_cases(seed);dump(folder/'acquired_cases.json',selected)
        settings=trial.config(1);settings['options']['seed']=seed
        dump(folder/'model_config.json',settings)
        initial=read(folder/'shared_initial.json')
        with extension.installed():
            evidence=loop.replay(initial,folder/'core/acquired',selected)
            assert evidence['healthy'] and evidence['counts']['misses']==2
            assert not evidence['counts']['unknown'] and not evidence['counts']['false_positives']
            for name,arm in trial.ARMS.items():
                model=trial.Model(folder/'preview'/name,settings)
                payload=model._payload(initial,'stall_stability',trial.feedback(folder,arm['search']),'controlled_stall_review')
                path=folder/'preview'/name/'request.preview.json'
                dump(path,payload)
                previews[path.relative_to(out).as_posix()]=hashlib.sha256(path.read_bytes()).hexdigest()
        requests={n:read(folder/'preview'/n/'request.preview.json') for n in trial.ARMS}
        assert requests['A']==requests['C'] and requests['B']==requests['D']
        dump(folder/'protocol.json',dict(seed=seed,gate_version=gate.VERSION,
            source_search_cost=f'Seed{seed} contract:4 queries/64 executions logically per B/D; shared physical acquisition from research30.',
            model_calls_per_arm=1,arm_order=list(trial.ARMS),
            original_history_reused=str(BASE),history_cases=105,search_cases=2,
            same_initial=loop.sha(initial),sampling=settings['options'],
            independence='All12 prompts committed before first call. Each seed gets a fresh26-case batch after all its four arms freeze; no results fed to later calls.',
            historical_holdouts='Published research30 tests considered development knowledge; excluded from all prompts, candidate selection and preparation validation. New test batch each seed.',
            limits='One task with artificial boundary faults. Three input/model seed values; provider seed determinism not guaranteed. No historical parent/global claims.'))
        dump(folder/'qualification.json',dict(passed=True,history_cases=105,search_cases=2,
            before_history=baseline['counts'],search_misses=2,paired_initial_requests_equal=True,
            model_calls=0,credentials_read=False,external_transmission=False))
        dump(folder/'outcome.json',dict(status='prepared_without_remote_calls'))
    dump(out/'protocol.json',dict(seeds=SEEDS,max_model_calls=12,calls_per_arm=1,arms=trial.ARMS,
        gate_version=gate.VERSION,gate_validation=str(validation),
        gate_source_sha256=hashlib.sha256(Path(gate.__file__).read_bytes()).hexdigest(),
        preview_hashes=previews,model=trial.config(1)['remote_model'],endpoint=trial.config(1)['remote_url'],
        prospective_no_adaptation=True,remote_authorization='New bounded grant required; prior4 exhausted.'))
    dump(out/'outcome.json',dict(status='twelve_requests_prepared_no_calls'))
    print(dict(status='prepared',seeds=SEEDS,requests=len(previews),model_calls=0),flush=True)


def run(prep,out,authorization):
    protocol=read(prep/'protocol.json');auth=read(authorization)
    assert auth['authorized_calls']==12 and auth['endpoint']==protocol['endpoint']
    assert auth['run_output']==out.relative_to(ROOT).as_posix()
    assert protocol['gate_source_sha256']==hashlib.sha256(Path(gate.__file__).read_bytes()).hexdigest()
    assert all(hashlib.sha256((prep/p).read_bytes()).hexdigest()==h for p,h in protocol['preview_hashes'].items())
    out.mkdir(parents=True,exist_ok=False);shutil.copy2(authorization,out/'authorization.json')
    dump(out/'protocol.json',protocol);dump(out/'prepared_source.json',dict(path=str(prep)))
    old_gate,old_snapshot,old_model=loop.decide,trial.snapshot,trial.Model
    calls=0
    try:
        loop.decide=gate.decide
        def extended_snapshot(folder):
            old_snapshot(folder)
            dump(folder/'protocol.json',read(prepared/'protocol.json'))
            for source in (Path(__file__),Path(gate.__file__)):
                shutil.copy2(source,folder/'source_snapshot'/source.name)
            dump(folder/'source_snapshot/hashes.json',{p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                for p in (folder/'source_snapshot').iterdir() if p.is_file() and p.name!='hashes.json'})
        trial.snapshot=extended_snapshot
        for seed in SEEDS:
            prepared=prep/f's{seed}'
            class LockedModel(old_model):
                def __init__(self,folder,settings):
                    super().__init__(folder,settings)
                    self.expected=read(prepared/'preview'/folder.name/'request.preview.json')
                def _payload(self,*args,**kwargs):
                    value=super()._payload(*args,**kwargs)
                    assert value==self.expected,'request_changed_after_precommit'
                    return value
                def call(self,*args,**kwargs):
                    nonlocal calls
                    assert calls<12,'authorized_call_cap'
                    calls+=1
                    dump(out/'attempt_budget.json',dict(reserved=calls,maximum=12))
                    return super().call(*args,**kwargs)
            trial.Model=LockedModel
            child_out=out/f's{seed}'
            child_auth=dict(auth,authorized_calls=4,run_output=child_out.relative_to(ROOT).as_posix(),
                            parent_authorization=str(out/'authorization.json'),seed=seed)
            auth_path=out/f'authorization_s{seed}.json';dump(auth_path,child_auth)
            trial.run(prepared,child_out,auth_path)
            print('SEED_COMPLETED',seed,flush=True)
        dump(out/'outcome.json',dict(status='three_seed_four_arm_runs_completed',calls=calls))
    except BaseException as exc:
        dump(out/'outcome.json',dict(status='execution_blocked',calls_reserved=calls,error=repr(exc)))
        raise
    finally:
        loop.decide,trial.snapshot,trial.Model=old_gate,old_snapshot,old_model


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run'])
    p.add_argument('--out',type=Path,required=True);p.add_argument('--validation',type=Path)
    p.add_argument('--prepared',type=Path);p.add_argument('--authorization',type=Path)
    a=p.parse_args();out=a.out.resolve();assert ROOT in out.parents
    if a.action=='prepare':prepare(out,a.validation.resolve())
    else:run(a.prepared.resolve(),out,a.authorization.resolve())


if __name__=='__main__':main()
