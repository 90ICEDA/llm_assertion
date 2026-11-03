"""Offline audit of sealed evidence, real-transport decoding and native probes."""
import argparse
import copy
import json
from pathlib import Path
from unittest.mock import patch
import research58_preservation_refinement as g


def run(prep,out):
    out.mkdir(parents=True,exist_ok=False);checks=[]
    def check(name,ok):
        checks.append(dict(name=name,passed=bool(ok)));assert ok,name
    for n,h in g.read(prep/'sealed.json').items():check('sealed/'+n,g.old.digest(prep/n)==h)
    for n,h in g.read(prep/'source_hashes.json').items():check('code/'+n,g.old.digest(g.ROOT/'scripts'/n)==h)
    for n,h in g.read(prep/'failure_binding.json').items():check('evidence/'+n,g.old.digest(g.ROOT/n)==h)
    protected=g.read(prep/'target_preservation.private.json')
    check('target_inventory',[len(protected[k]) for k in ('op_bit28_illegal','illegal_branch_persists')]==[420,270])
    pack=g.read(prep/'evidence_pack.json')
    for row in pack['representatives']:
        result=g.read(g.D/row['version']/row['cohort']/'result.json')
        actual=next(r for r in result['ledger'] if r['evidence_id']==row['evidence_id'])
        twin=next(r for r in result['ledger'] if r['sample']==actual['sample'] and r['configuration']==actual['configuration'] and r['revision']!=actual['revision'])
        check('sample/'+row['version']+'/'+row['evidence_id'],row==dict(version=row['version'],kind=row['kind'],cohort=row['cohort'],**g.prior.row_view(actual),paired_actual={actual['revision']:actual['observed'],twin['revision']:twin['observed']}))
        if row['kind']=='lost_target':
            check('lost_target_verified/'+row['evidence_id'],row['paired_actual']['before']!=row['expected'] and row['paired_actual']['after']==row['expected'] and not any(a['causal_detection'] for a in row['assertions']))
        else:check('legal_false_alarm_verified/'+row['evidence_id'],row['expected']==row['observed']==0 and any(a['failed'] for a in row['assertions']))
    for b in g.read(prep/'lost_probe_binding.json'):
        original=next(t for t in g.read(prep/(b['cohort']+'_cases.json')) if t['id']==b['original_id'])
        probe=next(t for t in g.read(prep/'alignment_cases.json') if t['id']==b['replay_id'])
        check('probe_exact/'+str(b['funct3']),probe=={**original,'id':b['replay_id']})
    for label in ('actual_v0','actual_v1','local_control'):
        folder=prep/'qualification'/label
        result=g.read(folder/'native/result.json');candidate=g.read(folder/'candidate.json')
        check('raw_native/'+label,g.diagnostic.audit_native(folder/'native',candidate,prep,'alignment')==len(result['ledger']))
        gate=g.read(folder/'native/alignment_gate.json')
        guard=g.prior.native_flow.prior.all_property_guard(result,{rev:g.read(folder/'native'/rev/'result.json') for rev in ('before','after')},candidate)
        check('guard/'+label,guard==gate['all_property_guard'])
        check('gate/'+label,gate['accepted']==(g.old.admissible(result) and guard['accepted'] and all(w['accepted'] for w in gate['bindings']))== (label=='local_control'))
    current=g.read(prep/'shared_initial.json');raw=g.read(g.R/'v0/model_call/model_edit.json')
    c,labels=g.diagnostic.adapt(raw,current)
    check('label_only',c==g.read(g.D/'v0/candidate.json'))
    for name,edit in [('reserved',lambda v:v['assertions'][0].update(id='a0')),('unknown',lambda v:v['assertions'][0].update(extra=True)),
        ('boolean_label',lambda v:v['assertions'][0].update(id=True)),('bad_identifier',lambda v:v['assertions'][0].update(id='a;')),
        ('missing_predicate',lambda v:v['assertions'][0].pop('antecedent')),('wrong_signal',lambda v:v['assertions'][0].update(antecedent='instr_i')),
        ('duplicate_label',lambda v:v['assertions'].append(copy.deepcopy(v['assertions'][0])))]:
        v=copy.deepcopy(raw);edit(v)
        try:g.diagnostic.adapt(v,current)
        except (ValueError,KeyError,TypeError):check('reject/'+name,True)
        else:raise AssertionError(name)
    with patch('urllib.request.build_opener',side_effect=AssertionError('network_forbidden')):
        model=g.Model(out/'transport',prep)
        req=model._payload(current,None,g.read(prep/'initial_feedback.json'),'sva')
        check('sealed_request_exact',req==g.read(prep/'request.preview.json'))
        body=json.loads(req['messages'][1]['content'])
        check('unabridged_original_rtl',all(body['rtl'][rev][p.name]==p.read_text() for rev in ('before','after') for p in (prep/rev).glob('*.sv')))
        check('fixed_branch_preserved',body['current_assertions']['assertions'][0]==g.read(prep/'protected_branch.json'))
        check('actual_verified_plan',body['actual_model_op_rule']==g.read(prep/'component_certificate.json')['actual_op_rule'])
        check('budget_no_calls',model.config['max_model_calls']==2 and not model.calls)
        try:model._payload(current,None,dict(extra='x'*g.prior.MAX_MESSAGE_BYTES),'sva')
        except RuntimeError:check('reject_oversize_before_network',True)
        else:raise AssertionError('oversize_not_rejected')
    check('independent_not_generated',not (prep/'independent').exists())
    g.dump(out/'result.json',dict(passed=True,checks=checks,new_model_calls=0,new_native_calls=0))
    print('PRESERVATION_PREFLIGHT',len(checks),'passed',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prepared',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();run(a.prepared.resolve(),a.out.resolve())
