"""Replay the actual failed-interface diagnostic through the fixed feedback path.

No model invocation. Does not reclassify either rejected real proposal.
"""
import argparse
import json
from pathlib import Path
import shutil
import research17_loop as loop
from research38_history_feedback import complete_feedback, payload
from research34_campaign import digest
from research37_local import assemble_replacement


def main(out):
    out.mkdir(parents=True,exist_ok=False)
    root=loop.ROOT/'deliverables/research38_real_20261022_r01'
    prep=loop.ROOT/'deliverables/research38_prepare_20261022_r01'
    version=root/'core/v0'
    call=loop.read(version/'model_call/result.json')
    verdict=loop.read(version/'decision.json')
    fixed=complete_feedback(None,verdict,call)
    old=json.loads(loop.read(root/'core/v1/model_call/request.json')['messages'][1]['content'])['previous_native_diagnostics']
    request=payload(loop.read(prep/'shared_initial.json'),fixed,loop.read(prep/'verified_plan.json'),loop.read(prep/'model_config.json'))
    actual=json.loads(request['messages'][1]['content'])['previous_native_diagnostics']
    checks=dict(real_interface_error=call['candidate_error']['detail']=='interface_unknown:rst',
                old_feedback_lacked_exact_error='interface_unknown:rst' not in json.dumps(old),
                new_feedback_preserves_exact_error=actual['interface_diagnostic']['candidate_error']==call['candidate_error'],
                native_not_claimed=actual['native_replay_performed'] is False,
                no_predicate_generated='assertions' not in actual,
                failure_not_reclassified=verdict['accepted'] is False,
                real_repeated_operands=loop.read(root/'core/v1/model_call/model_edit.json')['assertions']==loop.read(version/'model_call/model_edit.json')['assertions'])
    initial=loop.read(prep/'shared_initial.json')
    for name,edit in (
        ('keep',dict(operation='keep',assertion_id='',assertions=[],reason='fixture')),
        ('wrong_obligation_slot',dict(operation='replace_one',assertion_id='a0',assertions=[],reason='fixture'))):
        try:
            assemble_replacement(edit,initial)
            checks[name+'_rejected_before_native']=False
        except AssertionError:
            checks[name+'_rejected_before_native']=True
    loop.dump(out/'verification.json',dict(passed=all(checks.values()),checks=checks,model_calls=0,native_calls=0,
        source_result_sha256=digest(version/'model_call/result.json'),source_request_sha256=digest(root/'core/v1/model_call/request.json'),
        scope='Actual archived diagnostic replay; no new model repair or acceptance claim.'))
    loop.dump(out/'corrected_feedback.json',fixed)
    loop.dump(out/'request.preview.json',request)
    shutil.copy2(__file__,out/'check_source.py')
    print(dict(passed=all(checks.values()),checks=len(checks),model_calls=0),flush=True)
    assert all(checks.values())


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    main(a.out.resolve())
