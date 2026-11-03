"""Separately budgeted compact-feedback continuation after context overflow.

Original failed request, initial candidate and executable evidence remain intact.
This extra model attempt is never counted as completion within the two-call run.
"""
import argparse
import copy
import datetime
import hashlib
import json
import re
from pathlib import Path
import research_native_closed_loop as loop
from research_acceptance_gate import decide


def main(out):
    old=loop.OUT/'closed_loop'
    out.mkdir(parents=True,exist_ok=False)
    initial=json.loads((old/'model_calls/initial/candidate.json').read_text())
    before=json.loads((old/'v0_development/evaluation.json').read_text())
    prior_attempt=json.loads((old/'model_calls/revision/attempt.json').read_text())
    started=datetime.datetime.fromisoformat(prior_attempt['started_utc'].replace('Z','+00:00'))
    aborted=dict(status='cancelled_context_overflow',model_calls=1,retries=0,
        reason='Service reported n_ctx_slot=16384 and task.n_tokens=16383 for a 56571-byte request. Owned client PID19481 was interrupted before response; no usage receipt available.',
        prompt_tokens=None,completion_tokens=None,wall_seconds=(datetime.datetime.now(datetime.timezone.utc)-started).total_seconds(),
        note='Wall time is an upper-bound artifact-recording interval; cancellation preceded this record. Retain service timestamps for exact elapsed interval.',
        completed_response=False,continuation_is_extra_budget=True)
    loop.dump(old/'model_calls/revision/cancellation.json',aborted)
    loop.dump(out/'protocol.json',dict(parent_run=str(old),extra_model_call_budget=1,
        total_attempts_including_parent=3,options=loop.OPTIONS,development_seed=2026101431,
        independent_seed=2026101497,independent_parameters={'depth':4,'pipeline':2},
        purpose='repair initial false positives with compact actual feedback, then native replay and frozen independent test',
        trigger_scope='Initial model diagnostic trigger mismatches unconditional SVA. Metadata diagnostics cannot establish trigger preservation; gate must retain this unknown.',
        sampling='same model, options, RTL and development evidence as parent; only feedback selection is compacted. Additional attempt/cost explicitly separate.'))
    ctx=loop.context()
    fp=before['false_positives']
    examples=[]
    correct_trace=json.loads((old/'v0_development/correct/trace.json').read_text())
    for key in sorted((k for k in fp if '/correct/' in k),key=lambda k:int(re.search(r'/cycle(\d+)/',k)[1]))[:2]:
        c=int(re.search(r'/cycle(\d+)/',key)[1])
        examples.append(dict(key=key,legal=True,previous=correct_trace[c-1],current=correct_trace[c],
            meaning='Legal different FIFO payloads can change bit 0 between samples. No independent obligation is violated on this correct execution.'))
    ctx.update(task='Repair the actual false positives below, optionally add complementary assertions. Current SVA unconditionally demands bit stability, but distinct accepted transactions may have different payloads. Only stalled output has stability obligation. Accepted output order compares with the oldest accepted input tracked by ref_expected. Maximum three native SVA properties. Use explicit antecedent |-> or |=> and give the same ordinary boolean expression as trigger. Return full replacement assertion set.',
        current_assertions=initial,
        feedback=dict(native_compile='passed',native_execution='completed for correct/corrupt/duplicate_payload/drop',
            counts={k:len(before[k]) for k in ('false_positives','misses','detections')},
            legal_false_positive_examples=examples,
            target_violation_examples={mode:o['violations'][:2] for mode,o in before['oracles'].items() if mode!='correct'},
            baseline_trigger_audit='property has implicit unconditional antecedent; reported svalid&&sready&&mvalid&&mready trigger is mismatched and cannot prove property coverage'))
    tags=json.loads((old/'model_tags.json').read_text())
    digest=next(m['digest'] for m in tags['models'] if m['name']==loop.MODEL)
    call,revised=loop.ask(out/'model_call',ctx,digest)
    loop.dump(out/'budget_accounting.json',dict(parent_initial=json.loads((old/'model_calls/initial/result.json').read_text()),
        parent_aborted=aborted,extra_continuation=call,total_real_attempts=3,
        tokens_total=None,token_total_reason='aborted second attempt has no service usage receipt'))
    if not revised:
        loop.dump(out/'summary.json',dict(status='extra_revision_generation_failed',call=call,original_two_call_budget_succeeded=False));return
    after=loop.evaluate(revised,out/'development',2026101431,2,0)
    targets=sorted(fp,key=lambda k:int(re.search(r'/cycle(\d+)/',k)[1]))[:1]
    decision=decide(before,after,targets)
    if after['false_positives']:
        decision['accepted']=False
        decision['reasons'].append(dict(kind='remaining_legal_false_positive',keys=after['false_positives']))
    # Fail closed on the untrustworthy trigger mapping; still freeze and test
    # the proposed version diagnostically so useful partial progress is visible.
    decision['accepted']=False
    decision['reasons'].append(dict(kind='trigger_semantics_unconfirmed',
        detail='Initial unconditional property and supplied diagnostic trigger mismatch. Full trigger-preservation gate cannot be certified.'))
    loop.dump(out/'decision.json',decision)
    loop.dump(out/'frozen_proposal.json',revised)
    (out/'frozen_proposal.sva').write_text(loop.candidate_sva(revised))
    digest_sva=hashlib.sha256((out/'frozen_proposal.sva').read_bytes()).hexdigest()
    loop.dump(out/'freeze.json',dict(sha256=digest_sva,status='rejected_proposal_frozen_for_diagnostic_independent_test',
        accepted_version=None,no_test_feedback_to_model=True))
    independent=loop.evaluate(revised,out/'independent_test',2026101497,4,2)
    def compact(e):return dict(status=e['status'],**{k:len(e[k]) for k in ('false_positives','detections','misses','effective_triggers','attribution_unknown')})
    runs=[json.loads(p.read_text()) for p in out.rglob('result.json') if p.parent.name in loop.MUTANTS]
    summary=dict(status='extra_budget_native_revision_and_diagnostic_holdout_completed',original_two_call_budget_succeeded=False,
        initial=compact(before),revised_development=compact(after),independent_test=compact(independent),decision=decision,
        frozen_sva_sha256=digest_sva,accepted_version=None,call=call,
        native_cost=dict(compile_calls=sum('compile' in r for r in runs),simulation_calls=sum(r.get('native_simulation_calls',0) for r in runs),
            compile_wall_seconds=sum(r.get('compile',{}).get('wall_seconds',0) for r in runs),simulation_wall_seconds=sum(r.get('execute',{}).get('wall_seconds',0) for r in runs)),
        formal_cost=dict(calls=0,wall_seconds=0),scope='Finite native simulation of artificial boundary faults on actual FIFO RTL. Rejected proposal only, no accepted final set or global non-regression claim.')
    loop.dump(out/'summary.json',summary)
    print(json.dumps(summary,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',default=str(loop.OUT/'compact_continuation'))
    args=parser.parse_args();main(Path(args.out))
