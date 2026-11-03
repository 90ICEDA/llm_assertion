"""Qualify prospective feedback retention on the actual48 HTTP400 record.

No response/candidate is generated. The original run and decisions are immutable.
"""
import copy
import json
import shutil
from pathlib import Path
import research48_sva_campaign as c


def main():
    run=c.ROOT/'deliverables/research48_real_20261022_r01'
    out=c.ROOT/'deliverables/research48_feedback_fix_20261022_r01'
    out.mkdir(parents=True,exist_ok=False)
    hashes={str(p):c.common.digest(p) for p in c.common.files(run)}
    v0,v1=run/'core/v0',run/'core/v1'
    actual=c.read(v0/'next_feedback.json');untouched=copy.deepcopy(actual)
    call=c.read(v1/'model_call/result.json');assert call['status']=='service_http_error'
    updated=c.build_feedback(None,None,c.read(v1/'decision.json'),call,None,
        c.read(v0/'model_call/model_edit.json'),c.read(v1/'native_window_gate.json'),actual)
    checks=[]
    def check(name,value):checks.append(dict(name=name,passed=bool(value)));assert value,name
    check('prior_actual_native_kept_exactly',updated['retained_actual_native_feedback']==actual)
    check('prior_target_counts_preserved',updated['retained_actual_native_feedback']['counts']==c.read(v0/'visible_native/result.json')['counts'])
    check('prior_history_counts_preserved',updated['retained_actual_native_feedback']['historical_replay']['counts']==c.read(v0/'history_native/result.json')['counts'])
    check('prior_window_rejection_preserved',updated['retained_actual_native_feedback']['validated_windows_native_rejection']==c.read(v0/'native_window_gate.json'))
    check('failed_transport_not_new_native_run',updated['counts'] is None and 'retention_scope' in updated)
    check('no_mutation_of_saved_feedback',actual==untouched)
    updated['retained_actual_native_feedback']['counts']['misses']=-1
    check('deep_copy_not_alias',actual==untouched)
    empty=c.build_feedback(None,None,c.read(v1/'decision.json'),call,None,None,c.read(v1/'native_window_gate.json'))
    check('no_prior_no_invented_evidence','retained_actual_native_feedback' not in empty)
    small=c.read(v0/'visible_native/result.json');full=c.read(v0/'history_native/result.json')
    new=c.build_feedback(small,full,c.read(v0/'decision.json'),c.read(v0/'model_call/result.json'),
        c.read(v0/'model_call/model_edit.json'),None,c.read(v0/'native_window_gate.json'),actual)
    check('new_native_does_not_recursively_accumulate_old','retained_actual_native_feedback' not in new)
    check('new_native_counts_current',new['counts']==small['counts'])
    check('actual_run_files_unchanged',all(c.common.digest(Path(p))==h for p,h in hashes.items()))
    c.dump(out/'qualification.json',dict(passed=True,checks=checks,model_calls=0,new_native_calls=0,
        scope='Prospective implementation qualification using actual archived transport failure; no revised48 experiment or new SVA success.'))
    c.dump(out/'source_change.json',dict(actual_executed_campaign_sha256=c.common.digest(run/'source_snapshot/research48_sva_campaign.py'),
        future_campaign_sha256=c.common.digest(Path(c.__file__)),
        new_protocol_flag='retain_native_on_unusable_output_v1',
        original_run_not_amended=True,old_sealed_run_requires_original_source_snapshot=True))
    c.dump(out/'original_run_hashes.json',hashes)
    shutil.copy2(Path(__file__),out/'qualification_source.py')
    print('FEEDBACK_FIX_QUALIFIED',len(checks),'checks; no model/native calls',flush=True)


if __name__=='__main__':main()
