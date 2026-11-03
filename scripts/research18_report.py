"""Report an ended research18 continuation, without feeding tests to any model.

Reuses research17 accounting, freeze checks and evidence projection. A terminal
outcome is mandatory: do not inspect independent results while models run.
"""
from __future__ import annotations

import argparse
import datetime
import json
from pathlib import Path
import shutil

import research17_report as base
from research15_acceptance import inspect

ROOT = base.ROOT
read, dump, digest = base.read, base.dump, base.digest


def portable_path(value):
    """Resolve archived Windows/WSL workspace paths on either host."""
    text = str(value).replace('\\', '/')
    marker = '/AssertionForge-main1/'
    if marker in text:
        return ROOT / text.split(marker, 1)[1]
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def linked_cost_audit(protocol):
    """Charge prior failed runs and backend diagnostics without SVA credit.

    Protocol fields preceding_attempts/backend_probes are lists of directory
    paths, absolute Windows/WSL or repository-relative. Repeated paths are
    charged only on their first occurrence. No recursive historical summing.
    """
    result = {'preceding_attempts': [], 'backend_probes': [], 'duplicates_not_charged': []}
    seen = set()
    for kind in ('preceding_attempts', 'backend_probes'):
        paths = protocol.get(kind, [])
        if not isinstance(paths, list) or not all(isinstance(p, str) for p in paths):
            raise ValueError(kind + ' must be a list of directory path strings')
        for value in paths:
            folder = portable_path(value).resolve()
            if ROOT not in folder.parents or not folder.is_dir():
                raise ValueError('Linked cost directory must exist inside workspace: ' + value)
            if folder in seen:
                result['duplicates_not_charged'].append(dict(kind=kind, path=value))
                continue
            seen.add(folder)
            outcome = read(folder / 'outcome.json')
            if kind == 'preceding_attempts' and (not outcome or outcome.get('status') == 'running'):
                raise ValueError('Preceding experiment must have a terminal outcome: ' + value)
            files = base.artifacts(folder)
            cost = base.cost_audit(folder, files)
            recorded = cost.get('recorded_model_cost') or {}
            actual = cost['total']
            comparison = dict(recorded_calls=recorded.get('calls'), physical_attempts=actual['model_calls'],
                difference=(actual['model_calls'] - recorded['calls']) if type(recorded.get('calls')) is int else None,
                final_usage_unavailable=actual['usage_unavailable_calls'],
                crosscheck=cost.get('recorded_model_cost_crosscheck'),
                accounting='Physical attempt records govern; model_cost.json may count only calls returned to the caller. Cancelled attempts remain charged with unavailable final usage. A mismatch is disclosed, not silently treated as agreement.')
            tracked = {folder / c['path'] for c in cost['model_calls'] + cost['native_commands']}
            for call in cost['model_calls']:
                for filename in ('result.json', 'transport_result.json', 'request.json'):
                    p = (folder / call['path']).parent / filename
                    if p.is_file():
                        tracked.add(p)
            for filename in ('protocol.json', 'outcome.json', 'result.json', 'model_cost.json'):
                p = folder / filename
                if p.is_file():
                    tracked.add(p)
            tracked.update((folder / 'model_load').glob('*.json'))
            semantic = []
            if kind == 'preceding_attempts':
                for native_path in sorted((folder / 'core').glob('v*/native/result.json')):
                    native_result = read(native_path, {})
                    version = native_path.parent.parent
                    if native_result.get('group') and (version / 'model_call/candidate.json').is_file():
                        semantic.append(dict(version=version.relative_to(folder).as_posix(),
                            counts=native_result.get('counts'), decision=read(version / 'decision.json'),
                            candidate=read(version / 'model_call/candidate.json')))
            result[kind].append(dict(path=folder.relative_to(ROOT).as_posix(), outcome=outcome,
                diagnostic_result=read(folder / 'result.json') if kind == 'backend_probes' else None,
                protocol=read(folder / 'protocol.json'), cost=cost, accounting_comparison=comparison,
                completed_core_semantic_proposals=semantic,
                management_operations=management_audit(folder),
                context_preflight_audit=context_audit(folder, files),
                sva_success_credit=False,
                record_hashes={p.relative_to(folder).as_posix(): digest(p) for p in sorted(tracked)}))
    return result


