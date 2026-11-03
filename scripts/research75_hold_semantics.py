"""Sample-bound output-hold interpretation, before real SVA generation.

Independent port-history certificates supply truth. No assertion defines the
answers. Local fixtures and archived native controls never enter model requests.
"""
import copy
import json
from pathlib import Path
import research74_recovery as prior
from research34_applicability import certificate

b,ROOT,read,dump=prior.b,prior.ROOT,prior.read,prior.dump
SOURCE=ROOT/'deliverables/research73_discriminating_20261024_r01'
AUDIT=ROOT/'deliverables/research73_audit_20261024_r01'
FIELDS={'id','anchor_cycle','check_cycle','applicability','expected_data','observed_data','observed_valid','verdict'}


def truth(path,cycle):
    record=read(path);cert=certificate(record,cycle)
    assert cert['applicability']!='unknown',str(path)
    a,c=cert['samples'];required=cert['applicability']=='required'
    expected=a['mdata'] if required else None
    verdict=('satisfied' if c['mvalid']==1 and c['mdata']==expected else 'violated') if required else 'not_applicable'
    if required:
        assert len(cert['oracle_checks'])==1
        assert cert['oracle_checks'][0]['passed']==(verdict=='satisfied')
    return dict(anchor_cycle=cert['anchor_cycle'],check_cycle=cert['check_cycle'],applicability=cert['applicability'],
        expected_data=expected,observed_data=c['mdata'],observed_valid=c['mvalid'],verdict=verdict),cert


def windows():
    inventory=read(SOURCE/'history_cases.json');public_cases=read(SOURCE/'cases.json')
    regressions=read(AUDIT/'c04_evidence.json')['evidence'];selected=[];cases={}
    def add(path,cycle,category):
        path=Path(path);expected,cert=truth(path,cycle)
        case=read(path.parent.parent/'case.json');cases[case['id']]=case
        ident=f'w{len(selected)}'
        selected.append(dict(id=ident,category=category,source=str(path),source_sha256=b.search.digest(path),
            scenario_id=case['id'],mode=read(path)['mode'],check_cycle=cycle,expected=dict(id=ident,**expected),
            public=dict(id=ident,anchor_sample=cert['samples'][0],check_sample=cert['samples'][1])))
    # Both confirmed trigger classes, chosen by sorted evidence ID, not tests.
    for triggered in (False,True):
        row=next(e['after'] for e in regressions if e['kind']=='confirmed_lost_detection' and
                 any(a['trigger'] for a in e['after']['native']['assertions'])==triggered)
        path=b.gate.portable(row['source_directory'])/'replay.json'
        add(path,row['cycle'],'confirmed_loss_triggered_'+str(triggered))
        add(path.parent.parent/'correct/replay.json',row['cycle'],'paired_legal_control_'+str(triggered))
    # Stable output unequal to queue head: an actual obligation-level FP.
    for e in regressions:
        if e['kind']!='new_legal_false_positive':continue
        row=e['after'];path=b.gate.portable(row['source_directory'])/'replay.json'
        expected,cert=truth(path,row['cycle']);a,c=cert['samples']
        if expected['applicability']=='required' and expected['verdict']=='satisfied' and c['mdata']!=c['ref_expected']:
            add(path,row['cycle'],'stable_output_not_queue_head');break
    else:raise AssertionError('no_real_queue_head_contrast')
    info=b.loop.inspect(read(SOURCE/'baseline_public/result.json')['group']['ledger'])
    row=info['rows'][sorted(info['misses'])[0]]
    path=b.gate.portable(row['source_directory'])/'replay.json'
    add(path,row['cycle'],'public_valid_target')
    add(path.parent.parent/'correct/replay.json',row['cycle'],'public_target_legal_control')
    # Select reset, idle and input-idle legal hold directly from correct RTL.
    needed={'cancelled','reset_release','idle','required_input_idle'}
    for i,case in enumerate(inventory):
        path=SOURCE/f'baseline_history/case_{i}/correct/replay.json';record=read(path)
        for sample in record['trace'][1:]:
            expected,cert=truth(path,sample['cycle']);a,c=cert['samples'];category=None
            if expected['applicability']=='cancelled':category='cancelled'
            elif a['rst']==1 and c['rst']==0:category='reset_release'
            elif expected['applicability']=='not_required' and not a['rst'] and not c['rst'] and not a['mvalid']:category='idle'
            elif expected['applicability']=='required' and not a['svalid'] and expected['verdict']=='satisfied':category='required_input_idle'
            if category in needed:add(path,sample['cycle'],category);needed.remove(category)
            if not needed:break
        if not needed:break
    assert not needed,needed
    return selected,list(cases.values())


def expected_plan(rows):
    return dict(data_reference=dict(sample='anchor',signal='mdata'),
                valid_requirement=dict(sample='check',value=1),windows=[r['expected'] for r in rows])


