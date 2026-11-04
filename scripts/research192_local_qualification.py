"""Native validation of local-edit wiring; handwritten controls, zero model calls."""
import argparse
import json
from pathlib import Path
import research192_temporal_refinement as r


def run(out):
    out.mkdir(parents=True, exist_ok=False)
    initial, jobs, protected, evidence = r.archived_baseline()
    findings = r.localize(initial, evidence)
    r.s.dump(out/'initial.json', initial)
    r.s.dump(out/'localization.json', findings)
    r.s.dump(out/'evidence.json', evidence)
    baseline = r.binding.bound_measure(initial, jobs, protected)
    r.s.dump(out/'baseline.json', baseline)
    results = []
    for name, expression in [('positive_trigger_broadening', 'first_present'),
                             ('negative_ready_only_regression', 'first_present && m_axis_tready')]:
        folder = out/name
        edit = dict(edits=[dict(op='replace_field', assertion=initial[0]['label'],
            field='antecedent', value=expression)], reason='Handwritten native qualification, not a model proposal or algorithm improvement result')
        candidate = r.apply_local_edits(initial, edit, findings)
        r.s.dump(folder/'edit.json', edit)
        r.s.dump(folder/'candidate.json', candidate)
        (folder/'candidate.sva').write_text('\n'.join(
            f"{a['label']}: assert property (@(posedge clk) disable iff(rst) ({a['antecedent']}) |-> ({a['consequent']}));"
            for a in candidate)+'\n')
        print('NATIVE_LOCAL_FIXTURE '+name, flush=True)
        measured = r.evaluate(candidate, folder/'native', protected, workers=2)
        d = {strategy:r.decide(strategy, measured, baseline) for strategy in r.STRATEGIES}
        r.s.dump(folder/'decisions.json', d)
        actual_jobs = r.s.read(folder/'native/executions.json')
        all_ev = r.evidence_from_jobs(candidate, actual_jobs)
        r.s.dump(folder/'evidence.json', all_ev)
        excerpts = []
        for job in actual_jobs:
            if job['depth'] != 16 or job['revision'] != 'before':
                continue
            traces = r.s.traces(Path(job['folder']))
            refs = r.p.q.reference(traces, job['depth'])
            for ev in refs['events']:
                cycle = ev['first']['cycle']
                excerpts.append(dict(scene=job['scene_id'], first_presentation=cycle,
                    frame=ev['frame'], accepted_count=len(ev['accepted']),
                    later_output_handshakes=len(ev['outputs']),
                    samples=[row for row in traces if cycle-2 <= row['cycle'] <= cycle+2],
                    vcd=r.s.rel(Path(job['folder'])/'wave.vcd')))
        r.s.dump(folder/'transaction_waveforms.json', excerpts)
        results.append(dict(name=name, handwritten_fixture=True, model_calls=0,
            detected=len(measured['detected_ids']), targets=len(measured['public_targets'])+len(measured['historical_targets']),
            false_positives=len(measured['false_positives']), unknown=measured['critical_unknown'],
            lost=measured['lost'], decisions=d, native_compiles=12))
        r.s.dump(out/'results.json', results)
    assert results[0]['decisions']['R3']['accepted']
    assert not results[1]['decisions']['R3']['accepted']
    assert results[1]['decisions']['R1']['accepted']
    assert len(results[1]['lost']) == 2
    (out/'REPORT.md').write_text('''# Native local-edit qualification

These are handwritten wiring controls, not fresh LLM proposals, not R0–R3 experimental outcomes and not independent acceptance. No model request was sent.

The same confirmed missed transactions localize the initial assertion to its antecedent. The positive control replaces only the trigger with `first_present`; native replay checks all legal and target traces. The negative control selects only ready-first presentations: it repairs current misses but loses two previously detected stalled-first targets. R0/R1 ordinary acceptance permits this; R2/R3 historical protection rejects it and retains the baseline.

Initial SVA: `first_present && !m_axis_tready |-> input_complete && input_count <= DEPTH` (same-sample, disable iff reset). Candidate SVA, transaction waveform excerpts/VCD paths, complete native records and per-policy decisions accompany each control. One original FIFO parent bug, four exposed target transactions; Depth8 no-exposure remains separate. No formal proof is claimed.

This validates the integration and rejection boundary. It does not establish that a model will choose the positive edit, that local editing improves success probability, or that its benefit transfers to delay/matching/exception faults.
''', encoding='utf-8')
    r.s.dump(out/'source_bindings.json',{r.s.rel(Path(__file__)):r.s.sha(Path(__file__)),
        r.s.rel(Path(r.__file__)):r.s.sha(Path(r.__file__))})
    print(json.dumps(results), flush=True)
    return results


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', required=True, type=Path)
    a = p.parse_args()
    run(a.out.resolve())
