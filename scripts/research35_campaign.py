"""Bounded causal applicability repair, real refinement, and five-obligation holdout.

prepare: local native experiments only. run: at most two plan calls then two
SVA calls, explicit authorization required. No synthetic model answers.
"""
import argparse
import ast
import copy
import json
from pathlib import Path
import secrets
import shutil
import research17_loop as loop
import research31_gate as gate
import research32_runtime as extension
from research32_search import stimulus
from research32_campaign import initial_feedback
from research34_campaign import snapshot,digest,PREP
from research34_applicability import certificate,validate_plan,PlanModel,VerifiedPlanModel,native_target_gate,portable
from research15_evidence import merge_ledgers
from research17_report import cost_audit,artifacts
from research30_ablation_report import metrics

read,dump=loop.read,loop.dump
P34=loop.ROOT/'deliverables/research34_prepare_20261021_r01'
R34=loop.ROOT/'deliverables/research34_real_20261021_r01'


class EvidenceModel(VerifiedPlanModel):
    def transform_request(self,*args,**kwargs):
        request=super().transform_request(*args,**kwargs)
        body=json.loads(request['messages'][1]['content'])
        body['counterexample_first']['native_conclusion']='Read the per-property trigger and failure markers in each actual evidence record. An earlier or revised candidate may fail by not triggering OR by triggering with an insufficient consequent; do not assume either classification for every iteration.'
        request['messages'][1]['content']=json.dumps(body)
        return request


def join_results(parts):
    group=merge_ledgers([p['group'] for p in parts])
    return dict(healthy=all(p['healthy'] for p in parts),group=group,counts=loop.counts(group),
                feedback=[f for p in parts for f in p['feedback']],health=[h for p in parts for h in p['health']])


def causal_request(windows):
    req=read(P34/'plan_request.preview.json');body=json.loads(req['messages'][1]['content'])
    # Only observed causal inputs to applicability; current output values are
    # reserved for later property checking, not replaced with invented values.
    body['windows']=[dict(id=w['id'],anchor_sample={k:w['anchor_sample'][k] for k in ('cycle','rst','mvalid','mready')},
        check_sample={k:w['check_sample'][k] for k in ('cycle','rst')}) for w in windows]
    body['projection_scope']='Applicability depends on a previously established output obligation and whether reset interrupts it. Current output validity, payload and input-side activity are intentionally absent. They are checked separately during SVA replay. No observations are invented.'
    body['prior_actual_model_plan']=read(R34/'plan/model_call/applicability_plan.json')
    body['prior_actual_rejection']=read(R34/'plan/decision.json')
    body['feedback_scope']='The rejection is actual development feedback for the original nine windows. Additional windows are new native development observations. The complete expected-answer table is not supplied.'
    req['messages'][1]['content']=json.dumps(body)
    return req


