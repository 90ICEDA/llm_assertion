"""Post-terminal shared local/remote audit. No generation or model feedback."""
import argparse
import json
from pathlib import Path
import shutil
import research17_loop as loop
import research31_gate as gate
from research34_campaign import digest
from research34_applicability import native_target_gate, portable
from research36_applicability import validate_events
from research32_model import assemble
from research30_ablation_report import metrics
from research17_report import cost_audit, artifacts
from research29_drain import assess

read, dump = loop.read, loop.dump


def audit(run, out):
    outcome = read(run / 'outcome.json')
    assert outcome['status'] != 'running'
    out.mkdir(parents=True, exist_ok=False)
    remote = (run / 'prepared_source.json').exists()
    maximum_calls = read(run / 'protocol.json')['maximum_calls']
    expression_format = read(run / 'protocol.json').get('expression_format')
    ast_edit = expression_format in ('recursive_ast_replace_one_v1','recursive_ast_reset_variadic_v1')
    fresh_interface = expression_format == 'recursive_ast_reset_variadic_v1'
    prep = portable(read(run / 'prepared_source.json')['path'] if remote else read(run / 'protocol.json')['prepared'])
    checks = []
    def check(name, value): checks.append(dict(name=name, passed=bool(value)))
    for name, h in read(run / 'source_snapshot/hashes.json').items(): check('source:' + name, digest(run / 'source_snapshot' / name) == h)
    check('same_rtl', digest(run / 'axis_fifo.v') == digest(prep / 'axis_fifo.v'))
    plan = read(run / 'verified_plan.json')
    check('independently_reverified_plan', validate_events(plan, read(prep / 'expected.private.json'))['accepted'])
    plan_source = portable(read(prep / 'provenance.json')['plan_source'] if remote else read(run / 'protocol.json')['plan_source'])
    check('real_accepted_plan_source', read(plan_source / 'applicability_plan.json') == plan and read(plan_source.parent / 'decision.json')['accepted'])
    initial = read(prep / 'shared_initial.json')
    current = initial
    before = read(prep / 'full_baseline.json')
    final_result = before
    edits = []
    examples = []
    accepted = False
    calls = 0
    for version in sorted((run / 'core').glob('v*')):
        folder = version / 'model_call'
        decision = read(version / 'decision.json')
        check(version.name + ':no_edit_after_accept', not accepted)
        if not (folder / 'attempt.json').exists():
            preflight = read(version / 'context_preflight/result.json')
            check(version.name + ':no_call_after_context_rejection', preflight['fits_with_output_reserve'] is False and not decision['accepted'])
            edits.append(dict(iteration=version.name, call=None, decision=decision, context=preflight))
            continue
        calls += 1
        result = read(folder / 'result.json')
        request = read(folder / 'request.json')
        body = json.loads(request['messages'][1]['content'])
        expected_model = 'qwen/qwen-2.5-72b-instruct' if remote else 'qwen2.5-coder:7b-instruct'
        check(version.name + ':model_and_plan', request['model'] == expected_model and body['actual_verified_plan'] == plan)
        if remote:
            from research38_history_feedback import payload, feedback
            if ast_edit:
                from research39_ast_refinement import payload
            if fresh_interface:
                from research41_fresh_campaign import payload
            settings = read(prep / 'model_config.json')
            if version.name == 'v0':
                diagnostic = read(prep / 'development_diagnostics.json')
                check('fixed_first_request', request == read(prep / 'request.preview.json'))
            else:
                previous = version.parent / ('v' + str(int(version.name[1:])-1))
                native_path = previous / 'target_native/result.json'
                if read(run / 'protocol.json').get('feedback_version') == 4:
                    from research41_fresh_campaign import feedback as fresh_feedback
                    full_path=previous/'history_native/result.json'
                    actual_path=full_path if full_path.exists() else native_path
                    diagnostic=fresh_feedback(read(actual_path) if actual_path.exists() else None,read(previous/'decision.json'),read(previous/'model_call/result.json'),diagnostic)
                elif read(run / 'protocol.json').get('feedback_version') == 3:
                    from research39_ast_refinement import feedback as ast_feedback
                    diagnostic = ast_feedback(read(native_path) if native_path.exists() else None, read(previous / 'decision.json'), read(previous / 'model_call/result.json'), diagnostic)
                elif read(run / 'protocol.json').get('feedback_version') == 2:
                    from research38_history_feedback import complete_feedback
                    diagnostic = complete_feedback(read(native_path) if native_path.exists() else None, read(previous / 'decision.json'), read(previous / 'model_call/result.json'))
                else:
                    diagnostic = feedback(read(native_path) if native_path.exists() else None, read(previous / 'decision.json'))
            check(version.name + ':actual_numeric_feedback_request', request == payload(initial, diagnostic, plan, settings))
        else:
            check(version.name + ':context_fit', read(version / 'context_preflight/result.json')['fits_with_output_reserve'] is True)
        check(version.name + ':no_retry', result['retries'] == 0)
        edit = read(folder / 'model_edit.json') if (folder / 'model_edit.json').exists() else None
        candidate = read(folder / 'candidate.json') if (folder / 'candidate.json').exists() else None
        if edit is not None and remote:
            from research28_report import raw_response
            check(version.name + ':raw_stream_edit', raw_response(folder, edit))
        elif edit is not None:
            events = [json.loads(line) for line in (folder / 'response.stream.jsonl').read_text().splitlines()]
            content = ''.join(e.get('message', {}).get('content', '') for e in events)
            check(version.name + ':raw_stream_edit', json.loads(content) == edit and content == read(folder / 'response.raw.json')['message']['content'])
            check(version.name + ':terminal_usage', events[-1].get('done') and events[-1].get('prompt_eval_count') == result['prompt_tokens'] and events[-1].get('eval_count') == result['completion_tokens'])
        if candidate is not None:
            if ast_edit:
                from research39_ast_refinement import assemble as ast_assemble, render_edit
                if fresh_interface:
                    from research41_fresh_campaign import assemble as ast_assemble, render_edit
                check(version.name + ':raw_ast_rendering', render_edit(edit, initial) == read(folder / 'rendered_edit.json'))
                check(version.name + ':no_expression_rewrite', ast_assemble(edit, initial) == candidate)
            else:
                check(version.name + ':no_expression_rewrite', assemble(edit, initial) == candidate)
        small = None
        full = None
        target = None
        if (version / 'target_native/result.json').exists():
            small = read(version / 'target_native/result.json')
            target = native_target_gate(read(prep / 'target_baseline.json'), small, edit['assertion_id'])
            check(version.name + ':target_gate', target == read(version / 'target_gate.json'))
            if target['accepted']:
                full = read(version / 'history_native/result.json')
                hist = gate.decide(before['group']['ledger'], full['group']['ledger'], sorted(loop.inspect(before['group']['ledger'])['misses'])) if full.get('group') else dict(accepted=False, reasons=[dict(kind='native_unavailable')])
                hist['accepted'] = bool(hist['accepted'] and full['healthy'])
                check(version.name + ':history_gate', hist == read(version / 'historical_gate.json') == decision)
            else: check(version.name + ':target_rejection_stops_history', decision == target and not (version / 'history_native').exists())
            old = loop.inspect(read(prep / 'target_baseline.json')['group']['ledger'])
            new = loop.inspect(small['group']['ledger']) if small.get('group') else None
            for key in sorted(old['misses']): examples.append(dict(iteration=version.name, before=old['rows'][key], after=new['rows'].get(key) if new else None, edit=edit, decision=decision))
        else: check(version.name + ':no_native_no_accept', not decision['accepted'])
        if decision['accepted']:
            current = candidate
            final_result = full
            accepted = True
        edits.append(dict(iteration=version.name, edit=edit, call=result, decision=decision, target_gate=target,
                          native_metrics=metrics(small) if small and small.get('group') else None,
                          history_metrics=metrics(full) if full and full.get('group') else None))
    frozen = read(run / 'core/frozen_candidate.json')
    check('frozen_accepted_or_retained', frozen == current and loop.sha(current) == outcome['frozen_hash'] == read(run / 'core/freeze.json')['candidate_sha256'])
    check('accepted_matches_terminal', accepted == outcome['accepted'])
    old = loop.inspect(before['group']['ledger'])
    new = loop.inspect(final_result['group']['ledger'])
    history = dict(before=len(old['detections']), retained=len(old['detections'] & new['detections']), lost=len(old['detections'] - new['detections']),
                   new_false_positives=len(new['false_positives'] - old['false_positives']), replayed=accepted)
    independent = None
    if accepted or read(run/'protocol.json').get('evaluate_retained_versions',False):
        split = read(run / 'independent/split.json')
        independent = read(run / 'independent/summary.json')
        cases = split['boundary_cases'] + split['drain_cases']
        fresh = {loop.sha(c['rows']) for c in cases}
        exposed = {loop.sha(c['rows']) for c in read(prep / 'full_cases.json')}
        exposed.update(split.get('extra_exposed_input_hashes',[]))
        paths = [portable(r['path']) for r in read(loop.ROOT / 'deliverables/research32_real_report_20261021_r02/results.json')['prior_exposed_inputs']]
        paths += [loop.ROOT / f'deliverables/research{n}_real_20261021_r01/independent/split.json' for n in (32,33)]
        for p in paths:
            data = read(p)
            exposed.update([loop.sha(data)] if p.name == 'stimulus.json' else [loop.sha(c['rows']) for c in (data if isinstance(data,list) else data['cases'])])
        check('fresh_split', not fresh & exposed and split['frozen_hash'] == loop.sha(frozen))
        check('split_after_freeze', (run / 'independent/split.json').stat().st_mtime >= (run / 'core/freeze.json').stat().st_mtime)
        check('test_sizes', len(cases) == independent['scenarios'] == 56 and len(fresh) == independent['distinct_inputs'] == 48)
        check('all_test_candidates_frozen', all(read(p)['candidate'] == frozen for p in (run / 'independent').rglob('replay.json')))
        combined = read(run / 'independent/combined.json')
        check('test_metrics', metrics(combined) == independent['metrics'])
        drain = assess(run / 'independent/drain', split['drain_cases'], read(run / 'independent/drain/result.json'))
        check('drain_assessment', drain == read(run / 'independent/drain_assessment.json'))
        passing = combined['healthy'] and drain['passed'] and all(m['detections'] > 0 and m['triggers'] > 0 and not any(m[k] for k in ('misses','false_positives','unknown')) for m in independent['metrics']['obligations'].values())
        check('five_obligation_acceptance', passing == independent['all_five_pass_on_first_attributed_evidence'])
    else: check('no_holdout_for_rejected_version', not (run / 'independent').exists())
    cost = cost_audit(run, artifacts(run))
    check('physical_call_budget', calls == outcome['calls'] == cost['total']['model_calls'] <= maximum_calls and (remote or outcome['remote_calls'] == 0))
    if remote:
        auth = read(run / 'authorization.json')
        check('bound_remote_authorization', auth['authorized_calls'] == 2 and auth['run_output'] == run.relative_to(loop.ROOT).as_posix())
    check('usage_consistency', all(cost['recorded_model_cost_crosscheck'].values()))
    result = dict(passed=all(c['passed'] for c in checks), checks=checks, outcome=outcome, edits=edits, history=history, independent=independent, cost=cost['total'])
    dump(out / 'results.json', result)
    dump(out / 'case_examples.json', examples)
    dump(out / 'cost.json', cost)
    dump(out / 'run_manifest.json', {p.relative_to(run).as_posix():digest(p) for p in artifacts(run)})
    shutil.copy2(__file__, out / 'audit_source.py')
    lines = ['# 历史数值反馈：真实细化与独立验收', '',
             f"状态 `{outcome['status']}`，实际提交 {calls}/{maximum_calls} 次生成请求，后端 {'Highway/Qwen 72B' if remote else '本地 Qwen 7B（远程调用0）'}。", '',
             '复用 research36 已真实通过的13窗口事件与三分类判断，保持原生目标、历史和独立验收标准。单次通过不能证明稳定细化；本地模型切换不计作 Qwen 72B 的复现。']
    for e in edits:
        lines += ['', f"版本 {e['iteration']}，接受 {e['decision']['accepted']}。", '```json', json.dumps(e.get('edit'),ensure_ascii=False,indent=2),'```',
                  '拒绝项：'+json.dumps([r['kind'] for r in e['decision']['reasons']],ensure_ascii=False)]
    lines += ['', f"冻结 {outcome['frozen_hash']}；历史保留 {history['retained']}/{history['before']}，新增误报 {history['new_false_positives']}；本轮新历史回放 {history['replayed']}。"]
    if independent:
        lines += ['', f"独立输入 {independent['distinct_inputs']}，场景 {independent['scenarios']}，五义务首个可归因证据通过 {independent['all_five_pass_on_first_attributed_evidence']}。", '',
                  '|义务|触发|检出|漏报|误报|当前unknown|','|---|---:|---:|---:|---:|---:|']
        for o,m in independent['metrics']['obligations'].items(): lines.append(f"|{o}|{m['triggers']}|{m['detections']}|{m['misses']}|{m['false_positives']}|{m['unknown']}|")
        lines += ['', '全计数（包括后续unknown）：'+json.dumps(independent['metrics']['counts'])]
    else: lines += ['', '没有执行新独立测试，不计为通过。']
    lines += ['', '本轮实际成本：'+json.dumps(cost['total'],ensure_ascii=False), '',
              f"审计 {sum(c['passed'] for c in checks)}/{len(checks)}。实际FIFO加人工故障，有限回放不等于形式化证明或全局无退化。",'',
              '只读审计命令：','```powershell',f'wsl -- python3 scripts/research37_audit.py --run {run.relative_to(loop.ROOT).as_posix()} --out deliverables/research37_report_NEW','```']
    (out / 'SUMMARY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(dict(passed=result['passed'],checks=len(checks),status=outcome['status']),flush=True)
    assert result['passed'], [c for c in checks if not c['passed']]


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run', required=True, type=Path)
    p.add_argument('--out', required=True, type=Path)
    a = p.parse_args()
    audit(a.run.resolve(), a.out.resolve())
