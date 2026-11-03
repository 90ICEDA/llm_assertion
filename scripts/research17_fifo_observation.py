"""Native sampled FIFO diagnostics for model feedback, never an obligation oracle.

The existing port-history oracle and paired evidence attribution are reused.
Every monitor value below comes from $sampled in a native cover action; Python
does not infer signal values or evaluate model predicates. Only development
replays explicitly passed by the caller are included in feedback.
"""
from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path
import re

import research15_native_interface as interface
import research15_search_runtime as runtime
from research15_evidence import marker_map, paired_ledger

FIELDS = ('cycle', 'rst', 'svalid', 'sready', 'sdata', 'mvalid', 'mready',
          'mdata', 'ref_count', 'ref_expected', 'drain_due')
SAMPLED_BLOCK = '''
  // Additional observation only: no assumptions or candidate modifications.
  // Action values explicitly use the same preponed samples as native SVA.
  cv_research17_observation: cover property (@(posedge clk) (1'b1))
    $display("OBS17 %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d",
      $sampled(native_cycle), $sampled(rst), $sampled(svalid),
      $sampled(sready), $sampled(sdata), $sampled(mvalid),
      $sampled(mready), $sampled(mdata), $sampled(ref_count),
      $sampled(ref_expected), $sampled(drain_due));
'''


def testbench_template(depth=2, pipeline=0):
    template = runtime.testbench_template(depth, pipeline)
    assert template.count('// NATIVE_PROPERTIES') == 1
    return template.replace('// NATIVE_PROPERTIES', '// NATIVE_PROPERTIES\n' + SAMPLED_BLOCK)


def build(candidate, folder, depth=2, pipeline=0):
    """Same signature/result as research15_search_runtime.build."""
    return interface.compile_candidate(candidate, Path(folder), testbench_template(depth, pipeline))


def parse_observations(path):
    rows, errors = [], []
    for number, line in enumerate(Path(path).read_text(errors='replace').splitlines(), 1):
        if not line.startswith('OBS17 '):
            continue
        values = line.split()[1:]
        if len(values) != len(FIELDS):
            errors.append(dict(line=number, reason='malformed_native_sample', raw=line))
            continue
        rows.append({key: int(value) if re.fullmatch(r'-?\d+', value) else None
                     for key, value in zip(FIELDS, values)})
    return rows, errors


def validate_observations(trace, observations, rows):
    """Check diagnostics against real TRACE and reference queue, not SVA truth.

    ref_expected is intentionally undefined when ref_count=0. Queue validation
    only ensures the exported monitor's sampling semantics, and never replaces
    the independent obligation verdict in runtime.oracle.
    """
    issues, by_cycle = [], collections.defaultdict(list)
    for sample in observations:
        by_cycle[sample['cycle']].append(sample)
    pending = collections.deque()
    for t in trace:
        cycle = t['cycle']
        samples = by_cycle[cycle]
        if len(samples) != 1:
            issues.append(dict(cycle=cycle, reason='sample_count', observed=len(samples), expected=1))
        else:
            sample = samples[0]
            for key in FIELDS[:8]:
                if sample[key] != t[key]:
                    issues.append(dict(cycle=cycle, reason='trace_sample_mismatch', field=key,
                                       sampled=sample[key], trace=t[key]))
            if cycle < 0 or cycle >= len(rows):
                issues.append(dict(cycle=cycle, reason='schedule_cycle_out_of_range'))
            elif sample['drain_due'] != rows[cycle].get('drain_due', 0):
                issues.append(dict(cycle=cycle, reason='sampled_drain_marker_mismatch'))
            if not t['rst']:
                if sample['ref_count'] != len(pending):
                    issues.append(dict(cycle=cycle, reason='reference_count_sampling_mismatch',
                                       sampled=sample['ref_count'], expected=len(pending)))
                if pending and sample['ref_expected'] != pending[0]:
                    issues.append(dict(cycle=cycle, reason='reference_payload_sampling_mismatch',
                                       sampled=sample['ref_expected'], expected=pending[0]))
        if t['rst']:
            pending.clear()
        else:
            if t['mvalid'] and t['mready'] and pending:
                pending.popleft()
            if t['svalid'] and t['sready']:
                pending.append(t['sdata'])
    if not trace:
        issues.append(dict(reason='no_port_trace'))
    return dict(status='verified' if not issues else 'unknown', issues=issues,
                trace_samples=len(trace), native_observation_samples=len(observations),
                semantics='preponed $sampled values from native cover action; reference state before same-edge NBA updates')


