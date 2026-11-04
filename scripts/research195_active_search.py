"""Opt-in variable-cost active evidence selection using existing native adapters."""
import copy
import hashlib
from pathlib import Path
import random
import shutil
import time

import research194_cases as cases
import research194_active_search as prior
import research194_active_semantics as semantics
from research194_active_analysis import context_gaps
from research194_metrics import temporal_detection

ROOT=Path(__file__).resolve().parents[1]
STRATEGIES=('S2','active_no_cost','active_cost')
NATIVE_LOCK=ROOT/'deliverables/research195_active_native_execution.lock'


def fit_cost_calibration(records):
    """Nonnegative affine wall estimate, from the fixed development pilot only."""
    xs=[r['cost']['observed_sampled_cycles'] for r in records];ys=[r['cost']['native_seconds'] for r in records]
    xbar=sum(xs)/len(xs);ybar=sum(ys)/len(ys);variance=sum((x-xbar)**2 for x in xs)
    slope=max(0,sum((x-xbar)*(y-ybar) for x,y in zip(xs,ys))/variance) if variance else 0
    intercept=max(0,ybar-slope*xbar)
    return dict(native_seconds_intercept=intercept,native_seconds_per_sample=slope,calibration_queries=len(records),
        predictor='nonnegative affine fit on development calibration only; diagnostic, not the primary cycle-cost ranking',
        samples=[dict(sampled_cycles=x,native_seconds=y) for x,y in zip(xs,ys)])


def execute_query(case_id,candidate,query,folder):
    """Two real native jobs, no result cache; shared lock serializes compilers."""
    import fcntl
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=False)
    if shutil.disk_usage(ROOT).free<1024**3:raise RuntimeError('less_than_1GiB_free_before_native_query')
    config=cases.get_case(case_id);combined,mapping=prior.combine_candidates([candidate,*config['candidate_pool'][1:]])
    cases.dump(folder/'candidate_binding.json',dict(candidate_sha256=cases.digest(candidate),combined=combined,mapping=mapping))
    begin=time.monotonic();wait_start=begin
    with NATIVE_LOCK.open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX);lock_wait=time.monotonic()-wait_start
        raw=cases.evaluate(case_id,combined,folder/'native',queries=[query],fault='primary',split='development')
        fcntl.flock(lock,fcntl.LOCK_UN)
    projected=prior.project_measurement(raw,candidate,mapping);verification=[]
    for job in raw['executions']:
        v=semantics.verify_native_predictions(prior.semantic_candidate(combined,config),job['trace'],job['result'])
        verification.append(dict(query_id=job['query_id'],variant=job['variant'],status=v['status'],checks=v['checks'],native_healthy=v['native_healthy']))
    correct=[j for j in raw['executions'] if j['variant']=='correct']
    correct_legal=bool(correct) and all(j['result'].get('compile_status')=='passed' and j['result'].get('execution_status')=='completed'
        and not j['reference']['unknown'] and j['reference']['checks'] and all(c['passed'] for c in j['reference']['checks']) for j in correct)
    sem_ok=all(v['status']=='confirmed_semantics' for v in verification)
    cost=dict(raw['cost'],submitted_queries=1,submitted_sampled_cycles=2*len(query['rows']),
        observed_sampled_cycles=sum(len(j['trace']) for j in raw['executions']),
        lock_wait_seconds=lock_wait,acquisition_wall_seconds=time.monotonic()-begin,cache_reused_native_jobs=0)
    record=dict(case_id=case_id,candidate_sha256=cases.digest(candidate),query=query,measurement=projected,
        semantic_native_checks=verification,semantic_native_consistent=sem_ok,paired_correct_independently_legal=correct_legal,
        gap_contexts=context_gaps(projected) if sem_ok else {},temporal_detection=temporal_detection(projected),
        cost=cost,model_calls=0,heldout_access=False)
    record['actual_native_candidate_disagreement']=any(
        {m['detail'] for m in j['result'].get('failures',[]) if m['id'].startswith('c0_')} !=
        {m['detail'] for m in j['result'].get('failures',[]) if m['id'].startswith('c1_')} for j in raw['executions'])
    cases.dump(folder/'acquisition.json',record)
    return record


