"""Read-only audit: raw alternative-model response, native gates and fresh holdout."""
import argparse
import json
from pathlib import Path
from unittest.mock import patch
import research113_alternative_model_pilot as s
from research93_remote_recovery_audit import response
from research88_cross_parent_audit import inspect_version

ROOT, read, dump, sha = s.ROOT, s.read, s.dump, s.sha
x, p = s.x, s.p


def run(prep, trial, out):
    s.verify(prep); s.grant_check(read(trial / 'authorization.json'), prep, trial)
    checks = []

    def check(name, value):
        assert value, name
        checks.append(name)

    initial = read(prep / 'initial.json'); current = read(prep / 'proposal.json')
    original = current; active = initial; baseline = read(prep / 'baseline_full.json')
    rows, ev, records = inspect_version(s.r.VERSION / 'native', current, baseline)
    old_rows = rows; new_rows = 0
    check('old_candidate_still_rejected', not ev['history']['accepted'])
    check('old_690_detected_104_false_alarms', sum(records[c]['counts']['detections'] for c in ('history', 'search')) == 690
          and sum(records[c]['counts']['false_positives'] for c in ('history', 'search')) == 104)
    native_folder = s.r.VERSION / 'native'; diagnostic = None
    seen = {x.signature(initial), x.signature(current)}; versions = []; calls = []
    ledger = read(trial / 'budget_ledger.json'); accepted = False; stopped = False
    check('bounded_dispatches', 1 <= len(ledger) <= 2)
    for i, entry in enumerate(ledger):
        folder = trial / f'v{i}'; mf = folder / 'model_call'
        req = read(mf / 'request.json'); call = read(mf / 'result.json'); calls.append(call)
        check(f'v{i}_exact_own_request', req == s.request(current, records, native_folder, i, diagnostic))
        if i == 0:
            check('first_request_sealed', req == read(prep / 'request.preview.json'))
        check(f'v{i}_request_hash', entry['request_sha256'] == x.old.acceptance.sha(req))
        reservation = sum(len(m['content'].encode()) for m in req['messages']) + 2048 + req['max_tokens']
        check(f'v{i}_reserved_cost', reservation == entry['reservation'] == call['token_budget_reservation'] <= 40000)
        check(f'v{i}_model_and_no_retry', req['model'] == call['model'] == s.MODEL and call['retries'] == 0)
        text, raw = response(mf)
        check(f'v{i}_transport_status', raw['status'] == call['status'])
        candidate = None; evaluated = None; reason = dict(kind='transport_or_interface', actual=call)
        if (mf / 'candidate.json').exists():
            value = read(mf / 'model_edit.json')
            check(f'v{i}_actual_raw_model_edit', raw['complete'] and json.loads(text) == value)
            candidate, mapping = p.prior.p.TEXT_ADAPT(value, initial)
            check(f'v{i}_no_local_predicate_rewrite', candidate == read(mf / 'candidate.json'))
            check(f'v{i}_branch_immutable', candidate['assertions'][0] == initial['assertions'][0])
            check(f'v{i}_sva_exact', (mf / 'candidate.sva').read_text().strip() == '\n'.join(a['property'] for a in candidate['assertions']))
            check(f'v{i}_mapping_exact', mapping == read(mf / 'label_mapping.json'))
            if x.signature(candidate) in seen:
                reason = dict(kind='repeated_executable_proposal'); candidate = None
                check(f'v{i}_repeat_no_native', not (folder / 'native').exists())
            else:
                seen.add(x.signature(candidate))
                n, evaluated, newrecords = inspect_version(folder / 'native', candidate, baseline)
                new_rows += n
                accepted = bool(evaluated['history']['accepted'])
                reason = dict(kind='native_measured', decision=evaluated)
                current, records, native_folder = candidate, newrecords, folder / 'native'
                if accepted:
                    check(f'v{i}_full_690_targets', sum(records[c]['counts']['detections'] for c in ('history', 'search')) == 690)
                    check(f'v{i}_no_fp_miss_unknown', all(records[c]['counts'][k] == 0 for c in records for k in ('false_positives', 'misses', 'unknown')))
                    check(f'v{i}_required_trigger_and_absolute', evaluated['required_untriggered'] == 0 and evaluated['full_absolute'])
        transition = read(folder / 'transition/transition.json')
        check(f'v{i}_decision_recomputed', transition['accepted'] == accepted and transition['reason'] == reason)
        check(f'v{i}_prior_version_hash', transition['previous_sha256'] == x.old.acceptance.sha(active))
        check(f'v{i}_prior_file', read(folder / 'transition/before.json') == active)
        active = candidate if accepted else active
        check(f'v{i}_active_correct', read(folder / 'transition/active.json') == active and transition['active_sha256'] == x.old.acceptance.sha(active))
        diagnostic = None if evaluated else dict(reason=reason, actual_model_text=text)
        stopped = call['status'] != 'response_received'
        if accepted or stopped:
            check(f'v{i}_immediate_stop', i == len(ledger) - 1)
        versions.append(dict(iteration=i, model_edit=read(mf / 'model_edit.json') if (mf / 'model_edit.json').exists() else None,
             response=raw, native_checked=evaluated is not None, accepted=accepted,
             decision=evaluated if evaluated else reason, counts=evaluated['counts'] if evaluated else None,
             actual_server_model=call.get('actual_server_model')))
    outcome = read(trial / 'outcome.json'); decision = read(trial / 'pilot_decision.json')
    check('terminal_candidate_matches', read(trial / 'terminal/candidate.json') == active)
    check('outcome_matches', outcome['actual_calls'] == outcome['reserved_attempts'] == len(calls)
          and outcome['new_accepted_versions'] == int(accepted) and outcome['transport_stopped'] == stopped and outcome['completed'])
    check('outcome_active_hash', outcome['active_sha256'] == x.old.acceptance.sha(active))
    tests = None; independent_rows = 0
    if (trial / 'independent_summary.json').exists():
        check('independent_only_after_accept', accepted and not stopped)
        tests = read(trial / 'independent_summary.json'); freeze = read(trial / 'freeze.json')
        generation = read(trial / 'generation.json'); cases = read(trial / 'independent_cases.json')
        check('freeze_before_generation', generation['at'] > freeze['time'] and generation['freeze_sha256'] == sha(trial / 'freeze.json'))
        check('freeze_source_and_exclusions', freeze['source_sha256'] == read(prep / 'source_binding.json')['source_sha256']
              and freeze['development_exclusion_sha256'] == sha(prep / 'excluded_words.json'))
        check('seed_reproduces_new_cases', cases == x.holdout.base.generate(generation['seed'], read(prep / 'excluded_words.json')))
        words = {t['instruction'] for t in cases}
        check('96_unique_unseen_instructions', len(words) == 96 and not words & set(read(prep / 'excluded_words.json')))
        f = trial / 'frozen/alternative'; result = read(f / 'independent/result.json')
        check('candidate_frozen_exact', read(f / 'candidate.json') == active and freeze['versions'] == dict(alternative=x.old.acceptance.sha(active)))
        check('same_new_cases_executed', read(f / 'independent_cases.json') == cases)
        for revision in ('before', 'after'):
            for file in (prep / revision).glob('*.sv'):
                check('frozen_rtl_' + revision + '_' + file.name, sha(file) == sha(f / revision / file.name))
        if result['healthy']:
            independent_rows = x.holdout.base.native_audit(f, result)['rows_audited']
            with patch.object(x.old, 'CONFIGS', x.holdout.base.CONFIGS):
                guard = x.all_guard(f / 'independent', result, active)
            summary = x.holdout.summarize(result, guard)
        else:
            summary = dict(passed=False, counts=result['counts'], status='native_failure')
        check('independent_summary_recomputed', tests == dict(alternative=summary))
        check('independent_saved_unchanged', outcome['independent'] == tests)
    else:
        check('no_tests_without_acceptance', not accepted and outcome['independent'] is None and not (trial / 'freeze.json').exists())
    cost = read(trial / 'cost.json')['total']
    check('cost_ledger_recomputed', read(trial / 'cost.json') == x.costs.native_cost(trial))
    check('physical_model_cost', cost['model_calls'] == len(calls))
    check('native_cost_ceiling', cost['native_compile_calls'] <= 14 and cost['native_execute_calls'] <= 14 and cost['formal_calls'] == 0)
    check('reservation_total', sum(e['reservation'] for e in ledger) <= 80000)
    for name in ('prompt_tokens', 'completion_tokens'):
        if all(c.get(name) is not None for c in calls):
            check(name + '_actual_usage_sum', cost[name + '_total'] == sum(c[name] for c in calls))
    passed = bool(accepted and tests and tests['alternative']['passed'])
    check('qualification_decision_exact', decision == dict(alternative_passed=passed,
          status='qualified_selected_case_only' if passed else 'stop_alternative_route', automatic_expansion=False, mechanism_benefit_claim=False))
    check('no_automatic_expansion', not outcome['automatic_expansion'])
    s.verify(prep)
    check('old_failures_and_seals_unchanged', s.protected() == read(prep / 'protected_failures.json'))
    out.mkdir(parents=True, exist_ok=False)
    audit = dict(passed=True, checks=checks, check_count=len(checks), actual_model_calls=len(calls),
         new_accepted_versions=int(accepted), independent_passed=tests['alternative']['passed'] if tests else None,
         old_native_rows_reaudited=old_rows, new_development_rows_reaudited=new_rows,
         new_independent_rows_reaudited=independent_rows, route_qualified=passed, mechanism_benefit_claim=False,
         public_generation_capability_only=True, script_sha256=sha(Path(__file__)))
    for name, value in [('audit', audit), ('versions', versions), ('cost', cost), ('independent_summary', tests)]:
        dump(out / (name + '.json'), value)
    lines = ['# research113 / 115：单替代模型固定预算先导结果', '',
        f'真实模型 `{s.MODEL}`：实际调用 **{len(calls)}/2**，新完整接受版本 **{int(accepted)}**，新独立验收 **{tests["alternative"]["passed"] if tests else "未启动"}**。', '',
        '沿用research104失败候选、开发信息、输出表示、种子及原生接受规则，首轮请求仅替换model字段。Qwen结果是历史参照，不是同期随机对照；目录及服务返回的模型名已保存，但权重身份没有独立认证。', '',
        '|轮次|原生执行|完整接受|151事务检出|151事务误报|', '|---|---|---|---:|---:|']
    for v in versions:
        counts = v['counts']
        det = sum(counts[c]['detections'] for c in ('history', 'search')) if counts else '未执行'
        fp = sum(counts[c]['false_positives'] for c in ('history', 'search')) if counts else '未执行'
        lines.append(f'|{v["iteration"]}|{v["native_checked"]}|{v["accepted"]}|{det}|{fp}|')
    lines += ['', '验收范围：当前9事务及115历史＋36搜索事务；420 OP、270 BRANCH目标采样/配置点；首周期与保持阶段触发、合法误报、漏报、关键unknown和历史保护均使用原规则。计数不是独立Bug数量。', '',
        '|独立检出|漏报|误报|unknown|必要未触发|', '|---:|---:|---:|---:|---:|']
    if tests:
        t = tests['alternative']; c = t['counts']
        lines += [f'|{c["detections"]}|{c["misses"]}|{c["false_positives"]}|{c["unknown"]}|{t["required_untriggered"]}|', '',
            '断言与RTL哈希冻结后，生成96个排除开发数据及既有排除清单的新指令字，在四种RV32E/RV32M配置执行。原生记录及分义务/阶段曝光已复算；测试不反馈模型、不选择或修改候选。']
    else:
        lines += ['|未启动|||||']
    lines += ['', f'实际成本：输入/输出tokens **{cost["prompt_tokens_total"]}/{cost["completion_tokens_total"]}**；原生编译 **{cost["native_compile_calls"]}**，实验执行 **{cost["native_execute_calls"]}**，编译冒烟执行 **{cost["compile_smoke_execute_calls"]}**；形式化0。金额不可用，保守预留不当作实际消耗。', '',
        f'审计{len(checks)}项通过：复核旧原生记录{old_rows}条、新开发记录{new_rows}条、新独立记录{independent_rows}条；模型原始响应到可执行性质逐项核对，无人工补写谓词。', '',
        '研究结论：' + ('这个已选定Ibex #166 decoder案例的生成恢复瓶颈，在本预算内得到缓解。' if passed else '本替代路线未达到完整接受与独立通过条件，按协议停止。'),
        '不能据此给出跨案例/多种子生成成功率，也不能把更换模型的结果归因于契约搜索或防退化机制。历史回放只保证这些有限记录上的保护；仿真通过不是整核验证或形式化证明。', '',
        'research100/104/108的失败记录及更早独立结果保持不变。不使用剩余调用自动扩展、改参数或换模型。前瞻防退化实验须固定公共生成流程后另行封存协议与预算；搜索审计结果仍没有契约独有缺口优势。', '',
        '只读复核（不调用模型）：', '```powershell',
        f'wsl -- python3 scripts/research115_alternative_result_audit.py --prepared {prep.relative_to(ROOT).as_posix()} --run {trial.relative_to(ROOT).as_posix()} --out deliverables/research115_audit_NEW', '```']
    (out / 'SUMMARY.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    trace = ['# 真实生成及验收轨迹', '', '原始失败OP集合：', '```systemverilog']
    trace += [a['property'] for a in original['assertions'][1:]] + ['```', '',
        '原生开发诊断：起始sample9/transaction1的OP触发下一周期性质；sample10/transaction2已切换合法指令，illegal=0却仍要求illegal=1。完整151事务原有104条误报，另current9有6条。', '']
    for v in versions:
        trace += [f'## 真实第{v["iteration"] + 1}轮', '```json', json.dumps(v['model_edit'], ensure_ascii=False, indent=2), '```',
                  f'原生检查={v["native_checked"]}；完整接受={v["accepted"]}。', '']
    trace += ['终态活动集合：', '```systemverilog'] + [a['property'] for a in active['assertions']] + ['```', '',
        '完整决策、义务/触发/违例映射见运行目录v*/native/decision.json；冻结及新独立结果见freeze.json和independent_summary.json（仅条件满足时存在）。']
    (out / 'CASE_TRACE.md').write_text('\n'.join(trace) + '\n', encoding='utf-8')
    paths = [prep / 'sealed.json', trial / 'authorization.json', trial / 'outcome.json', trial / 'cost.json', trial / 'pilot_decision.json']
    if tests:
        paths += [trial / n for n in ('freeze.json', 'generation.json', 'independent_cases.json', 'independent_summary.json')]
    dump(out / 'bindings.json', {f.relative_to(ROOT).as_posix(): sha(f) for f in paths})
    print('AUDIT115', {k: v for k, v in audit.items() if k != 'checks'}, flush=True)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    for n in ('prepared', 'run', 'out'):
        ap.add_argument('--' + n, type=Path, required=True)
    a = ap.parse_args(); run(a.prepared.resolve(), a.run.resolve(), a.out.resolve())
