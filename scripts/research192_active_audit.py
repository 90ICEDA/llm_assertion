"""Read-only raw-output oracle replay and exact active-selector replay."""
import argparse
import collections
import json
from pathlib import Path
import time

import research192_active_search as run
import research_active_temporal as active

x, old = run.x, run.old


def audit(out):
    run.guard(out);run.setup(out)
    # Main v2 source must match its pre-execution snapshot; v1 is explicitly separate.
    for p in (out/'source_snapshot').glob('*.py'):
        assert x.sha(p)==x.sha(run.ROOT/'scripts'/p.name),p.name
    qs=[json.loads(s) for p in sorted((out/'search').glob('*/queries.jsonl')) for s in p.read_text().splitlines()]
    assert len(qs)==864
    cells=collections.Counter((q['case'],q['seed'],q['method']) for q in qs)
    assert len(cells)==72 and set(cells.values())=={12}
    start=time.perf_counter();raw_runs=0;oracle_checks=0;selector_checks=0
    for case in old.CASES:
        cq=[q for q in qs if q['case']==case]
        attempts=[json.loads(s) for s in (out/'search'/case/'attempts.jsonl').read_text().splitlines()]
        assert [a['query_id'] for a in attempts]==[q['query_id'] for q in cq]
        d=x.read(out/'frozen'/case/'definition.json')
        candidates=x.read(out/'frozen'/case/'candidates.json')['candidates']
        obligations=[o['obligation_id'] for o in x.read(out/'obligation_catalog.json') if o['case']==case]
        for q in cq:
            assert q['spec_status']=='scoped' or not q['evidence']
            for r in q['runs']:
                folder=run.ROOT/r['run'];raw=x.read(folder/'result.json')
                assert x.sha(folder/'rtl.v')==raw['rtl_sha256']
                assert x.sha(folder/'input.json')==raw['input_sha256']
                trace,checks=x.parse_stdout(folder/'simulate.stdout')
                ref=x.monitor(d,trace)
                assert ref==x.read(folder/'independent_reference.json')
                ev=[x.evidence(d,trace,checks[j],ref) for j in range(len(checks))]
                assert ev==x.read(folder/'independent_evidence.json')
                raw_runs+=1;oracle_checks+=len(ev)
        for seed in run.SEEDS:
            selector=active.ActiveSelector(candidates,obligations)
            incumbent,best,seen=None,-1,set()
            for q in sorted((q for q in cq if q['seed']==seed and q['method']=='S3'),key=lambda q:q['step']):
                step=q['step'];decision=selector.select(run.query_options(d,seed+step*1009,incumbent,obligations))
                saved=x.read(out/'search'/q['query_id']/'selection.json')
                assert decision['chosen']==saved['chosen'] and decision['ranking']==saved['ranking'],q['query_id']
                normalize=lambda hs:[dict(h,gap_keys=sorted(h['gap_keys'])) for h in hs]
                assert normalize(decision['history'])==normalize(saved['history']),q['query_id']
                assert q['first_gap_keys']==[list(g) for g in sorted(old.gaps([q])-seen)]
                seen.update(old.gaps([q]))
                rows=decision['chosen']['rows']
                actual=x.read(run.ROOT/q['runs'][0]['run']/'input.json')
                assert rows==actual
                score=len(old.gaps([q]))+len({w['obligation'] for w in q['repair_witnesses']})
                if score>best:incumbent,best=rows,score
                selector.observe(decision['chosen']['id'], 'confirmed' if q['spec_status']=='scoped' and q['status'] in ('ok','partial_candidate_unknown') else 'unknown',
                    q['obligation_coverage'],[list(g) for g in old.gaps([q])],1)
                selector_checks+=1
        print('AUDITED192',case,flush=True)
    result=dict(passed=True,queries=len(qs),cells=len(cells),physical_runs=raw_runs,
                independent_candidate_evidence_replays=oracle_checks,active_selection_replays=selector_checks,
                new_simulator_calls=0,model_calls=0,wall_seconds=time.perf_counter()-start,
                scope='Read-only independent reference and evidence recomputation from physical simulator stdout, candidate/RTL/input hashes and exact selector history replay. Not new acceptance.')
    x.dump(out/'audit.json',result)
    print(json.dumps(result),flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();audit(a.out.resolve())
