"""Prepare exact first requests from paid native S first-query records.

No second search query or independent outcome is read. Future requests are
conditional on real model outputs and remain bounded by the newly sealed code.
"""
import argparse
import concurrent.futures
from pathlib import Path
import research194_refinement as r
import research194_refinement_runner as run
import research194_active_search as active

CASES=['arbiter','counter','uart','ibex_flush']

def prepare(active_root,out):
    active_root=Path(active_root).resolve();out=Path(out).resolve()
    if out.exists():raise ValueError('new preparation directory required')
    protocol=run.read(active_root/'protocol.json')
    for path,expected in protocol['source_sha256'].items():
        if run.file_hash(run.ROOT/path)!=expected:raise ValueError('active_source_changed:'+path)
    if protocol['cases']!=CASES or protocol['seeds']!=list(run.SEEDS):raise ValueError('paired_population_changed')
    baselines=run.read(active_root/'baseline_index.json');entries=[]
    for cid in CASES:
        adapter=run.CaseAdapter(cid)
        if not adapter.case['specification']:raise ValueError('missing_specification:'+cid)
        for seed in run.SEEDS:
            base=run.read(baselines[f'{cid}/{seed}'])
            for search,strategy in r.TRAJECTORIES:
                first_path=active_root/'sessions'/cid/str(seed)/search/'query00/acquisition.json'
                acquired=run.read(first_path)
                if acquired['candidate_sha256']!=r.digest(adapter.case['initial']):raise ValueError('initial_candidate_changed')
                current=run.merge_measurements(adapter.case['initial'],[base['measurement'],acquired['measurement']])
                folder=out/'requests'/cid/str(seed)/(search+'_'+strategy)
                if current['critical_unknown'] or not current['native_complete'] or not current['reference_complete']:
                    state=dict(case_id=cid,strategy=strategy,seed=seed,initial=adapter.case['initial'],baseline=base['measurement'],
                        first_measurement=current,queries=run.query_union(base['queries'],acquired['queries']),status='unknown_retained_initial',model_calls=0)
                    run.dump(folder/'state.json',state)
                    entry=dict(mode='blocked_unknown',state=str(folder/'state.json'),state_sha256=run.file_hash(folder/'state.json'),request=None,request_sha256=None)
                else:
                    entry=run.prepare_first(adapter,strategy,seed,base['measurement'],
                        run.query_union(base['queries'],acquired['queries']),acquired,folder,current_measurement=current)
                entry.update(case_id=cid,seed=seed,search=search,strategy=strategy,prepared=str(folder),
                    baseline_source=baselines[f'{cid}/{seed}'],first_acquisition_source=str(first_path),
                    first_acquisition_sha256=run.file_hash(first_path),baseline_source_sha256=run.file_hash(baselines[f'{cid}/{seed}']))
                entries.append(entry)
    sealed=run.seal_package(out,entries,CASES)
    if sealed['maximum_population_model_calls']!=192:raise AssertionError('expected fixed population 64 paired trajectories x 3 rounds')
    run.dump(out/'review.json',dict(status='prepared_not_authorized',model_calls=0,
        exact_first_requests=sealed['exact_first_requests'],maximum_future_model_calls=sealed['maximum_model_calls'],fixed_trajectory_population=64,endpoint=run.ENDPOINT,
        first_query_only=True,independent_results_read=False,
        alias_pairs={k:list(v) for k,v in r.ABLATION_ALIASES.items()},
        maximum_logical_native_jobs=64*24,shared_baselines_and_standalone_search='separate original costs; first acquisition reuse is recorded'))
    return sealed


def execute(prepared,out,authorization,workers=2):
    """Explicit separate action, requires new seal-bound user authorization."""
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
    protocol,_=run.verify_package(prepared)
    backend=run.ApprovedRemoteBackend(prepared,authorization,out/'global_model_ledger.json')
    def one(entry):
        run.verify_package(prepared)
        adapter=run.CaseAdapter(entry['case_id']);state=run.read(entry['state'])
        base=run.read(entry['baseline_source'])
        folder=out/entry['case_id']/str(entry['seed'])/(entry['search']+'_'+entry['strategy'])
        if entry.get('mode')=='blocked_unknown':
            folder=folder/'refinement';run.dump(folder/'frozen.json',state['initial'])
            run.dump(folder/'terminal_measurement.json',state['first_measurement']);run.dump(folder/'trajectory_queries.json',state['queries'])
            result=dict(case_id=entry['case_id'],seed=entry['seed'],strategy=entry['strategy'],search_strategy=entry['search'],
                status='frozen',termination_reason='unknown_retained_initial',provenance='real_remote_model',model_calls=0,actual_model_calls=0,accepted_rounds=0,causal_comparison_eligible=False,
                frozen_sha256=r.digest(state['initial']),initial_sha256=r.digest(state['initial']))
            run.dump(folder/'outcome.json',result);return result
        session=active.Session(entry['case_id'],entry['search'],entry['seed'],folder/'search',
            initial_queries=base['queries'],initial_evidence=base['measurement']['evidence'],max_queries=3)
        # Session constructor owns its search child, while the trajectory owns
        # a separate result child so both preserve exist_ok=False guarantees.
        return run.run_trajectory(adapter,entry['strategy'],entry['seed'],folder/'refinement',
            state['baseline'],base['queries'],session,backend,prepared=entry['prepared'])
    results=[];errors=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures={pool.submit(one,e):e for e in protocol['entries']}
        for future in concurrent.futures.as_completed(futures):
            e=futures[future]
            try:results.append(future.result())
            except Exception as exc:
                errors.append(dict(case_id=e['case_id'],seed=e['seed'],search=e['search'],strategy=e['strategy'],error_type=type(exc).__name__,error=str(exc),status='unknown_not_retried'))
                folder=out/e['case_id']/str(e['seed'])/(e['search']+'_'+e['strategy'])/'refinement'
                results.append(run.freeze_interruption(folder,run.read(e['state']),exc,e['search']))
            run.dump(out/'progress.json',dict(results=results,errors=errors))
    result=dict(status='completed' if not errors else 'completed_with_unknown_trajectories',results=results,errors=errors,
        model_calls=sum(x['model_calls'] for x in results),reserved_physical_slots=len(backend.calls),independent_acceptance='not_read_or_run')
    run.dump(out/'outcome.json',result);return result


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('action',choices=['prepare','verify','run'])
    ap.add_argument('--active',type=Path);ap.add_argument('--prepared',type=Path);ap.add_argument('--out',type=Path)
    ap.add_argument('--authorization',type=Path);ap.add_argument('--workers',type=int,default=2);a=ap.parse_args()
    if a.action=='prepare':
        if not a.active or not a.out:ap.error('prepare requires --active and --out')
        p=prepare(a.active,a.out);print('PREPARED '+str(len(p['entries']))+' first requests; zero model calls')
    elif a.action=='verify':
        p,_=run.verify_package(a.prepared);print('VERIFIED '+str(len(p['entries']))+' first requests; zero model calls')
    else:
        if not a.prepared or not a.out or not a.authorization:ap.error('run requires --prepared, --out, and NEW --authorization')
        execute(a.prepared,a.out,a.authorization,a.workers)
