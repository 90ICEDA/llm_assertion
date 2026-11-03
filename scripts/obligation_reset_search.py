"""Pre-registered focused sensitivity block: reset while a transaction is pending.

The original 648-query experiment is immutable. This additional block fixes a
coverage weakness in the old guided template and keeps the same natural pool.
"""
import argparse
import copy
import json
from pathlib import Path
import obligation_isolated_search as iso
from obligation_isolated_search import x


def guided(d,seed,step):
    rows=x.policy.guided(d,seed,step)
    if step%2:
        key=d['key']
        trigger=next(i for i,r in enumerate(rows[:-4]) if r[d['rst']] and
                     (r['frame_done_i'] if key=='stat' else r['flush_i'] and r['push_i']))
        # Cancellation is intentional and explicitly NOT transaction-preserving.
        rows[trigger+1][d['rst']]=0
        rows[trigger+2][d['rst']]=1
    return x.policy.repair_environment(d,rows)


def main(run):
    x.OUT=x.ROOT/'deliverables'/run;iso.configure()
    folder=x.OUT/'reset_sensitivity';folder.mkdir(exist_ok=False)
    protocol=dict(parents=['stat','spill'],methods=['ordinary','disagreement','obligation'],seed=20261023,
        queries_per_parent_method=12,cycles=24,query_unit='same dual-RTL submitted input schedule as main search',
        change='only guided odd-numbered query inserts sampled active-low reset immediately after a trigger, before its due observation; other policies unchanged',
        basis='frozen public reset_cancellation contract: reset cancels pending events; deadlines of uncancelled events still checked in absolute sampled cycles',
        rationale='main guided templates place reset after drain; reset occurrence alone does not exercise cancellation',
        cohort='unchanged legacy natural candidates; post-diagnostic focused sensitivity, not replacement for six-parent main result',
        attribution='independent reference first; no causal credit from coincident alarms',
        frozen_before_all_queries=True,model_calls=0,retries=0,cache_hits=0)
    x.dump(folder/'protocol.json',protocol)
    frozen={x.rel(p):x.sha(p) for p in [Path(__file__),folder/'protocol.json',*[x.OUT/'frozen'/k/'candidates.json' for k in protocol['parents']]]}
    x.dump(folder/'freeze.json',frozen)
    qs=[]
    for k in protocol['parents']:
        d=x.read(x.OUT/'frozen'/k/'definition.json');cs=x.read(x.OUT/'frozen'/k/'candidates.json')['candidates']
        for method in protocol['methods']:
            incumbent=None;best=-1
            for step in range(12):
                seed=protocol['seed']+1009*step
                if method=='ordinary':rows=x.policy.ordinary(d,seed)
                elif method=='disagreement':rows=x.policy.disagreement(d,seed,incumbent if step%3 else None)
                else:rows=guided(d,seed,step)
                ident=f'{k}/{method}/{step}'
                x.append(folder/'attempts.jsonl',dict(id=ident,input_sha256=x.digest(rows)))
                q=iso.evaluate(d,rows,cs,'reset_sensitivity/'+ident)
                cancelled=0
                for rr in q['runs']:
                    if rr['status']=='ok':cancelled+=len(x.read(x.ROOT/rr['run']/'independent_reference.json')['cancelled'])
                q.update(case=k,method=method,step=step,id=ident,cancelled_transactions=cancelled)
                x.append(folder/'queries.jsonl',q);qs.append(q)
                if method=='disagreement' and q['disagreement_score']>best:best=q['disagreement_score'];incumbent=rows
    result=[]
    for k in protocol['parents']:
        for method in protocol['methods']:
            rows=[q for q in qs if q['case']==k and q['method']==method]
            result.append(dict(case=k,method=method,queries=len(rows),gaps=sorted(iso.gaps(rows)),gap_count=len(iso.gaps(rows)),
                cancelled_transactions=sum(q['cancelled_transactions'] for q in rows),
                compiles=sum(q['compile_attempts'] for q in rows),simulations=sum(q['simulation_attempts'] for q in rows),
                wall_seconds=sum(q['wall_seconds'] for q in rows),cpu_seconds=sum(q['cpu_seconds'] for q in rows)))
    assert all(x.sha(x.ROOT/p)==h for p,h in frozen.items())
    assert all(r['cancelled_transactions']>0 for r in result if r['method']=='obligation')
    x.dump(folder/'summary.json',result)
    print(json.dumps(result))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);main(p.parse_args().run)