def prepare(out):
    loop.prepare(out);snapshot(out)
    initial=read(P34/'shared_initial.json');old_cases=read(P34/'target_cases.json')
    old_path=portable(read(P34/'baseline_binding.json')['path']);old=read(old_path)
    new_cases=[]
    for depth in (4,8):
        for mode in extension.MODES:
            seed=35001+len(new_cases)
            new_cases.append(dict(id=f'dev35:s{seed}:d{depth}:{mode}',depth=depth,pipeline=2,mode=mode,
                rows=stimulus(seed,17),split='development',source='new_native_development'))
    with extension.installed():
        new=loop.replay(initial,out/'core/new_development',new_cases)
        assert new['healthy'] and new['counts']['misses']==4
        combined=join_results([old,new]);target_cases=old_cases+new_cases
        dump(out/'target_baseline.json',combined);dump(out/'target_cases.json',target_cases)
        windows=read(P34/'windows.public.json');expected=read(P34/'applicability.expected.private.json')
        info=loop.inspect(new['group']['ledger'])
        for key in sorted(info['misses']):
            row=info['rows'][key];source=portable(row['source_directory'])/'replay.json'
            cert=certificate(read(source),row['cycle']);fixed=certificate(read(source.parent.parent/'correct/replay.json'),row['cycle'])
            assert cert['applicability']==fixed['applicability']=='required'
            ident=f'w{len(windows)}'
            windows.append(dict(id=ident,anchor_sample=cert['samples'][0],check_sample=cert['samples'][1]))
            expected.append(dict(id=ident,**cert,source=str(source),source_sha256=digest(source),category=row['variant']))
        assert len(windows)==13
        dump(out/'windows.public.json',windows);dump(out/'expected.private.json',expected)
        controls=[]
        for name,path,slot,want in (
            ('bad',loop.ROOT/'deliverables/research33_real_20261021_r01/s3203/core/v0/model_call/candidate.json','a4',False),
            ('good',loop.ROOT/'deliverables/research32_real_20261021_r01/s3209/core/frozen_candidate.json','a2',True)):
            replay=loop.replay(read(path),out/'core'/name,target_cases)
            verdict=native_target_gate(combined,replay,slot)
            dump(out/f'{name}_control_gate.json',verdict);assert verdict['accepted']==want
            controls.append(dict(name=name,source=str(path),sha256=digest(path),accepted=verdict['accepted'],counts=replay['counts']))
    fixture=dict(windows=[{k:r[k] for k in ('id','anchor_cycle','check_cycle','applicability')} for r in expected])
    assert validate_plan(fixture,expected)['accepted']
    fixture['windows'][1]['applicability']='not_required'
    assert not validate_plan(fixture,expected)['accepted']
    # This fixture checks the validator only, not model performance.
    dump(out/'qualification.json',dict(passed=True,controls=controls,windows=13,targets=8,model_calls=0,fixture_scope='unit tests only, not model output'))
    dump(out/'shared_initial.json',initial)
    full_binding=read(PREP/'s3203/baseline_binding.json');full_path=portable(full_binding['result_path'])
    assert digest(full_path)==full_binding['result_sha256']
    dump(out/'full_baseline.json',join_results([read(full_path),new]))
    dump(out/'full_cases.json',read(PREP/'s3203/cases.json')+new_cases)
    settings=read(P34/'model_config.json');settings['max_model_calls']=2
    dump(out/'model_config.json',settings);dump(out/'request.preview.json',causal_request(windows))
    dump(out/'protocol.json',dict(maximum_calls=4,maximum_plan_calls=2,maximum_sva_calls=2,retries=0,
        endpoint=settings['remote_url'],model=settings['remote_model'],
        previous_unused_call='One research34 call remains conditional on its passed plan; reassignment must be explicitly authorized.',
        feedback='Actual prior development rejection is supplied; no successful SVA or full expected table inserted.',
        gates='All 13 applicability labels pass; edited property triggers/detects all 8 target rows; complete history gate; freeze; fresh holdout including fair drain.',
        independent='New short/long valid, reset, ordering and fair-drain inputs only after acceptance/freeze. No adaptation to tests.',
        limits='One selected FIFO artificial-fault task, finite oracle scope, no stable cross-seed or global guarantee.'))
    dump(out/'prepared_hashes.json',{p.relative_to(out).as_posix():digest(p) for p in out.glob('*.json')})
    dump(out/'local_cost.json',cost_audit(out,artifacts(out)))
    print('PREPARED',dict(windows=13,targets=8,model_calls=0),flush=True)


def refresh(source,out):
    """Reuse unchanged executed native qualification after a model-only change."""
    assert read(source/'qualification.json')['passed']
    changes=[n for n,h in read(source/'source_snapshot/hashes.json').items() if digest(loop.ROOT/'scripts'/n)!=h]
    assert changes==['research35_campaign.py'],changes
    old=ast.parse((source/'source_snapshot/research35_campaign.py').read_text())
    new=ast.parse(Path(__file__).read_text())
    for name in ('prepare','join_results','causal_request','holdout'):
        nodes=[next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name) for tree in (old,new)]
        assert ast.dump(nodes[0])==ast.dump(nodes[1]),'native_or_preview_protocol_changed:'+name
    loop.prepare(out);snapshot(out)
    for p in source.glob('*.json'):
        if p.name not in ('prepared_hashes.json','local_cost.json'):shutil.copy2(p,out/p.name)
    assert read(out/'request.preview.json')==causal_request(read(out/'windows.public.json'))
    dump(out/'qualification_reuse.json',dict(source=str(source),qualification_sha256=digest(source/'qualification.json'),
        source_manifest_sha256=digest(source/'prepared_hashes.json'),new_native_commands=0,
        reason='Only model feedback conclusion and this resealing command changed. Native preparation and holdout generator ASTs are identical; actual source snapshot remains in original preparation.'))
    dump(out/'prepared_hashes.json',{p.relative_to(out).as_posix():digest(p) for p in out.glob('*.json')})
    dump(out/'local_cost.json',cost_audit(out,artifacts(out)))
    print('REFRESHED_WITH_REUSED_NATIVE_QUALIFICATION',flush=True)


