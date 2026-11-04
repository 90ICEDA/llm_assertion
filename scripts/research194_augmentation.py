"""Paired development-fault augmentation; independent fault definitions excluded.

with: primary, fixed guided development fault 1, fixed guided development fault 2.
without: primary on the exact same three input schedules. Every acquisition is
physically submitted, including duplicates. Model requests require a new seal.
"""
import argparse
import concurrent.futures
import copy
from pathlib import Path
import research194_cases as cases
import research194_refinement as r
import research194_refinement_runner as run

CASES=('arbiter','counter','uart','ibex_flush')
CONDITIONS=('without','with')


class FaultAdapter(run.CaseAdapter):
    def evaluate(self,candidate,out,queries):
        groups={}
        allowed={f['id'] for f in self.case['faults'] if f.get('split','development')=='development'}|{'primary'}
        for query in queries:
            fault=query.get('_fault','primary')
            if fault not in allowed:raise ValueError('not_a_development_fault:'+fault)
            groups.setdefault(fault,[]).append(query)
        out=Path(out);out.mkdir(parents=True,exist_ok=False);parts=[]
        for fault,rows in groups.items():
            measured=cases.evaluate(self.case_id,candidate,out/fault,queries=rows,split='development',fault=fault)
            parts.append(run.bind_measurement(measured,candidate))
        result=run.merge_measurements(candidate,parts)
        result['cost']={key:sum(p['cost'].get(key,0) for p in parts) for key in
            ('queries','native_compile_attempts','native_execution_attempts','native_seconds','wall_seconds')}
        result['cost']['model_calls']=0;result['faults_evaluated']=list(groups)
        result['history_composition']['reason']='Actual separate same-candidate native execution for every development fault group.'
        run.dump(out/'measurement.json',result);return result


class FaultSession:
    def __init__(self,adapter,condition,seed,schedule,out):
        if condition not in CONDITIONS:raise ValueError('condition')
        self.adapter=adapter;self.condition=condition;self.seed=seed;self.schedule=copy.deepcopy(schedule)
        self.out=Path(out);self.out.mkdir(parents=True,exist_ok=False)
        self.strategy='augmentation_'+condition;self.records=[]
        self.allowed={f['id'] for f in adapter.case['faults'] if f.get('split','development')=='development'}|{'primary'}
        if len(schedule)!=3 or any(x['fault'] not in self.allowed for x in schedule):raise ValueError('three_development_only_rounds')
    def acquire(self,current_candidate,round,history=()):
        if round!=len(self.records) or round>=3:raise ValueError('fixed_sequential_query_budget')
        planned=self.schedule[round]
        fault=planned['fault'] if self.condition=='with' else 'primary'
        query=copy.deepcopy(planned['query']);query['_fault']=fault
        measurement=self.adapter.evaluate(current_candidate,self.out/f'query{round:02}'/'native',[query])
        record=dict(case_id=self.adapter.case_id,seed=self.seed,strategy=self.strategy,condition=self.condition,round=round,
            candidate_sha256=r.digest(current_candidate),query=query,queries=[query],measurement=measurement,
            evidence=measurement['evidence'],cost=dict(measurement['cost'],submitted_queries=1,submitted_native_jobs=2),
            fault_id=fault,source='fixed preregistered development schedule; no independent access',heldout_access=False)
        self.records.append(record);run.dump(self.out/f'query{round:02}'/'acquisition.json',record);return record
    def reuse_acquisition(self,record,current_candidate):
        if self.records or record['round']!=0:raise ValueError('only_prepared_first_acquisition')
        if (record['case_id'],record['seed'],record['condition'])!=(self.adapter.case_id,self.seed,self.condition):raise ValueError('paired_condition_binding')
        expected=dict(self.schedule[0]['query'],_fault='primary')
        if r.digest(expected)!=r.digest(record['query']) or record['candidate_sha256']!=r.digest(current_candidate):raise ValueError('first_query_or_candidate_changed')
        reused=copy.deepcopy(record);reused['reuse']=dict(physical_native_jobs=0,logical_native_jobs=2,source_sha256=r.digest(record),original_cost=record['cost'])
        reused['cost']=dict(record['cost'],native_compile_attempts=0,native_execution_attempts=0,native_seconds=0,wall_seconds=0,logical_native_jobs=2)
        self.records.append(reused);run.dump(self.out/'query00'/'acquisition.json',reused);return reused


