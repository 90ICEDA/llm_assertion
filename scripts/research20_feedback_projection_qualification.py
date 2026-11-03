"""Actual-development feedback fidelity checks; no model or native executions."""
import argparse
import copy
import hashlib
import json
from pathlib import Path

from research19_feedback import focus_feedback
from research20_model import project_feedback
from research20_loop import coverage_samples
from research17_model import ROOT, dump, read


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    source, out = args.source.resolve(), args.out.resolve()
    assert ROOT in source.parents and ROOT in out.parents
    out.mkdir(parents=True, exist_ok=False)
    path = source / 'core/before/result.json'
    original = read(path)
    plan = read(source / 'development_plan.json')
    rejection = read(source / 'core/v0/decision.json')
    checks, cases, sources = [], [], [path, source / 'development_plan.json', source / 'core/v0/decision.json']

    def check(name, passed, detail=None):
        checks.append(dict(name=name, passed=bool(passed), detail=detail))

    def audit(name, feedback, target):
        untouched = copy.deepcopy(feedback)
        full = focus_feedback(feedback, target)
        projected = project_feedback(feedback, target)
        check(name + ':input_unchanged', feedback == untouched)
        # Locate emitted cards by actual scenario/cycle, independently of order.
        for field, sides in [('paired_target_samples', ('fixed', 'mutant')),
                             ('legal_control_failure_samples', ('fixed',))]:
            originals = {(p['scenario'], p['cycle']): p for p in full[field]}
            for i, card in enumerate(projected[field]):
                key = (card['scenario'], card['cycle'])
                check(f'{name}:{field}:{i}:actual_card_exists', key in originals)
                old = originals.get(key, {})
                for side in sides:
                    for retained_key, value in card[side].items():
                        check(f'{name}:{field}:{i}:{side}:{retained_key}:exact', retained_key in old.get(side, {}) and value == old[side][retained_key])
                    # Each non-null sample must ALSO exist in the raw archived
                    # native feedback window; independent from focus_feedback.
                    diagnostic = next(e['diagnostic'][side] for e in original['feedback'] if e['scenario'] == card['scenario'])
                    samples = [s for w in diagnostic.get('sample_windows', []) for s in w.get('samples', []) if s['cycle'] == card['cycle']]
                    actual_sample = card[side].get('sample')
                    check(f'{name}:{field}:{i}:{side}:raw_native_sample', actual_sample in samples if actual_sample is not None else not samples)
        counts = projected['selection']
        check(name + ':paired_available_count', counts['paired_available'] == len(full['paired_target_samples']))
        check(name + ':paired_shown_count', counts['paired_shown'] == len(projected['paired_target_samples']) == min(4, counts['paired_available']))
        check(name + ':legal_available_count', counts['legal_failures_available'] == len(full['legal_control_failure_samples']))
        check(name + ':legal_shown_count', counts['legal_failures_shown'] == len(projected['legal_control_failure_samples']) == min(2, counts['legal_failures_available']))
        check(name + ':counts_verbatim', projected['counts'] == original['counts'])
        for key in ('actual_rejection', 'previous_rejected_proposal'):
            check(name + ':' + key + '_preserved', key in projected and projected[key] == feedback[key])
        for i, card in enumerate(projected.get('coverage_samples', [])):
            matching = [s for s in feedback['coverage_samples'] if s['scenario'] == card['scenario'] and s['independent_check'] == card['independent_check']]
            check(f'{name}:coverage:{i}:actual_values_preserved', bool(matching) and all(card[k] == matching[0][k] for k in card))
            check(f'{name}:coverage:{i}:not_invented_violation', card['independent_check']['passed'] is True)
        # A structural recursive subset check rules out injected predicates or
        # invented verdicts in all retained evidence cards, rather than merely
        # searching for a known expected expression.
        def subset(child, parent):
            if isinstance(child, dict):
                return isinstance(parent, dict) and all(k in parent and subset(v, parent[k]) for k, v in child.items())
            if isinstance(child, list):
                return child == parent
            return child == parent
        check(name + ':all_evidence_is_unmodified_projection', all(
            any(subset(card, old) for old in full[field])
            for field in ('paired_target_samples', 'legal_control_failure_samples', 'historical_observations')
            for card in projected[field]))
        cases.append(dict(name=name, target=target, selection=counts,
                          coverage_cards=len(projected['coverage_samples'])))
        dump(out / (name + '.json'), projected)
        return full, projected

    for target in ('drain_no_loss', 'no_unsolicited_output', 'stall_stability'):
        obligations = [target] if target != 'no_unsolicited_output' else [target, 'reset_cancellation']
        feedback = dict(counts=original['counts'], actual_native_evidence=original['feedback'],
                        coverage_samples=coverage_samples(source / 'core/before', plan, obligations),
                        actual_rejection=rejection, previous_rejected_proposal=[])
        full, projected = audit(target, feedback, target)
        if target == 'stall_stability':
            check('stall:no_invented_target_violation', full['paired_target_samples'] == projected['paired_target_samples'] == [])
            check('stall:actual_legal_coverage_kept', bool(projected['coverage_samples']))
        else:
            check(target + ':actual_fixed_mutant_pairs_present', len(projected['paired_target_samples']) == 2)
        # Cap-boundary qualification repeats actual records unchanged. These
        # are deliberately duplicate fixture rows, NEVER additional evidence.
        stress = copy.deepcopy(feedback)
        stress['actual_native_evidence'] *= 3
        audit(target + '_duplicate_cap_fixture', stress, target)

    # r20/r01 had no generated rejected proposal because preflight stopped each
    # call. Use an archived REAL rejected r19 model proposal solely to exercise
    # nonempty metadata preservation; do not call it part of r20's history.
    old_source = ROOT / 'deliverables/research19_closed_loop_20261016_r03/core/v1/model_call/model_edit.json'
    old_proposal = read(old_source)
    sources.append(old_source)
    metadata_fixture = dict(counts=original['counts'], actual_native_evidence=original['feedback'],
        coverage_samples=[], actual_rejection=rejection, previous_rejected_proposal=old_proposal)
    audit('archived_nonempty_proposal_metadata_fixture', metadata_fixture, 'drain_no_loss')
    result = dict(passed=all(c['passed'] for c in checks), checks=checks, cases=cases,
        source_hashes={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
        implementation_hash=hashlib.sha256((ROOT / 'scripts/research20_model.py').read_bytes()).hexdigest(),
        model_calls=0, native_executions=0, formal_calls=0,
        scope='Actual development-feedback projection fidelity only; no repair claim, no independent test reads. Duplicate cap fixture preserves actual values but is not new evidence. Nonempty r19 metadata fixture is not r20 experimental history.',
        limitations=['r20 before contains no fixed-control native failures, so nonempty legal-failure clipping is not qualified by these records.',
                     'Native marker arrays, source paths, status details and inherited-source metadata are deliberately omitted from the model projection; saved full records and native acceptance remain authoritative.',
                     'stall_stability has actual legal coverage samples but no target violation in this source; qualification does not invent one.'])
    dump(out / 'qualification.json', result)
    print(json.dumps(dict(passed=result['passed'], checks=len(checks), cases=cases), indent=2))
    if not result['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
