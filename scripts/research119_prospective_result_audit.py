"""Read-only audit of the sealed research116 three-rule prospective pilot."""
import argparse
import copy
import json
from pathlib import Path
from unittest.mock import patch
import research116_prospective_deepseek as s
from research93_remote_recovery_audit import response
from research88_cross_parent_audit import inspect_version

ROOT, read, dump, sha, x = s.ROOT, s.read, s.dump, s.sha, s.x


def run(prep, trial, out):
    s.verify(prep); s.grant_check(read(trial / 'authorization.json'), prep, trial)
    checks = []
    def check(name, value):
        assert value, name
        checks.append(name)
    initial = read(prep / 'initial.json'); baseline = read(prep / 'baseline_full.json')
    n, _, base_records = inspect_version(prep / 'baseline_native', initial, baseline)
    qualification_rows = n; development_rows = 0; independent_rows = 0
    ledger = read(trial / 'budget_ledger.json'); check('bounded_dispatches', 1 <= len(ledger) <= 4)
    measured = {}; calls = []; versions = []; first_candidate = first_ev = first_records = None
    first_reason = None
    for i, item in enumerate(ledger):
        folder = trial / item['path']; mf = folder / 'model_call'
        current = initial if i == 0 else first_candidate or initial
        records = base_records if i == 0 else first_records or base_records
        native_folder = trial / 'shared/v0/native' if i > 0 and first_records else prep / 'baseline_native'
        diagnostic = None
        if i == 0:
            check('shared_first', item['path'] == 'shared/v0')
            history = False; iteration = 0
        else:
            arm = folder.parent.name
            check(f'{i}_only_rejected_arm_continues', arm in s.ARMS and not measured['shared/v0']['decisions'][arm])
            check(f'{i}_one_continuation_per_arm', item['path'] == f'arms/{arm}/v1' and item['path'] not in measured)
            history = arm != 'O'; iteration = 1
            if first_ev is None:
                diagnostic = dict(reason=first_reason, actual_model_text=read(trial / 'shared/v0/model_call/response.assembled.json')['message']['content'])
        req = read(mf / 'request.json'); call = read(mf / 'result.json'); calls.append(call)
        check(f'{i}_exact_own_allowed_request', req == s.payload(current, records, native_folder, history, iteration, diagnostic))
        check(f'{i}_request_hash', item['request_sha256'] == x.old.acceptance.sha(req))
        check(f'{i}_model_no_retry', req['model'] == call['model'] == s.MODEL and call['retries'] == 0)
        check(f'{i}_reservation', item['reservation'] == call['token_budget_reservation'] == sum(len(m['content'].encode()) for m in req['messages']) + 2048 + req['max_tokens'] <= 40000)
        if i == 0: check('first_request_sealed', req == read(prep / 'request.preview.json'))
        text, raw = response(mf); candidate = ev = newrecords = None
        reason = dict(kind='transport_or_interface', actual=call)
        if (mf / 'candidate.json').exists():
            edit = read(mf / 'model_edit.json')
            check(f'{i}_raw_response_to_edit', raw['complete'] and json.loads(text) == edit)
            candidate, mapping = s.old.prior.p.TEXT_ADAPT(edit, initial)
            check(f'{i}_candidate_not_manually_repaired', candidate == read(mf / 'candidate.json'))
            check(f'{i}_mapping_exact', mapping == read(mf / 'label_mapping.json'))
            check(f'{i}_fixed_branch', candidate['assertions'][0] == initial['assertions'][0])
            check(f'{i}_sva_exact', (mf / 'candidate.sva').read_text().strip() == '\n'.join(a['property'] for a in candidate['assertions']))
            if x.signature(candidate) in {x.signature(initial), x.signature(current)}:
                reason = dict(kind='repeated_executable_proposal'); candidate = None
                check(f'{i}_repeat_skips_compile', not (folder / 'native').exists())
            else:
                rows, ev, newrecords = inspect_version(folder / 'native', candidate, baseline)
                development_rows += rows; reason = dict(kind='native_measured')
        decision = s.old.decisions(ev) if ev else {a: False for a in s.ARMS}
        check(f'{i}_three_decisions_recomputed', read(folder / 'measurement.json') == dict(decisions=decision, reason=reason))
        measured[item['path']] = dict(candidate=candidate, decisions=decision, ev=ev)
        if i == 0:
            first_candidate, first_ev, first_records, first_reason = candidate, ev, newrecords, copy.deepcopy(reason)
        if call['status'] != 'response_received': check(f'{i}_transport_stops', i == len(ledger) - 1)
        versions.append(dict(path=item['path'], response=raw, model_edit=read(mf / 'model_edit.json') if (mf / 'model_edit.json').exists() else None,
            decisions=decision, reason=reason, counts=ev['counts'] if ev else None,
            focus12=ev['current_gate']['focus12'] if ev else None,
            new_false_alarms=len(ev['new_false_alarm_ids']) if ev else None,
            lost_detections=len(ev['lost_detection_ids']) if ev else None,
            retained_detections=len(ev['retained_detection_ids']) if ev else None,
            actual_server_model=call.get('actual_server_model')))
    first = measured['shared/v0']['decisions']; states = read(trial / 'states.json'); active = {}
    for arm in s.ARMS:
        previous = initial; chain = [(trial / 'arms' / arm / 'v0', measured['shared/v0'])]
        key = f'arms/{arm}/v1'
        if key in measured: chain.append((trial / key / 'transition', measured[key]))
        for index, (folder, item) in enumerate(chain):
            tr = read(folder / 'transition.json'); accepted = item['decisions'][arm]
            check(f'{arm}{index}_decision_and_prior', tr['accepted'] == accepted and read(folder / 'before.json') == previous
                  and tr['previous_sha256'] == x.old.acceptance.sha(previous))
            check(f'{arm}{index}_proposal', tr['proposal_sha256'] == (x.old.acceptance.sha(item['candidate']) if item['candidate'] else None))
            previous = item['candidate'] if accepted else previous
            check(f'{arm}{index}_active_and_rollback', read(folder / 'active.json') == previous and tr['active_sha256'] == x.old.acceptance.sha(previous) and tr['rollback_verified'])
        active[arm] = previous
        check(arm + '_state', states[arm] == dict(accepted=chain[-1][1]['decisions'][arm], logical_calls=len(chain), initial_extra_rejection=bool(first['O'] and not first[arm])))
        check(arm + '_terminal', read(trial / 'terminal' / arm / 'candidate.json') == previous)
    hashes = {a: x.old.acceptance.sha(c) for a, c in active.items()}
    check('terminal_hashes', hashes == read(trial / 'terminal_versions.json'))
    # Post-run hash comparison only: never parse the old successful predicate.
    # A fresh model response may reproduce an existing structure; do not count
    # such reproducibility as a new globally distinct accepted assertion set.
    archived_hash = read(prep / 'protected_records.json')['deliverables/research113_real_20261025_r01/frozen/alternative/candidate.json']
    matches_archived = {a: sha(trial / 'terminal' / a / 'candidate.json') == archived_hash for a in s.ARMS}
    outcome = read(trial / 'outcome.json'); cost = read(trial / 'cost.json')['total']
    stopped = any(c['status'] != 'response_received' for c in calls)
    unique = len({hashes[a] for a in s.ARMS if states[a]['accepted']})
    check('outcome_exact', outcome == dict(actual_model_calls=len(calls), reserved_attempts=len(ledger),
        accepted_arms=sum(st['accepted'] for st in states.values()), unique_accepted_versions=unique,
        transport_stopped=stopped, independent_executed=(trial / 'independent_summary.json').exists(), completed=True, automatic_expansion=False))
    check('cost_recomputed', read(trial / 'cost.json') == x.costs.native_cost(trial))
    check('model_budget', cost['model_calls'] == len(calls) <= 4 and sum(e['reservation'] for e in ledger) <= 160000)
    check('native_budget', cost['native_compile_calls'] <= 30 and cost['native_execute_calls'] <= 30 and cost['formal_calls'] == 0)
    for key in ('prompt_tokens', 'completion_tokens'):
        if all(c.get(key) is not None for c in calls): check(key + '_sum', cost[key + '_total'] == sum(c[key] for c in calls))
    tests = None
    if (trial / 'independent_summary.json').exists():
        check('independent_after_accepted_terminal', not stopped and outcome['accepted_arms'] > 0)
        tests = read(trial / 'independent_summary.json'); freeze = read(trial / 'freeze.json')
        generation = read(trial / 'generation.json'); cases = read(trial / 'independent_cases.json')
        check('all_versions_frozen_before_new_cases', freeze['versions'] == hashes and generation['at'] > freeze['time'] and generation['freeze_sha256'] == sha(trial / 'freeze.json'))
        check('freeze_inputs', freeze['source_sha256'] == read(prep / 'source_binding.json')['source_sha256'] and freeze['development_exclusion_sha256'] == sha(prep / 'excluded_words.json'))
        check('new_cases_reproducible', cases == x.holdout.base.generate(generation['seed'], read(prep / 'excluded_words.json')))
        words = {t['instruction'] for t in cases}
        check('96_unique_nonoverlapping_instructions', len(words) == 96 and not words & set(read(prep / 'excluded_words.json')))
        for arm, candidate in active.items():
            folder = trial / 'frozen' / arm; result = read(folder / 'independent/result.json')
            check(arm + '_frozen_candidate_and_cases', read(folder / 'candidate.json') == candidate and read(folder / 'independent_cases.json') == cases)
            for rev in ('before', 'after'):
                for src in (prep / rev).glob('*.sv'): check(arm + rev + src.name + '_rtl_hash', sha(src) == sha(folder / rev / src.name))
            if result['healthy']:
                independent_rows += x.holdout.base.native_audit(folder, result)['rows_audited']
                with patch.object(x.old, 'CONFIGS', x.holdout.base.CONFIGS): guard = x.all_guard(folder / 'independent', result, candidate)
                expected = x.holdout.summarize(result, guard)
            else: expected = dict(passed=False, counts=result['counts'], status='native_failure')
            check(arm + '_independent_recomputed', tests[arm] == expected)
    else: check('no_unreported_holdout', not (trial / 'freeze.json').exists())
    ready = bool(not stopped and tests and any(states[a]['initial_extra_rejection'] and states[a]['accepted'] and tests[a]['passed'] for a in ('H', 'R')))
    pd = read(trial / 'pilot_decision.json')
    check('presealed_expansion_gate', pd == dict(eligible_to_request_multiseed=ready, automatic_expansion=False,
        first_shared_decisions=first, states=states, independent={a: t['passed'] for a, t in tests.items()} if tests else None,
        status='qualified_for_separately_authorized_replication' if ready else 'stop_no_qualified_chain'))
    extra = bool(first['O'] and (not first['H'] or not first['R']))
    increment = dict(ordinary_accepted_shared_proposals=int(first['O']), shared_fresh_proposals=1,
        historical_extra_rejection=int(extra), relative_rule_exclusive_rejection=int(first['O'] and first['H'] and not first['R']),
        bounded_recovery_eligible_arms=sum(states[a]['initial_extra_rejection'] for a in ('H', 'R')),
        qualified_rejection_recovery_chain=ready,
        interpretation='No extra rejection means recovery effect is not estimable; accepted arms/identical replays do not multiply independent proposals. Not a test of contract-search benefit.')
    s.verify(prep); check('research113_and_older_records_unchanged', s.protected() == read(prep / 'protected_records.json'))
    audit = dict(passed=True, count=len(checks), checks=checks, qualification_rows_reaudited=qualification_rows,
        new_development_rows_reaudited=development_rows, new_independent_rows_reaudited=independent_rows,
        actual_model_calls=len(calls), unique_new_accepted_versions=unique, increment=increment,
        terminal_file_matches_archived113=matches_archived,
        raw_predicates_verified=True, requests_and_information_isolation_verified=True,
        freeze_before_generation_verified=tests is not None, automatic_expansion=False, script_sha256=sha(Path(__file__)))
    out.mkdir(parents=True, exist_ok=False)
    for name, obj in [('audit', audit), ('versions', versions), ('cost', cost), ('mechanism_increment', increment), ('independent_summary', tests)]: dump(out / (name + '.json'), obj)
    lines = ['# research116 / 119：前瞻性三规则先导实际结果', '',
        f'实际DeepSeek调用 **{len(calls)}/4**；新接受的不同版本 **{unique}**；接受组 **{outcome["accepted_arms"]}/3**。',
        f'共享提案接受决定：普通O={first["O"]}，同历史绝对H={first["H"]}，防退化R={first["R"]}。', '',
        '运行终止后仅比较文件哈希，与research113归档集合相同的组：' + ', '.join(a for a in s.ARMS if matches_archived[a]) + '。这是新真实调用得到的集合；若哈希相同，则是旧结构的再次生成，不计全局新断言结构。该比较未用于提示、候选选择或门控。', '',
        '|实际提案|O|H|R|151事务检出|新增合法误报|丢失旧检出|', '|---|---|---|---|---:|---:|---:|']
    for v in versions:
        count = sum(v['counts'][c]['detections'] for c in ('history', 'search')) if v['counts'] else '未执行'
        lines.append(f'|{v["path"]}|{v["decisions"]["O"]}|{v["decisions"]["H"]}|{v["decisions"]["R"]}|{count}|{v["new_false_alarms"]}|{v["lost_detections"]}|')
    lines += ['', f'普通接受分母={int(first["O"])}/1份新共享提案；历史额外拒绝={int(extra)}，相对规则独有拒绝={increment["relative_rule_exclusive_rejection"]}；进入拒绝后恢复的历史组={increment["bounded_recovery_eligible_arms"]}。',
        '若没有额外拒绝，就没有可估计的拒绝后恢复效果；不能把直接生成成功记作门控的额外恢复，也不能把0个恢复机会报告为0%恢复成功率。', '',
        '|冻结组|独立通过|目标检出|漏报|误报|unknown|必要未触发|', '|---|---|---:|---:|---:|---:|---:|']
    if tests:
        for arm, t in tests.items():
            c = t['counts']; lines.append(f'|{arm}|{t["passed"]}|{c["detections"]}|{c["misses"]}|{c["false_positives"]}|{c["unknown"]}|{t.get("required_untriggered")}|')
        lines += ['', '全部终态冻结后才生成96个新指令，四配置；排除已用输入包括research113指令字。各组用同一批测试，相同断言不是多个独立新版本，相同测试不是多个独立总体。']
    else: lines += ['|未启动|||||||']
    lines += ['', f'符合预先定义的“普通接受→历史额外拒绝→同组预算内恢复→新独立通过”链：**{ready}**。' + ('只具备另行申请复现的资格，不自动扩种子。' if ready else '按协议停止，不扩种子，不追加同模型调用寻找区分结果。'), '',
        f'成本：模型{cost["model_calls"]}次，输入/输出tokens **{cost["prompt_tokens_total"]}/{cost["completion_tokens_total"]}**，原生编译/实验执行 **{cost["native_compile_calls"]}/{cost["native_execute_calls"]}**，另编译冒烟{cost["compile_smoke_execute_calls"]}次，形式化0。准备阶段18次原生编译/执行另计；服务金额不可用。', '',
        f'{len(checks)}项只读审计通过；复核资格{qualification_rows}、新开发{development_rows}、新独立{independent_rows}条原生记录。原始响应到性质逐字核验；没有复制research113成功性质，旧独立结果保持不变。', '',
        '边界：这是已知Ibex #166 decoder任务的新提案先导，不能估计跨案例成功率。BRANCH组件固定，此配置不检验模型删除BRANCH的退化；额外历史误报仍由三规则测量。H与R可能等价，共同拒绝不等于相对规则独有价值。有限仿真不是整核验证或形式化证明。',
        '本先导不测契约搜索收益；research117仍只是封存准备，本轮未执行其108查询。既有零独有缺口结果不能被本轮生成结果改写。', '',
        '复核（不调用模型）：', '```powershell',
        f'wsl -- python3 scripts/research119_prospective_result_audit.py --prepared {prep.relative_to(ROOT).as_posix()} --run {trial.relative_to(ROOT).as_posix()} --out deliverables/research119_audit_NEW', '```']
    (out / 'SUMMARY.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    trace = ['# 真实提案与配对决定', '', '共同初始部分BRANCH集合：', '```systemverilog'] + [a['property'] for a in initial['assertions']] + ['```', '']
    for v in versions:
        trace += ['## ' + v['path'], '```json', json.dumps(v['model_edit'], ensure_ascii=False, indent=2), '```',
            '实际接受决定：' + json.dumps(v['decisions']) + '；不是由模型解释文字判定。', '']
    (out / 'CASE_TRACE.md').write_text('\n'.join(trace) + '\n', encoding='utf-8')
    paths = [prep / 'sealed.json', trial / 'authorization.json', trial / 'outcome.json', trial / 'cost.json', trial / 'pilot_decision.json']
    if tests: paths += [trial / n for n in ('freeze.json', 'generation.json', 'independent_cases.json', 'independent_summary.json')]
    dump(out / 'bindings.json', {f.relative_to(ROOT).as_posix(): sha(f) for f in paths})
    print('AUDIT119', {k: v for k, v in audit.items() if k != 'checks'}, flush=True)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    for n in ('prepared', 'run', 'out'): ap.add_argument('--' + n, type=Path, required=True)
    a = ap.parse_args(); run(a.prepared.resolve(), a.run.resolve(), a.out.resolve())
