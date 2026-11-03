"""Read-only raw-response/native audit of the research123 bounded pilot."""
import argparse
import json
from pathlib import Path
from unittest.mock import patch
import research126_scoped_history_runner as runner
from research88_cross_parent_audit import inspect_version
from research93_remote_recovery_audit import response

p, s, x = runner.p, runner.s, runner.x
ROOT, read, dump, sha = runner.ROOT, runner.read, runner.dump, runner.sha


def audit(prep, trial, out):
    p.verify(prep); s.verify(p.PREP)
    runner.grant_check(read(trial / 'authorization.json'), prep, trial)
    checks = []
    def check(name, condition):
        assert condition, name
        checks.append(name)
    initial = read(prep / 'initial.json'); baseline = read(p.PREP / 'baseline_full.json')
    base_rows, _, base_records = inspect_version(p.PREP / 'baseline_native', initial, baseline)
    entries = read(trial / 'budget_ledger.json'); budget = p.Budget()
    check('one_or_two_calls', 1 <= len(entries) <= 2)
    first = None; first_status = None; current = initial; records = base_records
    folder = p.PREP / 'baseline_native'; measured = []; dev_rows = 0; test_rows = 0
    active = dict(O=initial, H=initial)
    for i, entry in enumerate(entries):
        expected_path = 'shared/v0' if i == 0 else 'history/v1'
        check('trajectory/' + str(i), entry['path'] == expected_path)
        loc = trial / expected_path; mf = loc / 'model_call'
        req = read(mf / 'request.json'); call = read(mf / 'result.json')
        with patch.object(s, 'SEED', p.SEED): expected = s.payload(current, records, folder, i == 1, i)
        check('allowed_feedback/' + str(i), req == expected)
        if i == 0: check('sealed_first_request', req == read(prep / 'request.preview.json'))
        budget.reserve(expected_path, req, first, first_status)
        check('exact_reservation/' + str(i), budget.entries[-1] == entry)
        check('real_model_no_retries/' + str(i), call['model'] == req['model'] == s.MODEL and call['retries'] == 0)
        candidate = ev = recs = None
        if (mf / 'candidate.json').exists():
            text, raw = response(mf); edit = read(mf / 'model_edit.json')
            check('raw_response/' + str(i), raw['complete'] and json.loads(text) == edit)
            candidate, mapping = s.old.prior.p.TEXT_ADAPT(edit, initial)
            check('unaltered_model_predicates/' + str(i), candidate == read(mf / 'candidate.json'))
            check('fixed_branch/' + str(i), candidate['assertions'][0] == initial['assertions'][0])
            check('label_mapping/' + str(i), mapping == read(mf / 'label_mapping.json'))
            check('executable_sva/' + str(i), (mf / 'candidate.sva').read_text().strip() == '\n'.join(a['property'] for a in candidate['assertions']))
            if x.signature(candidate) in {x.signature(initial), x.signature(current)}:
                candidate = None; check('repeat_skips_native/' + str(i), not (loc / 'native').exists())
            else:
                n, ev, recs = inspect_version(loc / 'native', candidate, baseline); dev_rows += n
        d = s.old.decisions(ev) if ev else dict(O=False,H=False,R=False)
        check('native_decisions/' + str(i), read(loc / 'measurement.json')['decisions'] == d)
        if i == 0:
            first, first_status = d, call['status']
            action = runner.next_action(d, first_status, recs)
            check('recorded_stopping', read(trial / 'first_decision.json')['next_action'] == action)
            check('only_qualified_history_continues', len(entries) == (2 if action == 'history_once' else 1))
        arms = ('O','H') if i == 0 else ('H',)
        for arm in arms:
            loc_arm = trial / 'arms' / arm / ('v0' if i == 0 else 'v1')
            tr = read(loc_arm / 'transition.json')
            accepted = d[arm] if i == 0 else d['H'] and d['R'] and runner.healthy(recs)
            check(f'{arm}{i}/old_active', read(loc_arm / 'before.json') == active[arm])
            check(f'{arm}{i}/acceptance', tr['accepted'] == accepted)
            if accepted: active[arm] = candidate
            check(f'{arm}{i}/rollback', read(loc_arm / 'active.json') == active[arm] and tr['rollback_verified'])
        measured.append(dict(path=expected_path, decisions=d, counts=ev['counts'] if ev else None,
            new_false_alarms=len(ev['new_false_alarm_ids']) if ev else None,
            lost_detections=len(ev['lost_detection_ids']) if ev else None,
            retained_detections=len(ev['retained_detection_ids']) if ev else None,
            call_status=call['status'], model_edit=read(mf / 'model_edit.json') if (mf / 'model_edit.json').exists() else None))
        current, records, folder = candidate, recs, loc / 'native'
    freeze = read(trial / 'terminal_freeze.json')
    hashes = {a:x.old.acceptance.sha(c) for a,c in active.items()}
    check('terminal_hashes', freeze['versions'] == hashes)
    for a,c in active.items():
        check(a + '_frozen_file', read(trial / 'terminal' / a / 'candidate.json') == c
              and sha(trial / 'terminal' / a / 'candidate.json') == freeze['candidate_files'][a])
    tests = None
    if (trial / 'independent_summary.json').exists():
        tests = read(trial / 'independent_summary.json'); gen = read(trial / 'generation.json')
        tfreeze = read(trial / 'freeze.json'); inputs = trial / 'independent_inputs'
        cases = read(trial / 'independent_cases.json'); excluded = read(inputs / 'excluded_words.json')
        check('both_physical_arms_only', set(tests) == {'O','H'})
        check('freeze_before_test_generation', gen['at'] > tfreeze['time'] >= freeze['time'] and tfreeze['versions'] == hashes)
        check('test_freeze_binding', gen['freeze_sha256'] == sha(trial / 'freeze.json'))
        check('new_96_inputs', len({t['instruction'] for t in cases}) == 96 and not {t['instruction'] for t in cases}.intersection(excluded))
        check('reproducible_test_generation', cases == x.holdout.base.generate(gen['seed'], excluded))
        check('exclusion_binding', tfreeze['development_exclusion_sha256'] == sha(inputs / 'excluded_words.json'))
        for a,c in active.items():
            loc = trial / 'frozen' / a; result = read(loc / 'independent/result.json')
            check(a + '_heldout_candidate', read(loc / 'candidate.json') == c)
            check(a + '_same_test_inputs', read(loc / 'independent_cases.json') == cases)
            for rev in ('before','after'):
                for src in (p.PREP / rev).glob('*.sv'): check(a + rev + src.name, sha(src) == sha(loc / rev / src.name))
            if result['healthy']:
                test_rows += x.holdout.base.native_audit(loc, result)['rows_audited']
                with patch.object(x.old, 'CONFIGS', x.holdout.base.CONFIGS): guard = x.all_guard(loc / 'independent', result, c)
                expected = x.holdout.summarize(result, guard)
            else: expected = dict(passed=False, counts=result['counts'], status='native_failure')
            check(a + '_holdout_recomputed', tests[a] == expected)
    cost = x.costs.native_cost(trial)
    check('cost_recomputed', cost == read(trial / 'cost.json'))
    check('model_cost_cap', cost['total']['model_calls'] == len(entries) <= 2)
    check('native_cost_cap', all(cost['total'][k] <= 16 for k in ('native_compile_calls','native_execute_calls','compile_smoke_execute_calls')))
    check('completed', read(trial / 'outcome.json')['completed'])
    extra = first['O'] and not first['H'] and not first['R']
    ready = bool(extra and len(measured) == 2 and measured[1]['decisions']['H'] and tests and tests['H']['passed'])
    check('expansion_not_automatic', read(trial / 'pilot_decision.json')['qualified_incremental_recovery_chain'] == ready
          and not read(trial / 'pilot_decision.json')['automatic_expansion'])
    s.verify(p.PREP); p.verify(prep)
    check('old_protected_records_unchanged', s.protected() == read(p.PREP / 'protected_records.json'))
    out.mkdir(parents=True, exist_ok=False)
    result = dict(passed=True, checks=checks, check_count=len(checks), qualification_rows_reaudited=base_rows,
        development_rows_reaudited=dev_rows, independent_rows_reaudited=test_rows,
        fresh_shared_proposals=1, ordinary_accepted=int(first['O']), historical_extra_rejections=int(extra),
        recovery_opportunities=int(extra), qualified_incremental_recovery_chain=ready,
        R_unique_effect='not_identifiable_same_history_rules_equivalent', automatic_expansion=False)
    dump(out / 'audit.json', result); dump(out / 'versions.json', measured)
    dump(out / 'cost.json', cost); dump(out / 'independent_summary.json', tests)
    c = cost['total']; outcome = read(trial / 'outcome.json')
    lines = ['# research123 受限前瞻先导实际结果', '',
        f'真实模型调用 {len(entries)}/2；本轮新调用接受的不同集合 {outcome["new_unique_accepted_versions"]}；完整151事务回放 {len([v for v in measured if v["counts"]])} 次。',
        f'首轮配对决定：O={first["O"]}，H={first["H"]}，R={first["R"]}。',
        f'历史额外拒绝 {int(extra)}/{int(first["O"])} 个普通接受提案；恢复机会 {int(extra)}；完整增量恢复链={ready}。',
        '若没有区分提案，按封存协议首轮即停；未追加调用或种子。没有恢复机会时，成功率不可估计，不能写成0%恢复成功率。R是H影子，不是第三个独立组；不能证明R胜过同历史绝对检查。', '',
        '|提案|OP+BRANCH检出（有限151事务）|新增误报|丢失检出|', '|---|---:|---:|---:|']
    for v in measured:
        detected = sum(v['counts'][k]['detections'] for k in ('history','search')) if v['counts'] else None
        lines.append(f'|{v["path"]}|{detected}|{v["new_false_alarms"]}|{v["lost_detections"]}|')
    lines += ['', '|冻结组|独立通过|检出|漏报|误报|关键unknown|必要未触发|', '|---|---|---:|---:|---:|---:|---:|']
    if tests:
        for a,t in tests.items():
            cc=t['counts']; lines.append(f'|{a}|{t["passed"]}|{cc["detections"]}|{cc["misses"]}|{cc["false_positives"]}|{cc["unknown"]}|{t.get("required_untriggered")}|')
    lines += ['', '全部终态冻结后生成共同96个新指令、四配置；相同集合和共同测试不增加独立模型样本数。结论仅限原始Ibex #166 decoder模块及有限证据，不是整核或形式化证明。',
        f'原生编译/实验执行 {c["native_compile_calls"]}/{c["native_execute_calls"]}；编译冒烟另{c["compile_smoke_execute_calls"]}次；输入/输出tokens {c["prompt_tokens_total"]}/{c["completion_tokens_total"]}；缺失用量调用{c["usage_unavailable_calls"]}；形式化0。',
        f'只读审计{len(checks)}项通过；复核资格{base_rows}、开发{dev_rows}、独立{test_rows}条原生记录。模型原始响应、原样性质、接受决定与回滚均核验。', '',
        '本轮不测搜索收益；research124/125的无独有缺口结果保持不变。', '',
        '只读复核：', '```powershell',
        f'wsl -- python3 scripts/research128_scoped_result_audit.py --prepared {prep.relative_to(ROOT).as_posix()} --run {trial.relative_to(ROOT).as_posix()} --out deliverables/research128_audit_NEW', '```']
    (out / 'SUMMARY.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    trace = ['# 实际模型提案与轨迹', '', '初始集合：', '```systemverilog'] + [a['property'] for a in initial['assertions']] + ['```']
    for v in measured:
        trace += ['', v['path'], '```json', json.dumps(v['model_edit'], indent=2, ensure_ascii=False), '```',
                  '实测决定：' + json.dumps(v['decisions'])]
    (out / 'CASE_TRACE.md').write_text('\n'.join(trace)+'\n', encoding='utf-8')
    dump(out / 'bindings.json', {str(f.relative_to(ROOT)):sha(f) for f in [prep / 'sealed.json', trial / 'outcome.json',
         trial / 'budget_ledger.json', trial / 'terminal_freeze.json', trial / 'pilot_decision.json', trial / 'cost.json']})
    print('AUDIT128', {k:v for k,v in result.items() if k != 'checks'}, flush=True)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ('prepared','run','out'): ap.add_argument('--'+name, type=Path, required=True)
    a = ap.parse_args(); audit(a.prepared.resolve(), a.run.resolve(), a.out.resolve())
