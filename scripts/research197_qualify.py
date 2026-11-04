"""Development-only real RTL qualification, no model or acceptance access."""
import argparse
from pathlib import Path
import research197_cases as cases
from research194_active_search import combine_candidates,project_measurement
from research194_refinement_runner import dump,bind_measurement,file_hash

def run(out):
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False);summary=[]
    for cid in cases.IDS:
        config=cases.get_case(cid);candidates=config['candidate_pool'];combined,mapping=combine_candidates(candidates)
        queries=cases.query_pool(cid)[:2]
        m=cases.evaluate(cid,combined,out/cid/'native',queries=queries,_trusted_bundle=True)
        rows=[]
        for i,candidate in enumerate(candidates):
            projected=bind_measurement(project_measurement(m,candidate,mapping,i),candidate)
            dump(out/cid/f'candidate{i}.json',projected)
            rows.append(dict(control='initial' if i==0 else 'handwritten_qualification_only',native_complete=projected['native_complete'],
                reference_complete=projected['reference_complete'],targets=len(projected['targets']),detected=len(projected['detected_ids']),
                false_positives=len(projected['false_positives']),unknown=projected['critical_unknown']))
        row=dict(case_id=cid,controls=rows,max_simultaneously_pending=max(j['reference'].get('max_simultaneously_pending',0) for j in m['executions']),
                 cost=m['cost'],correct_reference_legal=all(not j['reference']['unknown'] and all(c['passed'] for c in j['reference']['checks']) for j in m['executions'] if j['variant']=='correct'))
        summary.append(row);dump(out/'summary.json',summary);print(row,flush=True)
    dump(out/'outcome.json',dict(status='qualified' if all(r['correct_reference_legal'] and all(c['native_complete'] and c['reference_complete'] and c['targets'] for c in r['controls']) for r in summary) else 'qualification_failed',
        model_calls=0,independent_access=False,source_sha256=file_hash(cases.__file__),
        interpretation='Handwritten controls qualify executor/oracle and reachable RTL defects, not learned repair success.'))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True,type=Path);run(p.parse_args().out)
