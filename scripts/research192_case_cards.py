"""Bind representative archived evidence to exact SVA, waveform and decisions."""
import argparse
import hashlib
import html
import json
from pathlib import Path
import sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]


def main(out):
    out.mkdir(parents=True,exist_ok=False)
    bindings={}
    def text(path):
        p=ROOT/path
        bindings[path]=hashlib.sha256(p.read_bytes()).hexdigest()
        return p.read_text(encoding='utf-8')
    def read(path):return json.loads(text(path))
    cards=[]
    prep='deliverables/research145_stability_prepare_20261027_r02/candidates/'
    run='deliverables/research145_stability_real_20261027_r01/cells/'
    details=read('deliverables/research151_stability_audit_20261027_r01/case_details.json')
    for cid,kind in [('s14501_c00','confirmed_improvement_without_mechanism_discrimination'),
                     ('s14501_c01','regression_rejected')]:
        folder=run+cid+'/shared/v0/'
        initial=read(prep+cid.split('_')[-1]+'/initial.json')
        modified=text(folder+'model_call/candidate.sva')
        detail=next(x for x in details if x['id']==cid)
        decision=read(folder+'native/decision.json')
        cohort='search' if cid.endswith('c00') else 'history'
        samples=read(folder+'native/'+cohort+'/samples.json')
        logpath=folder+'native/'+cohort+'/after/execute.log'
        log=text(logpath)
        lines=log.splitlines()
        alarms=[(i,line) for i,line in enumerate(lines) if line.startswith('ASSERT_FAIL')]
        excerpt=lines[max(0,alarms[0][0]-4):alarms[0][0]+5] if alarms else [line for line in lines if line.startswith('TRACE')][:12]
        cards.append(dict(id=cid,mechanism='refinement_historical',kind=kind,parent_bug='lowRISC/ibex#166',
            original_sva=[a['property'] for a in initial['assertions']],modified_sva=modified,
            localization=('initial trigger only checks OP bit31, misses bit28; proposal adds bit28 obligation component' if cid.endswith('c00') else
                          'nonoverlapped |=> illegal_insn crosses instruction transaction boundary, producing legal-control false alarms'),
            localization_origin='retrospective interpretation, not newly executed TFL',
            decision=decision,stage_summary=detail,sample_map=samples[:12],key_transaction_excerpt=excerpt,
            artifacts=dict(initial=prep+cid.split('_')[-1]+'/initial.json',modified=folder+'model_call/candidate.sva',
                waveform=folder+'native/'+cohort+'/after/wave.vcd',trace=logpath,
                acceptance=folder+'native/decision.json',independent='deliverables/research151_stability_audit_20261027_r01/audit.json'),
            limitation='O and H agree; this supports repair/rejection behavior, not local-repair superiority or historical-gate increment'))
    ex=read('deliverables/research125_search_expansion_report_20261025_r01/examples.json')
    # Select by explicit evidence label, never by an unverified success claim.
    selected=next((x for x in ex if x['discovery']['method']=='candidate_disagreement'),ex[0])
    witness=selected['witness']
    tracefolder=witness['evidence']['source_directory'].replace('/mnt/d/AssertionForge-main1/','')
    replaypath=tracefolder+'/replay.json'
    replay=read(replaypath) if (ROOT/replaypath).exists() else None
    cycle=witness['evidence']['cycle']
    rows=[] if replay is None else [r for r in replay.get('trace',[]) if cycle-2<=r.get('cycle',-999)<=cycle+2]
    cards.append(dict(id='fifo_valid_withdraw_discovery',mechanism='search_historical',kind='confirmed_gap_not_refined_in_this_run',
        original_sva=[a['property'] for a in selected['candidate']['assertions']],modified_sva=None,
        localization='data-stability assertion requires current valid and only constrains data; valid withdrawal escapes the trigger/response obligation',
        localization_origin='retrospective interpretation',key_transaction_waveform=rows,confirmed_witness=witness,
        artifacts=dict(search=selected['discovery']['source'],waveform=tracefolder+'/wave.vcd',trace=replaypath,
            acceptance='deliverables/research125_search_expansion_report_20261025_r01/result.json'),
        limitation='No accepted modified version or independent test in this search run; cannot fabricate a successful search-to-repair chain'))
    negative=read('deliverables/research125_search_expansion_report_20261025_r01/result.json')
    cards.append(dict(id='contract_novelty_negative',mechanism='search_historical',kind='no_exclusive_gain',
        queries=sum(x['queries'] for x in negative['methods'].values()),
        method_gap_counts={k:len(v['keys']) for k,v in negative['methods'].items()},
        exclusive_contract=negative['contract_exclusive_keys'],original_sva=None,modified_sva=None,
        localization='contract novelty selected a narrower effective mechanism population; zero exclusive confirmed gaps and no refinements',
        artifacts=dict(result='deliverables/research125_search_expansion_report_20261025_r01/result.json',
            detailed_examples='deliverables/research125_search_expansion_report_20261025_r01/examples.json'),
        limitation='aggregate negative result, not a paired single-SVA edit'))
    exposure=read('deliverables/research191_fifo_exposure_audit_20261103_r02/scene_causes.json')
    missing=next(x for x in exposure if not x['old_exposed'])
    cards.append(dict(id='fifo_drop_no_exposure',mechanism='acceptance',kind='confirmed_exposure_failure',
        original_sva=text('deliverables/research190_fifo_independent_20261103_r01/frozen/candidate.sva'),modified_sva=None,
        localization='drop latch clears in idle gap but second capacity overflow rolls back frame before externally visible leak',
        scene=missing,acceptance='unchanged20/32; missing exposure is not SVA false negative',
        artifacts=dict(waveform='deliverables/research190_fifo_independent_20261103_r01/native/'+missing['scene_id']+'/before/wave.vcd',
            cycles='deliverables/research191_fifo_exposure_audit_20261103_r02/cycles/'+missing['scene_id']+'/before.jsonl',
            acceptance='deliverables/research190_fifo_independent_20261103_r01/summary.json'),
        limitation='Read-only diagnosis; if reused to tune generators, entire batch becomes development'))
    for card in cards:
        card['new_experiment']=False
        for p in card.get('artifacts',{}).values():
            if p and (ROOT/p).is_file():
                bindings[p]=hashlib.sha256((ROOT/p).read_bytes()).hexdigest()
    (out/'case_cards.json').write_text(json.dumps(cards,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (out/'source_bindings.json').write_text(json.dumps(bindings,indent=2)+'\n',encoding='utf-8')
    body='<!doctype html><meta charset="utf-8"><title>REGuard evidence cards</title><style>body{font:15px system-ui;margin:30px;color:#192839}pre{white-space:pre-wrap;background:#f0f3f8;padding:16px}article{margin-bottom:48px}a{overflow-wrap:anywhere}</style><h1>REGuard 历史正面与失败案例</h1><p>所有案例为既有运行的可追溯回顾；不宣称新机制优于旧方法。未发生的修改明确为null。</p>'
    for c in cards:
        body+='<article><h2>'+html.escape(c['id'])+'</h2><p>'+html.escape(c['kind'])+'</p><pre>'+html.escape(json.dumps({k:v for k,v in c.items() if k!='artifacts'},ensure_ascii=False,indent=2))+'</pre>'
        for k,p in c['artifacts'].items():
            body+='<p>'+html.escape(k)+': <a href="'+html.escape('../../'+p)+'">'+html.escape(p)+'</a></p>'
        body+='</article>'
    (out/'case_cards.html').write_text(body,encoding='utf-8')
    print(json.dumps(dict(output=str(out.relative_to(ROOT)),case_cards=len(cards),bound_sources=len(bindings))))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',required=True)
    args=p.parse_args();out=(ROOT/args.out).resolve()
    if not out.is_relative_to(ROOT/'deliverables'):raise ValueError('deliverables only')
    main(out)
