"""Readable additive delivery report; no experiment decisions or model calls."""
import argparse
from collections import Counter
from html import escape
import json
import os
from pathlib import Path
from research194_refinement_runner import read,dump,file_hash,ROOT
from research194_report import table


def run(prepared,execution,finish,cards,out):
    out.mkdir(parents=True,exist_ok=False)
    summary=read(finish/'report/summary.json');paired=read(finish/'report/paired.json')
    costs=read(finish/'report/costs.json');audit=read(finish/'report/final_audit.json')
    if audit['status']!='passed':raise ValueError('delivery_audit_failed')
    primary=[r for r in costs['summary'] if r['axis']=='tokens' and r['budget_label']=='131072']
    common=[r for r in costs['summary'] if r['budget_label']=='minimum_observed_total' and r['axis'] in ('tokens','service_seconds')]
    linkage=read(finish/'linkage.json');p=read(prepared/'protocol.json')
    arm_rows=[];online=[];native_failures=[];unattempted=[]
    for arm in ('B0','B1','B2','B3','A0','A1','A2','A3'):
        entries=[e for e in p['entries'] if e['arm']==arm];rounds=[];calls=[];dispatches=0
        for e in entries:
            folder=execution/e['id']/'refinement'
            entry_rounds=read(folder/'rounds.json') if (folder/'rounds.json').exists() else []
            rounds+=entry_rounds
            called={int(path.parent.parent.name[5:]) for path in folder.glob('round*/model_call/attempt.json')}
            outcome=read(folder/'outcome.json')
            last=entry_rounds[-1] if entry_rounds else {}
            for number in range(1,4):
                if number in called:continue
                reason='prior_native_unknown' if last.get('decision',{}).get('critical_unknown') else outcome.get('termination_reason') or ('controller_completed' if last.get('decision',{}).get('complete') else 'controller_ended_see_history')
                unattempted.append(dict(id=e['id'],round=number,reason=reason,last_record_status=last.get('status')))
            for r in entry_rounds:
                if not r.get('decision',{}).get('critical_unknown'):continue
                errors=[]
                for path in (folder/f"round{r['round']:02}").glob('proposal_native/**/compile.log'):
                    line=next((line for line in path.read_text(encoding='utf-8',errors='replace').splitlines() if '%Error' in line),None)
                    if line:errors.append(dict(path=str(path),first_error=line))
                native_failures.append(dict(id=e['id'],round=r['round'],stage=r.get('stage'),compile_errors=errors,
                    classification='proposal_native_unknown_not_confirmed_semantic_failure'))
            calls+= [read(path) for path in folder.glob('round*/model_call/result.json')]
            dispatches+=len(list(folder.glob('round*/model_call/attempt.json')))
            if e['cohort']=='online':
                records=[read(path) for path in sorted((execution/e['id']/'acquisition').glob('query*/acquisition.json'))]
                online.append(dict(id=e['id'],arm=arm,queries=len(records),fresh_queries=sum(not r.get('first_query_physical_reuse') for r in records),
                    changed_candidate_queries=sum(bool(r.get('online_link',{}).get('previous_candidate_sha256')) and r['online_link']['candidate_sha256']!=r['online_link']['previous_candidate_sha256'] for r in records),
                    query_ids=[r['query']['id'] for r in records],new_gap_counts=[len(r.get('new_gap_ids',[])) for r in records],
                    new_gap_obligations=sorted({g['obligation'] for r in records for g in r.get('gap_records',[]) if g['gap_id'] in r.get('new_gap_ids',[]) and g.get('obligation')}),
                    later_gap_obligations=sorted({g['obligation'] for r in records[1:] for g in r.get('gap_records',[]) if g['gap_id'] in r.get('new_gap_ids',[]) and g.get('obligation')})))
        arm_rows.append(dict(arm=arm,trajectories=len(entries),calls=dispatches,known_tokens=sum((r.get('prompt_tokens') or 0)+(r.get('completion_tokens') or 0) for r in calls),
            accepted=sum(r.get('status')=='accepted' for r in rounds),local_accepted=sum(r.get('status')=='accepted' and r.get('stage')=='local' for r in rounds),
            interface_failures=sum(r.get('status')=='interface_rejected' for r in rounds),
            interface_failure_rate=sum(r.get('status')=='interface_rejected' for r in rounds)/dispatches if dispatches else None,
            modification_acceptance_rate=sum(r.get('status')=='accepted' for r in rounds)/dispatches if dispatches else None,
            error_reasons=dict(Counter(str(r['error']) for r in rounds if r.get('error'))),
            outcomes=dict(Counter(r.get('status','unfinished') for r in rounds))))
    effects=[];online_effects=[]
    scopes=[('final',paired['summary']),('tokens_131072',primary)]
    scopes += [('minimum_observed_'+axis,[r for r in common if r['axis']==axis]) for axis in ('tokens','service_seconds')]
    for scope,rows in scopes:
        by={r['arm']:r for r in rows}
        for metric in ('transaction_rate','necessary_obligation_rate'):
            if not all(a in by and by[a].get(metric) is not None for a in ('B0','B1','B2','B3')):continue
            v={a:by[a][metric] for a in ('B0','B1','B2','B3')}
            effects.append(dict(scope=scope,metric=metric,route_generic=v['B1']-v['B0'],route_typed=v['B3']-v['B2'],
                contract_legacy=v['B2']-v['B0'],contract_local_first=v['B3']-v['B1'],interaction=v['B3']-v['B2']-v['B1']+v['B0']))
        for metric in ('transaction_rate','necessary_obligation_rate'):
            if not all(a in by and by[a].get(metric) is not None for a in ('A0','A1','A2','A3')):continue
            v={a:by[a][metric] for a in ('A0','A1','A2','A3')}
            online_effects.append(dict(scope=scope,metric=metric,search_basic=v['A1']-v['A0'],search_local=v['A3']-v['A2'],
                refinement_basic=v['A2']-v['A0'],refinement_active=v['A3']-v['A1'],interaction=v['A3']-v['A2']-v['A1']+v['A0']))
    data=dict(summary=summary,audit=audit,arm_execution=arm_rows,factorial_effects=effects,online_effects=online_effects,online=online,native_failure_diagnostics=native_failures,unattempted_slots=unattempted,primary_cost=primary,common_observed_cost=common,
        final_paired=paired,linked_improvements=linkage,model_calls=0,scope='Descriptive paired effects on registered cases; no item-level causal attribution or population significance claim.')
    dump(out/'delivery.json',data)
    def link(path,title):return '<a href="'+escape(os.path.relpath(path,out).replace('\\','/'))+'">'+escape(title)+'</a>'
    def tbl(rows,keys):return table(rows,[(k,k) for k in keys]) if rows else '<p>无符合条件的记录。</p>'
    def metric_rows(rows):
        return [dict(group=r['group'],arm=r['arm'],axis=r.get('axis'),paired_parents=r.get('paired_parents'),supported_parents=r.get('supported_parents'),transaction_pct=None if r.get('transaction_rate') is None else round(100*r['transaction_rate'],3),necessary_obligation_pct=None if r.get('necessary_obligation_rate') is None else round(100*r['necessary_obligation_rate'],3),false_positive_records=r.get('fp_records',r.get('legal_fp_records'))) for r in rows]
    recovery_note=''
    if (finish/'recovery.json').exists():
        recovery=read(finish/'recovery.json');data['recovery']=recovery;dump(out/'delivery.json',data)
        recovery_note='<p><strong>本地验收恢复：</strong>首次验收因磁盘满中断，原目录与不完整文件均保留。对执行产物做 NTFS 透明压缩后，以相同冻结候选、原预登记成本检查点和完全相同输入／故障计划恢复本地验收；第二次会话中断后复用完整测量，只执行缺失部分。模型未重试。首次中断的部分原生耗时无法完整恢复，不按零计费。'+link(finish/'recovery.json','恢复及额外成本记录')+'</p>'
    body=['<!doctype html><meta charset="utf-8"><title>REGuard research199</title><style>body{font:16px/1.6 sans-serif;max-width:1400px;margin:36px auto;padding:0 22px}table{border-collapse:collapse}td,th{border:1px solid #bbc;padding:7px}.scroll{overflow:auto}pre{white-space:pre-wrap;background:#eef2f6;padding:16px}</style>',
        '<h1>REGuard research199：收益来源与在线闭环</h1>',
        recovery_note,
        '<p>注册实验执行与算法是否有优势分别判断。B 组固定相同开发证据，隔离路由与操作契约；A 组以当前保留候选重新选择并执行查询。独立验收在全部 48 个版本冻结后进行。</p>',
        '<p>'+ ' · '.join([link(prepared/'protocol.json','封存协议'),link(prepared/'authorization.json','本批授权记录'),link(ROOT/'deliverables/research199_diagnosis_20261104_r01/report.html','P0 义务诊断'),link(finish/'report/report.html','原始分析报告'),link(cards/'cards.html','开发阶段预选案例'),link(finish/'report/final_audit.json','交付审计'),link(ROOT/'deliverables/reguard_mechanisms_20261104_r09/completion_review.html','历史完成范围')])+'</p>',
        '<h2>执行记录</h2><p>接口失败按逐轮 interface_rejected 统计；旧执行器 outcome 的 interface_failures 同时包含 no_change，不能直接当作接口错误次数。复用传输器的 phase 字段沿用 research197 标签，本批身份以封存协议、请求 experiment.version/arm 和账本为准，审计逐项核对。</p><pre>'+escape(json.dumps(summary,ensure_ascii=False,indent=2))+'</pre>',
        tbl(arm_rows,['arm','trajectories','calls','known_tokens','accepted','local_accepted','interface_failures','interface_failure_rate']),
        '<h2>没有调用的注册轮次</h2>'+tbl(unattempted,['id','round','reason','last_record_status']),
        '<h2>预登记主要成本截面：每轨迹 131072 tokens</h2><p>仅计入完整、成本已知且未超过预算的检查点；实际超额消耗仍计入执行成本。服务耗时作为辅助口径，包含查询规划、原生编译执行、回放和模型服务，排除调度等待及编排 I/O。此处是成本截面分析，不是严格等耗时重跑。</p>',
        tbl(metric_rows(primary),['group','arm','paired_parents','supported_parents','transaction_pct','necessary_obligation_pct','false_positive_records']),
        '<h2>共同实际成本的完整检查点</h2><p>各父案例／种子分别以四组实际总成本的最小值截取；没有已完成且未超预算的新版本时保留初始版本。它仍是描述性的完整轮次比较，各组最终花费并不相等。</p>',
        tbl(metric_rows(common),['group','arm','axis','paired_parents','supported_parents','transaction_pct','necessary_obligation_pct','false_positive_records']),
        '<h2>全部注册轮次后的配对结果</h2><p>B0 旧路由／通用字段；B1 局部优先／通用字段；B2 旧路由／专用操作；B3 局部优先／专用操作。A0 基础搜索／基础反馈；A1 主动搜索／基础反馈；A2 基础搜索／新局部细化；A3 主动搜索／新局部细化。按父案例等权、两种子和共同有效故障配对。</p>',
        tbl(metric_rows(paired['summary']),['group','arm','paired_parents','supported_parents','transaction_pct','necessary_obligation_pct','false_positive_records']),
        '<h2>路由与契约的条件贡献</h2><p>下表为率差（乘 100 为百分点），只对本批注册案例解释。接口错误和模型随机性均属于实际机制表现；不据此声称总体显著性。</p>',
        tbl(effects,['scope','metric','route_generic','route_typed','contract_legacy','contract_local_first','interaction']),
        '<h2>在线搜索与细化的条件贡献</h2>',
        tbl(online_effects,['scope','metric','search_basic','search_local','refinement_basic','refinement_active','interaction']),
        '<h2>在线执行与证据关联</h2>'+tbl(online,['id','queries','fresh_queries','changed_candidate_queries','new_gap_counts','later_gap_obligations']),
        '<p>符合预定义干净关联条件的在线链：'+str(linkage['clean_associated_online_chains'])+'。条件包括新增已确认开发证据、接受修改、独立新义务保护和没有新增合法误报。证据先于修改的关联不能替代移除该条证据的反事实实验。</p>',
        '<p>'+link(finish/'linkage.json','全部接受修改的逐故障独立前后效果')+' · '+link(finish/'report/fallback_paths.json','严格拒绝链与结构性回退分开统计')+' · '+link(finish/'acceptance/native/results.json','全部版本×故障验收记录')+' · '+link(finish/'cost/analysis.json','其他预登记成本截面')+'</p>',
        '<h2>解释边界</h2><p>新预留故障使用不同实例或位置，但不保证属于全新广义故障族。此前看过的预留故障只用于诊断。unknown、未曝光、执行失败均不当作通过。必要义务按显式映射统计：某义务没有映射与其物理波形完全没有报警不同。窗口、并发 ID、响应年龄和查询模板仍为有限范围。没有优势或没有观察到特定回退链，均保留为结果。</p>']
    (out/'report.html').write_text('\n'.join(body),encoding='utf-8')
    bindings={str(path.resolve()):file_hash(path) for path in [prepared/'protocol.json',finish/'report/final_audit.json',finish/'report/summary.json',finish/'report/paired.json',finish/'report/costs.json',finish/'linkage.json',cards/'selection.json',cards/'cards.html',Path(__file__)]}
    if (finish/'recovery.json').exists():bindings[str((finish/'recovery.json').resolve())]=file_hash(finish/'recovery.json')
    dump(out/'manifest.json',dict(source_bindings=bindings,model_calls=0,execution_not_repeated=True))
    print(dict(report=str(out/'report.html'),online_chains=linkage['clean_associated_online_chains']),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for key in ('prepared','execution','finish','cards','out'):parser.add_argument('--'+key,type=Path,required=True)
    a=parser.parse_args();run(a.prepared,a.execution,a.finish,a.cards,a.out)