def management_audit(run):
    folder = run / 'model_load'
    request = read(folder / 'request.json')
    if request is None:
        return dict(management_requests=0, completed_records=0, wall_seconds_known_subtotal=0,
                    generation_calls=0, records=[])
    result = read(folder / 'result.json')
    response = read(folder / 'response.json')
    return dict(management_requests=1, completed_records=int(result is not None),
        wall_seconds_known_subtotal=(result or {}).get('wall_seconds'),
        generation_calls=(result or {}).get('generation_calls'),
        records=[dict(path='model_load', request=request, response=response, result=result,
            record_hashes={p.name: digest(p) for p in folder.glob('*.json')})],
        scope='Empty-prompt model load is a management request. Its response/wall time is retained separately; no SVA generation or generation-token credit.')


def resumed_rejection_audit(run):
    archived = read(run / 'resumed_core_rejection.json')
    if archived is None:
        return None
    source = portable_path(archived['source']).resolve()
    if ROOT not in source.parents:
        raise ValueError('Resumed rejection must belong to workspace')
    candidate = read(source / 'model_call/candidate.json')
    decision = read(source / 'decision.json', {})
    result = read(source / 'native/result.json', {})
    files = ('model_call/candidate.json', 'model_call/result.json', 'decision.json', 'native/result.json')
    return dict(archived=archived, source=str(source), candidate=candidate, decision=decision,
        counts=result.get('counts'), source_was_rejected=decision.get('accepted') is False,
        feedback_counts_match=(archived.get('feedback') or {}).get('counts') == result.get('counts'),
        record_hashes={name: digest(source / name) for name in files if (source / name).is_file()},
        accounting='One actual prior semantic-rejection iteration; costs already charged in preceding_attempts, never added again.')


def context_audit(run, files):
    records = []
    for path in files:
        if path.name != 'result.json' or path.parent.name != 'context_preflight':
            continue
        iteration = path.parent.parent
        preflight = read(path, {})
        call = read(iteration / 'model_call/result.json', {})
        decision = read(iteration / 'decision.json', {})
        observed = call.get('context_preflight', {})
        delta = observed.get('observed_minus_rendered')
        margin = observed.get('wrapper_margin_tokens')
        checked = (preflight.get('fits_with_output_reserve') is True and
                   type(delta) is int and type(margin) is int and abs(delta) <= margin and
                   call.get('status') == 'response_received')
        records.append(dict(path=path.relative_to(run).as_posix(), preflight=preflight,
            observed=observed, model_status=call.get('status'), accepted=decision.get('accepted'),
            accepted_context_validated=checked if decision.get('accepted') else None,
            generation_call_record_present=(iteration / 'model_call/attempt.json').exists(),
            rejection_before_generation=read(iteration / 'context_preflight/decision.json')))
    return dict(records=records, tokenization_preflights=len(records),
        tokenization_calls_known_subtotal=sum(r['preflight'].get('tokenization_calls') or 0 for r in records),
        invalid_accepted_contexts=[r['path'] for r in records if r['accepted'] and not r['accepted_context_validated']],
        scope='Preflight tokenization is not a model-generation call. Context fit and observed token difference are engineering guards, not proof of semantic prompt understanding.')


def reused_integrity(reused):
    source = portable_path(reused.get('source', ''))
    checks = []
    if ROOT not in source.resolve().parents:
        return dict(passed=False, error='source_outside_workspace', checks=[])
    for rel, expected in reused.get('source_files', {}).items():
        path = (source / rel).resolve()
        if source.resolve() not in path.parents:
            raise ValueError('Unsafe reused source path')
        actual = digest(path) if path.is_file() else None
        checks.append(dict(path=rel, expected=expected, actual=actual, passed=actual == expected))
    return dict(source=str(source), passed=bool(checks) and all(c['passed'] for c in checks),
                checked=len(checks), checks=checks)


