"""Prepare and execute fresh contrast-based retries for two failed model seeds.

Two new calls need explicit authorization or reassignment of the two unspent
research32 calls; the prior grant capped that trial at three calls per seed.
No archived response is used by run. qualify/prepare never submit requests.
"""
import argparse
import hashlib
from pathlib import Path
import secrets
import shutil
import research17_loop as loop
import research31_gate as gate
import research32_runtime as extension
from research32_campaign import snapshot as previous_snapshot, initial_feedback
from research33_model import Model,screen,fingerprint,contrast_cards
from research21_loop import refine
from research31_gate import portable
from research32_search import stimulus

read,dump=loop.read,loop.dump
PREP=loop.ROOT/'deliverables/research32_prepare_20261021_r01'
RUN=loop.ROOT/'deliverables/research32_real_20261021_r01'
SEEDS=(3203,3217)


def snapshot(out):
    previous_snapshot(out)
    for n in ('research33_model.py','research33_campaign.py'):
        shutil.copy2(loop.ROOT/'scripts'/n,out/'source_snapshot'/n)
    dump(out/'source_snapshot/hashes.json',{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (out/'source_snapshot').glob('*.py')})


def prepare(out):
    loop.prepare(out);snapshot(out)
    initial=read(PREP/'shared_initial.json')
    valid=read(RUN/'s3209/core/frozen_candidate.json')
    dump(out/'shared_initial.json',initial)
    records=[];previews={}
    with extension.installed():
        for seed in SEEDS:
            source=PREP/f's{seed}';folder=out/f's{seed}'
            binding=read(source/'baseline_binding.json');before=read(portable(binding['result_path']))
            assert hashlib.sha256(portable(binding['result_path']).read_bytes()).hexdigest()==binding['result_sha256']
            assert before['healthy'] and before['counts']['misses']==4
            feedback=initial_feedback(before)
            cards=contrast_cards(feedback,'stall_stability')
            assert len(cards)==4 and all(c['differing_sampled_signals'] for c in cards)
            for index in range(3):
                path=RUN/f's{seed}/core/v{index}/model_call/candidate.json'
                old=read(path);decision=screen(old,initial,feedback)
                assert decision['kind']=='unchanged_known_missing_protection' and not decision['accepted_for_native']
                records.append(dict(seed=seed,iteration=index,source=str(path),source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),decision=decision))
            assert screen(valid,initial,feedback)['accepted_for_native']
            assert not screen(valid,initial,feedback,[fingerprint(valid)])['accepted_for_native']
            dump(folder/'contrasts.json',cards);dump(folder/'cases.json',read(source/'cases.json'))
            dump(folder/'baseline_binding.json',binding)
            settings=read(source/'model_config.json');settings['max_model_calls']=1
            dump(folder/'model_config.json',settings)
            model=Model(folder/'preview',settings)
            preview=model._payload(initial,'stall_stability',feedback,'core_fresh_boundary_repair')
            path=folder/'preview/request.preview.json';dump(path,preview)
            previews[path.relative_to(out).as_posix()]=hashlib.sha256(path.read_bytes()).hexdigest()
        # Explicit archived positive control, not a new model success.
        selected=read(PREP/'s3203/cases.json')
        cases=[selected[0]]+selected[-4:]
        dump(out/'local_controls/cases.json',cases)
        before=loop.replay(initial,out/'local_controls/core/before',cases)
        after=loop.replay(valid,out/'local_controls/core/archived_novel_candidate',cases)
        assert before['healthy'] and after['healthy']
        verdict=gate.decide(before['group']['ledger'],after['group']['ledger'],sorted(loop.inspect(before['group']['ledger'])['misses']))
        dump(out/'local_controls/gate.json',verdict)
        assert verdict['accepted'] and not after['counts']['misses']
    dump(out/'qualification.json',dict(passed=True,archived_repeats=records,
        control_source=str(RUN/'s3209/core/frozen_candidate.json'),
        control_source_sha256=hashlib.sha256((RUN/'s3209/core/frozen_candidate.json').read_bytes()).hexdigest(),
        positive_control_before=before['counts'],positive_control_after=after['counts'],
        native_duplicate_executions_avoided=6*218,
        avoided_count_scope='Counterfactual body replays only: six historical repeats x 109 cases x correct/fault. These are NOT actual newly saved resources or new executions; compilation excluded.',
        model_calls=0,scope='Local screening and actual native archived positive control only; no new model success claimed.'))
    dump(out/'protocol.json',dict(seeds=SEEDS,maximum_calls=2,calls_per_seed=1,
        endpoint=read(PREP/'protocol.json')['endpoint'],model=read(PREP/'protocol.json')['model'],
        previews=previews,source_hashes=read(out/'source_snapshot/hashes.json'),
        intervention='Fresh synthesis without old predicate text; all four exact paired contrasts; local no-op/rejected-token screening; same native history gate.',
        repeat_scope='Only lexical identity under whitespace/outer parentheses/metadata normalization. Novel expressions always need native verification.',
        selection='Two retrospectively selected failed seeds, not an unbiased stability sample or a four-arm ablation.',
        old_test_scope='All published research32 and earlier tests are development knowledge, but no old independent tests or successful candidate predicates enter model prompts.',
        independent='After both terminal freezes, create a new shared batch. No prompt, selection, or changes from fresh tests.',
        authorization='Prior nine-call study used seven. Its two unused slots require explicit reassignment to this new two-seed follow-up; no call submitted in prepare.'))
    dump(out/'outcome.json',dict(status='two_retry_requests_prepared',model_calls=0))
    print('PREPARED_WITH_ZERO_MODEL_CALLS',flush=True)


