"""Optional, cost-accounted active temporal evidence acquisition for R194.

Public input schedules and candidate predicates are the only planning inputs.
Counterfactual output assignments provide semantic query goals, never oracle
labels. Each submitted query is independently executed on correct and faulty
RTL. Candidate-pool native markers are projected back to the current candidate.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
from pathlib import Path
import random
import time

import research194_active_semantics as sem

VERSION='r194-temporal-semantics-v1'
STRATEGIES=('S0','S1','S2','S3')


def dump(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')


def semantic_candidate(candidate,config):
    return [dict(a,disable=config['disable']) for a in candidate]


def planner_query(query,config):
    """UART helpers exactly mirror the public, input-only passive TB sampler."""
    result=copy.deepcopy(query)
    if config['id']=='uart':
        active=age=data=0;rows=[]
        for row in query['rows']:
            rows.append(dict(row,txn_active=active,txn_age=age,latched_data=data))
            if not row['rst_n'] or not row['tx_enable']:active=age=data=0
            elif row['wr']:active=1;age=0;data=row['wr_data']
            elif active:age+=1
        result['planner_rows']=rows
    return result


def combine_candidates(candidates):
    combined=[];mapping={}
    for ci,candidate in enumerate(candidates):
        for ai,a in enumerate(candidate):
            label=f'c{ci}_a{ai}';combined.append(dict(a,label=label))
            mapping[label]=dict(candidate=ci,original_label=a['label'])
    return combined,mapping


def project_measurement(measurement,candidate,mapping,index=0):
    """Recompute metrics solely from this candidate's obligation-bound markers."""
    targets=set();detected=set();triggered=set();transactions=set();covered=set();fps=[];evidence=[]
    for raw in measurement['evidence']:
        ev=copy.deepcopy(raw);observations=[]
        for item in raw.get('assertions',[]):
            key=item.get('assertion');bound=mapping.get(key)
            if bound and bound['candidate']==index:
                observations.append(dict(item,assertion=bound['original_label']))
        ev['assertions']=observations
        ev['candidate_sha256']=sem.digest(candidate)
        ev['oracle_status']=ev['status']
        ev['candidate_predictions']=[dict(a,independent_facts={
            'required_trigger_missing':True} if ev['status']=='confirmed' and ev['label']=='violation' and ev.get('counted_target',False) and not a['trigger'] else {}) for a in observations]
        evidence.append(ev)
        if ev['status']!='confirmed':continue
        eid=ev.get('evidence_id',ev['id'])
        if ev['label']=='violation' and ev.get('counted_target',False):
            targets.add(eid);transactions.add(ev['transaction_id'])
            if any(a['trigger'] for a in observations):triggered.add(eid)
            if any(a['failure'] for a in observations):detected.add(eid);covered.add(ev['obligation'])
        elif ev['label']=='legal' and any(a['failure'] for a in observations):fps.append(ev)
    result={k:copy.deepcopy(v) for k,v in measurement.items() if k not in ('evidence','false_positives','executions')}
    critical_unknown=[]
    for raw in measurement.get('critical_unknown',[]):
        item=copy.deepcopy(raw)
        if item.get('assertion') in mapping:
            bound=mapping[item['assertion']]
            if bound['candidate']!=index:continue
            item['assertion']=bound['original_label']
        critical_unknown.append(item)
    result.update(candidate_sha256=sem.digest(candidate),targets=sorted(targets),detected_ids=sorted(detected),
        triggered_ids=sorted(triggered),target_transaction_ids=sorted(transactions),covered_obligations=sorted(covered),
        evidence=evidence,false_positives=fps,executions=measurement.get('executions',[]),critical_unknown=critical_unknown,
        reference_complete=not critical_unknown)
    return result


def gaps(evidence):
    result={}
    for ev in evidence:
        if ev.get('status')!='confirmed':continue
        observations=ev.get('assertions',[])
        kind='FN' if ev['label']=='violation' and ev.get('counted_target',False) and not any(a['failure'] for a in observations) else 'FP' if ev['label']=='legal' and any(a['failure'] for a in observations) else None
        if kind:
            key=kind+':'+ev.get('evidence_id',ev['id'])
            result[key]=dict(gap_id=key,evidence_id=ev.get('evidence_id',ev['id']),kind=kind,obligation=ev['obligation'],parent_bug=ev['parent_bug'],transaction_id=ev['transaction_id'])
    return result


