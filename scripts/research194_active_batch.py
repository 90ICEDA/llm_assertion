"""Predeclared native S0--S3 comparison. No model calls or held-out access."""
import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
import time
import research194_active_search as active
import research194_cases as cases

ROOT=Path(__file__).resolve().parents[1]
SEEDS=[19407,19419]
CASES=['arbiter','counter','uart','ibex_flush']


def run_unit(case_id,seed,out,baseline):
    config=cases.get_case(case_id);paths=[]
    for strategy in active.STRATEGIES:
        folder=out/'sessions'/case_id/str(seed)/strategy
        session=active.Session(case_id,strategy,seed,folder,initial_queries=baseline['queries'],initial_evidence=baseline['measurement']['evidence'],max_queries=2)
        for index in range(2):
            session.acquire(config['initial'],round=index)
            print(json.dumps(dict(case=case_id,seed=seed,strategy=strategy,query=index,status='completed')),flush=True)
        paths.append(str(folder/'summary.json'))
    return dict(case_id=case_id,seed=seed,sessions=paths)


def prepare(out):
    if out.exists():raise ValueError('new experiment directory required')
    out.mkdir(parents=True)
    configs={case:cases.get_case(case) for case in CASES}
    paths=[Path(__file__),Path(active.__file__),Path(active.sem.__file__),Path(cases.__file__),ROOT/'scripts/research194_ibex.py',ROOT/'scripts/research_native_runner.py']
    protocol=dict(experiment='r194 active native cross-design comparison',algorithm_version=active.VERSION,cases=CASES,seeds=SEEDS,
        strategies=list(active.STRATEGIES),initial_candidates={case:c['initial'] for case,c in configs.items()},
        submitted_queries_per_unit_strategy=2,total_search_queries=64,total_search_native_jobs=128,
        model_calls=0,heldout_access=False,baseline='first public query; one shared physical execution per unique descriptor and candidate; excluded from search cost',
        semantic_qualification='Ibex flush_ready and flush_stall, four extra native jobs, verify nonvacuous markers for all pool assertions; qualification evidence withheld from search histories',
        source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
        query_pool_sha256={f'{case}/{seed}':active.sem.digest(cases.query_pool(case,split='development',seed=seed)) for case in CASES for seed in SEEDS},
        stimuli_seed_note='arbiter/counter/UART seeds change selection, not fixed public stimuli; both predeclared odd Ibex seeds likewise share instruction schedule',
        analysis='unique first-violation transaction+obligation evidence IDs, legal false-alarm IDs, separate parent and transaction counts; public baseline gaps excluded from new coverage',
        cost='actual submitted query and actual native compile/execution attempts; no search evaluation memoization',
        stop_rule='fixed budget; execution failures retained as unknown, no replacement by successful extra query')
    active.dump(out/'protocol.json',protocol)
    for p in paths:
        frozen=out/'source_snapshot'/p.relative_to(ROOT)
        frozen.parent.mkdir(parents=True,exist_ok=True);frozen.write_bytes(p.read_bytes())
    return protocol


