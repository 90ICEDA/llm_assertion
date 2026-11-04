"""Separate requested operations from native-executed edits and accepted repairs.

Select every registered T trajectory before acceptance, so failed parsing cannot
silently remove a temporal-operator trial from the case material.
"""
import argparse
from collections import Counter
from html import escape
import json
from pathlib import Path
from research194_refinement_runner import read,dump,file_hash
from research194_report import table
from research196_results import classify_round,optional
from research197_cards import runtime


def requested_stage(entry,context):
    contract=context.get('output_contract',{});schema=contract.get('schema',{})
    if 'assertions' in schema:return 'free' if entry.get('arm') in ('F','P') or entry['strategy']!='R3' else 'regenerate'
    edits=schema.get('edits',[])
    return 'compose' if isinstance(edits,list) and edits and edits[0].get('op')=='add_assertion' else 'local'


def select(prepared,execution,out):
    prepared,execution,out=map(Path,(prepared,execution,out))
    if read(execution/'outcome.json')['status']!='completed_all_versions_frozen':raise ValueError('not_frozen')
    p=read(prepared/'protocol.json');rows=[];cards=[];bindings={};render=runtime().render
    def take(path,default=None):
        if not Path(path).exists():return default
        bindings[str(Path(path).resolve())]=file_hash(path);return read(path)
    for entry in p['entries']:
        folder=execution/entry.get('artifact_id',entry['id'])/'refinement';rounds=take(folder/'rounds.json',[])
        for index in range(1,entry['max_rounds']+1):
            rd=folder/f'round{index:02}';record=next((r for r in rounds if r['round']==index),None)
            request=take(rd/'request.preview.json');context=json.loads(request['messages'][-1]['content']) if request else {}
            edit=take(rd/'model_edit.json');native=take(rd/'proposal_native/measurement.json')
            operations=[e.get('op') for e in edit.get('edits',[]) if isinstance(e,dict)] if isinstance(edit,dict) else []
            row=dict(id=entry['id'],case_id=entry['case_id'],arm=entry.get('arm'),round=index,
                requested_stage=requested_stage(entry,context) if request else None,native_stage=record.get('stage') if record else None,
                classification=classify_round(record) if record else 'not_attempted',parse_error=record.get('error') if record else None,
                model_operations=operations,native_executed=native is not None,native_complete=native.get('native_complete') if native else None,
                reference_complete=native.get('reference_complete') if native else None,accepted=bool(record and record.get('status')=='accepted'))
            rows.append(row)
            if entry.get('arm')!='T':continue
            state=take(entry['state']);before=context.get('current_assertions',state['initial']);after=take(rd/'proposal.json')
            m=take(rd/'current_measurement.json',state['first_measurement'])
            interesting=[e for e in m['evidence'] if e.get('status')=='confirmed' and (e.get('label')=='violation' or any(a.get('failure') for a in e.get('assertions',[])))]
            witness=(interesting or m['evidence'])[0]
            job=next(j for j in m['executions'] if j['query_id']==witness['query_id'] and j['variant']==witness['variant'])
            waves=[t for t in job['trace'] if abs(t['cycle']-witness['cycle'])<=4]
            cards.append(dict(**row,original_sva=render(before,entry['case_id']),proposed_sva=render(after,entry['case_id']) if after else None,
                retained_sva=render(take(folder/'frozen.json'),entry['case_id']),model_response=edit,
                localization=take(rd/'localization.json'),key_evidence=witness,key_waveform=waves,
                decision=record.get('decision') if record else None,
                scope='All registered T trajectories; interface-rejected output has no validated proposal SVA. Developer handwritten probes are excluded.'))
    out.mkdir(parents=True,exist_ok=False)
    data=dict(selection_reads_acceptance=False,selection_rule='Every registered T trajectory, no success filter.',rows=rows,cards=cards,source_bindings=bindings)
    dump(out/'selection.json',data);dump(out/'seal.json',dict(sha256=file_hash(out/'selection.json')))
    print(dict(attempt_rows=len(rows),typed_cards=len(cards)),flush=True)


