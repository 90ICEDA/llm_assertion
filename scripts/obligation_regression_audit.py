"""Post-freeze replay of all acquired development inputs at each revision.

Results never enter a model request. Existing before executions are reused with
explicit cache accounting; every after replay is a real new query, even if an
input was duplicated. This is validation cost, not extra search-arm information.
"""
import argparse
import json
import obligation_refinement_block as ref
import obligation_isolated_search as iso
from obligation_isolated_search import x


def identity(events):
    return {(e['variant'],e['cycle'],e['kind'],tuple(c['obligation'] for c in e['obligations'])) for e in events}


def main(run):
    x.OUT=x.ROOT/'deliverables'/run;iso.configure();block=x.OUT/'refinement_r04'
    assert all(x.sha(x.ROOT/p)==h for p,h in x.read(block/'final_freeze.json').items())
    out=block/'regression_audit';out.mkdir(exist_ok=False)
    original=[json.loads(s) for s in (block/'queries.jsonl').read_text().splitlines()]
    results=[]
    for k in ref.KEYS:
        d=x.read(x.OUT/'frozen'/k/'definition.json')
        for arm in ref.ARMS:
            previous={}
            for round_no in range(2):
                checkpoint=x.read(block/'development'/k/arm/f'checkpoint_{round_no}.json')
                cs=checkpoint['after']
                acquired=[q for q in original if q['case']==k and q['arm']==arm and
                          q['phase'] in [f'round{j}_acquire' for j in range(round_no+1)]]
                for i,q in enumerate(acquired):
                    source=x.ROOT/q['runs'][0]['run'];rows=x.read(source/'input.json')
                    before=previous[q['id']] if q['id'] in previous else ref.combined(q)
                    label=f'regression_audit/{k}/{arm}/round{round_no}/{i}'
                    x.append(out/'attempts.jsonl',dict(id=label,input_sha256=x.digest(rows)))
                    after_query=iso.evaluate(d,rows,cs,label)
                    x.append(out/'queries.jsonl',dict(id=label,**after_query))
                    after=ref.combined(after_query);a,b=identity(before['events']),identity(after['events'])
                    results.append(dict(case=k,arm=arm,round=round_no,source_query=q['id'],new_query=label,
                        new_false_positive_witnesses=sorted(e for e in b-a if e[2]=='false_positive'),
                        new_miss_witnesses=sorted(e for e in b-a if e[2]=='miss'),
                        removed_witnesses=sorted(a-b),before_cache_hits=1,
                        status=after['execution'],claim='new concrete defects only; rejection before change did not prove causal protection'))
                    previous[q['id']]=after
    x.dump(out/'results.json',results)
    summary=[]
    for k in ref.KEYS:
        for arm in ref.ARMS:
            for n in range(2):
                rs=[r for r in results if (r['case'],r['arm'],r['round'])==(k,arm,n)]
                summary.append(dict(case=k,arm=arm,round=n,after_actual_queries=len(rs),before_explicit_cache_hits=len(rs),
                    new_fp=sum(len(r['new_false_positive_witnesses']) for r in rs),new_miss=sum(len(r['new_miss_witnesses']) for r in rs),
                    unknown_queries=sum(r['status']!='ok' for r in rs)))
    x.dump(out/'summary.json',summary)
    print(json.dumps(dict(new_queries=len(results),before_reuse_hits=len(results),checkpoints_with_new_fp=sum(r['new_fp']>0 for r in summary),checkpoints_with_new_miss=sum(r['new_miss']>0 for r in summary))))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);main(p.parse_args().run)
