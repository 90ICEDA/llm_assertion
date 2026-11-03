"""Prospective, sample-bound event gate; archived research46 is never revised.

The remote phase is plan-only. No SVA model call is implemented here. A passed
real plan can unlock a downstream request, but not a failed or locally repaired
plan. All hardware truth is rechecked through the existing native certificate.
"""
import argparse
import copy
import json
from pathlib import Path
import shutil

import research17_loop as loop
import research31_gate as gate
import research43_paired_ablation as common
import research45_campaign as prior
import research46_cycle_gate as previous
from research34_applicability import certificate
from research36_applicability import validate_events
from research17_report import cost_audit
from research28_report import raw_response

ROOT = loop.ROOT
read, dump = loop.read, loop.dump
PREP46 = ROOT / 'deliverables/research46_prepare_20261022_r01'
RUN46 = ROOT / 'deliverables/research46_real_20261022_r01'
FIELDS = {'id', 'anchor_cycle', 'check_cycle', 'anchor_reset', 'check_reset',
          'anchor_pending', 'applicability'}
BINDINGS = {
    'anchor_cycle': 'anchor_sample.cycle',
    'check_cycle': 'check_sample.cycle',
    'anchor_reset': 'anchor_sample.rst == 1',
    'check_reset': 'check_sample.rst == 1',
    'anchor_pending': 'anchor_sample.rst == 0 and anchor_sample.mvalid == 1 and anchor_sample.mready == 0',
}


def validate(value, expected):
    """Rename explicit check fields for the old oracle; never correct values."""
    reasons, projected, anchors = [], [], []
    if not expected or len({t['id'] for t in expected}) != len(expected):
        return dict(accepted=False, reasons=[dict(kind='invalid_expected_inventory')])
    if not isinstance(value, dict) or set(value) != {'windows'} or not isinstance(value['windows'], list):
        return dict(accepted=False, reasons=[dict(kind='sample_bound_plan_schema')])
    truths = {t['id']: t for t in expected}
    for row in value['windows']:
        if not isinstance(row, dict) or set(row) != FIELDS:
            reasons.append(dict(kind='sample_bound_row_schema'))
            continue
        projected.append(dict(id=row['id'], anchor_cycle=row['anchor_cycle'], check_cycle=row['check_cycle'],
                              pending=row['anchor_pending'], reset=row['check_reset'], applicability=row['applicability']))
        truth = truths.get(row['id']) if isinstance(row['id'], str) else None
        if truth is None:
            reasons.append(dict(kind='unrecognized_sample_window'))
            continue
        source = gate.portable(truth['source'])
        if not source.is_file() or common.digest(source) != truth['source_sha256']:
            reasons.append(dict(kind='native_record_changed', id=row['id']))
            continue
        cert = certificate(read(source), truth['check_cycle'])
        if cert.get('applicability') == 'unknown' or any(cert.get(k) != truth.get(k) for k in
                ('anchor_cycle', 'check_cycle', 'applicability', 'samples', 'oracle_checks')):
            reasons.append(dict(kind='native_certificate_changed', id=row['id']))
            continue
        expected_anchor = bool(cert['samples'][0]['rst'])
        anchors.append(dict(id=row['id'], sample='anchor_sample', cycle=cert['anchor_cycle'], reset=expected_anchor))
        if type(row['anchor_reset']) is not bool or row['anchor_reset'] != expected_anchor:
            reasons.append(dict(kind='incorrect_anchor_reset', id=row['id'], sample='anchor_sample',
                                cycle=cert['anchor_cycle'], expected=expected_anchor, actual=row['anchor_reset']))
        if row['anchor_reset'] is True and row['anchor_pending'] is True:
            reasons.append(dict(kind='model_pending_during_anchor_reset', id=row['id']))
    # Includes strict booleans, integer cycles, all IDs, independent labels,
    # source SHA, and consistency of the model's own pending/reset/label claims.
    legacy = validate_events(dict(windows=projected), expected)
    for reason in legacy['reasons']:
        item = copy.deepcopy(reason)
        if item['kind'] == 'incorrect_event_reset':
            item.update(kind='incorrect_check_reset', sample='check_sample', cycle=truths[item['id']]['check_cycle'])
        elif item['kind'] == 'incorrect_event_pending':
            item.update(kind='incorrect_anchor_pending', sample='anchor_sample', cycle=truths[item['id']]['anchor_cycle'])
        reasons.append(item)
    return dict(accepted=not reasons, reasons=reasons, stage='sample_bound_events_then_applicability',
                bindings=BINDINGS, anchor_certificates=anchors, legacy_gate=legacy,
                windows=len(expected), scope='All fields on these development windows only; not independent model generalization or SVA success.')


