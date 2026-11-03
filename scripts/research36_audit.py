"""Read-only audit of event claims, raw model edits, native gates and holdout.

Does not send requests, execute RTL, change candidates or feed test results back.
"""
import argparse
import json
from pathlib import Path
import shutil
import research17_loop as loop
import research31_gate as gate
from research34_campaign import digest
from research34_applicability import native_target_gate, portable
from research36_applicability import validate_events, request_from_previous
from research36_campaign import next_request, PREP, PRIOR
from research32_model import assemble
from research28_report import raw_response
from research30_ablation_report import metrics
from research17_report import artifacts, cost_audit
from research29_drain import assess

read, dump = loop.read, loop.dump


def audit(prep, run, out):
    assert (run / 'outcome.json').is_file(), 'run_not_terminal'
    out.mkdir(parents=True, exist_ok=False)
    checks = []
    def check(name, value): checks.append(dict(name=name, passed=bool(value)))
    for n, h in read(prep / 'prepared_hashes.json').items(): check('prepared:' + n, digest(prep / n) == h)
    for n, h in read(prep / 'source_snapshot/hashes.json').items(): check('source:' + n, digest(run / 'source_snapshot' / n) == h)
    check('same_rtl', digest(prep / 'axis_fifo.v') == digest(run / 'axis_fifo.v'))
    request = read(prep / 'request.preview.json')
    check('request_uses_actual_development_records', request == request_from_previous(PREP, PRIOR))
    expected = read(prep / 'expected.private.json')
    plans = []
    plan_ok = False
    plan = None
    for version in sorted((run / 'plan').glob('v*')):
        folder = version / 'model_call'
        check(version.name + ':no_call_after_plan_accept', not plan_ok)
        check(version.name + ':exact_request', read(folder / 'request.json') == request)
        plan = read(folder / 'applicability_plan.json') if (folder / 'applicability_plan.json').exists() else None
        if plan is not None: check(version.name + ':raw_model_plan', raw_response(folder, plan))
        verdict = validate_events(plan, expected)
        check(version.name + ':recomputed_event_and_label_gate', verdict == read(version / 'decision.json'))
        result = read(folder / 'result.json')
        check(version.name + ':no_retry', result['retries'] == 0)
        plans.append(dict(iteration=version.name, decision=verdict, actual=plan, call=result))
        plan_ok = verdict['accepted']
        request = next_request(request, plan, verdict)
    check('bounded_plan_calls', 1 <= len(plans) <= 2)
    initial = read(prep / 'shared_initial.json')
    current = initial
    baseline = read(prep / 'full_baseline.json')
    final_result = baseline
    edits = []
    examples = []
    accepted = False
    versions = sorted((run / 'core').glob('v*'))
    check('sva_only_after_event_accept', plan_ok or not versions)
    for version in versions:
        check(version.name + ':no_edit_after_accept', not accepted)
        folder = version / 'model_call'
        body = json.loads(read(folder / 'request.json')['messages'][1]['content'])
        check(version.name + ':actual_verified_model_plan', body['verified_model_applicability_plan'] == plan)
        result = read(folder / 'result.json')
        check(version.name + ':no_retry', result['retries'] == 0)
        edit = read(folder / 'model_edit.json') if (folder / 'model_edit.json').exists() else None
        candidate = read(folder / 'candidate.json') if (folder / 'candidate.json').exists() else None
        if edit is not None: check(version.name + ':raw_model_edit', raw_response(folder, edit))
        if candidate is not None: check(version.name + ':no_manual_expression_change', candidate == assemble(edit, initial))
        decision = read(version / 'decision.json')
        small = None
        full = None
        if (version / 'target_native/result.json').exists():
            small = read(version / 'target_native/result.json')
            target = native_target_gate(read(prep / 'target_baseline.json'), small, edit['assertion_id'])
            check(version.name + ':target_gate_recomputed', target == read(version / 'target_gate.json'))
            if target['accepted']:
                full = read(version / 'history_native/result.json')
                hist = gate.decide(baseline['group']['ledger'], full['group']['ledger'], sorted(loop.inspect(baseline['group']['ledger'])['misses'])) if full.get('group') else dict(accepted=False, reasons=[dict(kind='native_unavailable')])
                hist['accepted'] = bool(hist['accepted'] and full['healthy'])
                check(version.name + ':history_gate_recomputed', hist == read(version / 'historical_gate.json') == decision)
            else: check(version.name + ':target_failure_stops_history', not (version / 'history_native').exists() and decision == target)
            old = loop.inspect(read(prep / 'target_baseline.json')['group']['ledger'])
            new = loop.inspect(small['group']['ledger']) if small.get('group') else None
            for key in sorted(old['misses']):
                examples.append(dict(iteration=version.name, before=old['rows'][key], after=new['rows'].get(key) if new else None, edit=edit, decision=decision))
        else: check(version.name + ':no_native_no_accept', not decision['accepted'])
        if decision['accepted']:
            accepted = True
            current = candidate
            final_result = full
        edits.append(dict(iteration=version.name, edit=edit, decision=decision, call=result,
                          target=metrics(small) if small and small.get('group') else None,
                          history=metrics(full) if full and full.get('group') else None))
    check('bounded_sva_calls', len(versions) <= 2 and (not plan_ok or len(versions) >= 1))
    outcome = read(run / 'outcome.json')
    frozen = read(run / 'core/frozen_candidate.json')
    freeze = read(run / 'core/freeze.json')
    check('frozen_accepted_or_retained', frozen == current and loop.sha(frozen) == freeze['candidate_sha256'] == outcome['frozen_hash'])
    check('acceptance_matches_terminal', accepted == outcome['accepted'])
    old = loop.inspect(baseline['group']['ledger'])
    new = loop.inspect(final_result['group']['ledger'])
    history = dict(before=len(old['detections']), retained=len(old['detections'] & new['detections']),
                   lost=len(old['detections'] - new['detections']), new_false_positives=len(new['false_positives'] - old['false_positives']),
                   new_replay=accepted, scope='Finite recorded evidence; reused baseline is not a fresh replay.')
    independent = None
    if accepted:
        split = read(run / 'independent/split.json')
        summary = read(run / 'independent/summary.json')
        combined = read(run / 'independent/combined.json')
        cases = split['boundary_cases'] + split['drain_cases']
        fresh = {loop.sha(c['rows']) for c in cases}
        exposed = {loop.sha(c['rows']) for c in read(prep / 'full_cases.json')}
        sources = read(loop.ROOT / 'deliverables/research32_real_report_20261021_r02/results.json')['prior_exposed_inputs']
        paths = [portable(r['path']) for r in sources] + [loop.ROOT / f'deliverables/research{n}_real_20261021_r01/independent/split.json' for n in (32, 33)]
        for path in paths:
            data = read(path)
            exposed.update([loop.sha(data)] if path.name == 'stimulus.json' else [loop.sha(c['rows']) for c in (data if isinstance(data, list) else data['cases'])])
        check('fresh_no_exposed_input_overlap', not fresh & exposed)
        check('56_scenarios_48_distinct_inputs', len(cases) == summary['scenarios'] == 56 and len(fresh) == summary['distinct_inputs'] == 48)
        check('split_after_freeze', (run / 'independent/split.json').stat().st_mtime >= (run / 'core/freeze.json').stat().st_mtime)
        check('frozen_hash_same_in_test', split['frozen_hash'] == loop.sha(frozen))
        # Every actual native replay binds the tested candidate to this freeze.
        replay_paths = list((run / 'independent').rglob('replay.json'))
        check('all_independent_executions_same_candidate', bool(replay_paths) and all(loop.sha(read(p)['candidate']) == loop.sha(frozen) for p in replay_paths))
        check('independent_metrics', metrics(combined) == summary['metrics'])
        drain = assess(run / 'independent/drain', split['drain_cases'], read(run / 'independent/drain/result.json'))
        check('drain_assessment_recomputed', drain == read(run / 'independent/drain_assessment.json'))
        passed = combined['healthy'] and drain['passed'] and len(summary['metrics']['obligations']) == 5 and all(
            v['detections'] > 0 and v['triggers'] > 0 and not any(v[k] for k in ('misses', 'false_positives', 'unknown')) for v in summary['metrics']['obligations'].values())
        check('five_obligation_criterion', passed == summary['all_five_pass_on_first_attributed_evidence'])
        independent = dict(**summary, drain_assessment=drain)
    else: check('no_independent_after_rejection', not (run / 'independent').exists())
    cost = cost_audit(run, artifacts(run))
    check('cost_crosscheck', all(cost['recorded_model_cost_crosscheck'].values()))
    check('physical_call_budget', cost['total']['model_calls'] == outcome['calls'] == len(plans) + len(edits) <= 4)
    result = dict(passed=all(c['passed'] for c in checks), checks=checks, outcome=outcome,
                  plans=plans, edits=edits, history=history, independent=independent, cost=cost['total'], unused_calls=4-outcome['calls'])
    dump(out / 'results.json', result)
    dump(out / 'case_examples.json', examples)
    dump(out / 'cost.json', cost)
    manifest = {p.relative_to(run).as_posix(): digest(p) for p in artifacts(run)}
    dump(out / 'run_manifest.json', manifest)
    shutil.copy2(__file__, out / 'audit_source.py')
    lines = ['# research36：事件判定、真实细化与同版本独立验收', '',
             f"终态 `{outcome['status']}`；模型调用 {outcome['calls']}/4，未使用 {4-outcome['calls']} 次。", '',
             f"事件和原三分类门控：{[p['decision']['accepted'] for p in plans]}。没有放宽 research35 的三分类条件，也没有追认旧结果。"]
    for item in edits:
        lines += ['', f"SVA {item['iteration']}：接受 {item['decision']['accepted']}。", '```json', json.dumps(item['edit'], ensure_ascii=False, indent=2), '```',
                  '拒绝原因：' + json.dumps([r['kind'] for r in item['decision']['reasons']], ensure_ascii=False)]
    lines += ['', f"冻结哈希 `{outcome['frozen_hash']}`；历史检出保留 {history['retained']}/{history['before']}，新增误报 {history['new_false_positives']}；本轮重新回放历史：{history['new_replay']}。"]
    if independent:
        lines += ['', f"冻结后 {independent['scenarios']} 个场景 / {independent['distinct_inputs']} 条不同输入，五义务首个可归因证据通过：{independent['all_five_pass_on_first_attributed_evidence']}。", '',
                  '| 义务 | 触发 | 检出 | 漏报 | 误报 | 当前unknown |', '|---|---:|---:|---:|---:|---:|']
        for name, m in independent['metrics']['obligations'].items():
            lines.append(f"| {name} | {m['triggers']} | {m['detections']} | {m['misses']} | {m['false_positives']} | {m['unknown']} |")
        lines += ['', '完整计数（含后续归因unknown）：' + json.dumps(independent['metrics']['counts'], ensure_ascii=False)]
    else: lines += ['', '本轮没有新的独立验收结果。']
    c = cost['total']
    lines += ['', f"实际输入/输出 tokens：{c['prompt_tokens_total']}/{c['completion_tokens_total']}；编译 {c['native_compile_calls']}，执行 {c['native_execute_calls']}（含冒烟 {c['compile_smoke_execute_calls']}），形式化 0，金额不可用。", '',
              f"审计 {sum(c['passed'] for c in checks)}/{len(checks)}，内容清单 {len(manifest)} 文件。审计通过不代替硬件验收通过。", '',
              '范围：实际 axis_fifo RTL 加显式人工故障；义务×采样证据数不是独立Bug数。有限原生仿真不是形式化证明；首个可归因证据通过不消除后续归因unknown。单次成功不能证明跨种子稳定或机制优势。', '',
              '已执行命令（不要重复消耗授权调用）：', '```powershell',
              f'wsl -- python3 scripts/research36_campaign.py run --prepared {prep.relative_to(loop.ROOT).as_posix()} --out {run.relative_to(loop.ROOT).as_posix()} --authorization {prep.relative_to(loop.ROOT).as_posix()}/authorization.json', '```']
    (out / 'SUMMARY.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(dict(passed=result['passed'], checks=len(checks), files=len(manifest), status=outcome['status']), flush=True)
    assert result['passed'], [c for c in checks if not c['passed']]


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--prepared', required=True, type=Path)
    p.add_argument('--run', required=True, type=Path)
    p.add_argument('--out', required=True, type=Path)
    a = p.parse_args()
    audit(a.prepared.resolve(), a.run.resolve(), a.out.resolve())