def read_guided_feedback(paths,ibex_primary=None):
    """Only dedicated guided feedback files; no all-strategy/test catalogue."""
    result={};bindings={}
    for path in paths:
        path=Path(path).resolve();data=run.read(path)
        if isinstance(data,list):
            if ibex_primary is None or {x.get('fault') for x in data}!={'dev_ready_gate','dev_stall_advance'}:raise ValueError('explicit_ibex_primary_development_qualification_required')
            primary=Path(ibex_primary);protocol=run.read(primary/'protocol.json');measurement=run.read(primary/'initial'/'measurement.json')
            query=next(q for q in protocol['queries'] if q['family']=='flush_stall')
            witness=[e for e in measurement['evidence'] if e['query_id']==query['id'] and e['status']=='confirmed' and e['label']=='violation' and e.get('counted_target',False)]
            rows=[dict(fault_id='primary',order=0,valid_reachable_fault=bool(witness) and measurement['native_complete'],queries=[query],
                measurement=str(primary/'initial'/'measurement.json'),selection='fixed primary flush_stall qualification; no independent access')]
            for index,fault in enumerate(('dev_ready_gate','dev_stall_advance'),1):
                item=next(x for x in data if x['fault']==fault)
                rows.append(dict(fault_id=fault,order=index,valid_reachable_fault=item['valid_reachable'],queries=[item['query']],
                    measurement=item['measurement'],selection='fixed declared Ibex development fault order; no ranking by outcome'))
            bindings[str(primary/'protocol.json')]=run.file_hash(primary/'protocol.json')
            data=dict(cases={'ibex_flush':rows},independent_faults_exposed=False)
        if data.get('independent_faults_exposed') not in (False,0):raise ValueError('requires_explicit_development_only_feedback')
        bindings[str(path)]=run.file_hash(path)
        for cid,rows in data['cases'].items():
            if cid not in CASES:raise ValueError('unregistered_case')
            if cid in result and r.digest(result[cid])!=r.digest(rows):raise ValueError('ambiguous_feedback_version:'+cid)
            result[cid]=rows
            for item in rows:
                if isinstance(item['measurement'],str):bindings[item['measurement']]=run.file_hash(item['measurement'])
    return result,bindings


def development_schedule(adapter,feedback):
    ordered=sorted(feedback,key=lambda x:x['order'])
    primary=[x for x in ordered if x['fault_id']=='primary']
    other=[x for x in ordered if x['fault_id']!='primary']
    if len(primary)!=1 or len(other)!=2:raise ValueError('exact_fixed_primary_plus_two_guided_faults_required')
    result=[]
    allowed={f['id'] for f in adapter.case['faults'] if f.get('split','development')=='development'}|{'primary'}
    for item in primary+other:
        if item['fault_id'] not in allowed or item['valid_reachable_fault'] is not True:raise ValueError('guided_fault_not_confirmed_development')
        # A feedback entry supplies its predeclared complete stimulus. Joining
        # schedules would change semantics: require an explicit single query.
        if len(item['queries'])!=1:raise ValueError('one_preregistered_query_per_fault_required')
        validated=run.read(item['measurement']) if isinstance(item['measurement'],str) else item['measurement']
        result.append(dict(fault=item['fault_id'],query=item['queries'][0],
            validation_measurement_sha256=r.digest(validated),selection=item.get('selection'),
            valid_reachable_fault=True,development_only=True))
    return result


