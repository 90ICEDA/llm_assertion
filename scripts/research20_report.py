"""Terminal-only audit of fresh progressive FIFO assertion refinement.

Writes RUN/report only. No model calls, native executions, or test feedback.
The initial independent comparator uses shared_initial_freeze, not arms/initial.
"""
from __future__ import annotations

import argparse
import datetime
import json
from pathlib import Path
import shutil

import research17_report as base
import research18_report as prior
import research19_report as audit19
from research15_acceptance import inspect

ROOT = base.ROOT
read, dump, digest = base.read, base.dump, base.digest
TARGET_OBLIGATIONS = ('order_payload', 'drain_no_loss', 'no_unsolicited_output', 'reset_cancellation')


def response_content(record):
    """Support normalized Ollama or compatible chat completion envelopes."""
    message = record.get('message') or {}
    if isinstance(message.get('content'), str):
        return message['content'], 'normalized_message_content'
    choices = record.get('choices') or []
    if choices and isinstance(choices[0], dict):
        text = (choices[0].get('message') or {}).get('content')
        if isinstance(text, str):
            return text, 'compatible_choices_first_message_content'
    return None, 'unavailable'


def response_artifact(folder):
    """Verify a remote assembled body against saved upstream events/JSON."""
    folder = Path(folder)
    local = folder / 'response.raw.json'
    if local.is_file():
        content, envelope = response_content(read(local, {}))
        return content, dict(envelope=envelope, source='response.raw.json',
            integrity_passed=isinstance(content, str), remote_reconstruction=False)
    assembled_path = folder / 'response.assembled.json'
    assembled = read(assembled_path, {})
    content, _ = response_content(assembled)
    events_path, server_path, bytes_path = (folder / n for n in (
        'response.events.jsonl', 'response.server.json', 'response.stream.raw'))
    events, raw_events, errors = [], [], []
    source = 'unavailable'
    raw_matches, terminal = False, False
    try:
        if events_path.is_file():
            source = 'response.events.jsonl'
            events = [json.loads(line) for line in events_path.read_text(encoding='utf-8').splitlines() if line.strip()]
            data_lines = []
            if bytes_path.is_file():
                for line in bytes_path.read_text(encoding='utf-8').splitlines():
                    if line.startswith('data:'):
                        data_lines.append(line[5:].lstrip())
                    elif line == '' and data_lines:
                        data = '\n'.join(data_lines); data_lines = []
                        if data == '[DONE]':
                            terminal = True
                            break
                        raw_events.append(json.loads(data))
                raw_matches = raw_events == events
        elif server_path.is_file():
            source = 'response.server.json'
            events = [read(server_path)]
            if bytes_path.is_file():
                raw_matches = json.loads(bytes_path.read_bytes()) == events[0]
    except (ValueError, TypeError, UnicodeError) as exc:
        errors.append(type(exc).__name__)
    rebuilt, usage, finish = '', None, None
    for event in events:
        if not isinstance(event, dict):
            errors.append('non_object_event'); continue
        if event.get('usage') is not None:
            usage = event['usage']
        for choice in event.get('choices', []):
            if choice.get('index', 0) != 0:
                continue
            text = (choice.get('delta', choice.get('message', {})) or {}).get('content')
            if isinstance(text, str):
                rebuilt += text
            if choice.get('finish_reason') is not None:
                finish = choice['finish_reason']
    if source == 'response.server.json':
        terminal = finish is not None
    service = assembled.get('service_done') or {}
    exact = isinstance(content, str) and rebuilt == content
    passed = bool(source != 'unavailable' and raw_matches and exact and not errors
        and service.get('terminal_received') == terminal and service.get('finish_reason') == finish)
    return content, dict(envelope='locally_assembled_remote_first_choice', source=source,
        representation=assembled.get('representation'), remote_reconstruction=True,
        integrity_passed=passed, original_bytes_match_saved_events=raw_matches,
        reconstructed_content_matches=exact, event_count=len(events), errors=errors,
        terminal_marker_observed=terminal, finish_reason=finish,
        recorded_terminal_matches=service.get('terminal_received') == terminal,
        provider_usage_original=usage, assembled_usage_matches=service.get('usage') == usage,
        record_hashes={p.name: digest(p) for p in (assembled_path, events_path, server_path, bytes_path) if p.is_file()},
        scope='Assembled JSON is explicitly a local representation, not an upstream envelope. Bytes and original events/JSON reconstruct the content; completion/API status is checked separately.')


def direct_property_audit(edit, candidate, current):
    """Check full property text through the existing syntactic normalizer."""
    from research15_native_interface import unparen
    if not isinstance(edit, dict):
        return dict(format='unavailable', passed=None, records=[])
    items = edit.get('assertions') or []
    direct = [(i, a) for i, a in enumerate(items) if isinstance(a, dict) and 'property' in a]
    if not direct:
        return dict(format='keep' if edit.get('operation') == 'keep' else 'split_expression', passed=None, records=[])
    offset = len((current or {}).get('assertions', [])) if edit.get('operation') == 'add' else 0
    if edit.get('operation') == 'replace_one':
        ids = [a.get('id') for a in (current or {}).get('assertions', [])]
        offset = ids.index(edit.get('assertion_id')) if edit.get('assertion_id') in ids else len(ids)
    records = []
    for index, item in direct:
        asserted = (candidate or {}).get('assertions', [])
        actual = asserted[offset + index] if offset + index < len(asserted) else {}
        raw = item['property']
        normalized = unparen(raw) if isinstance(raw, str) else None
        labels = item.get('obligation')
        labels = labels if isinstance(labels, list) else [labels]
        records.append(dict(index=index, raw_property=raw, normalized_property=normalized,
            candidate_property=actual.get('property'), exact_raw_match=raw == actual.get('property'),
            normalized_text_match=normalized is not None and normalized == actual.get('property'),
            obligation_labels_match=actual.get('obligations') == labels))
    return dict(format='direct_property', passed=all(r['normalized_text_match'] and r['obligation_labels_match'] for r in records)
        if candidate is not None else None, records=records,
        scope='Only existing normalizer trimming and redundant outer parentheses removal allowed; implication/predicate text is not reconstructed or rewritten.')