def deduplicated_counts(group, replay_folder=None):
    """Do not count the same correct stimulus four times across mutant pairs."""
    scenarios = {}
    if replay_folder is not None:
        for path in sorted(Path(replay_folder).glob('case_*/case.json')):
            case = read(path)
            stimulus = {k: case[k] for k in ('depth', 'pipeline', 'rows')}
            scenarios[case['id']] = dict(stimulus_sha256=base.candidate_sha(stimulus),
                case_file=str(path), case_sha256=digest(path), depth=case['depth'], pipeline=case['pipeline'])
    buckets = {}
    original_hashes = {}
    missing = []
    for row in group.get('ledger', []):
        # Legacy stimulus_sha256 includes scenario_id, whose mode suffix makes
        # identical control inputs appear different. Rebuild from actual saved
        # stimulus and parameters, without changing any experiment artifact.
        projected = dict(row)
        scenario = row.get('scenario_id')
        original_hashes.setdefault(scenario, set()).add(row.get('stimulus_sha256'))
        if scenario in scenarios:
            projected['stimulus_sha256'] = scenarios[scenario]['stimulus_sha256']
        elif replay_folder is not None:
            missing.append(row.get('evidence_id'))
        key = tuple(projected.get(k) for k in ('stimulus_sha256', 'variant', 'epoch', 'cycle', 'obligation'))
        buckets.setdefault(key, []).append(projected)
    rows, conflicts = [], []
    for key, members in buckets.items():
        chosen = dict(members[0])
        # Preserve uncertainty if nominal duplicate executions disagree.
        if len({base.candidate_sha({k: r.get(k) for k in ('oracle', 'native')}) for r in members}) != 1:
            chosen['native'] = {}
            conflicts.append(dict(key=list(key), count=len(members)))
        chosen['evidence_id'] = 'dedup:' + base.candidate_sha(key)
        rows.append(chosen)
    info = inspect(rows)
    event_key = lambda r: tuple(r.get(k) for k in ('stimulus_sha256', 'variant', 'epoch', 'cycle'))
    targets = [r for r in info['rows'].values() if r.get('oracle', {}).get('verdict') == 'violated']
    misses = [info['rows'][key] for key in info['misses']]
    fields = ('detections', 'misses', 'unknown', 'false_positives', 'triggers')
    detail = {}
    for ob in base.ALL_OBLIGATIONS:
        selected = {k: r for k, r in info['rows'].items() if r.get('obligation') == ob}
        counts = {k: sum(info['rows'][eid].get('obligation') == ob for eid in info[k]) for k in fields}
        counts.update(rows=len(selected),
            satisfied_oracle_rows=sum(r.get('oracle', {}).get('verdict') == 'satisfied' for r in selected.values()),
            target_oracle_rows=sum(r.get('oracle', {}).get('verdict') == 'violated' for r in selected.values()),
            correct_control_rows=sum(r.get('variant') == 'correct' for r in selected.values()))
        detail[ob] = counts
    return dict(raw_rows=len(group.get('ledger', [])), unique_rows=len(rows),
        repeated_rows_removed=len(group.get('ledger', [])) - len(rows),
        counts={k: len(info[k]) for k in fields}, by_obligation=detail,
        inconsistent_duplicate_groups=conflicts, malformed=info['errors'],
        later_attribution_unknown_raw=len(group.get('exclusions', [])),
        original_stimulus_hashes={str(k): sorted(v, key=str) for k, v in original_hashes.items()},
        reconstructed_stimuli=scenarios, reconstruction_missing_rows=missing,
        reconstruction_complete=not missing if replay_folder is not None else None,
        first_target_obligation_rows=len(targets), first_target_events=len({event_key(r) for r in targets}),
        missed_obligation_rows=len(misses), missed_events=len({event_key(r) for r in misses}),
        missed_event_details=[{k: r.get(k) for k in ('scenario_id', 'variant', 'epoch', 'cycle', 'obligation')}
                             for r in misses],
        rule='Reconstructed SHA256 of saved case depth/pipeline/rows + RTL variant + reset epoch + cycle + obligation; original scenario-containing hashes retained separately; duplicate disagreements become unknown',
        unit='Obligation/sample rows, not independent failures or Bugs; physical replay cost remains fully charged.')


