"""Private pre-refinement fault quarantine and causal paired-prefix acceptance.

These are explicitly artificial sibling faults, never historical fixes. The
control and mutant use identical input schedules and differ in one target RTL
rule. Only a first violation with an accepted legal counterfactual prefix can
receive causal-detection credit. No result is supplied to the model.
"""
import argparse
import copy
import json
from pathlib import Path
import obligation_isolated_search as iso
import obligation_refinement_block as refinement
from obligation_isolated_search import x

BLOCK=None
KEYS=('filter','fifo','stat')


def init():
    assert not (x.OUT/'refinement_r03/development').exists(),'freeze before any refinement queries'
    BLOCK.mkdir(exist_ok=False)
    replacements={
        'fifo':('assign empty_o=~push_i;', 'assign empty_o=~push_i | (push_i & ~pop_i & data_i[0]);'),
        'filter':("(filter_synced != filter_q) ? '0", "(filter_synced != filter_q) ? {{(CntWidth-1){1'b0}},1'b1}"),
        'stat':('assign stat_valid_o=valid_pipe[1];', "assign stat_valid_o=valid_pipe[1] && (stat_len_o != 8'd149);")}
    for k in KEYS:
        folder=BLOCK/'quarantine'/k;folder.mkdir(parents=True)
        text=(x.OUT/'frozen'/k/'correct.v').read_text();old,new=replacements[k]
        assert text.count(old)==1
        (folder/'correct.v').write_text(text);(folder/'buggy.v').write_text(text.replace(old,new))
        d=x.read(x.OUT/'frozen'/k/'definition.json');rows=[]
        for i in range(24):
            r={n:0 for n in d['inputs']};r[d['rst']]=int(i>=2 and i!=18)
            if k=='filter':r.update(enable_i=1,thresh_i=2,filter_i=int(i in range(6,11) or i>=15))
            if k=='fifo':r.update(push_i=int(3<=i<=9 or 12<=i<=17),pop_i=int(i in (9,17) or i>=19),data_i=149 if i<11 else 203)
            if k=='stat':r.update(frame_done_i=int(i in (3,9,17,20)),frame_len_i=149 if i<8 else 203 if i<16 else 149)
            rows.append(r)
        rows=x.policy.repair_environment(d,rows)
        assert not x.check_inputs(d,rows)
        x.dump(folder/'input.json',rows)
        x.dump(folder/'provenance.json',dict(origin='artificial_sibling_mutation',historical_bug=False,
            source=x.rel(x.OUT/'frozen'/k/'correct.v'),change=dict(before=old,after=new),
            source_contract=x.rel(x.OUT/'frozen'/k/'spec_sources.json'),
            target={'filter':'qualification must restart with zero prior intervals','fifo':'presented item is nonempty even while stalled','stat':'valid must arrive at exact two-sample deadline for every payload'}[k],
            known_control_limitation='stat control invalid on overlapping lengths; hidden schedule uses spaced events so this issue is independently checked rather than presumed absent'))
    x.dump(BLOCK/'protocol.json',dict(frozen_before='all four-arm refinement queries and model calls',
        lineage='built after stage2 search began; never queried in stage2 or model development; no claim this quarantine preceded stage2',
        scenario_origin='three new same-target fault rules plus lawful reset/idle/backpressure inputs',
        isolation='private directory absent from model allowlist; hash checked before evaluation; final assertions frozen first',
        causal_rule='same input, same observed prefix before first violation, legal control prefix accepted, mutant alarms at due first violation; exactly one target observed output differs',
        per_parent_scenarios=1,acceptance_scope='these finite isolated faults only; no full-parent correctness proof'))
    x.dump(BLOCK/'freeze.json',{x.rel(p):x.sha(p) for p in [Path(__file__),BLOCK/'protocol.json',*BLOCK.glob('quarantine/*/*')] if p.is_file()})
    print('fault holdout frozen before model refinement')


def evaluate():
    assert all(x.sha(x.ROOT/p)==h for p,h in x.read(BLOCK/'freeze.json').items())
    freeze=x.read(x.OUT/'refinement_r03/final_freeze.json')
    assert len(freeze)==12 and all(x.sha(x.ROOT/p)==h for p,h in freeze.items())
    (BLOCK/'evaluation').mkdir(exist_ok=False);iso.configure()
    x.engine.sources=lambda d:(BLOCK/'quarantine'/d['key']/'correct.v',BLOCK/'quarantine'/d['key']/'buggy.v')
    result=[]
    for k in KEYS:
        d=x.read(x.OUT/'frozen'/k/'definition.json');rows=x.read(BLOCK/'quarantine'/k/'input.json')
        for arm in ('A','B','C','D'):
            for version in ('initial','final'):
                cs=x.read(x.OUT/'refinement_r03/initial'/f'{k}.json') if version=='initial' else x.read(x.OUT/'refinement_r03/development'/k/arm/'final.json')['candidates']
                q=iso.evaluate(d,rows,cs,f'fault_holdout/{k}/{arm}/{version}')
                x.append(BLOCK/'queries.jsonl',dict(case=k,arm=arm,version=version,**q))
                verdict=dict(case=k,arm=arm,version=version,status=q['status'],causal_detections=[],misses=[],unknown_attribution=[],false_positive_cycles=[])
                if q['status']=='ok':
                    r={v['variant']:x.ROOT/v['run'] for v in q['runs']}
                    traces={v:x.read(f/'trace.json') for v,f in r.items()}
                    oracles={v:x.read(f/'independent_reference.json') for v,f in r.items()}
                    checks={v:{z[0]['cycle']:any(c['fail'] for c in z) for z in zip(*[x.read(f/f'checker_{j}_cycles.json') for j in range(len(cs))])} for v,f in r.items()}
                    control={o['cycle']:o for o in oracles['correct']['events']}
                    for o in oracles['correct']['events']:
                        if o['legal_prefix'] and checks['correct'][o['cycle']]:verdict['false_positive_cycles'].append(o['cycle'])
                    for o in oracles['buggy']['events']:
                        if not o['first_violation']:continue
                        t=o['cycle'];start=max(i for i in range(t+1) if not rows[i][d['rst']])
                        earlier=range(start+1,t)
                        same=all(all(traces['correct'][i][n]==traces['buggy'][i][n] for n in d['observation_base']) for i in earlier)
                        no_prior=not any(checks['buggy'].get(i,False) for i in earlier)
                        control_accept=control[t]['legal_prefix'] and not any(checks['correct'].get(i,False) for i in range(start+1,t+1))
                        changed=[n for n in d['observation_base'] if traces['correct'][t][n]!=traces['buggy'][t][n]]
                        ev=dict(cycle=t,transaction_obligations=[c for c in o['checks'] if not c['passed']],changed_ports=changed)
                        if same and no_prior and control_accept and len(changed)==1 and checks['buggy'][t]:verdict['causal_detections'].append(ev)
                        elif no_prior and not checks['buggy'][t]:verdict['misses'].append(ev)
                        else:verdict['unknown_attribution'].append(ev)
                result.append(verdict)
    x.dump(BLOCK/'evaluation/results.json',result)
    print(json.dumps([dict(case=r['case'],arm=r['arm'],version=r['version'],causal=len(r['causal_detections']),miss=len(r['misses']),fp=len(r['false_positive_cycles']),unknown=len(r['unknown_attribution'])) for r in result]))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);p.add_argument('action',choices=['init','evaluate'])
    a=p.parse_args();x.OUT=x.ROOT/'deliverables'/a.run;BLOCK=x.OUT/'fault_holdout_r03';globals()[a.action]()
