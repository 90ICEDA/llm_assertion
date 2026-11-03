"""Explicit monitor-only compatibility follow-up; research185 remains failed.

Expand the reset loop into the same 256 constant-index NBA assignments. No
blocking-assignment substitution or event/sampling change; no RTL/SVA edit.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import research185_drop_partial as q


def execute(out):
    out.mkdir(parents=True,exist_ok=False)
    prior=q.D/'research185_drop_partial_20261102_r01'
    prior_cost=q.s.read(prior/'report/cost.json')
    original=q.bench
    loop='for(j=0;j<256;j=j+1) begin ingress_count[j]<=0;ingress_complete[j]<=0;output_seen[j]<=0;end'
    expanded=' '.join(f'ingress_count[{j}]<=0;ingress_complete[{j}]<=0;output_seen[{j}]<=0;' for j in range(256))
    checks=[]
    def ck(name,ok):checks.append(dict(name=name,passed=bool(ok)));assert ok,name
    def compatible(depth,policy):
        source=original(depth,policy)
        assert source.count(loop)==1
        return source.replace(loop,expanded)
    for depth in q.DEPTHS:
        for policy in q.POLICIES:
            a=original(depth,policy);b=compatible(depth,policy)
            ck(f'exact inverse {depth}/{policy}',b.replace(expanded,loop)==a)
            ck(f'768 reset NBAs {depth}/{policy}',expanded.count('<=0;')==768)
            ck(f'no reset blocking assignments {depth}/{policy}',not re.search(r'(?<!<)=0;',expanded))
    for entry in q.s.read(prior/'executions.json'):
        folder=prior/'native'/str(entry['depth'])/entry['policy']/entry['revision']
        ck('prior loop unsupported '+q.s.rel(folder),'%Error-BLKLOOPINIT' in (folder/'compile.log').read_text() and entry['result']['native_simulation_calls']==0)
    protocol=dict(purpose='local_monitor_compatibility_followup_not_model_pilot',
        change='Expand same256 reset iterations into constant-index nonblocking assignments. Retain clocked sampling, all other monitor statements, RTL, six controls, six scene pairs and oracle.',
        old_failed_run=q.s.rel(prior),old_cost=prior_cost,
        additional_native_compile_budget=12,additional_native_execution_budget=12,retries=0,model_calls=0,
        scope='All development. No old result changes, no response/model generation, no independent tests.',
        checks=checks,code_bindings={q.s.rel(p):q.s.sha(p) for p in (Path(__file__),Path(q.__file__),Path(q.s.__file__),prior/'prepared/seal.json',prior/'report/seal.json')})
    q.s.dump(out/'protocol.json',protocol)
    q.s.dump(out/'protocol_seal.json',{'protocol.json':q.s.sha(out/'protocol.json')})
    q.bench=compatible
    q.execute(out/'qualification')
    # The old artifacts stay untouched; aggregate both attempts separately.
    result=out/'qualification/report';audit=out/'qualification/compatibility_audit';audit.mkdir()
    current=q.s.read(result/'cost.json')
    total={k:prior_cost[k]+current[k] for k in current}
    q.s.dump(audit/'cost.json',dict(failed_loop_attempt=prior_cost,constant_index_attempt=current,total=total))
    q.s.dump(audit/'checks.json',checks)
    q.s.dump(audit/'bindings.json',protocol['code_bindings'])
    decision=q.s.read(result/'decision.json');matrix=q.s.read(result/'candidate_matrix.json')
    lines=['# research185/186 本地部分保护资格结果','',
           '**本地结构资格成立；未运行模型、未封存模型先导。**' if decision['local_structural_qualification'] else '**本地结构资格未成立；停止，不封存模型先导。**','',
           '|本地候选|公共检出|历史检出|误报|关键unknown|普通/历史|','|---|---|---|---|---|---|']
    for v in matrix:lines.append(f"|{v['candidate']}|{v['public_detected']}/{v['public_total']}|{v['historical_detected']}/{v['historical_total']}|{len(v['false_positive_records'])}|{len(v['critical_unknown'])}|{v['ordinary_accept']}/{v['historical_accept']}|")
    lines+=['','所有性质均为手写本地对照，不是模型生成或自动恢复。只检查首拍背压的部分候选、只检查首拍就绪的替换候选，以及联合/完整正对照、过宽与空触发负对照，全部使用相同原始RTL和独立事务参考。详见../report/candidate_matrix.json及obligation_evidence_mapping.json。',
            '', '公共与历史按首拍呈现时下游ready区分，不按帧ID、数据值或周期号白名单。帧ID只用于实际接受事务关联，原RTL启用其支持的ID_ENABLE=1；每个输入帧只计一个违例证据，多个泄漏拍不是多个Bug。早于握手的检出由后续实际握手核实。所有断言可编辑，没有固定不可编辑组件提前排除退化。',
            '', 'research185的12次原生编译因数组复位循环工具限制失败，原结果保持失败。本次另封存等价的768条逐元素非阻塞复位赋值，其余激励、性质和规则不变；逐拍原始端口重建复核被动监视器。不能将兼容性修复计作模型或机制收益。',
            '', f"累计编译尝试{total['native_compile_attempts']}次、原生执行{total['native_executions']}次，含旧失败成本；模型/形式化调用0。",
            '', '若本地资格成立，可进入下一阶段本地控制器/接口分支及未用独立语义样本余量核查；这些尚未完成，因此本轮没有模型先导请求。若资格不成立则停止。不能用手写联合对照充当真实恢复，条件恢复仍0/0不可估计。H/R等价，576次搜索负结果不变。',
            '', '全部新增样本属于开发已知材料；旧独立结果未用于候选选择。范围为同步FIFO、唯一帧ID、KEEP关闭、Depth8/16/32、初始化复位；不包含异步、稀疏KEEP、动态ID复用或复杂复位取消。有限仿真结果不是形式化证明。',
            '', '复现（新目录，产生12次本地原生执行，不调用模型）：','```powershell',
            'wsl -- python3 scripts/research186_drop_monitor_compat.py --out deliverables/research186_reproduce','```']
    (audit/'SUMMARY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    q.s.dump(audit/'seal.json',{p.name:q.s.sha(p) for p in audit.iterdir() if p.is_file()})
    print('COMPLETE186',json.dumps(decision),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True)
    execute(parser.parse_args().out.resolve())
