"""P0: source-bound obligation diagnosis from R198; no model/native calls."""
from collections import Counter
from html import escape
from pathlib import Path
import argparse
import json
from research194_refinement_runner import ROOT,read,dump,file_hash
from research198_refinement import runtime
from research196_results import classify_round
import research197_cases as cases

def run(out):
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    prep=ROOT/'deliverables/research198_refinement_prepare_20261104_r01'
    execution=ROOT/'deliverables/research198_refinement_execute_20261104_r01'
    ap=ROOT/'deliverables/research198_independent_20261104_r01/native/results.json'
    bindings={str(ap):file_hash(ap),str(prep/'protocol.json'):file_hash(prep/'protocol.json')}
    grades=read(ap);rows=[]
    def load(p):bindings[str(p)]=file_hash(p);return read(p)
    for entry in read(prep/'protocol.json')['entries']:
        s=load(Path(entry['state']));folder=execution/entry['id']/'refinement'
        frozen=load(folder/'frozen.json');terminal=load(folder/'terminal_measurement.json')
        rounds=load(folder/'rounds.json');core,_=runtime(entry['policy'])
        ev=core.normalize_evidence(s['first_measurement']['evidence'])
        endev=core.normalize_evidence(terminal['evidence'])
        findings=core.localize(s['initial'],ev)
        for ob in cases.get_case(entry['case_id'])['obligations']:
            targets=[v for v in ev if v['status']=='confirmed' and v['label']=='violation' and v.get('counted_target',True) and v.get('obligation')==ob]
            endtargets=[v for v in endev if v['status']=='confirmed' and v['label']=='violation' and v.get('counted_target',True) and v.get('obligation')==ob]
            initial_labels=[a['label'] for a in s['initial'] if ob in a['obligations']]
            final_labels=[a['label'] for a in frozen if ob in a['obligations']]
            target_ids={v['id'] for v in targets}
            localized=[f for f in findings if set(f['evidence_ids'])&target_ids or f['assertion'] in initial_labels]
            affected=[]
            for r in rounds:
                rd=folder/f"round{r['round']:02}"
                edit=load(rd/'model_edit.json') if (rd/'model_edit.json').exists() else None
                # Include all trajectory decisions, never infer a rejected edit's
                # effect on this obligation from its natural-language reason.
                affected.append(dict(round=r['round'],stage=r.get('stage'),classification=classify_round(r),
                    edit=edit,decision=r.get('decision'),source=str(rd)))
            independent=[]
            for g in grades:
                if g['id']!=entry['id']:continue
                independent.append(dict(fault=g['fault'],exposed=ob in g.get('exposed_obligations',[]),
                    fully_protected=ob in g.get('fully_transaction_protected_exposed_obligations',[]),
                    unknown=g['unknown_records'],unexposed_queries=g.get('no_exposure_queries',[])))
            if not targets:category='no_confirmed_development_exposure'
            elif not initial_labels:category='missing_component_requires_composition'
            elif not localized:category='exposed_without_localization_hypothesis'
            else:category='localized_existing_component_requires_proposal_and_gate_analysis'
            rows.append(dict(id=entry['id'],case_id=entry['case_id'],policy=entry['policy'],search=entry['search'],obligation=ob,
                development_target_ids=sorted(target_ids),development_evidence_source=entry['state'],
                baseline_labels=initial_labels,final_labels=final_labels,localized=localized,category=category,
                local_edit_scope='Only localized fields on existing labels; obligation mappings immutable. Findings are hypotheses, not proof of unique cause.',
                composition_observable=bool(targets),composition_needed_for_new_label=not bool(initial_labels),
                terminal_development_targets=len({v['id'] for v in endtargets}),
                terminal_timely_detected=len({v['id'] for v in endtargets if v['id'] in terminal['detected_ids']}),
                terminal_transaction_detected=len({v['id'] for v in endtargets if v['id'] in terminal.get('transaction_detected_ids',terminal['detected_ids'])}),
                independent=independent,round_records=affected))
    summary=[]
    for cid,ob in sorted({(r['case_id'],r['obligation']) for r in rows}):
        rr=[r for r in rows if r['case_id']==cid and r['obligation']==ob]
        summary.append(dict(case_id=cid,obligation=ob,trajectories=len(rr),
            development_exposed=sum(bool(r['development_target_ids']) for r in rr),
            declared_initially=sum(bool(r['baseline_labels']) for r in rr),declared_finally=sum(bool(r['final_labels']) for r in rr),
            categories=dict(Counter(r['category'] for r in rr))))
    result=dict(status='diagnosed_not_repaired',model_calls=0,native_calls=0,rows=rows,summary=summary,source_bindings=bindings,
        interpretation='Counts are paired trajectory-obligation records, not independent Bugs. No exposure is not a negative result or proof that a query cannot find it. Missing labels cannot be added through local fields.',
        contamination='All R197/R198 reserved faults and grades are now diagnostic material; do not claim them as fresh R199 generalization tests.')
    dump(out/'diagnosis.json',result)
    body=['<!doctype html><meta charset="utf-8"><title>R199 P0</title><style>body{font:16px/1.6 sans-serif;max-width:1200px;margin:35px auto}td,th{border:1px solid #aaa;padding:7px}table{border-collapse:collapse}pre{white-space:pre-wrap}</style><h1>R199：义务级缺口诊断</h1><p>无模型调用、无新仿真。定位结论是可检验假设，不能仅凭日志归因于某个机制。</p><p><a href="diagnosis.json">完整逐义务证据、提案、门判定及来源哈希</a></p><table><tr><th>案例</th><th>义务</th><th>轨迹</th><th>开发已曝光</th><th>初始组件</th><th>最终组件</th><th>分类</th></tr>']
    for r in summary:body.append('<tr>'+''.join('<td>'+escape(str(r[k]))+'</td>' for k in ('case_id','obligation','trajectories','development_exposed','declared_initially','declared_finally','categories'))+'</tr>')
    body+=['</table><p>事务检出增多只说明部分事务被保护；必要义务完整保护还要求义务被曝光且所有已曝光目标得到保护。改变既有组件的窗口或匹配表达式不会自动增加不可变的义务映射。</p><p>旧预留故障可用于此诊断，但据此设计后的新方法不能再把这些故障当作未见泛化证据。</p>']
    (out/'report.html').write_text('\n'.join(body),encoding='utf-8');print(json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);run(p.parse_args().out)
