"""Matched original/corrected typed contracts; costs chosen before acceptance."""
import argparse
import copy
from html import escape
import json
from pathlib import Path
from research194_refinement_runner import ROOT,read,dump,file_hash
from research194_report import table
from research197_cost_sections import runtime as cost_runtime
from research197_results import analysis_runtime
import research197_diagnostics as diagnostics

GROUP={'C':{'F':'F','P':'P','T_original':'T','T_corrected':'T_corrected'}}


def register(prepared,corrected,execution,corrected_execution,registration,out,cards):
    prepared,corrected,execution,corrected_execution,registration,out,cards=map(Path,(prepared,corrected,execution,corrected_execution,registration,out,cards))
    for folder in (execution,corrected_execution):
        if read(folder/'outcome.json')['status']!='completed_all_versions_frozen':raise ValueError('all_models_must_freeze')
    p=read(prepared/'protocol.json');q=read(corrected/'protocol.json');entries=[];card_entries=[]
    for e in p['entries']:
        if e.get('arm') in ('F','P','T'):entries.append(dict(e,id=str((execution/e['id']).resolve())))
    for e in q['entries']:
        state=corrected_execution/'prepared_state'/e['id']/'state.json'
        entries.append(dict(id=str((corrected_execution/e['id']).resolve()),case_id=e['case_id'],seed=e['seed'],arm='T_corrected',search='S0',strategy='R3',mode='ready',state=str(state.resolve())))
        card_entries.append(dict(id=e['id']+'_corrected',artifact_id=e['id'],case_id=e['case_id'],seed=e['seed'],strategy='R3',arm='T',max_rounds=1,state=str(state.resolve())))
    out.mkdir(parents=True,exist_ok=False)
    inputs=out/'input_protocol';dump(inputs/'protocol.json',dict(entries=entries,case_ids=p['case_ids'],seeds=p['seeds']))
    dump(inputs/'acceptance_registration.json',read(registration/'registration.json'))
    m=cost_runtime();m.GROUPS=copy.deepcopy(GROUP);m.register(inputs,execution,out/'cost')
    data=read(out/'cost/registration.json')
    for path in (Path(__file__),prepared/'protocol.json',corrected/'protocol.json',registration/'registration.json'):
        data['source_bindings'][str(path.resolve())]=file_hash(path)
    dump(out/'cost/registration.json',data);dump(out/'cost/seal.json',dict(sha256=file_hash(out/'cost/registration.json')))
    cp=out/'card_protocol';dump(cp/'protocol.json',dict(entries=card_entries))
    diagnostics.select(cp,corrected_execution,cards)
    dump(out/'protocol.json',dict(prepared=str(prepared.resolve()),corrected=str(corrected.resolve()),execution=str(execution.resolve()),
        corrected_execution=str(corrected_execution.resolve()),cards=str(cards.resolve()),model_calls=0,
        scope='Same one-call F/P/T evidence. Original conflicting-contract T is retained; corrected T is an additional cohort. Costs use completed prefixes; no acceptance grades read.'))


def finish(out,acceptance,report):
    out,acceptance,report=map(Path,(out,acceptance,report));config=read(out/'protocol.json')
    m=cost_runtime();m.GROUPS=copy.deepcopy(GROUP);m.evaluate(out/'cost',acceptance);m.analyze(out/'cost')
    p=read(Path(config['prepared'])/'protocol.json');q=read(Path(config['corrected'])/'protocol.json')
    arms={e['id']:e.get('arm') for e in p['entries']}
    arms.update({e['id']+'_corrected':'T_corrected' for e in q['entries']})
    aa=copy.deepcopy(read(acceptance/'results.json'))
    for row in aa:
        if arms.get(row['id']):row.update(search_strategy='isolation',strategy=arms[row['id']])
    analysis=analysis_runtime();analysis.GROUPS['C']={a:'isolation_'+v for a,v in GROUP['C'].items()}
    pairs=analysis.paired(aa);cost=read(out/'cost/analysis.json');operations=[];calls=[]
    execution=Path(config['corrected_execution'])
    for e in q['entries']:
        folder=execution/e['id']/'refinement';rounds=read(folder/'rounds.json') if (folder/'rounds.json').exists() else []
        for r in rounds:
            rd=folder/f"round{r['round']:02}";edit=read(rd/'model_edit.json') if (rd/'model_edit.json').exists() else None
            operations.append(dict(id=e['id']+'_corrected',round=r['round'],classification=analysis.classify_round(r),stage=r.get('stage'),parse_error=r.get('error'),
                model_operations=[o.get('op') for o in edit.get('edits',[]) if isinstance(o,dict)] if isinstance(edit,dict) else [],accepted=r.get('status')=='accepted'))
        for path in folder.glob('round*/model_call/result.json'):calls.append(dict(id=e['id']+'_corrected',**read(path)))
    summary=dict(original_contract_defect='Typed-only allowlist contradicted the retained replace_field example and operation catalogue.',
        correction='Only output_contract changed; same candidates, evidence, seeds and acceptance rules. Original T results retained.',
        corrected_dispatches=len(list(execution.glob('*/*/*/refinement/round*/model_call/attempt.json'))),
        corrected_known_tokens=sum((r.get('prompt_tokens') or 0)+(r.get('completion_tokens') or 0) for r in calls),
        corrected_unknown_usage_calls=sum(r.get('prompt_tokens') is None or r.get('completion_tokens') is None for r in calls),
        corrected_accepted=sum(r['accepted'] for r in operations),operations=operations,
        paired_summary=[r for r in pairs['summary'] if r['group']=='C'],paired_cells=[r for r in pairs['cells'] if r['group']=='C'],
        cost_summary=cost['summary'],scope='Descriptive comparison on three parents and two seeds. Contract repair is distinct from proof of local-edit benefit.')
    dump(out/'results.json',summary);dump(report/'corrected_isolation.json',summary)
    diagnostics.attach(config['cards'],acceptance,report)
    page=report/'report.html';html=page.read_text(encoding='utf-8')
    rows=summary['paired_summary'];html+='\n<h2>纠正提示后的 F/P/T 比较</h2><p>旧 T 提示保留了被禁止操作的示例，存在契约冲突。旧结果继续单列；纠正 T 仅修改操作契约，使用相同候选、开发证据、种子和接受门，另获最多六次授权。</p>'
    html+=table(rows,[(k,k) for k in rows[0]])+'<p><a href="corrected_isolation.json">纠正组实际操作、独立验收及共同成本截面</a></p>'
    page.write_text(html,encoding='utf-8');print(dict(corrected_accepted=summary['corrected_accepted'],corrected_dispatches=summary['corrected_dispatches']),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['register','finish'])
    for key in ('prepared','corrected','execution','corrected-execution','registration','cards','acceptance','report'):p.add_argument('--'+key,type=Path)
    p.add_argument('--out',required=True,type=Path);a=p.parse_args()
    if a.action=='register':register(a.prepared,a.corrected,a.execution,a.corrected_execution,a.registration,a.out,a.cards)
    else:finish(a.out,a.acceptance,a.report)
