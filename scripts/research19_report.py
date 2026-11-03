"""Audit a terminal fresh or continued research19 run; never read active tests.

Reuses existing native accounting, candidate freeze checks, and stimulus-based
deduplication. This command performs no model calls or hardware executions and
writes only RUN/report. Missing results are never treated as a passing result.
"""
from __future__ import annotations

import argparse
import datetime
import json
from pathlib import Path
import shutil

import research17_report as base
import research18_report as previous

ROOT = base.ROOT
read, dump, digest = base.read, base.dump, base.digest


def planning_audit(run, files, protocol, cost):
    """Account for advisory calls and verify exact raw-response inclusion.

    A planning response is never itself an executable candidate. Inspect only
    saved requests/responses; no model output is rewritten for this audit.
    """
    enabled = (protocol.get('contract_planning') or {}).get('enabled') is True
    records = []
    groups = {'contract_planning': [], 'sva_generation': []}
    for call in cost['model_calls']:
        attempt = run / call['path']
        folder = attempt.parent
        planning = folder.parent.name == 'planning'
        saved = read(folder / 'result.json', read(folder / 'transport_result.json', {}))
        purpose = 'contract_planning' if planning else 'sva_generation'
        call.update(purpose=purpose, recorded_phase=saved.get('phase'))
        groups[purpose].append(call)
        if planning:
            response = read(folder / 'response.raw.json', {})
            raw = (response.get('message') or {}).get('content')
            main_folder = folder.parent.parent / 'model_call'
            main_request = read(main_folder / 'request.json')
            main_submitted = (main_folder / 'attempt.json').is_file()
            included = None
            if main_request:
                for message in main_request.get('messages', []):
                    try:
                        content = json.loads(message.get('content', ''))
                    except (ValueError, TypeError):
                        continue
                    if isinstance(content, dict):
                        work = content.get('requested_work')
                        if isinstance(work, dict):
                            included = work.get('real_model_contract_draft')
            exact = isinstance(raw, str) and isinstance(included, str) and raw == included
            records.append(dict(path=folder.relative_to(run).as_posix(),
                status=saved.get('status', 'unknown'), candidate_status=saved.get('candidate_status'),
                main_generation_submitted=main_submitted,
                main_request=main_folder.relative_to(run).as_posix() + '/request.json',
                response_characters=len(raw) if isinstance(raw, str) else None,
                response_sha256=base.candidate_sha(raw) if isinstance(raw, str) else None,
                quoted_draft_sha256=base.candidate_sha(included) if isinstance(included, str) else None,
                exact_raw_response_in_main_request=exact if main_submitted else None,
                main_not_submitted_reason='Planning failure or stop before final generation; no SVA execution credit.' if not main_submitted else None,
                never_directly_executed=not (folder / 'candidate.json').exists()
                    and not (folder.parent / 'native').exists(),
                phase=saved.get('phase')))
    missing = []
    if enabled:
        for call in groups['sva_generation']:
            folder = (run / call['path']).parent
            linked = next((r for r in records if r['main_request'] == folder.relative_to(run).as_posix() + '/request.json'), None)
            if not linked or linked['status'] != 'response_received' or not linked['exact_raw_response_in_main_request']:
                missing.append(call['path'])
    def summarize(calls):
        return dict(model_calls=len(calls),
            prompt_tokens_known_subtotal=sum(c.get('prompt_tokens') or 0 for c in calls),
            completion_tokens_known_subtotal=sum(c.get('completion_tokens') or 0 for c in calls),
            usage_unavailable_calls=sum(c.get('prompt_tokens') is None or c.get('completion_tokens') is None for c in calls),
            wall_seconds_known_subtotal=sum(c.get('wall_seconds') or 0 for c in calls))
    totals = {purpose: summarize(calls) for purpose, calls in groups.items()}
    per_phase = {phase: {purpose: summarize([c for c in calls if c['phase'] == phase])
        for purpose, calls in groups.items()} for phase in sorted({c['phase'] for c in cost['model_calls']})}
    return dict(enabled=enabled, records=records, by_purpose=totals, by_phase_and_purpose=per_phase,
        all_physical_attempts_classified=sum(v['model_calls'] for v in totals.values()) == cost['total']['model_calls'],
        submitted_main_requests_missing_valid_exact_draft=missing,
        integrity_passed=not missing and all(r['never_directly_executed'] for r in records),
        scope='Planning and final SVA generation both consume real calls and tokens. Drafts are advisory, not native assertions. SHA256 fields hash JSON string values; exact equality also checked.')


