"""Verified hold interpretation -> genuine SVA -> unchanged admission -> fresh test.

Preparation is local. A new explicit <=4 authorization is required for run:
at most two interpretation and, only after passing, two SVA calls. No retries.
"""
import argparse
import copy
import json
import time
from pathlib import Path
import research75_hold_semantics as sem
import research72_policy as policy
import research74_recovery as old
from research17_report import cost_audit
from research68_result_audit import raw_replay

b,ROOT,read,dump=sem.b,sem.ROOT,sem.read,sem.dump
SEED=7503


class PlanModel(policy.Model):
    output_kind='sampled_hold_plan'
    def save_decoded_output(self,folder,value,current,secret):
        dump(folder/'hold_plan.json',value)
        return value,'hold_plan_received_not_validated'


def exclusion_hashes():
    # Prior complete inventory + the only newer independent batch (research72).
    # Parse input rows solely for hashing, never outcomes or candidate selection.
    p=ROOT/'deliverables/research72_prepare_20261024_r02/excluded_inputs.json'
    values=set(read(p)['input_hashes']);sources=[dict(path=str(p),sha256=b.search.digest(p))]
    path=ROOT/'deliverables/research72_real_20261024_r01/common_independent_split.json'
    data=read(path)
    values.update(b.loop.sha(c['rows']) for c in data['boundary_cases']+data['drain_cases'])
    sources.append(dict(path=str(path),sha256=b.search.digest(path),usage='input hashes only'))
    return values,sources


def plan_request(template,rows):
    request=copy.deepcopy(template);body=json.loads(template['messages'][1]['content'])
    task=dict(task='Interpret the sampled output-hold obligation before SVA generation. No SVA in this stage.',
        specification='A valid output not accepted at the anchor sample must retain valid and its presented payload at the next sample, including a ready rise, unless reset cancels the pending output. Input presentation is not acceptance. A queue-head correctness obligation is separate from output stability.',
        rtl_and_common_contract=body['rtl_and_common_contract'],windows=[r['public'] for r in rows],
        response_schema=dict(data_reference=dict(sample=['anchor','check'],signal=['mdata','ref_expected','sdata']),
            valid_requirement=dict(sample=['anchor','check'],value='integer 0 or 1'),
            windows=[dict(id='given ID',anchor_cycle='integer',check_cycle='integer',
                applicability=['required','cancelled','not_required','unknown'],expected_data='integer when required, otherwise null',
                observed_data='integer at check sample',observed_valid='integer at check sample',
                verdict=['satisfied','violated','not_applicable','unknown'])]),
        instruction='Choose the reference sample and signal required by the specification, then calculate each sampled judgment. expected_data is the required held value, not a prediction. Provide every window once, no extra fields. Anchor and check fields refer only to their explicitly named samples. No expected labels or evaluator answers are provided.')
    request['messages']=[dict(role='system',content='Interpret sampled hardware obligations accurately. Return only the specified JSON object, no SVA or prose.'),dict(role='user',content=json.dumps(task))]
    request.update(seed=SEED,max_tokens=2048)
    return request


