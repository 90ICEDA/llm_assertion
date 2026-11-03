"""Typed plan schema, unchanged semantic truth and native acceptance.

One judgment call, then one SVA call only if judgment passes. Requires explicit
transfer of research75's unused SVA-only slots; never silently relabels them.
"""
import argparse
import copy
import json
from pathlib import Path
import research75_campaign as old

b,ROOT,read,dump=old.b,old.ROOT,old.read,old.dump
P=ROOT/'deliverables/research75_prepare_20261024_r01'
R=ROOT/'deliverables/research75_real_20261024_r01'


def schema(rows):
    text=lambda values:dict(type='string',enum=values)
    obj=lambda props:dict(type='object',properties=props,required=list(props),additionalProperties=False)
    row=obj(dict(id=text([r['id'] for r in rows]),anchor_cycle=dict(type='integer'),check_cycle=dict(type='integer'),
        applicability=text(['required','cancelled','not_required','unknown']),
        expected_data=dict(type=['integer','null'],description='If required, the held payload read from your selected data_reference; otherwise null.'),
        observed_data=dict(type='integer'),observed_valid=dict(type='integer',enum=[0,1]),
        verdict=text(['satisfied','violated','not_applicable','unknown'])))
    return obj(dict(data_reference=obj(dict(sample=text(['anchor','check']),signal=text(['mdata','ref_expected','sdata']))),
        valid_requirement=obj(dict(sample=text(['anchor','check']),value=dict(type='integer',enum=[0,1]))),
        windows=dict(type='array',minItems=len(rows),maxItems=len(rows),items=row)))


def conforms(value,s):
    kinds=s.get('type');kinds=[kinds] if isinstance(kinds,str) else kinds
    types={'object':dict,'array':list,'integer':int,'string':str,'null':type(None)}
    if not any(type(value) is types[t] for t in kinds):return False
    if 'enum' in s and value not in s['enum']:return False
    if isinstance(value,dict):
        if set(value)!=set(s['required']):return False
        return all(conforms(v,s['properties'][k]) for k,v in value.items())
    if isinstance(value,list):return s['minItems']<=len(value)<=s['maxItems'] and all(conforms(v,s['items']) for v in value)
    return True


def validate(value,rows):
    if not conforms(value,schema(rows)):return dict(accepted=False,reasons=[dict(kind='typed_output_schema')])
    return old.sem.validate(value,rows)


def prepare(out):
    old.verify(P);assert read(R/'outcome.json')['model_calls']==2 and not read(R/'outcome.json')['plan_passed']
    out.mkdir(parents=True,exist_ok=False);rows=read(P/'windows.private.json')
    request=copy.deepcopy(read(P/'plan_request.preview.json'));body=json.loads(request['messages'][1]['content'])
    body['response_schema']=schema(rows)
    body['instruction']+=' Return an instance conforming to response_schema, not the schema itself. Each enum requires ONE scalar choice; never return its option array. Compute expected_data from your chosen reference, and judge whether the observed check output meets the requirement. Payload correctness against queue head is a different requirement.'
    request['messages'][1]['content']=json.dumps(body)
    dump(out/'plan_request.preview.json',request)
    good=old.sem.expected_plan(rows);tests=[]
    assert conforms(good,schema(rows)) and validate(good,rows)['accepted'];tests.append('private positive fixture only')
    for i in (0,1):
        value=read(R/f'plan/v{i}/model_call/hold_plan.json')
        assert not conforms(value,schema(rows));tests.append(f'actual old response {i} fails scalar schema')
        fixed_shape=copy.deepcopy(value)
        fixed_shape['data_reference']=dict(sample='check',signal='mdata')
        fixed_shape['valid_requirement']=dict(sample='check',value=1)
        assert conforms(fixed_shape,schema(rows)) and not validate(fixed_shape,rows)['accepted']
        tests.append(f'local format-only control {i} still fails semantic truth')
        fixed_shape['data_reference']=dict(sample='anchor',signal='mdata')
        assert not validate(fixed_shape,rows)['accepted'];tests.append(f'local reference-only control {i} still fails numeric/verdict truth')
    invalid=copy.deepcopy(good);invalid['valid_requirement']['value']=True
    assert not conforms(invalid,schema(rows));tests.append('strict Boolean/integer separation')
    for n in ('windows.private.json','windows.public.json','window_cases.json','cases.json','history_cases.json','initial.json','sva_template.json','excluded_inputs.json','protected.json','model_config.json'):
        dump(out/n,read(P/n))
    dump(out/'checks.json',dict(passed=True,checks=tests,model_calls=0,new_native_calls=0,
        native_reuse=dict(path=str(P/'native_qualification.json'),sha256=b.search.digest(P/'native_qualification.json'),
                         raw_records=30,old_false_controls_rejected=True,positive_control_passed=True)))
    dump(out/'source_bindings.json',read(P/'source_bindings.json'))
    dump(out/'protocol.json',dict(maximum_calls=2,plan_maximum=1,sva_maximum=1,retries=0,
        endpoint=read(P/'protocol.json')['endpoint'],model=read(P/'protocol.json')['model'],
        change='Typed scalar schema only; identical11 windows, semantic validator, native window gate,14 public and105 history, fresh56 holdout.',
        permission='Explicit transfer required: two remaining research75 slots were restricted to SVA after judgment pass. Here one judgment and one conditional SVA; no additional total slots.',
        scope='Selected development continuation, no new mechanism-effect estimate; formatting alone never establishes semantics.'))
    dump(out/'code_versions.json',{str(p):b.search.digest(p) for p in (ROOT/'scripts').glob('*.py')})
    dump(out/'sealed.json',{p.name:b.search.digest(p) for p in out.glob('*.json')})
    print('TYPED_SCHEMA_PREPARED',len(tests),'checks',flush=True)


