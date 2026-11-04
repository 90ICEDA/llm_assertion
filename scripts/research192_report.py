"""One read-only entry point for new experiments and explicitly historical evidence.

Missing experiments stay not_run; never manufacture results from protocol caps.
"""
import argparse
from collections import Counter
import hashlib
import html
import json
import os
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
D=ROOT/'deliverables'


def load(path, default=None):
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else default


def summarize_arms(rows, field, names):
    result=[]
    for name in names:
        group=[r for r in rows if r.get(field)==name]
        if not group:
            result.append(dict(arm=name,status='not_run_or_pending',seeds=0,
                               accepted=None,FP=None,FN=None,regressions=None,effective_rounds=None,calls=0,tokens=None))
            continue
        result.append(dict(arm=name,status='recorded_attempts',statuses=dict(Counter(r['status'] for r in group)),seeds=len(group),
            accepted=sum(r['accepted'] for r in group),FP=sum(r['final_fp'] for r in group),FN=sum(r['final_fn'] for r in group),
            target_transactions=sum(r['final_targets'] for r in group),
            protected_transactions=sum(r['final_detected'] for r in group),
            regressions=sum(r['regression_proposals'] for r in group),accepted_regressions=sum(r['accepted_regressions'] for r in group),
            effective_rounds=sum(r['effective_rounds'] for r in group),calls=sum(r['model_calls'] for r in group),
            unknown=sum(r['final_unknown'] for r in group),
            infrastructure_failures=sum(bool(r.get('infrastructure_failure')) or 'infrastructure' in r['status'] for r in group),
            proposal_unknowns=sum(bool(r.get('proposal_unknown')) for r in group),
            generated_candidates=sum(bool(r['candidate_generated']) for r in group),
            failure_reasons=dict(Counter(r['failure_reason'] for r in group if r.get('failure_reason'))),
            tokens=sum(r['prompt_tokens']+r['completion_tokens'] for r in group) if all(r.get('prompt_tokens') is not None and r.get('completion_tokens') is not None for r in group) else None,
            compile_attempts=sum(r['physical_native_compiles'] for r in group),
            native_seconds=sum(r['native_seconds'] for r in group) if all(r.get('native_seconds') is not None for r in group) else None,
            wall_seconds=sum(r['wall_seconds'] for r in group) if all(r.get('wall_seconds') is not None for r in group) else None))
    return result


def table(rows,fields=None):
    if not rows:return '<p>尚未完成；不计作通过或零收益。</p>'
    fields=fields or list(dict.fromkeys(k for r in rows for k in r))
    def cell(value):
        if value is None:return '— / unavailable'
        if isinstance(value,(dict,list)):return html.escape(json.dumps(value,ensure_ascii=False))
        return html.escape(str(value))
    return '<div class="scroll"><table><thead><tr>'+''.join('<th>'+html.escape(k)+'</th>' for k in fields)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+cell(row.get(k))+'</td>' for k in fields)+'</tr>' for row in rows)+'</tbody></table></div>'


def interactions(rows):
    result=[]
    for seed in sorted({r['seed'] for r in rows}):
        group={r['arm']:r for r in rows if r['seed']==seed}
        if set(group)!={'A0','A1','A2','A3'}:continue
        if any(r.get('causal_comparison_eligible') is False or r.get('infrastructure_failure') or 'infrastructure' in r['status'] for r in group.values()):
            result.append(dict(seed=seed,development_protection_interaction=None,
                status='ineligible_infrastructure_interruption',interpretation='All outcomes retained in arm table; interrupted pair cannot estimate algorithm interaction.'))
            continue
        rates={a:r['final_detected']/r['final_targets'] if r['final_targets'] else None for a,r in group.items()}
        value=None if any(v is None for v in rates.values()) else (rates['A3']-rates['A2'])-(rates['A1']-rates['A0'])
        result.append(dict(seed=seed,development_protection_interaction=value,
            formula='(A3-A2)-(A1-A0)',rates=rates,
            interpretation='Descriptive paired one-parent interaction; includes interface failures, not a population significance estimate.'))
    return result