def prepare(out):
    out.mkdir(parents=True,exist_ok=False)
    rows,cases=sem.windows();template=read(ROOT/'deliverables/research74_prepare_20261024_r01/request.preview.json')
    # Do not anchor generation on the previous incorrect predicate or its reason.
    body=json.loads(template['messages'][1]['content']);body.pop('actual_previous_attempt',None)
    template['messages'][1]['content']=json.dumps(body);template.update(seed=SEED,max_tokens=2048)
    initial=read(sem.SOURCE/'initial.json')
    dump(out/'initial.json',initial);dump(out/'windows.public.json',[r['public'] for r in rows]);dump(out/'windows.private.json',rows)
    dump(out/'window_cases.json',cases)
    for name in ('cases.json','history_cases.json'):dump(out/name,read(sem.SOURCE/name))
    dump(out/'sva_template.json',template);dump(out/'plan_request.preview.json',plan_request(template,rows))
    dump(out/'local_checks.json',sem.local_checks(rows,template))
    controls=[];audit_checks=[];native_logs=0
    with b.extension.installed():
        for name,path,want in [
            ('old_queue_head_next',sem.SOURCE/'c04/candidate.json',False),
            ('old_queue_head_current',ROOT/'deliverables/research74_real_20261024_r01/core/v1/model_call/candidate.json',False),
            ('archived_positive_not_model_input',sem.SOURCE/'c05/candidate.json',True)]:
            candidate=read(path);folder=out/'native_controls'/name
            result=b.loop.replay(candidate,folder,cases)
            verdict=sem.native_windows(result,rows,cases,folder)
            dump(folder/'window_gate.json',verdict)
            assert verdict['accepted']==want,(name,verdict)
            native_logs+=raw_replay(folder,cases,candidate,audit_checks)
            controls.append(dict(name=name,source=str(path),source_sha256=b.search.digest(path),expected=want,gate=verdict))
    dump(out/'native_qualification.json',dict(passed=True,controls=controls,raw_native_records=native_logs,checks=audit_checks,
        scope='Archived native controls only; not new model success. Positive control never supplied to model.'))
    excluded,sources=exclusion_hashes()
    for name in ('cases.json','history_cases.json','window_cases.json'):excluded.update(b.loop.sha(c['rows']) for c in read(out/name))
    dump(out/'excluded_inputs.json',dict(input_hashes=sorted(excluded),sources=sources))
    dump(out/'protected.json',old.screen.protected())
    source_paths=[sem.SOURCE/'baseline_public/result.json',sem.SOURCE/'baseline_history/result.json']
    source_paths += [Path(r['source']) for r in rows]
    dump(out/'source_bindings.json',{str(p):b.search.digest(p) for p in source_paths})
    settings=b.campaign.settings(SEED,2);dump(out/'model_config.json',settings)
    dump(out/'protocol.json',dict(maximum_calls=4,plan_maximum=2,sva_maximum=2,retries=0,seed=SEED,
        endpoint=settings['remote_url'],model=settings['remote_model'],timeout_seconds=300,
        interpretation='All sampled reference, validity, applicability and verdict fields checked against independent port-history certificates; no SVA call after failed plan.',
        generation='Only actual passing model plan and development windows added to same initial candidate and schema. No archived successful predicate, evaluator plan fixture or independent data.',
        native='Window gate plus unchanged14 public current_decision and unchanged105 history decision_for. Unknown rejects. Accepted version frozen before fresh independent generation.',
        stop='Each stage stops at pass; transport failure terminal; total <=4. Rejections retain original partial baseline. No repair from independent failures.',
        holdout='Existing56-scenario generator, depths2/4/8, five actual obligation exposures; prior independent inputs excluded by hashes only. Generate only after acceptance and freeze.',
        scope='Selected retrospective regression continuation with added public helper; not a fresh randomized mechanism-effect estimate.'))
    dump(out/'cost.json',cost_audit(out,b.paired.files(out)))
    dump(out/'code_versions.json',{str(p):b.search.digest(p) for p in (ROOT/'scripts').glob('*.py')})
    dump(out/'sealed.json',{p.name:b.search.digest(p) for p in out.glob('*.json')})
    print('PREPARED',len(rows),'windows',len(cases),'cases',native_logs,'native records',flush=True)


def verify(prep):
    for name,h in read(prep/'sealed.json').items():assert b.search.digest(prep/name)==h,name
    for name,h in read(prep/'code_versions.json').items():assert b.search.digest(Path(name))==h,name
    for name,h in read(prep/'source_bindings.json').items():assert b.search.digest(Path(name))==h,name
    assert old.screen.protected()==read(prep/'protected.json')


