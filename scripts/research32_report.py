"""Read-only physical cost, qualification and mechanism exposure report."""
import argparse
import hashlib
from pathlib import Path
import research17_loop as loop
import research17_report as audit
from research31_gate import portable

read,dump=loop.read,loop.dump


def main(search,gate,prep,qualification,out,run=None):
    out.mkdir(parents=True,exist_ok=False)
    costs={};manifests={}
    sources=dict(search=search,gate=gate,preparation=prep,qualification=qualification)
    if run:sources['real_refinement']=run
    for n,p in sources.items():
        files=audit.artifacts(p)
        cost=audit.cost_audit(p,files);costs[n]=cost['total'];dump(out/n/'cost.json',cost)
        manifest={f.relative_to(p).as_posix():hashlib.sha256(f.read_bytes()).hexdigest() for f in files}
        dump(out/n/'manifest.json',manifest);manifests[n]=len(manifest)
    records=read(search/'results.json');summary=read(search/'summary.json')
    methods=read(search/'protocol.json')['methods'];table=[]
    for m in methods:
        rows=[r for r in records if r['method']==m]
        unique={k for r in rows for k in r['independent_gap_keys']}
        table.append(dict(method=m,per_seed=[len(s['methods'][m]['gaps']) for s in summary],
            unique_gaps=len(unique),queries=len(rows),native_executions=sum(r['native_executions'] for r in rows),
            gap_rows=sum(len(r['gaps']) for r in rows),duplicates=sum(len(r['gaps']) for r in rows)-len(unique),
            unknown=sum(r['unknown'] for r in rows),later_unknown=sum(r['later_attribution_unknown'] for r in rows)))
    gate_result=read(gate/'outcome.json')
    q=read(qualification/'outcome.json')
    protocol=read(prep/'protocol.json')
    checks=dict(equal_queries=len({r['queries'] for r in table})==1,
        equal_executions=len({r['native_executions'] for r in table})==1,
        all_search_queries_healthy=all(r['healthy'] for r in records),
        four_methods_three_seeds=len(records)==48,
        native_qualification_all_seeds=all(read(prep/f's{s}/witness_qualification.json')['passed'] for s in protocol['seeds']),
        first_request_hashes=all(hashlib.sha256((prep/n).read_bytes()).hexdigest()==h for n,h in protocol['previews'].items()),
        same_natural_proposal_distinguishes_gate=gate_result['current_repair_accepts'] and not gate_result['full_gate_accepts'],
        bounded_refinement_control=q['continued_after_rejection'] and q['rollback_confirmed'])
    for seed in protocol['seeds']:
        binding=read(prep/f's{seed}/baseline_binding.json')
        checks[f'baseline_binding_{seed}']=hashlib.sha256(portable(binding['result_path']).read_bytes()).hexdigest()==binding['result_sha256']
    actual=read(run/'outcome.json') if run else None
    result=dict(checks=checks,all_checks_passed=all(checks.values()),search=table,gate=gate_result,
        preparation=read(prep/'outcome.json'),qualification=q,real_run=actual,costs=costs,manifest_files=manifests,
        limitations=['Search is a prospectively configured pilot on a deliberately chosen artificial long-stall counter fault.',
            'Gate example is a retrospective selection of an unmodified genuine archived proposal, not a new generation.',
            'Local archived-response control is not real-model refinement or evidence of model stability.',
            'Finite native simulation is not formal proof; later attribution unknown remains reported.'],
        historical_costs='105-case baseline and archived model proposals reused; prior costs are in research30/31/research27 artifacts and not counted as new calls.',
        project_accepted_freeze='research28 unchanged')
    dump(out/'results.json',result)
    lines=['# research32：多轮细化准备与机制曝光实跑','',
        '本轮已执行本地原生实验。新的真实模型多轮细化'+('已运行，见 results.json。' if run else '尚未运行，等待新增最多 9 次调用授权；旧额度已用完。'),'',
        '| 搜索方法 | 种子 3203 / 3209 / 3217 的独立缺口数 | 合并去重缺口 | 查询 / 原生执行 |',
        '|---|---|---:|---|']
    for r in table:lines.append(f"| {r['method']} | {' / '.join(map(str,r['per_seed']))} | {r['unique_gaps']} | {r['queries']} / {r['native_executions']} |")
    lines+=['','两个缺口分别是长背压中、解除边界的 valid 撤销。它们是显式人工计数故障；不是两个真实历史父 Bug。',
        '初始候选为 research27，第二个完整候选为 research28，均来自已有真实模型生成。每查询相同 112 拍、两候选 × 正确与两故障，共 6 次执行。普通补测、分歧和差分策略看不到评估侧义务结果。所有输入均为开发数据。',
        '本例契约搜索合并后比普通补测多 1 类缺口，但与分歧/差分合并后的类别总数相同；区别主要是种子内覆盖。不能推广为一般优越性。','',
        '## 同一个真实历史提案的门控对照','',
        f"research27/v0 原样提案在所选当前样例中修复 2 条漏报，当前样例规则接受；在历史场景产生 {gate_result['historical_new_false_alarm_rows']} 个误报采样行，完整门控拒绝。保留 {gate_result['after']['unknown']} 条当前归因 unknown 和 {gate_result['after']['later_attribution_unknown']} 条后续 unknown。38 行不是 38 个独立问题。",
        '原始提案：`mvalid |-> (ref_count > 0) && (mdata == ref_expected)`。选择规则及原模型输入输出哈希见 gate 案例 provenance.json。使用的是原研究27初始集合；没有移植或手改这个提案来制造退化。',
        '这是回顾性机制曝光，对照使用同一提案，因此没有两次模型输出差异的混杂；不能据此估计自然退化发生率。','',
        '## 真实细化入口','',
        '模型分别生成 Boolean 前件、后件及 same_sample/next_sample；拼装器只加括号和对应蕴含，不修改谓词。嵌套蕴含、未知端口、超过集合槽位、替换时改变义务映射均拒绝。',
        '复用已有多轮循环，最多三个种子各三次请求，拒绝后保留旧集合并反馈原生/接口诊断。完整门控与当前证据规则对同一提案作成对记录。三个版本全部冻结后才生成共同的新独立测试。',
        f"本地归档响应控制：先拒绝仍有 4 条漏报的真实旧提案，再接受另一份归档有效表达式的纯语法拆分/拼装回放；结果 {q['after']['detections']} 检出、{q['after']['misses']} 漏报。该控制实验零模型调用，不能冒充新的自动细化。",'',
        '## 复现命令','', '输出目录必须是新的不存在目录。', '```powershell',
        'wsl -- python3 scripts/research32_search.py --out deliverables/research32_search_NEW',
        'wsl -- python3 scripts/research32_gate_case.py --out deliverables/research32_gate_case_NEW',
        'wsl -- python3 scripts/research32_campaign.py prepare --search deliverables/research32_search_20261021_r01 --out deliverables/research32_prepare_NEW',
        'wsl -- python3 scripts/research32_qualification.py --prepared deliverables/research32_prepare_20261021_r01 --out deliverables/research32_qualification_NEW',
        '# 仅在获得新增授权并落盘对应 authorization.json 后运行：',
        'wsl -- python3 scripts/research32_campaign.py run --prepared deliverables/research32_prepare_20261021_r01 --out deliverables/research32_real_20261021_r01 --authorization deliverables/research32_prepare_20261021_r01/authorization.json',
        '```','',
        '实际成本见 results.json 的 costs 及各子目录 cost.json（含编译 smoke）。形式化调用为 0，金额不可用。研究28项目验收版本保持不变；整个父案例完整保护、通用收益和真实历史父案例闭环均未据此完成。']
    (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    assert all(checks.values()),checks
    print(dict(passed=True,checks=len(checks),costs=costs),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('search','gate','prepared','qualification','out'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--run',type=Path)
    a=p.parse_args();main(a.search.resolve(),a.gate.resolve(),a.prepared.resolve(),a.qualification.resolve(),a.out.resolve(),a.run.resolve() if a.run else None)
