"""Post-freeze replay of all acquired inputs, never sent back to the model."""
import argparse
import json
import obligation_continuation_experiment as exp
from obligation_continuation import x, ref, iso, NAME


def identity(m):
    out=set()
    for kind in ('fp','first_misses','later_misses'):
        for e in m[kind]:
            if kind=='fp':out.add((kind,e,''))
            else:
                for c in e['transaction_obligations']:
                    out.add((kind,e['cycle'],c['obligation']))
    return out


def main(historical):
    x.OUT=x.ROOT/'deliverables'/NAME
    if historical:
        import obligation_ibex_experiment as ibex
        ibex.install()
    exp.setup();block=ref.BLOCK
    assert all(x.sha(x.ROOT/p)==h for p,h in x.read(block/'final_freeze.json').items())
    out=block/'postfreeze_regression';out.mkdir(exist_ok=False)
    queries=[json.loads(s) for s in (block/'queries.jsonl').read_text().splitlines()]
    records=[]
    for k in exp.KEYS:
        d=x.read(x.OUT/'frozen'/k/'definition.json')
        for arm in exp.ARMS:
            previous={}
            for rnd in range(2):
                cp=x.read(block/'development'/k/arm/f'checkpoint_{rnd}.json')
                acquired=[q for q in queries if q['case']==k and q['arm']==arm and q['phase'] in [f'round{r}_acquire' for r in range(rnd+1)]]
                for i,q in enumerate(acquired):
                    rows=x.read(x.ROOT/q['runs'][0]['run']/'input.json')
                    before=previous.get(q['id'])
                    if before is None:before=exp.paired_metrics(d,q,cp['before'])
                    label=f'{exp.BLOCK_NAME}/postfreeze_regression/{k}/{arm}/{rnd}/{i}'
                    after_q=iso.evaluate(d,rows,cp['after'],label)
                    x.append(out/'queries.jsonl',dict(case=k,arm=arm,round=rnd,**after_q))
                    after=exp.paired_metrics(d,after_q,cp['after'])
                    a,b=identity(before),identity(after)
                    records.append(dict(case=k,arm=arm,round=rnd,source_query=q['id'],new_query=label,
                        before_cache_hits=1,new_witnesses=sorted(b-a),removed_witnesses=sorted(a-b),
                        status=after['status'],before=before,after=after))
                    previous[q['id']]=after
    x.dump(out/'results.json',records)
    summary=[]
    for k in exp.KEYS:
        for arm in exp.ARMS:
            for rnd in range(2):
                rs=[r for r in records if (r['case'],r['arm'],r['round'])==(k,arm,rnd)]
                summary.append(dict(case=k,arm=arm,round=rnd,queries=len(rs),cache_hits=len(rs),
                    new_fp=sum(e[0]=='fp' for r in rs for e in r['new_witnesses']),
                    new_misses=sum(e[0]!='fp' for r in rs for e in r['new_witnesses']),
                    removed_fp=sum(e[0]=='fp' for r in rs for e in r['removed_witnesses']),
                    removed_misses=sum(e[0]!='fp' for r in rs for e in r['removed_witnesses']),
                    unknown=sum(r['status']!='ok' for r in rs)))
    x.dump(out/'summary.json',summary)
    print('REGRESSION',len(records),'actual queries; same number explicitly cached before results',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--historical',action='store_true');a=p.parse_args();main(a.historical)