def execute(compiled, folder, rows, mode):
    """Native RTL replay, extended with sampled state and validated diagnostics."""
    record = runtime.execute(compiled, folder, rows, mode)
    samples, parse_errors = parse_observations(Path(folder) / 'execute.log')
    trace_cycles = {t['cycle'] for t in record['trace']}
    matched = [s for s in samples if s['cycle'] in trace_cycles]
    validation = validate_observations(record['trace'], matched, rows)
    if parse_errors:
        validation['issues'].extend(parse_errors)
        validation['status'] = 'unknown'
    record.update(observations=matched, observation_validation=validation)
    interface.dump(Path(folder) / 'sampled_observations.json', dict(samples=samples, validation=validation))
    interface.dump(Path(folder) / 'replay.json', record)
    return record


def _properties(record):
    triggers = marker_map(record['native'], 'triggers')
    failures = marker_map(record['native'], 'failures')
    healthy = (record['native'].get('compile_status') == 'passed'
               and record['native'].get('execution_status') == 'completed'
               and 'native cover property' in record['native'].get('trigger_measurement', ''))
    result = []
    for item in record['candidate']['assertions']:
        pid = item['id']
        result.append(dict(id=pid, obligations=item['obligations'], property=item['property'],
            antecedent=item['derived_antecedent'], consequent=item['consequent'],
            derived_delay=item['derived_delay'], trigger_cycles=sorted(triggers[pid]),
            failure_cycles=sorted(failures[pid]), trigger_count=len(triggers[pid]),
            failure_count=len(failures[pid]),
            native_status='unknown' if not healthy else 'violation' if failures[pid]
                else 'untriggered' if not triggers[pid] else 'no_violation_within_execution'))
    return result


def _cycle_context(record, cycle, radius=2):
    """Actual samples plus transactions/events linked by accepted handshakes."""
    oracle = record['oracle']
    txns = oracle.get('transactions', [])
    accepted = [t for t in txns if t['accept_cycle'] <= cycle]
    pending = [t for t in accepted
               if (t.get('response_cycle') is None or t['response_cycle'] >= cycle)
               and (t.get('cancel_cycle') is None or t['cancel_cycle'] >= cycle)]
    samples = [s for s in record.get('observations', []) if cycle-radius <= s['cycle'] <= cycle+radius]
    return dict(samples=samples,
        events_at_cycle=dict(
            accepted=[t for t in txns if t['accept_cycle'] == cycle],
            responses=[t for t in txns if t.get('response_cycle') == cycle],
            cancelled=[t for t in txns if t.get('cancel_cycle') == cycle]),
        outstanding_before_cycle=[t for t in pending if t['accept_cycle'] < cycle],
        reference_expected_valid_only_when_count_positive=True)