def run(prep,out,authpath):
    old.verify(prep);auth=read(authpath);protocol=read(prep/'protocol.json')
    assert auth['authorized_calls']==2 and auth['prepared_sha256']==b.search.digest(prep/'sealed.json')
    assert auth['endpoint']==protocol['endpoint'] and auth['model']==protocol['model'] and auth['run_output']==out.relative_to(ROOT).as_posix()
    out.mkdir(parents=True,exist_ok=False);dump(out/'authorization.json',auth);dump(out/'protocol.json',protocol)
    initial=read(prep/'initial.json');current=initial;rows=read(prep/'windows.private.json');models=[]
    accepted=False;plan_passed=False;independent=False;status='plan_failed'
    try:
        planner=old.PlanModel(out/'plan_model',read(prep/'model_config.json'),read(prep/'plan_request.preview.json'));models.append(planner)
        dump(out/'attempt_budget.json',dict(reserved=1,maximum=2,stage='plan'))
        folder=out/'plan/v0';call,plan=planner.call(folder/'model_call',initial,'stall_stability',{},'typed_hold_interpretation')
        if call['status']!='response_received':status='transport_stopped';return
        verdict=validate(plan,rows);dump(folder/'decision.json',verdict);plan_passed=verdict['accepted']
        print('PLAN',plan_passed,flush=True)
        if not plan_passed:return
        dump(out/'accepted_plan.json',plan)
        request=old.sem.unlock(read(prep/'sva_template.json'),plan,old.sem.validate(plan,rows),rows)
        dump(out/'sva_request.preview.json',request)
        model=old.policy.Model(out/'sva_model',read(prep/'model_config.json'),request);models.append(model)
        folder=out/'core/v0';dump(out/'attempt_budget.json',dict(reserved=2,maximum=2,stage='sva'))
        call,candidate=model.call(folder/'model_call',current,'stall_stability',{},'verified_hold_generation')
        if call['status']!='response_received':status='transport_stopped';return
        edit=read(folder/'model_call/model_edit.json') if (folder/'model_call/model_edit.json').exists() else None
        status='sva_failed'
        with b.extension.installed():
            wr=b.loop.replay(candidate,folder/'windows',read(prep/'window_cases.json')) if candidate else None
            wg=old.sem.native_windows(wr,rows,read(prep/'window_cases.json'),folder/'windows');dump(folder/'window_gate.json',wg)
            small=b.loop.replay(candidate,folder/'public',read(prep/'cases.json')) if wg['accepted'] else None
            before=read(old.sem.SOURCE/'baseline_public/result.json');historic=read(old.sem.SOURCE/'baseline_history/result.json')
            plain=b.paired.current_decision(before,small,edit) if small else dict(accepted=False,reasons=wg['reasons'])
            full=b.loop.replay(candidate,folder/'history',read(prep/'history_cases.json')) if plain['accepted'] else None
            decision=old.policy.decision_for(plain,full,historic,True);dump(folder/'decision.json',decision)
            current=b.journal(folder,current,candidate,decision);accepted=decision['accepted'];print('SVA',accepted,flush=True)
            if not accepted:return
            b.loop.freeze(out/'core',current,'accepted_before_new_independent')
            development=sum((read(prep/n) for n in ('cases.json','history_cases.json','window_cases.json')),[])
            b.holdout(out,current,development,set(read(prep/'excluded_inputs.json')['input_hashes']));independent=True
            status='accepted_independent_passed' if read(out/'independent/summary.json')['all_five_pass_on_first_attributed_evidence'] else 'accepted_independent_failed_no_feedback'
    except BaseException as exc:
        status='execution_exception';dump(out/'exception.json',dict(type=type(exc).__name__,detail=str(exc)));raise
    finally:
        if not (out/'core/freeze.json').exists():b.loop.freeze(out/'core',current,'retained_terminal_no_independent')
        dump(out/'outcome.json',dict(status=status,plan_passed=plan_passed,accepted=accepted,independent_performed=independent,
            model_calls=sum(len(m.calls) for m in models),frozen_hash=b.loop.sha(current),protected_unchanged=old.old.screen.protected()==read(prep/'protected.json')))
        dump(out/'cost.json',old.cost_audit(out,b.paired.files(out)));print('TERMINAL',status,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','run']);p.add_argument('--prepared',type=Path);p.add_argument('--authorization',type=Path);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    if a.action=='prepare':prepare(a.out.resolve())
    else:run(a.prepared.resolve(),a.out.resolve(),a.authorization.resolve())
