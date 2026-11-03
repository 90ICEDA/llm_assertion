"""Engineering qualification of runtime schedules and reset-cancellation oracle."""
import json
from research15_search_runtime import ROOT,build,execute,write_json,MODES
from research15_search_experiment import stimulus,adjudicate,Policy


def main():
    out=ROOT/'deliverables/research15_search_20261015_r01/engineering_qualification'
    out.mkdir(parents=True,exist_ok=False)
    candidate={'assertions':[
        {'property':'(mvalid && mready) |-> (ref_count > 0 && mdata == ref_expected)','obligations':['order_payload']},
        {'property':'(mvalid && mready) |-> (ref_count > 0)','obligations':['no_unsolicited_output']},
        {'property':'(mvalid && !mready) |=> (mvalid && $stable(mdata))','obligations':['stall_stability']},
        {'property':'drain_due |-> (ref_count == 0)','obligations':['drain_no_loss']} ]}
    compiled=build(candidate,out/'compiled',5,1)
    if compiled['native']['compile_status']!='passed':raise RuntimeError('native compile failed')
    candidate=compiled['candidate'];write_json(out/'candidate.json',candidate)
    rows=stimulus(2026101549,'reset_pending');write_json(out/'stimulus.json',rows)
    runs={}
    for mode in MODES:
        replay=execute(compiled,out/mode,rows,mode)
        runs[mode]=dict(folder=str(out/mode),native=replay['native'])
    evaluation=adjudicate(rows,runs,candidate,'engineering_qualification')
    write_json(out/'evaluation.json',evaluation)
    reset=[e for e in evaluation['mapping'] if e['variant']=='reset_residue' and e['obligation']=='reset_cancellation']
    # A same-seed policy receiving different acquired coverage must be able to
    # select a different next target. This checks actual feedback dependency.
    p=Policy('contract_coverage',1);before=p.choose()
    fake=dict(fixed_obligation_checks={o:10 for o in ('order_payload','no_unsolicited_output','drain_no_loss','reset_cancellation')},
              effective_native_triggers={o:10 for o in ('order_payload','no_unsolicited_output','drain_no_loss','reset_cancellation')},
              causal_protected={o:1 for o in ('order_payload','no_unsolicited_output','drain_no_loss','reset_cancellation')},
              obligation_gap_keys=[])
    p.update('reset_pending',fake);after=p.choose()
    summary=dict(provenance='engineering_controls_not_LLM',native_compilations=1,native_replays=5,
        oracle_verdicts=evaluation['reference_verdicts'],unknown=evaluation['errors'],
        legal_control_false_positives=sum(x['kind']=='false_positive' for x in evaluation['findings']),
        reset_cancelled_payload_witnesses=reset,
        policy_feedback_unit_check=dict(before=before,after=after,explicit_synthetic_policy_input_not_experimental_evidence=True,
            passed=after['target_obligation']=='stall_stability'),
        passed=evaluation['status']=='ok' and bool(reset) and not [x for x in evaluation['findings'] if x['kind']=='false_positive'])
    write_json(out/'summary.json',summary)
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