def validate(value,rows):
    reasons=[]
    if not rows or len({r['id'] for r in rows})!=len(rows):
        return dict(accepted=False,reasons=[dict(kind='empty_or_duplicate_truth_inventory')])
    if not isinstance(value,dict) or set(value)!={'data_reference','valid_requirement','windows'}:
        return dict(accepted=False,reasons=[dict(kind='plan_schema')])
    for field,want in [('data_reference',dict(sample='anchor',signal='mdata')),('valid_requirement',dict(sample='check',value=1))]:
        if value[field]!=want or (field=='valid_requirement' and (not isinstance(value[field],dict) or type(value[field].get('value')) is not int)):
            reasons.append(dict(kind='incorrect_reference_binding',field=field))
    actual={}
    if not isinstance(value['windows'],list):return dict(accepted=False,reasons=[dict(kind='windows_schema')])
    for w in value['windows']:
        if not isinstance(w,dict) or set(w)!=FIELDS or type(w.get('id')) is not str or w['id'] in actual:
            reasons.append(dict(kind='window_schema_or_duplicate'));continue
        actual[w['id']]=w
    if set(actual)!={r['id'] for r in rows}:reasons.append(dict(kind='window_inventory'))
    for row in rows:
        path=Path(row['source'])
        if b.search.digest(path)!=row['source_sha256']:
            reasons.append(dict(kind='native_source_changed',id=row['id']));continue
        fresh,_=truth(path,row['check_cycle']);expected=dict(id=row['id'],**fresh)
        if expected!=row['expected']:reasons.append(dict(kind='private_truth_changed',id=row['id']));continue
        w=actual.get(row['id'],{})
        for field,want in expected.items():
            if type(w.get(field)) is not type(want) or w.get(field)!=want:
                reasons.append(dict(kind='incorrect_sample_judgment',id=row['id'],field=field,
                    observed=w.get(field),expected=want))
    return dict(accepted=not reasons,reasons=reasons,windows=len(rows),
        scope='Development sample interpretation only; native SVA and105-history checks still mandatory.')


def unlock(template,plan,verdict,rows):
    actual=validate(plan,rows)
    if not actual['accepted'] or actual!=verdict:raise ValueError('hold_interpretation_not_passed')
    request=copy.deepcopy(template);body=json.loads(request['messages'][1]['content'])
    body.pop('actual_previous_attempt',None)
    body['verified_model_hold_plan']=plan
    body['hold_development_samples']=[r['public'] for r in rows]
    body['execution_contract']='Implement your own independently validated sampled hold interpretation as an AST edit. Native checks still determine acceptance. No predicate or timing will be repaired by the evaluator.'
    request['messages'][1]['content']=json.dumps(body)
    return request


def local_checks(rows,template):
    good=expected_plan(rows);checks=[]
    def test(name,value,want=False):
        verdict=validate(value,rows);assert verdict['accepted']==want,name
        if not want:
            try:unlock(template,value,dict(accepted=True),rows)
            except ValueError:pass
            else:raise AssertionError('failed_plan_unlocked')
        checks.append(name)
    test('oracle_fixture_only',good,True)
    for name,reference in [('queue_head',dict(sample='check',signal='ref_expected')),('same_data',dict(sample='check',signal='mdata')),('input_data',dict(sample='anchor',signal='sdata'))]:
        v=copy.deepcopy(good);v['data_reference']=reference;test(name,v)
    for i,w in enumerate(good['windows']):
        for field in FIELDS-{'id'}:
            v=copy.deepcopy(good);del v['windows'][i][field];test(f'{i}:missing:{field}',v)
        for field in ('anchor_cycle','check_cycle','observed_data','observed_valid'):
            for replacement in (w[field]+1,True):
                v=copy.deepcopy(good);v['windows'][i][field]=replacement;test(f'{i}:bad:{field}:{replacement}',v)
        v=copy.deepcopy(good);v['windows'][i]['applicability']='unknown';test(f'{i}:unknown',v)
        v=copy.deepcopy(good);v['windows'][i]['verdict']='violated' if w['verdict']!='violated' else 'satisfied';test(f'{i}:wrong_verdict',v)
        v=copy.deepcopy(good);v['windows'][i]['expected_data']=None if w['expected_data'] is not None else 0;test(f'{i}:wrong_reference_value',v)
    for name in ('missing','duplicate'):
        v=copy.deepcopy(good)
        if name=='missing':v['windows'].pop()
        else:v['windows'].append(v['windows'][0])
        test(name,v)
    unlock(template,good,validate(good,rows),rows)
    return dict(passed=True,checks=checks,fixture_only=True,model_calls=0)


def native_windows(result,rows,cases,folder):
    if not result or not result.get('group'):return dict(accepted=False,reasons=[dict(kind='native_unavailable')])
    info=b.loop.inspect(result['group']['ledger']);failures=[];details=[]
    for w in rows:
        i=next(i for i,c in enumerate(cases) if c['id']==w['scenario_id'])
        p=folder/f'case_{i}'/w['mode']/'replay.json';expect,cert=truth(p,w['check_cycle'])
        assert expect=={k:v for k,v in w['expected'].items() if k!='id'}
        found=[r for r in info['rows'].values() if r['scenario_id']==w['scenario_id'] and r['variant']==w['mode'] and r['cycle']==w['check_cycle'] and r['obligation']=='stall_stability']
        if expect['applicability']!='required':
            details.append(dict(id=w['id'],applicability=expect['applicability'],required=False));continue
        assert len(found)==1,(w['id'],len(found))
        row=found[0];key=row['evidence_id'];required_ok=key in info['triggers'] and key not in info['unknown']
        detected=key in info['detections'] if expect['verdict']=='violated' else key not in info['false_positives']
        okay=required_ok and detected
        detail=dict(id=w['id'],passed=okay,expected=expect,triggered=key in info['triggers'],
            causal_detection=key in info['detections'],false_positive=key in info['false_positives'],unknown=key in info['unknown'])
        details.append(detail)
        if not okay:failures.append(dict(kind='sampled_hold_not_implemented',**detail))
    return dict(accepted=not failures,reasons=failures,details=details)
