"""Posthoc read-only replay of sealed inputs, cost receipts and native evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import random
import re

import research194_cases as cases
import research194_active_search as prior
import research194_active_semantics as semantics
from research194_active_analysis import context_gaps
import research195_active_queries as queries

ROOT=Path(__file__).resolve().parents[1]


def read(path):return json.loads(Path(path).read_text())
def local(path):
    s=str(path).replace('\\','/');m=re.match(r'^(?:[A-Za-z]:|/mnt/[a-z])/'+re.escape(ROOT.name)+r'/(.*)$',s)
    return ROOT/m[1] if m else Path(path)


def audit(out):
    out=Path(out).resolve();checks=[]
    def check(ok,reason):checks.append(dict(passed=bool(ok),check=reason))
    if not (out/'outcome.json').exists():raise ValueError('completed_main_required_for_final_audit')
    protocol=read(out/'protocol.json');seal=read(out/'seal.json')
    check(read(out/'outcome.json')['status']=='completed','main completion marker')
    check(hashlib.sha256((out/'protocol.json').read_bytes()).hexdigest()==seal['protocol_sha256'],'frozen protocol hash')
    for path,value in seal['source_sha256'].items():
        check(hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==value,'current source '+path)
        check(hashlib.sha256((out/'source_snapshot'/path).read_bytes()).hexdigest()==value,'source snapshot '+path)
    for case in protocol['cases']:
        for seed in protocol['seeds']:
            pool=queries.query_pool(case,seed)
            check(cases.digest(pool)==protocol['query_pool_hashes'][f'{case}/{seed}'],'seeded pool reproduction '+case+'/'+str(seed))
    records=[];native_folders=[]
    for top in ('calibration','baseline','sessions'):
        for path in sorted((out/top).glob('**/acquisition.json')):
            r=read(path);records.append((top,r));folder=path.parent;binding=read(folder/'candidate_binding.json');raw=read(folder/'native/measurement.json')
            candidate=protocol['initial_candidates'][r['case_id']]
            check(r['candidate_sha256']==cases.digest(candidate),'initial candidate '+str(path))
            projected=prior.project_measurement(raw,candidate,binding['mapping'])
            for field in ('targets','detected_ids','false_positives','critical_unknown','evidence'):
                check(projected[field]==r['measurement'][field],'projected candidate isolation '+field+' '+str(path))
            check(context_gaps(projected)==r['gap_contexts'],'confirmed context accounting '+str(path))
            actual_cycles=0;seconds=0
            for job in raw['executions']:
                native_folder=local(job['folder']);native_folders.append(str(native_folder.resolve()));log=(native_folder/'execute.log').read_text()
                trace=[{k:int(v) for k,v in re.findall(r'(\w+)=(-?\d+)',line)} for line in log.splitlines() if line.startswith('TRACE ')]
                check(trace==job['trace'],'native trace reparse '+str(native_folder))
                check(len(trace)==len(r['query']['rows']),'submitted input length '+str(native_folder))
                check(all(all(t.get(k)==v for k,v in row.items()) for t,row in zip(trace,r['query']['rows'])),'submitted input values '+str(native_folder))
                check(cases.reference(r['case_id'],trace)==job['reference'],'independent monitor replay '+str(native_folder))
                check(hashlib.sha256((native_folder/'tb.sv').read_text().encode()).hexdigest()==job['result']['source_sha256'],'native testbench source '+str(native_folder))
                for marker,field in [('ASSERT_FAIL','failures'),('TRIGGER','triggers')]:
                    parsed=[dict(id=a,detail=b.strip()) for a,b in re.findall(r'^'+marker+r'\s+(\S+)(.*)$',log,re.M)]
                    check(parsed==job['result'][field],'native '+marker+' '+str(native_folder))
                validation=semantics.verify_native_predictions(prior.semantic_candidate(binding['combined'],cases.get_case(r['case_id'])),trace,job['result'])
                check(validation['status']=='confirmed_semantics','temporal semantics native agreement '+str(native_folder))
                actual_cycles+=len(trace)
                seconds+=sum(read(native_folder/f'{name}.json')['wall_seconds'] for name in ('compile','execute'))
            check(actual_cycles==r['cost']['observed_sampled_cycles'],'actual cycle receipt '+str(path))
            check(abs(seconds-r['cost']['native_seconds'])<1e-7,'native seconds receipts '+str(path))
            check(r['cost']['cache_reused_native_jobs']==0,'no zero-cost result reuse '+str(path))
    check(len(native_folders)==len(set(native_folders))==protocol['total_expected_native_jobs'],'112 distinct physically executed native jobs')
    for unit in protocol['run_order']:
        folder=out/'sessions'/unit['case_id']/str(unit['seed'])/unit['strategy'];rng=random.Random(unit['seed']);seen=set();cost=0
        for index in range(protocol['max_queries_per_unit']):
            selection=read(folder/f'selection{index:02}.json');ranked=selection['ranked']
            if unit['strategy']=='S2':best=min(x['obligation_exposure_count'] for x in ranked);choices=[x for x in ranked if x['obligation_exposure_count']==best]
            else:best=max(x['score'] for x in ranked);choices=[x for x in ranked if abs(x['score']-best)<1e-12]
            check(rng.choice(choices)['query_id']==selection['selected_query_id'],'seeded strategy tie replay '+str(folder)+'/'+str(index))
            for rank in ranked:
                expected=rank['benefit_score']/rank['scheduled_sampled_cycles'] if unit['strategy']=='active_cost' else rank['benefit_score']
                check(abs(rank['score']-expected)<1e-12,'declared cost divisor '+rank['query_id'])
                check(rank['query_id'] not in seen and cost+rank['scheduled_sampled_cycles']<=protocol['reserved_cycle_budget_per_unit'],'unseen in-budget proposal '+rank['query_id'])
            record=read(folder/f'query{index:02}/acquisition.json')
            check(record['query']['id']==selection['selected_query_id'],'submitted equals selected '+str(folder)+'/'+str(index))
            seen.add(record['query']['id']);cost+=record['cost']['submitted_sampled_cycles']
        check(len(seen)==4,'four distinct real queries '+str(folder))
    result=dict(status='passed' if all(c['passed'] for c in checks) else 'failed',checks=len(checks),failures=[c for c in checks if not c['passed']],
        native_jobs_replayed=len(native_folders),main_queries=sum(top=='sessions' for top,r in records),model_calls=0,new_native_jobs=0,
        total_wall_seconds_excluding_lock_wait=sum(r['cost'].get('total_wall_seconds_excluding_lock_wait',r['cost']['acquisition_wall_seconds']-r['cost']['lock_wait_seconds']) for top,r in records),
        analysis_only_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),checks_are_posthoc_not_selection=True)
    cases.dump(out/'audit.json',result);print(json.dumps(result));return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);audit(p.parse_args().out)
