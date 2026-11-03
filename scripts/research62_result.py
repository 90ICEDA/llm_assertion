"""Report actual category-component generation and full native acceptance."""
import argparse
import json
from pathlib import Path
import research62_category as trial
g=trial.g


def run(root,audit,out):
    verified=g.read(audit/'audit.json');assert verified['passed']
    out.mkdir(parents=True,exist_ok=False)
    outcome=g.read(root/'outcome.json');cost=g.read(root/'cost.json')['total'];versions=[];rows=[];trace=[]
    previous=None;campaign_cost=dict(cost)
    if (root/'comparison_adapter_snapshot.py').exists():
        prior=g.ROOT/'deliverables/research62_local_20261023_r01'
        prior_audit=g.read(g.ROOT/'deliverables/research62_category_audit_20261023_r01/audit.json');assert prior_audit['passed']
        previous=dict(run=prior.relative_to(g.ROOT).as_posix(),outcome=g.read(prior/'outcome.json'),cost=g.read(prior/'cost.json')['total'],audit_checks=len(prior_audit['checks']),category_failures_per_version=2304)
        for k in ('model_calls','native_compile_calls','native_execute_calls','formal_calls','prompt_tokens_total','completion_tokens_total'):
            campaign_cost[k]=cost[k]+previous['cost'][k] if cost[k] is not None and previous['cost'][k] is not None else None
    for v in sorted(root.glob('v[0-9]*')):
        decision=g.read(v/'decision.json');category=g.read(v/'model_call/category_gate.json')
        item=dict(version=v.name,decision=decision,category={k:x for k,x in category.items() if k!='checks'},
                  model_output=g.read(v/'model_call/model_edit.json'),full={})
        if (v/'alignment/result.json').exists():
            item['small']=g.read(v/'alignment/result.json')['counts']
            item['focus']=g.read(v/'alignment/focus_gate.json')['phases']
            item['small_gate']=g.read(v/'alignment/alignment_gate.json')['accepted']
        for cohort in ('history','search'):
            if (v/cohort/'result.json').exists():
                r=g.read(v/cohort/'result.json')
                item['full'][cohort]=dict(counts=r['counts'],required_untriggered=len(r['required_untriggered']))
        full=item['full'];small=item.get('small',{})
        rows.append(f"| {v.name} | {category.get('checked',0)-category.get('failed',0)}/{category.get('checked',0)} | {sum(p['detected'] for p in item.get('focus',{}).values())}/12 | {small.get('false_positives','未执行')} | {sum(r['counts']['detections'] for r in full.values())}/690 | {sum(r['counts']['false_positives'] for r in full.values()) if full else '未执行'} | {'接受' if decision['accepted'] else '拒绝'} |")
        versions.append(item)
        trace += ['',f'## {v.name}','', '实际新模型输出：','```json',json.dumps(item['model_output'],ensure_ascii=False,indent=2),'```']
        if (v/'model_call/candidate.sva').exists():trace+=['','按模型选择组合并实际执行的SVA：','```systemverilog',(v/'model_call/candidate.sva').read_text().strip(),'```']
        trace+=['','实际结果：','```json',json.dumps({k:x for k,x in item.items() if k not in ('model_output','decision')},ensure_ascii=False,indent=2),'```',f"接受决定：{decision['accepted']}；完整依据：{v.relative_to(g.ROOT).as_posix()}/decision.json"]
    accepted=outcome['status']=='accepted_development_only'
    if accepted:
        a=next(v for v in versions if v['decision']['accepted'])
        assert a['category']['accepted'] and a['small_gate']
        assert all(p['detected']==p['exposed'] for p in a['focus'].values())
        assert sum(p['triggered_revision_points'] for p in a['focus'].values())==24
        assert sum(r['counts']['detections'] for r in a['full'].values())==690
        assert all(r['counts'][k]==0 for r in a['full'].values() for k in ('misses','false_positives','unknown'))
        assert all(r['required_untriggered']==0 for r in a['full'].values())
        assert all(p['lost']==0 for p in a['decision']['target_preservation'].values())
    g.dump(out/'status.json',dict(outcome=outcome,versions=versions,cost=cost,previous_category_failures=previous,campaign_cost=campaign_cost,independent_test='not_run',scope='original Ibex decoder finite development replay'))
    verdict='已通过完整151事务接受检查。' if accepted else '尚未通过完整151事务接受检查。'
    entry='research62_comparison.py' if previous else 'research62_category.py'
    text=f'''# research62：类别适用条件与完整151事务验收

{verdict}本轮真实本地Qwen只生成类别过滤AST及组合运算符，保留research61实际模型生成的bit28子性质和原模型BRANCH性质。程序仅按这些模型选择进行语法组合，没有手工替换位号、类别值或运算符。这是组件细化，不是重新自由生成整条性质。

| 版本 | 独立类别判定一致 | 聚焦OP检出 | 小门误报 | 完整目标检出 | 完整合法误报 | 决定 |
| --- | --- | --- | --- | --- | --- | --- |
{chr(10).join(rows)}

类别门控逐项检查4236条既有采样记录，包括9事务小门和151事务历史/搜索回放的原有记录；这些并非独立测试。原生新回放包括首周期3点、保持9点及跨前后RTL必要触发24点。完整151事务由115历史＋36搜索组成，共3996条记录，目标420 OP＋270 BRANCH=690点。样本/配置点数不等于独立Bug数。

实际各阶段计数、误报、漏报、unknown、必要触发和保护保持见status.json；义务—断言—证据映射在运行目录各vN/mapping.json。任何关键unknown或保护丢失均不按通过处理。拒绝版本与research61的636条误报保持原样。

本轮实际成本：本地生成{cost['model_calls']}次，远程0次；原生编译{cost['native_compile_calls']}次、执行{cost['native_execute_calls']}次、形式化{cost['formal_calls']}次。输入/输出tokens={cost['prompt_tokens_total']}/{cost['completion_tokens_total']}。一次本地模型加载管理请求另存model_load，不算生成；准备阶段复核旧日志不算新仿真。结果审计{len(verified['checks'])}项通过，审计通过只说明结果一致性。

{'此前两轮类别AST仅返回裸opcode字段，各错分2304/4236，被前置门控拒绝，未执行原生仿真；这些失败已通过173项记录审计，不能改算成功。当前接口要求模型明确输出field/comparison/value/combine，语法转换不补选任何缺失值。含前两轮的本次任务合计' if previous else '本次任务合计'}本地生成{campaign_cost['model_calls']}次，原生编译/执行{campaign_cost['native_compile_calls']}/{campaign_cost['native_execute_calls']}次，tokens={campaign_cost['prompt_tokens_total']}/{campaign_cost['completion_tokens_total']}。仅限本次research62，不重复计入research61已有运行。

## 可复制命令

```powershell
# 本轮实际生成/细化入口；重跑需要新目录，有本地模型计算成本
wsl -- python3 scripts/{entry} --out deliverables/research62_local_NEW
# 复核已有运行，不调用模型、不新增仿真
wsl -- python3 scripts/research60_local_audit.py --run {root.relative_to(g.ROOT).as_posix()} --out deliverables/research62_audit_NEW
wsl -- python3 scripts/research62_result.py --run {root.relative_to(g.ROOT).as_posix()} --audit {audit.relative_to(g.ROOT).as_posix()} --out deliverables/research62_report_NEW
```

原始响应流、模型输出、组合AST和实际SVA在 `{root.relative_to(g.ROOT).as_posix()}/vN/model_call/`；原生RTL、日志、事务和波形在各vN的alignment/history/search目录。断言内容版本哈希由outcome.json记录；完整来源清单在本目录content_versions.json。仓库无可用Git提交记录，不补造历史提交。

结论仅限原始decoder模块和上述有限开发范围，不是整核验证、形式化证明或全局无退化。尚未运行新的冻结后独立测试。{'下一步应保存完整冻结清单后执行未参与生成、分类门控和修改的新指令字及配置。' if accepted else '仍需依据实际拒绝诊断得到通过完整接受检查的真实模型版本。'} stat及原始FIFO presented未确认项仍为unknown。
'''
    (out/'SUMMARY.md').write_text(text,encoding='utf-8')
    (out/'CASE_TRACE.md').write_text('# 真实类别补齐与原生轨迹\n\n起点：research61的真实bit28检查在小门12/12、误报0，但历史合法BRANCH误报636，未接受。固定子性质来自其原始模型AST；本轮类别与组合操作全部来自新模型响应。\n'+'\n'.join(trace)+'\n',encoding='utf-8')
    files=[p for d in (root,audit) for p in d.rglob('*') if p.is_file()]+[Path(__file__),Path(trial.__file__),Path(trial.ast.__file__),g.ROOT/'scripts/research60_local_audit.py']
    files += [trial.SOURCE/'v0/model_call/model_edit.json',trial.base.P/'protected_branch.json']
    if previous:
        files += [g.ROOT/'scripts/research62_comparison.py']
        files += [p for p in (g.ROOT/previous['run']).rglob('*') if p.is_file()]
    g.dump(out/'content_versions.json',{p.relative_to(g.ROOT).as_posix():g.old.digest(p) for p in files})
    print('RESEARCH62_REPORT',accepted,'model_calls',cost['model_calls'],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('run','audit','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();run(a.run.resolve(),a.audit.resolve(),a.out.resolve())
