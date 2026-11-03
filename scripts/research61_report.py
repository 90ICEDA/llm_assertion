"""Summarize audited real refinement; no generation, simulation or editing SVA."""
import argparse
import json
from pathlib import Path
import research61_contrast_refine as trial
g=trial.g


def run(root,audit,out):
    out.mkdir(parents=True,exist_ok=False)
    verified=g.read(audit/'audit.json');assert verified['passed']
    status=g.read(root/'outcome.json');cost=g.read(root/'cost.json')['total']
    versions=g.read(audit/'versions.json');details=[]
    rows=[]
    for v in sorted(root.glob('v[0-9]*')):
        decision=g.read(v/'decision.json');call=g.read(v/'model_call/result.json')
        edit=g.read(v/'model_call/model_edit.json') if (v/'model_call/model_edit.json').exists() else None
        item=dict(version=v.name,decision=decision,model_call=call,model_edit=edit)
        if (v/'alignment/alignment_gate.json').exists():
            gate=g.read(v/'alignment/alignment_gate.json');native=g.read(v/'alignment/result.json')
            focus=gate['focus12']['phases']
            item.update(small_gate=gate,counts=native['counts'],focus=focus)
            rows.append(f"| {v.name} | {focus['first']['detected']}/3 | {focus['held']['detected']}/9 | {sum(x['triggered_revision_points'] for x in focus.values())}/24 | {native['counts']['false_positives']} | {native['counts']['unknown']} | {'通过' if gate['accepted'] else '拒绝'} |")
        else:rows.append(f"| {v.name} | 未执行 | 未执行 | 未执行 | 不适用 | 不适用 | 原生执行前拒绝 |")
        full={}
        for cohort in ('history','search'):
            if (v/cohort/'result.json').exists():full[cohort]=g.read(v/cohort/'result.json')['counts']
        item['full151']=full;details.append(item)
    accepted=status['status']=='accepted_development_only'
    state=dict(accepted=accepted,scope='Ibex #166 original decoder; finite development evidence',
               versions=details,full151_run=any(bool(x['full151']) for x in details),
               independent_test='not_run',frozen_for_independent='not_created',remote_calls=0)
    g.dump(out/'status.json',state);g.dump(out/'cost.json',cost)
    table='\n'.join(rows)
    summary=f'''# research61：真实模型细化与原生验收

结果：{'得到新的开发阶段接受版本' if accepted else '未得到新的接受版本'}。模型输出由本地缓存 Qwen 7B 实际生成，没有人工替换条件或位号。

| 版本 | 首周期OP | 保持阶段OP | 必要触发（前后RTL） | 合法误报 | 关键unknown | 小范围门控 |
| --- | --- | --- | --- | --- | --- | --- |
{table}

固定范围：9个开发事务、240条采样记录，48目标点；聚焦12点是其子集。只有小门通过才执行115历史＋36搜索事务及420 OP＋270 BRANCH保护保持。每条模型性质保留原BRANCH，原始RTL、独立ISA规则和接受标准未改。

本轮实现：从真实原生记录计算指令解码字段，把合法误报与必要违例成对反馈；18组覆盖240行，逐行核验位域、样本、阶段、配置、独立期望和实际输出。旧错误OP签名纳入跨运行编译前去重。本地模型请求实际包含开发对照表与来源绑定RTL片段；未提供手写成功SVA或独立测试。模型和提示范围沿用本地探索路径，不能用于声称受控机制增益。

完整151是否执行：{state['full151_run']}。最终接受：{accepted}。独立测试未执行，尚未创建独立测试冻结清单。单项检出改善不等于整个历史案例独立通过，不是整核验证或形式化证明。

实际成本：本地生成{cost['model_calls']}次、远程0次、原生编译{cost['native_compile_calls']}次/执行{cost['native_execute_calls']}次、形式化{cost['formal_calls']}次；tokens输入{cost['prompt_tokens_total']}、输出{cost['completion_tokens_total']}，缺用量调用{cost['usage_unavailable_calls']}次。模型加载管理调用另记在运行目录model_load；原生执行数含编译检查执行，不重复累加。离线审计{len(verified['checks'])}项通过，仅确认记录和门控一致性。

## 命令

实际运行目录：`{root.relative_to(g.ROOT).as_posix()}`。下面复核不新增模型或仿真调用，输出目录须不存在：

```powershell
wsl -- python3 scripts/research60_local_audit.py --run {root.relative_to(g.ROOT).as_posix()} --out deliverables/research61_audit_NEW
wsl -- python3 scripts/research61_report.py --run {root.relative_to(g.ROOT).as_posix()} --audit {audit.relative_to(g.ROOT).as_posix()} --out deliverables/research61_report_NEW
```

真实细化复现入口（新目录，最多2次本地生成，有实际计算成本）：

```powershell
wsl -- python3 scripts/research61_contrast_refine.py --out deliverables/research61_local_NEW
```

详细原始响应、性质、决定、日志和采样保存在各vN目录。机器可读汇总见status.json；成本见cost.json。原research60的78条误报结果与其他历史失败不改写。
'''
    (out/'SUMMARY.md').write_text(summary,encoding='utf-8')
    trace=['# 实际提案与验证轨迹','', '起点：research60真实Qwen性质检出12/12，但78条合法误报；旧性质和真实失败仅作为开发反馈。']
    for item in details:
        trace.extend(['',f"## {item['version']}",'','```json',json.dumps(item['model_edit'],ensure_ascii=False,indent=2),'```',
                      '', '实际接受/拒绝：','```json',json.dumps(item['decision'],ensure_ascii=False,indent=2),'```',
                      '', '完整151记录：','```json',json.dumps(item['full151'],ensure_ascii=False,indent=2),'```'])
    trace.append('\n没有冻结后独立结果。若将来依据独立失败修改，须将该批数据转为开发数据并重新准备独立验收。\n')
    (out/'CASE_TRACE.md').write_text('\n'.join(trace),encoding='utf-8')
    files=[p for d in (root,audit) for p in d.rglob('*') if p.is_file()]+[Path(__file__),Path(trial.__file__)]
    g.dump(out/'content_versions.json',{p.relative_to(g.ROOT).as_posix():g.old.digest(p) for p in files})
    print('REPORT',status['status'],flush=True)


