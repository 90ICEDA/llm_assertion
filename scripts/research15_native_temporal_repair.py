"""One explicitly extra-budget common initialization temporal repair call."""
import json
import re
from pathlib import Path
import research15_native_models as models
import research15_native_interface as interface
import research15_search_runtime as runtime
import research_fifo_experiment as fifo
from research15_evidence import paired_ledger
from research15_acceptance import inspect,sha


def main():
    out=interface.OUT;dump=interface.dump
    original=json.loads((out/'model_calls/initial_semantic_repair/candidate.json').read_text())
    source=out/'initial_qualification/semantic_repair'
    fixed=json.loads((source/'correct/replay.json').read_text())
    mutant=json.loads((source/'corrupt/replay.json').read_text())
    examples=[]
    for event in fixed['native']['failures'][:2]:
        c=int(re.search(r'cycle=(\d+)',event['detail'])[1])
        examples.append(dict(kind='legal_false_positive',cycle=c,
            samples=[t for t in fixed['trace'] if c-1<=t['cycle']<=c],
            independent_checks=[r for r in fixed['oracle']['checks'] if r['cycle']==c]))
    for v in mutant['oracle']['violations'][:1]:
        examples.append(dict(kind='first_accepted_output_violation',violation=v,
            samples=[t for t in mutant['trace'] if v['cycle']-1<=t['cycle']<=v['cycle']]))
    block=out/'initial_temporal_continuation';block.mkdir(parents=True,exist_ok=False)
    dump(block/'protocol.json',dict(extra_budget_calls=1,total_common_initialization_attempts=3,
        original_two_call_block='failed semantic qualification; never relabelled success',
        feedback_provenance='actual native false positives and independent transaction oracle + explicit human-authored sampling/interface explanation',
        no_manual_candidate_edit=True))
    ctx=models.context()
    ctx.update(current_assertions=original,feedback=examples,
        task='Correct ONLY the temporal operator of this rejected order_payload assertion, returning one complete native SVA in JSON. The OUTPUT acceptance event and comparison against ref_expected are evaluated at the SAME sampling edge. There is NO next-cycle requirement: after that edge both output and reference head may advance. Non-overlapped implication imposes the wrong timing. Select the implication operator matching a same-edge consequent. Keep accepted-output coverage and full mdata versus ref_expected comparison; do not use sdata or compare successive outputs. This is a response to the actual false positives above, not an independent test.')
    call,candidate=models.call(out/'model_calls/initial_temporal_repair',ctx,models.service())
    if candidate is None:
        dump(block/'summary.json',dict(status='extra_temporal_generation_failed',call=call));return
    rows=fifo.stimulus(2026101501)
    for row in rows:row['drain_due']=0
    compiled=runtime.build(candidate,block/'compiled',2,0)
    fixed=runtime.execute(compiled,block/'correct',rows,'correct')
    mutant=runtime.execute(compiled,block/'corrupt',rows,'corrupt')
    ledger=paired_ledger(fixed,mutant,'initial_qualification:d2:p0:s2026101501')
    dump(block/'ledger.json',ledger);info=inspect(ledger['ledger'])
    qualified=not info['unknown'] and not info['false_positives'] and not info['misses'] and bool(info['detections'])
    if qualified:
        dump(out/'shared_initial.json',candidate)
        dump(out/'shared_initial_freeze.json',dict(candidate_sha256=sha(candidate),source_model_call='initial_temporal_repair',
            common_initialization_calls=3,original_budget_succeeded=False,extra_budget_calls=1,
            scope='Order-payload only, selected with explicit common engineering interface/timing feedback and actual finite native replay. Shared unchanged by all four arms.'))
    summary=dict(status='shared_initial_qualified_extra_budget' if qualified else 'shared_initial_still_unqualified',call=call,
        counts={k:len(info[k]) for k in ('rows','false_positives','detections','misses','triggers','unknown')},
        original_budget_succeeded=False,extra_budget_calls=1)
    dump(block/'summary.json',summary);print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
