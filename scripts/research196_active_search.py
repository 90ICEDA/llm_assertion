"""Wall-cost-aware S0-S3 extension of existing acquisition/execution adapters.

Costs are fitted only on paid development calibration. Output hypotheses are
planning aids, never legality evidence. Unknown reference labels remain intact.
"""
import copy
import math
import time
from pathlib import Path
import research194_active_search as prior
import research194_active_semantics as sem


def control_contexts(query, output_signals=()):
    """Bounded input transitions; no outputs, data values, or trace prefixes."""
    rows=query.get('planner_rows',query['rows']);contexts=set()
    control=('rst_n','rst','flush','clr','en','load','down','request','acknowledge','ready','wr','tx_enable','tick_baud_x16','valid','req_valid','req_ready','rsp_ready')
    previous=None;run=0
    for row in rows:
        state=tuple((k,int(row[k])) for k in control if k in row and k not in output_signals)
        run=run+1 if state==previous else 1
        duration=min(3,int(math.log2(run)))
        contexts.add((previous,state,duration));previous=state
    return contexts


def fit_wall_cost(records):
    if len(records)<3:raise ValueError('at_least_three_development_calibration_queries')
    x=[];y=[];sources=[]
    for r in records:
        if r['query'].get('split')!='development' or r.get('heldout_access') is True:raise ValueError('heldout_cost_calibration_forbidden')
        c=r['cost'];n=c.get('observed_sampled_cycles',2*len(r['query']['rows']))
        wall=c.get('acquisition_wall_seconds',c.get('wall_seconds'))
        if wall is None:raise ValueError('actual_wall_cost_required')
        wall-=c.get('lock_wait_seconds',0)
        if n<=0 or wall<=0 or not math.isfinite(wall):raise ValueError('invalid_calibration_cost')
        x.append(n);y.append(wall);sources.append(sem.digest(r))
    meanx=sum(x)/len(x);meany=sum(y)/len(y);den=sum((a-meanx)**2 for a in x)
    slope=max(0,sum((a-meanx)*(b-meany) for a,b in zip(x,y))/den) if den else 0
    intercept=max(.001,meany-slope*meanx)
    return dict(version='r196-wall-v1',fixed_seconds=intercept,seconds_per_sample=slope,
        calibration_record_sha256=sources,observed_pairs=list(zip(x,y)),
        cost_unit='actual acquisition seconds minus scheduler lock wait',
        rmse=(sum((intercept+slope*a-b)**2 for a,b in zip(x,y))/len(x))**.5,
        heldout_access=False)


def predict(model, query):
    return model['fixed_seconds']+model['seconds_per_sample']*2*len(query['rows'])


class BudgetExhausted(Exception):pass


class Session(prior.Session):
    def __init__(self,*args,cost_model,wall_budget=120.0,**kwargs):
        if cost_model.get('heldout_access') is not False:raise ValueError('development_cost_model_required')
        self.cost_model=copy.deepcopy(cost_model);self.wall_budget=wall_budget
        super().__init__(*args,**kwargs)
        prior.dump(self.out/'wall_protocol.json',dict(version='research196',model=self.cost_model,wall_budget=wall_budget,
            rule='Prospective cost estimates filter every arm. Actual completed-query costs determine reported common cuts; an overrun receives no below-budget evidence credit.',
            score='(3*semantic_pair_fraction + 2*unprotected_fraction + log1p(unseen_control_contexts))/predicted_acquisition_seconds',
            context_rule='Only bounded input control transitions/run-duration bins; no data payload, outputs, or oracle grades.',
            model_calls=0))

    def spent(self):
        return sum(r['cost'].get('r196_total_seconds',r['cost']['acquisition_wall_seconds']+r['cost'].get('planning_seconds',0)) for r in self.records)

    def rank(self,candidate,history=()):
        start=time.perf_counter();remaining=self.wall_budget-self.spent()
        pool=[q for q in self.pool if predict(self.cost_model,q)<=remaining]
        if not pool:raise BudgetExhausted('no_complete_query_predicted_to_fit_remaining_wall_budget')
        if self.strategy!='S3':
            original=self.pool;self.pool=pool
            try:result=super().rank(candidate,history)
            finally:self.pool=original
            result['planning_seconds']=time.perf_counter()-start;result['remaining_wall_budget']=remaining
            return result
        protected=prior.protected_obligations([*self.history,*history],sem.digest(candidate))
        candidates=[prior.semantic_candidate(candidate,self.config),*[prior.semantic_candidate(c,self.config) for c in self.config['candidate_pool'][1:]]]
        seen=set().union(*(control_contexts(q,self.config['output_signals']) for q in self.initial_queries+[r['query'] for r in self.records]))
        ranks=[]
        for q in pool:
            goal=sem.plan_goal(prior.planner_query(q,self.config),candidates,self.config['output_signals'],max_hypotheses=24)
            deficit=sum(o not in protected for o in q['obligations'])/max(1,len(q['obligations']))
            novel=control_contexts(q,self.config['output_signals'])-seen
            benefit=3*goal['semantic_discrimination']+2*deficit+math.log1p(len(novel))
            seconds=predict(self.cost_model,q)
            ranks.append(dict(query_id=q['id'],goal=goal,semantic_discrimination=goal['semantic_discrimination'],
                unprotected_fraction=deficit,novel_control_contexts=len(novel),estimated_acquisition_seconds=seconds,
                benefit_score=benefit,score=benefit/seconds,unqueried=q['id'] not in self.seen))
        allowed=[r for r in ranks if r['unqueried']] or ranks;best=max(r['score'] for r in allowed)
        selected=self.rng.choice([r for r in allowed if abs(r['score']-best)<1e-12])
        return dict(selected_query_id=selected['query_id'],reason='confirmed_history_and_input_diversity_per_development_fitted_wall_cost',ranked=ranks,
            candidate_sha256=sem.digest(candidate),candidate_differences=sem.semantic_differences(candidates),heldout_access=False,
            remaining_wall_budget=remaining,planning_seconds=time.perf_counter()-start)

    def acquire(self,*args,**kwargs):
        try:record=super().acquire(*args,**kwargs)
        except BudgetExhausted as exc:
            prior.dump(self.out/'budget_stop.json',dict(reason=str(exc),actual_seconds=self.spent(),budget=self.wall_budget))
            return None
        record['cost']['planning_seconds']=record['selection']['planning_seconds']
        record['cost']['r196_total_seconds']=record['cost']['acquisition_wall_seconds']+record['cost']['planning_seconds']-record['cost'].get('shared_lock_wait_seconds',0)
        record['cost']['predicted_acquisition_seconds']=predict(self.cost_model,record['query'])
        record['cost']['wall_budget_overrun']=self.spent()>self.wall_budget
        prior.dump(self.out/f"query{len(self.records)-1:02d}"/'acquisition.json',record)
        return record
