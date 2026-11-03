"""Separate trigger and consequence; execute model rules on native samples.

No model answer is repaired. The independently certified port-history oracle
remains authoritative. Private positive/negative fixtures never enter requests.
"""
import argparse
import copy
import json
from pathlib import Path
import research76_schema_continuation as prior

old=prior.old
b,ROOT,read,dump=prior.b,prior.ROOT,prior.read,prior.dump
P=ROOT/'deliverables/research76_prepare_20261024_r01'
R=ROOT/'deliverables/research76_real_20261024_r01'


def schema(rows):
    obj=lambda props:dict(type='object',properties=props,required=list(props),additionalProperties=False)
    sample=lambda:dict(type='string',enum=['anchor','check'])
    bit=lambda:dict(type='integer',enum=[0,1])
    return obj(dict(
        trigger_condition=obj(dict(sample=sample(),mvalid=bit(),mready=bit(),rst=bit())),
        reset_cancellation=obj(dict(sample=sample(),rst=bit())),
        hold_requirement=obj(dict(sample=sample(),mvalid=bit(),
            data_reference=prior.schema(rows)['properties']['data_reference'])),
        windows=prior.schema(rows)['properties']['windows']))


def fixture_rules():
    # Private local oracle fixture, never an automatically repaired model plan.
    return dict(trigger_condition=dict(sample='anchor',mvalid=1,mready=0,rst=0),
        reset_cancellation=dict(sample='check',rst=1),
        hold_requirement=dict(sample='check',mvalid=1,data_reference=dict(sample='anchor',signal='mdata')))


def evaluate(rules,window):
    """Execute exactly the returned model rule, even when it is incorrect."""
    pick=lambda name:window[name+'_sample']
    t=rules['trigger_condition'];c=rules['reset_cancellation'];h=rules['hold_requirement']
    triggered=all(pick(t['sample'])[key]==t[key] for key in ('mvalid','mready','rst'))
    cancelled=triggered and pick(c['sample'])['rst']==c['rst']
    applicability='cancelled' if cancelled else 'required' if triggered else 'not_required'
    required=applicability=='required';ref=h['data_reference']
    expected=pick(ref['sample'])[ref['signal']] if required else None
    actual=pick(h['sample'])
    satisfied=actual['mvalid']==h['mvalid'] and actual['mdata']==expected
    check=pick('check');anchor=pick('anchor')
    return dict(id=window['id'],anchor_cycle=anchor['cycle'],check_cycle=check['cycle'],
        applicability=applicability,expected_data=expected,observed_data=check['mdata'],
        observed_valid=check['mvalid'],
        verdict=('satisfied' if satisfied else 'violated') if required else 'not_applicable')


def validate(value,rows):
    if not rows or len({r['id'] for r in rows})!=len(rows):
        return dict(accepted=False,reasons=[dict(kind='truth_inventory')])
    if not prior.conforms(value,schema(rows)):
        return dict(accepted=False,reasons=[dict(kind='typed_output_schema')])
    reasons=[];details=[];actual={w['id']:w for w in value['windows']}
    if len(actual)!=len(rows) or set(actual)!={r['id'] for r in rows}:
        reasons.append(dict(kind='window_inventory'))
    for key,want in fixture_rules().items():
        if value[key]!=want:reasons.append(dict(kind='incorrect_rule_binding',field=key))
    for row in rows:
        path=Path(row['source'])
        if b.search.digest(path)!=row['source_sha256']:
            reasons.append(dict(kind='native_source_changed',id=row['id']));continue
        fresh,cert=old.sem.truth(path,row['check_cycle']);truth=dict(id=row['id'],**fresh)
        samples=dict(id=row['id'],anchor_sample=cert['samples'][0],check_sample=cert['samples'][1])
        if row['expected']!=truth or row['public']!=samples:
            reasons.append(dict(kind='certificate_or_sample_changed',id=row['id']));continue
        executed=evaluate(value,samples);reported=actual.get(row['id'])
        for kind,left,right in [('rule_vs_certificate',executed,truth),
                                ('window_vs_certificate',reported,truth),
                                ('rule_vs_window',executed,reported)]:
            if left!=right:
                reasons.append(dict(kind=kind,id=row['id']))
        details.append(dict(id=row['id'],executed_rule=executed,model_window=reported,
            rule_matches_certificate=executed==truth,window_matches_certificate=reported==truth,
            rule_matches_window=executed==reported))
    return dict(accepted=not reasons,reasons=reasons,details=details,windows=len(rows),
        scope='Development sample consistency only; native SVA and unchanged105-history admission remain mandatory.')