def initial_audit(run):
    """Require a real qualified origin, current or explicitly hashed source."""
    initial = read(run / 'shared_initial.json')
    stamp = read(run / 'shared_initial_freeze.json', {})
    protocol = read(run / 'protocol.json', {})
    reused = read(run / 'reused_source.json')
    continued = protocol.get('fresh_initial_call') is False
    source = previous.portable_path((reused or {}).get('source', '')).resolve() if continued else run
    source_valid = ROOT in source.parents and source.is_dir()
    integrity = previous.reused_integrity(reused) if continued and reused else None
    origin = previous.portable_path(stamp.get('origin', '')).resolve()
    inside = source_valid and source in origin.parents and origin.parent.parent == source / 'initial'
    copied_inputs = []
    if continued and source_valid:
        for rel in ('shared_initial.json', 'shared_initial_freeze.json',
                    'search/admitted_cases.json', 'search/strict_witnesses.json', 'search/corrected_comparison.json'):
            current, original = run / rel, source / rel
            copied_inputs.append(dict(path=rel, passed=current.is_file() and original.is_file()
                and read(current) == read(original)))
        current, original = run / 'axis_fifo.v', source / 'axis_fifo.v'
        copied_inputs.append(dict(path='axis_fifo.v', passed=current.is_file() and original.is_file()
            and digest(current) == digest(original)))
    call = read(origin / 'result.json', {}) if inside else {}
    candidate = read(origin / 'candidate.json') if inside else None
    decision = read(origin.parent / 'decision.json', {}) if inside else {}
    actual = base.candidate_sha(initial) if initial is not None else None
    return dict(passed=bool(inside and (not continued or (integrity or {}).get('passed'))
        and all(c['passed'] for c in copied_inputs)
        and (origin / 'attempt.json').is_file()
        and (origin / 'request.json').is_file() and call.get('status') == 'response_received'
        and candidate and initial and base.candidate_sha(candidate) == actual
        and stamp.get('hash') == actual and decision.get('qualified') is True),
        origin=str(origin), origin_inside_fresh_initial=inside and not continued,
        origin_inside_declared_initial=inside, fresh_initial_call=not continued,
        declared_source=str(source), reused_source_integrity=integrity,
        copied_inputs_match=copied_inputs,
        candidate_hash=actual, call_status=call.get('status'), qualification=decision,
        record_hashes={p.name: digest(p) for p in origin.glob('*.json')} if inside else {},
        scope='Actual attempt/request/response candidate identity and native qualification, current or explicitly hashed source; no full specification coverage claim.')


def reused_source_cost(run):
    """Read source cost only after the current model experiment is terminal."""
    reused = read(run / 'reused_source.json')
    if not reused:
        return None
    if read(run / 'outcome.json', {}).get('status') in (None, 'running'):
        raise ValueError('Cannot audit source costs while the current experiment is active')
    source = previous.portable_path(reused['source']).resolve()
    if ROOT not in source.parents or not source.is_dir():
        raise ValueError('Existing workspace source required')
    outcome = read(source / 'outcome.json', {})
    if outcome.get('status') in (None, 'running'):
        raise ValueError('Reused source must have a terminal outcome')
    # Only actual model and native command accounting is consulted. Source
    # independent results are never projected as this continuation's tests.
    files = base.artifacts(source)
    cost = base.cost_audit(source, files)
    planning = planning_audit(source, files, read(source / 'protocol.json', {}), cost)
    tracked = [p for p in files if p.name in ('attempt.json', 'request.json', 'response.raw.json', 'result.json',
        'transport_result.json', 'compile.json', 'execute.json', 'outcome.json', 'model_cost.json', 'diagnosis.json')
        and ('model_call' in p.parts or p.name in ('compile.json', 'execute.json', 'outcome.json', 'model_cost.json', 'diagnosis.json'))]
    return dict(source=source.relative_to(ROOT).as_posix(), outcome=outcome,
        cost=cost, by_purpose=planning['by_purpose'], diagnosis=read(source / 'diagnosis.json'),
        initial_and_search_cost={k: v for k, v in cost['by_phase'].items() if k in ('initial', 'search')},
        record_hashes={p.relative_to(source).as_posix(): digest(p) for p in tracked},
        scope='Historical source costs only, charged separately once. Source initial/search are reused, not new discoveries. No source independent result is a current independent result.')


