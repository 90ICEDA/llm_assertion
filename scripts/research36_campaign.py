"""Event-validated applicability, real SVA repair, native history and fresh holdout.

Reuse research35 native evidence and gates. Never edit a model expression.
prepare is local only; run needs a bound authorization for the new call scope.
"""
import argparse
import copy
import json
from pathlib import Path
import shutil
import research17_loop as loop
import research31_gate as gate
import research32_runtime as extension
from research32_campaign import initial_feedback
from research34_campaign import snapshot, digest
from research34_applicability import PlanModel, native_target_gate, portable
from research35_campaign import EvidenceModel, holdout
from research36_applicability import validate_events, request_from_previous
from research17_report import artifacts, cost_audit

read, dump = loop.read, loop.dump
PREP = loop.ROOT / 'deliverables/research35_prepare_20261021_r02'
PRIOR = loop.ROOT / 'deliverables/research35_real_20261021_r01'


def prepare(out):
    for n, h in read(PREP / 'prepared_hashes.json').items():
        assert digest(PREP / n) == h, n
    loop.prepare(out)
    snapshot(out)
    for name in ('shared_initial', 'model_config', 'target_cases', 'target_baseline', 'full_cases', 'full_baseline', 'windows.public', 'expected.private'):
        shutil.copy2(PREP / (name + '.json'), out / (name + '.json'))
    request = request_from_previous(PREP, PRIOR)
    dump(out / 'request.preview.json', request)
    expected = read(out / 'expected.private.json')
    # Explicit oracle fixture, never a model result or submitted request.
    fixture = dict(windows=[])
    for t in expected:
        prev, now = t['samples']
        fixture['windows'].append(dict(**{k: t[k] for k in ('id', 'anchor_cycle', 'check_cycle', 'applicability')},
                                      pending=bool(not prev['rst'] and prev['mvalid'] and not prev['mready']), reset=bool(now['rst'])))
    tests = []
    def check(name, value, accepted):
        decision = validate_events(value, expected)
        tests.append(dict(name=name, expected_acceptance=accepted, passed=decision['accepted'] == accepted, decision=decision))
        assert tests[-1]['passed'], name
    check('oracle_fixture_not_model', fixture, True)
    for i, row in enumerate(fixture['windows']):
        for field in ('pending', 'reset'):
            bad = copy.deepcopy(fixture)
            bad['windows'][i][field] = not row[field]
            check(f'{row["id"]}:wrong_{field}_correct_label', bad, False)
    for label in ('cancelled', 'not_required'):
        bad = copy.deepcopy(fixture)
        row = next(r for r in bad['windows'] if r['id'] == ('w4' if label == 'cancelled' else 'w8'))
        row['applicability'] = label
        check('actual_research35_failure_' + row['id'], bad, False)
    for kind in ('missing', 'duplicate', 'unknown', 'non_boolean', 'shifted_cycle'):
        bad = copy.deepcopy(fixture)
        if kind == 'missing': bad['windows'].pop()
        elif kind == 'duplicate': bad['windows'].append(copy.deepcopy(bad['windows'][0]))
        elif kind == 'unknown': bad['windows'][0]['applicability'] = 'unknown'
        elif kind == 'non_boolean': bad['windows'][0]['pending'] = 1
        else: bad['windows'][0]['check_cycle'] += 1
        check(kind, bad, False)
    dump(out / 'local_validator_tests.json', dict(passed=all(t['passed'] for t in tests), tests=tests, scope='Validator tests only; zero model calls.'))
    actual = portable(read(PREP / 'qualification_reuse.json')['source'])
    controls = []
    for name, slot, wanted in (('bad', 'a4', False), ('good', 'a2', True)):
        result_path = actual / 'core' / name / 'result.json'
        verdict = native_target_gate(read(out / 'target_baseline.json'), read(result_path), slot)
        assert verdict['accepted'] == wanted
        controls.append(dict(name=name, source=str(result_path), sha256=digest(result_path), decision=verdict))
    dump(out / 'reused_native_controls.json', controls)
    dump(out / 'qualification.json', dict(passed=True, validator_checks=len(tests), windows=len(expected),
         targets=8, full_history_scenarios=len(read(out / 'full_cases.json')), native_reexecutions=0,
         reused_preparation=str(PREP), new_model_calls=0, previous_model_runs_are_not_reclassified=True))
    dump(out / 'protocol.json', dict(maximum_calls=4, maximum_plan_calls=2, maximum_sva_calls=2, retries=0,
         endpoint=request['model'] and read(out / 'model_config.json')['remote_url'], model=request['model'],
         gates='All event claims AND original three-way labels; native edited-property target gate; complete history; accepted freeze; fresh 56-scenario holdout.',
         stopping='No SVA after failed plan. Stop on acceptance. No holdout after rejection. No response retries.',
         authorization_needed='Explicit reassignment of 2 unused research35 calls plus up to 2 new calls; no request submitted by prepare.',
         expected_table='Local only. Actual prior model rejections are development feedback.',
         scope='One selected complex FIFO task with explicit artificial faults; no stability or historical upstream success claim.'))
    dump(out / 'prepared_hashes.json', {p.relative_to(out).as_posix(): digest(p) for p in out.glob('*.json')})
    print('PREPARED', dict(checks=len(tests), windows=len(expected), model_calls=0), flush=True)


