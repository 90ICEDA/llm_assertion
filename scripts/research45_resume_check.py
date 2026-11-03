"""Qualify duplicate-ID feedback repair on actual failed-round artifacts."""
import json
from pathlib import Path
import shutil
import research45_campaign as campaign
import research43_paired_ablation as old
import research17_loop as loop

run=loop.ROOT/'deliverables/research45_real_20261022_r01'
prep=loop.ROOT/'deliverables/research45_prepare_20261022_r02'
out=run/'amendments/feedback_scope_v1'
assert loop.read(run/'outcome.json')['status']=='execution_exception'
assert loop.read(run/'outcome.json')['actual_calls']==1
out.mkdir(parents=True,exist_ok=False)
for name in ('outcome.json','cost.json','attempt_budget.json'):
    shutil.copy2(run/name,out/('before_'+name))
version=run/'pilot/core/v0'
small=loop.read(version/'visible_native/result.json')
full=loop.read(version/'history_native/result.json')
decision=loop.read(version/'decision.json')
call=loop.read(version/'model_call/result.json')
edit=loop.read(version/'model_call/model_edit.json')
value=campaign.attempt_feedback(small,full,decision,call,edit)
assert value['counts']==small['counts']
assert value['historical_replay']['counts']==full['counts']
assert value['previous_actual_model_edit']==edit
assert campaign.attempt_feedback(small,None,decision,call,edit).get('historical_replay') is None
common={r['evidence_id'] for r in small['group']['ledger']} & {r['evidence_id'] for r in full['group']['ledger']}
assert common,'actual_duplicate_identity_not_exposed'
request=campaign.request_from(loop.read(prep/'pilot/request.preview.json'),loop.read(prep/'shared_initial.json'),4401,value)
assert json.loads(request['messages'][1]['content'])['actual_previous_attempt']==value
loop.dump(out/'next_request.preview.json',request)
preserved=[p for p in old.files(version) if p.suffix=='.json']
loop.dump(out/'preserved_round0_hashes.json',{p.relative_to(run).as_posix():old.digest(p) for p in preserved})
shutil.copy2(loop.ROOT/'scripts/research45_campaign.py',out/'research45_campaign.py')
loop.dump(out/'amendment.json',dict(reason='Current common case and full-history common case share stable evidence IDs but have different physical source directories. Keep diagnostics separate instead of merging their ledgers.',
    old_campaign_sha256=old.digest(prep/'source_snapshot/research45_campaign.py'),
    new_campaign_sha256=old.digest(loop.ROOT/'scripts/research45_campaign.py'),
    actual_duplicate_ids=len(common),qualification_passed=True,
    unchanged=['model','seed','output_budget','initial_candidate','target_and_history_gates','call_limits','test_isolation'],
    completed_calls_reused=1,remaining_pilot_calls=2,remaining_conditional_ablation_calls=8,
    new_model_calls=0,new_native_calls=0,original_results_preserved=True,
    scope='Implementation bug correction and restart support, recorded after first failure; not a new pristine preregistration or a reset experiment.'))
print('RESUME_QUALIFIED',len(common),'duplicate_ids',flush=True)