def attach(out,acceptance,report):
    out,acceptance,report=map(Path,(out,acceptance,report));data=read(out/'selection.json')
    if file_hash(out/'selection.json')!=read(out/'seal.json')['sha256']:raise ValueError('selection_changed')
    if (out/'selection.json').stat().st_mtime_ns>=(acceptance/'plan.json').stat().st_mtime_ns:raise ValueError('selection_after_acceptance')
    for path,h in data['source_bindings'].items():
        if file_hash(path)!=h:raise ValueError('source_changed')
    aa=read(acceptance/'results.json')
    for c in data['cards']:c['independent_acceptance']=[a for a in aa if a['id'] in (c['id'],c['case_id']+'/initial_control')]
    summary=[]
    for cid in sorted({r['case_id'] for r in data['rows']}):
        for stage in ('local','compose','regenerate','free'):
            rows=[r for r in data['rows'] if r['case_id']==cid and r['requested_stage']==stage]
            summary.append(dict(case_id=cid,requested_stage=stage,requests=len(rows),native_executed=sum(r['native_executed'] for r in rows),
                native_complete=sum(r['native_complete'] is True for r in rows),accepted=sum(r['accepted'] for r in rows),
                classifications=dict(Counter(r['classification'] for r in rows))))
    corrected=any(r['id'].endswith('/T_corrected') for r in data['rows'])
    coverage_name='temporal_operation_coverage_corrected.json' if corrected else 'temporal_operation_coverage.json'
    dump(out/'diagnostics.json',dict(**data,summary=summary));dump(report/coverage_name,dict(summary=summary,rows=data['rows']))
    def code(v):return '<pre>'+escape(v if isinstance(v,str) else json.dumps(v,ensure_ascii=False,indent=2))+'</pre>'
    body=['<!doctype html><meta charset="utf-8"><title>R197 typed-operation trials</title><style>body{font:15px/1.6 system-ui;max-width:1200px;margin:30px auto;padding:20px}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#eff4f6;padding:14px}.scroll{overflow:auto}td,th{border:1px solid #bdc9d1;padding:6px}table{border-collapse:collapse}</style>',
        '<h1>R197 专用操作：全部 T 轨迹</h1><p>按预注册轨迹全部展示，未按收益筛选。请求局部修改、成功解析、原生执行和通过接受门是不同事件。独立验收评价最终冻结版本。</p>',table(summary,[(k,k) for k in summary[0]])]
    for c in data['cards']:
        body+=['<h2>'+escape(c['id'])+'</h2>',code({k:c[k] for k in ('classification','parse_error','model_operations','native_executed','accepted')}),
            '<h3>原始 SVA</h3>',code(c['original_sva']),'<h3>关键采样波形</h3>',table(c['key_waveform'],[(k,k) for k in c['key_waveform'][0]]),
            '<h3>定位及模型输出</h3>',code(c['localization']),code(c['model_response']),'<h3>有效提案 SVA（解析失败时为空）</h3>',code(c['proposed_sva']),
            '<h3>最终保留 SVA</h3>',code(c['retained_sva']),'<h3>独立验收</h3>',code([{k:a.get(k) for k in ('id','fault','valid_reachable_fault','false_positive_records','transaction_detected','target_transaction_obligations','unknown_records','full_planned_transaction_scope_pass')} for a in c['independent_acceptance']])]
    (out/'cards.html').write_text('\n'.join(body),encoding='utf-8')
    label='纠正契约 T 组' if corrected else '原注册 T 组'
    page=report/'report.html';page.write_text(page.read_text(encoding='utf-8')+'\n<p><a href="../'+out.name+'/cards.html">'+label+'：全部专用操作轨迹、接口失败和独立验收</a> · <a href="'+coverage_name+'">请求／执行／接受覆盖矩阵</a></p>',encoding='utf-8')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['select','attach'])
    for key in ('prepared','execution','acceptance','report'):p.add_argument('--'+key,type=Path)
    p.add_argument('--out',required=True,type=Path);a=p.parse_args()
    select(a.prepared,a.execution,a.out) if a.action=='select' else attach(a.out,a.acceptance,a.report)
