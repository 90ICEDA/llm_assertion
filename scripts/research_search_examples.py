"""Extract two actual, independently adjudicated search witnesses (no SVA edits)."""
import argparse
import json
from pathlib import Path

import research_search_compare as e


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--run',default='research_search_20261014_r01');a=ap.parse_args()
    if Path(a.run).name!=a.run or a.run in ('.','..'):ap.error('run must be a directory name')
    e.OUT=e.x.ROOT/'deliverables'/a.run;e.setup();e.guard()
    examples=[];lines=['# Actual search witnesses','','These are development search results. Candidates were frozen; no model revision, native SVA execution, historical nonregression, or independent final test is claimed here.','']
    for case,cid,ob in [('spill','slot_07','collision_empty'),('stat','slot_05','valid_latency')]:
        qs=[json.loads(s) for s in (e.OUT/'search'/case/'queries.jsonl').read_text().splitlines()]
        match=next((q,w) for q in qs if q['method']=='contract' for w in q['pair_witnesses'] if w['candidate_id']==cid and w['kind']=='miss' and ob in w['obligations'])
        q,w=match;p=e.x.ROOT/w['run'];cs=e.x.read(p/'candidates.json');index=next(i for i,c in enumerate(cs) if c['id']==cid)
        sva=(p/'assertions.sva').read_text().splitlines()[index]
        buggy=e.x.read(p/'trace.json');fixed=e.x.read(p.parent/'correct'/'trace.json')
        assertion=e.x.read(p/f'checker_{index}_cycles.json');verdict=e.x.read(p/'independent_reference.json')
        t=w['cycle'];reset=max(i for i in range(t+1) if not buggy[i][e.x.read(p/'definition.json')['rst']])
        data=dict(case=case,candidate_id=cid,obligation=ob,query_id=q['query_id'],run=w['run'],cycle=t,original_sva=sva,candidate_sha256=e.x.digest(cs[index]),buggy_trace=buggy[reset:t+1],fixed_trace=fixed[reset:t+1],checker_events=[z for z in assertion if reset<=z['cycle']<=t],independent_reference=[z for z in verdict['events'] if reset<=z['cycle']<=t],repair_witnesses=[z for z in q['repair_witnesses'] if z['cycle']==t],spec_status=q['spec_status'],modified_sva=None,reason='Search-only arm; no model call or candidate edit was performed')
        assert data['repair_witnesses'] and data['independent_reference'][-1]['first_violation']
        assert not any(z['fail'] for z in data['checker_events'])
        examples.append(data)
        lines += [f'## {case}: {cid}, {ob}', '',f"Actual query `{q['query_id']}`, cycle {t}. The candidate accepts the reset-to-first-violation prefix; the independent monitor identifies a buggy violation and a fixed-safe obligation witness.",'','```systemverilog',sva,'```','', '| Cycle | Buggy sample | Fixed sample |', '|---|---|---|']
        for b,f in zip(data['buggy_trace'],data['fixed_trace']):
            lines.append(f"| {b['cycle']} | `{json.dumps({k:v for k,v in b.items() if k!='cycle'},sort_keys=True)}` | `{json.dumps({k:v for k,v in f.items() if k!='cycle'},sort_keys=True)}` |")
        lines += ['', f"Raw run: `{w['run']}`. Full assertion checks and independent reference events are in `evidence_examples.json`.",'']
    e.x.dump(e.OUT/'evidence_examples.json',examples)
    (e.OUT/'EVIDENCE_EXAMPLES.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps([dict(case=z['case'],query=z['query_id'],cycle=z['cycle']) for z in examples]))


if __name__=='__main__':main()