def feedback(runs, scenario_id='development', group=None):
    """Return JSON-ready model feedback for an explicitly supplied replay set.

    runs: mapping mode -> native replay from execute(), with key ``correct``.
    group: optional previously computed merged paired-ledger group. If omitted,
    paired_ledger computes first-violation attribution using the existing oracle.
    No filesystem discovery or holdout reads occur in this function.
    """
    fixed = runs['correct']
    if group is None:
        from research15_evidence import merge_ledgers
        groups = [paired_ledger(fixed, mutant, scenario_id)
                  for mode, mutant in runs.items() if mode != 'correct']
        group = merge_ledgers(groups or [paired_ledger(fixed, None, scenario_id)])
    replay_summary = {}
    for mode, record in runs.items():
        replay_summary[mode] = dict(
            directory=record.get('directory'), waveform=str(Path(record['directory']) / 'wave.vcd'),
            native={k: record['native'].get(k) for k in
                ('compile_status', 'tool_support_status', 'execution_status', 'property_status', 'trigger_status')},
            sampled_diagnostics=record.get('observation_validation', dict(status='unknown', issues=['no_sampled_diagnostics'])),
            properties=_properties(record), legality=record['oracle']['legality'],
            independent_oracle_verdict=record['oracle']['verdict'],
            oracle_unknown=record['oracle'].get('unknown', []),
            accepted_transactions=record['oracle']['transactions'],
            cancelled_transactions=record['oracle']['cancelled'],
            outstanding_at_end=record['oracle']['pending'],
            drain_scope=record['oracle']['drain_scope'])
    issues = []
    for row in group['ledger']:
        target = row.get('oracle', {}).get('verdict') == 'violated'
        alarms = [a for a in row.get('native', {}).get('assertions', []) if a.get('failed')]
        if not target and not alarms:
            continue
        mode, cycle = row['variant'], row['cycle']
        if mode not in runs:
            continue
        record = runs[mode]
        mapped = row.get('native', {}).get('assertions', [])
        attribution = row.get('native', {}).get('attribution_status')
        native = row.get('native', {})
        valid = (row['oracle'].get('legality') == 'legal'
                 and row['oracle'].get('paired_control_pass') is True
                 and row['oracle'].get('identical_input_handshakes') is True
                 and attribution == 'confirmed'
                 and all(native.get(k) == v for k, v in
                         [('compile', 'ok'), ('support', 'supported'), ('execution', 'ok')]))
        if target:
            status = ('unknown' if not valid else 'detected'
                      if any(a.get('causal_detection') is True for a in mapped)
                      else 'no_property_for_obligation' if not mapped
                      else 'untriggered_at_target' if not any(a.get('trigger') for a in mapped)
                      else 'triggered_but_not_detected')
        else:
            status = 'false_positive' if valid else 'unknown'
        prop_details = []
        triggers = marker_map(record['native'], 'triggers')
        failures = marker_map(record['native'], 'failures')
        for prop in record['candidate']['assertions']:
            trigger_cycle = cycle-prop['derived_delay']
            prop_details.append(dict(id=prop['id'], obligations=prop['obligations'],
                mapped_to_target_obligation=row['obligation'] in prop['obligations'],
                antecedent=prop['derived_antecedent'], consequent=prop['consequent'],
                relevant_trigger_cycle=trigger_cycle,
                native_cover_observed=trigger_cycle in triggers[prop['id']],
                native_failure_at_target=cycle in failures[prop['id']],
                antecedent_sample=_cycle_context(record, trigger_cycle, 0)['samples'],
                target_sample=_cycle_context(record, cycle, 0)['samples']))
        issues.append(dict(evidence_id=row['evidence_id'], scenario_id=row.get('scenario_id'),
            variant=mode, cycle=cycle, obligation=row['obligation'], classification=status,
            oracle=row['oracle'], oracle_violation=row.get('oracle_violation', []),
            mapped_assertion_evidence=mapped, all_property_observations=prop_details,
            fixed_control=_cycle_context(fixed, cycle), target=_cycle_context(record, cycle),
            diagnostic_status='verified' if all(r.get('observation_validation', {}).get('status') == 'verified'
                for r in (fixed, record)) else 'unknown'))
    counts = collections.Counter(i['classification'] for i in issues)
    return dict(schema='research17_native_sampled_feedback_v1', scenario_id=scenario_id,
        replays=replay_summary, issues=issues, counts=dict(counts),
        later_attribution_unknown=group.get('exclusions', []),
        scope='Finite native simulation and independent accepted-transaction oracle. No formal proof. Missing diagnostic samples remain unknown. Cover is the exact native parsed antecedent; no Python predicate evaluator is used.')


