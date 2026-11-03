"""No-network preflight for fresh OP synthesis and its live decoder gate."""
import argparse
import copy
import json
from pathlib import Path
from unittest.mock import patch
import research56_fresh_op as g


def run(prep,out):
    out.mkdir(parents=True,exist_ok=False);checks=[]
    def check(name,ok):checks.append(dict(name=name,passed=bool(ok)));assert ok,name
    for n,h in g.read(prep/'sealed.json').items():check('sealed/'+n,g.old.digest(prep/n)==h)
    for n,h in g.read(prep/'source_hashes.json').items():check('current_source/'+n,g.old.digest(g.ROOT/'scripts'/n)==h)
    for n,h in g.read(prep/'failure_binding.json').items():check('actual_evidence/'+n,g.old.digest(g.ROOT/n)==h)
    g.previous.prior.components(prep)
    current=g.read(prep/'shared_initial.json');feedback=g.read(prep/'initial_feedback.json')
    with patch('urllib.request.build_opener',side_effect=AssertionError('network_forbidden')):
        model=g.Model(out/'transport_metadata_only',prep)
        request=model._payload(current,None,feedback,'sva')
        check('exact_first_request',request==g.read(prep/'request.preview.json'))
        check('actual_seed',model.config['options']['seed']==request['seed']==5601)
        local=g.read(g.P55/'qualification/correct_local_control/candidate.json')
        value=dict(operation='replace_op',reason='LOCAL API CONTROL; not a model response',assertions=[
            {k:a[k] for k in ('antecedent','consequent','timing','obligations')} for a in local['assertions'][1:]])
        folder=out/'local_interface_control';folder.mkdir()
        candidate,status=model.save_decoded_output(folder,value,current,'local_fixture_no_credential')
        check('novel_local_predicate_not_blocked',candidate is not None)
        check('branch_exact',candidate['assertions'][0]==current['assertions'][0])
        check('op_exact_without_rewrite',candidate['assertions'][1:]==local['assertions'][1:])
        changed=copy.deepcopy(value);changed['reason']='Changed reason only'
        changed['assertions'][0]['antecedent']=' ( '+changed['assertions'][0]['antecedent']+' ) '
        folder=out/'local_repeated_control';folder.mkdir()
        repeated,status=model.save_decoded_output(folder,changed,current,'local_fixture_no_credential')
        check('within_run_repeat_ignores_reason_and_whitespace',repeated is None)
        check('new_duplicate_reason',g.read(folder/'novelty_gate.json')['reasons'][0]['kind']=='previously_rejected_op_set')
        check('no_real_calls',model.calls==[])
    body=json.loads(request['messages'][1]['content'])
    check('current_only_branch',body['current_assertions']['assertions']==[current['assertions'][0]])
    check('both_original_rtl_revisions',set(body['rtl'])=={'before','after'})
    check('real_op_plan',body['actual_model_op_rule']==g.read(prep/'component_certificate.json')['actual_op_rule'])
    check('native_failures_retained',body['actual_development_feedback']['measured_latest_gate']['counts']['misses']==12)
    check('full151_preserved',len(g.read(prep/'history_cases.json'))==115 and len(g.read(prep/'search_cases.json'))==36)
    check('private_answer_not_top_level',not any(k in body for k in ('expected','expected.private','correct_answers')))
    check('no_independent_test',(prep/'independent').exists() is False)
    check('old_outcome_preserved',g.read(g.R55/'outcome.json')['status']=='no_accepted_sva')
    g.dump(out/'result.json',dict(passed=True,checks=checks,new_model_calls=0,new_native_calls=0,
        local_controls_not_model_outputs=True))
    print('FRESH_OP_PREFLIGHT',len(checks),'passed',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prepared',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();run(a.prepared.resolve(),a.out.resolve())