def run(out,workers):
    protocol=json.loads((out/'protocol.json').read_text())
    for path,digest in protocol['source_sha256'].items():
        if hashlib.sha256((ROOT/path).read_bytes()).hexdigest()!=digest:raise ValueError('source changed after protocol: '+path)
    started=time.monotonic();baselines={};units=[];qualification_cost=0
    for case_id in CASES:
        cfg=cases.get_case(case_id)
        for seed in SEEDS:
            if (out/'STOP').exists():raise RuntimeError('STOP requested before next baseline query')
            query=cases.query_pool(case_id,split='development',seed=seed)[0]
            key=active.sem.digest(dict(case=case_id,candidate=cfg['initial'],query=query))
            if key not in baselines:
                folder=out/'baselines'/key[:16]
                combined,mapping=active.combine_candidates(cfg['candidate_pool'])
                raw=cases.evaluate(case_id,combined,folder/'native',queries=[query],split='development')
                verification=[dict(variant=j['variant'],**active.sem.verify_native_predictions(active.semantic_candidate(combined,cfg),j['trace'],j['result'])) for j in raw['executions']]
                active.dump(folder/'semantic_native_preflight.json',verification)
                if any(v['status']!='confirmed_semantics' for v in verification):
                    failed=dict(status='preflight_failed',case_id=case_id,seed=seed,reason='native trigger/failure markers disagree with bounded semantic predictions or semantics unknown',checks=verification,search_queries=0)
                    active.dump(out/'outcome.json',failed)
                    return failed
                measurement=active.project_measurement(raw,cfg['initial'],mapping)
                for ev in measurement['evidence']:ev['candidate_sha256']=active.sem.digest(cfg['initial'])
                base=dict(case_id=case_id,candidate_sha256=active.sem.digest(cfg['initial']),queries=[query],measurement=measurement,
                    shared_physical=True,source_path=str(folder/'baseline.json'))
                active.dump(folder/'baseline.json',base);baselines[key]=base
            units.append((case_id,seed,baselines[key]))
    active.dump(out/'baseline_index.json',{f'{c}/{s}':b['source_path'] for c,s,b in units})
    cfg=cases.get_case('ibex_flush');combined,mapping=active.combine_candidates(cfg['candidate_pool'])
    qualified_labels=set()
    for query in cases.query_pool('ibex_flush',split='development',seed=SEEDS[0]):
        if query['family'] not in ('flush_ready','flush_stall'):continue
        if (out/'STOP').exists():raise RuntimeError('STOP requested before next qualification query')
        folder=out/'qualification_only'/query['family']
        raw=cases.evaluate('ibex_flush',combined,folder/'native',queries=[query],split='development')
        qualification_cost+=raw['cost']['native_execution_attempts']
        verification=[dict(variant=j['variant'],**active.sem.verify_native_predictions(active.semantic_candidate(combined,cfg),j['trace'],j['result'])) for j in raw['executions']]
        for j in raw['executions']:qualified_labels.update(m['id'] for m in j['result']['triggers'])
        active.dump(folder/'semantic_native_preflight.json',dict(checks=verification,excluded_from_search_history=True))
        if any(v['status']!='confirmed_semantics' for v in verification):
            failed=dict(status='preflight_failed',case_id='ibex_flush',query_id=query['id'],reason='nonvacuous semantic/native inconsistency',checks=verification,search_queries=0)
            active.dump(out/'outcome.json',failed);return failed
    if qualified_labels!={a['label'] for a in combined}:
        failed=dict(status='preflight_failed',reason='Ibex pool assertions not all triggered in qualification',qualified_labels=sorted(qualified_labels),search_queries=0)
        active.dump(out/'outcome.json',failed);return failed
    if (out/'STOP').exists():raise RuntimeError('STOP requested before main search')
    completed=[];errors=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures={pool.submit(run_unit,c,s,out,b):(c,s) for c,s,b in units}
        for f in concurrent.futures.as_completed(futures):
            try:completed.append(f.result())
            except Exception as exc:
                case,seed=futures[f];errors.append(dict(case_id=case,seed=seed,error=repr(exc)))
            active.dump(out/'progress.json',dict(completed=completed,errors=errors,wall_seconds=time.monotonic()-started))
    result=dict(status='completed' if not errors and len(completed)==8 else 'incomplete',completed=completed,errors=errors,
        model_calls=0,wall_seconds=time.monotonic()-started,shared_baseline_native_execution_attempts=sum(b['measurement']['cost']['native_execution_attempts'] for b in baselines.values()),qualification_native_execution_attempts=qualification_cost)
    active.dump(out/'outcome.json',result)
    return result


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--prepare-only',action='store_true');ap.add_argument('--run-prepared',action='store_true');ap.add_argument('--workers',type=int,default=2)
    args=ap.parse_args();out=args.out.resolve()
    if not out.is_relative_to(ROOT/'deliverables'):raise ValueError('deliverables only')
    if not args.run_prepared:prepare(out)
    if not args.prepare_only:print(json.dumps(run(out,args.workers)))


if __name__=='__main__':main()
