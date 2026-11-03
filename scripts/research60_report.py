"""Build a report from persisted local model runs; no inference or simulation."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
D=ROOT/'deliverables'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run(out):
    out.mkdir(parents=True,exist_ok=False)
    runs=[D/n for n in ('research60_local_20261023_r01','research60_local_compact_20261023_r02','research60_local_refine_20261023_r01','research60_deepseek_20261023_r01')]
    audits=[D/n for n in ('research60_compact_audit_20261023_r01','research60_refine_audit_20261023_r01','research60_deepseek_audit_20261023_r01')]
    for a in audits:assert read(a/'audit.json')['passed']
    costs=[read(p/'cost.json')['total'] for p in runs]
    cost={k:sum(c[k] for c in costs) for k in ('model_calls','prompt_tokens_known_subtotal','completion_tokens_known_subtotal','usage_unavailable_calls','model_wall_seconds_known_subtotal','native_compile_calls','native_execute_calls','native_compile_wall_seconds','native_execute_wall_seconds','formal_calls')}
    cost.update(remote_calls=0,local_model_management_calls=4,prompt_tokens_total=None,completion_tokens_total=None,monetary_cost=None,
                scope='Only research60 new physical calls. Preparation replay from research59 is reused, excluded. Compile-smoke executions are not added again.',
                usage_reason='One cancelled generation lacks final provider usage; known subtotal is not total consumption.')
    assert cost['model_calls']==4 and cost['native_compile_calls']==cost['native_execute_calls']==4
    first=read(audits[0]/'versions.json')[0];second=read(audits[1]/'versions.json')[0]
    for item in (first,second):
        assert item['focus']['first']['detected']==3 and item['focus']['held']['detected']==9
        assert item['small_counts']['false_positives']==78 and not item['decision']['accepted']
    duplicate=sha(runs[1]/'v0/model_call/model_edit.json')==sha(runs[2]/'v0/model_call/model_edit.json')
    assert duplicate
    native=read(runs[1]/'v0/alignment/result.json')
    fp=[r for r in native['ledger'] if r.get('sample',{}).get('sample_id')==18 and r.get('revision')=='after']
    assert len(fp)==3 and all(r['expected']==r['observed']==0 and any(a['failed'] for a in r['native']['assertions']) for r in fp)
    status=dict(accepted=False,scope='Ibex #166 original decoder module; development evidence only',
                focused_op_detected=12,focused_op_exposed=12,necessary_trigger_revision_points=24,
                legal_false_positives_per_qwen_version=78,critical_unknown_per_qwen_version=0,
                full151='not_run_small_gate_failed',freeze='not_created',independent='not_run',
                repeated_model_edit=duplicate,versions=[first,second,read(audits[2]/'versions.json')[0]],
                previous_accepted_versions='unchanged',remaining='Real model must eliminate legal false alarms while retaining first/held target detection and BRANCH protection, then pass unchanged full151 acceptance.')
    for name,value in [('status.json',status),('cost_roles.json',cost),('false_positive_sample18.json',fp)]:
        (out/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    checks=[len(read(a/'audit.json')['checks']) for a in audits]
    summary=f'''# research60：小范围原生门控仍未通过

真实本地 Qwen 已检出全部 12 个聚焦 OP 违例，但对合法行为有 78 条误报，因此不接受。误报反馈后的提案逐字重复，也被拒绝。没有人工改写位号、前件或后件。

| 实际尝试 | 首周期 | 保持阶段 | 必检触发（前后 RTL） | 合法误报 | 关键 unknown | 结果 |
| --- | --- | --- | --- | --- | --- | --- |
| Qwen 7B 完整源码输入 | 未产生候选 | 未产生候选 | 未执行 | 不适用 | 不适用 | 长输入推理取消；最终用量不可用 |
| Qwen 7B 精简源码输入 | 3/3 | 9/9 | 24/24 | 78 | 0 | 拒绝 |
| Qwen 7B 实际误报反馈 | 3/3 | 9/9 | 24/24 | 78 | 0 | 与上一版逐字相同，拒绝 |
| DeepSeek Coder 6.7B | 未执行 | 未执行 | 未执行 | 不适用 | 不适用 | 使用未声明 opcode，接口拒绝 |

两次实际原生回放各覆盖 9 个开发事务、240 条记录、48 个目标点（33 OP＋15 BRANCH），目标均检出；聚焦 12 点是其中子集。误报计数是采样/配置/修订记录，不是独立 Bug 数。触发子门通过不等于整个门控通过。完整151事务、420 OP＋270 BRANCH保持、冻结及新独立测试均未启动。

已实现真实本地模型入口、源码绑定的上下文精简、真实诊断反馈与响应审计。精简输入保留原始 OP 代码块及可逆的修复差分、来源行号/哈希；其他 opcode 分支未完整提供。原生 DUT 始终是完整原始 RTL。模型和输入范围均与远程试验不同，属于探索性尝试，不是公平机制消融或模型优劣结论。没有发送手写正对照或独立测试。

成本：{cost['model_calls']} 次本地生成提交（1 次取消、3 次完成），4 次本地加载管理请求，远程0次；原生编译4次、执行4次，形式化0次。已知输入/输出 tokens 为 {cost['prompt_tokens_known_subtotal']}/{cost['completion_tokens_known_subtotal']}，因取消调用缺最终用量，总量保持 null。三个完成运行的离线审计分别通过 {checks[0]}、{checks[1]}、{checks[2]} 项；审计通过只说明记录一致，不表示性质合格。

取消运行的原 outcome.calls=0 已保留，submission_reconciliation.json 依据实际 transport/cost 记录补记1次提交；未来 runner 已改为依据持久化传输记录计数。research60_local_compact_20261023_r01 为发送前上下文校验失败，调用0，不计入上述4次。

## 复核命令

在仓库根目录运行，输出目录须不存在；以下复核不调用模型、不运行新的仿真：

```powershell
wsl -- python3 scripts/research60_local_audit.py --run deliverables/research60_local_compact_20261023_r02 --out deliverables/research60_compact_audit_NEW
wsl -- python3 scripts/research60_local_audit.py --run deliverables/research60_local_refine_20261023_r01 --out deliverables/research60_refine_audit_NEW
wsl -- python3 scripts/research60_local_audit.py --run deliverables/research60_deepseek_20261023_r01 --out deliverables/research60_deepseek_audit_NEW
wsl -- python3 scripts/research60_report.py --out deliverables/research60_report_NEW
```

实际执行过的生成命令：

```powershell
wsl -- python3 scripts/research60_compact_local.py --out deliverables/research60_local_compact_20261023_r02
wsl -- python3 scripts/research60_local_refine.py --out deliverables/research60_local_refine_20261023_r01
wsl -- python3 scripts/research60_deepseek.py --out deliverables/research60_deepseek_20261023_r01
```

重跑生成需使用新目录，会产生新的本地模型与原生执行成本。原请求、响应流、SVA、决策、采样和日志在各运行目录。原失败记录、之前接受版本和 stat/FIFO presented unknown 均不更改。

仍需真实模型生成无合法误报的新 OP 性质，同时保留12点检出及BRANCH保护；小门通过后才进入完整151事务。不能据当前结果冻结或声称独立验收成功。现有远程额度已用尽，本轮未新增远程调用。
'''
    (out/'SUMMARY.md').write_text(summary,encoding='utf-8')
    edit=read(runs[1]/'v0/model_call/model_edit.json')
    trace='''# 实际模型轨迹

初始缺口：0x50b1e633 在首周期与保持阶段共12个采样/配置点；独立规则判违例，原始buggy输出illegal=0、fixed输出illegal=1。旧模型未检出。

本轮Qwen的真实OP输出如下（完整原响应已保存，BRANCH保持原模型版本）：

```json
'''+json.dumps(edit,ensure_ascii=False,indent=2)+'''
```

原生执行：12/12聚焦点被检出，首周期3/3、保持9/9；全9事务48/48目标检出，但78条合法误报。该前件未实现精确的bit28义务适用条件，仅检出目标仍不足。

实际误报样本：修复后RTL sample18、transaction3、phase0、instr_new=1，RV32E=0/RV32M=1；独立期望illegal=0，实际illegal=0，a1却触发失败。完整记录见false_positive_sample18.json。模型收到实际误报和保护要求后，输出与上一版model_edit.json逐字相同；重放结果未改善。跨运行重复经哈希确认，本次并非编译前去重成功。

DeepSeek另一真实响应引入未声明opcode及非SVA集合表达式；接口以未声明标识符拒绝，没有编译或将其记为RTL违例。未自动重写为可执行谓词。

没有新接受版本，没有完整151事务结果，没有冻结后独立结果。有限开发证据上的检出和拒绝记录不能推广为形式化证明或全局无退化。
'''
    (out/'CASE_TRACE.md').write_text(trace,encoding='utf-8')
    files=[p for root in runs+audits for p in root.rglob('*') if p.is_file()]
    files+=list((ROOT/'scripts').glob('research60*.py'))
    manifest={str(p.relative_to(ROOT)).replace('\\','/'):sha(p) for p in files}
    (out/'content_versions.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print('REPORT_SAVED',out,'accepted=False',flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();run(a.out.resolve())
