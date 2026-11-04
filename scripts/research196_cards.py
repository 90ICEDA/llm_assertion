"""Select mechanism examples from development only, then attach frozen acceptance."""
import argparse
from html import escape
import json
import os
from pathlib import Path
from research194_refinement_runner import ROOT,read,dump,file_hash
from research194_cases import get_case
from research194_report import table
from research196_results import search_analysis,optional


def render(candidate,cid):
    disable=get_case(cid)['disable']
    return '\n'.join(f"{a['label']}: assert property (@(posedge clk) disable iff({disable}) ({a['antecedent']}) {'|=>' if a['timing']=='next_sample' else '|->'} ({a['consequent']}));" for a in candidate)


def select(prepared,execution,out):
    prepared,execution,out=map(Path,(prepared,execution,out))
    if read(execution/'outcome.json')['status']!='completed_all_versions_frozen':raise ValueError('campaign_not_frozen')
    out.mkdir(parents=True,exist_ok=False);p=read(prepared/'protocol.json');search=search_analysis(p,execution);choices=[]
    deltas=[dict(case_id=c['case_id'],seed=c['seed'],delta=c['checkpoints']['S3']['new_gap_count']-c['checkpoints']['S0']['new_gap_count'],
        cut=c['common_actual_query_seconds'],checkpoint=c['checkpoints']['S3'],comparator_checkpoint=c['checkpoints']['S0']) for c in search['common_cuts']]
    for label,positive in [('active_benefit',True),('active_no_benefit',False)]:
        rows=[r for r in deltas if (r['delta']>0 if positive else r['delta']<=0)]
        if rows:
            r=sorted(rows,key=lambda r:(-r['delta'] if positive else r['delta'],r['case_id'],r['seed']))[0]
            choices.append(dict(kind=label,id=f"{r['case_id']}/{r['seed']}/S3_R1",round=max(1,r['checkpoint']['queries']),development_search_comparison=r,
                selected_round_within_common_cost_cut=r['checkpoint']['queries']>0,
                claim='Evidence acquisition comparison only until independent results are attached.'))
    local_success=[];local_failure=[];composition=[]
    for e in p['entries']:
        if e['strategy']!='R3':continue
        for r in optional(execution/e['id']/'refinement/rounds.json',[]):
            item=dict(id=e['id'],round=r['round'],stage=r.get('stage'),status=r.get('status'),decision=r.get('decision'))
            if r.get('stage')=='local':
                if r.get('status')=='accepted':local_success.append(item)
                elif r.get('status')=='rejected':local_failure.append(item)
            if r.get('stage')=='compose' and r.get('status')=='accepted':composition.append(item)
    for label,rows in [('local_success',local_success),('local_failure',local_failure),('composition_success',composition)]:
        if rows:choices.append(dict(kind=label,**sorted(rows,key=lambda r:(r['id'],r['round']))[0]))
    cards=[];bindings={}
    for choice in choices:
        folder=execution/choice['id']/'refinement';rd=folder/f"round{choice['round']:02}"
        request=optional(rd/'request.preview.json',None);context=json.loads(request['messages'][-1]['content']) if request else {}
        state=read(next(e['state'] for e in p['entries'] if e['id']==choice['id']))
        before=context.get('current_assertions',state['initial']);after=optional(rd/'proposal.json',None)
        m=optional(rd/'current_measurement.json',state['first_measurement']);evidence=m['evidence']
        interesting=[e for e in evidence if e.get('status')=='confirmed' and (e['label']=='legal' and any(a.get('failure') for a in e.get('assertions',[])) or e['label']=='violation' and e.get('counted_target') and not any(a.get('failure') for a in e.get('assertions',[])))]
        localization=optional(rd/'localization.json',[])
        chosen_ids={i for finding in localization for i in finding.get('evidence_ids',[])}
        selected_query_id=None;search_choice=None
        if choice['kind'].startswith('active_'):
            acquired=optional(execution/choice['id']/f"acquisition/query{choice['round']-1:02}/acquisition.json",state['first_acquisition'])
            selected_query_id=acquired['query']['id']
            chosen_ids={g.split(':',1)[1] for g in acquired['new_gap_ids']}
            selected_rank=next(r for r in acquired['selection']['ranked'] if r['query_id']==selected_query_id)
            search_choice=dict(reason=acquired['selection']['reason'],chosen_score=selected_rank,query_constraints=acquired['query'].get('constraints'),
                query_obligations=acquired['query']['obligations'],actual_cost=acquired['cost'])
        linked=[e for e in interesting if e['id'] in chosen_ids and (selected_query_id is None or e['query_id']==selected_query_id)]
        witness=linked[0] if linked else interesting[0] if interesting else evidence[0]
        job=next(j for j in m['executions'] if j['query_id']==witness['query_id'] and j['variant']==witness['variant'])
        waves=[r for r in job['trace'] if abs(r['cycle']-witness['cycle'])<=3]
        records=optional(folder/'rounds.json',[]);record=next((r for r in records if r['round']==choice['round']),{})
        cid=choice['id'].split('/')[0]
        card=dict(**choice,original_sva=render(before,cid),proposed_sva=render(after,cid) if after else None,
            actually_retained_sva=render(read(folder/'frozen.json'),cid),localization=localization,
            sva_rendering='Preserves actual clock and disable condition; restores original property labels from native bundle aliases; diagnostic display actions omitted.',
            witness_linked_to_selected_evidence=bool(linked),selected_query_id=selected_query_id,
            search_choice=search_choice,
            model_edit=optional(rd/'model_edit.json',None),round_record=record,key_evidence=witness,key_waveform=waves,
            evidence_linkage=optional(rd/'evidence_linkage.json',None),frozen_sha256=read(folder/'outcome.json')['frozen_sha256'])
        cards.append(card)
        for path in [folder/'frozen.json',folder/'outcome.json',rd/'request.preview.json',rd/'proposal.json',rd/'current_measurement.json']:
            if path.exists():bindings[str(path.resolve())]=file_hash(path)
    data=dict(selection_read_independent_results=False,cards=cards,
        missing=[name for name,rows in [('local_success',local_success),('local_failure',local_failure),('composition_success',composition)] if not rows],
        source_bindings=bindings,selection_rule='Deterministic maximum/minimum shared-cost S3-vs-S0 gap examples; first sorted measured local success/failure and composition success. No independent quality used in example selection.')
    dump(out/'selection.json',data);dump(out/'seal.json',dict(sha256=file_hash(out/'selection.json')))
    print(dict(cards=len(cards),missing=data['missing']),flush=True)


