"""Local qualification and sealed-request report; never a model-results report."""
import argparse
from html import escape
import json
import os
from pathlib import Path
from research194_refinement_runner import ROOT,read,dump,file_hash
from research197_prepare import verify


def run(prepared,out):
    prepared=Path(prepared).resolve();out=Path(out).resolve()
    p=verify(prepared);review=read(prepared/'review.json')
    out.mkdir(parents=True,exist_ok=False);bindings={};links=[]
    def take(path):
        path=Path(path);bindings[str(path.resolve())]=file_hash(path);return read(path)
    def link(path,label):
        path=Path(path);links.append(path)
        return '<a href="'+escape(os.path.relpath(path,out).replace('\\','/'))+'">'+escape(label)+'</a>'
    def table(rows):
        if not rows:return '<p>No records.</p>'
        keys=list(rows[0])
        return '<table><tr>'+''.join('<th>'+escape(k)+'</th>' for k in keys)+'</tr>'+''.join('<tr>'+''.join('<td>'+escape(str(r.get(k)))+'</td>' for k in keys)+'</tr>' for r in rows)+'</table>'
    qualification=take(Path(p['qualification'])/'summary.json')
    local=take(Path(p['local_qualification'])/'outcome.json')
    sources=take(ROOT/'deliverables/research197_history_sources_20261104_r01/provenance.json')
    evidence=[];seen=set();requests=[]
    for e in p['entries']:
        state=take(e['state']);request=take(e['request'])
        requests.append(dict(id=e['id'],mode=e['mode'],max_rounds=e['max_rounds'],file_bytes=Path(e['request']).stat().st_size,
                             content_bytes=sum(len(m['content'].encode()) for m in request['messages'])))
        key=(e['case_id'],e['seed'],e['search'])
        if key in seen:continue
        seen.add(key);a=state['first_acquisition']
        evidence.append(dict(case_id=e['case_id'],seed=e['seed'],strategy=e['search'],new_context_gaps=len(a['new_gap_ids']),
            actual_seconds=a['cost']['r196_total_seconds'],predicted_seconds=a['cost']['predicted_acquisition_seconds'],
            critical_unknown=len(a['measurement']['critical_unknown'])))
    controls=[dict(case_id=q['case_id'],max_pending=q['max_simultaneously_pending'],correct_reference_legal=q['correct_reference_legal'],**c) for q in qualification for c in q['controls']]
    report=dict(status='qualified_and_sealed_not_model_executed',model_calls=0,review={k:v for k,v in review.items() if k!='requests'},
        qualification=qualification,local_qualification=local,first_acquisitions=evidence,request_sizes=requests,
        remaining=['New seal-bound external model authorization and actual S/R/A plus F/P/T execution.',
                   'Cost-only checkpoint selection, frozen versions, independent new-input and reserved-fault acceptance.',
                   'Final paired tables, actual model operation/fallback coverage and evidence-to-independent-outcome cards.'],
        limits=p['limits']+['Two source-confirmed historical fixes; ID-queue fault is explicitly artificial.',
            'Handwritten qualification proposals and full fallback probe do not count as model successes.',
            'Four generated schedule families per case remain bounded coverage, not arbitrary protocol exploration.',
            'First-query context gaps are neither independent bugs nor evidence of final assertion improvement.'])
    dump(out/'report.json',report)
    parts=['<!doctype html><meta charset="utf-8"><title>REGuard R197 qualification and request review</title>',
      '<style>body{font:16px system-ui;max-width:1240px;margin:32px auto;padding:20px;color:#153247}table{border-collapse:collapse;width:100%;font-size:13px}th,td{border:1px solid #c6d2da;padding:8px;text-align:left}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f1f5f7;padding:16px}a{color:#1265a1}</style>',
      '<h1>REGuard R197：真实时序与历史修复补充</h1><p>本地资格验证与请求封存已完成；新模型调用为 0。手写控制提案不计为模型修复结果，尚无本轮独立验收结果。</p>',
      '<p>'+link(ROOT/'deliverables/reguard_mechanisms_20261104_r05/report.html','R196 完整历史报告')+' · '+link(prepared/'protocol.json','封存协议')+' · '+link(prepared/'review.json','请求清单')+' · '+link(out/'report.json','本报告数据')+'</p>',
      '<h2>原生 RTL 资格验证</h2>'+table(controls),
      '<p>stream_delay：common_cells PR #190 原始修复前后，检查年龄 18..21 的有限响应窗口及握手。delta_counter：PR #242 原始修复前后，检查精确下一周期溢出。ID queue：上游真实 RTL，三笔不同 ID 同时在途、逆序读取、peek 和 clear，开发故障为人工数据翻转。</p>',
      '<p>'+link(ROOT/'deliverables/research197_history_sources_20261104_r01/provenance.json','PR #190 来源和哈希')+' · '+link(Path(p['qualification'])/'outcome.json','原生资格结果')+' · '+link(Path(p['local_qualification'])/'typed_operations.json','专用操作回执')+' · '+link(Path(p['local_qualification'])/'fallback.json','三阶段回退回执')+'</p>',
      '<h2>专用操作与回退</h2><pre>'+escape(json.dumps(local,ensure_ascii=False,indent=2))+'</pre>',
      '<h2>首轮 S0–S3（尚非完整自适应搜索曲线）</h2>'+table(evidence),
      '<h2>模型实验注册</h2><pre>'+escape(json.dumps(report['review'],ensure_ascii=False,indent=2))+'</pre>',
      '<p>主实验为三个父案例、两个种子、八种搜索/细化配置，每轨迹最多三轮。另有同证据 F/P/T 单轮隔离对照：F 自由修改且无定位提示，P 自由修改且有定位提示，T 仅允许专用局部操作；三组共享历史和组件触发接受门。实际调用及未知失败必须在执行后另报。</p>',
      '<h2>尚待执行与覆盖边界</h2><pre>'+escape(json.dumps(dict(remaining=report['remaining'],limits=report['limits']),ensure_ascii=False,indent=2))+'</pre>']
    (out/'report.html').write_text('\n'.join(parts),encoding='utf-8')
    checks=[dict(path=str(path),exists=path.exists()) for path in links]
    if not all(c['exists'] for c in checks):raise ValueError('missing_report_link')
    audit=dict(status='passed',model_calls=0,protocol_sha256=file_hash(prepared/'protocol.json'),
        reconstructed_requests=len(p['entries']),verified_bound_sources=len(p['source_bindings']),
        native_evidence_binding_validation='research197_prepare.verify completed',link_checks=checks)
    dump(out/'source_bindings.json',bindings);dump(out/'audit.json',audit)
    print(dict(report=str(out/'report.html'),model_calls=0,maximum_model_calls=p['maximum_model_calls']),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--prepared',required=True,type=Path);parser.add_argument('--out',required=True,type=Path)
    args=parser.parse_args();run(args.prepared,args.out)
