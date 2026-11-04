"""Reuse active selection with interface-only context and passive launch signals."""
import copy
import math
from research195_refinement_adapter import clone
import research197_cases as cases

class SearchCases:
    @staticmethod
    def get_case(cid):
        cfg=cases.get_case(cid)
        if cid==cases.IDS[0]:cfg['output_signals']={k:v for k,v in cfg['output_signals'].items() if k!='launch'}
        return cfg
    @staticmethod
    def query_pool(cid,split='development',seed=19711):
        pool=cases.query_pool(cid,split,seed)
        if cid==cases.IDS[0]:
            for q in pool:
                prior=0;rows=[]
                for r in q['rows']:
                    rows.append(dict(r,launch=int(r['valid'] and not prior)));prior=r['valid'] if r['rst_n'] else 0
                q['planner_rows']=rows
        return pool
    validate=staticmethod(cases.validate)
    evaluate=staticmethod(cases.evaluate)

def contexts(query,output_signals=()):
    result=set();previous=None;run=0
    for r in query.get('planner_rows',query['rows']):
        state=tuple((k,int(r[k])) for k in ('rst_n','clear','en','load','down','valid','ready','launch','inp_req','out_req','pop') if k in r and k not in output_signals)
        run=run+1 if state==previous else 1
        result.add((previous,state,min(4,int(math.log2(run)))));previous=state
    return result

def session(cid,strategy,seed,out,*,baseline,queries,cost_model,max_queries=3):
    module=clone('research196_active_search');module.control_contexts=contexts
    return module.Session(cid,strategy,seed,out,initial_queries=queries,initial_evidence=baseline['evidence'],
                          cost_model=cost_model,wall_budget=180,max_queries=max_queries,adapter=SearchCases)
