"""Offline checks for the decoded-sample adapter and inherited real campaign."""
import argparse
import copy
import json
from pathlib import Path
from unittest.mock import patch
import research53_decoded_applicability as g


def run(prep,out):
    out.mkdir(parents=True,exist_ok=False);checks=[]
    def check(name,ok):
        checks.append(dict(name=name,passed=bool(ok)));assert ok,name
    for n,h in g.read(prep/'sealed.json').items():check('sealed:'+n,g.prior.old.digest(prep/n)==h)
    for n,h in g.read(prep/'source_hashes.json').items():check('source:'+n,g.prior.old.digest(g.ROOT/'scripts'/n)==h)
    for n,h in g.read(g.P52/'sealed.json').items():check('research52_preserved:'+n,g.prior.old.digest(g.P52/n)==h)
    check('old_failure_preserved',g.read(g.R52/'outcome.json')['status']=='plan_not_accepted')
    context=g.source_check(prep);fixture=g.fixture(context);verdict=g.validate(fixture,context)
    current=g.read(prep/'shared_initial.json')
    with patch('urllib.request.build_opener',side_effect=AssertionError('network_forbidden')):
        model=g.Model(out/'transport_metadata_only',prep)
        req=model._payload(None,None,None,'plan')
        check('actual_first_payload_equals_sealed',req==g.read(prep/'plan_request.preview.json'))
        body=json.loads(req['messages'][1]['content'])
        check('public_decoded_fields_exact',body['windows']==context['public'])
        check('no_expected_applicability_labels',all(set(w)=={'id','instruction_hex','sample','decoded','measured'} for w in body['windows']))
        check('no_private_answer_or_sva',body['current_assertions'] is None and 'expected' not in body and 'verified_model_plan' not in body)
        model.stage='sva';model.output_kind='sva'
        try:model._payload(current,None,None,'sva')
        except ValueError:check('missing_plan_blocks_sva',True)
        else:raise AssertionError('missing_plan_allowed')
        bad=copy.deepcopy(fixture);bad['rules']['op_bit28_illegal']['bit_index']=31
        model.plan=bad;model.verdict=verdict
        try:model._payload(current,None,None,'sva')
        except ValueError:check('wrong_rule_forged_pass_blocks_sva',True)
        else:raise AssertionError('forged_plan_allowed')
        model.plan=fixture;model.verdict=verdict
        local=model._payload(current,None,None,'sva');b=json.loads(local['messages'][1]['content'])
        check('model_plan_retained_no_translation',b['verified_model_plan']==fixture and b['current_assertions']==current)
        check('sva_parameters',local['seed']==5301 and local['max_tokens']==model.config['options']['num_predict']==2048)
        check('zero_calls',model.calls==[])
    h=g.read(prep/'baseline/history/result.json');s=g.read(prep/'baseline/search/result.json')
    check('complete_baseline_reused_by_identity',g.prior.combine(h,s)==g.read(prep/'baseline_full.json'))
    check('same420_targets_and270_protected',h['counts']['misses']+s['counts']['misses']==420 and h['counts']['detections']+s['counts']['detections']==270)
    check('native_decode_qualification',g.read(prep/'decode_check.json')['passed'])
    # Exercise inherited save path with a local duplicate fixture, no model call.
    model.stage='sva';folder=out/'duplicate_fixture_ONLY';folder.mkdir()
    repeated=g.read(g.prior.R51/'v2/model_call/model_edit.json')
    candidate,status=model.save_decoded_output(folder,repeated,current,'unused_local_test_marker')
    check('inherited_duplicate_gate_rejects_before_native',candidate is None and status=='duplicate_rejected_before_native')
    g.dump(out/'result.json',dict(passed=True,checks=checks,model_calls=0,new_native_calls=0,
        local_fixture_payload_not_saved=True,duplicate_fixture_is_archived_failed_model_edit_not_new_generation=True))
    print('DECODED_PREFLIGHT',len(checks),'passed; model calls0')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prepared',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();run(a.prepared.resolve(),a.out.resolve())
