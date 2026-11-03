"""Derive human-readable traces and cost roles from completed research50 records.

Read-only with respect to all model/native/frozen/test artifacts. No calls.
"""
import argparse
from collections import defaultdict
from pathlib import Path
import shutil
import research50_controlled_ablation as campaign

read,dump=campaign.read,campaign.dump


def build(run,prep,out):
    result=read(out/'results.json')
    assert result['audit_passed'] and read(out/'additional_audit.json')['passed']
    assert not (out/'CASE_TRACE.md').exists()
    initial=read(prep/'shared_initial.json')
    cost=read(out/'cost.json');setup=read(prep/'local_cost.json')['total']
    categories={}
    def costs(records):
        return dict(compiles=sum(r['kind']=='compile' for r in records),
                    executes=sum(r['kind']=='execute' for r in records),
                    smoke_executes=sum(r['kind']=='execute' and r['smoke'] for r in records),
                    command_wall_seconds=sum(r['wall_seconds'] or 0 for r in records))
    for group,needle in [('visible_current','/visible_native/'),('shared_history','/history_native/'),('independent_measurement','evaluation/')]:
        categories[group]=costs([r for r in cost['native_commands'] if needle in r['path']])
    assert sum(r['executes'] for r in categories.values())==cost['total']['native_execute_calls']
    assert sum(r['compiles'] for r in categories.values())==cost['total']['native_compile_calls']
    model_groups={}
    for stream in ('ordinary','search'):
        calls=[c for c in cost['model_calls'] if '/'+stream+'/' in c['path']]
        assert len(calls)==3 and all(c['retries']==0 for c in calls)
        model_groups[stream]=dict(calls=len(calls),prompt_tokens=sum(c['prompt_tokens'] for c in calls),
                                 output_tokens=sum(c['completion_tokens'] for c in calls))
    breakdown=dict(real_native=categories,real_model=model_groups,preparation=setup,
        new_preparation_plus_run=dict(model_calls=cost['total']['model_calls'],
            native_compile_calls=cost['total']['native_compile_calls']+setup['native_compile_calls'],
            native_execute_calls=cost['total']['native_execute_calls']+setup['native_execute_calls'],
            smoke_executes=cost['total']['compile_smoke_execute_calls']+setup['compile_smoke_execute_calls'],formal_calls=0),
        cost_roles='Each full history replay is shared by paired arms: post-decision measurement for A/B, admission treatment for C/D. Do not add paired logical charges to physical costs.',
        reused_search=dict(physical_model_calls=0,contract_queries_across_three_seeds=12,
            contract_native_query_executions=72,
            accounting='Already included in research42 search benchmark; shared compile/smoke overhead remains in the original cost records. Not new research50 executions. B/D each logically require4 queries/24 executions per seed.'),
        monetary_cost=None)
    dump(out/'cost_roles.json',breakdown)
    variants=[]
    lines=['# research50：真实提案、拒绝与独立失败轨迹','',
        '三个种子均完成普通/搜索各一次真实调用。以下数值为义务×采样周期证据行，不是独立Bug数量。模型响应和原生记录未改写。','',
        '公共原始a4：','```systemverilog',next(a['property'] for a in initial['assertions'] if a['id']=='a4'),'```','',
        '契约搜索的两类有效见证：持续背压撤销valid、解除边界撤销valid。独立事务参考检查确认输入合法、握手接受一致、错误侧违例而正确侧满足义务；不是仅靠波形差异判定。初始性质触发但约束不足。', '',
        '|种子/反馈|模型操作|当前误报/关键unknown|历史误报/关键unknown|普通/门控接纳|',
        '|---|---|---:|---:|---|']
    for seed in campaign.base.SEEDS:
        for stream in ('ordinary','search'):
            folder=run/f's{seed}/{stream}'
            pair=read(folder/'pair_result.json');edit=read(folder/'model_call/model_edit.json')
            candidate=read(folder/'model_call/candidate.json')
            changed=campaign.interface.executable_hash(candidate)!=campaign.interface.executable_hash(initial)
            variants.append(dict(seed=seed,stream=stream,operation=edit['operation'],executable_changed=changed,
                executable_hash=campaign.interface.executable_hash(candidate),
                current_accepted=pair['plain']['accepted'],history_gated_accepted=pair['gated']['accepted']))
            cur=pair['current']['counts'];hist=pair['history']['counts']
            lines.append(f'|{seed}/{stream}|{edit["operation"]}|{cur["false_positives"]}/{cur["unknown"]}|{hist["false_positives"]}/{hist["unknown"]}|{pair["plain"]["accepted"]}/{pair["gated"]["accepted"]}|')
    changed_eligible=[v for v in variants if v['executable_changed'] and v['current_accepted']]
    dump(out/'executable_proposal_classification.json',dict(proposals=variants,
        changed_current_pass=len(changed_eligible),
        unique_changed_executable_proposals=len({v['executable_hash'] for v in variants if v['executable_changed']}),
        history_gate_repair_benefit_estimable=bool(changed_eligible)))
    lines+=['','普通反馈的keep只表示没有修改，不计新修复。三个搜索提案在当前检查已拒绝，因而其历史失败不构成历史门控的额外拒绝收益。','',
            '## 案例一：4201的搜索提案','']
    for seed in (4201,4211):
        folder=run/f's{seed}/search';pair=read(folder/'pair_result.json')
        candidate=read(folder/'model_call/candidate.json');edit=read(folder/'model_call/model_edit.json')
        if seed==4211:lines+=['','## 案例二：4211增加复位条件','']
        lines+=['原始模型生成的修改：','```systemverilog',next(a['property'] for a in candidate['assertions'] if a['id']==edit['assertion_id']),'```']
        target=pair['plain']['target_gate']['target_rows']
        lines+=['本轮原生目标采样：']
        for t in target:
            a=t['edited_assertion']
            lines.append(f'- 周期{t["check_cycle"]}，编辑性质前件触发={a["trigger"]}，失败={a["failed"]}，因果检出={a["causal_detection"]}；证据ID `{t["evidence_id"]}`。')
        lines+=['','当前valid为0时前件关闭，不能检出valid提前撤销；同周期比较过去数据又对合法事务造成误报。关键unknown没有被当作通过。当前和历史检查均拒绝，回退到公共初始版本。',
            f'原始响应及SVA：`{folder.relative_to(campaign.ROOT).as_posix()}/model_call/`；原生当前/历史回放分别在`visible_native/`、`history_native/`。']
    freeze=read(run/'all_arms_freeze.json');hashes={v['frozen_hash'] for v in freeze.values()}
    assert len(hashes)==1  # Actual completed outcome of this batch, not a runner assumption.
    h=next(iter(hashes));summary=read(run/f'evaluation/{h}/independent/summary.json')
    split=read(run/'common_independent_split.json');cases=split['boundary_cases']+split['drain_cases']
    parent=dict(parent='axis_fifo_RTL_with_explicit_artificial_faults',historical_upstream_bug_verified=False,
        parent_complete_pass=summary['all_five_pass_on_first_attributed_evidence'],
        unique_frozen_versions=1,logical_groups=12,independent_scenarios=56,independent_inputs=48,
        obligations=summary['metrics']['obligations'],counts=summary['metrics']['counts'],
        unexposed_scenarios=summary['metrics']['scenarios_without_first_attributable_target'],
        scope='First attributable evidence only; subsequent unknowns remain. Simulation, not formal proof. Known fault families with fresh inputs, not unseen bug-family generalization.')
    dump(out/'parent_result.json',parent)
    lines+=['','## 冻结后独立测量','',f'12逻辑组全部保留同一哈希 `{h}`；没有新接受修改。全部冻结之后才生成seed={split["seed"]}的56场景/48新输入，与694种排除输入无重复。深度'+str(sorted({c['depth'] for c in cases}))+ '，仅执行协议列出的具体参数组合，不代表全部参数笛卡尔积。','',
        '|义务|检出|漏报|误报|关键unknown|触发|','|---|---:|---:|---:|---:|---:|']
    for obligation,m in parent['obligations'].items():
        lines.append('|'+obligation+'|'+'|'.join(str(m[k]) for k in ('detections','misses','false_positives','unknown','triggers'))+'|')
    lines+=['',f'整例通过={parent["parent_complete_pass"]}；后续归因unknown={parent["counts"]["later_attribution_unknown"]}，无首个可归因目标场景={len(parent["unexposed_scenarios"])}。这些场景不计目标检出成功，逐项名单在parent_result.json。排空曝光检查通过，但背压稳定性20条漏报使整例失败。',
        '','本批独立结果没有进入模型、修改或候选选择；本轮在此终止。如后续利用这些失败进行改进，必须把相应整批转为开发数据，再创建新的独立批次。','',
        '## 实际成本','',f'真实运行：6模型调用，输入{cost["total"]["prompt_tokens_total"]}、输出{cost["total"]["completion_tokens_total"]} tokens；38编译、1434执行（含38冒烟），0形式化。加本轮准备合计42编译、1452执行（含42冒烟）。金额不可用。',
        '','普通/搜索实际token不完全对齐、历史处理/测量角色及复用搜索成本见cost_roles.json；不能把共享执行重复收费或计为独立样本。',
        '','复核入口（不调用模型/仿真，使用新报告目录）：','```powershell',
        'wsl -- python3 scripts/research50_ablation_report.py --run deliverables/research50_real_20261022_r01 --out deliverables/research50_report_NEW','```']
    (out/'CASE_TRACE.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    shutil.copy2(__file__,out/'delivery_report_source.py')
    print('DELIVERY_REPORT',len(variants),'proposals;',len(changed_eligible),'changed current-pass; parent_pass',parent['parent_complete_pass'])


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('run','prepared','report'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();build(a.run.resolve(),a.prepared.resolve(),a.report.resolve())