class Session:
    def __init__(self,case_id,strategy,seed,pool,baseline,calibration,out,max_queries=4,cycle_budget=1728):
        if strategy not in STRATEGIES:raise ValueError('strategy')
        self.case_id=case_id;self.strategy=strategy;self.seed=seed;self.pool=copy.deepcopy(pool);self.baseline=baseline
        if any(q['split']!='development' for q in pool):raise ValueError('heldout_pool_not_allowed')
        self.config=cases.get_case(case_id);self.candidate=self.config['initial'];self.calibration=calibration
        self.out=Path(out);self.out.mkdir(parents=True,exist_ok=False);self.max_queries=max_queries;self.cycle_budget=cycle_budget
        self.rng=random.Random(seed);self.records=[];self.history=copy.deepcopy(baseline['measurement']['evidence'])
        self.seen=set();self.family_counts={};self.seen_contexts=set();self.baseline_contexts=set(baseline['gap_contexts'])
        self.reserved_cycles=0
        cases.dump(self.out/'protocol.json',dict(case_id=case_id,strategy=strategy,seed=seed,max_queries=max_queries,cycle_budget=cycle_budget,
            candidate_sha256=cases.digest(self.candidate),query_pool_sha256=cases.digest(pool),calibration=calibration,
            baseline_query_id=baseline['query']['id'],baseline_physical_cost_separately_charged=True))

    def rank(self):
        start=time.perf_counter();ranked=[];protected=prior.protected_obligations(self.history,cases.digest(self.candidate))
        candidates=[prior.semantic_candidate(c,self.config) for c in self.config['candidate_pool']]
        prior_queries=[self.baseline['query'],*[r['query'] for r in self.records]]
        for query in self.pool:
            cost=2*len(query['rows'])
            if query['id'] in self.seen or self.reserved_cycles+cost>self.cycle_budget:continue
            goal=semantics.plan_goal(query,candidates,self.config['output_signals'],max_hypotheses=24) if self.strategy!='S2' else None
            deficit=sum(o not in protected for o in query['obligations'])/len(query['obligations'])
            novelty=1/(1+self.family_counts.get(query['family'],0))
            numerator=3*(goal['semantic_discrimination'] if goal else 0)+2*deficit+novelty
            exposure=sum(sum(o in old['obligations'] for old in prior_queries) for o in query['obligations'])
            ranked.append(dict(query_id=query['id'],family=query['family'],input_cycles=len(query['rows']),scheduled_sampled_cycles=cost,
                predicted_native_seconds=self.calibration['native_seconds_intercept']+cost*self.calibration['native_seconds_per_sample'],
                semantic_discrimination=goal['semantic_discrimination'] if goal else None,unprotected_fraction=deficit,
                protected_obligations=sorted(protected),family_novelty=novelty,benefit_score=numerator,
                score=numerator/cost if self.strategy=='active_cost' else numerator,obligation_exposure_count=exposure,
                goal=goal))
        if not ranked:return dict(selected_query_id=None,ranked=[],planning_seconds=time.perf_counter()-start,stop_reason='no_unseen_query_fits_remaining_reserved_cycle_budget')
        if self.strategy=='S2':
            best=min(r['obligation_exposure_count'] for r in ranked);choices=[r for r in ranked if r['obligation_exposure_count']==best]
        else:
            best=max(r['score'] for r in ranked);choices=[r for r in ranked if abs(r['score']-best)<1e-12]
        chosen=self.rng.choice(choices)
        return dict(selected_query_id=chosen['query_id'],ranked=ranked,planning_seconds=time.perf_counter()-start,
            reserved_cycles_before=self.reserved_cycles,remaining_reserved_cycles=self.cycle_budget-self.reserved_cycles,
            evidence_history_is_development_only=True)

    def acquire(self):
        if len(self.records)>=self.max_queries:raise ValueError('query_budget_exhausted')
        selection=self.rank();index=len(self.records)
        cases.dump(self.out/f'selection{index:02}.json',selection)
        if selection['selected_query_id'] is None:return None
        query=next(q for q in self.pool if q['id']==selection['selected_query_id'])
        self.reserved_cycles+=2*len(query['rows'])
        record=execute_query(self.case_id,self.candidate,query,self.out/f'query{index:02}')
        self.seen.add(query['id']);self.family_counts[query['family']]=self.family_counts.get(query['family'],0)+1
        self.history.extend(record['measurement']['evidence'])
        self.seen_contexts.update(set(record['gap_contexts'])-self.baseline_contexts)
        record.update(strategy=self.strategy,seed=self.seed,round=index,task_id=f'{self.case_id}/{self.seed}/{self.strategy}',
            cumulative_new_context_ids=sorted(self.seen_contexts),reserved_cycles_cumulative=self.reserved_cycles)
        chosen=next(r for r in selection['ranked'] if r['query_id']==query['id'])
        record['selected_rank']={k:v for k,v in chosen.items() if k!='goal'}
        record['cost']['planning_seconds']=selection['planning_seconds']
        record['cost']['total_wall_seconds_excluding_lock_wait']=record['cost']['acquisition_wall_seconds']-record['cost']['lock_wait_seconds']+selection['planning_seconds']
        self.records.append(record);cases.dump(self.out/f'query{index:02}'/'acquisition.json',record)
        return record