def prepare(active_root,feedback_paths,out,workers=2,ibex_primary=None):
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
    feedback,feedback_bindings=read_guided_feedback(feedback_paths,ibex_primary)
    if set(feedback)!=set(CASES):raise ValueError('all_four_fixed_cases_required_no_population_shrinkage')
    baselines=run.read(Path(active_root)/'baseline_index.json')
    schedules={cid:development_schedule(FaultAdapter(cid),feedback[cid]) for cid in CASES}
    run.dump(out/'development_schedules.json',schedules)
    plans=[(cid,seed,condition) for cid in CASES for seed in run.SEEDS for condition in CONDITIONS]
    def first(plan):
        cid,seed,condition=plan;adapter=FaultAdapter(cid);folder=out/'requests'/cid/str(seed)/condition
        base=run.read(baselines[f'{cid}/{seed}'])
        # Fresh physical acquisition for BOTH conditions; repeated primary is
        # deliberately charged, not memoized based on an earlier success.
        session=FaultSession(adapter,condition,seed,schedules[cid],folder/'first_search')
        acquisition=session.acquire(adapter.case['initial'],0)
        current=run.merge_measurements(adapter.case['initial'],[base['measurement'],acquisition['measurement']])
        queries=run.query_union(base['queries'],acquisition['queries'])
        if current['critical_unknown'] or not current['native_complete'] or not current['reference_complete']:
            state=dict(case_id=cid,strategy='R3',seed=seed,initial=adapter.case['initial'],baseline=base['measurement'],first_measurement=current,queries=queries,status='unknown_retained_initial',model_calls=0)
            run.dump(folder/'prepared'/'state.json',state)
            entry=dict(mode='blocked_unknown',state=str(folder/'prepared'/'state.json'),state_sha256=run.file_hash(folder/'prepared'/'state.json'),request=None,request_sha256=None)
        else:
            entry=run.prepare_first(adapter,'R3',seed,base['measurement'],queries,acquisition,folder/'prepared',current_measurement=current)
        entry.update(case_id=cid,seed=seed,condition=condition,strategy='R3',prepared=str(folder/'prepared'),
            baseline_source=baselines[f'{cid}/{seed}'],first_acquisition_source=str(folder/'first_search'/'query00'/'acquisition.json'),schedule=schedules[cid])
        return entry
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:entries=list(pool.map(first,plans))
    protocol=run.seal_package(out,entries,list(CASES))
    protocol.update(package='development_fault_augmentation',trajectories=['without','with'],
        conditions=list(CONDITIONS),strategy='R3',fixed_trajectory_population=16,
        acquisition_schedule='with: primary/dev1/dev2; without: primary/primary/primary; identical rows and query submissions',
        development_feedback_bindings=feedback_bindings,
        actual_preparation_native_compile_attempts=sum(run.read(e['first_acquisition_source'])['cost']['native_compile_attempts'] for e in entries),
        independent_fault_definitions='Never read into schedules or model requests',
        fault_augmentation='This package; separate from 192-call main comparison',
        native_budget=dict(search_queries_per_condition=3,native_jobs_per_query=2,
            repeated_queries='Physically executed and charged for both conditions',
            maximum_proposal_gate_jobs_per_condition=18,maximum_total_logical_native_jobs_per_condition=24,
            note='Proposal history groups queries by fault AND input rows. Different faults cannot be deduplicated together.'))
    protocol['source_bindings'][str(Path(__file__).resolve())]=run.file_hash(__file__)
    protocol['source_bindings'][str(out/'development_schedules.json')]=run.file_hash(out/'development_schedules.json')
    protocol['source_bindings'].update(feedback_bindings)
    run.dump(out/'protocol.json',protocol)
    run.dump(out/'seal.json',dict(protocol_sha256=run.file_hash(out/'protocol.json'),version='research194'))
    run.dump(out/'review.json',dict(status='prepared_not_authorized',model_calls=0,maximum_model_calls=protocol['maximum_model_calls'],maximum_population_model_calls=48,
        first_requests=protocol['exact_first_requests'],actual_preparation_native_compile_attempts=protocol['actual_preparation_native_compile_attempts'],endpoint=run.ENDPOINT))
    return protocol