def verified_sva_request(template, plan, verdict, expected):
    checked = validate(plan, expected)
    if not checked['accepted'] or checked != verdict:
        raise ValueError('sample_bound_plan_not_accepted')
    request = copy.deepcopy(template)
    body = json.loads(request['messages'][1]['content'])
    body['verified_model_applicability_plan'] = copy.deepcopy(plan)
    body['verified_plan_field_bindings'] = BINDINGS
    body['stage_contract'] = ('Every model event, cycle and applicability claim passed independent native records. '
        'The original model plan is unchanged. SVA still requires native window triggers, causal target detection, '
        'legal controls and full history replay; event acceptance alone never accepts an assertion.')
    request['messages'][1]['content'] = json.dumps(body)
    return request


def fixture(expected):
    """Local validator fixture ONLY; never sent to the model or counted as output."""
    return dict(windows=[dict(id=t['id'], anchor_cycle=t['anchor_cycle'], check_cycle=t['check_cycle'],
        anchor_reset=bool(t['samples'][0]['rst']), check_reset=bool(t['samples'][1]['rst']),
        anchor_pending=bool(not t['samples'][0]['rst'] and t['samples'][0]['mvalid'] and not t['samples'][0]['mready']),
        applicability=t['applicability']) for t in expected])


def qualify(expected, template):
    good = fixture(expected)
    checks = []
    def test(name, value, want=False, truth=None):
        verdict = validate(value, expected if truth is None else truth)
        assert verdict['accepted'] == want, name
        if not want:
            try:
                verified_sva_request(template, value, dict(accepted=True), expected if truth is None else truth)
            except ValueError:
                pass
            else:
                raise AssertionError('failed_plan_unlocked_sva:' + name)
        checks.append(dict(name=name, passed=True, rejection_kinds=sorted({r['kind'] for r in verdict['reasons']})))
    test('oracle_fixture_ONLY_not_model', good, True)
    for i, row in enumerate(good['windows']):
        for field in ('anchor_reset', 'check_reset', 'anchor_pending'):
            for replacement in (not row[field], int(row[field]), None):
                bad = copy.deepcopy(good); bad['windows'][i][field] = replacement
                test(f"{row['id']}:wrong_or_nonboolean:{field}:{replacement!r}", bad)
        for field in ('anchor_cycle', 'check_cycle'):
            for replacement in (row[field] + 1, float(row[field]), True):
                bad = copy.deepcopy(good); bad['windows'][i][field] = replacement
                test(f"{row['id']}:wrong_or_noninteger:{field}:{replacement!r}", bad)
        for field in FIELDS:
            bad = copy.deepcopy(good); del bad['windows'][i][field]
            test(f"{row['id']}:missing:{field}", bad)
        bad = copy.deepcopy(good); bad['windows'][i]['applicability'] = 'unknown'
        test(f"{row['id']}:unknown", bad)
        bad = copy.deepcopy(good)
        bad['windows'][i]['anchor_cycle'], bad['windows'][i]['check_cycle'] = row['check_cycle'], row['anchor_cycle']
        test(f"{row['id']}:swapped_cycles", bad)
        if row['anchor_reset'] != row['check_reset']:
            bad = copy.deepcopy(good)
            bad['windows'][i]['anchor_reset'], bad['windows'][i]['check_reset'] = row['check_reset'], row['anchor_reset']
            test(f"{row['id']}:swapped_sample_resets", bad)
    for kind in ('missing_window', 'duplicate_window', 'extra_window', 'old_ambiguous_reset'):
        bad = copy.deepcopy(good)
        if kind == 'missing_window': bad['windows'].pop()
        elif kind == 'duplicate_window': bad['windows'].append(copy.deepcopy(bad['windows'][0]))
        elif kind == 'extra_window': bad['windows'][0]['id'] = 'not_a_window'
        else: bad['windows'][0]['reset'] = bad['windows'][0]['check_reset']
        test(kind, bad)
    bad_truth = copy.deepcopy(expected); bad_truth[0]['source_sha256'] = '0' * 64
    test('changed_native_source', good, truth=bad_truth)
    bad_truth = copy.deepcopy(expected); bad_truth[0]['samples'][0]['rst'] ^= 1
    test('changed_private_sample_certificate', good, truth=bad_truth)
    test('empty_expected_cannot_vacuously_pass', dict(windows=[]), truth=[])
    for bad in (None, [], dict(windows=[None]), dict(windows='not a list')):
        test('malformed_plan:' + repr(bad), bad)
    checked = validate(good, expected)
    request = verified_sva_request(template, good, checked, expected)
    assert json.loads(request['messages'][1]['content'])['verified_model_applicability_plan'] == good
    checks.append(dict(name='fixture_unlocks_payload_ONLY_not_remote_call', passed=True))
    stale = copy.deepcopy(checked); stale['stage'] = 'stale'
    try: verified_sva_request(template, good, stale, expected)
    except ValueError: checks.append(dict(name='stale_verdict_rejected', passed=True))
    else: raise AssertionError('stale_verdict_unlocked')
    return dict(passed=True, checks=checks, model_calls=0, new_native_calls=0,
                scope='Executable gate qualification on archived native development records; no model success claim.')