def holdout(out,candidate,development,extra_exposed_hashes=(),fixed_split=None):
    from research21_cases import independent_cases
    from research28_cases import cases as valid_cases
    from research29_drain import cases as drain_cases,assess
    seed=secrets.randbelow(2**31);fresh=valid_cases(seed,True)+independent_cases(seed)
    for depth in (4,8):
        for duration in (9,17,24):
            for mode in extension.MODES:
                n=seed+len(fresh)
                fresh.append(dict(id=f'independent35:{n}:d{depth}:{duration}:{mode}',depth=depth,pipeline=2,mode=mode,
                    rows=stimulus(n,duration),split='independent_test'))
    drains=drain_cases(seed+1)
    if fixed_split is not None:
        # A common batch may be replayed only after all compared versions freeze.
        seed=fixed_split['seed']
        fresh=fixed_split['boundary_cases']
        drains=fixed_split['drain_cases']
    used={loop.sha(c['rows']) for c in development}
    used.update(extra_exposed_hashes)
    published=read(loop.ROOT/'deliverables/research32_real_report_20261021_r02/results.json')['prior_exposed_inputs']
    paths=[portable(r['path']) for r in published]+[loop.ROOT/f'deliverables/research{n}_real_20261021_r01/independent/split.json' for n in (32,33)]
    for path in paths:
        data=read(path)
        used.update([loop.sha(data)] if path.name=='stimulus.json' else [loop.sha(c['rows']) for c in (data if isinstance(data,list) else data['cases'])])
    assert not used&{loop.sha(c['rows']) for c in fresh+drains}
    dump(out/'independent/split.json',dict(seed=seed,boundary_cases=fresh,drain_cases=drains,
        frozen_hash=loop.sha(candidate),usage='no_feedback_no_selection',created_after_freeze=True,
        extra_exposed_input_hashes=sorted(extra_exposed_hashes),shared_frozen_batch=fixed_split is not None))
    boundary=loop.replay(candidate,out/'independent/boundary',fresh)
    drain=loop.replay(candidate,out/'independent/drain',drains)
    drain_check=assess(out/'independent/drain',drains,drain)
    dump(out/'independent/drain_assessment.json',drain_check)
    combined=join_results([boundary,drain])
    for row in combined['group']['ledger']:row['split']='independent_test'
    dump(out/'independent/combined.json',combined)
    m=metrics(combined)
    finite_pass=combined['healthy'] and drain_check['passed'] and all(
        v['detections']>0 and v['triggers']>0 and not any(v[k] for k in ('misses','false_positives','unknown')) for v in m['obligations'].values())
    dump(out/'independent/summary.json',dict(metrics=m,all_five_pass_on_first_attributed_evidence=finite_pass,
        distinct_inputs=len({loop.sha(c['rows']) for c in fresh+drains}),scenarios=len(fresh+drains),
        scope='Finite first-attribution evidence only; subsequent attribution unknowns remain. Not a global proof.'))