def execute(prepared,out,authorization,workers=2):
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
    protocol,_=run.verify_package(prepared)
    if protocol.get('package')!='development_fault_augmentation':raise ValueError('augmentation_seal_required')
    backend=run.ApprovedRemoteBackend(prepared,authorization,out/'global_model_ledger.json')
    def one(entry):
        state=run.read(entry['state']);folder=out/entry['case_id']/str(entry['seed'])/entry['condition']
        adapter=FaultAdapter(entry['case_id']);base=run.read(entry['baseline_source'])
        if entry.get('mode')=='blocked_unknown':
            terminal=folder/'refinement'
            run.dump(terminal/'frozen.json',state['initial']);run.dump(terminal/'terminal_measurement.json',state['first_measurement']);run.dump(terminal/'trajectory_queries.json',state['queries'])
            result=dict(case_id=entry['case_id'],seed=entry['seed'],condition=entry['condition'],strategy='R3',search_strategy='augmentation_'+entry['condition'],status='frozen',termination_reason='unknown_retained_initial',provenance='real_remote_model',model_calls=0,actual_model_calls=0,causal_comparison_eligible=False,frozen_sha256=r.digest(state['initial']),initial_sha256=r.digest(state['initial']))
            run.dump(terminal/'outcome.json',result);return result
        session=FaultSession(adapter,entry['condition'],entry['seed'],entry['schedule'],folder/'search')
        result=run.run_trajectory(adapter,'R3',entry['seed'],folder/'refinement',state['baseline'],base['queries'],session,backend,prepared=entry['prepared'])
        result['condition']=entry['condition'];run.dump(folder/'refinement'/'outcome.json',result);return result
    results=[];errors=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures={pool.submit(one,e):e for e in protocol['entries']}
        for future in concurrent.futures.as_completed(futures):
            entry=futures[future]
            try:results.append(future.result())
            except Exception as exc:
                errors.append(dict(case_id=entry['case_id'],seed=entry['seed'],condition=entry['condition'],error_type=type(exc).__name__,error=str(exc),status='unknown_not_retried'))
                folder=out/entry['case_id']/str(entry['seed'])/entry['condition']/'refinement'
                results.append(run.freeze_interruption(folder,run.read(entry['state']),exc,'augmentation_'+entry['condition'],entry['condition']))
            run.dump(out/'progress.json',dict(results=results,errors=errors))
    result=dict(status='completed' if not errors else 'completed_with_unknown_trajectories',results=results,errors=errors,
        reserved_physical_slots=len(backend.calls),independent_acceptance='not_read_or_run')
    run.dump(out/'outcome.json',result);return result


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('action',choices=['prepare','verify','run'])
    ap.add_argument('--active',type=Path);ap.add_argument('--feedback',type=Path,nargs='+');ap.add_argument('--prepared',type=Path)
    ap.add_argument('--ibex-primary',type=Path)
    ap.add_argument('--out',type=Path);ap.add_argument('--authorization',type=Path);ap.add_argument('--workers',type=int,default=2);a=ap.parse_args()
    if a.action=='prepare':
        if not a.active or not a.feedback or not a.out:ap.error('prepare requires --active --feedback --out')
        p=prepare(a.active,a.feedback,a.out,a.workers,a.ibex_primary);print('PREPARED augmentation '+str(p['exact_first_requests'])+' first requests; zero model calls')
    elif a.action=='verify':
        p,_=run.verify_package(a.prepared);print('VERIFIED '+str(p['exact_first_requests'])+' first requests; zero model calls')
    else:
        if not a.prepared or not a.out or not a.authorization:ap.error('run requires new --authorization and --prepared --out')
        execute(a.prepared,a.out,a.authorization,a.workers)