def unlock(template,plan,verdict,rows):
    actual=validate(plan,rows)
    if not actual['accepted'] or actual!=verdict:raise ValueError('rule_consistency_not_passed')
    request=copy.deepcopy(template);body=json.loads(request['messages'][1]['content'])
    body.pop('actual_previous_attempt',None)
    body['verified_model_hold_plan']=plan
    body['hold_development_samples']=[r['public'] for r in rows]
    body['execution_contract']='Implement your actual verified trigger_condition, reset_cancellation and hold_requirement as an AST edit. The trigger sample establishes pending output; the requirement sample checks retention. They are distinct roles. Native target, trigger and historical checks determine acceptance; no evaluator repairs a predicate or timing.'
    request['messages'][1]['content']=json.dumps(body)
    return request


def local_checks(rows,template):
    good=dict(**fixture_rules(),windows=[r['expected'] for r in rows]);tests=[]
    def check(name,value,want=False):
        verdict=validate(value,rows);assert verdict['accepted']==want,name
        if not want:
            try:unlock(template,value,dict(accepted=True),rows)
            except ValueError:pass
            else:raise AssertionError('failed_plan_unlocked:'+name)
        tests.append(name)
        return verdict
    check('private oracle fixture only',good,True)
    un=unlock(template,good,validate(good,rows),rows)
    assert json.loads(un['messages'][1]['content'])['verified_model_hold_plan']==good
    tests.append('unlock preserves model plan exactly')
    # Map the real failed global rule without correcting its sample or window labels.
    previous=read(R/'plan/v0/model_call/hold_plan.json')
    mapped=copy.deepcopy(good)
    mapped['hold_requirement']=dict(sample=previous['valid_requirement']['sample'],
        mvalid=previous['valid_requirement']['value'],data_reference=previous['data_reference'])
    mapped['windows']=previous['windows']
    v=check('actual research76 rule mapped without correction',mapped)
    assert any(r['kind']=='rule_vs_window' and r['id']=='w5' for r in v['reasons'])
    tests.append('actual valid withdrawal exposes rule-window inconsistency')
    # Internal agreement alone is insufficient: wrong rule plus wrong labels rejects.
    mapped['windows']=[evaluate(mapped,r['public']) for r in rows]
    v=check('internally consistent but spec-wrong rule and labels',mapped)
    assert not any(r['kind']=='rule_vs_window' for r in v['reasons'])
    tests.append('independent truth rejects internally consistent wrong plan')
    paths=[('trigger_condition','sample'),('trigger_condition','mvalid'),('trigger_condition','mready'),
           ('trigger_condition','rst'),('reset_cancellation','sample'),('reset_cancellation','rst'),
           ('hold_requirement','sample'),('hold_requirement','mvalid'),
           ('hold_requirement','data_reference','sample'),('hold_requirement','data_reference','signal')]
    for path in paths:
        for mutation in ('wrong','missing','array','boolean'):
            v=copy.deepcopy(good);node=v
            for k in path[:-1]:node=node[k]
            key=path[-1];x=node[key]
            if mutation=='missing':del node[key]
            elif mutation=='array':node[key]=[x]
            elif mutation=='boolean':node[key]=True
            elif type(x) is int:node[key]=1-x
            elif x in ('anchor','check'):node[key]='check' if x=='anchor' else 'anchor'
            else:node[key]='ref_expected'
            check('/'.join(path)+':'+mutation,v)
    for i,row in enumerate(good['windows']):
        for field in ('anchor_cycle','check_cycle','applicability','expected_data','observed_data','observed_valid','verdict'):
            v=copy.deepcopy(good);x=row[field]
            v['windows'][i][field]=x+1 if type(x) is int else 0 if x is None else 'unknown'
            check(f'window{i}:{field}',v)
    for kind in ('duplicate','missing'):
        v=copy.deepcopy(good)
        if kind=='duplicate':v['windows'][-1]=v['windows'][0]
        else:v['windows'].pop()
        check('window:'+kind,v)
    assert not validate(good,[])['accepted'];tests.append('empty certificates reject')
    changed=copy.deepcopy(rows);changed[0]['public']['check_sample']['mvalid']^=1
    assert not validate(good,changed)['accepted'];tests.append('unbound public sample rejected')
    return dict(passed=True,checks=tests,actual_research76_rejection=validate(dict(
        trigger_condition=fixture_rules()['trigger_condition'],reset_cancellation=fixture_rules()['reset_cancellation'],
        hold_requirement=dict(sample=previous['valid_requirement']['sample'],mvalid=previous['valid_requirement']['value'],data_reference=previous['data_reference']),
        windows=previous['windows']),rows),fixture_only=True,model_calls=0)