def archive_hashes():
    roots = (PREP46, RUN46, ROOT / 'deliverables/research46_report_20261022_r01')
    return {p.relative_to(ROOT).as_posix(): common.digest(p) for root in roots for p in common.files(root)}


def prepare(out):
    loop.prepare(out)
    before = archive_hashes()
    expected = read(PREP46 / 'expected.private.json')
    public = read(PREP46 / 'windows.public.json')
    assert len(expected) == len(public) == 11
    for name in ('expected.private.json', 'windows.public.json', 'shared_initial.json', 'sva_request.template.json'):
        shutil.copy2(PREP46 / name, out / name)
    request = read(PREP46 / 'plan_request.preview.json')
    body = json.loads(request['messages'][1]['content'])
    body['event_semantics'] = dict(field_bindings=BINDINGS,
        classification='If anchor_pending is false: not_required. Otherwise check_reset true: cancelled; check_reset false: required. Each reset field reports only its named sample, even when no obligation is pending.')
    body['response_schema'] = dict(windows=[dict(id='given id', anchor_cycle='integer', check_cycle='integer',
        anchor_reset='boolean from anchor_sample.rst only', check_reset='boolean from check_sample.rst only',
        anchor_pending='boolean from anchor_sample only', applicability=['required', 'cancelled', 'not_required', 'unknown'])])
    body['validation'] = ('Every field is independently checked against its bound native sample. '
        'The ambiguous reset and pending fields are invalid. Missing, swapped, mistyped or unknown fields reject the plan. '
        'No model value is corrected, including non-required windows. Return exactly one row per supplied window.')
    request['messages'][1]['content'] = json.dumps(body)
    # Keep seed, sampling parameters and observed windows fixed relative to46.
    dump(out / 'plan_request.preview.json', request)
    template = read(out / 'sva_request.template.json')
    qualification = qualify(expected, template)
    dump(out / 'qualification.json', qualification)
    archived = []
    for version in ('v0', 'v1'):
        path = RUN46 / 'plan' / version / 'model_call/applicability_plan.json'
        decision = validate_events(read(path), expected)
        assert decision == read(path.parent.parent / 'decision.json') and not decision['accepted']
        archived.append(dict(version=version, decision=decision, response_sha256=common.digest(path)))
    dump(out / 'research46_unchanged_rejections.json', archived)
    dump(out / 'archive_hashes.json', before)
    dump(out / 'protected.json', common.protected())
    dump(out / 'protocol.json', dict(stage='sample_bound_plan_only', max_plan_calls=2, max_sva_calls=0,
        endpoint=prior.settings(previous.SEED, 2)['remote_url'], model=request['model'],
        seed=request['seed'], temperature=request['temperature'], max_output_tokens=request['max_tokens'], retries=0,
        acceptance='All 11 windows: exact IDs, integer cycles, all three explicit sample-bound booleans, original labels, independent native certificates; no relaxation.',
        stop='Stop immediately on accepted plan or after two attempts. Failed attempt diagnostics only may enter next request.',
        data='Same development windows as46; no new independent test, full private answer table or previous successful plan/SVA in plan prompt.',
        authorization='Pending explicit transfer/new allocation for at most2 plan calls. Existing46 SVA-only remainder and45 conditional-ablation remainder cannot be used automatically.',
        downstream='Only accepted real plan permits a local SVA request artifact. No SVA call or assertion acceptance in this campaign.'))
    common.snapshot(out)
    assert before == archive_hashes()
    (out / 'SUMMARY.md').write_text(
        '# research47：采样字段绑定门控\n\n'
        f'本地正负检查 {len(qualification["checks"])}/{len(qualification["checks"])} 通过。'
        '复用11个原生开发窗口，新增 anchor_reset/check_reset/anchor_pending 明确字段；'
        '各字段逐项核验，失败或伪造的接受结果不能创建SVA请求。\n\n'
        'research46两个真实失败结果只读复核一致，全部历史产物哈希保持不变。'
        '本阶段真实模型调用尚未执行，不能宣称周期判断已通过；新增仿真/形式化为0。\n\n'
        '请求：plan_request.preview.json；本地证书：expected.private.json（不发送）；'
        '检查：qualification.json；规则：protocol.json。\n\n'
        '真实调用需先明确转用或新增最多2次周期判断额度；旧剩余额度用途不同。'
        '通过即停止，仅生成受门控的后续请求产物，不调用SVA模型。\n', encoding='utf-8')
    dump(out / 'prepared_hashes.json', {p.relative_to(out).as_posix(): common.digest(p) for p in common.files(out)
        if 'source_snapshot' not in p.parts})
    print('PREPARED', len(expected), 'windows', len(qualification['checks']), 'checks; remote_calls=0', flush=True)


