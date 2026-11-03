"""Offline source, sampling, phase-gate and request isolation checks."""
import argparse
import json
from pathlib import Path
from unittest.mock import patch
import research59_phase_gate as g


def run(prep,out):
    out.mkdir(parents=True,exist_ok=False);checks=[]
    def check(name,ok):checks.append(dict(name=name,passed=bool(ok)));assert ok,name
    for n,h in g.read(prep/'sealed.json').items():check('sealed/'+n,g.old.digest(prep/n)==h)
    for n,h in g.read(prep/'source_hashes.json').items():check('code/'+n,g.old.digest(g.ROOT/'scripts'/n)==h)
    for n,h in g.read(prep/'failure_binding.json').items():check('source/'+n,g.old.digest(g.ROOT/n)==h)
    manifest=g.read(prep/'focus.private.json');table=g.read(prep/'phase_table.public.json')
    source=g.read(g.R/'v0/alignment/result.json')
    check('exact12',len(manifest['targets'])==12 and len({(e['sample_id'],json.dumps(e['configuration'],sort_keys=True)) for e in manifest['targets']})==12)
    for e in manifest['targets']:
        row=next(r for r in source['ledger'] if r['evidence_id']==e['source_evidence_id'])
        check('bound/'+e['source_evidence_id'],e==dict(sample_id=row['sample']['sample_id'],sample=row['sample'],configuration=row['configuration'],source_evidence_id=row['evidence_id']))
        check('ISA/'+e['source_evidence_id'],g.old.historical.oracle(row['sample']['instruction'],row['sample']['instr_new'],row['configuration'])==1)
    for t in table:
        actual=[r for r in source['ledger'] if r['sample']==t['sample'] and r['revision']=='before']
        check('public_sampling/'+str(t['sample']['sample_id']),len(actual)==3 and t['configurations']==[r['configuration'] for r in actual] and all(r['observed']==t['before_illegal'] and r['expected']==t['expected_illegal'] for r in actual))
        check('first_held_new/'+str(t['sample']['sample_id']),t['sample']['instr_new']==int(t['sample']['phase']==0))
    for label in ('actual_model','local_positive','local_first_only'):
        folder=prep/'qualification'/label;candidate=g.read(folder/'candidate.json');result=g.read(folder/'native/result.json')
        check('native_raw/'+label,g.prior.diagnostic.audit_native(folder/'native',candidate,prep,'alignment')==240)
        focus=g.focus_gate(result,manifest);gate=g.read(folder/'native/alignment_gate.json')
        check('focus_recomputed/'+label,focus==g.read(folder/'native/focus_gate.json')==gate['focus12'])
        guard=g.prior.prior.native_flow.prior.all_property_guard(result,{rev:g.read(folder/'native'/rev/'result.json') for rev in ('before','after')},candidate)
        check('all_property_guard/'+label,guard==gate['all_property_guard'])
        check('full_small_gate/'+label,gate['accepted']==(g.old.admissible(result) and guard['accepted'] and focus['accepted'] and all(x['accepted'] for x in gate['bindings']))==(label=='local_positive'))
    current=g.read(prep/'shared_initial.json');feedback=g.read(prep/'initial_feedback.json')
    with patch('urllib.request.build_opener',side_effect=AssertionError('network_forbidden')):
        model=g.Model(out/'transport',prep);req=model._payload(current,None,feedback,'sva')
        check('exact_request',req==g.read(prep/'request.preview.json'))
        body=json.loads(req['messages'][1]['content'])
        check('actual_model_candidate',body['current_assertions']==g.read(g.R/'v0/model_call/candidate.json'))
        check('real_sampling_table',body['native_stage_table']==table)
        check('complete_original_RTL',all(body['rtl'][rev][p.name]==p.read_text() for rev in ('before','after') for p in (prep/rev).glob('*.sv')))
        check('correct_plan_unchanged',body['actual_model_op_rule']==g.read(prep/'component_certificate.json')['actual_op_rule'])
        check('no_calls_and_two_cap',not model.calls and model.config['max_model_calls']==2)
        raw=g.read(g.R/'v0/model_call/model_edit.json');folder=out/'repeat';folder.mkdir()
        c,status=model.save_decoded_output(folder,raw,current,'local_fixture')
        check('actual_repeated_proposal_rejected',c is None and status=='previously_measured_or_duplicate_op_rejected')
        check('no_rewrite',g.read(folder/'candidate.json')==g.read(g.R/'v0/model_call/candidate.json'))
    check('full151_retained',g.read(prep/'history_cases.json')==g.read(g.P/'history_cases.json') and g.read(prep/'search_cases.json')==g.read(g.P/'search_cases.json'))
    check('full690_preservation',g.read(prep/'target_preservation.private.json')==g.read(g.P/'target_preservation.private.json'))
    check('no_holdout',not (prep/'independent').exists())
    g.dump(out/'result.json',dict(passed=True,checks=checks,new_model_calls=0,new_native_calls=0))
    print('PHASE_PREFLIGHT',len(checks),'passed',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prepared',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();run(a.prepared.resolve(),a.out.resolve())
