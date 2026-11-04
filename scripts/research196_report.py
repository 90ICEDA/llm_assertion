"""Evidence-linked progress report; never equates a prepared campaign with results."""
import argparse
from html import escape
import json
import os
from pathlib import Path
from research194_refinement_runner import ROOT,read,dump,file_hash
from research194_cases import render


def local(path):
    value=str(path).replace('/mnt/d/AssertionForge-main1',str(ROOT))
    return Path(value)


def summarize(m):
    return dict(targets=len(m['targets']),timely_detected=len(m['detected_ids']),
        false_positive_records=len(m['false_positives']),critical_unknown=len(m['critical_unknown']),
        native_complete=m['native_complete'],reference_complete=m['reference_complete'])


def run(out):
    out=Path(out);out.mkdir(parents=True,exist_ok=False);d=ROOT/'deliverables';bindings={}
    def take(path):
        path=local(path);bindings[str(path)]=file_hash(path);return read(path)
    guard=take(d/'research196_guard_qualification_20261103_r01/outcome.json')
    audit=take(d/'research196_guard_qualification_20261103_r01/results.json')
    temporal=take(d/'research196_temporal_qualification_20261103_r01/outcome.json')
    acquisitions=d/'research196_first_acquisitions_20261103_r01'
    first=take(acquisitions/'progress.json');paid=take(acquisitions/'protocol.json')
    rows=[]
    for strategy in ('S0','S1','S2','S3'):
        group=[r for r in first if r['strategy']==strategy];records=[take(r['path']) for r in group]
        gaps=set().union(*(set(r['new_gap_ids']) for r in records))
        rows.append(dict(strategy=strategy,queries=len(group),confirmed_context_gap_ids=len(gaps),unknown_units=sum(r['unknown']>0 for r in group),
            native_jobs=sum(r['cost']['native_execution_attempts'] for r in group),
            actual_acquisition_seconds=sum(r['cost']['r196_total_seconds'] for r in group),
            predicted_seconds=sum(r['cost']['predicted_acquisition_seconds'] for r in group)))
    cards=[]
    independent=take(d/'research195_refinement_independent_20261103_r02/results.json')
    for fixture in ('exception','window'):
        identity=f'{fixture}/19507/L';folder=d/'research195_refinement_execute_20261103_r01'/identity/'refinement';rd=folder/'round01'
        before=take(folder/'initial.json');after=take(rd/'proposal.json');m=take(rd/'current_measurement.json')
        proposal=take(rd/'proposal_native/measurement.json')
        decision=next(a for a in audit if a['id']==identity)
        anchors=[e for e in m['evidence'] if e['status']=='confirmed' and e['label']=='legal' and any(a.get('failure') for a in e['assertions'])]
        witness=anchors[0] if anchors else m['evidence'][0]
        job=next(j for j in m['executions'] if j['query_id']==witness['query_id'] and j['variant']==witness['variant'])
        wave=[r for r in job['trace'] if abs(r['cycle']-witness['cycle'])<=3]
        accepted=next(r for r in independent if r['id']==identity)
        control=next(r for r in independent if r['id']==fixture+'/initial_control')
        cards.append(dict(id=identity,origin='Archived real model response; fresh component-gate verification, zero new model calls.',
            original_sva=render(before),proposal_sva=render(after),localization=take(rd/'localization.json'),edit=take(rd/'model_edit.json'),
            development_before=summarize(m),development_after=summarize(proposal),runtime_decisions=decision,
            key_evidence=witness,key_waveform=wave,source_vcd=witness['source_vcd'],
            independent_before=summarize(take(control['projection'])),independent_after=summarize(take(accepted['projection'])),
            independent_scope='R195 new input replay on development fault instances; not unseen-fault generalization. Window proposal is rejected by R196 and its R195 outcome must not count as an R196 success.'))
    report=dict(version='research196',status='core_fixes_qualified_latest_model_campaign_pending_authorization',guard=guard,temporal=temporal,
        first_query_comparison=rows,first_query_scope='One paid query per case/seed/strategy; context gaps, not independent parent bugs. No full adaptive curve or model improvement claim.',
        cost_models=paid['cost_models'],cards=cards,new_model_calls=0,
        limitations=['General-window and multiple-outstanding qualification uses synthetic interfaces, not new real RTL/model repair cases.',
            'No new historical repair case added in this patch.',
            'Latest combined model experiment and reserved-fault acceptance not executed.',
            'UART/Ibex calibration has no length variation; fitted slope is zero, fixed cost only. Runtime prediction errors remain.'])
    dump(out/'report.json',report);dump(out/'source_bindings.json',bindings)
    def table(records):
        if not records:return ''
        keys=list(records[0]);return '<table><tr>'+''.join('<th>'+escape(k)+'</th>' for k in keys)+'</tr>'+''.join('<tr>'+''.join('<td>'+escape(str(r.get(k)))+'</td>' for k in keys)+'</tr>' for r in records)+'</table>'
    def code(value):return '<pre>'+escape(value if isinstance(value,str) else json.dumps(value,ensure_ascii=False,indent=2))+'</pre>'
    html=['<!doctype html><meta charset="utf-8"><title>REGuard R196 补充验证</title><style>body{font:16px system-ui;max-width:1180px;margin:40px auto;padding:20px;color:#183047}table{border-collapse:collapse;width:100%;font-size:13px}td,th{border:1px solid #b9c7d0;padding:8px;text-align:left}pre{background:#eff3f6;padding:16px;white-space:pre-wrap;overflow-wrap:anywhere}h1,h2{color:#12456b}</style>',
        '<h1>REGuard R196：接受门修复与新版实验准备</h1><p>尚未全部完成。新模型调用为 0；封包不等于实验结果，执行完成也不等于验收通过。</p>',
        '<p><a href="../reguard_mechanisms_20261103_r03/report.html">上一版完整报告</a> · <a href="report.json">本报告数据</a> · <a href="../research196_refinement_prepare_20261103_r01/review.json">新请求清单</a></p>',
        '<h2>组件接受门</h2>',code(guard),'<p>改动组件必须在已确认且对应义务的原生回放中有采样触发记录。触发计数来自辅助前件监视器，不是原生 cover 或形式证明。有限回放无触发会被拒绝，不能解释为已证明逻辑空触发。</p>',
        '<h2>实际开销模型与首轮 S0–S3</h2><p>计入固定编译开销、执行及规划时间，扣除明确的调度锁等待。下表仅为首轮查询；缺口按上下文去重，不是独立父 Bug 数。</p>',table(rows),
        '<h2>一般窗口与多在途接口资格验证</h2>',code(temporal),'<p>原生并发断言执行与独立事件监视器核对；尚未接入真实 RTL 的模型修复对照。</p>']
    for c in cards:
        html += ['<h2>'+escape(c['id'])+'</h2><p>'+('纯局部修改正例：增加 flush 合法例外，减少合法误报，未新增目标检出；完整义务保护仍未通过。' if c['id'].startswith('exception') else '失败例：窗口组件失去触发，旧聚合门接受，新运行时门拒绝。')+'</p>',
            '<h3>原始 SVA</h3>',code(c['original_sva']),'<h3>定位与模型修改</h3>',code(c['localization']),code(c['edit']),
            '<h3>关键事务采样波形</h3>',table(c['key_waveform']),'<p><a href="'+escape(os.path.relpath(local(c['source_vcd']),out).replace('\\','/'))+'">原始 VCD 波形</a></p>','<h3>提案 SVA</h3>',code(c['proposal_sva']),
            '<h3>开发回放</h3>',table([dict(version='before',**c['development_before']),dict(version='proposal',**c['development_after'])]),
            '<h3>独立新输入记录（R195，非未见故障）</h3>',table([dict(version='before',**c['independent_before']),dict(version='R195 frozen',**c['independent_after'])]),
            '<p>完整运行时决定、证据 ID 和 VCD 原路径见 report.json。</p>']
    html += ['<h2>剩余边界</h2>',code(report['limitations'])]
    (out/'report.html').write_text('\n'.join(html),encoding='utf-8')
    print(dict(report=str(out/'report.html'),new_model_calls=0),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.out)
