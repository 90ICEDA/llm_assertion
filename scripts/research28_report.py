"""Read-only result analysis, raw-model integrity and content manifest."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import research17_loop as loop
import research17_report as report
from research28_model import RemoteModel

read, dump = loop.read, loop.dump


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def portable(path):
    raw = str(path).replace('\\', '/')
    marker = '/AssertionForge-main1/'
    return loop.ROOT/raw.split(marker, 1)[1] if marker in raw else Path(raw)


def metrics(result):
    info = loop.inspect(result['group']['ledger'])
    return dict(counts=result['counts'], healthy=result['healthy'], mapping=info['mapping'],
        by_obligation={o:{k:sum(info['rows'][key]['obligation'] == o for key in info[k])
            for k in ('detections', 'misses', 'unknown', 'false_positives', 'triggers')}
            for o in loop.model.SPECS})


def raw_response(folder, edit):
    """Reconstruct first-choice text from saved transport bytes, not edits."""
    raw = (folder/'response.stream.raw').read_text(encoding='utf-8')
    events = []
    if raw.lstrip().startswith('{'):
        events = [json.loads(raw)]
    else:
        data = []
        for line in raw.splitlines()+['']:
            if line.startswith('data:'):
                data.append(line[5:].strip())
            elif not line and data:
                payload = '\n'.join(data)
                if payload != '[DONE]':
                    events.append(json.loads(payload))
                data = []
    content = ''
    for event in events:
        for choice in event.get('choices', []):
            if choice.get('index', 0) == 0:
                text = choice.get('delta', choice.get('message', {})).get('content')
                if isinstance(text, str):
                    content += text
    assembled = read(folder/'response.assembled.json')['message']['content']
    return bool(events) and content == assembled and json.loads(content) == edit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    args = parser.parse_args()
    run = args.run.resolve()
    outcome = read(run/'outcome.json')
    assert outcome['status'] != 'running'
    dest = run/'report'
    dest.mkdir(exist_ok=True)
    files = [p for p in run.rglob('*') if p.is_file() and 'report' not in p.relative_to(run).parts]
    cost = report.cost_audit(run, files)
    dump(dest/'cost.json', cost)
    result = dict(outcome=outcome, cost=cost['total'], monetary_cost=None,
        scope='Finite native simulation of actual axis_fifo with explicitly injected output faults; no global or historical-parent success claim.',
        full_five_obligations_proven=False)
    if (run/'qualification.json').exists():
        qualification = read(run/'qualification.json')
        result['qualification'] = qualification
        result['completed'] = ['native_missing_evidence_qualification'] if qualification['passed'] else []
        result['pending'] = ['real_model_refinement', 'historical_replay', 'fresh_independent_replay']
        lines = ['# Research28：valid 保持开发见证', '',
            f"有效见证 {qualification['valid_witnesses']} 条，按义务与边界机制去重为 {len(qualification['distinct_mechanisms'])} 类。",
            '分别覆盖持续背压和 ready 恢复边界。正确控制满足义务；故障只撤销 valid、数据不变；当前 SVA 没有报告失败。',
            f"原生计数：`{qualification['counts']}`。",
            ('尚未调用模型；已保存请求预览。' if (run/'request.preview.json').exists()
             else '尚未调用模型；本次预览因开发目录防泄漏检查失败，原失败保留。'),
            '自动修复、历史防退化和冻结后新独立验收仍待执行。',
            '源代码、实际事务、波形、原生失败与前件 cover 记录均在运行目录。']
    else:
        initial = read(run/'shared_initial.json')
        final = read(run/'core/frozen_candidate.json')
        history = read(run/'core/history.json')
        accepted = [h for h in history if h['decision']['accepted']]
        last = run/'core'/f"v{accepted[-1]['iteration']}"/'native' if accepted else run/'core/before'
        result['development_before'] = metrics(read(run/'core/before/result.json'))
        result['development_after'] = metrics(read(last/'result.json'))
        result['frozen_hash'] = loop.sha(final)
        result['frozen_hash_valid'] = loop.sha(final) == read(run/'core/freeze.json')['candidate_sha256']
        result['history'] = history
        result['changed_properties'] = [dict(id=a['id'], before=a['property'], after=b['property'])
            for a, b in zip(initial['assertions'], final['assertions']) if a['property'] != b['property']]
        result['reset_property_unchanged'] = initial['assertions'][3] == final['assertions'][3]
        result['examples'] = []
        selected = read(run/'development_plan.json')
        source = portable(read(run/'shared_initial_freeze.json')['origin'])
        result['initial_lineage'] = dict(source=str(source),
            unchanged=read(source/'frozen_candidate.json') == initial,
            source_frozen_hash=read(source/'freeze.json')['candidate_sha256'],
            current_initial_hash=loop.sha(initial))
        old_development = read(source.parent/'development_plan.json')
        result['historical_development_unchanged'] = selected[:len(old_development)] == old_development
        promotions = []
        for case in selected[len(old_development):]:
            if case['source'] != 'published_test_promoted_after_observed_failure':
                continue
            path = portable(case['provenance']['source_case'])
            old = read(path)
            promotions.append(dict(case=case['id'], source=str(path),
                passed=digest(path)==case['provenance']['source_sha256'] and case['rows']==old['rows']
                    and case['mode']==old['mode'] and case['depth']==old['depth']
                    and case['pipeline']==old['pipeline'] and case['split']=='development'))
        result['public_test_promotion'] = dict(count=len(promotions), records=promotions,
            passed=len(promotions)==18 and all(p['passed'] for p in promotions))
        seen_modes = set()
        for i, case in enumerate(selected):
            if not case['mode'].startswith('valid_withdraw_') or case['mode'] in seen_modes:
                continue
            before_folder = run/'core/before'/f'case_{i}'
            before_ledger = read(before_folder/'ledger.json')['ledger']
            after_rows = {r['evidence_id']:r for r in read(last/f'case_{i}/ledger.json')['ledger']}
            targets = [r for r in before_ledger if r['obligation']=='stall_stability' and r['oracle']['verdict']=='violated']
            if not targets:
                continue
            row = targets[0]
            cycle = row['cycle']
            faulty = read(before_folder/case['mode']/'replay.json')
            fixed = read(before_folder/'correct/replay.json')
            pending = [t for t in fixed['oracle']['transactions'] if t['accept_cycle']<cycle
                       and (t['response_cycle'] is None or t['response_cycle']>=cycle)
                       and (t['cancel_cycle'] is None or t['cancel_cycle']>cycle)]
            result['examples'].append(dict(case=case['id'], mode=case['mode'], cycle=cycle,
                associated_transaction=min(pending,key=lambda t:t['accept_cycle']) if pending else None,
                faulty_samples=[s for s in faulty['reference_trace'] if cycle-1<=s['cycle']<=cycle],
                fixed_samples=[s for s in fixed['reference_trace'] if cycle-1<=s['cycle']<=cycle],
                before=row, after=after_rows.get(row['evidence_id']),
                native_before=str(before_folder/case['mode']),
                native_after=str(last/f'case_{i}'/case['mode'])))
            seen_modes.add(case['mode'])
        current = initial
        integrity = []
        prompt_audit = []
        for h in history:
            folder = run/'core'/f"v{h['iteration']}"/'model_call'
            if (folder/'model_edit.json').exists() and (folder/'candidate.json').exists():
                edit = read(folder/'model_edit.json')
                reconstructed = RemoteModel.replace_stall_slot(edit, current)
                generated = read(folder/'candidate.json')
                exact_raw = raw_response(folder, edit)
                integrity.append(dict(iteration=h['iteration'],
                    passed=reconstructed == generated and exact_raw,
                    raw_transport_matches_model_edit=exact_raw,
                    accepted=h['decision']['accepted'], model_edit=edit))
                if h['decision']['accepted']:
                    current = generated
            request = read(folder/'request.json')
            body = json.loads(request['messages'][1]['content'])
            for card in body['boundary_repair']['actual_observations']:
                for key, samples in (('source', 'faulty_samples'), ('control_source', 'correct_samples')):
                    source = portable(card[key]['path'])
                    actual = {s['cycle']:s for s in read(source)}
                    okay = (digest(source) == card[key]['sha256'] and
                            'core_independent' not in source.parts and
                            all(actual[s['cycle']] == s for s in card[samples]))
                    prompt_audit.append(dict(path=str(source), passed=okay))
        result['raw_model_integrity'] = dict(records=integrity, passed=bool(integrity) and all(x['passed'] for x in integrity) and current == final)
        result['prompt_evidence_integrity'] = dict(records=prompt_audit, passed=bool(prompt_audit) and all(x['passed'] for x in prompt_audit))
        if outcome.get('independent_executed'):
            folder = run/'core_independent'
            fresh = read(folder/'split.json')
            result['independent'] = {name:metrics(read(folder/name/'result.json')) for name in ('core', 'initial')}
            new_rows = {loop.sha(c['rows']) for c in fresh['cases']}
            old_rows = {loop.sha(c['rows']) for c in read(run/'development_plan.json')}
            result['test_separation'] = dict(no_schedule_overlap=not (new_rows & old_rows),
                frozen_hash_matches=fresh['candidate_hash'] == loop.sha(final),
                split_created_after_freeze=(folder/'split.json').stat().st_mtime >= (run/'core/freeze.json').stat().st_mtime,
                seed=fresh['seed'], scenarios=len(fresh['cases']))
            result['independent_valid_boundaries'] = {}
            for name in ('core', 'initial'):
                counts = Counter()
                for i, case in enumerate(fresh['cases']):
                    if not case['mode'].startswith('valid_withdraw_'):
                        continue
                    info = loop.inspect(read(folder/name/f'case_{i}/ledger.json')['ledger'])
                    for metric in ('detections', 'misses', 'unknown', 'false_positives'):
                        counts[(case['mode'], metric)] += sum(info['rows'][k]['obligation'] == 'stall_stability' for k in info[metric])
                result['independent_valid_boundaries'][name] = {mode:{m:counts[(mode,m)] for m in ('detections','misses','unknown','false_positives')}
                    for mode in ('valid_withdraw_stalled','valid_withdraw_release')}
        checks = result.get('test_separation', {})
        test = result.get('independent', {}).get('core', {})
        counts = test.get('counts', {})
        result['target_chain_passed'] = bool(accepted and result['reset_property_unchanged'] and
            result['raw_model_integrity']['passed'] and result['prompt_evidence_integrity']['passed'] and
            result['historical_development_unchanged'] and result['public_test_promotion']['passed'] and
            result['initial_lineage']['unchanged'] and
            result['initial_lineage']['source_frozen_hash']==result['initial_lineage']['current_initial_hash'] and
            result['frozen_hash_valid'] and all(checks.get(k) for k in ('no_schedule_overlap','frozen_hash_matches','split_created_after_freeze')) and
            test.get('healthy') and counts.get('misses') == counts.get('unknown') == counts.get('false_positives') == 0 and
            len(result.get('independent_valid_boundaries', {}).get('core', {})) == 2 and
            all(v['detections'] > 0 for v in result['independent_valid_boundaries']['core'].values()))
        lines = ['# Research28：valid 保持真实模型细化', '',
            f"本轮目标证据链通过：{result['target_chain_passed']}。原复位保护保持原文：{result['reset_property_unchanged']}。",
            f"开发前：`{result['development_before']['counts']}`。",
            f"开发后：`{result['development_after']['counts']}`。",
            f"冻结哈希：`{result['frozen_hash']}`。"]
        for change in result['changed_properties']:
            lines += ['', f"模型修改 {change['id']}：", '```systemverilog', change['before'], '```',
                      '修改后：', '```systemverilog', change['after'], '```']
        for example in result['examples']:
            before, after = example['faulty_samples']
            detected = any(a['causal_detection'] for a in example['after']['native']['assertions'])
            lines += ['', f"实际案例 `{example['case']}`：周期 {before['cycle']}→{after['cycle']}，"
                f"ready {before['mready']}→{after['mready']}，valid {before['mvalid']}→{after['mvalid']}，"
                f"数据 {before['mdata']}→{after['mdata']}。"
                f"原集合漏报，最终集合原生因果检出：{detected}。事务与正确对照见 results.json 的 examples。"]
        lines += ['', f"新独立测试：`{counts}`。",
                  f"valid 两类边界：`{result.get('independent_valid_boundaries')}`。",
                  '全部原始模型请求/流式响应、每轮候选、接受拒绝原因、开发历史回放和新独立波形保留。',
                  '历史保持结论仅限回放证据；后续归因 unknown 不删除，排空无曝光不按通过计。']
    lines += ['', f"实际成本：`{cost['total']}`。",
              '实际 axis_fifo RTL 加明确人工输出边界故障；不是上游历史 Bug 复现，也不是形式化证明。',
              '可执行命令见运行目录 execution.command.json；重新运行须新目录及有效模型调用授权。', '']
    dump(dest/'results.json', result)
    (dest/'SUMMARY.md').write_text('\n'.join(lines), encoding='utf-8')
    manifest = {str(p.relative_to(run)):digest(p) for p in files}
    dump(dest/'manifest.json', manifest)
    failures = [name for name, expected in manifest.items() if digest(run/name) != expected]
    dump(dest/'verification.json', dict(passed=not failures, checked_files=len(manifest), failures=failures,
        source_snapshot_hashes_valid=all(digest(run/'source_snapshot'/name)==expected
            for name, expected in read(run/'source_snapshot/hashes.json').items())))
    print(dict(report=str(dest), verified_files=len(manifest), failures=len(failures),
               target_chain=result.get('target_chain_passed')), flush=True)


if __name__ == '__main__':
    main()