def extended_cost_audit(run, files):
    """Preserve provider metadata without double charging normalized usage."""
    result = base.cost_audit(run, files)
    for call in result['model_calls']:
        folder = (run / call['path']).parent
        request = read(folder / 'request.json', {})
        final = read(folder / 'result.json', {})
        transport = read(folder / 'transport_result.json', {})
        raw = read(folder / 'response.raw.json', {})
        assembled = read(folder / 'response.assembled.json', {})
        _, provenance = response_artifact(folder)
        call['request_configuration'] = {k: request[k] for k in ('model', 'options', 'temperature',
            'max_tokens', 'max_completion_tokens', 'top_p', 'seed', 'presence_penalty',
            'frequency_penalty', 'stream', 'response_format', 'format') if k in request}
        call['sampling_parameter_location'] = 'options' if isinstance(request.get('options'), dict) else 'top_level_request_fields'
        call['model_digest'] = final.get('digest', transport.get('digest'))
        call['model_digest_status'] = 'unavailable' if call['model_digest'] in (None, 'unavailable') else 'recorded'
        call['provider_returned_model'] = raw.get('model', transport.get('actual_server_model', transport.get('provider_model')))
        usage = transport.get('provider_usage', transport.get('usage', raw.get('usage',
            (assembled.get('service_done') or {}).get('usage'))))
        call['provider_usage_original'] = usage
        call['provider_usage_accounting'] = 'Source detail only; normalized prompt_tokens/completion_tokens already counted once in physical totals.'
        call['response_provenance'] = provenance
    result['accounting'] = ('Current run physical attempt/compile/execute records, including failure and compile smoke. '
        'Provider usage metadata is retained but never added again to normalized token totals. No source/pilot/arm costs imported. '
        'No recorded final usage means unavailable, not zero total. Monetary cost unavailable.')
    result['model_response_outcomes'] = dict(
        complete_model_responses=sum(c['status'] == 'response_received' for c in result['model_calls']),
        incomplete_or_failed_responses=sum(c['status'] != 'response_received' for c in result['model_calls']),
        scope='API request attempts are not automatically successful generation; interface/native acceptance is separate again.')
    return result


def initial_expression_audit(run):
    from research20_model import assemble
    stamp = read(run / 'shared_initial_freeze.json', {})
    folder = prior.portable_path(stamp.get('origin', '')).resolve()
    if run not in folder.parents:
        return dict(passed=False, status='initial_origin_unavailable')
    raw, provenance = response_artifact(folder)
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        parsed = None
    edit = read(folder / 'model_edit.json')
    candidate = read(run / 'shared_initial.json')
    direct = direct_property_audit(parsed, candidate, None)
    assembled, error = None, None
    if parsed is not None and candidate is not None:
        try:
            assembled = assemble(parsed, None) == candidate
        except Exception as exc:
            assembled, error = False, repr(exc)
    return dict(passed=bool(provenance['integrity_passed'] and parsed is not None and parsed == edit and assembled
            and (direct['format'] != 'direct_property' or direct['passed'])),
        raw_json_matches_saved_edit=parsed is not None and parsed == edit,
        candidate_equals_model_edit_assembly=assembled, assembly_error=error,
        direct_property_preservation=direct, response_provenance=provenance)


def initial_attempts_audit(run):
    from research20_model import assemble
    records = []
    for version in sorted((run / 'initial').glob('v*'), key=lambda p: int(p.name[1:])):
        folder = version / 'model_call'
        decision = read(version / 'decision.json', {})
        call = read(folder / 'result.json', decision.get('call') or {})
        raw, provenance = response_artifact(folder)
        try:
            parsed = json.loads(raw)
        except (ValueError, TypeError):
            parsed = None
        edit = read(folder / 'model_edit.json')
        candidate = read(folder / 'candidate.json')
        exact, error = None, None
        if parsed is not None and candidate is not None:
            try:
                exact = assemble(parsed, None) == candidate
            except Exception as exc:
                exact, error = False, repr(exc)
        records.append(dict(version=version.relative_to(run).as_posix(), call=call, decision=decision,
            actual_generation_attempt=(folder / 'attempt.json').is_file(), candidate=candidate, edit=edit,
            native_result_present=(version / 'native/result.json').is_file(),
            response_provenance=provenance, raw_json_matches_saved_edit=parsed is not None and parsed == edit,
            candidate_equals_model_edit_assembly=exact, assembly_error=error,
            direct_property_preservation=direct_property_audit(parsed, candidate, None)))
    return records