def reused_response_audit(run, files):
    """Check syntax retries against original real responses, without execution."""
    import research17_model as model
    paths = sorted((p for p in files if p.name == 'reused_response.json'),
        key=lambda p: (p.parent.parent.parent.as_posix(), int(p.parent.parent.name.removeprefix('v'))))
    records = []
    current = read(run / 'shared_initial.json')
    declared_source = previous.portable_path(read(run / 'reused_source.json', {}).get('source', '')).resolve()
    for path in paths:
        archived = read(path)
        folder = path.parent
        source = previous.portable_path(archived['source']).resolve()
        safe = ROOT in source.parents and declared_source in source.parents
        checks = []
        if safe:
            for rel, expected in archived.get('hashes', {}).items():
                p = (source / rel).resolve()
                if source not in p.parents:
                    raise ValueError('Unsafe prior-response reference')
                actual = digest(p) if p.is_file() else None
                checks.append(dict(path=rel, expected=expected, actual=actual, passed=actual == expected))
        original = read(source / 'result.json', {}) if safe else {}
        raw_record = read(source / 'response.raw.json', {}) if safe else {}
        raw = (raw_record.get('message') or {}).get('content')
        try:
            decoded = json.loads(raw)
        except (ValueError, TypeError):
            decoded = None
        edit = read(source / 'model_edit.json') if safe else None
        source_valid = bool(safe and checks and all(c['passed'] for c in checks)
            and original == archived.get('original_call')
            and original.get('status') == 'response_received'
            and original.get('candidate_status') == 'interface_rejected'
            and (source / 'attempt.json').is_file()
            and not (source.parent / 'native').exists()
            and decoded and decoded == edit == archived.get('edit'))
        replay = read(folder / 'result.json', {})
        decision = read(folder.parent / 'decision.json', {})
        candidate = read(folder / 'candidate.json')
        main_is_core = folder.parent.parent == run / 'core' and replay.get('phase') == 'core_both_mechanisms'
        zero_calls = replay.get('status') == 'replayed_actual_prior_response' and replay.get('model_calls') == 0
        zero_calls &= not (folder / 'attempt.json').exists() and not (folder / 'request.json').exists()
        assembly_equal, assembly_error = None, None
        if candidate and decoded:
            try:
                expected = model.assemble(decoded, current, candidate.get('syntax_profile'))
                assembly_equal = expected == candidate
            except Exception as exc:
                assembly_equal, assembly_error = False, repr(exc)
        context = original.get('context_preflight') or {}
        delta, margin = context.get('observed_minus_rendered'), context.get('wrapper_margin_tokens')
        context_ok = (context.get('fits_with_output_reserve') is True and type(delta) is int
            and type(margin) is int and abs(delta) <= margin)
        passed = bool(source_valid and main_is_core and zero_calls and context_ok
            and (candidate is None or assembly_equal))
        records.append(dict(path=path.relative_to(run).as_posix(), source=str(source),
            passed=passed, original_response_verified=source_valid, source_hash_checks=checks,
            raw_response_equals_saved_edit=bool(decoded and decoded == edit == archived.get('edit')),
            candidate_equals_generic_assembly=assembly_equal, assembly_error=assembly_error,
            original_context_validated=context_ok, restricted_to_core=main_is_core,
            no_new_generation_attempt=zero_calls, accepted=decision.get('accepted'),
            recorded_status=replay.get('status'), actual_native_replay=(folder.parent / 'native').exists(),
            source_record_hashes={p.name: digest(p) for p in source.glob('*.json')} if safe else {}))
        if decision.get('accepted') and candidate:
            current = candidate
    expected_order = read(run / 'pending_interface_edits.json', {}).get('paths', [])
    normalized_expected = [str(previous.portable_path(p).resolve()) for p in expected_order]
    actual_order = [r['source'] for r in records]
    order_ok = actual_order == normalized_expected[:len(actual_order)]
    return dict(records=records, syntax_retry_operations=len(records), new_generation_calls=0,
        chronological_prefix_matches=order_ok,
        integrity_passed=all(r['passed'] for r in records) and order_ok,
        accepted_prior_response_versions=[r['path'] for r in records if r['accepted']],
        scope='Original real generation plus later syntax-capability replay; never a new LLM response. Original calls/tokens charged only in source. Reused proposals are restricted to core pilot, not four arms.')


def deduplicated_scope(test, dedup, name):
    projected = base.independent_scope(test, name, base.CORE_OBLIGATIONS)
    data = dedup.get(name)
    checked = bool(data and data.get('reconstruction_complete')
        and not data.get('inconsistent_duplicate_groups') and not data.get('malformed'))
    by = (data or {}).get('by_obligation', {})
    for ob in base.CORE_OBLIGATIONS:
        counts = by.get(ob) or {}
        checked &= bool(counts.get('detections', 0) > 0 and counts.get('triggers', 0) > 0
            and all(counts.get(k) == 0 for k in ('misses', 'unknown', 'false_positives')))
    return dict(passed=bool(projected['passed'] and checked), raw_projection=projected,
        deduplicated_evidence_checked=checked,
        scope='Finite first-attribution order_payload and drain_no_loss evidence only; later attribution unknown remains separate.')