def run(prep, out, authorization):
    auth, protocol = read(authorization), read(prep / 'protocol.json')
    assert auth['authorized_plan_calls'] in (1, 2) and auth['authorized_sva_calls'] == 0
    assert auth['endpoint'] == protocol['endpoint'] and auth['model'] == protocol['model']
    assert auth['run_output'] == out.relative_to(ROOT).as_posix()
    assert auth['prepared_request_sha256'] == common.digest(prep / 'plan_request.preview.json')
    assert auth['user_answer'] and auth['scope'] == 'research47_sample_bound_plan_only'
    common.check_sources(prep)
    assert read(prep / 'archive_hashes.json') == archive_hashes()
    loop.prepare(out); common.snapshot(out)
    # loop.prepare installs a legacy generic protocol; the sealed experiment
    # protocol, not that scaffolding default, describes this actual run.
    shutil.copy2(prep / 'protocol.json', out / 'protocol.json')
    shutil.copy2(authorization, out / 'authorization.json')
    dump(out / 'prepared_source.json', dict(path=str(prep)))
    expected, initial = read(prep / 'expected.private.json'), read(prep / 'shared_initial.json')
    model = previous.EventModel(out / 'plan/model', prior.settings(previous.SEED, auth['authorized_plan_calls']),
                                read(prep / 'plan_request.preview.json'))
    status, accepted = 'running', False
    try:
        for i in range(auth['authorized_plan_calls']):
            folder = out / 'plan' / f'v{i}'
            _, plan = model.call(folder / 'model_call', initial, 'stall_stability', {}, 'sample_bound_event_gate')
            verdict = validate(plan, expected); dump(folder / 'decision.json', verdict)
            print('PLAN', i, 'accepted', verdict['accepted'], 'reasons', len(verdict['reasons']), flush=True)
            if verdict['accepted']:
                dump(out / 'accepted_plan.json', plan); dump(out / 'accepted_plan_gate.json', verdict)
                request = verified_sva_request(read(prep / 'sva_request.template.json'), plan, verdict, expected)
                dump(out / 'gated_sva_request.preview.json', request)
                accepted = True; status = 'sample_bound_plan_accepted_no_sva_call'; break
            body = json.loads(model.payload['messages'][1]['content'])
            body.update(prior_actual_model_plan=plan, prior_actual_rejection=verdict['reasons'])
            model.payload['messages'][1]['content'] = json.dumps(body)
        if not accepted: status = 'sample_bound_plan_rejected_no_sva'
    except BaseException:
        status = 'execution_exception'; raise
    finally:
        dump(out / 'outcome.json', dict(status=status, plan_accepted=accepted, model_calls=len(model.calls),
            sva_calls=0, new_native_calls=0, formal_calls=0, initial_hash=loop.sha(initial),
            research46_unchanged=read(prep / 'archive_hashes.json') == archive_hashes()))
        dump(out / 'cost.json', cost_audit(out, common.files(out)))
        print('TERMINAL', status, flush=True)