def initial_provenance(run):
    """Fresh generation or explicitly hashed accepted-core continuation."""
    reused = read(run / 'reused_core_source.json')
    if reused is None:
        source = audit19.initial_audit(run)
        source['generation_origin'] = 'current_run_real_initial_generation'
        return source, initial_expression_audit(run), None
    source = prior.portable_path(reused.get('source', '')).resolve()
    if ROOT not in source.parents or not source.is_dir() or source == run:
        raise ValueError('Invalid accepted-core source')
    outcome = read(source / 'outcome.json', {})
    if outcome.get('status') in (None, 'running'):
        raise ValueError('Accepted-core source must be terminal')
    if (source / 'reused_core_source.json').exists():
        raise ValueError('Nested accepted-core continuation needs explicit recursive audit')
    checks = []
    for rel, expected in reused.get('files', {}).items():
        path = (source / rel).resolve()
        if source not in path.parents or 'core_independent' in path.relative_to(source).parts:
            raise ValueError('Unsafe or independent-test accepted-core source input')
        actual = digest(path) if path.is_file() else None
        checks.append(dict(path=rel, expected=expected, actual=actual, passed=actual == expected))
    original_freeze = read(source / 'core/freeze.json', {})
    original_initial_freeze = read(source / 'shared_initial_freeze.json', {})
    source_candidate = read(source / 'core/frozen_candidate.json')
    starting_candidate = read(run / 'shared_initial.json')
    starting_freeze = read(run / 'shared_initial_freeze.json', {})
    candidate_sha = base.candidate_sha(source_candidate) if source_candidate is not None else None
    identities = dict(source_files=bool(checks) and all(c['passed'] for c in checks),
        source_freeze_matches=reused.get('source_freeze') == original_freeze,
        source_original_initial_freeze_matches=reused.get('source_initial_freeze') == original_initial_freeze,
        source_frozen_hash_matches=bool(candidate_sha and original_freeze.get('candidate_sha256') == candidate_sha),
        reused_candidate_matches=bool(source_candidate and starting_candidate == source_candidate),
        current_starting_hash_matches=bool(candidate_sha and starting_freeze.get('hash') == candidate_sha),
        starting_origin_matches=prior.portable_path(starting_freeze.get('origin', '')).resolve() == source / 'core',
        explicitly_reused=starting_freeze.get('reused_accepted_set') is True)
    original_initial = audit19.initial_audit(source)
    original_expression = initial_expression_audit(source)
    original_core = read(source / 'core/summary.json', {})
    original_trace = model_trace_audit(source, original_core)
    source_missing = missing_evidence_audit(source)
    passed = bool(all(identities.values()) and original_initial['passed'] and original_expression['passed']
        and original_trace['accepted_integrity_passed'] and original_trace['final_candidate_equals_last_accepted'])
    record = dict(source=source.relative_to(ROOT).as_posix(), outcome=outcome, passed=passed,
        identity_checks=identities, source_file_checks=checks, original_initial_source=original_initial,
        original_initial_expression=original_expression, original_core=original_core,
        original_model_trace=original_trace, original_missing_evidence=source_missing,
        source_independent_read=False,
        scope='Source original real generation and accepted edits verified through development records only. Starting set is reused accepted core, not a new initial response. Source independent outcomes never used for continuation.')
    provenance = dict(passed=passed, generation_origin='reused_accepted_source_core',
        source=str(source), current_initial_generation_calls=0, source_candidate_sha256=candidate_sha,
        identity_checks=identities,
        scope='This run starts from the explicitly frozen source accepted set; no new initial generation credit.')
    expression = dict(passed=passed, generation_origin='reused_accepted_source_core',
        source_original_initial=original_expression,
        source_accepted_edits_match=original_trace['accepted_integrity_passed'])
    return provenance, expression, record


def source_cost_accounting(run, reused):
    if reused is None:
        return None
    if read(run / 'outcome.json', {}).get('status') in (None, 'running'):
        raise ValueError('Source cost accounting only after current run ends')
    source = prior.portable_path(reused['source']).resolve()
    cost = extended_cost_audit(source, base.artifacts(source))
    return dict(source=reused['source'], physical=cost,
        accounting='Historical source costs kept separate. Never added to current physical attempts; campaign aggregation must count each run once. Source independent cost is accounting only, not current test results.')


def independent_audit(run, freezes):
    summary = read(run / 'core_independent/summary.json')
    split = read(run / 'core_independent/split.json')
    if summary is None:
        return dict(status='not_completed', summary=None, split=split, all_frozen_hashes_match=False)
    checks = []
    for name, expected in (split or {}).get('hashes', {}).items():
        scope = {'core': 'core', 'initial': 'shared_initial'}.get(name)
        match = next((f for f in freezes if f['scope'] == scope), {})
        checks.append(dict(candidate=name, freeze_scope=scope, expected=expected,
            actual=match.get('actual'), passed=bool(match.get('passed') and match.get('actual') == expected)))
    return dict(status='completed', summary=summary, split=split, freeze_matches=checks,
        all_frozen_hashes_match=bool(checks) and set(summary) == {'core', 'initial'}
            and set((split or {}).get('hashes', {})) == {'core', 'initial'} and all(c['passed'] for c in checks),
        independence='One shared batch created after final freeze; initial hash checked against shared_initial_freeze. No test used for generation or selection. External preregistration not established.')


def scope(test, deduplicated, name, obligations):
    raw = base.independent_scope(test, name, obligations)
    data = deduplicated.get(name) or {}
    detail = {o: data.get('by_obligation', {}).get(o) for o in obligations}
    valid = bool(data.get('reconstruction_complete') and not data.get('malformed')
        and not data.get('inconsistent_duplicate_groups'))
    for counts in detail.values():
        valid &= bool(counts and counts.get('detections', 0) > 0 and counts.get('triggers', 0) > 0
            and all(counts.get(k) == 0 for k in ('misses', 'unknown', 'false_positives')))
    return dict(passed=bool(raw['passed'] and valid), raw=raw, deduplicated=detail,
        scope='Finite first-attribution target obligations only. Coverage-only stability evidence cannot satisfy target detection.')