def build(out,search,native,refinement,ablation,archive,independent,acquisition):
    out.mkdir(parents=True,exist_ok=True)
    sources={}
    def get(folder,name,default=None):
        file=folder/name
        if file.is_file():sources[str(file.relative_to(ROOT))]=hashlib.sha256(file.read_bytes()).hexdigest()
        return load(file,default)
    search_rows=get(search,'method_totals.json',[])
    search_curve=get(search,'cost_curve.json',[])
    native_rows=get(native,'method_totals.json',get(native,'summary.json',[]))
    r_rows=get(refinement,'results.json',[])
    a_rows=get(ablation,'results.json',[])
    for folder,rows,field in ((refinement,r_rows,'strategy'),(ablation,a_rows,'arm')):
        for row in rows:
            raw=get(folder/f"seed{row['seed']}"/row[field]/'model_call','result.json',{})
            error=raw.get('candidate_error') or raw.get('error') or {}
            row['failure_reason']='infrastructure_interruption' if row.get('infrastructure_failure') else (
                error.get('detail',error.get('type')) if isinstance(error,dict) else str(error))
    r_table=summarize_arms(r_rows,'strategy',['R0','R1','R2','R3'])
    a_table=summarize_arms(a_rows,'arm',['A0','A1','A2','A3'])
    acquisition=get(acquisition,'queries.json',[])
    for row in a_table:
        stream='active' if row['arm'] in ('A1','A3') else 'ordinary'
        acquired=[r for r in acquisition if r['stream']==stream]
        row['shared_acquisition_stream']=stream
        row['logical_queries_including_duplicates']=len(acquired)
        row['shared_stream_physical_compiles']=sum(r['native_compile_attempts'] for r in acquired)
        row['shared_stream_physical_executions']=sum(r['native_execution_attempts'] for r in acquired)
    acquisition_cost=dict(physical_queries=len(acquisition),
        physical_compiles=sum(r['native_compile_attempts'] for r in acquisition),
        physical_executions=sum(r['native_execution_attempts'] for r in acquisition),
        allocation='Each stream is shared by two arms. Sum physical acquisition ONCE; do not sum repeated stream columns across arms.')
    old_acceptance=get(archive,'historical_independent_acceptance.json',[])
    new_acceptance=get(independent,'results.json',[])
    readiness=get(archive,'cross_design_readiness.json',[])
    findings=get(archive,'mechanism_findings.json',[])
    interaction=interactions(a_rows)
    actual_costs=get(out,'actual_costs.json',{})
    model_audit=get(out,'model_call_audit.json',{})
    parent_acceptance=[]
    for row in new_acceptance:
        parent_acceptance.append(dict(parent_bug=row['parent_bug'],experiment=row['experiment'],arm=row['arm'],seed=row['seed'],
            required_obligations=1,exposed_scope_obligations_protected=int(row['exposed']>0 and row['misses']==0 and row['false_positives']==0 and row['unknown']==0),
            full_planned_scope_accepted=int(row['whole_scope_pass']),exposed_target_transactions=row['exposed'],
            detected_target_transactions=row['exposed']-row['misses'],unexposed_scenarios=row['missing_exposure'],
            interpretation='One parent and one required atomic-drop obligation; scenarios, seeds and versions do not increase parent count.'))
    summary=dict(search_diagnostic=search_rows,search_native=native_rows,refinement=r_table,acquisition_cost=acquisition_cost,interaction=interaction,
                 ablation=a_table,historical_independent=old_acceptance,new_independent=new_acceptance,
                 new_parent_obligation_acceptance=parent_acceptance,
                 parent_bug_count_rule='unique historical parent; neither seeds nor scenarios nor candidate versions are independent bugs',
                 no_unseen_fault_generalization_claim=True)
    (out/'tables.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    def relative(path):return os.path.relpath(path.resolve(),out.resolve()).replace('\\','/')
    def link(path,label):return '<a href="'+html.escape(relative(path))+'">'+html.escape(label)+'</a>'
    content='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>REGuard 核心机制实验</title>
<style>body{font:15px/1.65 system-ui,sans-serif;margin:36px auto;max-width:1250px;padding:0 20px;color:#17263a;background:#fafbfd}h1,h2{line-height:1.25}h2{margin-top:36px}table{border-collapse:collapse;background:white;font-size:13px}td,th{padding:9px;border:1px solid #d4dce7;text-align:left;vertical-align:top;max-width:450px}th{background:#eaf0f7}.scroll{overflow:auto}img{max-width:100%}.note{padding:14px;background:#fff2d8;border-left:4px solid #ae7918}a{color:#175fa4}</style>
<h1>REGuard：核心机制增强与统一实验入口</h1>
<p>2026-11-03。复用现有搜索、RTL执行器、独立参考监视器与接受门。旧实验只读索引，新增结果按实际执行记录生成。有限仿真不等于形式化证明。</p>
<div class="note">以下分别列出新搜索、真实模型修改、组合消融和历史独立验收。not_run 表示尚未执行；不使用手写对照或旧模型响应填充新模型实验。候选缺口、事务、场景、版本和父 Bug 分母分别保留。</div>'''
    content+='<h2>1 · S0–S3 证据搜索</h2><p>原11对候选 / 六父案例，程序诊断层；同候选、配对种子、实际查询预算。</p>'
    content+=table(search_rows,['method','queries','confirmed_gaps','fp_gaps','fn_gaps','exclusive_gaps','unknown_spec_queries','failed_queries','simulation_attempts','wall_seconds'])
    curve=search/'cost_curve.png'
    if curve.exists():content+='<img alt="有效缺口随实际仿真成本变化" src="'+relative(curve)+'">'
    content+='<p>'+link(search/'REPORT.md','搜索详细协议、解释和限制')+'</p>'
    content+='<p>复杂FIFO原生SVA层单独统计，不能把程序诊断结果当作原生SVA结果。</p>'
    content+=table(native_rows if isinstance(native_rows,list) else [native_rows],
        ['method','queries','confirmed_gaps','exclusive_gaps','native_executions','unknown','later_attribution_unknown','selector_seconds','query_wall_seconds'])
    if search_rows and isinstance(native_rows,list) and native_rows:
        totals={r['method']:r['confirmed_gaps'] for r in search_rows}
        first={m:min((r['queries_per_parent_seed'] for r in search_curve if r['method']==m and r['confirmed_gaps']==total),default=None) for m,total in totals.items()}
        content+='<p><strong>本轮搜索结论：</strong>'+html.escape(f"诊断层最终缺口 {totals}；达到各自最终缺口数的每单元查询次数 {first}。")+'结构分歧预测不等于可达行为区分，反复追逐未获得保护证书的义务可能消耗预算而没有新证据。按固定协议保留全部正负结果，未据此改测试集或重跑挑选种子。</p>'
    native_curve=native/'paired_mean_cost_curve.png'
    if native_curve.exists():content+='<img alt="逐种子配对平均新增缺口覆盖" src="'+relative(native_curve)+'">'
    comparison_fields=['arm','seeds','accepted','protected_transactions','target_transactions','FP','FN','regressions','accepted_regressions','effective_rounds','infrastructure_failures','calls','tokens']
    content+='<h2>2 · R0–R3 断言细化</h2><p>同原始SVA、原始证据、模型、两个配对种子，每组一次调用。共同初始是research188沿用的工程化部分保护种子，并非本轮新模型生成；本轮修改由真实模型输出。R3首轮测试定位与局部字段修改；多轮组合回退尚不在此试验范围。</p>'+table(r_table,comparison_fields)
    content+='<p>'+link(D/'research192_refinement_report_20261103_r01/REPORT.md','细化逐种子结果、接口失败与配对资格')+'</p>'
    content+='<h2>3 · A0–A3 组合消融</h2><p>A0普通搜索+基本双向反馈；A1主动搜索+基本反馈；A2普通搜索+局部细化及历史保护；A3两者启用。同一搜索流在细化组之间共享，实际成本与逻辑分配分别记账。</p>'+table(a_table,comparison_fields)
    content+='<p>证据获取总成本（物理运行只累计一次）：</p>'+table([acquisition_cost])
    content+='<p>配对组合增量（开发范围描述性统计）：</p>'+table(interaction)
    if any('infrastructure' in r['status'] for r in [*r_rows,*a_rows]):
        content+='<p class="note">磁盘耗尽中断了部分原生验收。对应模型响应、坏记录与已执行成本保留，终态保留初始候选；没有重发请求或重跑失败作业。全表保留该结果，但受影响种子不用于算法稳定性或组合增益的因果比较。后续只执行原预算内尚未提交的请求。最终独立验收检验实际保留版本，不能补写中断提案的开发接受。</p>'
    content+='<h2>4 · 跨设计独立验收</h2><p>以下是重新索引的历史结果，不冒充本轮新增验收。未曝光、未触发和unknown不按通过处理。</p>'+table(old_acceptance)
    content+='<p>本轮冻结版本的新输入验收：</p>'+table(new_acceptance,
        ['experiment','arm','seed','origin','passed','scenarios','exposed','misses','false_positives','missing_exposure','untriggered','unknown','native_failures','whole_scope_pass'])
    content+='<p>按父Bug和必要义务汇总：本轮新验收始终只有一个父Bug、一个原子丢帧义务。已曝光范围的保护与完整计划范围的验收分列；未曝光场景不能从分母中删除后宣布整批通过。</p>'+table(parent_acceptance,
        ['parent_bug','experiment','arm','seed','required_obligations','exposed_scope_obligations_protected','full_planned_scope_accepted','exposed_target_transactions','detected_target_transactions','unexposed_scenarios'])
    content+='<p>'+link(independent/'protocol.json','冻结后独立验收协议')+' · '+link(independent/'grades.json','逐场景验收与未曝光记录')+'</p>'
    if (independent/'audit.json').exists():
        get(independent,'audit.json',{})
        content+='<p>'+link(independent/'audit.json','独立验收557项只读复核')+'</p>'
    content+='<h2>机制正反例及适用边界</h2>'+table(findings)
    content+='<p>'+link(D/'research192_case_cards_20261103_r01/case_cards.html','原始SVA、修改、波形与验收案例卡')+'</p>'
    content+='<p>'+link(D/'research192_ablation_cards_20261103_r01/case_cards.html','本轮真实A3局部修改正例与A1历史检出替换负例')+'</p>'
    fault=D/'research192_fault_family_pilot_20261103_r01'
    fault_summary=get(fault,'summary.json',{})
    content+='<h2>故障族探索：原生资格实验</h2>'+table([fault_summary] if fault_summary else [])
    content+='<h2>跨设计准备度</h2>'+table(readiness)
    content+='<p>第三模块保持探索性：有效故障须编译、执行、独立判定可达违例；开发与测试按位置/算子分开。已有人工边界故障不自动成为独立泛化结果。新增Arbiter/Timer/UART的完成状态以准备度与实际执行记录为准。</p>'
    content+='<h2>实际成本与尚未完成的证据链</h2>'
    content+=table(actual_costs.get('rows',[]),['role','model_calls','prompt_tokens','completion_tokens','native_compile_commands','native_execution_commands','diagnostic_query_simulations','command_seconds','missing_or_truncated_command_records','terminal_status'])
    content+='<p>'+link(out/'actual_costs.json','实际成本完整账本')+'。命令耗时为并发工作量合计，不能当作整轮墙钟时间；磁盘事故缺失记录不补估，金额无账单依据，保持unknown。</p>'
    content+='<p>'+link(out/'model_call_audit.json','16次封存请求与真实调用审计')+'。调用摘要中的旧transport timeout元数据为180秒，实际attempt/generation deadline为授权的300秒；审计保留此不一致，不修改原始记录。</p>'
    content+='<p>本轮没有证明S3优于S2，也没有证明R3或A3总体更稳定。当前真实模型比较只覆盖一个FIFO父Bug、两个种子、每组一轮；历史跨设计结果不能充当本轮跨设计消融。Timer/UART及flush/完整流水线新适配、三种变异策略的公平比较、开发故障增强对未见故障的收益、多轮义务组合，仍未完成。</p>'
    content+='<p>'+link(archive/'archive_index.json','历史实验产物索引')+' · '+link(out/'tables.json','机器可读四组表')+' · '+link(out/'source_bindings.json','本报告源文件哈希')+'</p></html>'
    (out/'report.html').write_text(content,encoding='utf-8')
    (out/'source_bindings.json').write_text(json.dumps(sources,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(report=str(out/'report.html'),search_rows=len(search_rows),real_refinement_arms=len(r_rows),real_ablation_arms=len(a_rows)),ensure_ascii=False))


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out',type=Path,default=D/'reguard_mechanisms_20261103_r01')
    ap.add_argument('--search',type=Path,default=D/'research192_active_20261103_r03')
    ap.add_argument('--native',type=Path,default=D/'research193_active_native_20261103_r01')
    ap.add_argument('--refinement',type=Path,default=D/'research192_refinement_20261103_r01')
    ap.add_argument('--ablation',type=Path,default=D/'research192_ablation_20261103_r01')
    ap.add_argument('--archive',type=Path,default=D/'research192_archive_audit_20261103_r03')
    ap.add_argument('--independent',type=Path,default=D/'research192_independent_20261103_r01')
    ap.add_argument('--acquisition',type=Path,default=D/'research192_ablation_prepare_20261103_r01')
    args=ap.parse_args();build(**vars(args))