def audit(run_dir, out):
    loop.prepare(out)
    prep = gate.portable(read(run_dir / 'prepared_source.json')['path'])
    expected = read(prep / 'expected.private.json')
    checks, attempts = [], []
    def check(name, passed):
        checks.append(dict(name=name, passed=bool(passed)))
    for name, digest in read(prep / 'prepared_hashes.json').items():
        check('prepared:' + name, common.digest(prep / name) == digest)
    request = read(prep / 'plan_request.preview.json'); accepted = None
    for version in sorted((run_dir / 'plan').glob('v*')):
        folder = version / 'model_call'
        check(version.name + ':no_call_after_accept', accepted is None)
        check(version.name + ':request', read(folder / 'request.json') == request)
        plan = read(folder / 'applicability_plan.json') if (folder / 'applicability_plan.json').exists() else None
        if plan is not None: check(version.name + ':raw_model_plan', raw_response(folder, plan))
        verdict = validate(plan, expected)
        check(version.name + ':decision', verdict == read(version / 'decision.json'))
        attempts.append(dict(version=version.name, accepted=verdict['accepted'], reasons=verdict['reasons']))
        if verdict['accepted']: accepted = plan
        body = json.loads(request['messages'][1]['content'])
        body.update(prior_actual_model_plan=plan, prior_actual_rejection=verdict['reasons'])
        request['messages'][1]['content'] = json.dumps(body)
    outcome = read(run_dir / 'outcome.json')
    auth = read(run_dir / 'authorization.json')
    check('call_budget', 1 <= len(attempts) <= auth['authorized_plan_calls'] <= 2)
    check('status', outcome['plan_accepted'] == (accepted is not None))
    if accepted is not None:
        verdict = validate(accepted, expected)
        check('saved_actual_plan', read(run_dir / 'accepted_plan.json') == accepted)
        check('guarded_sva_request', read(run_dir / 'gated_sva_request.preview.json') ==
              verified_sva_request(read(prep / 'sva_request.template.json'), accepted, verdict, expected))
    else: check('no_sva_request_on_failure', not (run_dir / 'gated_sva_request.preview.json').exists())
    check('research46_unchanged', read(prep / 'archive_hashes.json') == archive_hashes())
    check('no_sva_native_or_independent_run', not any((run_dir / n).exists() for n in ('sva', 'core', 'independent')))
    check('cost_recomputed', read(run_dir / 'cost.json') == cost_audit(run_dir, common.files(run_dir)))
    dump(out / 'audit.json', dict(passed=all(c['passed'] for c in checks), checks=checks, attempts=attempts, outcome=outcome))
    (out / 'SUMMARY.md').write_text('# research47 actual result\n\n' + json.dumps(outcome, ensure_ascii=False, indent=2) +
        '\n\nPlan-only development gate. No new SVA, native replay or independent acceptance claimed.\n', encoding='utf-8')
    assert all(c['passed'] for c in checks), 'audit_failed'
    print('AUDITED', len(checks), 'checks', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'run', 'audit'))
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--prepared', type=Path)
    parser.add_argument('--authorization', type=Path)
    parser.add_argument('--run', type=Path)
    args = parser.parse_args(); destination = args.out.resolve()
    assert ROOT in destination.parents
    if args.action == 'prepare': prepare(destination)
    elif args.action == 'run': run(args.prepared.resolve(), destination, args.authorization.resolve())
    else: audit(args.run.resolve(), destination)