def model_trace_audit(run, core):
    """Recompute assembly only; never change candidates or execute them."""
    from research20_model import assemble
    if read(run/'protocol.json', {}).get('boundary_replace'):
        from research26_model import replace_one as assemble
    current = read(run / 'shared_initial.json')
    traces = []
    for h in core.get('history', []):
        version = run / 'core' / f"v{h['iteration']}"
        folder = version / 'model_call'
        call = read(folder / 'result.json', h.get('call') or {})
        candidate = read(folder / 'candidate.json')
        edit = read(folder / 'model_edit.json')
        raw, provenance = response_artifact(folder)
        try:
            parsed = json.loads(raw)
        except (ValueError, TypeError):
            parsed = None
        genuine = bool((folder / 'attempt.json').is_file() and (folder / 'request.json').is_file()
            and call.get('status') == 'response_received')
        exact, error = None, None
        if candidate is not None and parsed is not None:
            try:
                exact = assemble(parsed, current) == candidate
            except Exception as exc:
                exact, error = False, repr(exc)
        accepted = h.get('decision', {}).get('accepted') is True
        attempted = (folder / 'attempt.json').is_file()
        preflight = read(version / 'context_preflight/result.json')
        direct = direct_property_audit(parsed, candidate, current)
        traces.append(dict(version=version.relative_to(run).as_posix(), history=h,
            call=call, generation_attempt_present=attempted, context_preflight=preflight,
            rejected_before_generation=bool(not attempted and preflight
                and preflight.get('fits_with_output_reserve') is False),
            real_current_run_response=genuine, raw_json_matches_saved_edit=parsed is not None and parsed == edit,
            candidate_equals_model_edit_assembly=exact, assembly_error=error,
            accepted_integrity_passed=bool(genuine and provenance['integrity_passed'] and parsed == edit and exact
                and (direct['format'] != 'direct_property' or direct['passed'])) if accepted else None,
            response_provenance=provenance, direct_property_preservation=direct,
            candidate=candidate, edit=edit, accepted=accepted,
            native_result_present=(version / 'native/result.json').is_file(),
            model_record_hashes={p.name: digest(p) for p in folder.glob('*.json')}))
        if accepted and candidate:
            current = candidate
    frozen = read(run / 'core/frozen_candidate.json')
    return dict(records=traces,
        accepted_integrity_passed=all(t['accepted_integrity_passed'] for t in traces if t['accepted'])
            if any(t['accepted'] for t in traces) else None,
        acceptance_audit_status='checked' if any(t['accepted'] for t in traces) else 'no_accepted_edit',
        final_candidate_equals_last_accepted=frozen is not None and current == frozen,
        accepted_new_target_edits=sum(t['accepted'] and not t['history'].get('coverage_only') for t in traces),
        accepted_coverage_only_edits=sum(t['accepted'] and t['history'].get('coverage_only') for t in traces),
        scope='Real current-run raw JSON and generic assembly checked. Obligation labels alone do not demonstrate detection.')


def missing_evidence_audit(run):
    before = read(run / 'core/before/result.json', {})
    group = before.get('group') or {}
    info = inspect(group.get('ledger', []))
    recorded = read(run / 'search/validated_missing_evidence.json', {}).get('witnesses', [])
    cases = {c['id']: (i, c) for i, c in enumerate(read(run / 'development_plan.json', []))}
    records = []
    for key in sorted(info['misses']):
        row = info['rows'][key]
        oracle = row.get('oracle') or {}
        assertions = row.get('native', {}).get('assertions', [])
        valid = bool(before.get('healthy') and oracle.get('legality') == 'legal'
            and oracle.get('paired_control_pass') is True
            and oracle.get('identical_input_handshakes') is True
            and oracle.get('verdict') == 'violated' and oracle.get('validator') == 'independent_fifo_port_history_queue')
        alignment = []
        case_info = cases.get(row.get('scenario_id'))
        if case_info:
            index, case = case_info
            folder = run / 'core/before' / f'case_{index}'
            fixed = read(folder / 'correct/oracle.json', {})
            mutant = read(folder / case['mode'] / 'oracle.json', {})
            ids = {v['transaction_id'] for v in row.get('oracle_violation', []) if v.get('transaction_id')}
            for v in row.get('oracle_violation', []):
                ids.update(v.get('outstanding', []))
            for tx in mutant.get('transactions', []):
                if tx.get('transaction_id') not in ids:
                    continue
                paired = next((t for t in fixed.get('transactions', []) if t['transaction_id'] == tx['transaction_id']), None)
                alignment.append(dict(buggy=tx, fixed=paired, accepted_match=bool(paired and all(
                    paired.get(k) == tx.get(k) for k in ('accept_cycle', 'data', 'epoch')))))
        records.append(dict(evidence_id=key, valid=valid, gap_class=[row.get('variant'), row.get('obligation')],
            scenario_id=row.get('scenario_id'), cycle=row.get('cycle'), epoch=row.get('epoch'),
            obligation=row.get('obligation'), variant=row.get('variant'), oracle=oracle,
            independent_violation=row.get('oracle_violation'), source_directory=row.get('source_directory'),
            aligned_transactions=alignment,
            parameters={k: case_info[1][k] for k in ('depth', 'pipeline')} if case_info else None,
            miss_subtype='no_assertion_mapped' if not assertions else 'triggered_but_insufficient'
                if any(a.get('trigger') for a in assertions) else 'mapped_but_not_triggered', native=row.get('native')))
    return dict(status='development_replay_checked' if group.get('ledger') else 'not_executed',
        records=records, confirmed_missing_rows=sum(r['valid'] for r in records),
        unique_gap_classes=[list(k) for k in sorted({tuple(r['gap_class']) for r in records if r['valid']})],
        archived_missing_rows_match=recorded == [info['rows'][k] for k in sorted(info['misses'])],
        unknown_rows=len(info['unknown']), malformed=info['errors'],
        scope='Actual paired ledger and independent port-history queue. Dedup fault+obligation, not seed/parameter variations. Shared reset events may violate multiple obligations; these are not independent parent Bugs.')


