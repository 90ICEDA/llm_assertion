"""Seal-bound 144-call maximum; existing transport, no automatic retry."""
import argparse
import copy
import random
import threading
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
from research194_refinement_runner import ROOT,read,dump,file_hash,ENDPOINT
from research197_execute import Backend as Transport
from research199_execution_core import configured,FixedSession
from research199_search import session
import research197_cases as cases

class Backend(Transport):
    def __init__(self,prepared,authorization,out):
        from research199_prepare import verify
        self.prepared=Path(prepared);self.protocol=verify(prepared);self.seal=file_hash(self.prepared/'protocol.json');a=read(authorization)
        expected=dict(version='research199',protocol_sha256=self.seal,endpoint=ENDPOINT,model=self.protocol['model'],maximum_model_calls=self.protocol['maximum_model_calls'],max_output_tokens=2048,timeout_seconds=300,workers=2,retries=0)
        if a.get('approved') is not True or not a.get('user_message_reference') or any(a.get(k)!=v for k,v in expected.items()):raise ValueError('new_exact_scope_authorization_required')
        self.limit=self.protocol['maximum_model_calls']
        if self.limit>144:raise ValueError('budget')
        self.root=Path(out).resolve();self.ledger=self.root/'ledger.json';self.entries={e['id']:e for e in self.protocol['entries'] if e['mode']=='ready'}
        if self.root.exists():raise ValueError('immutable_execution_no_retry')
        self.calls=[];self.lock=threading.RLock();dump(self.ledger,[])

def run(prepared,authorization,out):
    backend=Backend(prepared,authorization,out);p=backend.protocol;out=Path(out)
    old=read(ROOT/'deliverables/research197_refinement_prepare_20261104_r01/protocol.json')
    def worker(e):
        state=read(e['state']);adapter=cases.CaseAdapter(e['case_id']);core,runner,cache=configured(e['arm'],state,adapter)
        folder=out/e['id']/'refinement'
        if e['cohort']=='factorial':
            s=FixedSession(state,e['search'],cache,out/e['id']/'acquisition');public=state['queries']
        else:
            baseline=read(old['baselines'][e['case_id']]);public=baseline['queries']
            s=session(e['case_id'],e['search'],e['seed'],out/e['id']/'acquisition',baseline=baseline['measurement'],queries=public,cost_model=p['cost_models'][e['case_id']])
        if e['mode']=='blocked_unknown':
            dump(folder/'frozen.json',state['initial']);dump(folder/'terminal_measurement.json',state['first_measurement']);dump(folder/'trajectory_queries.json',state['queries'])
            result=dict(status='frozen',termination_reason='unknown_initial',actual_model_calls=0,causal_comparison_eligible=False,provenance=backend.provenance,frozen_sha256=core.digest(state['initial']))
        else:
            try:result=runner.run_trajectory(adapter,e['strategy'],e['seed'],folder,state['baseline'],public,s,backend,max_rounds=3,prepared=Path(e['state']).parent)
            except Exception as exc:result=runner.freeze_interruption(folder,state,exc,e['search'])
        if (s.out/'budget_stop.json').exists():result['termination_reason']='registered_search_budget_exhausted'
        result.update(id=e['id'],registered_id=e['id'],case_id=e['case_id'],seed=e['seed'],search_strategy=e['search'],strategy=e['strategy'],arm=e['arm'],cohort=e['cohort'],version='research199')
        dump(folder/'outcome.json',result);return result
    entries=copy.deepcopy(p['entries']);random.Random(19901).shuffle(entries);dump(out/'run_order.json',[e['id'] for e in entries]);done=[]
    with ThreadPoolExecutor(max_workers=2) as pool:
        for f in as_completed([pool.submit(worker,e) for e in entries]):
            result=f.result();done.append(result);dump(out/'progress.json',done);print('FROZEN',result['id'],result.get('actual_model_calls'),flush=True)
    if len(done)!=48 or not all(r['status']=='frozen' for r in done):raise ValueError('incomplete_population')
    dump(out/'outcome.json',dict(status='completed_all_versions_frozen',population=48,reserved_calls=len(backend.calls),maximum_calls=backend.limit,independent_inputs_constructed=False))

if __name__=='__main__':
    p=argparse.ArgumentParser()
    for k in ('prepared','authorization','out'):p.add_argument('--'+k,type=Path,required=True)
    a=p.parse_args();run(a.prepared,a.authorization,a.out)
