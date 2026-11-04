"""Read-only replay of search selection, native records and independent monitors.

Only audit.json is written. This audit launches no simulations or models and
never constructs the independent-test query population.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import random
import re
import research194_active_search as active
import research194_cases as cases

ROOT=Path(__file__).resolve().parents[1]


def audit(root):
    errors=[];checks=0;counts=dict(records=0,native_logs=0,oracle_replays=0,selection_replays=0,preflight_jobs=0)
    def check(condition,message):
        nonlocal checks
        checks+=1
        if not condition:errors.append(message)
    protocol=json.loads((root/'protocol.json').read_text())
    for path,digest in protocol['source_sha256'].items():
        check(hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==digest,'current source changed '+path)
        check(hashlib.sha256((root/'source_snapshot'/path).read_bytes()).hexdigest()==digest,'snapshot source mismatch '+path)
    if errors:
        result=dict(status='blocked_source_mismatch',errors=errors,checks=checks,new_native_executions=0,model_calls=0)
        active.dump(root/'audit.json',result);return result
    baseline_index=json.loads((root/'baseline_index.json').read_text())
    for p in root.glob('baselines/*/semantic_native_preflight.json'):
        for v in json.loads(p.read_text()):
            counts['preflight_jobs']+=1;check(v['status']=='confirmed_semantics',str(p)+' baseline unknown')
    for p in root.glob('qualification_only/*/semantic_native_preflight.json'):
        data=json.loads(p.read_text());check(data['excluded_from_search_history'],str(p)+' qualification leaked')
        for v in data['checks']:
            counts['preflight_jobs']+=1;check(v['status']=='confirmed_semantics',str(p)+' qualification unknown')
    for folder in sorted((root/'sessions').glob('*/*/S*')):
        sp=json.loads((folder/'protocol.json').read_text());case=sp['case_id'];cfg=cases.get_case(case)
        basepath=Path(baseline_index[f'{case}/{sp["seed"]}'])
        if not basepath.exists():basepath=root/'baselines'/basepath.parent.name/'baseline.json'
        base=json.loads(basepath.read_text())
        replay=active.Session.__new__(active.Session)
        replay.config=cfg;replay.pool=sp['query_pool'];replay.rng=random.Random(sp['seed']);replay.strategy=sp['strategy']
        replay.initial_queries=base['queries'];replay.history=copy.deepcopy(base['measurement']['evidence']);replay.seen={q['id'] for q in base['queries']}
        replay.observed_xor={};replay.records=[];replay.counts={q['id']:int(q['id'] in replay.seen) for q in replay.pool}
        baseline_gaps=set(active.gaps(replay.history));discovered=set()
        check(sp['initial_candidate_sha256']==active.sem.digest(cfg['initial']),str(folder)+' initial changed')
        check(sp['query_pool_sha256']==protocol['query_pool_sha256'][f'{case}/{sp["seed"]}'],str(folder)+' population changed')
        for path in sorted(folder.glob('query*/acquisition.json')):
            r=json.loads(path.read_text());counts['records']+=1
            check(r['candidate_sha256']==active.sem.digest(cfg['initial']),str(path)+' candidate changed')
            check(not r['heldout_access'] and r['query']['split']=='development',str(path)+' hidden access')
            expected=replay.rank(cfg['initial']);counts['selection_replays']+=1
            check(expected['selected_query_id']==r['query']['id'],str(path)+' selection mismatch')
            check(expected['reason']==r['selection']['reason'],str(path)+' reason mismatch')
            for er,ar in zip(expected['ranked'],r['selection']['ranked']):
                check(all(er[k]==ar[k] for k in ('query_id','semantic_discrimination','unprotected_fraction','novelty','score','query_count')),str(path)+' rank component mismatch')
            raw=json.loads((path.parent/'native'/'measurement.json').read_text());mapping=json.loads((path.parent/'candidate_bindings.json').read_text())['mapping']
            projection=active.project_measurement(raw,cfg['initial'],mapping)
            for field in ('targets','detected_ids','triggered_ids','target_transaction_ids','covered_obligations','critical_unknown'):
                check(projection[field]==r['measurement'][field],str(path)+' projection mismatch '+field)
            current=set(active.gaps(projection['evidence']));new=current-baseline_gaps-discovered
            check(current==set(r['gap_ids']),str(path)+' wrong gap IDs');check(new==set(r['new_gap_ids']),str(path)+' wrong marginal IDs')
            discovered.update(new);check(discovered==set(r['cumulative_new_gap_ids']),str(path)+' cumulative mismatch')
            actual_xor=False
            for index,job in enumerate(raw['executions']):
                logfile=path.parent/'native'/'q0'/job['variant']/'execute.log'
                if not logfile.exists():
                    check(job['result'].get('execution_status')!='completed',str(logfile)+' missing completed log');continue
                text=logfile.read_text();counts['native_logs']+=1
                for marker,field in [('ASSERT_FAIL','failures'),('TRIGGER','triggers')]:
                    parsed=[dict(id=a,detail=b.strip()) for a,b in re.findall(r'^'+marker+r'\s+(\S+)(.*)$',text,re.M)]
                    check(parsed==job['result'][field],str(logfile)+' native marker mismatch '+field)
                trace=[{k:int(v) for k,v in re.findall(r'(\w+)=(-?\d+)',line)} for line in text.splitlines() if line.startswith('TRACE ')]
                check(trace==job['trace'],str(logfile)+' trace mismatch')
                ref=cases.reference(case,trace);counts['oracle_replays']+=1
                check(ref==job['reference'],str(logfile)+' independent monitor mismatch')
                check(all(all(row.get(k)==v for k,v in q.items()) for row,q in zip(trace,r['query']['rows'])) and len(trace)==len(r['query']['rows']),str(logfile)+' submitted inputs mismatch')
                sets=[]
                for ci in range(len(cfg['candidate_pool'])):sets.append({m['detail'] for m in job['result']['failures'] if mapping[m['id']]['candidate']==ci})
                actual_xor=actual_xor or any(a!=b for a in sets for b in sets)
                labels={a['label'] for a in cfg['initial']}
                check(all(a['assertion'] in labels for e in projection['evidence'] for a in e['assertions']),str(path)+' comparison marker leaked')
            check(actual_xor==any(v['actual_native_xor'] for v in r['native_prediction_validation']),str(path)+' XOR mismatch')
            check(r['cost']['model_calls']==0 and r['cost']['submitted_native_jobs']==2,str(path)+' cost policy')
            check(r['cost']['native_execution_attempts']==len(list((path.parent/'native').rglob('execute.json'))),str(path)+' physical execution count')
            replay.seen.add(r['query']['id']);replay.counts[r['query']['id']]+=1;replay.history.extend(r['evidence']);replay.records.append(r);replay.observed_xor[r['query']['id']]=actual_xor
    check(counts['records']==64,'incomplete planned 64 query records')
    result=dict(status='passed' if not errors else 'failed',checks=checks,counts=counts,errors=errors,new_native_executions=0,model_calls=0,
        scope='predeclared source bindings, exact selection replay, current-candidate label isolation, actual native markers and inputs, independent monitor replay, evidence uniqueness and cost counts; no heldout access')
    active.dump(root/'audit.json',result);return result


def main():
    ap=argparse.ArgumentParser();ap.add_argument('root',type=Path);args=ap.parse_args();print(json.dumps(audit(args.root.resolve())))


if __name__=='__main__':main()