def run(prep,out,authorization):
    verify(prep);auth=read(authorization);protocol=read(prep/'protocol.json')
    assert auth['authorized_calls']==4 and auth['prepared_sha256']==b.search.digest(prep/'sealed.json')
    assert auth['endpoint']==protocol['endpoint'] and auth['model']==protocol['model']
    assert auth['run_output']==out.relative_to(ROOT).as_posix()
    out.mkdir(parents=True,exist_ok=False);dump(out/'authorization.json',auth);dump(out/'protocol.json',protocol)
    initial=read(prep/'initial.json');current=initial;rows=read(prep/'windows.private.json');models=[]
    accepted_plan=None;accepted=False;independent=False;status='plan_failed';reserved=0
    def reserve(stage,i):
        nonlocal reserved
        assert i<2 and reserved<4
        reserved+=1;dump(out/'attempt_budget.json',dict(reserved=reserved,maximum=4,stage=stage,iteration=i))
    try:
        plan_source=read(prep/'plan_request.preview.json')
        planner=PlanModel(out/'plan_model',read(prep/'model_config.json'),plan_source);models.append(planner)
        for i in range(2):
            folder=out/'plan'/f'v{i}';reserve('plan',i)
            call,value=planner.call(folder/'model_call',initial,'stall_stability',{},'sampled_hold_interpretation')
            if call['status']!='response_received':status='transport_stopped';return
            verdict=sem.validate(value,rows);dump(folder/'decision.json',verdict)
            print('PLAN',i,verdict['accepted'],flush=True)
            if verdict['accepted']:
                accepted_plan=value;dump(out/'accepted_plan.json',value);break
            if i==0:
                planner.request=copy.deepcopy(plan_source)
                body=json.loads(planner.request['messages'][1]['content'])
                # Report errors without supplying the private expected answer table.
                body['rejected_model_plan']=value
                body['actual_rejection']=[{k:v for k,v in r.items() if k!='expected'} for r in verdict['reasons']]
                planner.request['messages'][1]['content']=json.dumps(body)
                dump(folder/'next_request.preview.json',planner.request)
        if accepted_plan is None:return
        template=sem.unlock(read(prep/'sva_template.json'),accepted_plan,verdict,rows)
        dump(out/'sva_request.preview.json',template)
        model=policy.Model(out/'sva_model',read(prep/'model_config.json'),template);models.append(model)
        baseline=read(sem.SOURCE/'baseline_public/result.json');historical=read(sem.SOURCE/'baseline_history/result.json')
        seen={b.interface.executable_hash(initial)};last_edit=None;status='sva_failed'
        with b.extension.installed():
            for i in range(2):
                folder=out/'core'/f'v{i}';reserve('sva',i)
                call,candidate=model.call(folder/'model_call',current,'stall_stability',{},'verified_sampled_hold_generation')
                if call['status']!='response_received':status='transport_stopped';return
                edit=read(folder/'model_call/model_edit.json') if (folder/'model_call/model_edit.json').exists() else None
                repeated=bool(candidate and b.interface.executable_hash(candidate) in seen)
                if candidate:seen.add(b.interface.executable_hash(candidate))
                window_result=b.loop.replay(candidate,folder/'windows',read(prep/'window_cases.json')) if candidate and not repeated else None
                wg=sem.native_windows(window_result,rows,read(prep/'window_cases.json'),folder/'windows')
                dump(folder/'window_gate.json',wg)
                small=b.loop.replay(candidate,folder/'public',read(prep/'cases.json')) if window_result and wg['accepted'] else None
                plain=b.paired.current_decision(baseline,small,edit) if small else dict(accepted=False,reasons=wg['reasons']+[dict(kind='repeated_or_interface' if not window_result else 'hold_native_gate')])
                full=b.loop.replay(candidate,folder/'history',read(prep/'history_cases.json')) if plain['accepted'] else None
                decision=policy.decision_for(plain,full,historical,True)
                dump(folder/'decision.json',decision);current=b.journal(folder,current,candidate,decision)
                accepted=decision['accepted'];print('SVA',i,accepted,flush=True)
                if accepted:break
                diagnostic=policy.feedback_for(small or window_result,full,decision,call,edit,last_edit,True)
                diagnostic['actual_sampled_hold_gate']=wg;dump(folder/'next_feedback.json',diagnostic)
                if i==0:
                    req=b.campaign.request_from(template,current,SEED,diagnostic)
                    # Revalidate unchanged plan; preserve this actual failure diagnostic.
                    check=sem.validate(accepted_plan,rows);assert check['accepted']
                    body=json.loads(req['messages'][1]['content']);assert body['verified_model_hold_plan']==accepted_plan
                    model.request=req;dump(folder/'next_request.preview.json',req)
                last_edit=edit
            if not accepted:return
            b.loop.freeze(out/'core',current,'accepted_before_fresh_independent')
            development=sum((read(prep/n) for n in ('cases.json','history_cases.json','window_cases.json')),[])
            b.holdout(out,current,development,set(read(prep/'excluded_inputs.json')['input_hashes']))
            independent=True
            passed=read(out/'independent/summary.json')['all_five_pass_on_first_attributed_evidence']
            status='accepted_independent_passed' if passed else 'accepted_independent_failed_no_feedback'
    except BaseException as exc:
        status='execution_exception';dump(out/'exception.json',dict(type=type(exc).__name__,detail=str(exc)));raise
    finally:
        if not (out/'core/freeze.json').exists():b.loop.freeze(out/'core',current,'retained_terminal_no_independent')
        dump(out/'outcome.json',dict(status=status,plan_passed=accepted_plan is not None,accepted=accepted,
            independent_performed=independent,model_calls=sum(len(m.calls) for m in models),reserved=reserved,
            frozen_hash=b.loop.sha(current),protected_unchanged=old.screen.protected()==read(prep/'protected.json')))
        dump(out/'cost.json',cost_audit(out,b.paired.files(out)));print('TERMINAL',status,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','run','verify']);p.add_argument('--prepared',type=Path);p.add_argument('--out',type=Path);p.add_argument('--authorization',type=Path)
    a=p.parse_args()
    if a.action=='prepare':prepare(a.out.resolve())
    elif a.action=='verify':verify(a.prepared.resolve());print('VERIFIED',flush=True)
    else:run(a.prepared.resolve(),a.out.resolve(),a.authorization.resolve())
