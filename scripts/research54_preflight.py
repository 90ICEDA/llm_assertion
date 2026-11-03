"""Offline verification before separately authorized complementary synthesis."""
import argparse
import json
from pathlib import Path
from unittest.mock import patch
import research54_complementary_sva as g


def run(prep,out):
    out.mkdir(parents=True,exist_ok=False);checks=[]
    def check(name,ok):checks.append(dict(name=name,passed=bool(ok)));assert ok,name
    for n,h in g.read(prep/'sealed.json').items():check('seal:'+n,g.old.digest(prep/n)==h)
    for n,h in g.read(prep/'source_hashes.json').items():check('source:'+n,g.old.digest(g.ROOT/'scripts'/n)==h)
    c=g.components(prep)
    check('old_plan_rejected',not c['original_plan_verdict']['accepted'])
    check('only_op_subjudgment_valid',c['op_certificate']['accepted'])
    check('270_measured_branch_detections',c['branch_detections_retained']==270)
    current=g.read(prep/'shared_initial.json');feedback=g.read(prep/'initial_feedback.json')
    with patch('urllib.request.build_opener',side_effect=AssertionError('network_forbidden')):
        model=g.Model(out/'transport_metadata_only',prep)
        request=model._payload(current,None,feedback,'sva')
        check('exact_sealed_request',request==g.read(prep/'request.preview.json'))
        body=json.loads(request['messages'][1]['content'])
        check('actual_op_rule_preserved',body['actual_model_op_rule']==c['actual_op_rule'])
        check('actual_op_judgments_preserved',body['actual_model_op_membership']==c['actual_op_membership'])
        check('current_branch_original_model_predicate',body['current_assertions']['assertions'][0]==g.read(prep/'protected_branch.json'))
        check('no_local_expected_answer',not any(k in body for k in ('expected','expected.private','correct_answers')))
        check('two_call_cap',model.config['max_model_calls']==2)
        check('zero_calls',model.calls==[])
    for n,h in g.read(g.P53/'sealed.json').items():check('old_prepare_unchanged:'+n,g.old.digest(g.P53/n)==h)
    check('research53_outcome_unchanged',g.read(g.R53/'outcome.json')['status']=='plan_not_accepted')
    g.dump(out/'result.json',dict(passed=True,checks=checks,model_calls=0,new_native_calls=0))
    print('COMPLEMENT_PREFLIGHT',len(checks),'passed',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prepared',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();run(a.prepared.resolve(),a.out.resolve())
