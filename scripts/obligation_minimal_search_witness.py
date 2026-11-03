"""Delta-reduce new frozen-search evidence; bill every trial, including invalids."""
import argparse
import copy
import json
import obligation_isolated_search as iso
from obligation_isolated_search import x


def main(run):
    x.OUT=x.ROOT/'deliverables'/run;iso.configure()
    folder=x.OUT/'minimal_search';folder.mkdir(exist_ok=False)
    qs=[json.loads(s) for s in (x.OUT/'search/queries.jsonl').read_text().splitlines()]
    picks=[]
    for k,kind,component in [('filter','miss','qualified_value'),('stat','miss','captured_length'),('fifo','false_positive',None)]:
        events=[e for q in qs if q['case']==k for e in q['evidence'] if e['kind']==kind and
                (component is None or any(c['obligation']==component and not c['passed'] for c in e['obligations']))]
        if events:picks.append((k,kind,component,min(events,key=lambda e:e['cycle'])))
    output=[]
    for k,kind,component,original in picks:
        source=x.ROOT/original['run'];d=x.read(source/'definition.json')
        c=next(z for z in x.read(source/'candidates.json') if z['id']==original['candidate_id'])
        rows=x.read(source/'input.json')[:original['cycle']+1];name=k+'_'+kind;trials=[]
        def attempt(trial):
            trial=copy.deepcopy(trial)
            for i,r in enumerate(trial):r['cycle']=i;r['stimulus_id']=f'minimal:{i}'
            ident=name+'/'+str(len(trials));x.dump(folder/'inputs'/(ident+'.json'),trial)
            x.append(folder/'attempts.jsonl',dict(id=ident,status='submitted',input_sha256=x.digest(trial)))
            q=iso.evaluate(d,trial,[c],'minimal_search/'+ident)
            found=[e for e in q['evidence'] if e['variant']==original['variant'] and e['kind']==kind and
                   (component is None or any(z['obligation']==component and not z['passed'] for z in e['obligations']))]
            q.update(id=ident,preserves_target=bool(found),sample_count=len(trial))
            x.append(folder/'queries.jsonl',q);trials.append(q)
            return bool(found),found[0] if found else None
        ok,witness=attempt(rows);assert ok
        changed=True
        while changed:
            changed=False
            for i in range(2,len(rows)):
                trial=rows[:i]+rows[i+1:];ok,new_witness=attempt(trial)
                if ok:rows=trial;witness=new_witness;changed=True;break
        output.append(dict(case=k,kind=kind,component=component,original_witness=original,minimal_witness=witness,
            sampled_cycles=len(rows),actual_queries=len(trials),invalid_queries=sum(q['status']=='invalid_input' for q in trials),
            compiles=sum(q['compile_attempts'] for q in trials),simulations=sum(q['simulation_attempts'] for q in trials),
            wall_seconds=sum(q['wall_seconds'] for q in trials),
            minimality='single-sample deletion minimal with original initial two reset samples retained; input values not minimized; exact obligation and candidate preserved'))
    x.dump(folder/'index.json',output)
    print(json.dumps([dict(case=r['case'],kind=r['kind'],cycles=r['sampled_cycles'],queries=r['actual_queries']) for r in output]))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);main(p.parse_args().run)