def attach(out,acceptance):
    out,acceptance=Path(out),Path(acceptance);data=read(out/'selection.json')
    if read(out/'seal.json')['sha256']!=file_hash(out/'selection.json'):raise ValueError('example_selection_changed')
    for p,h in data['source_bindings'].items():
        if file_hash(p)!=h:raise ValueError('example_source_changed')
    if read(acceptance/'outcome.json')['status']!='completed':raise ValueError('acceptance_not_completed')
    aa=read(acceptance/'results.json');cards=[]
    for card in data['cards']:
        cid=card['id'].split('/')[0]
        versions=[r for r in aa if r['id']==card['id'] or r['id']==cid+'/initial_control']
        cards.append(dict(**card,independent_acceptance=versions,
            interpretation='Acceptance belongs to the terminal frozen SVA. A round proposal is not automatically that terminal SVA. Unknown and unexposed records remain explicit.'))
    dump(out/'cards.json',dict(cards=cards,missing=data['missing'],selection_read_independent_results=False))
    def code(value):return '<pre>'+escape(value if isinstance(value,str) else json.dumps(value,ensure_ascii=False,indent=2))+'</pre>'
    html=['<!doctype html><meta charset="utf-8"><title>R196 机制案例</title><style>body{font:15px/1.6 system-ui;max-width:1200px;margin:30px auto;padding:20px}pre{background:#eef3f6;white-space:pre-wrap;overflow-wrap:anywhere;padding:14px}.scroll{overflow:auto}table{border-collapse:collapse}td,th{border:1px solid #bdc9d1;padding:7px}</style><h1>R196 机制正反案例</h1><p>案例根据开发结果选定并在独立验收前封存；独立验收结果随后附加。证据增加不等于断言改善，提案也不等于最终保留版本。</p>']
    if data['missing']:html+=['<p>本轮没有符合条件的案例类型：'+escape(', '.join(data['missing']))+'。不以其他类型替代。</p>']
    for c in cards:
        brief=[{k:r.get(k) for k in ('id','fault','fault_kind','valid_reachable_fault','unknown_records','false_positive_records','transaction_detected','target_transaction_obligations','untriggered','no_exposure_queries','full_planned_transaction_scope_pass')} for r in c['independent_acceptance']]
        vcd=c['key_evidence'].get('source_vcd')
        waveform_link='<p><a href="'+escape(os.path.relpath(vcd,out).replace('\\','/'))+'">原始 VCD</a></p>' if vcd else ''
        html+=['<h2>'+escape(c['kind']+' — '+c['id'])+'</h2>','<h3>开发比较</h3>',code(c.get('development_search_comparison',c['round_record'])),
            '<h3>查询选择</h3>',code(c['search_choice']),'<h3>原始 SVA</h3>',code(c['original_sva']),'<h3>关键事务波形与证据</h3>',table(c['key_waveform'],[(k,k) for k in c['key_waveform'][0]]) if c['key_waveform'] else '<p>无可确认的波形。</p>',code(c['key_evidence']),
            waveform_link,
            '<h3>定位与修改</h3>',code(c['localization']),code(c['model_edit']),'<h3>修改提案</h3>',code(c['proposed_sva']),
            '<h3>最终保留 SVA</h3>',code(c['actually_retained_sva']),'<h3>独立验收及初始控制</h3>',code(brief)]
    html+=['<p><a href="cards.json">完整验收、波形路径与证据关联</a> · <a href="selection.json">验收前案例选择</a></p>']
    (out/'cards.html').write_text('\n'.join(html),encoding='utf-8')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['select','attach']);p.add_argument('--prepared',type=Path);p.add_argument('--execution',type=Path);p.add_argument('--acceptance',type=Path);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();select(a.prepared,a.execution,a.out) if a.action=='select' else attach(a.out,a.acceptance)