def next_request(request, plan, verdict):
    result = copy.deepcopy(request)
    body = json.loads(result['messages'][1]['content'])
    # Send only the actual failed checks; successful certificates/full truth
    # table stay local. This also bounds the follow-up prompt size.
    body['current_actual_attempt'] = dict(plan=plan, rejection=dict(accepted=False, reasons=verdict['reasons']))
    result['messages'][1]['content'] = json.dumps(body)
    return result


def run(prep, out, authorization):
    auth = read(authorization)
    protocol = read(prep / 'protocol.json')
    assert auth['authorized_calls'] == 4 and auth['maximum_plan_calls'] == auth['maximum_sva_calls'] == 2
    assert auth['endpoint'] == protocol['endpoint'] and auth['model'] == protocol['model']
    assert auth['run_output'] == out.relative_to(loop.ROOT).as_posix()
    for n, h in read(prep / 'prepared_hashes.json').items(): assert digest(prep / n) == h, n
    for n, h in read(prep / 'source_snapshot/hashes.json').items(): assert digest(loop.ROOT / 'scripts' / n) == h, n
    loop.prepare(out)
    snapshot(out)
    shutil.copy2(authorization, out / 'authorization.json')
    dump(out / 'protocol.json', protocol)
    initial = read(prep / 'shared_initial.json')
    current = initial
    models = []
    status = 'not_started'
    try:
        request = read(prep / 'request.preview.json')
        settings = read(prep / 'model_config.json')
        model = PlanModel(out / 'plan', settings, request)
        models.append(model)
        plan_ok = False
        for i in range(2):
            _, plan = model.call(out / 'plan' / f'v{i}' / 'model_call', initial, 'stall_stability', {}, 'event_applicability_repair')
            verdict = validate_events(plan, read(prep / 'expected.private.json'))
            dump(out / 'plan' / f'v{i}' / 'decision.json', verdict)
            print('PLAN', i, 'accepted', verdict['accepted'], 'reasons', len(verdict['reasons']), flush=True)
            if verdict['accepted']:
                plan_ok = True
                break
            request = next_request(request, plan, verdict)
            model.payload = request
        if not plan_ok:
            status = 'applicability_unresolved'
            return
        model = EvidenceModel(out / 'sva', settings, plan)
        models.append(model)
        before = read(prep / 'full_baseline.json')
        feedback = initial_feedback(before)
        with extension.installed():
            for i in range(2):
                version = out / 'core' / f'v{i}'
                call, candidate = model.call(version / 'model_call', current, 'stall_stability', feedback, 'event_verified_boundary_repair')
                verdict = dict(accepted=False, reasons=[call.get('proposal_rejection', dict(kind='unusable_model_output'))])
                small = None
                if candidate:
                    edit = read(version / 'model_call/model_edit.json')
                    small = loop.replay(candidate, version / 'target_native', read(prep / 'target_cases.json'))
                    verdict = native_target_gate(read(prep / 'target_baseline.json'), small, edit['assertion_id'])
                    dump(version / 'target_gate.json', verdict)
                    if verdict['accepted']:
                        full = loop.replay(candidate, version / 'history_native', read(prep / 'full_cases.json'))
                        verdict = gate.decide(before['group']['ledger'], full['group']['ledger'], sorted(loop.inspect(before['group']['ledger'])['misses'])) if full.get('group') else dict(accepted=False, reasons=[dict(kind='native_unavailable')])
                        verdict['accepted'] = bool(verdict['accepted'] and full['healthy'])
                        dump(version / 'historical_gate.json', verdict)
                dump(version / 'decision.json', verdict)
                print('SVA', i, 'accepted', verdict['accepted'], 'reasons', len(verdict['reasons']), flush=True)
                if verdict['accepted']:
                    current = candidate
                    break
                feedback.update(actual_rejection=verdict, transport_or_interface_diagnostic=call)
                if small and small.get('feedback'): feedback['actual_native_evidence'] = small['feedback']
            loop.freeze(out / 'core', current, 'terminal_before_new_independent_inputs')
            if loop.sha(current) == loop.sha(initial):
                status = 'sva_refinement_unresolved'
                return
            holdout(out, current, read(prep / 'full_cases.json'))
            status = 'accepted_and_independent_completed'
    except BaseException:
        status = 'execution_exception'
        raise
    finally:
        if not (out / 'core/freeze.json').exists(): loop.freeze(out / 'core', current, 'retained_after_failed_trial')
        calls = [c for m in models for c in m.calls]
        dump(out / 'model_cost.json', dict(calls=len(calls), prompt_tokens=sum(c.get('prompt_tokens') or 0 for c in calls),
             completion_tokens=sum(c.get('completion_tokens') or 0 for c in calls),
             usage_unavailable=sum(c.get('prompt_tokens') is None or c.get('completion_tokens') is None for c in calls)))
        dump(out / 'outcome.json', dict(status=status, calls=len(calls), accepted=loop.sha(current) != loop.sha(initial), frozen_hash=loop.sha(current)))
        dump(out / 'cost.json', cost_audit(out, artifacts(out)))
        print('TERMINAL', status, flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=('prepare', 'run'))
    p.add_argument('--out', required=True, type=Path)
    p.add_argument('--prepared', type=Path)
    p.add_argument('--authorization', type=Path)
    a = p.parse_args()
    out = a.out.resolve()
    assert loop.ROOT in out.parents
    if a.action == 'prepare': prepare(out)
    else: run(a.prepared.resolve(), out, a.authorization.resolve())
