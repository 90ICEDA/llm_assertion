"""Prospective A0-A3 protocol using existing native FIFO and refinement adapters.

prepare performs local acquisition and seals all eight exact remote requests.
run is separate: never dispatch as a side effect of preparing or reporting.
"""
import argparse
import copy
import itertools
import json
import random
from pathlib import Path

import research192_temporal_refinement as refine
import research_active_temporal as active

p,s,ROOT=refine.p,refine.s,refine.ROOT
SEEDS=(19207,19219)
ARMS={'A0':('ordinary','R1'),'A1':('active','R1'),
      'A2':('ordinary','R3'),'A3':('active','R3')}


def options():
    return [dict(id=f'{depth}/{policy}',descriptor=p.descriptor(depth,policy,6,0),
                 dimensions=['trigger','exception'], obligations=[p.OB+'/'+policy],
                 estimated_cost=2,constraints=['accepted input handshake','unique TID','initial reset','frame completion','first presentation readiness'])
            for depth,policy in itertools.product((16,32),p.q.POLICIES)]


def prepare(out):
    out.mkdir(parents=True,exist_ok=False)
    initial,jobs,protected,evidence=refine.archived_baseline()
    # Historical protection is visible to every group; new ready-first evidence
    # must come from its own charged queries. Full gate remains the same for all.
    history=[e for e in evidence if e.get('policy')=='stalled_first']
    request=s.read(refine.SOURCE/'request.preview.json')
    body=json.loads(request['messages'][1]['content'])
    body['current_status']='Partial current candidate; infer applicability only from the shared specification and supplied observations.'
    body.pop('public_development',None)
    request['messages'][1]['content']=json.dumps(body,separators=(',',':'))
    protocol=dict(purpose='research192_native_2x2_active_local_pilot',arms=ARMS,seeds=SEEDS,
        authorization='Current request authorizes experiments; external dispatch separately gated by approval review.',
        model=refine.MODEL,temperature=0.2,max_output_tokens=1024,max_model_calls=8,
        per_arm_model_calls=1,per_stream_queries=2,query_native_executions=2,retries=0,
        initial_sha256=p.digest(initial),common_history_sha256=p.digest(history),
        selection='S0 uniform public descriptor pool; S3 ranks uncovered readiness branch, acquisition novelty and measured cost. One initial candidate means structural disagreement is zero in this stratum.',
        fairness='A0/A2 share identical ordinary acquisition; A1/A3 share active acquisition. Both streams same pool, common history, seed, two actual queries. Model budget is equal; actual tokens reported, never assumed equal.',
        scope='One original FIFO historical parent. Readiness branches are not separate bugs or obligations in final metrics.',
        safety='Unknown/duplicate/no-exposure queries charged; no query retries or outcome-dependent budget extensions.',
        independence='All acquisition is development. No independent test outcomes or successful archived proposals enter requests.',
        test_plan='All16 R/A terminal versions freeze before a common16-scene independent run; same parent defect, no unseen-mutant claim.')
    s.dump(out/'protocol.json',protocol)
    s.dump(out/'initial.json',initial)
    s.dump(out/'history.json',history)
    s.dump(out/'protected.json',protected)
    s.dump(out/'base_request.json',request)
    records=[]
    for seed in SEEDS:
        for stream in ('ordinary','active'):
            rng=random.Random(seed)
            selector=active.ActiveSelector(initial,[p.OB+'/'+v for v in p.q.POLICIES])
            selector.observe('shared_history','confirmed',[p.OB+'/stalled_first'],(),2,
                             protected_obligations=[p.OB+'/stalled_first'])
            acquired=[]; selected=[]
            for step in range(2):
                folder=out/f'seed{seed}'/stream/f'q{step}'
                pool=options()
                if stream=='active':
                    selection=selector.select(pool); chosen=selection['chosen']
                else:
                    chosen=rng.choice(pool);selection=dict(chosen=chosen,policy='seeded_uniform',future_outcomes_used=False)
                s.dump(folder/'selection.json',selection)
                measurement=refine.evaluate(initial,folder/'native',(),[chosen['descriptor']],workers=2)
                jobs=s.read(folder/'native/executions.json')
                observed=refine.evidence_from_jobs(initial,jobs)
                acquired.extend(observed);selected.append(chosen['descriptor'])
                targets=set(measurement['public_targets']+measurement['historical_targets'])
                missed=targets-set(measurement['detected_ids'])
                gap_keys=[p.OB+'/FN/atomic_drop'] if missed else []
                confirmed=not measurement['critical_unknown']
                selector.observe(chosen['id'],'confirmed' if confirmed else 'unknown',chosen['obligations'],gap_keys,2,
                    protected_obligations=chosen['obligations'] if confirmed and targets and not missed else ())
                record=dict(seed=seed,stream=stream,step=step,action_id=chosen['id'],
                    gap_keys=gap_keys if confirmed else [],exposed=len(targets),missed=len(missed),
                    unknown=len(measurement['critical_unknown']),native_compile_attempts=len(jobs),
                    native_execution_attempts=sum(j['result']['compile_status']=='passed' for j in jobs),
                    source=s.rel(folder/'native/measurement.json'))
                records.append(record);s.dump(out/'queries.json',records)
                print('ACQUIRED',seed,stream,step,json.dumps(record),flush=True)
            s.dump(out/f'seed{seed}'/stream/'evidence.json',history+acquired)
            s.dump(out/f'seed{seed}'/stream/'descriptors.json',selected)
            for arm,(arm_stream,strategy) in ARMS.items():
                if arm_stream!=stream:continue
                req,findings=refine.build_request(request,strategy,history+acquired,seed,initial)
                s.dump(out/'requests'/f'{seed}_{arm}.json',req)
                s.dump(out/'localization'/f'{seed}_{arm}.json',findings)
    files=[out/'protocol.json',out/'initial.json',out/'history.json',out/'protected.json',out/'base_request.json']
    files+=list((out/'requests').glob('*.json'))+list(out.glob('seed*/*/evidence.json'))+list(out.glob('seed*/*/descriptors.json'))
    files+=[Path(__file__),Path(refine.__file__),Path(active.__file__)]
    s.dump(out/'seal.json',{s.rel(f):s.sha(f) for f in files})
    s.dump(out/'outcome.json',dict(status='prepared_waiting_external_dispatch_approval',model_calls=0,requests=8,queries=len(records)))