def render(run, result):
    text = base.render(run, result).replace('scripts/research17_report.py', 'scripts/research19_report.py')
    text = text.replace('## 独立回放与范围', '## 独立回放原始计数（未去重）')
    if result['reused_response_audit']['records']:
        notice = ('本次 core 是跨运行重验：模型在来源运行真实生成表达式，升级前端后自动重放原响应，'
            '再执行原生验收；core 没有新增模型生成调用。四组 A–D 的模型调用另行统计，'
            '不能把 core 的修复结果替代 D 组结果，或据此声称两个机制优于基线。'
            '完整父案例通过仍未建立。\n\n')
        text = text.replace('## 实际修改轨迹', notice + '## 实际修改轨迹', 1)
    text = text.replace('初始与最终 SVA 均直接来自真实模型表达式及模型时序选择；通用组装器没有人工修正表达式。',
        '已经生成并保存的 SVA 来自真实模型表达式及模型时序选择；通用组装器没有人工修正表达式。未生成候选时下列代码为空，不计生成或执行成功。')
    default = 'wsl -- python3 scripts/research19_loop.py --out deliverables/research19_repro_new'
    command = result.get('execution_command')
    command = command.get('command') if isinstance(command, dict) else command
    text = text.replace('wsl -- python3 scripts/research17_loop.py --out deliverables/research17_closed_loop_20261016_r02', command or default)
    text = text.replace('在仓库根目录可执行同一实验入口（运行目录必须未使用）：',
        '以下为保存的启动命令（无记录时为入口示例）；复现必须将 --out 换成未使用目录：')
    continued = not result['fresh_initial_audit']['fresh_initial_call']
    lines = ['', '## 实验来源与数据边界', '',
        f"初始候选真实来源核验：`{result['fresh_initial_audit']['passed']}`。"
        + ('本轮复用已发生的真实初始生成和严格搜索，不计为本轮新生成或新发现；真实细化与新回放另计。' if continued else '本轮采用新鲜真实初始生成和搜索，未把复制记录计作新结果。'),
        f"初始生成范围：`{result['experimental_design_limits']['initial_generation_scope']}`。具体任务和可见背景以模型 request.json 为准。",
        '初始为受控局部候选时，不能把未覆盖义务称为全规格生成的自发遗漏。原生工具支持的表达式范围也不等于全部 SVA 语言。', '',
        '所有实际执行组冻结后只生成一个 core_independent 公共测试批次；未执行组不计为已冻结或已测试。'
        '旧实验中已读取的独立数据视为后续研究开发信息；本轮测试不得参与生成、搜索、选择或修改。'
        '时间顺序来自运行记录与代码，不构成外部预注册证明。', '',
        'A/C 若保留原候选且没有取得新缺口，接受仅表示保留已有保护，不能计作新漏报修复。'
        'A/B 的普通接受策略只验收最后一个开发 case；全部历史 replay 的计数和 gate 审计仍保留，'
        '但不参与这些组的接受。B/D 共享一次实际搜索，成本按真实执行一次计入。', '',
        '两个参数配置中相同 fault/obligation 属于一个失效机制；契约搜索不预设优于其他方法。'
        '单 property 时的候选分歧回退探索不能算作有效候选分歧算法对照。', '',
        '## 原生细化逐版结果', '',
        '| 组/版本 | 旧检出 | 旧漏报 | 新检出 | 新漏报 | 新误报 | 新 unknown | 接受 |',
        '|---|---:|---:|---:|---:|---:|---:|---|']
    for name, summary in [('core', result['core']), *result['arms'].items()]:
        for h in summary.get('history', []):
            before, after = h.get('before') or {}, h.get('after') or {}
            values = [before.get('detections'), before.get('misses'), after.get('detections'),
                after.get('misses'), after.get('false_positives'), after.get('unknown'),
                h.get('decision', {}).get('accepted')]
            lines.append(f"| {name}/v{h.get('iteration')} | " + ' | '.join(map(str, values)) + ' |')
    lines += ['', '各版模型 SVA 原文：', '']
    for proposal in result['model_proposals']:
        lines += [f"`{proposal['version']}`，来源类型 `{proposal['generation_kind']}`，"
            f"接受／资格记录：`{proposal['decision']}`。", '```systemverilog']
        lines += [a['property'] for a in proposal['candidate'].get('assertions', [])]
        lines += ['```', '']
    lines += ['## 四组实际机制比较', '',
        '以下只比较独立执行的 A–D，core pilot 不作为 D 的结果。普通反馈中保留原断言，'
        '不能等同于修复搜索取得的新漏报。实际模型调用包含规划与最终 SVA 生成。', '',
        '| 组 | 搜索证据 | 防退化门 | 实际模型调用 | 开发缺口 | 本轮新生成修复开发缺口 | 两义务独立结果 |',
        '|---|---|---|---:|---|---|---|']
    for name, item in result['arm_mechanism_comparison'].items():
        lines.append(f"| {name} | {item['search_enabled']} | {item['gate_enabled']} | "
            f"{item['actual_model_calls']} | {item['has_acquired_gap']} | "
            f"{item['current_run_generated_gap_repair']} | {item['independent_two_obligations']['passed']} |")
    arm_comparison = result['arm_comparison_conclusion']
    lines += ['', f"四组结论：`{arm_comparison['status']}`。四组冻结集合均与初始相同："
        f"`{arm_comparison['all_frozen_candidates_equal_initial']}`。", '']
    if arm_comparison['status'] == 'no_new_accepted_gap_repair_in_four_arms':
        lines += ['本次四组均未建立新增保护，不能以 core 的跨运行修复替代四组结果，'
            '也不能据此宣称搜索或防退化机制带来了最终断言性能提升。', '']
    for name, item in result['arm_mechanism_comparison'].items():
        lines.append(f"{name}：`{item['development_outcome']}`；"
            f"接口诊断 `{item['interface_errors']}`；门控原因 `{item['decision_reasons']}`。")
    lines += ['', '未执行组或缺失独立结果按未建立处理，不以零成本或零记录判定成功。'
        '搜索证据为实验处理，A/C 不应收到；上述运行设计不构成统计显著性或全局无退化保证。', '',
        '## 独立测试去重与义务分母', '',
        '从 case.json 的实际 depth、pipeline、rows 重建输入哈希，按输入哈希、RTL 变体、复位 epoch、周期、义务去重。'
        '同一 correct 输入随多种故障重复运行的成本全部保留；重复判定不一致转为 unknown。'
        '行数为义务采样行，不是独立 Bug 数。', '',
        '| 组 | 义务 | 满足行 | 违例行 | 检出 | 漏报 | 误报 | unknown | 触发行 |',
        '|---|---|---:|---:|---:|---:|---:|---:|---:|']
    notes = []
    for name, data in result['independent_deduplicated'].items():
        for ob, counts in data['by_obligation'].items():
            lines.append(f'| {name} | {ob} | ' + ' | '.join(str(counts[k]) for k in (
                'satisfied_oracle_rows', 'target_oracle_rows', 'detections', 'misses',
                'false_positives', 'unknown', 'triggers')) + ' |')
        notes.append(f"{name}：原始 {data['raw_rows']} 行，去重 {data['unique_rows']} 行，后续归因 unknown "
            f"{data['later_attribution_unknown_raw']} 条；{data['missed_obligation_rows']} 个漏报义务行对应 "
            f"{data['missed_events']} 个采样事件。事件数也不等于独立故障数。")
        notes += [f"漏报：{m['scenario_id']}，周期 {m['cycle']}，义务 {m['obligation']}。" for m in data['missed_event_details']]
    lines += ['', '\n\n'.join(notes), '', '## 各阶段实际成本', '',
        '| 阶段 | 模型调用 | 输入 tokens 已知小计 | 输出 tokens 已知小计 | usage 不可用 | 原生编译 | 原生执行 |',
        '|---|---:|---:|---:|---:|---:|---:|']
    for name, cost in result['cost']['by_phase'].items():
        lines.append('| ' + name + ' | ' + ' | '.join(str(cost[k]) for k in (
            'model_calls', 'prompt_tokens_known_subtotal', 'completion_tokens_known_subtotal',
            'usage_unavailable_calls', 'native_compile_calls', 'native_execute_calls')) + ' |')
    source_cost = result.get('reused_source_cost')
    if source_cost:
        lines += ['', '## 复用来源成本（单列，不计入本轮新调用）', '',
            f"来源：`{source_cost['source']}`，终态 `{source_cost['outcome'].get('status')}`。"
            f"输入内容核验：`{result['fresh_initial_audit']['reused_source_integrity']['passed']}`。", '',
            '| 来源阶段 | 模型调用 | 输入 tokens 已知小计 | 输出 tokens 已知小计 | usage 不可用 | 原生编译 | 原生执行 |',
            '|---|---:|---:|---:|---:|---:|---:|']
        for phase, values in [('来源全部已发生成本', source_cost['cost']['total']), *source_cost['initial_and_search_cost'].items()]:
            lines.append('| ' + phase + ' | ' + ' | '.join(str(values[k]) for k in (
                'model_calls', 'prompt_tokens_known_subtotal', 'completion_tokens_known_subtotal',
                'usage_unavailable_calls', 'native_compile_calls', 'native_execute_calls')) + ' |')
        lines += ['', 'initial/search 是来源总成本的子集，不再次相加。来源其他失败、取消及独立回放成本保留，'
            '但来源独立结果不计为本轮新独立测试。源码资格范围变化与旧运行之间不能作严格机制因果比较。', '']
        if source_cost.get('diagnosis'):
            lines += ['来源失败诊断：', '```json', json.dumps(source_cost['diagnosis'], ensure_ascii=False, indent=2), '```', '']
    lines += ['', '按实际 attempt 计费，失败和取消均保留，缺失终态用量保持不可用。模型计费金额不可用。'
        '独立测试每组成本可按 native_commands 中 core_independent/组 路径复核。', '']
    management = result['management_operations']
    context = result['context_preflight_audit']
    lines += [f"空提示模型加载管理操作 {management['management_requests']} 次，已知耗时 "
        f"{management['wall_seconds_known_subtotal']} 秒；不算 SVA 生成。"
        f"上下文预检 {context['tokenization_preflights']} 次，tokenizer 已知调用 "
        f"{context['tokenization_calls_known_subtotal']} 次，不算生成。"
        f"接受提案未通过上下文守卫：`{context['invalid_accepted_contexts']}`。", '',
        '## 真实规划调用与最终 SVA 调用', '',
        f"规划开关：`{result['contract_planning_audit']['enabled']}`。规划响应不会直接编译或接受；"
        '后续主生成请求仍提供完整 RTL，并原样引用真实规划响应。', '',
        '| 类型 | 实际调用 | 输入 tokens 已知小计 | 输出 tokens 已知小计 | usage 不可用 |',
        '|---|---:|---:|---:|---:|']
    for purpose, values in result['contract_planning_audit']['by_purpose'].items():
        lines.append('| ' + purpose + ' | ' + ' | '.join(str(values[k]) for k in (
            'model_calls', 'prompt_tokens_known_subtotal', 'completion_tokens_known_subtotal', 'usage_unavailable_calls')) + ' |')
    lines += ['', '两类调用已全部计入前述总成本，不重复相加；失败规划也计费。每轮修改最多包含规划和最终生成两次调用，'
        '迭代上限与实际模型请求数必须区分。', '',
        f"规划原文引用完整性：`{result['contract_planning_audit']['integrity_passed']}`；"
        f"不匹配的主请求：`{result['contract_planning_audit']['submitted_main_requests_missing_valid_exact_draft']}`。", '',
        '| 规划路径 | 模型状态 | 主生成已提交 | 原样引用核验 |', '|---|---|---|---|']
    for item in result['contract_planning_audit']['records']:
        lines.append(f"| {item['path']} | {item['status']} | {item['main_generation_submitted']} | {item['exact_raw_response_in_main_request']} |")
    diagnosis = result.get('diagnosis')
    if diagnosis:
        lines += ['', '## 已保存的失败诊断', '', '```json', json.dumps(diagnosis, ensure_ascii=False, indent=2), '```', '',
            '上述诊断保留原始实验请求和成本，不追认为已修复。接口失败后的反馈缺失不能算合格的证据驱动细化。']
    retried = result['reused_response_audit']
    if retried['records']:
        lines += ['', '## 历史真实响应的自动接口重验', '',
            f"语法能力重验 {retried['syntax_retry_operations']} 次，新模型生成调用 0 次。"
            f"来源引用、原始响应 JSON、编辑与通用组装一致性：`{retried['integrity_passed']}`。", '',
            '这是先前真实模型生成后，修复前端语法能力再继续原生执行和接受检查。'
            '不将重放声称为本轮新 LLM 生成，也不人工改写表达式。历史调用成本只在来源账目列一次。'
            '即使此次门控和独立验证成功，也只能称为跨运行的真实生成—前端修复—重新验收链；'
            '不能称为本轮新模型反馈后生成成功。旧提案仅提供给 core pilot，四组仍独立调用模型。', '',
            '| 重验路径 | 来源 | 新调用为零 | 原文及编辑匹配 | 候选组装匹配 | 接受 |',
            '|---|---|---|---|---|---|']
        for item in retried['records']:
            lines.append(f"| {item['path']} | {item['source']} | {item['no_new_generation_attempt']} | "
                f"{item['raw_response_equals_saved_edit']} | {item['candidate_equals_generic_assembly']} | {item['accepted']} |")
    lines += ['',
        '## 验收范围', '',
        '| 要求 | 产物 | 状态依据 |', '|---|---|---|',
        ('| 复用真实初始生成 | reused_source.json、来源 initial/v*/model_call | 来源身份、资格及输入哈希；本轮非新生成 |' if continued else
         '| 新鲜真实生成 | initial/v*/model_call、shared_initial.json | fresh_initial_audit，不以代码存在代替运行 |'),
        ('| 复用原生契约搜索 | 来源 search、当前 strict_witnesses.json | 重验五条件及去重缺口键；本轮非新发现 |' if continued else
         '| 原生契约搜索 | search/strict_witnesses.json、corrected_comparison.json | 五条件及去重缺口键 |'),
        '| 自动细化与防退化 | core/v*/native、decision.json | 本轮目标、历史保护、触发和 unknown 门控 |',
        '| 复杂 FIFO | case.json、原生波形及事务记录 | 参数与真实握手参考模型 |',
        '| 独立测试 | core_independent | 冻结哈希、未参与反馈、逐义务计数 |',
        '| 四组消融 | arms/A..D | 未执行组明确 not_executed |', '',
        '两义务链通过仍不能代表所有五义务或父 Bug 整体通过。stat 与原始 FIFO presented 保持 unknown，'
        '人工输出边界故障按一个工程父案例计。未知状态及未找到见证均不删除。', '']
    return text + '\n'.join(lines)


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
    freezes = base.freeze_audit(run)
    archived = read(out / 'results.json', {})
    linked_checks = []
    source_integrity = None
    if read(run / 'reused_source.json'):
        source_integrity = previous.reused_integrity(read(run / 'reused_source.json'))
        source_record = archived.get('reused_source_cost') or {}
        source = previous.portable_path(source_record.get('source', '')).resolve()
        for rel, expected in source_record.get('record_hashes', {}).items():
            path = (source / rel).resolve()
            if ROOT not in source.parents or source not in path.parents:
                raise ValueError('Unsafe reused cost record path')
            actual = digest(path) if path.is_file() else None
            linked_checks.append(dict(path=str(path), expected=expected, actual=actual, passed=actual == expected))
    for record in archived.get('reused_response_audit', {}).get('records', []):
        source = previous.portable_path(record['source']).resolve()
        for rel, expected in record.get('source_record_hashes', {}).items():
            path = (source / rel).resolve()
            if ROOT not in source.parents or source not in path.parents:
                raise ValueError('Unsafe retried-response record path')
            actual = digest(path) if path.is_file() else None
            linked_checks.append(dict(path=str(path), expected=expected, actual=actual, passed=actual == expected))
    # A failed run may never have produced a candidate: seal integrity still
    # can pass, while the result contains no verified chain or candidate claim.
    result = dict(passed=all(c['passed'] for c in checks) and not extra
        and all(f['passed'] for f in freezes)
        and (source_integrity is None or source_integrity['passed'])
        and all(c['passed'] for c in linked_checks), checked=len(checks), checks=checks,
        unmanifested_files=extra, freezes=freezes,
        reused_source_integrity=source_integrity, linked_cost_checks=linked_checks,
        scope='Artifact and any existing freeze integrity, not experiment success.')
    dump(out / 'verification.json', result)
    print(json.dumps({k: v for k, v in result.items() if k not in ('checks', 'freezes', 'linked_cost_checks', 'reused_source_integrity')}))
    if not result['passed']:
        raise SystemExit(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    run = args.run.resolve()
    if ROOT not in run.parents or not run.is_dir():
        raise ValueError('Existing workspace run required')
    outcome = read(run / 'outcome.json')
    if not outcome or outcome.get('status') in (None, 'running'):
        raise SystemExit('Run has no terminal outcome; independent results were not read.')
    out = run / 'report'
    out.mkdir(exist_ok=True)
    if args.verify:
        return verify(run, out)
    files = base.artifacts(run)
    freezes = base.freeze_audit(run)
    cost = base.cost_audit(run, files)
    test = base.test_audit(run, 'core_independent', freezes)
    core = read(run / 'core/summary.json', {})
    witnesses = read(run / 'search/strict_witnesses.json', [])
    protocol = read(run / 'protocol.json', {})
    context = previous.context_audit(run, files)
    planning = planning_audit(run, files, protocol, cost)
    retries = reused_response_audit(run, files)
    initial = initial_audit(run)
    dedup = {}
    for name in (test.get('summary') or {}):
        ledger = read(run / 'core_independent' / name / 'independent_ledger.json')
        if ledger is not None:
            dedup[name] = previous.deduplicated_counts(ledger, run / 'core_independent' / name)
    projected = deduplicated_scope(test, dedup, 'core')
    chain = bool(core.get('resolved') and core.get('has_acquired_gap') and projected['passed']
        and initial['passed'] and planning['integrity_passed'] and retries['integrity_passed']
        and any(w.get('valid') for w in witnesses)
        and not context['invalid_accepted_contexts'] and all(f['passed'] for f in freezes)
        and any(f['scope'] == 'core' and f['passed'] for f in freezes)
        and any(h.get('decision', {}).get('accepted') and h['decision'].get('gate_enforced')
                for h in core.get('history', [])))
    proposals = []
    for candidate_path in files:
        if candidate_path.name == 'candidate.json' and candidate_path.parent.name == 'model_call':
            candidate_call = read(candidate_path.parent / 'result.json', {})
            proposals.append(dict(version=candidate_path.parent.parent.relative_to(run).as_posix(),
                candidate=read(candidate_path), decision=read(candidate_path.parent.parent / 'decision.json'),
                generation_kind='prior_real_response_syntax_retry' if (candidate_path.parent / 'reused_response.json').is_file()
                    else 'current_run_model_response', call_status=candidate_call.get('status'),
                generation_attempt_present=(candidate_path.parent / 'attempt.json').is_file()))
    result = dict(status=outcome['status'], generated_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        protocol=protocol, outcome=outcome, execution_command=read(run / 'execution.command.json'),
        fresh_initial_audit=initial, initial_candidate=read(run / 'shared_initial.json'),
        core_candidate=read(run / 'core/frozen_candidate.json'), core=core, model_proposals=proposals,
        arms={a: read(run / 'arms' / a / 'summary.json', {'status': 'not_executed'}) for a in 'ABCD'},
        strict_witnesses=witnesses, search_comparison=read(run / 'search/corrected_comparison.json'),
        independent={'core_independent': test}, independent_deduplicated=dedup,
        freeze_checks=freezes, cost=cost, context_preflight_audit=context,
        contract_planning_audit=planning, diagnosis=read(run / 'diagnosis.json'),
        reused_response_audit=retries,
        reused_source_cost=reused_source_cost(run),
        management_operations=previous.management_audit(run),
        experimental_design_limits=dict(initial_generation_scope=protocol.get('initial_generation_scope', protocol.get('core', 'unavailable; inspect initial request')),
            ordinary_keep='Retention without a new acquired gap is not a repaired false negative.',
            unguarded_acceptance='A/B admit on the last development case; full historical replay is observational.',
            generalization='Single engineering parent; finite first-attribution evidence; no global guarantee.'),
        core_chain=dict(status=('verified_two_obligations_after_prior_real_response_frontend_retry'
            if retries['accepted_prior_response_versions'] else 'verified_for_two_obligations_on_recorded_scope')
            if chain else 'not_established',
            passed=chain, independent_two_obligations=projected,
            generation_path='cross_run_real_generation_followed_by_frontend_retry' if retries['accepted_prior_response_versions'] else 'current_run_model_refinement',
            new_llm_refinement_success=bool(chain and not retries['accepted_prior_response_versions'])),
        whole_parent_case=dict(passed=False, status='not_established', required_obligations=list(base.ALL_OBLIGATIONS),
            original_historical_fifo_bug='unknown', stat='unknown', engineering_parent_count=1))
    result['accepted_obligation_mapping'] = {'core': base.accepted_mapping(run, 'core', core),
        **{a: base.accepted_mapping(run, 'arms/' + a, result['arms'][a]) for a in 'ABCD'}}
    result['arm_mechanism_comparison'] = {}
    for name, summary in result['arms'].items():
        arm_config = (protocol.get('arms') or {}).get(name, {})
        attempts = [c for c in cost['model_calls'] if c['phase'] == 'arms/' + name]
        actual_new_acceptance = any(h.get('decision', {}).get('accepted')
            and h.get('call', {}).get('status') == 'response_received' for h in summary.get('history', []))
        frozen = read(run / 'arms' / name / 'frozen_candidate.json')
        changed = bool(frozen and base.candidate_sha(frozen) != base.candidate_sha(result['initial_candidate']))
        errors = [h.get('call', {}).get('candidate_error') for h in summary.get('history', [])
            if h.get('call', {}).get('candidate_error')]
        reasons = [r.get('kind') for h in summary.get('history', [])
            for r in h.get('decision', {}).get('reasons', [])]
        development_outcome = ('not_executed' if summary.get('status') == 'not_executed' else
            'existing_candidate_retained_without_new_gap' if summary.get('resolved') and not summary.get('has_acquired_gap') else
            'acquired_gap_unrepaired' if summary.get('has_acquired_gap') and not summary.get('resolved') else
            'proposal_interface_rejected' if errors and not summary.get('resolved') else
            'acquired_gap_repaired_on_development' if summary.get('resolved') and summary.get('has_acquired_gap') else
            'not_established')
        result['arm_mechanism_comparison'][name] = dict(status=summary.get('status', 'executed'),
            search_enabled=arm_config.get('search'), gate_enabled=arm_config.get('gate'),
            actual_model_calls=len(attempts), by_purpose=planning['by_phase_and_purpose'].get('arms/' + name),
            has_acquired_gap=summary.get('has_acquired_gap'), candidate_changed=changed,
            development_outcome=development_outcome, interface_errors=errors, decision_reasons=reasons,
            current_run_generated_gap_repair=bool(summary.get('resolved') and summary.get('has_acquired_gap')
                and actual_new_acceptance and changed),
            independent_two_obligations=deduplicated_scope(test, dedup, name))
    all_executed = all(a.get('status') != 'not_executed' for a in result['arm_mechanism_comparison'].values())
    no_repairs = all(not a['current_run_generated_gap_repair'] for a in result['arm_mechanism_comparison'].values())
    result['arm_comparison_conclusion'] = dict(
        status='no_new_accepted_gap_repair_in_four_arms' if all_executed and no_repairs else 'assess_per_arm_finite_results',
        all_four_executed=all_executed,
        all_frozen_candidates_equal_initial=all_executed and all(not a['candidate_changed'] for a in result['arm_mechanism_comparison'].values()),
        scope='Core pilot is excluded from four-arm mechanism effectiveness. No statistical or global superiority claim.')
    dump(out / 'results.json', result)
    dump(out / 'cost/results.json', dict(physical=cost, by_purpose=planning['by_purpose'],
        by_phase_and_purpose=planning['by_phase_and_purpose'], management=result['management_operations'], context=context,
        reused_historical=result['reused_source_cost']))
    dump(out / 'freeze_checks.json', freezes)
    (out / 'REPORT.md').write_text(render(run, result), encoding='utf-8')
    shutil.copy2(__file__, out / 'report_script_snapshot.py')
    manifest = {p.relative_to(run).as_posix(): digest(p) for p in files}
    dump(out / 'manifest.json', manifest)
    dump(out / 'source_and_rtl_hashes.json', {k: v for k, v in manifest.items() if Path(k).suffix in ('.py', '.sv', '.v')})
    print(json.dumps(dict(status=result['status'], core_chain=chain, cost=cost['total'], report=str(out / 'REPORT.md'))))


if __name__ == '__main__':
    main()
