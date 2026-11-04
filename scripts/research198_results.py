"""Report real execution, bounded coverage and paired parent-level outcomes."""
import argparse
from collections import Counter
import copy
from html import escape
import json
from pathlib import Path
from research194_refinement_runner import read,dump
from research194_report import trajectories,aggregate,cross_design_table,table
from research195_refinement_adapter import clone
from research198_cost_sections import GROUPS
from research198_paths import chains,ordered_stages,structural_chains

def optional(path,default):return read(path) if Path(path).exists() else default

def build(prepared,execution,acceptance,cost,cards,out):
    prepared,execution,acceptance,cost,cards,out=map(Path,(prepared,execution,acceptance,cost,cards,out))
    p=read(prepared/'protocol.json')
    if read(execution/'outcome.json')['status']!='completed_all_versions_frozen' or read(acceptance/'outcome.json')['status']!='completed':raise ValueError('unfinished_experiment')
    rr=trajectories(execution);aa=read(acceptance/'results.json');analysis=clone('research196_results');analysis.GROUPS=GROUPS
    analysis_rows=copy.deepcopy(aa)
    for r in rr:r['strategy']=r['policy']
    for r in analysis_rows:
        if r.get('role')!='initial_control':r['strategy']=r['policy']
    paired=analysis.paired(analysis_rows)
    tables=dict(refinement_S0=aggregate(rr,[(v,'S0',v) for v in ('feedback','legacy','local_first')],analysis_rows),
        refinement_S3=aggregate(rr,[(v,'S3',v) for v in ('feedback','legacy','local_first')],analysis_rows),
        ablation=aggregate(rr,[('A0','S0','feedback'),('A1','S3','feedback'),('A2','S0','local_first'),('A3','S3','local_first')],analysis_rows),
        cross_design=cross_design_table(aa),paired=paired['summary'],interactions=paired['interactions'])
    attempts=[];paths=[];calls=[]
    for e in p['entries']:
        folder=execution/e['id']/'refinement';rounds=optional(folder/'rounds.json',[]);stages=[];requested_stages=[];confirmed_stages=[]
        for index in range(1,6):
            r=next((v for v in rounds if v['round']==index),None);rd=folder/f'round{index:02}'
            request=optional(rd/'request.preview.json',None)
            context=json.loads(request['messages'][-1]['content']) if request else {}
            contract=context.get('output_contract',{});requested=None
            if request:
                requested='local' if isinstance(contract.get('operations'),dict) else 'compose' if 'edits' in contract.get('schema',{}) else 'regenerate' if (context.get('fallback_receipt') or {}).get('stage')=='compose' else 'free'
            native_stage=r.get('stage') if r and 'decision' in r else None
            if native_stage:stages.append(native_stage)
            if requested:requested_stages.append(requested)
            if native_stage and not r['decision'].get('critical_unknown'):confirmed_stages.append(native_stage)
            attempts.append(dict(id=e['id'],policy=e['policy'],round=index,requested_stage=requested,native_stage=native_stage,
                classification=analysis.classify_round(r) if r else 'not_attempted',status=r.get('status') if r else None,
                model_edit=optional(rd/'model_edit.json',None),decision=r.get('decision') if r else None))
        linked=chains(optional(folder/'controller_history.json',[]))
        structural=structural_chains(optional(folder/'controller_history.json',[]))
        paths.append(dict(id=e['id'],policy=e['policy'],requested_stages=requested_stages,native_stages=stages,
            ordered_three_stage_requests=ordered_stages(requested_stages),ordered_three_stage_native_attempts=ordered_stages(stages),
            ordered_three_stage_confirmed_measurements=ordered_stages(confirmed_stages),
            full_three_stage=bool(linked),linked_chains=linked,partial_improvement_structural_chains=structural))
        for path in folder.glob('round*/model_call/result.json'):calls.append(dict(id=e['id'],**read(path)))
    markers=list(execution.glob('*/*/*/refinement/round*/model_call/attempt.json'))
    missing=[str(x) for x in markers if not (x.parent/'result.json').exists()]
    summary=dict(status='registered_experiment_executed_not_necessarily_successful',frozen_versions=len(rr),model_calls=len(markers),
        maximum_model_calls=p['maximum_model_calls'],reserved_calls=len(read(execution/'ledger.json')),known_tokens=sum((c.get('prompt_tokens') or 0)+(c.get('completion_tokens') or 0) for c in calls),
        unknown_usage_calls=len(missing)+sum(c.get('prompt_tokens') is None or c.get('completion_tokens') is None for c in calls),
        call_statuses=dict(Counter(c['status'] for c in calls)),attempt_classifications=dict(Counter(r['classification'] for r in attempts)),
        accepted_local=sum(r['native_stage']=='local' and r['status']=='accepted' for r in attempts),
        accepted_local_by_policy=dict(Counter(r['policy'] for r in attempts if r['native_stage']=='local' and r['status']=='accepted')),
        full_native_three_stage_paths=sum(r['full_three_stage'] for r in paths),
        partial_improvement_structural_three_stage_paths=sum(bool(r['partial_improvement_structural_chains']) for r in paths),
        ordered_three_stage_requests=sum(r['ordered_three_stage_requests'] for r in paths),
        ordered_three_stage_native_attempts=sum(r['ordered_three_stage_native_attempts'] for r in paths),
        ordered_three_stage_confirmed_measurements=sum(r['ordered_three_stage_confirmed_measurements'] for r in paths),
        independent_version_fault_records=len(aa),independent_unknown_records=sum(bool(r['unknown_records']) for r in aa),
        independent_unexposed_records=sum(bool(r.get('no_exposure_queries')) for r in aa),
        independent_full_scope_pass_records=sum(r['full_planned_transaction_scope_pass'] for r in aa),
        limitations=p['limits']+['Fixed S0/S3 acquisition outputs; not a new online adaptive-search experiment.','Qualification and archived replay are excluded from real model statistics.','No success or full branch traversal is forced.','New controller changes routing and typed contract together; no separate causal attribution between these two implementation changes.'])
    out.mkdir(parents=True,exist_ok=False)
    for name,value in [('summary',summary),('tables',tables),('paired_analysis',paired),('attempt_matrix',attempts),('fallback_paths',paths),('calls',calls),('trajectory_index',rr),('cost_analysis',read(cost/'analysis.json'))]:dump(out/(name+'.json'),value)
    body=['<!doctype html><meta charset="utf-8"><title>REGuard R198</title><style>body{font:15px/1.6 sans-serif;max-width:1350px;margin:35px auto}.scroll{overflow:auto}table{border-collapse:collapse}td,th{border:1px solid #bbc;padding:7px}pre{white-space:pre-wrap;background:#eef2f6;padding:15px}</style><h1>R198：自动局部优先与真实回退验证</h1><p>注册实验执行完成不等于所有断言验收通过，也不等于新策略总体占优。</p>',
        '<p><a href="../reguard_mechanisms_20261104_r07/report.html">此前统一实验矩阵</a> · <a href="../research198_case_cards_20261104_r01/cards.html">原始 SVA、波形与正反案例</a> · <a href="cost_analysis.json">实际成本及三/五轮共同截面</a></p>',
        '<p>S0/S3 是已封存开发搜索结果。固定这些证据比较普通反馈、旧 R3 和局部优先 R3；没有新增搜索调用。所有模型组采用相同五次调用上限，另报告三轮和实际成本截面。</p>',
        '<pre>'+escape(json.dumps(summary,ensure_ascii=False,indent=2))+'</pre>']
    for key in ('refinement_S0','refinement_S3','ablation','paired','cross_design'):
        rows=tables[key];body+=['<h2>'+escape(key)+'</h2>',table(rows,[(k,k) for k in rows[0]]) if rows else '<p>无可比较记录。</p>']
    body += ['<p><a href="attempt_matrix.json">逐轮未尝试／失败／拒绝／改善</a> · <a href="fallback_paths.json">实际原生回退路径</a></p>']
    body += ['<h2>独立的解析器修正</h2><p>组合权限应根据当前保留候选的原生证据计算，不能使用被拒绝提案的覆盖。已提供可开关的独立适配器，并单独回放实际组合响应。本表仍是原封存 R198 的真实模型结果；该修正未混入本批。构造的回归测试不是模型成功案例。</p><p><a href="../research198_composition_fix_20261104_r01/replay.json">全部实际组合响应的并列解析回放</a></p>']
    (out/'report.html').write_text('\n'.join(body),encoding='utf-8');print(summary,flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser()
    for k in ('prepared','execution','acceptance','cost','cards','out'):p.add_argument('--'+k,type=Path,required=True)
    a=p.parse_args();build(a.prepared,a.execution,a.acceptance,a.cost,a.cards,a.out)