def render(run, result):
    # Retain tested standard trace and finite-scope explanations, replace only
    # continuation-specific accounting and command text.
    text = base.render(run, result)
    text = text.replace('scripts/research17_loop.py --out deliverables/research17_closed_loop_20261016_r02',
                        'scripts/research18_continue.py --source deliverables/research17_closed_loop_20261016_r01 --out deliverables/research18_closed_loop_20261016_r02')
    text = text.replace('scripts/research17_report.py', 'scripts/research18_report.py')
    recorded_command = result.get('execution_command')
    if recorded_command is not None:
        if isinstance(recorded_command, str):
            display_command = recorded_command
        elif isinstance(recorded_command, dict) and isinstance(recorded_command.get('command'), str):
            display_command = recorded_command['command']
        else:
            display_command = json.dumps(recorded_command, ensure_ascii=False, indent=2)
        example = ('wsl -- python3 scripts/research18_continue.py --source '
                   'deliverables/research17_closed_loop_20261016_r01 --out '
                   'deliverables/research18_closed_loop_20261016_r02')
        text = text.replace(example, display_command)
        text = text.replace('在仓库根目录可执行同一实验入口（运行目录必须未使用）：',
            '以下为 execution.command.json 中保存的实际启动记录。复现时只将 --out 换成未使用目录，保留其他参数；已有目录禁止覆盖：')
    prefix = [
        '# 本轮实际结果', '',
        f"运行终态：`{result['status']}`。两项义务的有限证据链：`{result['core_chain']['status']}`。"
        '全五义务案例通过与原始历史 FIFO 缺陷复现均未建立。', '',
        '## 续跑与复用边界', '',
        '本轮真实模型调用用于自动细化。初始 SVA 的真实生成和契约搜索来自 research17 已保存的运行，'
        '没有重新生成初始候选，也没有把复制的搜索记录计为本轮新发现。原请求、响应、来源清单和 SHA256 均可追溯。', '',
        '所有实际执行的候选在独立输入生成前冻结；本次独立测试包含：'
        + '、'.join((result['independent']['core_independent'].get('summary') or {}).keys())
        + '。未启动的四组不计为已执行或已冻结。本轮只有 core_independent 一个测试批次，'
        '不存在第二个 ablation_independent 批次。报告不向模型提供独立结果。', '',
        '## 实验设计限制', '',
        '公共背景包含五项义务，但 shared_initial 的真实模型任务明确要求只生成一条 order_payload 断言。'
        '因此它是受控的局部初始候选；搜索暴露的是尚未保护的 drain_no_loss。'
        '本实验不能证明模型自主生成全部义务时自然遗漏了该义务，也不能代表一般强基线的能力。'
        '两个参数配置上的 drop/drain_no_loss 属于同一缺口类。', '',
        'A/C 若模型选择 keep 并获接受，表示当前普通反馈未要求新增保护、原候选被保留；'
        '不能把此类无新增问题的接受记为漏报修复成功。应同时查看 has_acquired_gap、候选变化及独立结果。', '',
        '未启用防退化的 B 组按最后一个开发 case 的当前证据验收；它可能在该 case 通过时接受。'
        '其 after 计数仍汇总全部开发 case，historical_gate_audit.json 另存全部历史回放的审计结果，'
        '但该审计不参与 B 的接受决策。不能把 B 的 accepted 等同于全历史防退化门通过。'
        'A 也使用同一普通验收策略，因其只有公共 case，验收范围恰与当前开发 case 重合。', '',
        '| 成本口径 | 真实调用 | 输入 tokens 已知小计 | 输出 tokens 已知小计 | usage 不可用调用 | 原生编译 | 原生执行 |',
        '|---|---:|---:|---:|---:|---:|---:|',
    ]
    cost_rows = [('本轮新执行', result['cost']['total']),
                 ('复用历史运行（单列，不重复计新成本）', result['historical_cost'].get('total', {}))]
    for kind, label in [('preceding_attempts', '此前失败实验'), ('backend_probes', '后端格式探针')]:
        cost_rows += [(label + '：' + item['path'], item['cost']['total'])
                      for item in result['linked_costs'][kind]]
    for label, cost in cost_rows:
        prefix.append('| ' + label + ' | ' + ' | '.join(str(cost.get(k, 'unavailable')) for k in (
            'model_calls', 'prompt_tokens_known_subtotal', 'completion_tokens_known_subtotal',
            'usage_unavailable_calls', 'native_compile_calls', 'native_execute_calls')) + ' |')
    prefix += ['', '失败实验与后端格式探针没有丢弃，其实际请求、原生执行和不可用用量分别列入成本。'
        '格式探针只检查服务是否执行 JSON grammar，不能作为 SVA 生成、编译或功能修复成功证据。', '',
        '历史 core/v0 取消调用没有服务最终用量；tokens 保持不可用。已知小计不能当作完整总成本。'
        '取消调用、失败调用和编译附带执行均保留；模型计费金额不可用。', '',
        '四组结果不预设防退化优于普通反馈。防退化验收通过只说明已回放历史证据上的保护保持；'
        '相同冻结候选或相同测试结果不能据此证明某一机制有额外收益。', '']
    management = result['management_operations']
    prefix += ['## 模型加载管理调用', '',
        f"本轮空提示模型加载请求 {management['management_requests']} 次，已记录终态 "
        f"{management['completed_records']} 次，实际耗时已知值 "
        f"{management['wall_seconds_known_subtotal']} 秒，generation_calls="
        f"{management['generation_calls']}。request/response/result 均保存于 model_load。"
        '这是保持或恢复本地 runner 的管理操作，不并入真实 SVA 生成调用数或生成 tokens；'
        '未记录的终态保持不可用。此前运行的同类管理操作也在 linked_costs 单列。', '']
    for item in result['linked_costs']['preceding_attempts']:
        comparison = item['accounting_comparison']
        prefix += [f"此前实验 `{item['path']}` 终态 `{(item['outcome'] or {}).get('status')}`："
            f"model_cost.json 记录 {comparison['recorded_calls']} 次，实际 attempt 记录 "
            f"{comparison['physical_attempts']} 次，最终用量不可用 {comparison['final_usage_unavailable']} 次。"
            '若次数不同，保留差异；取消请求可能未返回上层调用计数器。本报告按实际 attempt 计数，'
            '不把已完成调用小计声称为完整成本。', '']
        recorded_reason = (item.get('outcome') or {}).get('reason')
        if recorded_reason:
            prefix += [f'该次停止原因原记录：`{recorded_reason}`。', '']
    resumed = result.get('resumed_core_rejection')
    if resumed:
        counts = resumed.get('counts') or {}
        prefix += ['## 连续保留的真实拒绝轨迹', '',
            f"本轮从 `{resumed['source']}` 的实际拒绝继续，旧提案没有成为已接受版本。"
            f"该提案原生回放产生 {counts.get('false_positives', '不可用')} 个合法证据行误报、"
            f"{counts.get('unknown', '不可用')} 个归因 unknown 行，接受状态 `{resumed['decision'].get('accepted')}`。", '',
            '原拒绝版本的 SVA：', '```systemverilog']
        prefix += [a['property'] for a in (resumed.get('candidate') or {}).get('assertions', [])]
        prefix += ['```', '',
            '该版本把输出握手与参考队列为空关联起来；正常输出的采样时刻参考队列仍包含待输出事务，'
            '因而在合法事务上产生误报。新运行收到的是这次真实拒绝的提案、原因和计数，'
            '并未把错误版本改成成功版本。', '',
            '原有 order_payload 断言仍在。新增的早期误报污染后续违例归因，导致历史检出无法确认，'
            '门控因而拒绝；这不表示原断言被删除或完全停止触发，也不能把检出计数下降解读为新增遗漏多个独立 Bug。'
            '原始门控原因完整保留于 results.json 的 resumed_core_rejection.decision。', '',
            f"此前运行实际完成原生语义回放的核心提案 {result['preceding_core_semantic_proposals']} 轮，"
            f"核心本轮最多 {result['protocol'].get('max_refinement_calls', '不可用')} 轮；"
            '恢复文件指向其中最近的真实语义拒绝，不额外增加轮数。此前格式错误、取消调用及生成前预检拒绝分别记账。'
            '上一运行被取消的后续请求不计为正式成功，最终用量没有记录时保持不可用。', '']
    context = result['context_preflight_audit']
    prefix += ['## 上下文完整性守卫', '',
        f"保存 {context['tokenization_preflights']} 次生成前预检，实际 tokenizer 调用已知小计 "
        f"{context['tokenization_calls_known_subtotal']} 次；这些不计为生成调用。"
        '每次保留渲染提示词和 token 计数；预检不能容纳输入及输出预留时不发送生成请求。'
        '响应的实际 prompt tokens 与预检渲染计数差异超出容差时，不接受或执行候选。', '',
        f"接受版本中未通过上下文核验的记录：`{context['invalid_accepted_contexts']}`。"
        '该守卫检查截断风险，不证明模型理解了全部上下文。', '']
    suffix = ['', '## 验收矩阵', '',
        '| 要求 | 实现 | 实际产物 | 本轮状态 |', '|---|---|---|---|',
        '| 真实初始生成 | research17_model.py | reused_source.json 指向原请求/响应、shared_initial.json | 复用已发生的真实生成，非本轮新调用 |',
        '| 合法漏报搜索及事务对齐 | research17_search_audit.py | search/strict_witnesses.json、admitted_cases.json | 复用并重验原见证，非新增搜索 |',
        '| 自动细化与原生回放 | research17_loop.py、research17_model_schema.py | core/v*/model_call、core/v*/native | ' + str(result['core'].get('resolved', False)) + '（是否接受修订） |',
        '| 历史保护及有效触发验收 | research15_acceptance.py | core/v*/historical_gate_audit.json、decision.json | 所有拒绝与接受理由保留 |',
        '| 复杂 FIFO 多参数 | research17_fifo_feedback.py | 开发 depth2/p0、depth5/p1；测试 depth4/p2 原生目录 | 以实际 healthy 和逐义务结果为准 |',
        '| 冻结后独立验证 | research17_loop.holdout | core_independent/split.json、summary.json | ' + str(result['independent']['core_independent']['status']) + ' |',
        '| 四组机制比较 | research18_continue.py | arms/A..D、公共独立批次 | ' + str(result['status']) + ' |',
        '| 内容版本与成本审计 | research18_report.py | report/manifest.json、freeze_checks.json、cost/results.json | 当前与复用历史成本分开 |', '',
        '上表统一实验命令见前文；报告脚本只读实验数据并写 report 目录。函数检查或语法检查通过不代替上述端到端结果。', '',
        '## 原生细化的逐版证据数量', '',
        '| 组/版本 | 旧检出 | 旧漏报 | 新检出 | 新漏报 | 新误报 | 新unknown | 接受 |',
        '|---|---:|---:|---:|---:|---:|---:|---|']
    for name, summary in [('core', result['core']), *result['arms'].items()]:
        for entry in summary.get('history', []):
            before, after = entry.get('before') or {}, entry.get('after') or {}
            suffix.append(f"| {name}/v{entry['iteration']} | {before.get('detections', '不可用')} | "
                f"{before.get('misses', '不可用')} | {after.get('detections', '不可用')} | "
                f"{after.get('misses', '不可用')} | {after.get('false_positives', '不可用')} | "
                f"{after.get('unknown', '不可用')} | {entry.get('decision', {}).get('accepted')} |")
    suffix += ['', '## 四组实际成本', '',
        '| 组 | 细化调用 | 输入tokens | 输出tokens | usage不可用 | 开发编译 | 开发执行 | 独立编译 | 独立执行 |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    # base cost phases group the shared holdout together; attribute its commands
    # by the explicit candidate path without inventing per-arm shared charges.
    for name in 'ABCD':
        if result['arms'][name].get('status') == 'not_executed':
            suffix.append(f'| {name}（未执行） | — | — | — | — | — | — | — | — |')
            continue
        c = result['cost']['by_phase'].get('arms/' + name, {})
        commands = [v for v in result['cost']['native_commands']
                    if v['path'].startswith('core_independent/' + name + '/')]
        suffix.append(f'| {name} | ' + ' | '.join(str(c.get(k, 0)) for k in (
            'model_calls', 'prompt_tokens_known_subtotal', 'completion_tokens_known_subtotal',
            'usage_unavailable_calls', 'native_compile_calls', 'native_execute_calls')) +
            f" | {sum(v['kind'] == 'compile' for v in commands)} | "
            f"{sum(v['kind'] == 'execute' for v in commands)} |")
    suffix += ['', '初始生成与搜索历史成本作为公共来源单列，未机械分摊或重复计入每组；core pilot 成本单列于机器可读分阶段成本。'
        '未执行组的零调用不意味着实验成功。', '',
        '初始候选、每版模型响应、候选 SVA、拒绝原因与最终冻结版本均分别保存。'
        '模型未返回可执行候选的版本没有原生结果，记为不可用。搜索中不同深度的 drop/drain_no_loss 见证'
        '属于同一失效机制的两个参数实例，不能计成两个独立缺口。', '',
        '## 公共独立测试去重与义务分母', '',
        '原始回放中同一输入的 correct 控制会随四种故障分别运行。旧 stimulus_sha256 包含带故障标签的 scenario_id，'
        '不能直接用来跨故障去重。报告从保存的 case.json 中 depth、pipeline、rows 重建输入哈希，保留旧哈希与原始计数，'
        '不修改实验产物。实际成本全部计入，下面按重建输入哈希、'
        'RTL 变体、复位 epoch、周期及义务去重。重复结果不一致时记为 unknown。不同周期仍属于同一失败机制，'
        '这些行数不代表独立发现数量。', '',
        '| 组 | 义务 | 满足义务行 | 目标违例行 | 检出 | 漏报 | 误报 | unknown | 触发行 |',
        '|---|---|---:|---:|---:|---:|---:|---:|---:|']
    notes = []
    for name, data in result['independent_deduplicated'].items():
        for ob, c in data['by_obligation'].items():
            suffix.append(f'| {name} | {ob} | ' + ' | '.join(str(c[k]) for k in (
                'satisfied_oracle_rows', 'target_oracle_rows', 'detections', 'misses',
                'false_positives', 'unknown', 'triggers')) + ' |')
        notes.append(f"{name}：原始 {data['raw_rows']} 行，去重后 {data['unique_rows']} 行，"
                      f"移除重复 {data['repeated_rows_removed']} 行；后续违例归因 unknown "
                      f"{data['later_attribution_unknown_raw']} 条另行保留。")
        notes.append(f"{name}：{data['first_target_obligation_rows']} 个首违例义务行对应 "
            f"{data['first_target_events']} 个首违例采样事件；{data['missed_obligation_rows']} 个漏报义务行对应 "
            f"{data['missed_events']} 个采样事件。同一事件可能违反多项义务；事件数也不是独立 Bug 数。")
        for missed in data['missed_event_details']:
            notes.append(f"漏报：{missed['scenario_id']}，周期 {missed['cycle']}，义务 {missed['obligation']}。")
    suffix += ['', '\n\n'.join(notes), '', '本轮完整案例通过仍未建立；两项义务的证据链结论取决于实际回放及哈希检查。'
        'stat、原始 FIFO presented 保持 unknown。axis_fifo 加人工边界故障仅计为一个工程父案例。', '',
        f"复用源文件哈希核验：{result['reused_source_integrity']['passed']}，"
        f"核验文件数 {result['reused_source_integrity'].get('checked', 0)}。", '']
    return '\n'.join(prefix) + text + '\n'.join(suffix)


def verify(run, out):
    manifest = read(out / 'manifest.json')
    if not manifest:
        raise ValueError('Missing nonempty manifest')
    checks = []
    for rel, expected in manifest.items():
        path = (run / rel).resolve()
        if run not in path.parents:
            raise ValueError('Unsafe manifest path')
        actual = digest(path) if path.is_file() else None
        checks.append(dict(path=rel, expected=expected, actual=actual, passed=actual == expected))
    extra = sorted({p.relative_to(run).as_posix() for p in base.artifacts(run)} - set(manifest))
    source = reused_integrity(read(run / 'reused_source.json', {}))
    archived_result = read(out / 'results.json', {})
    archived = archived_result.get('linked_costs', {})
    linked_checks = []
    for kind in ('preceding_attempts', 'backend_probes'):
        for item in archived.get(kind, []):
            folder = portable_path(item['path']).resolve()
            for rel, expected in item.get('record_hashes', {}).items():
                path = (folder / rel).resolve()
                if ROOT not in folder.parents or folder not in path.parents:
                    raise ValueError('Unsafe linked cost manifest path')
                actual = digest(path) if path.is_file() else None
                linked_checks.append(dict(path=str(path), expected=expected, actual=actual, passed=actual == expected))
    resumed = archived_result.get('resumed_core_rejection')
    if resumed:
        folder = portable_path(resumed['source']).resolve()
        for rel, expected in resumed.get('record_hashes', {}).items():
            path = (folder / rel).resolve()
            if ROOT not in folder.parents or folder not in path.parents:
                raise ValueError('Unsafe resumed rejection path')
            actual = digest(path) if path.is_file() else None
            linked_checks.append(dict(path=str(path), expected=expected, actual=actual, passed=actual == expected))
    freezes = base.freeze_audit(run)
    result = dict(passed=all(c['passed'] for c in checks) and not extra and source['passed']
        and bool(freezes) and all(f['passed'] for f in freezes) and all(c['passed'] for c in linked_checks),
        checked=len(checks), checks=checks, linked_cost_checks=linked_checks,
        unmanifested_files=extra, reused_source=source, freezes=freezes)
    dump(out / 'verification.json', result)
    print(json.dumps(dict(passed=result['passed'], checked=len(checks), unmanifested_files=extra)))
    if not result['passed']:
        raise SystemExit(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, default=ROOT / 'deliverables/research18_closed_loop_20261016_r01')
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    run = args.run.resolve()
    if ROOT not in run.parents or not run.is_dir():
        raise ValueError('Existing workspace run required')
    outcome = read(run / 'outcome.json')
    if not outcome or outcome.get('status') == 'running':
        raise SystemExit('Run has no terminal outcome; independent results were not read.')
    out = run / 'report'
    out.mkdir(exist_ok=True)
    if args.verify:
        return verify(run, out)
    files = base.artifacts(run)
    cost, freezes = base.cost_audit(run, files), base.freeze_audit(run)
    test = base.test_audit(run, 'core_independent', freezes)
    core = read(run / 'core/summary.json', {})
    witnesses = read(run / 'search/strict_witnesses.json', [])
    reused = read(run / 'reused_source.json', {})
    protocol = read(run / 'protocol.json', {})
    linked = linked_cost_audit(protocol)
    resumed = resumed_rejection_audit(run)
    context = context_audit(run, files)
    management = management_audit(run)
    integrity = reused_integrity(reused)
    projected = base.independent_scope(test, 'core', base.CORE_OBLIGATIONS)
    chain = bool(core.get('resolved') and core.get('has_acquired_gap') and projected['passed']
        and any(w.get('valid') for w in witnesses) and integrity['passed']
        and not context['invalid_accepted_contexts']
        and any(f['scope'] == 'core' and f['passed'] for f in freezes)
        and any(h.get('decision', {}).get('accepted') and h['decision'].get('gate_enforced')
                for h in core.get('history', [])))
    result = dict(status=outcome['status'], generated_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        protocol=protocol, outcome=outcome, linked_costs=linked,
        resumed_core_rejection=resumed, context_preflight_audit=context,
        management_operations=management, execution_command=read(run / 'execution.command.json'),
        preceding_core_semantic_proposals=sum(len(item['completed_core_semantic_proposals'])
            for item in linked['preceding_attempts']),
        initial_candidate=read(run / 'shared_initial.json'), core_candidate=read(run / 'core/frozen_candidate.json'),
        core=core, arms={a: read(run / 'arms' / a / 'summary.json', {'status': 'not_executed'}) for a in 'ABCD'},
        strict_witnesses=witnesses, search_comparison=read(run / 'search/corrected_comparison.json'),
        independent={'core_independent': test}, freeze_checks=freezes, cost=cost,
        historical_cost=reused.get('cost', {}), reused_source_integrity=integrity,
        reused_source_metadata={k: v for k, v in reused.items() if k not in ('cost', 'source_files')},
        experimental_design_limits=dict(
            initial_candidate='Real model explicitly requested one order_payload property despite five-obligation context; controlled partial candidate, not spontaneous omission under all-obligation generation.',
            ordinary_keep='Accepted keep in A/C with no acquired gap is retention, not a newly repaired false negative.',
            unguarded_acceptance='A/B use only the last development case for admission; full replay counts and historical gate audit are observational, not enforced.',
            witness_diversity='Two depth configurations of drop/drain_no_loss are one obligation/failure-mechanism gap class.',
            generalization='Does not establish superiority over a strong general baseline or a global non-regression guarantee.'),
        core_chain=dict(status='verified_for_two_obligations_on_recorded_scope' if chain else 'not_established',
            passed=chain, independent_two_obligations=projected,
            scope='Two projected first-attribution obligations on finite replay, not a global or whole-case guarantee'),
        whole_parent_case=dict(passed=False, status='not_established', required_obligations=list(base.ALL_OBLIGATIONS),
            original_historical_fifo_bug='unknown', stat='unknown', engineering_parent_count=1),
        independent_deduplicated={})
    for name in (test.get('summary') or {}):
        ledger = read(run / 'core_independent' / name / 'independent_ledger.json')
        if ledger is not None:
            result['independent_deduplicated'][name] = deduplicated_counts(ledger, run / 'core_independent' / name)
    result['accepted_obligation_mapping'] = {'core': base.accepted_mapping(run, 'core', core),
        **{a: base.accepted_mapping(run, 'arms/' + a, result['arms'][a]) for a in 'ABCD'}}
    dump(out / 'results.json', result)
    dump(out / 'cost/results.json', dict(new_actual=cost, reused_historical=result['historical_cost'],
        linked_attempts_and_probes=linked, management_operations=management,
        tokenization_preflights=context))
    dump(out / 'freeze_checks.json', freezes)
    (out / 'REPORT.md').write_text(render(run, result), encoding='utf-8')
    shutil.copy2(__file__, out / 'report_script_snapshot.py')
    manifest = {p.relative_to(run).as_posix(): digest(p) for p in files}
    dump(out / 'manifest.json', manifest)
    dump(out / 'source_and_rtl_hashes.json', {k: v for k, v in manifest.items() if Path(k).suffix in ('.py', '.sv', '.v')})
    print(json.dumps(dict(status=result['status'], core_chain=chain, cost=cost['total'], report=str(out / 'REPORT.md'))))


if __name__ == '__main__':
    main()