def smoke():
    """Development-only instrumentation qualification on an archived model SVA."""
    from research15_search_experiment import stimulus
    out = runtime.ROOT / 'deliverables/research17_fifo_observation_20261016_r01'
    out.mkdir(parents=True, exist_ok=False)
    source = runtime.ROOT / 'deliverables/research16_ablation_20261016_r03/shared_initial.json'
    candidate = json.loads(source.read_text())
    interface.dump(out / 'provenance.json', dict(candidate_source=str(source),
        candidate_origin='archived_real_model_initial', model_calls=0,
        purpose='diagnostic_instrumentation_qualification_only', independent_test=False))
    rows = stimulus(2026101551, 'tail_loss')
    compiled = build(candidate, out / 'compiled', 2, 0)
    if compiled['native']['compile_status'] != 'passed':
        raise RuntimeError('Native sampling compilation failed; see compile.log')
    runs = {mode: execute(compiled, out / mode, rows, mode) for mode in ('correct', 'drop')}
    result = feedback(runs, 'instrumentation:d2:p0:s2026101551')
    interface.dump(out / 'feedback.json', result)
    assert all(r['observation_validation']['status'] == 'verified' for r in runs.values())
    loss = [i for i in result['issues'] if i['obligation'] == 'drain_no_loss']
    assert len(loss) == 1 and loss[0]['classification'] == 'no_property_for_obligation'
    assert loss[0]['fixed_control']['samples'][-1]['ref_count'] == 0
    assert loss[0]['target']['samples'][-1]['ref_count'] == 1
    interface.dump(out / 'qualification.json', dict(passed=True,
        native_compilations=1, native_simulations=3, model_calls=0,
        observation_validation={mode: r['observation_validation'] for mode, r in runs.items()},
        target_classification=loss[0]['classification']))
    print(json.dumps(dict(passed=True, output=str(out), counts=result['counts'])))


def diagnose_archived_revision():
    """Reproduce the old model-selected vacuity with sampled diagnostic values."""
    from research15_search_experiment import stimulus
    out = runtime.ROOT / 'deliverables/research17_fifo_observation_20261016_r01/archived_revision'
    out.mkdir(parents=True, exist_ok=False)
    source = runtime.ROOT / 'deliverables/research16_ablation_20261016_r03/arms/B/compiled/compiled.json'
    candidate = json.loads(source.read_text())['candidate']
    interface.dump(out / 'provenance.json', dict(candidate_source=str(source), model_calls=0,
        candidate_origin='archived_real_model_rejected_revision', independent_test=False,
        purpose='native_diagnostic_qualification_only; not a new model refinement'))
    compiled = build(candidate, out / 'compiled', 2, 0)
    if compiled['native']['compile_status'] != 'passed':
        raise RuntimeError('Archived candidate native compilation failed')
    rows = stimulus(2026101551, 'tail_loss')
    runs = {mode: execute(compiled, out / mode, rows, mode) for mode in ('correct', 'drop')}
    result = feedback(runs, 'instrumentation:archived_revision:d2:p0:s2026101551')
    interface.dump(out / 'feedback.json', result)
    loss = [i for i in result['issues'] if i['obligation'] == 'drain_no_loss']
    assert all(r['observation_validation']['status'] == 'verified' for r in runs.values())
    assert len(loss) == 1 and loss[0]['classification'] == 'untriggered_at_target'
    props = [p for p in result['replays']['drop']['properties'] if 'drain_no_loss' in p['obligations']]
    assert props and all(p['trigger_count'] == 0 and p['failure_count'] == 0 for p in props)
    interface.dump(out / 'qualification.json', dict(passed=True, native_compilations=1,
        native_simulations=3, model_calls=0, target_classification=loss[0]['classification']))
    print(json.dumps(dict(passed=True, output=str(out), counts=result['counts'])))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['smoke', 'diagnose_archived_revision'])
    args = parser.parse_args()
    globals()[args.action]()
