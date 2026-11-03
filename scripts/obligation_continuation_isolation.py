"""Audit actual model messages and nontrivial holdout duplication, post-freeze only."""
import json
import obligation_continuation as cont
from obligation_continuation import x, public, PRIOR


def projected_signature(k,rows,d):
    # Preserve all deadline-bearing sample positions and reset boundaries.
    # Ignore FIFO data renaming; canonicalize stat ordinary payload equality.
    data_map={};out=[]
    for r in rows:
        if not r[d['rst']]:
            out.append((0,));data_map={};continue
        if k=='fifo':out.append((r[d['rst']],r['push_i'],r['pop_i']))
        elif k=='stat':
            token=None
            if r['frame_done_i']:
                v=r['frame_len_i'];token=v if v in (0,255,187) else ('value',data_map.setdefault(v,len(data_map)))
            out.append((r[d['rst']],r['frame_done_i'],token))
        else:out.append(tuple(r[n] for n in sorted([d['rst'],*d['inputs']])))
    return json.dumps(out)


def main():
    x.OUT=x.ROOT/'deliverables'/cont.NAME;output=[];duplicates=[]
    for b,keys in [('formal',('filter','fifo','stat')),('historical_formal',('ibex',))]:
        block=x.OUT/b;queries=[json.loads(s) for s in (block/'queries.jsonl').read_text().splitlines()]
        for f in sorted((block/'models').glob('*/*/*/request.json')):
            k,arm,rnd=f.parts[-4:-1];rnd=int(rnd)
            request=x.read(f);assert len(request['messages'])==1
            prompt=json.loads(request['messages'][0]['content'])
            assert prompt['contract']==x.read(x.OUT/'frozen'/k/'public_contract.json')
            cp=x.read(block/'development'/k/arm/f'checkpoint_{rnd}.json')
            assert prompt['current']==[{n:c[n] for n in ('antecedent','consequent','delay')} for c in cp['before']]
            commonphase='initial' if rnd==0 else f'round{rnd-1}_regression'
            common=[q for q in queries if (q['case'],q['arm'],q['phase'])==(k,arm,commonphase)]
            expected=[public.feedback(q) for q in common]
            assert all(q['status']=='ok' for q in common),'audit needs explicit prior compiler feedback reconstruction'
            acquired=[q for q in queries if (q['case'],q['arm'],q['phase'])==(k,arm,f'round{rnd}_acquire')]
            expected += [public.feedback(q,'legacy' if arm=='A' else 'miss' if arm=='C' else 'both') for q in acquired]
            assert prompt['feedback']==expected,(k,arm,rnd,'unexpected feedback')
            assert set(prompt)=={'task','contract','ports','expression_rules','current','feedback'}
            output.append(dict(request=x.rel(f),own_group_feedback_exact=True,public_contract_exact=True,private_files_transmitted=False))
        if b=='formal':
            for k in keys:
                d=x.read(x.OUT/'frozen'/k/'definition.json')
                dev=[x.read(x.ROOT/q['runs'][0]['run']/'input.json') for q in queries if q['case']==k and q['runs']]
                dev+=x.read(PRIOR/'refinement_r04/quarantine'/f'{k}.json')
                sig={projected_signature(k,r,d) for r in dev}
                for i,rows in enumerate(x.read(block/'quarantine'/k/'inputs.json')):
                    overlap=projected_signature(k,rows,d) in sig
                    duplicates.append(dict(case=k,scenario=i,overlap_after_irrelevant_payload_renaming=overlap))
                    assert not overlap
    initial_requests=list((x.OUT/'historical_generation/models/ibex/shared_initial').glob('*/request.json'))+list((x.OUT/'historical_generation_v2/models/ibex/shared_initial').glob('*/request.json'))
    for p in initial_requests:
        gen=x.read(p);gp=json.loads(gen['messages'][0]['content']);assert not gp['feedback'] and not gp['current']
        assert gp['contract']==x.read(x.OUT/'frozen/ibex/public_contract.json')
    x.dump(x.OUT/'isolation_audit.json',dict(formal_messages=len(output),records=output,shared_initial_generation_public_only=True,
        initial_generation_requests=len(initial_requests),duplicate_checks=duplicates,scope='full timed reset/transaction signatures; FIFO payload renaming ignored and stat data equality normalized; not exhaustive equivalence proof',
        ibex_encoding_isolation=x.read(x.OUT/'historical_formal/acceptance/isolation.json')))
    print('ISOLATION',len(output),'formal requests exactly match their own acquired feedback',flush=True)


if __name__=='__main__':main()