def run(prepared,out):
    for name,expected in s.read(prepared/'seal.json').items():
        if s.sha(ROOT/name)!=expected:raise ValueError('prepared_changed:'+name)
    out.mkdir(parents=True,exist_ok=False)
    results=[]
    initial=s.read(prepared/'initial.json');protected=s.read(prepared/'protected.json')
    base_request=s.read(prepared/'base_request.json')
    for seed in SEEDS:
        for arm,(stream,strategy) in ARMS.items():
            evidence=s.read(prepared/f'seed{seed}'/stream/'evidence.json')
            descriptors=s.read(prepared/f'seed{seed}'/stream/'descriptors.json')
            req,_=refine.build_request(base_request,strategy,evidence,seed,initial)
            if req!=s.read(prepared/'requests'/f'{seed}_{arm}.json'):raise ValueError('request_changed')
            result=refine.run_arm(out/f'seed{seed}'/arm,strategy,seed,evidence,initial,protected,
                                 base_request,descriptors,workers=2)
            result['arm']=arm;result['search_stream']=stream
            results.append(result);s.dump(out/'results.json',results)
            print('ARM',json.dumps(result),flush=True)
    s.dump(out/'outcome.json',dict(status='completed',model_calls=sum(r['model_calls'] for r in results)))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['prepare','run'])
    parser.add_argument('--out',required=True,type=Path)
    parser.add_argument('--prepared',type=Path)
    args=parser.parse_args()
    if args.action=='prepare':prepare(args.out.resolve())
    else:run(args.prepared.resolve(),args.out.resolve())
