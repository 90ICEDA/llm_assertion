"""Frozen factorial and online contrasts, prefix costs and evidence linkage."""
import copy
from collections import Counter
from html import escape
from pathlib import Path
import json
import os
from research194_refinement_runner import ROOT,read,dump
from research194_report import table
from research195_refinement_adapter import clone
from research199_cost import GROUPS
from research198_paths import chains,structural_chains

def run(prepared,execution,acceptance,cost,linkage,out):
    out=Path(out);out.mkdir(parents=True,exist_ok=False);p=read(Path(prepared)/'protocol.json')
    if read(Path(execution)/'outcome.json')['status']!='completed_all_versions_frozen' or read(Path(acceptance)/'outcome.json')['status']!='completed':raise ValueError('unfinished')
    aa=read(Path(acceptance)/'results.json');analysis=clone('research196_results');analysis.GROUPS=GROUPS
    analysis_rows=copy.deepcopy(aa)
    for r in analysis_rows:
        if r.get('role')!='initial_control':r['strategy']=r['arm']
    paired=analysis.paired(analysis_rows);interactions={}
    for group in GROUPS:
        rr={r['arm']:r for r in paired['summary'] if r['group']==group};arms=[group+str(i) for i in range(4)]
        interactions[group]={k:None if any(rr[a][k] is None for a in arms) else rr[arms[3]][k]-rr[arms[2]][k]-rr[arms[1]][k]+rr[arms[0]][k] for k in ('transaction_rate','timely_rate','fp_records','necessary_obligation_rate')}
    attempts=[];paths=[];calls=[]
    for e in p['entries']:
        folder=Path(execution)/e['id']/'refinement';rounds=read(folder/'rounds.json') if (folder/'rounds.json').exists() else []
        for i in range(1,4):
            r=next((r for r in rounds if r['round']==i),None)
            attempts.append(dict(id=e['id'],arm=e['arm'],round=i,status=r.get('status') if r else 'not_attempted',classification=analysis.classify_round(r) if r else 'not_attempted',stage=r.get('stage') if r else None))
        history=read(folder/'controller_history.json') if (folder/'controller_history.json').exists() else []
        paths.append(dict(id=e['id'],strict_rejected_local_chains=chains(history),partial_local_structural_chains=structural_chains(history)))
        calls.extend(read(f) for f in folder.glob('round*/model_call/result.json'))
    summary=dict(population=48,actual_model_calls=len(list(Path(execution).glob('*/*/*/refinement/round*/model_call/attempt.json'))),
        known_tokens=sum((c.get('prompt_tokens') or 0)+(c.get('completion_tokens') or 0) for c in calls),unknown_usage_calls=sum(c.get('prompt_tokens') is None or c.get('completion_tokens') is None for c in calls),
        classifications=dict(Counter(r['classification'] for r in attempts)),
        independent_records=len(aa),unknown_records=sum(bool(r['unknown_records']) for r in aa),unexposed_records=sum(bool(r['no_exposure_queries']) for r in aa),
        full_scope_pass_records=sum(r['full_planned_transaction_scope_pass'] for r in aa),
        strict_rejected_local_paths=sum(bool(r['strict_rejected_local_chains']) for r in paths),structural_paths=sum(bool(r['partial_local_structural_chains']) for r in paths),
        completion='Registered execution completion is separate from positive results, coverage and full-scope acceptance.')
    costs=read(Path(cost)/'analysis.json');primary=[r for r in costs['summary'] if r['axis']=='tokens' and r['budget_label']=='131072']
    for name,value in [('summary',summary),('paired',paired),('interactions',interactions),('attempts',attempts),('fallback_paths',paths),('costs',costs),('linkage',read(linkage))]:dump(out/(name+'.json'),value)
    body=['<!doctype html><meta charset="utf-8"><title>REGuard R199</title><style>body{font:15px/1.6 sans-serif;max-width:1300px;margin:35px auto}td,th{border:1px solid #aaa;padding:7px}table{border-collapse:collapse}pre{white-space:pre-wrap}.scroll{overflow:auto}</style><h1>R199：因果隔离与在线闭环</h1><p>B0–B3 为旧／局部优先路由 × 通用／专用操作契约。A0–A3 为 S0／S3 在线搜索 × 基础／新局部细化。两个队列单独解释，不把固定证据比较称为在线搜索。</p>',
        '<p><a href="../research199_diagnosis_20261104_r01/report.html">事前义务诊断</a> · <a href="../reguard_mechanisms_20261104_r09/completion_review.html">历史结果</a> · <a href="linkage.json">新证据、修改与独立义务效果关联</a></p>',
        '<h2>真实执行</h2><pre>'+escape(json.dumps(summary,ensure_ascii=False,indent=2))+'</pre>',
        '<h2>预登记主要 token 截面：131072</h2>'+table(primary,[(k,k) for k in primary[0]]) if primary else '<p>没有共同主要成本截面，不能声称等成本改善。</p>']
    for group in GROUPS:
        rows=[r for r in paired['summary'] if r['group']==group];body+=['<h2>'+group+' 最终配对</h2>',table(rows,[(k,k) for k in rows[0]])]
    body+=['<p><a href="costs.json">全部预登记成本截面</a> · <a href="attempts.json">失败分类</a> · <a href="fallback_paths.json">回退分支</a></p><p>证据与独立改善的关联不等于某一条证据的反事实因果效应。新故障是不同实例／位置，不保证不同广义故障族；未知与未曝光不计作通过。实际成本截面不是严格等成本随机执行。有限窗口和唯一在途 ID 的覆盖边界继续保留。</p>']
    html='\n'.join(body)
    for name,file in [('research199_diagnosis_20261104_r01','report.html'),('reguard_mechanisms_20261104_r09','completion_review.html')]:
        html=html.replace('../'+name+'/'+file,os.path.relpath(ROOT/'deliverables'/name/file,out).replace('\\','/'))
    (out/'report.html').write_text(html,encoding='utf-8');print(summary,flush=True)