def campaign(out):
    out.mkdir(parents=True,exist_ok=False)
    paths=['research61_local_20261023_r01','research61_ast_20261023_r01','research61_history_refine_20261023_r01']
    audits=['research61_text_audit_20261023_r02','research61_ast_audit_20261023_r01','research61_history_audit_20261023_r01']
    records=[];lines=[]
    for name,audit_name in zip(paths,audits):
        root=g.ROOT/'deliverables'/name;review=g.read(g.ROOT/'deliverables'/audit_name/'audit.json');assert review['passed']
        record=dict(run=name,outcome=g.read(root/'outcome.json'),cost=g.read(root/'cost.json')['total'],audit_checks=len(review['checks']),versions=[])
        for v in sorted(root.glob('v[0-9]*')):
            item=dict(version=v.name,decision=g.read(v/'decision.json'),model_output=g.read(v/'model_call/model_edit.json'))
            if (v/'alignment/result.json').exists():
                item['small_counts']=g.read(v/'alignment/result.json')['counts'];item['focus']=g.read(v/'alignment/focus_gate.json')
                small=item['small_counts'];phases=item['focus']['phases'];detect=sum(p['detected'] for p in phases.values())
                check=f"{detect}/12；误报{small['false_positives']}；unknown{small['unknown']}"
            else:check='重复性质，原生执行前拒绝'
            full={}
            for cohort in ('history','search'):
                if (v/cohort/'result.json').exists():full[cohort]=g.read(v/cohort/'result.json')['counts']
            item['full']=full
            full_text=(f"检出{sum(x['detections'] for x in full.values())}/690；误报{sum(x['false_positives'] for x in full.values())}；unknown{sum(x['unknown'] for x in full.values())}" if full else '未执行')
            lines.append(f"| {name}/{v.name} | {check} | {full_text} | {'接受' if item['decision']['accepted'] else '拒绝'} |")
            record['versions'].append(item)
        records.append(record)
    final=records[-1];accepted=final['outcome']['status']=='accepted_development_only'
    totals={key:sum(r['cost'][key] for r in records) for key in ('model_calls','prompt_tokens_known_subtotal','completion_tokens_known_subtotal','usage_unavailable_calls','native_compile_calls','native_execute_calls','model_wall_seconds_known_subtotal','formal_calls')}
    totals.update(remote_calls=0,local_model_management_calls=3)
    totals['prompt_tokens_total']=totals['prompt_tokens_known_subtotal'] if not totals['usage_unavailable_calls'] else None
    totals['completion_tokens_total']=totals['completion_tokens_known_subtotal'] if not totals['usage_unavailable_calls'] else None
    result=dict(accepted=accepted,records=records,cost=totals,independent='not_run',scope='original Ibex decoder; finite development only')
    g.dump(out/'status.json',result)
    table='\n'.join(lines)
    verdict='已消除已验收开发范围内的合法误报，并保持全部目标检出。' if accepted else '原小范围78条误报已消除，但最终完整接受标准仍未通过。'
    text=f'''# research61 最终结果

{verdict}真实模型输出未经人工位号替换或条件修正；接受由原生执行与独立ISA规则共同决定。

| 实际版本 | 9事务小门（含聚焦12点） | 完整151事务 | 最终决定 |
| --- | --- | --- | --- |
{table}

12个点包含首周期3点、保持9点；必要触发跨前后RTL共24点。690个目标是420 OP＋270 BRANCH的有限采样/配置点，不是690个独立Bug。151事务共3996条记录。

实际轨迹：两轮文本模型仍重复旧funct3性质，被编译前去重拒绝；随后真实模型以AST首次生成bit28检查，原小门12/12、误报0，但遗漏opcode范围而在历史回放中产生636条合法误报，被防退化门控拒绝。再把实际合法BRANCH的首周期/保持误报交给模型，以同一标准复验。全部中间版本及拒绝理由保留，不把小门通过追认为完整接受。

实现复用了原生门控、历史回放、模型传输及research17语法树渲染。新增的解码对照表与原生240行逐项核验；AST接口保留全部32个位选，程序仅按模型AST加括号生成SVA。OP阶段不展示固定BRANCH文本，但实际编译仍完整保留其原模型性质。错误条件没有由程序自动修正为正确答案。

成本：本地真实模型提交{totals['model_calls']}次，加载管理请求3次，远程0；新增原生编译{totals['native_compile_calls']}次、执行{totals['native_execute_calls']}次，形式化0。输入/输出tokens为{totals['prompt_tokens_total']}/{totals['completion_tokens_total']}。准备阶段只复核旧日志，不计为新增仿真。各组审计分别{', '.join(str(r['audit_checks']) for r in records)}项通过；审计通过不等于性质通过。

结论限于原始decoder模块的上述开发证据。没有新独立测试结果、没有整核验证或形式化证明，不能宣称全局无退化。未运行受控机制消融，不能把本次表示与反馈变更的结果归因为某一机制的独立收益。

## 复现与产物

```powershell
# 原样审计最终运行，不新增模型/仿真，输出目录须不存在
wsl -- python3 scripts/research60_local_audit.py --run deliverables/research61_history_refine_20261023_r01 --out deliverables/research61_final_audit_NEW
# 实际执行过的本地细化入口；重跑须换新目录，会产生计算成本
wsl -- python3 scripts/research61_ast_feedback.py --out deliverables/research61_history_refine_NEW
# 仅重建汇总
wsl -- python3 scripts/research61_report.py --campaign --out deliverables/research61_final_NEW
```

最终原始模型响应、AST、渲染版本和SVA：`deliverables/research61_history_refine_20261023_r01/v0/model_call/`。
小门及历史/搜索原生日志：同一v0下`alignment/`、`history/`、`search/`。
接受/拒绝理由：同一v0下`decision.json`；义务映射为`mapping.json`。
机器可读全程结果与成本：本目录`status.json`。模型原始输出与接受轨迹：`CASE_TRACE.md`。

后续：{'为新接受版本另建冻结清单并进行未参与本轮的独立验收。' if accepted else '继续根据最终拒绝原因让真实模型修正；本轮结果不可冻结为接受版本。'} stat及原始FIFO presented未确认项保持unknown。
'''
    (out/'SUMMARY.md').write_text(text,encoding='utf-8')
    trace=['# 真实模型轨迹']
    for record in records:
        for v in record['versions']:
            decision=v['decision'];short={k:val for k,val in decision.items() if k!='reasons'}
            short['reason_kinds']=[r.get('kind') for r in decision.get('reasons',[])]
            trace+=['',f"## {record['run']}/{v['version']}",'','```json',json.dumps(v['model_output'],ensure_ascii=False,indent=2),'```','',
                '原生计数：','```json',json.dumps(dict(small=v.get('small_counts'),full=v['full'],decision=short),ensure_ascii=False,indent=2),'```']
    (out/'CASE_TRACE.md').write_text('\n'.join(trace)+'\n',encoding='utf-8')
    files=[p for name in paths+audits for p in (g.ROOT/'deliverables'/name).rglob('*') if p.is_file()]
    files+=list((g.ROOT/'scripts').glob('research61*.py'))+[g.ROOT/'scripts/research60_local_audit.py']
    g.dump(out/'content_versions.json',{p.relative_to(g.ROOT).as_posix():g.old.digest(p) for p in files})
    print('CAMPAIGN',accepted,totals,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('run','audit','out'):p.add_argument('--'+n,type=Path,required=(n=='out'))
    p.add_argument('--campaign',action='store_true')
    a=p.parse_args()
    if a.campaign:campaign(a.out.resolve())
    else:run(a.run.resolve(),a.audit.resolve(),a.out.resolve())
