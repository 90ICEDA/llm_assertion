"""Select actual development observations; never synthesize assertion predicates.

The adapter reorders evidence, not its verdicts or signal values. Native replay
and the independent oracle remain authoritative. It never reads holdout files.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path


def _sample(record, cycle):
    for window in record.get('sample_windows', []):
        for sample in window.get('samples', []):
            if sample.get('cycle') == cycle:
                return copy.deepcopy(sample)
    return None


def _native_at(record, cycle):
    result = []
    for prop in record.get('properties', []):
        # Missing marker arrays must remain unknown, never become False.
        result.append(dict(id=prop.get('id'), obligations=prop.get('obligations'),
            property=prop.get('property'),
            triggered=(cycle in prop['trigger_cycles']) if 'trigger_cycles' in prop else None,
            failed=(cycle in prop['failure_cycles']) if 'failure_cycles' in prop else None))
    return result


def _side(record, cycle):
    return dict(mode=record.get('mode'), sample=_sample(record, cycle),
        native_at_cycle=_native_at(record, cycle), native_status=record.get('native_status'),
        independent_oracle=dict(legality=record.get('oracle_legality'),
            unknown=record.get('oracle_unknown'),
            first_violations_at_cycle=[v for v in record.get('first_oracle_violations', [])
                                       if v.get('cycle') == cycle]),
        sampling_qualification=record.get('sampling_qualification', {}).get('status'),
        source=copy.deepcopy(record.get('artifacts', {})))


def _summary(record):
    return dict(mode=record.get('mode'), native_status=record.get('native_status'),
        properties=[{key: prop.get(key) for key in
            ('id', 'obligations', 'trigger_count', 'failure_count', 'execution_observation')}
            for prop in record.get('properties', [])],
        oracle_legality=record.get('oracle_legality'), oracle_unknown=record.get('oracle_unknown'),
        source=copy.deepcopy(record.get('artifacts', {})))


def _compact(value):
    if isinstance(value, list):
        return [_compact(v) for v in value]
    if not isinstance(value, dict):
        return value
    result = {}
    for key, val in value.items():
        if key in ('evidence_keys', 'current_gap_ids') and isinstance(val, list):
            result[key + '_count'] = len(val)
        elif key not in ('initial_feedback', 'actual_native_evidence'):
            result[key] = _compact(val)
    return result


def _evidence_source(feedback):
    """Find the nearest archived evidence carried by the caller's envelope.

    An interface failure has no new native execution. Its empty evidence list
    must not erase earlier observations or represent them as a new replay.
    """
    cursor, path, visited = feedback, '$', set()
    while isinstance(cursor, dict) and id(cursor) not in visited:
        visited.add(id(cursor))
        entries = cursor.get('actual_native_evidence')
        if isinstance(entries, list) and entries:
            return entries, dict(path=path + '.actual_native_evidence',
                inherited=path != '$', new_native_execution_claimed=False,
                counts_at_source=copy.deepcopy(cursor.get('counts')),
                status='available')
        cursor = cursor.get('initial_feedback')
        path += '.initial_feedback'
    return [], dict(path=None, inherited=False, new_native_execution_claimed=False,
                    counts_at_source=None, status='unavailable_in_feedback_envelope')


def focus_feedback(feedback, target):
    """Return target pairs, real legal failures, then compact historical summary.

    No obligations, signal values, failures or predicates are inferred. Missing
    source windows produce null samples and explicit unavailable accounting.
    Only records present in the caller's development feedback are accessed.
    """
    entries, provenance = _evidence_source(feedback)
    pairs, legal_failures, history = [], [], []
    for entry in entries:
        diagnostic = entry.get('diagnostic', {})
        fixed = diagnostic.get('fixed') or {}
        mutant = diagnostic.get('mutant') or {}
        scenario = entry.get('scenario')
        targets = diagnostic.get('target_evidence', [])
        for evidence in targets:
            if evidence.get('obligation') != target:
                continue
            cycle = evidence.get('cycle')
            pairs.append(dict(scenario=scenario, cycle=cycle,
                target_evidence=copy.deepcopy(evidence),
                fixed=_side(fixed, cycle), mutant=_side(mutant, cycle)))
        failures = sorted({cycle for prop in fixed.get('properties', [])
                           for cycle in prop.get('failure_cycles', [])})
        # First failure with an actual archived window, not a synthetic sample.
        available = [cycle for cycle in failures if _sample(fixed, cycle) is not None]
        if failures:
            cycle = available[0] if available else failures[0]
            legal_failures.append(dict(scenario=scenario, cycle=cycle,
                classification='native_failure_on_paired_fixed_control',
                first_native_failure_cycle=failures[0],
                selected_first_failure_with_available_sample=bool(available),
                sample_available=bool(available), fixed=_side(fixed, cycle),
                qualification='Use native failure plus independently confirmed legal fixed control; missing data remains unknown.'))
        history.append(dict(scenario=scenario, fixed=_summary(fixed), mutant=_summary(mutant),
            non_target_evidence=[copy.deepcopy(e) for e in targets if e.get('obligation') != target],
            target_evidence_count=sum(e.get('obligation') == target for e in targets),
            fixed_native_failure_count=len(failures)))
    result = dict(requested_obligation=target, paired_target_samples=pairs,
        legal_control_failure_samples=legal_failures, historical_observations=history,
        selected_native_evidence_source=provenance,
        earlier_feedback_available='initial_feedback' in feedback and feedback['initial_feedback'] is not None,
        interpretation='Actual pre-NBA samples and recorded native markers only. Null is unavailable, not passed. No proposed predicate is supplied by this adapter.')
    for key, val in feedback.items():
        if key not in ('actual_native_evidence', 'initial_feedback'):
            result[key] = _compact(val)
    return result


def qualify(source, out):
    """Qualify on archived development records only, with exact-value checks."""
    source, out = Path(source).resolve(), Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    results = []
    for name, relative in [('before', 'core/before/result.json'),
                           ('rejected', 'core/v0/native/result.json')]:
        path = source / relative
        original = json.loads(path.read_text(encoding='utf-8-sig'))
        feedback = dict(counts=original['counts'], actual_native_evidence=original['feedback'])
        focused = focus_feedback(feedback, 'drain_no_loss')
        checks = []
        for card in focused['paired_target_samples']:
            entry = next(e for e in original['feedback'] if e['scenario'] == card['scenario'])
            for side in ('fixed', 'mutant'):
                expected = _sample(entry['diagnostic'][side], card['cycle'])
                checks.append(card[side]['sample'] == expected and expected is not None)
                checks.append(card[side]['native_at_cycle'] ==
                              _native_at(entry['diagnostic'][side], card['cycle']))
        if name == 'before':
            checks.append(len(focused['paired_target_samples']) == 2)
            checks.append(all(c['fixed']['sample']['drain_due'] == 1 and
                              c['mutant']['sample']['drain_due'] == 1
                              for c in focused['paired_target_samples']))
        if name == 'rejected':
            checks.append(bool(focused['legal_control_failure_samples']))
            for card in focused['legal_control_failure_samples']:
                checks.append(card['sample_available'] and
                              any(p['failed'] is True for p in card['fixed']['native_at_cycle']))
        (out / (name + '.json')).write_text(json.dumps(focused, indent=2) + '\n', encoding='utf-8')
        results.append(dict(name=name, source=str(path), source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            checks=len(checks), passed=all(checks), target_cards=len(focused['paired_target_samples']),
            legal_failure_cards=len(focused['legal_control_failure_samples'])))
        # These are envelope-transition fixtures using unchanged actual native
        # records, not mock executions or generated experiment successes.
        first_failure = dict(actual_native_evidence=[], initial_feedback=feedback,
            transport_or_interface_diagnostic={'candidate_status': 'interface_rejected'})
        second_failure = dict(actual_native_evidence=[], initial_feedback=first_failure,
            transport_or_interface_diagnostic={'candidate_status': 'interface_rejected'})
        recovered = []
        for index, envelope in enumerate((first_failure, second_failure), 1):
            answer = focus_feedback(envelope, 'drain_no_loss')
            expected_path = '$' + '.initial_feedback' * index + '.actual_native_evidence'
            transition_checks = [
                answer['paired_target_samples'] == focused['paired_target_samples'],
                answer['legal_control_failure_samples'] == focused['legal_control_failure_samples'],
                answer['historical_observations'] == focused['historical_observations'],
                answer['selected_native_evidence_source']['path'] == expected_path,
                answer['selected_native_evidence_source']['inherited'] is True,
                answer['selected_native_evidence_source']['new_native_execution_claimed'] is False]
            recovered.append(dict(consecutive_interface_failures=index,
                checks=len(transition_checks), passed=all(transition_checks), focused=answer))
        # Prefer a newer nonempty envelope; never merge it with older markers.
        newer = dict(actual_native_evidence=original['feedback'], initial_feedback=first_failure)
        nearest = focus_feedback(newer, 'drain_no_loss')
        unavailable = focus_feedback(dict(actual_native_evidence=[], initial_feedback=None), 'drain_no_loss')
        extra_checks = [nearest['selected_native_evidence_source']['path'] == '$.actual_native_evidence',
            nearest['selected_native_evidence_source']['inherited'] is False,
            unavailable['paired_target_samples'] == [],
            unavailable['selected_native_evidence_source']['status'] == 'unavailable_in_feedback_envelope']
        transition = dict(scope='Envelope retention qualification only; caller must retain initial_feedback across failures.',
            source=str(path), transitions=recovered, additional_checks_passed=all(extra_checks))
        (out / (name + '_interface_failure_retention.json')).write_text(json.dumps(transition, indent=2) + '\n', encoding='utf-8')
        results.append(dict(name=name + '_interface_failure_retention',
            checks=sum(r['checks'] for r in recovered) + len(extra_checks),
            passed=all(r['passed'] for r in recovered) and all(extra_checks),
            scope='Actual evidence retained through one/two nested interface failure envelopes; not native replay.'))
    report = dict(passed=all(r['passed'] for r in results), results=results,
        model_calls=0, native_executions=0, formal_calls=0,
        scope='Read-only development feedback transformation qualification; no generation or refinement success claim.',
        implementation_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (out / 'qualification.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report))
    if not report['passed']:
        raise RuntimeError('feedback qualification failed')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    qualify(args.source, args.out)
