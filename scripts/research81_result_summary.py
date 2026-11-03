"""Publish audited recovery-comparison results without another experiment."""
import argparse
import json
from pathlib import Path


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def properties(candidate):
    return '\n'.join(a['id'] + ': ' + a.get('property',
        f"{a.get('derived_antecedent', '')} {a.get('implication', '')} {a.get('consequent', '')}")
        for a in candidate['assertions'])


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--prepared', type=Path, required=True)
    p.add_argument('--run', type=Path, required=True)
    p.add_argument('--audit', type=Path, required=True)
    a = p.parse_args()
    audit, outcome = read(a.audit / 'audit.json'), read(a.run / 'outcome.json')
    assert audit['passed'] and audit['outcome'] == outcome
    costs = read(a.audit / 'cost.json')
    trace = read(a.audit / 'trace.json')
    mapping = read(a.run / 'independent_mapping.json') if (a.run / 'independent_mapping.json').exists() else {}
    arms = {arm: read(a.run / 'arms' / arm / 'outcome.json') for arm in ('P', 'D')}
    accepted_hashes = {x['frozen_hash'] for x in arms.values() if x['accepted']}
    report = dict(outcome=outcome, arms=arms, distinct_new_accepted_hashes=len(accepted_hashes),
                  cost=costs['total'], independent=mapping,
                  limitation='One selected FIFO task and fixed seed. Workflow comparison, not isolated gate causality or core mechanism benefit.')
    lines = ['# research81：固定预算恢复流程对照结果', '',
             f"实际终态：{outcome['status']}。最多4次调用，实际{outcome['actual_model_calls']}次；无自动扩展。", '',
             '|里程碑|新增|', '|---|---:|',
             f"|接受版本（不同哈希）|{len(accepted_hashes)}|",
             f"|完成105历史回放|{outcome['completed_history_replays']}|",
             f"|新独立验收通过（组）|{outcome['new_independent_passes']}|",
             '|两个核心机制增量证据|0|', '',
             '|组|实际调用|新版本接受|新独立验收|', '|---|---:|---|---|']
    for arm, data in arms.items():
        test = mapping.get(arm)
        label = str(test['passed']) if test else '未启动'
        lines.append(f"|{arm}|{data['calls']}|{data['accepted']}|{label}|")
    if arms['D']['accepted'] and arms['D']['calls'] == 1:
        lines += ['', 'D首轮直接生成即通过，未发生本轮拒绝后细化。因此本轮不能证明历史拒绝反馈促成了恢复；若P计划失败，也不能据此断言逐窗口门控一般有害。']
    lines += ['', 'P为完整计划后生成；D为直接生成、必要时真实反馈细化一次。两组初始候选、公共开发信息和最终原生标准一致；每组上限2次，但P将一次额度用于计划，D最多有两次性质机会。实际不同响应不是共享提案，不能将结果当成纯门控因果估计。', '',
              '## 真实修改轨迹', '', '共同初始集合：', '', '```systemverilog',
              properties(read(a.prepared / 'initial.json')), '```']
    for item in trace:
        arm, stage = item['arm'], item['stage']
        lines += ['', f"### {arm} / {stage}", '', f"接受：{item['accepted']}。"]
        if stage == 'plan':
            d = read(a.run / 'arms' / arm / 'plan/v0/decision.json')
            lines += [f"实际规则执行正确{sum(x['rule_matches_certificate'] for x in d.get('details', []))}/11；窗口答案正确{sum(x['window_matches_certificate'] for x in d.get('details', []))}/11。",
                      '拒绝原因：' + json.dumps(d['reasons'], ensure_ascii=False)]
            continue
        index = 0 if stage == 'generate' else 1
        folder = a.run / 'arms' / arm / 'core' / f'v{index}'
        path = folder / 'model_call/candidate.json'
        if path.exists():
            lines += ['', '实际模型性质（原样组装）：', '', '```systemverilog', properties(read(path)), '```']
        lines += ['', '|阶段|检出|漏报|合法误报|关键unknown|后续归因unknown|', '|---|---:|---:|---:|---:|---:|']
        for phase, counts in item['counts'].items():
            if counts:
                lines.append('|'+phase+'|'+'|'.join(str(counts[k]) for k in
                    ('detections', 'misses', 'false_positives', 'unknown', 'later_attribution_unknown'))+'|')
            else:
                lines.append('|'+phase+'|未执行|||||')
        lines += ['', '实际接受/拒绝理由：' + json.dumps(item['decision']['reasons'], ensure_ascii=False)]
    if mapping:
        lines += ['', '## 冻结后的独立测试', '',
                  '两组终止并冻结后才生成共同新批次；没有根据独立结果改写候选或选择版本。相同候选哈希只物理测量一次，统计点不是独立Bug数。']
        for arm, value in mapping.items():
            folder = a.run / value['path'] / 'independent'
            summary = read(folder / 'summary.json')
            lines += ['', f"{arm}冻结哈希：`{value['candidate_hash']}`。", '',
                      '```json', json.dumps(summary, ensure_ascii=False, indent=2), '```']
            report.setdefault('independent_details', {})[arm] = summary
    else:
        lines += ['', '没有新独立测试；不能将未启动写成测试通过或失败。']
    lines += ['', '## 成本与结论范围', '', '```json', json.dumps(costs['total'], ensure_ascii=False, indent=2), '```',
              '', '准备阶段的13次编译、271次执行另见准备目录cost.json，不混入本次生成策略成本。货币账单不可用。',
              '单种子、一个已观察的开发恢复任务不支持稳定成功率结论。任何通过只适用于有限原生仿真范围；后续归因unknown保留，不是全局无退化或形式化证明。',
              '本轮检验辅助生成流程，未新增契约搜索独有缺口或防退化前瞻性多种子收益证据。不会自动追加同模型调用、第二种子或机制比较。', '',
              '## 只读复核', '', '```powershell',
              'wsl -- python3 scripts/research81_audit.py --prepared deliverables/research81_prepare_20261025_r01 --run deliverables/research81_real_20261025_r01 --out deliverables/research81_audit_recheck_20261025_r01',
              'wsl -- python3 scripts/research81_result_summary.py --prepared deliverables/research81_prepare_20261025_r01 --run deliverables/research81_real_20261025_r01 --audit deliverables/research81_audit_recheck_20261025_r01', '```']
    (a.audit / 'RESULTS.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    (a.audit / 'milestones.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print('PUBLISHED', outcome['status'])


if __name__ == '__main__':
    main()
