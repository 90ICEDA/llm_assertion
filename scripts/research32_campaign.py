"""Bounded multi-iteration real refinement, qualified search and paired gate audit.

prepare does local native qualification and saves exact first requests. run
requires a new nine-call grant (three seeds, at most three semantic iterations).
All model work finishes and candidates freeze before any fresh test generation.
"""
import argparse
import hashlib
import json
from pathlib import Path
import secrets
import shutil
import research17_loop as loop
import research30_ablation as trial
import research31_gate as gate
import research32_runtime as extension
from research32_model import Model
from research32_search import SEEDS, stimulus
from research21_loop import refine
from research15_evidence import merge_ledgers
from research28_campaign import qualify

read,dump=loop.read,loop.dump
BASE=loop.ROOT/'deliverables/research30_ablation_prepare_20261020_r02'
SOURCES=('research32_campaign.py','research32_model.py','research32_runtime.py',
         'research32_search.py','research31_gate.py','research21_loop.py')


def snapshot(out):
    trial.snapshot(out)
    for name in SOURCES:shutil.copy2(loop.ROOT/'scripts'/name,out/'source_snapshot'/name)
    dump(out/'source_snapshot/hashes.json',{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (out/'source_snapshot').glob('*.py')})


def initial_feedback(before):
    info=loop.inspect(before['group']['ledger'])
    targets=sorted(k for k in info['misses']|info['false_positives'] if info['rows'][k]['obligation']=='stall_stability')
    return dict(requested_obligations=('stall_stability',),current_gap_ids=targets,
        counts=before['counts'],actual_native_evidence=before['feedback'])


def prepare(search,out):
    assert read(search/'outcome.json')['all_healthy']
    loop.prepare(out);snapshot(out)
    initial=read(BASE/'shared_initial.json');history=read(BASE/'history_cases.json')
    old=read(BASE/'core/history/result.json')
    assert old['healthy'] and not any(old['counts'][k] for k in ('misses','unknown','false_positives'))
    dump(out/'shared_initial.json',initial)
    dump(out/'history_reuse.json',dict(source=str(BASE/'core/history/result.json'),
        sha256=hashlib.sha256((BASE/'core/history/result.json').read_bytes()).hexdigest(),
        new_executions=0,history_cases=len(history)))
    acquired=read(search/'acquired_cases.json');previews={}
    with extension.installed():
        for seed in SEEDS:
            folder=out/f's{seed}'
            long=[c for c in acquired if c['id'].startswith(f'long32:s{seed}:')]
            assert len(long)==2
            short=trial.select_cases(3113)
            for c in short:c['dedup_class']='stall_stability:'+c['mode']
            selected=history+short+long
            evidence=loop.replay(initial,folder/'core/acquired',short+long)
            witness=qualify(evidence,short+long,folder/'core/acquired')
            dump(folder/'witness_qualification.json',witness)
            assert witness['passed'] and evidence['counts']['misses']==4
            group=merge_ledgers([old['group'],evidence['group']])
            before=dict(healthy=True,group=group,health=old['health']+evidence['health'],
                counts=loop.counts(group),feedback=old['feedback']+evidence['feedback'])
            dump(folder/'core/baseline/result.json',before)
            dump(folder/'cases.json',selected)
            binding=dict(candidate_hash=loop.sha(initial),cases_hash=loop.sha(selected),
                result_path=str(folder/'core/baseline/result.json'),
                result_sha256=hashlib.sha256((folder/'core/baseline/result.json').read_bytes()).hexdigest())
            dump(folder/'baseline_binding.json',binding)
            settings=trial.config(3);settings['options']['seed']=seed
            dump(folder/'model_config.json',settings)
            llm=Model(folder/'preview',settings)
            request=llm._payload(initial,'stall_stability',initial_feedback(before),'core_fresh_boundary_repair')
            dump(folder/'preview/request.preview.json',request)
            previews[f's{seed}/preview/request.preview.json']=hashlib.sha256((folder/'preview/request.preview.json').read_bytes()).hexdigest()
    dump(out/'protocol.json',dict(seeds=SEEDS,maximum_calls=9,iterations_per_seed=3,
        endpoint=trial.config(3)['remote_url'],model=trial.config(3)['remote_model'],
        previews=previews,source_search=str(search),source_gate=gate.VERSION,
        first_payloads_fixed=True,later_payloads='Only actual development interface/native/gate feedback; no hand editing or forced successful predicates.',
        source_sha256=read(out/'source_snapshot/hashes.json'),
        known_tests='All published research31/earlier results are development knowledge. No new test materializes before all three terminal freezes.',
        stability='3 model seeds, <=3 calls each; failed seeds retained. Not broad model stability or controlled four-arm ablation.',
        gate_pairing='Each actual proposal evaluated under current visible evidence and full historical gate. Same proposal, no generative confound. Shadow decision does not update the accepted set.',
        acceptance='Current targets repaired, full native/control/sampling health, historical detections and applicable triggers retained. Unknown rejects.',
        project_freeze='research28 unchanged; new run freezes are experimental until independently evaluated.',
        no_new_model_calls=True,formal_calls=0))
    dump(out/'outcome.json',dict(status='nine_call_campaign_prepared',model_calls=0,qualified_seeds=3))
    print('PREPARED',out,flush=True)