def prepare(out):
    old.verify(P)
    assert read(R/'outcome.json')['model_calls']==1 and not read(R/'outcome.json')['plan_passed']
    out.mkdir(parents=True,exist_ok=False);rows=read(P/'windows.private.json')
    request=copy.deepcopy(read(P/'plan_request.preview.json'));body=json.loads(request['messages'][1]['content'])
    body['response_schema']=schema(rows)
    body['task']='Choose separate sampled trigger, reset cancellation and held-output requirement rules, then evaluate every supplied window. No SVA yet.'
    body['instruction']='Return a JSON instance, not this schema. Choose ONE scalar per enum. trigger_condition describes when an output becomes pending: its mvalid/mready/rst fields are an AND at its selected sample. reset_cancellation describes cancellation of a pending output. hold_requirement describes what the pending output must retain at its selected sample, using the selected data_reference. Do not confuse the condition creating a pending obligation with the later check of that obligation. The selected hold sample must satisfy BOTH its mvalid value and equality of its mdata to the selected reference data. For each window, first evaluate your trigger, then cancellation, then the hold requirement. Report not_required when trigger is false, cancelled when trigger and cancellation are true, otherwise required. expected_data is the selected reference when required, otherwise null; observed_data/observed_valid always report check_sample. A required verdict is satisfied only when both selected hold requirements pass. Your global rules and all window labels must agree and will also be checked independently against native samples. No SVA or additional fields.'
    body['previous_actual_rejection']=dict(model_valid_requirement=read(R/'plan/v0/model_call/hold_plan.json')['valid_requirement'],
        diagnostic='The previous global rule was rejected for incorrect_reference_binding of valid_requirement despite its per-window labels passing. Resolve the trigger-versus-requirement role; do not merely repeat independently plausible labels.')
    request['messages'][1]['content']=json.dumps(body);dump(out/'plan_request.preview.json',request)
    for n in ('windows.private.json','windows.public.json','window_cases.json','cases.json','history_cases.json','initial.json','sva_template.json','excluded_inputs.json','protected.json','model_config.json'):
        dump(out/n,read(P/n))
    dump(out/'local_checks.json',local_checks(rows,read(P/'sva_template.json')))
    # Re-audit actual archived native logs; no recompile or new generation claimed.
    controls=[];checks=[];raw=0;source=prior.P
    with b.extension.installed():
        for item in read(source/'native_qualification.json')['controls']:
            path=Path(item['source']);assert b.search.digest(path)==item['source_sha256']
            folder=source/'native_controls'/item['name'];candidate=read(path)
            raw+=old.raw_replay(folder,read(P/'window_cases.json'),candidate,checks)
            gate=old.sem.native_windows(read(folder/'result.json'),rows,read(P/'window_cases.json'),folder)
            assert gate==item['gate'] and gate['accepted']==item['expected']
            controls.append(dict(name=item['name'],accepted=gate['accepted'],expected=item['expected']))
    dump(out/'native_reaudit.json',dict(passed=True,controls=controls,raw_records=raw,checks=checks,new_native_calls=0))
    bindings=read(P/'source_bindings.json')
    for path in (R/'plan/v0/model_call/hold_plan.json',R/'plan/v0/decision.json',R/'outcome.json',source/'native_qualification.json'):
        bindings[str(path)]=b.search.digest(path)
    dump(out/'source_bindings.json',bindings)
    dump(out/'protocol.json',dict(maximum_calls=2,plan_maximum=1,sva_maximum=1,retries=0,
        endpoint=read(P/'protocol.json')['endpoint'],model=read(P/'protocol.json')['model'],
        change='Separate trigger, cancellation and requirement; execute actual model rules and compare rules/windows/independent certificates. Same11 windows, native target gates,14 public,105 history and fresh56 holdout.',
        permission='Requires1 new judgment slot and explicit transfer of research76 unused conditional1 SVA slot. No remote calls during preparation.',
        scope='Observed development continuation; not a new randomized mechanism-benefit comparison.'))
    dump(out/'code_versions.json',{str(p):b.search.digest(p) for p in (ROOT/'scripts').glob('*.py')})
    dump(out/'sealed.json',{p.name:b.search.digest(p) for p in out.glob('*.json')})
    print('PREPARED',len(read(out/'local_checks.json')['checks']),'checks',raw,'re-audited native records',flush=True)


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
        folder=out/'plan/v0';call,plan=planner.call(folder/'model_call',initial,'stall_stability',{},'trigger_requirement_consistency')
        if call['status']!='response_received':status='transport_stopped';return
        verdict=validate(plan,rows);dump(folder/'decision.json',verdict);plan_passed=verdict['accepted']
        print('PLAN',plan_passed,flush=True)
        if not plan_passed:return
        dump(out/'accepted_plan.json',plan)
        request=unlock(read(prep/'sva_template.json'),plan,verdict,rows)
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