def protected_obligations(history,candidate_hash):
    # Only outcomes of this exact candidate can establish observed protection.
    by_ob={}
    for ev in history:
        if ev.get('status')!='confirmed' or ev.get('candidate_sha256')!=candidate_hash:continue
        entry=by_ob.setdefault(ev['obligation'],dict(targets=0,misses=0,fps=0))
        if ev['label']=='violation' and ev.get('counted_target',False):
            entry['targets']+=1;entry['misses']+=int(not any(a['failure'] for a in ev.get('assertions',[])))
        elif ev['label']=='legal':entry['fps']+=int(any(a['failure'] for a in ev.get('assertions',[])))
    return {o for o,v in by_ob.items() if v['targets'] and not v['misses'] and not v['fps']}


class Session:
    """One paired trajectory, fixed seed and exact submitted-query budget.

    `initial_queries`/`initial_evidence` are the shared public baseline, whose
    physical cost belongs to the caller's baseline ledger. No native execution
    or held-out query is performed by construction or planning.
    """
    def __init__(self,case_id,strategy,seed,out,*,initial_queries=(),initial_evidence=(),max_queries=3,adapter=None):
        if strategy not in STRATEGIES:raise ValueError('strategy')
        if adapter is None:
            import research194_cases as adapter
        self.adapter=adapter;self.case_id=case_id;self.strategy=strategy;self.seed=seed
        self.config=adapter.get_case(case_id);self.pool=adapter.query_pool(case_id,split='development',seed=seed)
        self.out=Path(out);self.out.mkdir(parents=True,exist_ok=True)
        self.rng=random.Random(seed);self.max_queries=max_queries;self.records=[]
        self.initial_queries=copy.deepcopy(list(initial_queries));self.history=copy.deepcopy(list(initial_evidence))
        self.seen={q['id'] for q in initial_queries};self.observed_xor={};self.counts={q['id']:0 for q in self.pool}
        for q in initial_queries:self.counts[q['id']]=self.counts.get(q['id'],0)+1
        self.baseline_gap_ids=set(gaps(self.history));self.discovered={}
        self.task_id=f'{self.config["id"]}/seed{seed}/{strategy}'
        protocol=dict(version=VERSION,task_id=self.task_id,case_id=case_id,strategy=strategy,seed=seed,
            max_submitted_queries=max_queries,max_native_jobs=2*max_queries,baseline_queries=[q['id'] for q in initial_queries],
            initial_candidate_sha256=sem.digest(self.config['initial']),candidate_pool=self.config['candidate_pool'],
            query_pool=self.pool,query_pool_sha256=sem.digest(self.pool),model_calls=0,heldout_access=False,
            strategies=dict(S0='uniform sampling with replacement',S1='observed native XOR exploitation with probability .65, otherwise uniform',
                S2='least observed obligation schedule then least queried, seeded tie breaks',
                S3='unqueried schedules first; (3*semantic discrimination + 2*unprotected fraction + novelty)/estimated native cost; seeded ties'),
            count_units=['native executions','unique evidence IDs','parent Bugs','transaction IDs'],
            semantics='hypothetical outputs are planning only; actual native markers validate predictions; independent oracle assigns labels',
            source_sha256={Path(__file__).name:hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),Path(sem.__file__).name:hashlib.sha256(Path(sem.__file__).read_bytes()).hexdigest()})
        protocol_path=self.out/'protocol.json'
        if protocol_path.exists():raise ValueError('existing acquisition session')
        dump(protocol_path,protocol)

    def rank(self,candidate,history=()):
        protected=protected_obligations([*self.history,*history],sem.digest(candidate))
        candidates=[semantic_candidate(candidate,self.config)]
        candidates.extend(semantic_candidate(c,self.config) for c in self.config['candidate_pool'][1:])
        ranks=[]
        for q in self.pool:
            goal=sem.plan_goal(planner_query(q,self.config),candidates,self.config['output_signals']) if self.strategy=='S3' else None
            deficit=sum(o not in protected for o in q['obligations'])/max(1,len(q['obligations']))
            novelty=1/(1+self.counts[q['id']]);cost=max(1,float(q.get('estimated_cost',2)))
            score=(3*goal['semantic_discrimination']+2*deficit+novelty)/cost if goal else 0
            obligation_seen=sum(sum(o in seen.get('obligations',[]) for seen in self.initial_queries+[r['query'] for r in self.records]) for o in q['obligations'])
            ranks.append(dict(query_id=q['id'],semantic_discrimination=goal['semantic_discrimination'] if goal else None,
                unprotected_fraction=deficit,protected_obligations=sorted(protected),novelty=novelty,estimated_native_cost=cost,
                score=score,unqueried=q['id'] not in self.seen,obligation_exposure_count=obligation_seen,query_count=self.counts[q['id']],goal=goal))
        if self.strategy=='S0':selected=self.rng.choice(ranks);reason='uniform'
        elif self.strategy=='S1':
            positive=[r for r in ranks if self.observed_xor.get(r['query_id'],False)]
            selected=self.rng.choice(positive if positive and self.rng.random()<.65 else ranks);reason='prior_actual_native_xor_or_uniform'
        elif self.strategy=='S2':
            best=min((r['obligation_exposure_count'],r['query_count']) for r in ranks)
            selected=self.rng.choice([r for r in ranks if (r['obligation_exposure_count'],r['query_count'])==best]);reason='contract_exposure_then_query_novelty'
        else:
            allowed=[r for r in ranks if r['unqueried']] or ranks
            best=max(r['score'] for r in allowed)
            selected=self.rng.choice([r for r in allowed if abs(r['score']-best)<1e-12]);reason='semantic_goal_unprotected_obligation_novelty_per_cost'
        return dict(selected_query_id=selected['query_id'],reason=reason,ranked=ranks,candidate_sha256=sem.digest(candidate),
            candidate_differences=sem.semantic_differences(candidates),heldout_access=False)

    def reuse_acquisition(self,record,current_candidate):
        """Import a previously paid first acquisition without exposing later ones."""
        if self.records:raise ValueError('reuse only first acquisition')
        if record['candidate_sha256']!=sem.digest(current_candidate):raise ValueError('candidate hash mismatch')
        if record['case_id']!=self.config['id'] or record['seed']!=self.seed or record['strategy']!=self.strategy:raise ValueError('trajectory mismatch')
        selection=self.rank(current_candidate)
        if selection['selected_query_id']!=record['query']['id']:raise ValueError('selection replay mismatch')
        known=next(q for q in self.pool if q['id']==record['query']['id'])
        if sem.digest(known)!=sem.digest(record['query']):raise ValueError('query changed')
        reused=copy.deepcopy(record);old_cost=copy.deepcopy(record['cost'])
        reused['reuse']=dict(source_task=record['task_id'],source_acquisition_index=record['round'],source_record_sha256=sem.digest(record),
            physical_native_jobs=0,logical_native_jobs=2,original_cost=old_cost,reason='identical first candidate and public query already physically evaluated')
        reused['cost']=dict(old_cost,native_compile_attempts=0,native_execution_attempts=0,native_seconds=0,wall_seconds=0,
            reused_native_execution_attempts=old_cost.get('native_execution_attempts',0),logical_native_jobs=2)
        self.records.append(reused);self.seen.add(known['id']);self.counts[known['id']]+=1;self.history.extend(reused['evidence'])
        self.observed_xor[known['id']]=any(v['actual_native_xor'] for v in record['native_prediction_validation'])
        self.discovered.update({k:v for k,v in gaps(reused['evidence']).items() if k not in self.baseline_gap_ids})
        dump(self.out/'query00'/'acquisition.json',reused)
        return reused

    def acquire(self,current_candidate=None,round=None,seed=None,strategy=None,history=(),**kwargs):
        if any((p/'STOP').exists() for p in [self.out,*list(self.out.parents)[:5]]):raise RuntimeError('STOP requested before next native query')
        candidate=current_candidate if current_candidate is not None else kwargs.get('candidate')
        if candidate is None:raise ValueError('current_candidate required')
        if seed is not None and seed!=self.seed:raise ValueError('seed mismatch')
        if strategy is not None and strategy!=self.strategy:raise ValueError('strategy mismatch')
        if len(self.records)>=self.max_queries:raise ValueError('submitted query budget exhausted')
        candidate=self.adapter.validate(self.case_id,candidate)
        selection=self.rank(candidate,history);query=next(q for q in self.pool if q['id']==selection['selected_query_id'])
        index=len(self.records);folder=self.out/f'query{index:02d}';folder.mkdir(exist_ok=False)
        dump(folder/'selection_before_execution.json',selection)
        candidates=[candidate,*self.config['candidate_pool'][1:]]
        combined,mapping=combine_candidates(candidates)
        dump(folder/'candidate_bindings.json',dict(candidate_sha256=sem.digest(candidate),combined=combined,mapping=mapping))
        begin=time.monotonic()
        raw=self.adapter.evaluate(self.case_id,combined,folder/'native',queries=[query],split='development',fault='primary')
        projected=project_measurement(raw,candidate,mapping)
        verification=[];native_xor=False
        for job in raw.get('executions',[]):
            result=sem.verify_native_predictions(semantic_candidate(combined,self.config),job['trace'],job['result'])
            predicted=result['prediction']['assertions'];by_pool=[]
            for ci in range(len(candidates)):
                labels={key for key,bound in mapping.items() if bound['candidate']==ci}
                by_pool.append(sorted({cycle for item in predicted if item['label'] in labels for cycle in item['failures']}))
            actual_sets=[]
            for ci in range(len(candidates)):
                actual_sets.append(sorted({m['detail'] for m in job['result'].get('failures',[]) if mapping.get(m['id'],{}).get('candidate')==ci}))
            healthy=job['result'].get('compile_status')=='passed' and job['result'].get('execution_status')=='completed'
            xor=healthy and any(a!=b for a in actual_sets for b in actual_sets)
            native_xor=native_xor or xor
            verification.append(dict(variant=job['variant'],query_id=query['id'],semantic_validation=result,
                actual_native_candidate_failure_signatures=actual_sets,actual_native_xor=xor,predicted_failure_cycles=by_pool))
        evidence=projected['evidence']
        for ev in evidence:
            ev.update(task_id=self.task_id,acquisition_index=index,case_id=self.config['id'])
        current_gaps=gaps(evidence);new={k:v for k,v in current_gaps.items() if k not in self.baseline_gap_ids and k not in self.discovered}
        self.discovered.update(new);self.seen.add(query['id']);self.counts[query['id']]+=1;self.history.extend(evidence)
        self.observed_xor[query['id']]=native_xor
        cost=dict(raw['cost'],submitted_queries=1,submitted_native_jobs=2,planning_seconds=sum(r['goal']['planning_seconds'] for r in selection['ranked'] if r['goal']),
            acquisition_wall_seconds=time.monotonic()-begin,model_calls=0)
        record=dict(task_id=self.task_id,case_id=self.config['id'],candidate_sha256=sem.digest(candidate),strategy=self.strategy,seed=self.seed,
            round=round if round is not None else index,query=query,queries=[query],evidence=evidence,cost=cost,
            measurement=projected,selection=selection,native_prediction_validation=verification,
            gap_ids=sorted(current_gaps),new_gap_ids=sorted(new),cumulative_new_gap_ids=sorted(self.discovered),
            gap_records=list(current_gaps.values()),evidence_ids=sorted({e['evidence_id'] for e in evidence}),
            heldout_access=False)
        self.records.append(record);dump(folder/'acquisition.json',record)
        dump(self.out/'summary.json',dict(task_id=self.task_id,complete=len(self.records)==self.max_queries,
            submitted_queries=len(self.records),submitted_native_jobs=2*len(self.records),
            native_execution_attempts=sum(r['cost'].get('native_execution_attempts',0) for r in self.records),
            model_calls=0,new_gap_ids=sorted(self.discovered),records=[str(self.out/f'query{i:02d}'/'acquisition.json') for i in range(len(self.records))]))
        return record


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--case',required=True);ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--strategy',choices=STRATEGIES,default='S3');ap.add_argument('--seed',type=int,default=19407);ap.add_argument('--queries',type=int,default=3)
    ap.add_argument('--prepare-only',action='store_true');args=ap.parse_args()
    session=Session(args.case,args.strategy,args.seed,args.out,max_queries=args.queries)
    if args.prepare_only:
        dump(args.out/'prepared_selection.json',session.rank(session.config['initial']));return
    for i in range(args.queries):session.acquire(session.config['initial'],round=i)
    print(json.dumps(dict(out=str(args.out),submitted_queries=len(session.records),model_calls=0)))


if __name__=='__main__':main()
