"""Select examples from development records before independent acceptance."""
import argparse
from html import escape
import json
import os
from pathlib import Path
from research194_refinement_runner import read,dump,file_hash
from research194_report import table
from research198_paths import chains,structural_chains

def optional(path,default):return read(path) if Path(path).exists() else default

def select(prepared,execution,out):
    p=read(Path(prepared)/'protocol.json');execution=Path(execution);out=Path(out)
    if read(execution/'outcome.json')['status']!='completed_all_versions_frozen':raise ValueError('population_not_frozen')
    out.mkdir(parents=True,exist_ok=False);selected={};paths=[]
    for e in sorted(p['entries'],key=lambda x:x['id']):
        folder=execution/e['id']/'refinement';rounds=optional(folder/'rounds.json',[])
        native=[r.get('stage') for r in rounds if 'decision' in r]
        linked=chains(optional(folder/'controller_history.json',[]))
        structural=structural_chains(optional(folder/'controller_history.json',[]))
        paths.append(dict(id=e['id'],policy=e['policy'],native_stages=native,full_three_stage=bool(linked),linked_chains=linked,partial_improvement_structural_chains=structural))
        if e['policy']!='local_first':continue
        for r in rounds:
            if r.get('stage')=='local' and r.get('status') in ('accepted','rejected'):
                selected.setdefault(e['case_id']+'/local_'+r['status'],dict(entry=e,round=r['round']))
            if r.get('stage') in ('compose','regenerate') and 'decision' in r:
                selected.setdefault(r['stage']+'_native',dict(entry=e,round=r['round']))
        if paths[-1]['full_three_stage']:
            selected.setdefault('full_three_stage',dict(entry=e,round=max(r['round'] for r in rounds)))
        if structural:
            selected.setdefault('partial_improvement_structural_three_stage',dict(entry=e,round=structural[0]['rounds'][-1]))
    data=dict(selection_reads_independent_results=False,execution=str(execution.resolve()),cards=selected,paths=paths,
        source_bindings={str(Path(__file__).resolve()):file_hash(__file__),str(Path(prepared)/'protocol.json'):file_hash(Path(prepared)/'protocol.json')},
        missing_categories=[k for k in ('full_three_stage','compose_native','regenerate_native') if k not in selected])
    dump(out/'selection.json',data);dump(out/'seal.json',dict(sha256=file_hash(out/'selection.json')))
    print(dict(selected_cards=len(selected),full_native_paths=sum(r['full_three_stage'] for r in paths)),flush=True)

def sva(candidate):
    return '\n\n'.join(f"{a['label']}: assert property (@(posedge clk) disable iff (!rst_n)\n  ({a['antecedent']}) {'|=>' if a['timing']=='next_sample' else '|->'} ({a['consequent']}));" for a in candidate)

def attach(out,acceptance):
    out=Path(out);data=read(out/'selection.json')
    if file_hash(out/'selection.json')!=read(out/'seal.json')['sha256']:raise ValueError('selection_changed')
    aa=read(Path(acceptance)/'results.json');body=['<!doctype html><meta charset="utf-8"><title>R198 cases</title><style>body{font:15px/1.6 sans-serif;max-width:1200px;margin:35px auto}pre{white-space:pre-wrap;background:#eef2f6;padding:15px}table{border-collapse:collapse}td,th{border:1px solid #bbc;padding:7px}.scroll{overflow:auto}</style><h1>R198 自动局部与回退案例</h1><p>案例按开发阶段记录顺序选定，独立结果在冻结后附加；没有某类轨迹就明确缺失。</p>'];cards=[]
    def pre(v):return '<pre>'+escape(v if isinstance(v,str) else json.dumps(v,ensure_ascii=False,indent=2))+'</pre>'
    for key,chosen in data['cards'].items():
        e=chosen['entry'];folder=Path(data['execution'])/e['id']/'refinement';rd=folder/f"round{chosen['round']:02}"
        request=read(rd/'request.preview.json');context=json.loads(request['messages'][-1]['content'])
        current=read(rd/'current_measurement.json');wave=[]
        for label in ('violation','legal'):
            relevant=[v for v in context['development_observations'] if v.get('status')=='confirmed' and v.get('label')==label]
            if label=='legal':relevant=[v for v in relevant if any(a.get('failure') for a in v.get('assertions',[]))]
            wave += relevant[:3]
        grades=[r for r in aa if r['id']==e['id'] or r['id']==e['case_id']+'/initial_control']
        card=dict(category=key,id=e['id'],round=chosen['round'],original=read(folder/'initial.json'),before=context['current_assertions'],
            localization=context.get('localization',[]),evidence=wave,model_edit=optional(rd/'model_edit.json',None),
            proposal=optional(rd/'proposal.json',None),frozen=read(folder/'frozen.json'),history=read(folder/'controller_history.json'),independent_acceptance=grades,
            evidence_native_bindings=current['native_bindings'])
        cards.append(card);body += ['<h2>'+escape(key+' · '+e['id'])+'</h2><h3>原始 SVA</h3>',pre(sva(card['original'])),
            '<h3>关键事务采样及独立标签</h3>',pre(wave),'<h3>定位与模型修改</h3>',pre(card['localization']),pre(card['model_edit']),
            '<h3>提案 SVA</h3>',pre(sva(card['proposal'])) if card['proposal'] else '<p>接口失败，无合法提案。</p>',
            '<h3>冻结 SVA 与接受记录</h3>',pre(sva(card['frozen'])),pre(card['history']),'<h3>独立验收</h3>',
            table(grades,[(k,k) for k in ('id','fault','valid_reachable_fault','target_transaction_obligations','transaction_detected','false_positive_records','unknown_records','full_planned_transaction_scope_pass')])]
        links=[p for p in current['native_bindings'] if p.endswith('wave.vcd')]
        body += ['<p>原始波形：'+' · '.join('<a href="'+escape(os.path.relpath(p,out).replace('\\','/'))+'">VCD '+str(i+1)+'</a>' for i,p in enumerate(links))+'</p>']
    body += ['<h2>未覆盖类别</h2>',pre(data['missing_categories'])]
    dump(out/'cards.json',dict(cards=cards,missing_categories=data['missing_categories']));(out/'cards.html').write_text('\n'.join(body),encoding='utf-8')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['select','attach'])
    for k in ('prepared','execution','acceptance','out'):p.add_argument('--'+k,type=Path)
    a=p.parse_args();select(a.prepared,a.execution,a.out) if a.action=='select' else attach(a.out,a.acceptance)
