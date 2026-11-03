"""Qualification of opt-in obligation labels; never a model repair experiment."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys

import research20_model as model
import research15_native_interface as native
import research17_fifo_feedback as runtime
import research15_search_experiment as search
from research15_evidence import paired_ledger
from research15_acceptance import inspect


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    assert native.ROOT in out.parents
    out.mkdir(parents=True, exist_ok=False)
    source = native.ROOT / 'deliverables/research19_closed_loop_20261016_r03/shared_initial.json'
    original = json.loads(source.read_text())
    checks = []

    def check(name, passed, detail=None):
        checks.append(dict(name=name, passed=bool(passed), detail=detail))

    def rejected(name, fn):
        try:
            fn()
        except (AssertionError, TypeError, KeyError, ValueError) as exc:
            check(name, True, repr(exc))
        else:
            check(name, False, 'Unexpected acceptance')

    candidate = copy.deepcopy(original)
    labels = ['order_payload', 'reset_cancellation']
    candidate['assertions'][0]['obligations'] = labels.copy()
    rejected('default_rejects_multiple_labels', lambda: native.normalize_candidate(candidate))
    candidate['syntax_profile'] = 'qualified_sampled_v1'
    rejected('sampled_v1_still_rejects_multiple_labels', lambda: native.normalize_candidate(candidate))
    candidate['syntax_profile'] = 'qualified_sampled_multi_v2'
    candidate = native.normalize_candidate(candidate)
    check('native_preserves_exact_original_property', candidate['assertions'][0]['property'] == original['assertions'][0]['property'])
    check('native_preserves_declared_labels', candidate['assertions'][0]['obligations'] == labels)
    ant = native.unparen(original['assertions'][0]['derived_antecedent'])
    cons = native.unparen(original['assertions'][0]['consequent'])
    edit = dict(operation='replace', assertions=[dict(antecedent=ant, consequent=cons,
                timing='same_sample', obligation=labels.copy())], reason='Interface-only label qualification')
    assembled = model.assemble(edit, None)
    check('replace_exact_expression_preserved', assembled['assertions'][0]['property'] == original['assertions'][0]['property'])
    check('replace_labels_preserved', assembled['assertions'][0]['obligations'] == labels)
    check('replace_does_not_mutate_input', edit['assertions'][0]['obligation'] == labels)
    kept = model.assemble(dict(operation='keep', assertions=[], reason='Qualification'), assembled)
    check('keep_preserves_complete_candidate', kept == assembled and kept is not assembled)
    add = dict(operation='add', assertions=[dict(antecedent='drain_due', consequent='ref_count == 0',
                timing='same_sample', obligation='drain_no_loss')], reason='Interface-only assembly probe, not executed')
    added = model.assemble(add, assembled)
    check('add_preserves_original_set', len(added['assertions']) == 2 and added['assertions'][0] == assembled['assertions'][0])
    check('add_preserves_new_single_label', added['assertions'][1]['obligations'] == ['drain_no_loss'])
    replaced = model.assemble(edit, added)
    check('replace_removes_previous_other_properties', len(replaced['assertions']) == 1 and replaced == assembled)
    for invalid in ([], ['invalid_obligation'], ['order_payload', 'order_payload'], ['order_payload', 'invalid_obligation']):
        bad = copy.deepcopy(edit)
        bad['assertions'][0]['obligation'] = invalid
        rejected('reject_model_labels_' + repr(invalid), lambda bad=bad: model.assemble(bad, None))
        bad_candidate = copy.deepcopy(candidate)
        bad_candidate['assertions'][0]['obligations'] = invalid
        rejected('reject_native_labels_' + repr(invalid), lambda bad_candidate=bad_candidate: native.normalize_candidate(bad_candidate))
    sampled = copy.deepcopy(edit)
    sampled['assertions'][0].update(antecedent='$rose(drain_due)', consequent='ref_count == 0')
    check('qualified_sampled_expression_stays_model_text',
          native.unparen(model.assemble(sampled, None)['assertions'][0]['derived_antecedent']) == '$rose(drain_due)')
    native.dump(out / 'invocation.json', dict(argv=sys.argv, source=str(source),
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(), model_calls=0,
        scope='Interface qualification using old real-model property unchanged; added metadata labels are deliberately unproven. No new LLM call or repair claim.'))
    native.dump(out / 'assembly_checks.json', checks)
    native.dump(out / 'candidate.json', candidate)
    (out / 'candidate.sva').write_text(native.candidate_sva(candidate))
    rows = search.stimulus(2026101507, 'reset_pending')
    native.dump(out / 'stimulus.json', rows)
    native.dump(out / 'expectations_before_execution.json', dict(
        reset_violation='Independent oracle must find at least one reset_cancellation target.',
        labels_do_not_detect='Original order property requires ref_count>0; a cancelled output with zero outstanding references must remain a missed reset target despite its added label.',
        legal_samples='Triggering without a native failure never counts as violation detection.',
        model_calls=0))
    compiled = runtime.build(candidate, out / 'native/compiled', 2, 0)
    fixed = runtime.execute(compiled, out / 'native/correct', rows, 'correct')
    mutant = runtime.execute(compiled, out / 'native/reset_residue', rows, 'reset_residue')
    ledger = paired_ledger(fixed, mutant, 'mapping_qualification:d2:p0:s2026101507')
    native.dump(out / 'ledger.json', ledger)
    summary = inspect(ledger['ledger'])
    for record in (fixed, mutant):
        n = record['native']
        check('native_health_' + record['mode'], n['compile_status'] == 'passed' and
              n['execution_status'] == 'completed' and record['sampling_qualification']['status'] == 'passed' and
              record['oracle']['legality'] == 'legal' and not record['oracle']['unknown'])
    reset_targets = [r for r in ledger['ledger'] if r['obligation'] == 'reset_cancellation' and r['oracle']['verdict'] == 'violated']
    check('actual_reset_targets_exist', bool(reset_targets), len(reset_targets))
    check('added_reset_label_does_not_make_detection', bool(reset_targets) and all(r['evidence_id'] in summary['misses'] for r in reset_targets))
    check('actual_reset_targets_have_no_trigger_or_failure', bool(reset_targets) and all(
        a['trigger'] is False and a['failed'] is False and a['causal_detection'] is False
        for r in reset_targets for a in r['native']['assertions']))
    triggered_legal = [r for r in ledger['ledger'] if r['oracle']['verdict'] == 'satisfied' and any(a['trigger'] and not a['failed'] for a in r['native']['assertions'])]
    check('trigger_without_failure_is_not_detection', bool(triggered_legal) and all(r['evidence_id'] not in summary['detections'] for r in triggered_legal), len(triggered_legal))
    check('no_false_positives_or_unknown', not summary['false_positives'] and not summary['unknown'])
    result = dict(passed=all(c['passed'] for c in checks), checks=checks,
                  target_rows=reset_targets, model_calls=0,
                  costs=dict(native_compiles=1, native_executions=3, explanation='One compiled-run smoke and two paired scenario executions.'),
                  counts={k:len(summary[k]) for k in ('detections','triggers','misses','false_positives','unknown')},
                  scope='Finite interface qualification only. No LLM-generation/repair success; adding obligation labels does not establish protection.')
    native.dump(out / 'result.json', result)
    native.dump(out / 'source_hashes.json', {str(p.relative_to(native.ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in [Path(__file__), native.ROOT/'scripts/research20_model.py', native.ROOT/'scripts/research15_native_interface.py', native.ROOT/'scripts/research15_evidence.py', native.ROOT/'scripts/research15_acceptance.py']})
    print(json.dumps(dict(passed=result['passed'], checks=len(checks), counts=result['counts']), indent=2))
    if not result['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
