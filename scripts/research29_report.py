"""Audit and report a terminal frozen-candidate drain evaluation."""
import argparse
import hashlib
from pathlib import Path
import shutil
import research17_loop as loop
import research17_report as common

read,dump=loop.read,loop.dump


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True)
    args=parser.parse_args()
    run=args.run.resolve()
    assert read(run/'outcome.json')['status']!='running'
    summary=read(run/'summary.json')
    split=read(run/'split.json')
    binding=read(run/'freeze_binding.json')
    report=run/'report'
    report.mkdir(exist_ok=True)
    files=[p for p in run.rglob('*') if p.is_file() and 'report' not in p.relative_to(run).parts]
    cost=common.cost_audit(run,files)
    dump(report/'cost.json',cost)
    frozen=read(run/'frozen_candidate.json')
    # Known historical batches are read solely for post-evaluation separation
    # auditing. Neither their results nor schedules entered generation here.
    prior=loop.ROOT/'deliverables/research28_valid_closed_loop_20261020_r01'
    historic=read(prior/'development_plan.json')+read(prior/'core_independent/split.json')['cases']
    overlap={loop.sha(c['rows']) for c in split['cases']} & {loop.sha(c['rows']) for c in historic}
    checks=dict(candidate_hash_matches=loop.sha(frozen)==binding['candidate_sha256']==split['candidate_sha256'],
        original_frozen_candidate_unchanged=frozen==read(prior/'core/frozen_candidate.json'),
        source_freeze_matches=binding['source_freeze']==read(prior/'core/freeze.json'),
        original_files_unchanged=all(digest(prior/'core'/n)==h for n,h in binding['source_file_hashes'].items()),
        source_snapshot_hashes=all(digest(run/'source_snapshot'/n)==h for n,h in read(run/'source_snapshot/hashes.json').items()),
        split_created_after_binding=(run/'split.json').stat().st_mtime>=(run/'freeze_binding.json').stat().st_mtime,
        no_input_overlap_with_research28=not overlap,
        independent_rows_labeled=all(r['split']=='independent_test' for r in read(run/'native/result.json')['group']['ledger']),
        no_model_call=cost['total']['model_calls']==0)
    summary.update(verification_checks=checks,acceptance_passed=summary['passed'] and all(checks.values()),
        seed=split['seed'],frozen_hash=binding['candidate_sha256'],cost=cost['total'],monetary_cost=None)
    dump(report/'results.json',summary)
    info=loop.inspect(read(run/'native/result.json')['group']['ledger'])
    dump(report/'obligation_mapping.json',info['mapping'])
    lines=['# Research29：冻结 research28 后的排空不丢失独立验收','',
        f"本批验收通过：{summary['acceptance_passed']}。冻结断言未修改；真实模型调用 0，形式化调用 0。",
        f"冻结哈希：`{summary['frozen_hash']}`。新随机种子：{summary['seed']}。",'',
        '| 配置 | 目标违例检出 / 有效曝光计划 | 合法对照通过 / 计划 |',
        '|---|---:|---:|']
    for depth,pipeline in ((2,0),(4,1),(8,2)):
        rows=[r for r in summary['scenarios'] if r['depth']==depth and r['pipeline']==pipeline]
        targets=[r for r in rows if r['role']=='target_loss']
        controls=[r for r in rows if r['role']=='legal_control']
        lines.append(f"| Depth {depth}, Pipeline {pipeline} | {sum(r['passed'] for r in targets)}/{len(targets)} | {sum(r['passed'] for r in controls)}/{len(controls)} |")
    lines+=['',
        '目标覆盖孤立请求、连续请求、先背压后释放、复位后新事务四种场景。合法对照覆盖三个事务正常排空和复位取消未完成事务。每个目标同时运行相同合法输入下的正确 FIFO。',
        '复用已有 mode3 人工故障：隐藏每第 4 个原始输出。只丢失最后一个事务后不再发出后续输出，因此能把排空违例作为独立检查器发现的首个错误，避免顺序错误抢先造成归因混淆。参数和波形变体归为同一个尾部丢失机制。',
        '所有检查依据实际握手、响应和复位记录。只有实际连续至少 18 拍输出 ready、输入 valid 为低、无复位，才认可排空检查点；不以输入 intent 或计划间隔代替。',
        '', '冻结版本原有排空 SVA：','```systemverilog',
        next(a['property'] for a in frozen['assertions'] if 'drain_no_loss' in a['obligations']),
        '```',
        '本次只验证该既有性质在实际曝光的场景上是否有效，没有人工替换性质或计作新的自动细化成功。合法排空时前件可以不触发；违例目标必须有原生前件 cover 和同拍断言失败，不能凭空触发通过。',
        '',f"全部原生计数：`{summary['counts']}`。",'']
    examples=[next(r for r in summary['scenarios'] if r['family']==family and r['depth']==8)
              for family in ('isolated_tail','reset_then_tail')]
    for ex in examples:
        lines.append(f"实际案例 `{ex['case']}`：检查点 {ex['deadline']}，实际公平后缀 {ex['actual_fair_samples']}；验收 {ex['passed']}。")
        for tx in ex['loss_transaction_correspondence']:
            lines.append(f"事务 `{tx['faulty']['transaction_id']}` 在周期 {tx['faulty']['accept_cycle']} 接受，正确版本周期 {tx['fixed']['response_cycle']} 响应，故障版本到检查点仍未响应且未取消。")
        lines.append('')
    if summary['acceptance_passed']:
        lines+=['本批没有观察到需要修改断言的失败，因此没有转为开发数据，也没有调用模型。冻结候选仍为 research28 原版本。']
    else:
        lines+=['失败或 unknown 场景全部保留；不修改或筛选本批结果。若据此继续修复，先将整批显式转为开发数据，再冻结新候选并创建新独立批次。']
    lines+=['','每条义务的完整映射见 obligation_mapping.json；事务对照、实际原生触发/失败、日志、波形、工具版本和命令均保留。',
        f"实际成本：`{cost['total']}`。",
        '这是已知人工丢失机制上的新输入独立测试，不是新故障类别泛化、真实历史修复复现或形式化证明。research28 旧批次的后续归因 unknown 不因本批通过而被清除。其他义务沿用原验收范围，不把跨批次结果宣称为全局完整保护。','',
        '复现实验（须使用新的输出目录；会生成新种子，无模型调用）：','```powershell',
        'wsl -- python3 scripts/research29_drain.py --out deliverables/research29_drain_independent_NEW','```',
        '报告核验：','```powershell',
        f'wsl -- python3 scripts/research29_report.py --run {run.relative_to(loop.ROOT).as_posix()}','```','']
    (report/'SUMMARY.md').write_text('\n'.join(lines),encoding='utf-8')
    shutil.copy2(__file__,report/'report_source.py')
    manifest={p.relative_to(run).as_posix():digest(p) for p in files}
    dump(report/'manifest.json',manifest)
    failures=[name for name,h in manifest.items() if digest(run/name)!=h]
    dump(report/'verification.json',dict(passed=not failures and all(checks.values()),files=len(files),
        failures=failures,checks=checks))
    print(dict(acceptance_passed=summary['acceptance_passed'],verified_files=len(files),failures=failures,
               targets=summary['valid_target_detections'],legal=summary['legal_scenarios_passed']),flush=True)


if __name__=='__main__':
    main()
