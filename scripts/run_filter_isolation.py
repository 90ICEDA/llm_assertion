"""Separate execution-only ablation: identical frozen candidates and query inputs.

Isolate candidate compilation so one unsupported expression cannot hide another
candidate's evidence. All attempts remain charged; no candidate text is repaired.
"""
import argparse
import collections
import json
import time
import run_obligation_evidence as x

def run():
    x.guard();folder=x.OUT/'filter_isolation';folder.mkdir(exist_ok=False)
    queries=[json.loads(s) for s in (x.OUT/'search/queries.jsonl').read_text().splitlines()]
    queries=[q for q in queries if q['case']=='filter']
    assert len(queries)==108
    d=x.read(x.OUT/'frozen/filter/definition.json');pool=x.read(x.OUT/'frozen/filter/candidates.json')['candidates']
    protocol=dict(candidates_sha256=x.sha(x.OUT/'frozen/filter/candidates.json'),queries=len(queries),
        change='candidate compilation isolation only; original inputs reused byte-for-byte, methods not rerun/adapted; three candidates remain frozen',
        comparison='execution ablation; separate from original equal-budget search result. Same input schedule and candidate set per query; six compile attempts instead of two',
        primary_budget='one complete frozen-pool x dual-RTL schedule submission; failures included',
        unsupported='two invalid candidates stay unknown; no hand repairs or drops',
        policy_equivalence='original disagreement got score zero on every failed batch; one executable candidate has zero pairwise disagreement as well; no learned scheduling change',
        source_sha256=x.sha(__file__),frozen_before_execution=True)
    x.dump(folder/'protocol.json',protocol)
    x.engine.OUT=x.OUT;x.engine.tb_text=x.checker.tb_text
    x.engine.sources=lambda dd:(x.OUT/'frozen/filter/correct.v',x.OUT/'frozen/filter/buggy.v')
    for q in queries:
        start=time.perf_counter();inp=x.read(x.ROOT/q['runs'][0]['run']/'input.json')
        result=dict(query_id=q['query_id'],original_query=q['query_id'],method=q['method'],seed=q['seed'],step=q['step'],
            attempted_queries=1,compile_attempts=0,simulation_attempts=0,input_sha256=x.digest(inp),candidates=[],evidence=[])
        assert result['input_sha256']==q['input_content_sha256']
        for j,c in enumerate(pool):
            for variant in ['correct','buggy']:
                r=x.engine.execute_run(d,inp,[c],f'filter_isolation/{q["query_id"]}/candidate{j}',variant)
                result['compile_attempts']+=1;result['simulation_attempts']+=int(r['simulate'] is not None)
                run=x.ROOT/r['run_id']
                a=x.adjudicate_folder(run,d) if r['status']=='ok' else dict(status=r['status'])
                x.dump(run/'adjudication.json',a)
                result['candidates'].append(dict(candidate_id=c['id'],candidate_sha256=x.digest(c),variant=variant,status=a['status'],run=r['run_id']))
                for evs in a.get('evidence',[]):
                    result['evidence'] += [dict(**e,candidate_id=c['id'],run=r['run_id']) for e in evs if e['kind'] in ['miss','false_positive']]
        result['wall_seconds']=time.perf_counter()-start;x.append(folder/'queries.jsonl',result)
    summaries=[]
    rows=[json.loads(s) for s in (folder/'queries.jsonl').read_text().splitlines()]
    for m in ['ordinary','disagreement','obligation']:
        rr=[r for r in rows if r['method']==m];ev=[e for r in rr for e in r['evidence']]
        summaries.append(dict(method=m,queries=len(rr),compiles=sum(r['compile_attempts'] for r in rr),simulations=sum(r['simulation_attempts'] for r in rr),
            statuses=dict(collections.Counter(c['status'] for r in rr for c in r['candidates'])),
            defects=sorted(set((e['candidate_id'],e['kind']) for e in ev)),raw_evidence=len(ev),seconds=sum(r['wall_seconds'] for r in rr),
            parent_pass=False,reason='two unsupported candidates remain unknown; one valid candidate has observed defects'))
    x.dump(folder/'summary.json',summaries);print(json.dumps(summaries))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);a=p.parse_args();x.OUT=x.ROOT/'deliverables'/a.run;run()
