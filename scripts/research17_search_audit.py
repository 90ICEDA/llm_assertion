"""Read-only re-adjudication of archived native FIFO search witnesses.

No model call, RTL execution, old-file writes, or independent-test reads.
The witness validator can also be called by a new development experiment.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import json
from pathlib import Path

from research15_search_runtime import oracle, parse_trace
from research15_evidence import epoch_map, marker_map

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_witness(search_root, witness=None):
    """Validate all five conditions from actual archived native observations.

    All paths are resolved below search_root, never trusted from exported
    absolute paths. Absence of mapped protection is separated from vacuity.
    This is finite replay evidence, not a formal proof of the fixed design.
    """
    if Path(search_root).is_file() or (Path(search_root).suffix == '.json' and not isinstance(witness, dict)):
        # Explicit candidate+witness paths add strict candidate identity checks.
        # Preserve the existing directory+dict API used by research17_loop.
        from research17_search_requalification import validate_witness as qualify
        result = qualify(search_root, witness)
        result['valid'] = result['qualified']
        return result
    search_root = Path(search_root).resolve()
    witness = witness if witness is not None else read(search_root/'treatment_witness.json')
    if not witness:
        return dict(valid=False, status='no_witness', conditions={})
    query = (search_root/witness['scenario_id']).resolve()
    if search_root not in query.parents:
        raise ValueError('Witness path escapes search root')
    mode = witness['mode']
    if mode not in ('corrupt', 'duplicate_payload', 'drop', 'reset_residue'):
        raise ValueError('Unknown recorded fault mode')
    rows = read(query/'stimulus.json')
    candidate = read(search_root/'initial_candidate.json')
    violation = witness['first_violation']
    cycle, obligation = violation['cycle'], violation['obligation']
    runs = {}
    sources = []
    for variant in ('correct', mode):
        folder = query/variant
        trace = parse_trace(folder/'execute.log')
        recomputed = oracle(trace, rows)
        native = read(folder/'replay.json')['native']
        original = read(folder/'independent_oracle.json')
        runs[variant] = dict(trace=trace, oracle=recomputed, native=native,
                             oracle_matches_archive=recomputed == original)
        sources += [folder/name for name in ('execute.log', 'replay.json', 'independent_oracle.json', 'wave.vcd')]
    fixed, buggy = runs['correct'], runs[mode]
    input_fields = ('cycle', 'rst', 'svalid', 'sready', 'sdata', 'mready')
    same_inputs = ([[r.get(k) for k in input_fields] for r in fixed['trace']] ==
                   [[r.get(k) for k in input_fields] for r in buggy['trace']])
    epochs = epoch_map(buggy['trace'])
    epoch = epochs.get(cycle)
    relevant = [a for a in candidate['assertions'] if obligation in a.get('obligations', [])]
    native_triggers = marker_map(buggy['native'], 'triggers')
    native_failures = marker_map(buggy['native'], 'failures')
    measured = [dict(id=a['id'], derived_delay=a.get('derived_delay'),
                     trigger_at_target=(cycle-a['derived_delay'] in native_triggers[a['id']])
                        if type(a.get('derived_delay')) is int else None,
                     trigger_count=len(native_triggers[a['id']]),
                     failed_at_target=cycle in native_failures[a['id']]) for a in relevant]
    exact_target = [v for v in buggy['oracle']['violations'] if v['cycle'] == cycle and v['obligation'] == obligation]
    transactions = buggy['oracle']['transactions']
    tids = set(violation.get('oracle_details', {}).get('outstanding', []))
    if violation.get('transaction_id'):
        tids.add(violation['transaction_id'])
    aligned = []
    for transaction in transactions:
        if transaction['transaction_id'] in tids:
            paired = next((t for t in fixed['oracle']['transactions']
                           if t['transaction_id'] == transaction['transaction_id']), None)
            aligned.append(dict(buggy=transaction, fixed=paired,
                matched_accept=bool(paired and all(paired[k] == transaction[k]
                    for k in ('accept_cycle', 'data', 'epoch')))))
    no_alarm = all(not any(epochs.get(c) == epoch and c <= cycle for c in values)
                   for values in native_failures.values())
    fixed_epochs = epoch_map(fixed['trace'])
    fixed_no_alarm = all(not any(fixed_epochs.get(c) == epoch and c <= cycle for c in values)
                        for values in marker_map(fixed['native'], 'failures').values())
    health = {}
    for variant, run in runs.items():
        n = run['native']
        health[variant] = dict(compile=n.get('compile_status'), support=n.get('tool_support_status'),
            execution=n.get('execution_status'), native_cover=n.get('trigger_measurement'),
            oracle_unknown=run['oracle']['unknown'], oracle_matches_archive=run['oracle_matches_archive'])
    healthy = all(h['compile'] == 'passed' and h['support'] == 'supported_for_compiled_constructs'
        and h['execution'] == 'completed' and 'native cover property' in h['native_cover'].lower()
        and not h['oracle_unknown'] and h['oracle_matches_archive'] for h in health.values())
    # Drain targets reference outstanding transaction IDs, not a response event.
    transaction_confirmed = bool(aligned) and all(t['matched_accept'] for t in aligned)
    conditions = dict(
        legal_inputs=all(r['oracle']['legality'] == 'legal' for r in runs.values()),
        accepted_transactions_aligned=same_inputs and transaction_confirmed,
        buggy_violates_confirmed_obligation=bool(exact_target),
        fixed_satisfies_same_obligation=bool([c for c in fixed['oracle']['checks']
            if c['obligation'] == obligation and c['cycle'] == cycle and c['passed']])
            and not fixed['oracle']['violations'] and same_inputs,
        candidate_misses_with_accepted_legal_control=no_alarm and fixed_no_alarm)
    if not relevant:
        subtype = 'no_assertion_mapped_to_obligation'
    elif any(m['trigger_at_target'] is None for m in measured):
        subtype = 'trigger_unknown'
    elif any(m['trigger_at_target'] for m in measured):
        subtype = 'triggered_but_constraint_insufficient'
    else:
        subtype = 'mapped_assertions_not_triggered_at_target'
    return dict(valid=healthy and all(conditions.values()), conditions=conditions,
        native_and_oracle_healthy=healthy, native_health=health, obligation=obligation,
        fault_mode=mode, cycle=cycle, miss_subtype=subtype, mapped_assertions=measured,
        all_candidate_trigger_counts={a['id']:len(native_triggers[a['id']]) for a in candidate['assertions']},
        aligned_transactions=aligned, same_accepted_inputs=same_inputs,
        source_query=str(query), source_hashes={str(p.relative_to(ROOT)):digest(p) for p in sources},
        scope='Finite native replay of artificial FIFO boundary fault; no original FIFO presented bug claim or formal proof.')


def audit_search(search_root):
    search_root = Path(search_root)
    protocol, records = read(search_root/'protocol.json'), read(search_root/'results.json')
    methods = {}
    for method in protocol['methods']:
        subset = [r for r in records if r['method'] == method]
        keys = [set(r['evidence']['obligation_gap_keys']) for r in subset]
        unique = set().union(*keys)
        per_seed_duplicates = sum(r['duplicate_gap_keys'].__len__() for r in subset)
        global_duplicates = sum(map(len, keys))-len(unique)
        methods[method] = dict(queries=len(subset), native_replays=sum(r['cost']['native_replays'] for r in subset),
            unique_gap_keys=sorted(unique), unique_gap_count=len(unique),
            archived_duplicate_gap_observations=per_seed_duplicates,
            recomputed_cross_seed_duplicate_gap_observations=global_duplicates,
            unknown_queries=sum(r['evidence']['status'] != 'ok' for r in subset))
    contract = set(methods['contract_coverage']['unique_gap_keys'])
    for method, summary in methods.items():
        summary['contract_additional_gap_keys_vs_this_method'] = sorted(contract-set(summary['unique_gap_keys']))
    return dict(methods=methods, candidate_disagreement_eligible=protocol['candidate_disagreement_eligible'],
        same_candidate_sha256=protocol['candidate_sha256'], declared_specs=protocol['specs'],
        planned_queries=protocol['planned_queries'], planned_replays=protocol['planned_replays'],
        dedup=protocol['dedup'],
        audit_findings=[
            'Per-query duplicate tracking resets each seed. Unique gap totals union seeds correctly, but archived duplicate totals omit cross-seed repetitions; corrected counts supplied.',
            'Single-property disagreement has no genuine candidate pair. It consumes random decisions differently from ordinary, so a different result is exploration variance, not disagreement efficacy.',
            'Search classifications do not themselves gate every native/unknown condition. New witness admission must call strict validation before exporting treatment.',
            'Obligation labels are declared proxies. Missing declared mapping is distinct from mapped-property vacuity, and neither proves a semantic entailment theorem.'
        ])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--search', type=Path, default=ROOT/'deliverables/research16_ablation_20261016_r02/search')
    parser.add_argument('--out', type=Path, default=ROOT/'deliverables/research17_search_audit_20261016_r01')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    witness = validate_witness(args.search)
    comparison = audit_search(args.search)
    parent = read(ROOT/'deliverables/research15_integration_20261015_r01/parent_status.json')
    stat = read(ROOT/'deliverables/historical_record_recovery_20261015_r01/stat_origin/effective_provenance.json')
    result = dict(witness=witness, comparison=comparison,
        scope_status=dict(stat=stat['effective_classification'], stat_historical_pass=False,
            fifo_presented='unknown; no confirmed original defect witness',
            ibex='Archived original RTL module-level reproduction; not full-chip or LLM refinement validation',
            original_parent_denominator=parent['original_parent_denominator']),
        acceptance_gate_audit=dict(
            existing_checks=['unknown replay rejected', 'historical identity/rows preserved', 'new FP rejected',
                'lost detections rejected', 'lost obligation triggers rejected', 'current gap repair required'],
            integration_requirements=['Pass a non-empty target_keys list for new-gap refinement.',
                'If starting qualification is clean, require zero total FP on accepted set, not only zero newly introduced FP.',
                'Ledger only projects explicitly declared obligations; preserve an all-property native failure check on legal controls.',
                'Keep later oracle violations as unknown, do not discard them from whole-case denominators.'],
            scope='Historical replay only; trigger preservation per evidence row is conservative and does not establish global non-regression'),
        new_model_calls=0, new_rtl_executions=0, independent_test_files_read=False)
    (args.out/'audit.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    (args.out/'witness_validation.json').write_text(json.dumps(witness, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    (args.out/'comparison.json').write_text(json.dumps(comparison, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    (args.out/'script_snapshot.py').write_bytes(Path(__file__).read_bytes())
    lines=['# Archived native-search audit', '',
        f'Five-condition witness valid: {witness["valid"]}. Miss subtype: {witness["miss_subtype"]}.',
        'The original order assertion triggered on prior responses, but no assertion is mapped to finite drain/no-loss. This is an obligation gap; do not label the whole candidate vacuous.', '',
        '| Method | Queries | Replays | Independent gap classes | Cross-seed duplicates |',
        '|---|---:|---:|---:|---:|']
    for method, v in comparison['methods'].items():
        lines.append(f'| {method} | {v["queries"]} | {v["native_replays"]} | {v["unique_gap_count"]} | {v["recomputed_cross_seed_duplicate_gap_observations"]} |')
    lines += ['', 'Contract additionally found drop/drain_no_loss versus ordinary/raw difference in this small run; the degenerate disagreement exploration also found it. No exclusive or general superiority is established.', '',
        'The exported drain target had null transaction_id, but its outstanding list identifies e1:t3. The audit resolves that ID to accepted input and fixed response cycles, preserving the missing mutant response.', '',
        'All source artifacts remain unchanged. This audit recomputed the independent oracle from archived native traces; no model call, new RTL execution, or independent-test read occurred.', '',
        'Stat provenance/timing remains unresolved; original FIFO presented defect remains unknown. Artificial FIFO boundary faults and Ibex module-level reproductions must remain separate cohorts.', '',
        'See audit.json for gate integration requirements and source hashes.']
    (args.out/'REPORT.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    manifest={str(p.relative_to(args.out)):digest(p) for p in args.out.rglob('*') if p.is_file()}
    (args.out/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(dict(witness_valid=witness['valid'], miss_subtype=witness['miss_subtype'],
        methods={k:v['unique_gap_count'] for k,v in comparison['methods'].items()},out=str(args.out))))


if __name__ == '__main__':
    main()