def source_audit(run):
    expected = read(run / 'source_snapshot/hashes.json', {})
    checks = []
    for name, value in expected.items():
        path = (run / 'source_snapshot' / name).resolve()
        if (run / 'source_snapshot').resolve() not in path.parents:
            raise ValueError('Unsafe source snapshot path')
        actual = digest(path) if path.is_file() else None
        checks.append(dict(path=name, expected=value, actual=actual, passed=actual == value))
    return dict(passed=bool(checks) and all(c['passed'] for c in checks), checks=checks,
        git_commit=None, scope='Recorded source snapshot SHA256; no retrospective Git identity invented.')


def render(run, result):
    core = result['core']
    cost = result['cost']['total']
    continuation = result['initial_source'].get('generation_origin') == 'reused_accepted_source_core'
    lines = ['# 真实模型渐进式 FIFO 断言细化报告', '',
        f"运行终态：`{result['status']}`。两义务完整链：`{result['two_obligation_chain']['passed']}`；"
        f"四项目标义务独立保护：`{result['four_target_obligations']['passed']}`；"
        f"五义务现有目标样本范围：`{result['five_obligations_recorded_scope']['passed']}`。**五义务完整保护仍未建立**。", '',
        ('本轮从明确来源的冻结已接受集合继续，初始化新调用为 0；仅新的修改请求计作本轮真实调用。没有重放旧响应冒充新修改。'
         f"两义务链包含继承的来源修复：本轮接受目标编辑 {result['model_trace']['accepted_new_target_edits']} 次；"
         '本轮没有接受新编辑时，链成立表示来源保护在新的独立回放中保持，不能称为本轮新修复成功。' if continuation else
         '本轮初始 SVA 与修改均要求真实新模型调用；没有重放历史模型响应。') + '主案例是真实 axis_fifo RTL 加工程输出边界故障，'
        '不计为原始历史 FIFO presented 修复复现。合法背压触发覆盖不能代替 stall_stability 目标违例检出。', '',
        f"stall 故障配置：`{result['stall_fault_configuration']}`；独立测试缺少实际目标违例的义务："
        f"`{result['whole_parent_case']['untested_target_obligations']}`。"
        '配置启用不等于找到违例；只有实际目标、原生检出与有效触发齐备且无误报、漏报、unknown，才按记录范围判断。', '',
        '背压子条件必须分开：当前已接受的连续两拍 stall 数据检查，只覆盖两拍均保持 mvalid 且 !mready 时的数据。'
        '它没有建立 valid 必须保持、解除背压当拍数据仍保持等完整子条件的保护；通过 stall_glitch 样本不能替代这些验证。'
        '排空断言也只在有限公平排空样本上验证，不是与完整规范等价的证明。', '',
        '有限仿真未发现违例不等于形式证明；历史回放保持只适用于已回放证据。'
        'stat 与原始 FIFO presented 仍 unknown。本轮没有四组消融或搜索基线对比，不能据此宣称机制优于基线。', '',
        '## 实际新生成与修改轨迹', '',
        f"取得资格的公共初始来源核验：`{result['initial_source']['passed']}`；接受编辑原始 JSON/通用组装核验："
        f"`{result['model_trace']['accepted_integrity_passed']}`；冻结集合等于最后接受版本："
        f"`{result['model_trace']['final_candidate_equals_last_accepted']}`。"
        f"初始表达式原响应／组装核验：`{result['initial_expression_audit']['passed']}`。"
        f"接受审计状态：`{result['model_trace']['acceptance_audit_status']}`；没有接受编辑时不显示为核验通过。", '',
        '初始候选尝试：', '', '| 版本 | 实际调用 | 状态 | 原生执行结果 | 初始资格通过 |',
        '|---|---|---|---|---|']
    for attempt in result['initial_attempts']:
        c = attempt['call']; d = attempt['decision']
        lines.append(f"| {attempt['version']} | {attempt['actual_generation_attempt']} | "
            f"{c.get('status', 'unavailable')} / {c.get('candidate_status', 'unavailable')} | "
            f"{attempt['native_result_present']} | {d.get('qualified')} |")
    for attempt in result['initial_attempts']:
        lines += ['', f"`{attempt['version']}` 原生计数：`{attempt['decision'].get('counts', 'unavailable')}`。"]
        if attempt['candidate']:
            lines += ['```systemverilog'] + [a['property'] for a in attempt['candidate'].get('assertions', [])] + ['```', '']
        elif attempt.get('edit'):
            lines += ['原始模型提案（未组装为候选、未原生执行；保留接口错误）：', '```json',
                json.dumps(attempt['edit'], ensure_ascii=False, indent=2), '```', '']
        else:
            lines += ['没有可解析模型提案；不构造替代 SVA。', '']
    lines += [('本轮起始断言（复用来源已接受 core，不是本轮新初始生成）：' if continuation else
        '获得资格的公共初始断言（未取得资格则为空）：'), '```systemverilog']
    lines += [a['property'] for a in (result['initial_candidate'] or {}).get('assertions', [])]
    lines += ['```', '', '| 版本 | 请求义务 | 仅合法覆盖 | 实际调用 | 模型/预检状态 | 原生结果 | 接受 | 检出/漏报/误报/unknown（修改后） |',
        '|---|---|---|---|---|---|---|---|']
    for t in result['model_trace']['records']:
        h = t['history']; c = h.get('after') or {}
        lines.append(f"| {t['version']} | {','.join(h.get('requested_obligations', []))} | {h.get('coverage_only')} | "
            f"{t['generation_attempt_present']} | {t['call'].get('status', 'unknown')} / "
            f"{t['call'].get('candidate_status', 'unavailable')} | {t['native_result_present']} | {t['accepted']} | "
            + '/'.join(str(c.get(k, '不可用')) for k in ('detections', 'misses', 'false_positives', 'unknown')) + ' |')
    for t in result['model_trace']['records']:
        h = t['history']
        lines += ['', f"### {t['version']}", '', f"修改理由：{(t.get('edit') or {}).get('reason', '未返回可解析编辑')}。", '']
        if t['candidate']:
            lines += ['```systemverilog'] + [a['property'] for a in t['candidate'].get('assertions', [])] + ['```', '']
        elif t.get('edit'):
            lines += ['原始模型提案（未组装为候选、未原生执行；保留接口错误）：', '```json',
                json.dumps(t['edit'], ensure_ascii=False, indent=2), '```', '']
        else:
            lines += ['没有可解析模型提案；不构造替代 SVA。', '']
        lines += ['接受／拒绝原因：`' + json.dumps(h.get('decision'), ensure_ascii=False) + '`。',
            f"历史回放修改前：`{h.get('before')}`；修改后：`{h.get('after')}`。"]
        if t['rejected_before_generation']:
            p = t['context_preflight']
            lines += [f"本轮在提交生成请求前被上下文预检拒绝，新增模型调用为 0；"
                f"输入保守估计 {p.get('conservative_input_estimate')} tokens，输出预留 {p.get('output_reserved_tokens')}，"
                f"上下文上限 {p.get('context_tokens')}。不能把此次迭代记作真实模型修改。"]
        elif t['call'].get('candidate_error'):
            lines += [f"接口诊断：`{t['call']['candidate_error']}`。该响应未获原生执行时，不计语义检出或修复成功。"]
        if t['direct_property_preservation']['format'] == 'direct_property':
            lines += [f"完整 property 来源核验：`{t['direct_property_preservation']['passed']}`。"
                '核对原始 JSON 字符串经过既有规范化后与候选逐字一致，仅允许去首尾空白和多余最外层括号；不重写前后件或时序关系。']
    lines += ['', '最终冻结断言：', '```systemverilog']
    lines += [a['property'] for a in (result['core_candidate'] or {}).get('assertions', [])]
    lines += ['```', '', '## 契约引导取得的有效漏报', '',
        (f"当前合格初始候选开发回放确认 {result['missing_evidence']['confirmed_missing_rows']} 个遗漏义务行，"
         f"去重缺口类 `{result['missing_evidence']['unique_gap_classes']}`。重复种子与参数变体不另算独立缺口。"
         if result['missing_evidence']['status'] != 'not_executed' else
         '未进入合格初始候选的开发补证阶段；空表不表示没有漏报。初始候选资格失败的实际误报和漏报另见前文。'), '',
        '| 场景 | 周期 | 故障 | 义务 | 漏报类型 | 有效 |', '|---|---:|---|---|---|---|']
    for w in result['missing_evidence']['records']:
        lines.append(f"| {w['scenario_id']} | {w['cycle']} | {w['variant']} | {w['obligation']} | {w['miss_subtype']} | {w['valid']} |")
    shown = set()
    for w in sorted(result['missing_evidence']['records'], key=lambda x: (
            {'drain_no_loss': 0, 'reset_cancellation': 1}.get(x['obligation'], 2), x['scenario_id'])):
        if w['variant'] in shown or len(shown) >= 2:
            continue
        shown.add(w['variant'])
        lines += ['', f"实例 `{w['scenario_id']}`，参数 `{w['parameters']}`，义务 `{w['obligation']}`："]
        for pair in w['aligned_transactions'][:3]:
            b, f = pair['buggy'], pair['fixed'] or {}
            lines.append(f"事务 `{b['transaction_id']}` 接受周期 {b.get('accept_cycle')}，"
                f"正确版本响应周期 {f.get('response_cycle')}，故障版本响应周期 {b.get('response_cycle')}，"
                f"取消周期 {b.get('cancel_cycle')}，接受数据/epoch 对齐 `{pair['accepted_match']}`。")
        lines.append('独立违例记录：`' + json.dumps(w['independent_violation'], ensure_ascii=False) + '`。')
    lines += ['', '依据独立端口事务队列及同输入握手对照判断义务，待评估 SVA 不是功能正确性判据。'
        '具体事务接受、响应、复位取消记录位于各 case 的 oracle.json，波形位于 wave.vcd；路径与违例详情见 results.json。', '',
        '## 阶段完成范围', '', '| 义务阶段 | 状态 | 仅覆盖 |', '|---|---|---|']
    for stage in core.get('stages', []):
        lines.append(f"| {','.join(stage['obligations'])} | {stage['status']} | {stage.get('coverage_only')} |")
    lines += ['', 'coverage_only 的接受只表示合法适用样本开始触发且历史证据未退化，不能算新增违例检出。'
        '模型声明多个义务标签也不能单独证明保护：下面仍分别列每项义务的原生触发与违例检出。', '',
        '## 冻结后公共独立回放（按实际输入去重）', '',
        f"独立执行状态：`{result['independent']['status']}`。未执行时空表不表示通过。"
        '实际执行时，core 与 initial 使用同一批冻结后生成的输入；initial 是本轮起点比较，不是额外消融组。'
        + ('本轮 initial 具体指来源已接受 core，不能当作最早那条单义务初始断言。' if continuation else '') +
        '按 case 中 depth/pipeline/rows 重建输入哈希，加变体、复位 epoch、周期和义务去重。重复判定冲突转 unknown，物理执行成本不去重。', '']
    for name, data in result['independent_deduplicated'].items():
        lines += ['| 候选 | 义务 | 满足行 | 违例行 | 检出 | 漏报 | 误报 | unknown | 触发行 |',
            '|---|---|---:|---:|---:|---:|---:|---:|---:|']
        for ob, counts in data['by_obligation'].items():
            lines.append(f'| {name} | {ob} | ' + ' | '.join(str(counts[k]) for k in (
                'satisfied_oracle_rows', 'target_oracle_rows', 'detections', 'misses', 'false_positives', 'unknown', 'triggers')) + ' |')
        lines += ['', f"{name}：原始 {data['raw_rows']} 行，去重 {data['unique_rows']} 行；"
            f"后续归因 unknown {data['later_attribution_unknown_raw']} 条另存；"
            f"{data['missed_obligation_rows']} 个漏报义务行对应 {data['missed_events']} 个采样事件。", '']
    lines += ['记录行数、事件数和独立父 Bug 数不同。未触发、无目标样本和 unknown 均不能按通过处理。', '',
        '## 实际成本与命令', '',
        f"本轮实际模型/API 请求尝试 {cost['model_calls']} 次，完整模型响应 "
        f"{result['cost']['model_response_outcomes']['complete_model_responses']} 次，失败或不完整响应 "
        f"{result['cost']['model_response_outcomes']['incomplete_or_failed_responses']} 次；"
        f"输入 tokens 已知小计 {cost['prompt_tokens_known_subtotal']}，"
        f"输出 {cost['completion_tokens_known_subtotal']}，usage 不可用 {cost['usage_unavailable_calls']} 次。"
        f"原生编译 {cost['native_compile_calls']} 次、执行 {cost['native_execute_calls']} 次"
        f"（含编译 smoke {cost['compile_smoke_execute_calls']} 次）；形式化 {cost['formal_calls']}。", '',
        '失败尝试全部计费；模型管理加载与分词预检另列，不算生成。开发案例资格检查 research20_cases_20261018_r01 '
        '是此前单独的开发审计，不混入本轮新调用成本；本轮相同输入在当前候选上的实际重新执行照常计费。', '',
        '远程兼容传输的 temperature/max_tokens 等顶层参数与本地 options 均按真实请求保存于成本记录。'
        'provider usage 原记录不再次加总；服务无法提供模型 digest 时保持 unavailable，不影响真实调用身份记录，'
        '也不编造与本地模型权重一致的结论。远程未执行本地分词预检时，不宣称该预检已通过。', '',
        '```powershell', (result.get('execution_command') or {}).get('command', '启动记录不可用'),
        f'wsl -- python3 scripts/research20_report.py --run {run.relative_to(ROOT).as_posix()}',
        f'wsl -- python3 scripts/research20_report.py --run {run.relative_to(ROOT).as_posix()} --verify', '```', '',
        '重跑实验须更换 --out；不能覆盖原产物。随机种子、开发参数、源码内容版本及实际工具命令均保留。'
        'report/manifest.json 封存所有非报告产物；源码快照与 RTL 内容哈希单列，缺失 Git 提交号保持为空。', '',
        '## 尚未完成或结论限制', '',
        f"- 独立测试没有实际违例分母的义务：`{result['whole_parent_case']['untested_target_obligations']}`；不能按通过处理。",
        '- 原始历史 FIFO 与 stat 不计成功；当前只有一个工程父案例。',
        '- 本轮不包含四组消融或新搜索基线比较。',
        '- 独立失败不得用于修改当前冻结版本；若后续利用，须转为开发数据并另建独立测试。', '']
    if result.get('diagnosis'):
        lines += ['## 本次运行保存的诊断', '', '```json',
            json.dumps(result['diagnosis'], ensure_ascii=False, indent=2), '```', '',
            '诊断保留原请求和失败成本，不追认已发生的失败为成功。未提交的生成请求没有模型 tokens；'
            '已经提交但最终用量缺失的调用保持 unavailable，二者不可混淆。', '']
    reused = result.get('reused_core_source_audit')
    if reused:
        source_cost = result['reused_source_cost']['physical']['total']
        lines += ['## 续跑来源与独立记账', '',
            f"来源 `{reused['source']}`；源初始、接受编辑、冻结和 {len(reused['source_file_checks'])} 项输入哈希核验：`{reused['passed']}`。",
            '来源初始生成和已有修复均为过去真实调用，本轮新修改另计。来源独立结果没有用于提示或选择；'
            '只在终态报告阶段核算其物理成本，不把旧独立结果作为新结果。', '',
            f"来源历史成本：{source_cost['model_calls']} 次请求，输入 {source_cost['prompt_tokens_known_subtotal']}、"
            f"输出 {source_cost['completion_tokens_known_subtotal']} tokens，编译 {source_cost['native_compile_calls']}、"
            f"执行 {source_cost['native_execute_calls']}。此行不并入本轮成本，campaign 按运行目录只计一次。", '',
            '来源曾接受的模型编辑：']
        for t in reused['original_model_trace']['records']:
            if t['accepted']:
                lines += ['', f"`{reused['source']}/{t['version']}`：", '```systemverilog']
                lines += [a['property'] for a in (t['candidate'] or {}).get('assertions', [])]
                lines += ['```', '']
    return '\n'.join(lines)


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
        checks.append(dict(path=rel, expected=expected, actual=actual, passed=expected == actual))
    extra = sorted({p.relative_to(run).as_posix() for p in base.artifacts(run)} - set(manifest))
    freezes = base.freeze_audit(run)
    snapshot = source_audit(run)
    reused = read(out / 'results.json', {}).get('reused_core_source_audit')
    source_checks = []
    if reused:
        source = prior.portable_path(reused['source']).resolve()
        for record in reused['source_file_checks']:
            path = (source / record['path']).resolve()
            if ROOT not in source.parents or source not in path.parents:
                raise ValueError('Unsafe continuation source path')
            actual = digest(path) if path.is_file() else None
            source_checks.append(dict(path=str(path), passed=actual == record['expected'], expected=record['expected'], actual=actual))
    test = independent_audit(run, freezes)
    passed = all(c['passed'] for c in checks) and not extra and snapshot['passed'] and all(f['passed'] for f in freezes)
    passed &= all(c['passed'] for c in source_checks)
    if test['status'] == 'completed':
        passed &= test['all_frozen_hashes_match']
    result = dict(passed=bool(passed), checked=len(checks), checks=checks, unmanifested_files=extra,
        freezes=freezes, snapshot=snapshot, source_checks=source_checks, independent_freeze_matches=test.get('freeze_matches'),
        scope='Artifact/freeze integrity, not success of functionality claims.')
    dump(out / 'verification.json', result)
    print(json.dumps(dict(passed=result['passed'], checked=len(checks), unmanifested_files=extra)))
    if not passed:
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
        raise SystemExit('No terminal outcome; independent results were not read.')
    out = run / 'report'; out.mkdir(exist_ok=True)
    if args.verify:
        return verify(run, out)
    files = base.artifacts(run)
    freezes = base.freeze_audit(run)
    test = independent_audit(run, freezes)
    dedup = {}
    for name in (test.get('summary') or {}):
        ledger = read(run / 'core_independent' / name / 'independent_ledger.json')
        if ledger is not None:
            dedup[name] = prior.deduplicated_counts(ledger, run / 'core_independent' / name)
    core = read(run / 'core/summary.json', {})
    initial, initial_expression, reused = initial_provenance(run)
    trace = model_trace_audit(run, core)
    context = prior.context_audit(run, files)
    missing = missing_evidence_audit(run)
    sources = source_audit(run)
    two = scope(test, dedup, 'core', base.CORE_OBLIGATIONS)
    four = scope(test, dedup, 'core', TARGET_OBLIGATIONS)
    five = scope(test, dedup, 'core', base.ALL_OBLIGATIONS)
    untested = [o for o in base.ALL_OBLIGATIONS
        if not (dedup.get('core', {}).get('by_obligation', {}).get(o) or {}).get('target_oracle_rows')]
    protocol = read(run / 'protocol.json', {})
    source_target_edit = (reused or {}).get('original_model_trace', {}).get('accepted_new_target_edits', 0)
    accepted_trace_valid = trace['accepted_integrity_passed'] is not False
    chain = bool(initial['passed'] and initial_expression['passed'] and accepted_trace_valid
        and trace['final_candidate_equals_last_accepted'] and trace['accepted_new_target_edits'] + source_target_edit > 0
        and not context['invalid_accepted_contexts'] and sources['passed']
        and missing['confirmed_missing_rows'] and missing['archived_missing_rows_match'] and two['passed'])
    result = dict(status=outcome['status'], generated_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        outcome=outcome, protocol=protocol, execution_command=read(run / 'execution.command.json'),
        diagnosis=read(run / 'diagnosis.json'),
        initial_source=initial, initial_expression_audit=initial_expression,
        reused_core_source_audit=reused, reused_source_cost=source_cost_accounting(run, reused),
        initial_attempts=initial_attempts_audit(run),
        initial_candidate=read(run / 'shared_initial.json'), core_candidate=read(run / 'core/frozen_candidate.json'),
        core=core, model_trace=trace, missing_evidence=missing,
        independent=test, independent_deduplicated=dedup, freeze_checks=freezes, source_snapshot=sources,
        accepted_obligation_mapping=base.accepted_mapping(run, 'core', core),
        cost=extended_cost_audit(run, files), context_preflight_audit=context,
        management_operations=prior.management_audit(run),
        two_obligation_chain=dict(passed=chain, independent=two,
            generation='reused_source_real_initial_and_accepted_edits_plus_current_refinement' if reused else 'current_run_real_initial_and_edits',
            current_run_accepted_target_edits=trace['accepted_new_target_edits'], source_accepted_target_edits=source_target_edit),
        four_target_obligations=four,
        five_obligations_recorded_scope=five, stall_fault_configuration=protocol.get('stall_fault', {'enabled': False}),
        whole_parent_case=dict(passed=False, status='not_established', engineering_parent_count=1,
            required_obligations=list(base.ALL_OBLIGATIONS), untested_target_obligations=untested,
            reason='Missing target denominators remain unverified. Passing supplied stall_glitch samples does not establish valid-hold or stall-release stability. Drain is finite replay, not specification equivalence. Any five-obligation sample pass is not complete obligation protection.',
            original_historical_fifo_bug='unknown', stat='unknown'),
        semantic_coverage_limits=dict(stall_stability=dict(
            continued_stall_data='Only actual native replay evidence; candidate property remains in core_candidate.',
            valid_must_remain_asserted='not_established', data_stable_on_backpressure_release='not_established'),
            drain_no_loss='Finite fair-drain samples only, no logical equivalence or unbounded guarantee.'),
        baseline_comparison=dict(status='not_conducted', initial_is_frozen_comparator_only=True),
        prior_development_audit=dict(path='deliverables/research20_cases_20261018_r01',
            charged_in_current_run=False, scope='Separate earlier development audit, not new generation or independent validation.'))
    dump(out / 'results.json', result)
    dump(out / 'cost/results.json', dict(physical=result['cost'], context=context, management=result['management_operations'],
        reused_source_cost=result['reused_source_cost']))
    dump(out / 'freeze_checks.json', freezes)
    (out / 'REPORT.md').write_text(render(run, result), encoding='utf-8')
    shutil.copy2(__file__, out / 'report_script_snapshot.py')
    manifest = {p.relative_to(run).as_posix(): digest(p) for p in files}
    dump(out / 'manifest.json', manifest)
    dump(out / 'source_and_rtl_hashes.json', {k: v for k, v in manifest.items() if Path(k).suffix in ('.py', '.sv', '.v')})
    print(json.dumps(dict(status=result['status'], two_obligation_chain=chain, four_target_obligations=four['passed'],
        whole_parent_case=False, cost=result['cost']['total'], report=str(out / 'REPORT.md'))))


if __name__ == '__main__':
    main()
