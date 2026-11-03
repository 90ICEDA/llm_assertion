"""Read-only result/code audit supplement; never changes frozen experiments."""
import json
import shutil
from pathlib import Path
from research_fifo_experiment import DEFAULT_OUT, ROOT, sha, write_json


def main():
    out=DEFAULT_OUT/'supplement'
    out.mkdir(exist_ok=False)
    results=json.loads((DEFAULT_OUT/'results.json').read_text())
    active_unknown=[]
    dev_ids=set(); test_ids=set()
    for r in results:
        trace=json.loads((DEFAULT_OUT/r['artifact_directory']/'trace.json').read_text())
        for t in trace:
            if not t['rst'] and ((t['svalid'] and t['sready'] and t['sdata'] is None) or (t['mvalid'] and t['mready'] and t['mdata'] is None)):
                active_unknown.append(dict(run=r['artifact_directory'],cycle=t['cycle']))
        schedule=DEFAULT_OUT/r['artifact_directory']/'intent_schedule.json'
        (dev_ids if r['split']=='development' else test_ids).add(sha(schedule))
    findings=[
        dict(id='G1',severity='scope_limit',code='scripts/research_gate_experiment.py:evidence',
             finding='status copies q.status, not paired_metrics.attribution_unknown or pending. Accepted can coexist with non-target attribution uncertainty.',
             consequence='Cannot describe acceptance as every replay obligation fully known. Current target and prior causal detections still have explicit preservation checks.'),
        dict(id='G2',severity='scope_limit',code='scripts/research_gate_experiment.py:evidence',
             finding='effective_triggers uses consequent output-name substring plus temporal activation; a tautological consequent referencing the output also qualifies.',
             consequence='Activation preservation is bounded syntactic relevance, not semantic non-vacuity. Prior causal detections remain guarded but unprotected obligations can remain vacuous.'),
        dict(id='G3',severity='scope_limit',code='scripts/research_gate_experiment.py:develop/evidence',
             finding='Only first_misses enter misses, and the lexically first acquired target is required. Later misses and other current gaps need not be repaired for acceptance.',
             consequence='Report incremental repair of the selected gap and retention of existing detection evidence, not full obligation completion.'),
        dict(id='G4',severity='caller_contract',code='scripts/research_acceptance_gate.py:decide',
             finding='The gate trusts caller-supplied status, stable keys, resolved_keys and legality/causality. Missing list fields default empty.',
             consequence='A standalone gate decision is not validation of the evidence backend. Current experiment supplies the fields, but future integrations require schema/coverage validation.'),
        dict(id='F1',severity='scope_limit',code='scripts/research_fifo_experiment.py:stimulus/main',
             finding='Independent tests use new seeds but the same phases, reset positions, depth grid and pipeline grid as development.',
             consequence='No unseen parameter or unseen reset-timing generalization has been established; this is a fresh-data in-distribution check.'),
        dict(id='F2',severity='scope_limit',code='scripts/research_fifo_experiment.py:oracle',
             finding='Reset cancellation records cancelled queue transactions; no dedicated reset-residue mutant is executed. Post-reset payload/order checks provide indirect safety evidence.',
             consequence='Do not mark reset-cancellation fault detection fully validated from cancellation counts alone.'),
        dict(id='F3',severity='latent_monitor_limit',code='scripts/research_fifo_experiment.py:oracle',
             finding='Unknown payload values at an accepted transaction are not explicitly converted to unknown; only unknown control fields are checked.',
             consequence='This does not affect these saved runs: all accepted payloads are known, as audited. Before using the oracle for X-bearing traces, treat payload unknown as unknown rather than comparing None.'),
        dict(id='F4',severity='scope_limit',code='scripts/research_fifo_experiment.py:main',
             finding='The initial engineering candidates are fixed manually and only independently tested, never LLM-refined in the 96-run experiment.',
             consequence='Cannot use these 96 runs as evidence of successful automatic synthesis or LLM non-regression.'),
        dict(id='F5',severity='scope_limit',code='scripts/research_fifo_experiment.py:oracle',
             finding='No bounded per-transaction deadline under arbitrary backpressure is asserted. Loss is checked only after a sustained fair final drain.',
             consequence='Supports finite drain/order safety evidence, not global liveness or formal proof.'),
    ]
    audit=dict(read_only=True,frozen_experiment_modified=False,
        accepted_payload_unknown_count=len(active_unknown),accepted_payload_unknown_events=active_unknown,
        exact_intent_schedule_overlap=len(dev_ids&test_ids),
        independent_unique_intent_schedules=len(test_ids),development_unique_intent_schedules=len(dev_ids),
        findings=findings,
        frozen_runner_hash_matches=sha(ROOT/'scripts/research_fifo_experiment.py')==json.loads((DEFAULT_OUT/'freeze.json').read_text())['runner_sha256'])
    write_json(out/'audit.json',audit)
    shutil.copy2(ROOT/'scripts/research_fifo_experiment.py',out/'research_fifo_experiment.py.snapshot')
    (out/'AUDIT.md').write_text('# Read-only audit of FIFO and acceptance-gate scope\n\n'+
        f'Accepted payloads containing X/Z: {len(active_unknown)}. Exact development/test intent-schedule overlap: {len(dev_ids&test_ids)}. Frozen FIFO runner hash matches: {audit["frozen_runner_hash_matches"]}.\n\n'+
        '\n\n'.join(f'**{f["id"]} ({f["severity"]})** {f["finding"]} {f["consequence"]}' for f in findings)+
        '\n\nThe sealed 96-run result is unchanged. These limitations must accompany result aggregation.\n')
    print(json.dumps(audit,indent=2))


if __name__=='__main__': main()