def run(prep,out,authorization):
    auth=read(authorization);protocol=read(prep/'protocol.json')
    assert auth['authorized_calls']==9 and auth['endpoint']==protocol['endpoint']
    assert auth['run_output']==out.relative_to(loop.ROOT).as_posix()
    for n,h in protocol['previews'].items():assert hashlib.sha256((prep/n).read_bytes()).hexdigest()==h
    for n,h in protocol['source_sha256'].items():
        source=loop.ROOT/'scripts'/n
        if source.exists():assert hashlib.sha256(source.read_bytes()).hexdigest()==h, ('changed_source',n)
    loop.prepare(out);snapshot(out);dump(out/'protocol.json',protocol)
    shutil.copy2(authorization,out/'authorization.json')
    calls=0;models=[];frozen={};summaries={};old_gate=loop.decide
    try:
        with extension.installed():
            for seed in SEEDS:
                source=prep/f's{seed}';folder=out/f's{seed}'
                initial=read(prep/'shared_initial.json');cases=read(source/'cases.json')
                expected=read(source/'preview/request.preview.json')
                class LockedFirstModel(Model):
                    def call(self,*args,**kwargs):
                        nonlocal calls
                        assert calls<9,'authorized_call_cap'
                        calls+=1;dump(out/'attempt_budget.json',dict(reserved=calls,maximum=9))
                        return super().call(*args,**kwargs)
                    def _payload(self,*args,**kwargs):
                        payload=super()._payload(*args,**kwargs)
                        if not self.calls:assert payload==expected,'first_request_changed'
                        return payload
                llm=LockedFirstModel(folder,read(source/'model_config.json'));models.append(llm)
                gate_index=0
                def paired_gate(before,after,targets=()):
                    nonlocal gate_index
                    full=gate.decide(before,after,targets)
                    old=loop.inspect(before)
                    scenarios={old['rows'][k]['scenario_id'] for k in targets}
                    current=[r for r in after if r['scenario_id'] in scenarios]
                    info=loop.inspect(current)
                    shadow=bool(current) and not(info['misses'] or info['false_positives'] or info['unknown'])
                    dump(folder/'paired_gate'/f'{gate_index}.json',dict(current_only_accepts=shadow,
                        full_gate_accepts=full['accepted'],same_proposal=True,scenarios=sorted(scenarios),
                        gate=full,scope='Same proposal/evidence. Current-only shadow never affects actual state.'))
                    gate_index+=1
                    return full
                loop.decide=paired_gate
                final,summary=refine(folder,llm,initial,cases,3,stages_to_run=(('stall_stability',),),
                    qualified_before=read(source/'baseline_binding.json'))
                frozen[str(seed)]=final;summaries[str(seed)]=summary
                print('TERMINAL',seed,summary['resolved'],len(llm.calls),flush=True)
            dump(out/'all_freeze.json',{s:loop.sha(c) for s,c in frozen.items()})
            # The first creation of these inputs occurs only after all model work.
            from research28_cases import cases as short_cases
            from research21_cases import independent_cases
            seed=secrets.randbelow(2**31)
            fresh=short_cases(seed,True)+independent_cases(seed)
            for depth,pipeline in ((4,2),(8,2)):
                for duration in (9,17,24):
                    for mode in extension.MODES:
                        n=seed+len(fresh)
                        fresh.append(dict(id=f'independent32:s{n}:d{depth}:p{pipeline}:{duration}:{mode}',
                            depth=depth,pipeline=pipeline,mode=mode,rows=stimulus(n,duration),split='independent_test'))
            development={loop.sha(c['rows']) for s in SEEDS for c in read(prep/f's{s}/cases.json')}
            assert all(loop.sha(c['rows']) not in development for c in fresh)
            dump(out/'independent/split.json',dict(seed=seed,cases=fresh,created_after_all_freeze=True,
                hashes={s:loop.sha(c) for s,c in frozen.items()},usage='no_feedback_no_selection'))
            tests={}
            for s,c in frozen.items():
                result=loop.replay(c,out/'independent'/s,fresh)
                for r in result.get('group',{}).get('ledger',[]):r['split']='independent_test'
                dump(out/'independent'/s/'result.json',result)
                tests[s]=dict(healthy=result['healthy'],counts=result.get('counts'))
            dump(out/'outcome.json',dict(status='bounded_real_refinement_and_fresh_replay_completed',
                model_calls=calls,summaries=summaries,independent=tests))
    except BaseException as exc:
        dump(out/'outcome.json',dict(status='blocked',calls_reserved=calls,error_type=type(exc).__name__))
        raise
    finally:
        loop.decide=old_gate
        recorded=[c for m in models for c in m.calls]
        dump(out/'model_cost.json',dict(calls=len(recorded),reserved_calls=calls,
            prompt_tokens=sum(c.get('prompt_tokens') or 0 for c in recorded),
            completion_tokens=sum(c.get('completion_tokens') or 0 for c in recorded),
            usage_unavailable=sum(c.get('prompt_tokens') is None or c.get('completion_tokens') is None for c in recorded),formal_calls=0))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('prepare','run'))
    p.add_argument('--out',type=Path,required=True);p.add_argument('--search',type=Path)
    p.add_argument('--prepared',type=Path);p.add_argument('--authorization',type=Path)
    a=p.parse_args();out=a.out.resolve();assert loop.ROOT in out.parents
    if a.action=='prepare':prepare(a.search.resolve(),out)
    else:run(a.prepared.resolve(),out,a.authorization.resolve())
