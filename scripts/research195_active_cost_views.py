"""Supplemental actual-wall cuts and measured-data PNG; no experiment reruns."""
import argparse
import hashlib
import html
import json
import os
from pathlib import Path
import statistics
import sys

from research195_active_analysis import state_at_cut

ROOT=Path(__file__).resolve().parents[1]
STRATEGIES=('S2','active_no_cost','active_cost')


def build(out):
    out=Path(out).resolve()
    def read(name):return json.loads((out/name).read_text())
    if read('outcome.json')['status']!='completed':raise ValueError('main_not_completed')
    units=read('unit_cost_curves.json');analysis=read('analysis.json');cycle=read('mean_cycle_curve.json');query=read('paired_query_cuts.json')
    unit_ids=sorted({(u['case_id'],u['seed']) for u in units});wall=[];paired=[]
    global_support=min(u['points'][-1]['total_seconds_excluding_lock_wait'] for u in units)
    for cut in range(0,int(global_support)+1,10):
        for strategy in STRATEGIES:
            states=[state_at_cut(u['points'],'total_seconds_excluding_lock_wait',cut) for u in units if u['strategy']==strategy]
            wall.append(dict(strategy=strategy,actual_wall_cut_seconds=cut,paired_units=len(states),mean_new_contexts=statistics.mean(s['new_contexts'] for s in states),
                mean_queries_completed=statistics.mean(s['queries'] for s in states)))
    for case,seed in unit_ids:
        selected={u['strategy']:u for u in units if (u['case_id'],u['seed'])==(case,seed)}
        support=min(u['points'][-1]['total_seconds_excluding_lock_wait'] for u in selected.values())
        states={s:state_at_cut(u['points'],'total_seconds_excluding_lock_wait',support) for s,u in selected.items()}
        for comparator in ('S2','active_no_cost'):
            paired.append(dict(case_id=case,seed=seed,method='active_cost',comparator=comparator,common_wall_cut_seconds=support,
                method_queries=states['active_cost']['queries'],comparator_queries=states[comparator]['queries'],
                context_difference_at_wall_cut=states['active_cost']['new_contexts']-states[comparator]['new_contexts']))
    query_mean=[]
    for cut in (0,1,2,3,4):
        for strategy in STRATEGIES:
            rr=[r for r in query if r['query_cut']==cut and r['strategy']==strategy]
            if len(rr)==len(unit_ids):query_mean.append(dict(strategy=strategy,query_cut=cut,mean_new_contexts=statistics.mean(r['new_contexts'] for r in rr)))
    payload=dict(cycle=cycle,query=query_mean,wall=wall,paired_wall=paired,tables=analysis['tables'],
        status='supplemental_read_only_cost_view',wall_cost='Measured acquisition wall plus planning, excluding separately recorded shared-lock wait; full-query step cuts only.',
        wall_analysis_posthoc=True,predeclared_primary_axes=['actual_sampled_cycles','actual_query_count'],
        source_sha256={name:hashlib.sha256((out/name).read_bytes()).hexdigest() for name in ('unit_cost_curves.json','analysis.json','mean_cycle_curve.json','paired_query_cuts.json')},
        plotting_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),new_native_jobs=0,model_calls=0)
    records=[json.loads(p.read_text()) for p in sorted((out/'sessions').glob('*/*/*/query*/acquisition.json'))]
    diagnostics=[]
    for strategy in STRATEGIES:
        rr=[r for r in records if r['strategy']==strategy]
        diagnostics.append(dict(strategy=strategy,queries=len(rr),
            queries_without_confirmed_target=sum(not r['measurement']['targets'] for r in rr),
            queries_without_initial_candidate_native_trigger=sum(not any(m['id'].startswith('c0_') for j in r['measurement']['executions'] for m in j['result'].get('triggers',[])) for r in rr),
            native_semantic_unknown_queries=sum(not r['semantic_native_consistent'] for r in rr),
            selected_24_cycle_queries=sum(len(r['query']['rows'])==24 for r in rr),
            measured_acquisition_plus_planning_seconds=sum(r['cost']['total_wall_seconds_excluding_lock_wait'] for r in rr),
            lock_wait_seconds=sum(r['cost']['lock_wait_seconds'] for r in rr),
            diagnostic_native_wall_prediction_rmse=(statistics.mean((r['selected_rank']['predicted_native_seconds']-r['cost']['native_seconds'])**2 for r in rr))**.5))
    payload['execution_diagnostics']=diagnostics
    selections=[(p,json.loads(p.read_text())) for p in sorted((out/'sessions').glob('*/*/*/selection*.json'))]
    mechanism=[]
    for case in sorted({r['case_id'] for r in records}):
        for strategy in STRATEGIES:
            selected=[r for r in records if r['case_id']==case and r['strategy']==strategy]
            ranks=[r['ranked'] for p,r in selections if p.parent.parent.parent.name==case and p.parent.name==strategy]
            values=[[x['semantic_discrimination'] for x in rr if x['semantic_discrimination'] is not None] for rr in ranks]
            mechanism.append(dict(case_id=case,strategy=strategy,selection_rounds=len(values),
                semantic_score_saturated_rounds=sum(bool(v) and len(set(v))==1 for v in values),
                semantic_score_all_one_rounds=sum(bool(v) and all(x==1 for x in v) for v in values),
                semantic_score_minimum=min((x for v in values for x in v),default=None),
                semantic_score_maximum=max((x for v in values for x in v),default=None),
                selected_lengths=[len(r['query']['rows']) for r in selected],
                native_candidate_disagreement_queries=sum(r['actual_native_candidate_disagreement'] for r in selected),
                interpretation='Hypothetical semantic score is candidate-pair discrimination, not expected evidence count; no LLM was called.'))
    payload['mechanism_diagnostics']=mechanism
    (out/'mechanism_diagnostics.json').write_text(json.dumps(dict(rows=mechanism,
        scoring='benefit = 3 * candidate-pair discrimination + 2 * unprotected-obligation fraction + family novelty; active_cost divides by 2 * input rows.',
        limitation='A bounded pair-discrimination numerator can saturate while longer schedules expose more distinct observed contexts. Per-query compile overhead is not captured by a cycle denominator.',
        posthoc_analysis_only=True,new_native_jobs=0,model_calls=0),indent=2)+'\n')
    data=out/'cost_view_data.json';data.write_text(json.dumps(payload,indent=2)+'\n')
    (out/'wall_cost_analysis.json').write_text(json.dumps(dict(status=payload['status'],wall_analysis_posthoc=True,
        cost_definition=payload['wall_cost'],curve=wall,paired_comparisons=paired,execution_diagnostics=diagnostics,
        source_sha256=payload['source_sha256'],new_native_jobs=0,model_calls=0),indent=2)+'\n')
    # Root prepared this isolated plotting dependency. No installer or network
    # is invoked here, and no execution/selection source is changed.
    sys.path.insert(0,str(ROOT/'.research195_plotdeps'))
    os.environ['MPLCONFIGDIR']=str(ROOT/'.research195_plotcache')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    names={'S2':'S2 contract','active_no_cost':'Active (no cost)','active_cost':'Active / cycles'}
    colors={'S2':'#176e94','active_no_cost':'#bd6527','active_cost':'#7b3c9d'}
    styles={'S2':'-','active_no_cost':':','active_cost':'--'}
    fig,axes=plt.subplots(1,3,figsize=(16,5.1))
    panels=[(cycle,'cycle_cut','A. Equal sampled-cycle cuts','Actual sampled cycles per (case, seed)'),
        (query_mean,'query_cut','B. Equal query cuts','Actual submitted queries per (case, seed)'),
        (wall,'actual_wall_cut_seconds','C. Wall cuts (supplemental)','Acquisition + planning seconds, excluding lock wait')]
    for ax,(rows,field,title,xlabel) in zip(axes,panels):
        for strategy in STRATEGIES:
            rr=sorted((r for r in rows if r['strategy']==strategy),key=lambda r:r[field])
            ax.step([r[field] for r in rr],[r['mean_new_contexts'] for r in rr],where='post',label=names[strategy],
                color=colors[strategy],linestyle=styles[strategy],marker='o',markersize=3,linewidth=1.8)
        ax.set_title(title);ax.set_xlabel(xlabel,fontsize=9);ax.grid(alpha=.22);ax.legend(fontsize=9)
        ax.set_ylabel('Mean new confirmed gap contexts')
    fig.suptitle('Variable-cost temporal evidence: the cost unit changes the comparison',fontsize=15)
    fig.text(.5,.045,'Arbiter + Counter, two paired seeds; complete queries only. Shared baseline/calibration charged separately.',ha='center',fontsize=9)
    fig.text(.5,.015,'First-violation / FP contexts; late detections and unknowns separate. Different y scales. Cycle savings are not wall speedups.',ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.10,1,.93));fig.savefig(out/'paired_cost_views.png',dpi=180);plt.close(fig)
    def table(rows):
        if not rows:return '<p>无记录。</p>'
        keys=list(rows[0]);cell=lambda x:html.escape(json.dumps(x,ensure_ascii=False) if isinstance(x,(dict,list)) else str(round(x,3) if isinstance(x,float) else x))
        return '<div class="scroll"><table><tr>'+''.join('<th>'+html.escape(k)+'</th>' for k in keys)+'</tr>'+''.join('<tr>'+''.join('<td>'+cell(r.get(k))+'</td>' for k in keys)+'</tr>' for r in rows)+'</table></div>'
    columns=('strategy','actual_queries','native_executions','actual_sampled_cycles','native_seconds','planning_seconds','mean_new_contexts_per_case_seed','critical_unknown')
    body='<h1>R195 可变成本主动时序证据实验</h1><p>两个设计、两个配对种子、三种策略。初始候选和生成器在执行前冻结。周期截面和查询数截面预先声明；墙钟截面为只读补充分析。</p>'
    body+='<img src="paired_cost_views.png" alt="实际周期、查询次数和采集加规划时间的配对完整查询成本曲线">'
    body+='<h2>实际执行与成本</h2>'+table([{k:t[k] for k in columns} for t in analysis['tables']])
    body+='<p>共享开发校准和公共基线的实际开销：</p><pre>'+html.escape(json.dumps(analysis['physical_auxiliary_cost'],ensure_ascii=False,indent=2))+'</pre>'
    body+='<h2>同实际周期截面</h2>'+table(analysis['paired_comparisons'])+'<h2>同采集加规划时间截面（补充）</h2>'+table(paired)
    body+='<h2>未曝光、无触发与计时诊断</h2>'+table(diagnostics)
    body+='<h2>候选语义分歧与短查询偏置</h2>'+table(mechanism)
    body+='<p>分子衡量候选对能否区分，并不估计该查询将产生多少独特证据。分歧分数饱和时，周期分母会偏向短查询；每次编译的固定开销则限制墙钟收益。这里记录机制局限，未据结果修改策略或查询池。</p>'
    body+='<p>未知片段不会成为合法或违例证据；未曝光与无触发不会成为通过。波形周期成本不是墙钟加速证明。采集计时加规划不包含其后的报告序列化、绘图开销，锁等待另列。</p>'
    body+='<p><a href="protocol.json">冻结协议</a> · <a href="seal.json">来源封存</a> · <a href="audit.json">112 个原生作业只读审计</a> · <a href="analysis.json">主分析</a> · <a href="cost_view_data.json">图与补充截面数据</a> · <a href="gap_context_index.json">证据上下文索引</a></p>'
    (out/'report.html').write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>R195 可变成本主动证据</title><style>body{font:15px/1.55 system-ui;max-width:1500px;margin:32px auto;padding:20px;color:#203040}img{width:100%}.scroll{overflow:auto}table{border-collapse:collapse;font-size:12px}th,td{padding:8px;border:1px solid #ccd5df}pre{white-space:pre-wrap;background:#eef3f8;padding:15px}</style><body>'+body+'</body></html>',encoding='utf-8')
    print(json.dumps(dict(status=payload['status'],paired_wall_comparisons=len(paired),model_calls=0,new_native_jobs=0)))
    return payload


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);build(p.parse_args().out)
