"""Recount reachability, transaction identities, budgets, and holdout overlap."""
import argparse
import collections
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import run_obligation_evidence as x


def canonical(d,rows):
    # Exclude all filenames/cycle labels/stimulus IDs. Do not stutter-compress
    # filter samples, stat pulses, deadlines or resets: those change semantics.
    names=sorted([d['rst'],*d['inputs']])
    physical=[[r[n] for n in names] for r in rows]
    return x.digest([names,physical])


def audit(run):
    out=x.ROOT/'deliverables'/run;dest=out/'trace_audit';dest.mkdir(exist_ok=False)
    qs=[json.loads(s) for s in (out/'search/queries.jsonl').read_text().splitlines()]
    def inspect(pair):
        q,rr=pair;folder=x.ROOT/rr['run'];raw=x.read(folder/'result.json')
        d=x.read(folder/'definition.json');rows=x.read(folder/'input.json')
        a=x.read(folder/'adjudication.json');oracle=x.read(folder/'independent_reference.json') if a['status']=='ok' else None
        return dict(case=q['case'],method=q['method'],seed=q['seed'],run=rr['run'],variant=rr['variant'],
            canonical_input_sha256=canonical(d,rows),candidate_triggers={c['id']:c['trigger_count'] for c in raw.get('candidates',[])},
            reference_branches=dict(collections.Counter(c['obligation']+':'+str(c['branch']) for e in (oracle or {}).get('events',[]) for c in e['checks'])),
            first_target_violations=sum(e['first_violation'] for e in (oracle or {}).get('events',[])),
            cancelled_transactions=len((oracle or {}).get('cancelled',[])),pending_at_end=len((oracle or {}).get('pending',[])))
    with ThreadPoolExecutor(max_workers=16) as pool:
        records=list(pool.map(inspect,[(q,r) for q in qs for r in q['runs']]))
    x.dump(dest/'reachability_runs.json',records)
    summaries=[]
    for k in x.IDS:
        for method in ('ordinary','disagreement','obligation'):
            rs=[r for r in records if r['case']==k and r['method']==method]
            triggers=collections.Counter();branches=collections.Counter()
            for r in rs:triggers.update(r['candidate_triggers']);branches.update(r['reference_branches'])
            summaries.append(dict(case=k,method=method,antecedent_hits=dict(triggers),reference_branches=dict(branches),
                first_target_violations=sum(r['first_target_violations'] for r in rs),cancelled_transactions=sum(r['cancelled_transactions'] for r in rs),
                runs_pending_at_end=sum(r['pending_at_end']>0 for r in rs),scope='simulation reachability only; unsupported candidates omitted from hit map, retained unknown in query records'))
    x.dump(dest/'nonvacuity_summary.json',summaries)
    block=out/'refinement_r04'
    development=[json.loads(s) for s in (block/'queries.jsonl').read_text().splitlines() if s.strip()]
    development=[q for q in development if not q['phase'].startswith('heldout')]
    dev={k:set(r['canonical_input_sha256'] for r in records if r['case']==k) for k in x.IDS}
    for q in development:
        if q['runs']:
            f=x.ROOT/q['runs'][0]['run'];d=x.read(f/'definition.json');dev[q['case']].add(canonical(d,x.read(f/'input.json')))
    overlap=[]
    for k in ('filter','fifo','stat'):
        d=x.read(out/'frozen'/k/'definition.json')
        for i,rows in enumerate(x.read(block/'quarantine'/f'{k}.json')):
            overlap.append(dict(case=k,scenario=i,canonical_input_sha256=canonical(d,rows),duplicate=canonical(d,rows) in dev[k]))
    x.dump(dest/'holdout_input_overlap.json',dict(records=overlap,no_exact_electrical_schedule_overlap=not any(r['duplicate'] for r in overlap),
        canonicalization='declared inputs and reset only; ignores cycle/stimulus labels; preserves all deadline-bearing samples',
        equivalence_limit='No exhaustive proof of semantic inequivalence under every candidate. Conclusions restricted to these new sampled transaction schedules, not independent bug counts.'))
    vectors=x.read(out/'historical_screening/ibex_54/boundary_vectors.json')
    x.dump(dest/'historical_boundary_dedup.json',dict(raw_vectors=len(vectors),unique_instructions=len({v['instruction'] for v in vectors}),
        duplicate_reason='The original issue 0x7065 is retained explicitly and also appears in exhaustive nonzero C.LUI-x0 boundary enumeration.'))
    expected_budget={}
    for k in ('filter','fifo','stat'):
        for arm in ('A','B','C','D'):
            count=sum(q['case']==k and q['arm']==arm for q in development)
            expected_budget[k+'/'+arm]=dict(actual_queries=count,expected=14,matched=count==14)
    x.dump(dest/'refinement_budget.json',expected_budget)
    assert all(v['matched'] for v in expected_budget.values())
    assert not any(r['duplicate'] for r in overlap)
    print(json.dumps(dict(search_runs=len(records),holdout_schedules=len(overlap),exact_duplicates=0,refinement_budgets_verified=True)))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);audit(p.parse_args().run)
