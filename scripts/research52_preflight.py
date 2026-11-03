"""No-network seal, transport payload, source-binding and stage-gate checks."""
import argparse
import copy
import json
from pathlib import Path
from unittest.mock import patch
import research52_ibex_bit_gate as gate


def run(prep,out):
    out.mkdir(parents=True,exist_ok=False);checks=[]
    def check(name,ok):
        checks.append(dict(name=name,passed=bool(ok)));assert ok,name
    for name,h in gate.read(prep/'sealed.json').items():check('seal:'+name,gate.old.digest(prep/name)==h)
    for name,h in gate.read(prep/'source_hashes.json').items():check('source:'+name,gate.old.digest(gate.ROOT/'scripts'/name)==h)
    for name,h in gate.read(gate.P51/'sealed.json').items():check('research51_unchanged:'+name,gate.old.digest(gate.P51/name)==h)
    check('prior_failure_not_relabelled',gate.read(gate.R51/'outcome.json')['status']=='no_accepted_version')
    with patch('urllib.request.build_opener',side_effect=AssertionError('network_forbidden')):
        model=gate.Model(out/'transport_metadata_only',prep)
        request=model._payload(None,None,None,'plan')
        check('exact_plan_preview',request==gate.read(prep/'plan_request.preview.json'))
        body=json.loads(request['messages'][1]['content'])
        check('plan_has_no_current_sva',body['current_assertions'] is None)
        check('plan_has_public_windows_only',body['windows']==gate.read(prep/'windows.public.json'))
        check('no_private_answer_in_plan',not any(k in body for k in ('expected','expected.private','verified_model_plan','correct_answers')))
        expected=gate.source_check(prep);verdict=gate.validate(expected,expected)
        model.stage='sva';model.output_kind='sva'
        current=gate.read(prep/'shared_initial.json')
        try:model._payload(current,None,None,'sva')
        except ValueError:check('missing_actual_plan_blocks_sva_payload',True)
        else:raise AssertionError('missing_plan_allowed')
        bad=copy.deepcopy(expected);bad['op_illegal_bit']=31
        model.plan=bad;model.verdict=verdict
        try:model._payload(current,None,None,'sva')
        except ValueError:check('forged_pass_for_wrong_bit_blocked',True)
        else:raise AssertionError('forged_plan_allowed')
        with patch.object(gate.old,'digest',return_value='changed_source'):
            try:gate.verified_plan(prep,expected,verdict)
            except AssertionError:check('changed_native_source_blocks_sva',True)
            else:raise AssertionError('changed_source_allowed')
        model.plan=expected;model.verdict=verdict
        local_only=model._payload(current,None,None,'sva')
        checked_body=json.loads(local_only['messages'][1]['content'])
        check('fixture_payload_keeps_exact_plan_no_rewrite',checked_body['verified_model_plan']==expected)
        check('effective_sva_parameters',local_only['seed']==model.config['options']['seed']==5201 and local_only['max_tokens']==model.config['options']['num_predict']==2048)
        check('zero_model_calls',model.calls==[])
        # No fixture-derived SVA payload or answer table is persisted as a preview.
    h=gate.read(prep/'baseline/history/result.json');s=gate.read(prep/'baseline/search/result.json')
    check('full_native_baseline',h['healthy'] and s['healthy'])
    check('all151_transactions',len(gate.read(prep/'history_cases.json'))==115 and len(gate.read(prep/'search_cases.json'))==36)
    check('actual420_misses_270_protected',h['counts']['misses']+s['counts']['misses']==420 and h['counts']['detections']+s['counts']['detections']==270)
    check('native_unknown_and_false_alarms_zero',all(r['counts'][k]==0 for r in (h,s) for k in ('unknown','false_positives')))
    gate.dump(out/'result.json',dict(passed=True,checks=checks,model_calls=0,new_native_calls=0,
        local_fixture_payload_not_saved=True,source_hash=gate.old.digest(Path(__file__))))
    print('PREFLIGHT',len(checks),'passed; no model calls')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prepared',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();run(a.prepared.resolve(),a.out.resolve())