def run(prep,out,authorization):
    auth=read(authorization);protocol=read(prep/'protocol.json')
    assert auth['authorized_calls']==4 and auth['endpoint']==protocol['endpoint'] and auth['run_output']==out.relative_to(loop.ROOT).as_posix()
    for n,h in read(prep/'prepared_hashes.json').items():assert digest(prep/n)==h,n
    for n,h in read(prep/'source_snapshot/hashes.json').items():assert digest(loop.ROOT/'scripts'/n)==h,n
    loop.prepare(out);snapshot(out);shutil.copy2(authorization,out/'authorization.json');dump(out/'protocol.json',protocol)
    initial=read(prep/'shared_initial.json');current=initial;models=[];status='not_started'
    try:
        request=read(prep/'request.preview.json');settings=read(prep/'model_config.json')
        model=PlanModel(out/'plan',settings,request);models.append(model);plan_ok=False
        for i in range(2):
            _,plan=model.call(out/'plan'/f'v{i}'/'model_call',initial,'stall_stability',{},'causal_applicability_repair')
            verdict=validate_plan(plan,read(prep/'expected.private.json'));dump(out/'plan'/f'v{i}'/'decision.json',verdict)
            if verdict['accepted']:plan_ok=True;break
            # Actual failed labels and machine rejection become development feedback.
            body=json.loads(request['messages'][1]['content']);body.update(prior_actual_model_plan=plan,prior_actual_rejection=verdict)
            request=copy.deepcopy(request);request['messages'][1]['content']=json.dumps(body);model.payload=request
        if not plan_ok:status='applicability_unresolved';return
        model=EvidenceModel(out/'sva',settings,plan);models.append(model)
        before=read(prep/'full_baseline.json');feedback=initial_feedback(before)
        with extension.installed():
            for i in range(2):
                version=out/'core'/f'v{i}'
                call,candidate=model.call(version/'model_call',current,'stall_stability',feedback,'core_fresh_boundary_repair')
                verdict=dict(accepted=False,reasons=[call.get('proposal_rejection',dict(kind='unusable_model_output'))]);small=None
                if candidate:
                    edit=read(version/'model_call/model_edit.json')
                    small=loop.replay(candidate,version/'target_native',read(prep/'target_cases.json'))
                    verdict=native_target_gate(read(prep/'target_baseline.json'),small,edit['assertion_id'])
                    dump(version/'target_gate.json',verdict)
                    if verdict['accepted']:
                        full=loop.replay(candidate,version/'history_native',read(prep/'full_cases.json'))
                        verdict=gate.decide(before['group']['ledger'],full['group']['ledger'],sorted(loop.inspect(before['group']['ledger'])['misses'])) if full.get('group') else dict(accepted=False,reasons=[dict(kind='native_unavailable')])
                        verdict['accepted']=bool(verdict['accepted'] and full['healthy'])
                        dump(version/'historical_gate.json',verdict)
                dump(version/'decision.json',verdict)
                if verdict['accepted']:
                    current=candidate;break
                feedback.update(actual_rejection=verdict,transport_or_interface_diagnostic=call)
                if small and small.get('feedback'):feedback['actual_native_evidence']=small['feedback']
            loop.freeze(out/'core',current,'terminal_before_new_independent_inputs')
            if loop.sha(current)==loop.sha(initial):status='sva_refinement_unresolved';return
            holdout(out,current,read(prep/'full_cases.json'));status='accepted_and_independent_completed'
    except BaseException:
        status='execution_exception';raise
    finally:
        if not (out/'core/freeze.json').exists():loop.freeze(out/'core',current,'retained_after_failed_trial')
        calls=[c for m in models for c in m.calls]
        dump(out/'model_cost.json',dict(calls=len(calls),prompt_tokens=sum(c.get('prompt_tokens') or 0 for c in calls),completion_tokens=sum(c.get('completion_tokens') or 0 for c in calls),usage_unavailable=sum(c.get('prompt_tokens') is None or c.get('completion_tokens') is None for c in calls)))
        dump(out/'outcome.json',dict(status=status,calls=len(calls),accepted=loop.sha(current)!=loop.sha(initial),frozen_hash=loop.sha(current)))
        print('TERMINAL',status,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('prepare','refresh','run'));p.add_argument('--out',type=Path,required=True);p.add_argument('--prepared',type=Path);p.add_argument('--authorization',type=Path)
    a=p.parse_args();out=a.out.resolve();assert loop.ROOT in out.parents
    if a.action=='prepare':prepare(out)
    elif a.action=='refresh':refresh(a.prepared.resolve(),out)
    else:run(a.prepared.resolve(),out,a.authorization.resolve())