def run(prep,out,authorization):
    auth=read(authorization);protocol=read(prep/'protocol.json')
    assert auth['authorized_calls']==2 and auth['endpoint']==protocol['endpoint']
    assert auth['run_output']==out.relative_to(loop.ROOT).as_posix()
    for n,h in protocol['previews'].items():assert hashlib.sha256((prep/n).read_bytes()).hexdigest()==h
    for n,h in protocol['source_hashes'].items():
        assert hashlib.sha256((loop.ROOT/'scripts'/n).read_bytes()).hexdigest()==h
    loop.prepare(out);snapshot(out);dump(out/'protocol.json',protocol)
    shutil.copy2(authorization,out/'authorization.json')
    models=[];frozen={};summaries={};old_gate=loop.decide
    try:
        loop.decide=gate.decide
        with extension.installed():
            for seed in SEEDS:
                source=prep/f's{seed}';folder=out/f's{seed}'
                expected=read(source/'preview/request.preview.json')
                class LockedModel(Model):
                    def _payload(self,*args,**kwargs):
                        payload=super()._payload(*args,**kwargs)
                        assert payload==expected,'prepared_request_changed'
                        return payload
                model=LockedModel(folder,read(source/'model_config.json'));models.append(model)
                final,summary=refine(folder,model,read(prep/'shared_initial.json'),read(source/'cases.json'),1,
                    stages_to_run=(('stall_stability',),),qualified_before=read(source/'baseline_binding.json'))
                frozen[str(seed)]=final;summaries[str(seed)]=summary
                print('TERMINAL',seed,summary['resolved'],flush=True)
            dump(out/'all_freeze.json',{s:loop.sha(c) for s,c in frozen.items()})
            from research28_cases import cases as short_cases
            from research21_cases import independent_cases
            seed=secrets.randbelow(2**31);fresh=short_cases(seed,True)+independent_cases(seed)
            for depth,pipeline in ((4,2),(8,2)):
                for duration in (9,17,24):
                    for mode in extension.MODES:
                        n=seed+len(fresh)
                        fresh.append(dict(id=f'independent33:s{n}:d{depth}:p{pipeline}:{duration}:{mode}',depth=depth,
                            pipeline=pipeline,mode=mode,rows=stimulus(n,duration),split='independent_test'))
            used={loop.sha(c['rows']) for s in SEEDS for c in read(prep/f's{s}/cases.json')}
            used.update(loop.sha(c['rows']) for c in read(RUN/'independent/split.json')['cases'])
            assert not used&{loop.sha(c['rows']) for c in fresh}
            dump(out/'independent/split.json',dict(seed=seed,cases=fresh,created_after_all_freeze=True,
                hashes={s:loop.sha(c) for s,c in frozen.items()},usage='no_feedback_no_selection'))
            tests={}
            for s,candidate in frozen.items():
                result=loop.replay(candidate,out/'independent'/s,fresh)
                for row in result.get('group',{}).get('ledger',[]):row['split']='independent_test'
                dump(out/'independent'/s/'result.json',result)
                tests[s]=dict(healthy=result['healthy'],counts=result.get('counts'))
            dump(out/'outcome.json',dict(status='real_contrast_retries_completed',summaries=summaries,independent=tests))
    except BaseException as exc:
        dump(out/'outcome.json',dict(status='blocked',error_type=type(exc).__name__));raise
    finally:
        loop.decide=old_gate
        calls=[c for m in models for c in m.calls]
        dump(out/'model_cost.json',dict(calls=len(calls),prompt_tokens=sum(c.get('prompt_tokens') or 0 for c in calls),
            completion_tokens=sum(c.get('completion_tokens') or 0 for c in calls),
            usage_unavailable=sum(c.get('prompt_tokens') is None or c.get('completion_tokens') is None for c in calls),formal_calls=0))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('prepare','run'))
    p.add_argument('--out',type=Path,required=True);p.add_argument('--prepared',type=Path);p.add_argument('--authorization',type=Path)
    a=p.parse_args();out=a.out.resolve();assert loop.ROOT in out.parents
    if a.action=='prepare':prepare(out)
    else:run(a.prepared.resolve(),out,a.authorization.resolve())
