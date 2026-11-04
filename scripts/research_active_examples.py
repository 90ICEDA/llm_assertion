"""Outcome-faithful mechanism analysis; reads completed frozen experiments only."""
import argparse
import collections
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def dump(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def legacy(out):
    qs=[json.loads(s) for p in sorted((out/'search').glob('*/queries.jsonl')) for s in p.read_text().splitlines()]
    gap=lambda rs:{tuple(g) for r in rs for e in r['evidence'] for g in e['gap_keys']}
    parents=[];examples=[]
    for case in sorted({q['case'] for q in qs}):
        result={m:gap([q for q in qs if q['case']==case and q['method']==m]) for m in ('S0','S1','S2','S3')}
        parents.append(dict(case=case,parent_bug=next(q['parent_bug'] for q in qs if q['case']==case),
            gaps={m:len(v) for m,v in result.items()},S3_exclusive=sorted(result['S3']-set().union(*(v for m,v in result.items() if m!='S3'))),
            baseline_only=sorted(set().union(*(v for m,v in result.items() if m!='S3'))-result['S3']),
            unknown_queries={m:sum(q['spec_status']!='scoped' for q in qs if q['case']==case and q['method']==m) for m in result}))
        active=[q for q in qs if q['case']==case and q['method']=='S3']
        chosen=next((q for q in active if q['first_gap_keys']),None)
        if chosen:
            evidence=chosen['evidence'][0]
            candidates=read(out/'frozen'/case/'candidates.json')['candidates']
            candidate=next(c for c in candidates if c['id']==evidence['candidate_id'])
            trace=read(ROOT/evidence['run']/'trace.json')
            t=evidence['cycle'];selection=read(out/'search'/chosen['query_id']/'selection.json')
            examples.append(dict(case=case,query_id=chosen['query_id'],label='confirmed_acquisition_not_assertion_improvement',
                original_candidate=candidate,independent_evidence=evidence,
                key_waveform=[r for r in trace if t-3<=r['cycle']<=t+2],
                candidate_localization_hypothesis=selection['chosen']['dimensions'],ranking=selection['ranking'],
                modified_sva=None,acceptance='not_evaluated_search_only',
                original_trace=str((ROOT/evidence['run']/'trace.json').relative_to(ROOT))))
    dump(out/'parent_mechanism_analysis.json',parents);dump(out/'representative_evidence.json',examples)
    return parents


def native(out):
    rr=read(out/'records.json');examples=[];diagnosis=[];first_costs=[];paired_costs=[]
    first={}
    for r in sorted(rr,key=lambda r:(r['seed'],r['method'],r['query'])):
        for key in r['first_new_keys']:
            identity=(r['seed'],r['method'],key)
            first[identity]=r['query']+1
            prior=[p for p in rr if p['seed']==r['seed'] and p['method']==r['method'] and p['query']<=r['query']]
            first_costs.append(dict(seed=r['seed'],method=r['method'],key=key,first_query=r['query']+1,
                actual_native_executions=sum(p['native_executions'] for p in prior),
                query_wall_seconds=sum(p['query_wall_seconds'] for p in prior)))
    for seed in sorted({r['seed'] for r in rr}):
        for method in ('S0','S1','S2'):
            keys={k for s,m,k in first if s==seed and m=='S3'}&{k for s,m,k in first if s==seed and m==method}
            paired_costs.append(dict(seed=seed,comparator=method,common_gaps=len(keys),
                S3_earlier=sum(first[seed,'S3',k]<first[seed,method,k] for k in keys),
                tied=sum(first[seed,'S3',k]==first[seed,method,k] for k in keys),
                S3_later=sum(first[seed,'S3',k]>first[seed,method,k] for k in keys)))
    for seed in sorted({r['seed'] for r in rr}):
        active=[r for r in rr if r['seed']==seed and r['method']=='S3'];seen=set()
        for r in active:
            action=(r['family'],r['duration']);repeat=action in seen;seen.add(action)
            if repeat and not r['first_new_keys']:
                diagnosis.append(dict(seed=seed,query=r['query'],action=action,status='repeated_action_zero_marginal_gap',
                    cost_native_executions=r['native_executions'],
                    reason='Static structural/obligation score outweighed the soft novelty penalty; no overall advantage inferred. Policy remains frozen.',
                    path=str((out/'queries'/f's{seed}'/'S3'/f"q{r['query']}"/'selection.json').relative_to(ROOT))))
        for r in active:
            if r['first_new_keys']:
                g=next(g for g in r['gaps'] if g['key'] in r['first_new_keys'])
                examples.append(dict(seed=seed,query=r['query'],family=r['family'],duration=r['duration'],
                    gap=g,original_candidate=str((out/'candidates/bounded.json').relative_to(ROOT)),
                    comparator=str((out/'candidates/valid.json').relative_to(ROOT)),
                    waveform_path=g.get('replay_source'),modified_sva=None,
                    acceptance='confirmed_development_gap_only_no_refinement_or_unseen_fault_acceptance'))
                break
    dump(out/'failure_mechanism_analysis.json',diagnosis);dump(out/'representative_evidence.json',examples)
    dump(out/'first_discovery_cost.json',first_costs);dump(out/'paired_first_discovery.json',paired_costs)
    return diagnosis


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('kind',choices=('legacy','native'));ap.add_argument('--out',type=Path,required=True)
    a=ap.parse_args();out=a.out.resolve();assert read(out/'outcome.json')['status']=='completed'
    print(json.dumps(globals()[a.kind](out),ensure_ascii=False))
