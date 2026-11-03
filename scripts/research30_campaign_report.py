"""Read completed research30 experiments; never execute models or change candidates."""
import argparse
import hashlib
from pathlib import Path
import shutil

import research17_loop as loop
import research17_report as audit

read, dump = loop.read, loop.dump
ROOT = loop.ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    assert ROOT in out.parents
    search = ROOT / 'deliverables/research30_search_compare_20261020_r01'
    prep = ROOT / 'deliverables/research30_ablation_prepare_20261020_r02'
    run = ROOT / 'deliverables/research30_ablation_20261020_r01'
    assert read(run / 'outcome.json')['status'] == 'four_real_model_arms_completed'
    s = read(search / 'report/results.json')
    a = read(run / 'report/results.json')
    assert read(search / 'report/verification.json')['passed']
    assert read(run / 'report/verification.json')['passed']
    out.mkdir(parents=True, exist_ok=True)
    prep_files = audit.artifacts(prep)
    prep_cost = audit.cost_audit(prep, prep_files)
    dump(out / 'preparation_cost.json', prep_cost)
    prep_hashes = {p.relative_to(prep).as_posix(): audit.digest(p) for p in prep_files}
    dump(out / 'preparation_manifest.json', prep_hashes)
    failures = [p for p, h in prep_hashes.items() if audit.digest(prep / p) != h]
    dump(out / 'preparation_verification.json', dict(passed=not failures,
        files=len(prep_hashes), failures=failures))
    sources = dict(search=s['cost'], preparation=prep_cost['total'], ablation=a['cost'])
    fields = ('model_calls', 'prompt_tokens_total', 'completion_tokens_total',
              'usage_unavailable_calls', 'native_compile_calls', 'native_execute_calls',
              'compile_smoke_execute_calls', 'formal_calls')
    total = {k: sum(v[k] for v in sources.values()) if all(v[k] is not None for v in sources.values()) else None
             for k in fields}
    dump(out / 'cost.json', dict(physical_by_stage=sources, physical_total=total,
        search_logical_executions_per_B_D_arm=64,
        accounting='Count each physical command once. B/D acquisition already belongs to search cost; logical charges are not added again.',
        failed_preparation_r01=dict(model_calls=0, native_compile_calls=0, native_execute_calls=0,
            reason='Wrong stimulus path failed before native execution; original failure retained.'),
        monetary_cost=None))
    state = dict(search_comparison='completed_three_seeds_one_native_candidate_pair',
        model_ablation='completed_four_real_requests_one_model_seed',
        gate_rule='unchanged_during_trial',
        search_additional_classes_vs_ordinary=len(s['methods']['contract_coverage']['additional_vs_each']['ordinary']),
        gate_counterfactual_on_B=a['counterfactual_gate_on_B'],
        remaining=['No demonstrated additional unique gaps versus ordinary or candidate disagreement in this task.',
                   'Trigger preservation gate rejects reset-cancelled, non-required historical triggers; needs separately validated applicability-aware rule.',
                   'One model request per arm: no multi-seed model stability or causal statistical claim.',
                   'Legacy 11 pairs not converted to native SVA experiments.',
                   'Artificial boundary faults on actual FIFO RTL; no new original historical parent-bug completion.'],
        independent=dict(seed=a['independent_seed'], cases=a['independent_cases'],
            frozen_hashes={n:r['frozen_hash'] for n,r in a['arms'].items()}))
    dump(out / 'results.json', state)
    lines = ['# Research30：固定候选后的搜索比较与四组真实消融', '',
        '本轮按顺序完成四类搜索比较和四组真实模型消融。保留所有失败、平局和后续归因 unknown；没有修改被冻结的候选或事后放宽验收。', '',
        '搜索比较：同一原生候选对、三个种子、每方法每种子四次查询，每次两候选 × 正确及七类故障，共 16 次原生执行。所有方法最终均发现两类 valid 保持缺口。契约搜索相对普通补测和候选对分歧新增独立缺口为 0；首次发现较普通补测快一条查询的种子有两个。普通差分在一个种子预算内没有发现。', '',
        '四组真实消融：每组一次 Highway/Qwen 72B 请求，A/C 提示相同，B/D 提示相同。新搜索证据只提供给 B/D。每组终止后冻结，所有组冻结后再执行共同历史审计及同一批新独立输入。', '',
        '| 组 | 实际处理 | 历史原有检出保留 | 新搜索漏报剩余 | 独立检出/漏报 | 独立误报/当前 unknown |',
        '|---|---|---:|---:|---:|---:|']
    labels = dict(A='普通反馈', B='搜索', C='防退化', D='搜索＋防退化')
    for n, r in a['arms'].items():
        h = r['historical_preservation']
        t = r['independent']['counts']
        lines.append(f"| {n} {labels[n]} | {'接受修改' if r['decision']['accepted'] else '拒绝修改，保留初始'} | "
            f"{h['original_detections']-len(h['lost_original_detections'])}/{h['original_detections']} | "
            f"{len(h['remaining_search_misses'])} | {t['detections']}/{t['misses']} | {t['false_positives']}/{t['unknown']} |")
    lines += ['', 'A 返回两个蕴含运算符，未通过接口约束，没有进入该候选的原生编译；不能称为原生语法错误。B 将 a2 替换为下式，模型表达式未经人工修改：', '',
        '原 a2：', '```systemverilog', a['arms']['B']['changed_properties'][0]['before'], '```', '',
        '模型修改后的 a2：', '```systemverilog', a['arms']['B']['changed_properties'][0]['after'], '```', '',
        'C、D 均只生成数据保持表达式，未增加 valid 保护。D 的两条新漏报未修复，拒绝有实际依据。C 的拒绝仅来自两条历史触发减少。', '',
        '对减少触发逐条检查发现，前一拍复位已取消待完成的背压保持义务，独立检查器在该周期没有对应检查。不能把这两条拒绝算作保住了必要检查。对 B 的实际冻结候选执行只读门控复算，也被同一规则拒绝，表明门控存在过度保守问题；该复算不改变任何实验组结果。', '',
        '相同提示、相同采样配置仍产生了不同模型输出，因此单次 B/D 差异不能完全归因于门控。当前实验证明搜索证据可驱动一次有效修复，尚未证明防退化提高了最终效果或两机制稳定优于基线。', '',
        f"新独立输入 seed {a['independent_seed']}，共 {a['independent_cases']} 场景。各组后续归因 unknown：", '']
    for n,r in a['arms'].items():
        lines.append(f"- {n}：{r['independent']['counts']['later_attribution_unknown']}；历史审计后续归因 unknown {r['historical_audit']['counts']['later_attribution_unknown']}。")
    lines += ['', '两个实际修改案例（事务明细与原始 native 行见消融报告 case_examples.json）：', '']
    for example in a['concrete_examples']:
        prev, now = example['native_samples']
        tx = example['accepted_uncompleted_transactions_at_violation']
        lines += [f"- {example['mechanism']}：周期 {prev['cycle']} 的 valid/ready 为 "
            f"{prev['mvalid']}/{prev['mready']}，下一周期 {now['cycle']} 为 "
            f"{now['mvalid']}/{now['mready']}，数据仍为 {now['mdata']}。"
            f"当时有 {len(tx)} 个已接受、尚未完成或取消的事务；旧 a4 已触发但只约束数据，漏掉 valid 撤销。"
            f"B 的新 a2 经原生执行检出；新独立输入中的对应义务结果 `{example['independent_by_arm']['B']}`。"]
    lines += ['', '本批独立输入的排空义务是否曝光，逐组列出，零曝光不能算验收通过：', '']
    for n,r in a['arms'].items():
        lines.append(f"- {n}：`{r['independent']['obligations']['drain_no_loss']}`。")
    lines += ['', '原 research28 冻结版本及 research29 的 12/12 排空丢失验收保持原记录；本轮消融使用 research27 作为共同起点，并未替换项目已验收版本。', '',
        f"物理总成本：`{total}`。完整分阶段成本见 cost.json。B/D 各计逻辑 64 次搜索执行，实际共享采集已计入搜索阶段，不重复相加。金额不可用，形式化查询为 0。", '',
        '本轮是一种已知真实 FIFO RTL 上的人工边界故障任务，搜索有三个种子，模型消融只有一个种子。不是跨父 Bug 稳定性、形式证明或全局无退化结论。', '',
        '可复核命令（报告入口只读原实验，不调用模型）：', '',
        '```powershell',
        'wsl -- python3 scripts/research30_report.py --run deliverables/research30_search_compare_20261020_r01',
        'wsl -- python3 scripts/research30_ablation_report.py --run deliverables/research30_ablation_20261020_r01',
        'wsl -- python3 scripts/research30_campaign_report.py --out deliverables/research30_campaign_20261020_r01',
        '```', '',
        '实际搜索及消融命令分别保存在原运行 execution.command.json；原目录不可覆盖重跑。新的模型实验需另建输出目录并取得相应调用额度。', '',
        '完整来源：', '',
        f'- 搜索逐项发现、同预算和去重核验：{search / "report/SUMMARY.md"}',
        f'- 四组原始响应、每版断言、决定、历史和独立统计：{run / "report/SUMMARY.md"}',
        f'- 实际 B 候选的只读门控复算：{run / "report/counterfactual_gate_on_B.json"}',
        '- 本目录 results.json：完成状态和仍未建立的结论。', '']
    (out / 'SUMMARY.md').write_text('\n'.join(lines), encoding='utf-8')
    shutil.copy2(__file__, out / 'report_source.py')
    dump(out / 'source_reports.json', {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (search/'report/results.json', run/'report/results.json',
                  search/'report/verification.json', run/'report/verification.json')})
    print(dict(total=total, preparation_files=len(prep_files), preparation_verified=not failures))


if __name__ == '__main__':
    main()
