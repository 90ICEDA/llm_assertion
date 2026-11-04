"""Automatic-controller experiment. Reuse transport and native runner, no retries."""
import argparse
import copy
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
import random
import threading
from research194_refinement_runner import read,dump,file_hash,ENDPOINT
from research197_execute import Backend as SealedTransport
from research198_refinement import runtime
import research197_cases as cases

class Backend(SealedTransport):
    # Inherited dispatch validates state, source seals, exact first requests,
    # archive-before-send, parameters, native bindings, unique calls and budget.
    # Its transport diagnostic tag retains R197; actual identity is the new
    # sealed ledger/request and experiment.version=research198.
    def __init__(self,prepared,authorization,out):
        from research198_prepare import verify
        self.prepared=Path(prepared);self.protocol=verify(prepared);self.seal=file_hash(self.prepared/'protocol.json')
        auth=read(authorization)
        expected=dict(version='research198',protocol_sha256=self.seal,endpoint=ENDPOINT,model=self.protocol['model'],
            maximum_model_calls=self.protocol['maximum_model_calls'],max_output_tokens=2048,timeout_seconds=300,workers=2,retries=0)
        if auth.get('approved') is not True or not auth.get('user_message_reference') or any(auth.get(k)!=v for k,v in expected.items()):
            raise ValueError('new_exact_scope_authorization_required')
        self.limit=self.protocol['maximum_model_calls']
        if self.limit>180:raise ValueError('maximum_calls')
        self.root=Path(out).resolve();self.ledger=self.root/'ledger.json'
        self.entries={e['id']:e for e in self.protocol['entries'] if e['mode']=='ready'}
        if self.root.exists():raise ValueError('immutable_execution_no_restart')
        self.calls=[];self.lock=threading.RLock();dump(self.ledger,[])

class FixedSession:
    """Reuses current same-candidate measurements. No new search or oracle calls."""
    def __init__(self,state,strategy,cache,out):
        self.state=state;self.strategy=strategy;self.cache=cache;self.out=Path(out)
    def reuse_acquisition(self,record,candidate):
        result=copy.deepcopy(record)
        result['historical_acquisition_cost']=result.get('cost',{})
        result['cost']=dict(native_compile_attempts=0,native_execution_attempts=0,native_seconds=0,wall_seconds=0)
        result['fixed_evidence_replay']=True
        return result
    def acquire(self,candidate,index,history=()):
        m=copy.deepcopy(self.cache[cases.digest(candidate)])
        return dict(queries=[],measurement=m,cost=dict(native_compile_attempts=0,native_execution_attempts=0,native_seconds=0,wall_seconds=0),
            fixed_evidence_replay=True,round=index,task_id='research198/fixed_development_replay',
            provenance='Already measured retained candidate on the identical registered query union; no new search acquisition.')

def fixed_runtime(policy,state,adapter):
    core,runner=runtime(policy);cache={core.digest(state['initial']):state['first_measurement']}
    evaluate=adapter.evaluate
    def measured(candidate,folder,queries):
        value=evaluate(candidate,folder,queries);cache[core.digest(candidate)]=value;return value
    adapter.evaluate=measured
    def merge(candidate,measurements):
        a,b=measurements
        if (a['candidate_sha256']!=core.digest(candidate) or b['candidate_sha256']!=core.digest(candidate)
            or core.digest(a['evidence'])!=core.digest(b['evidence'])):raise ValueError('fixed_history_mismatch')
        result=copy.deepcopy(a)
        result['cost']=dict(native_compile_attempts=0,native_execution_attempts=0,native_seconds=0,wall_seconds=0)
        result['history_composition']=dict(physical_native_jobs=0,reason='Identical complete development history reused without duplication.')
        return result
    runner.merge_measurements=merge
    return core,runner,cache

def run(prepared,authorization,out):
    backend=Backend(prepared,authorization,out);p=backend.protocol;out=Path(out).resolve()
    def worker(e):
        state=read(e['state']);adapter=cases.CaseAdapter(e['case_id'])
        core,runner,cache=fixed_runtime(e['policy'],state,adapter)
        session=FixedSession(state,e['search'],cache,out/e['id']/'acquisition');folder=out/e['id']/'refinement'
        if e['mode']!='ready':raise ValueError('registered_unknown_requires_explicit_freeze')
        try:
            result=runner.run_trajectory(adapter,e['strategy'],e['seed'],folder,state['baseline'],state['queries'],session,backend,
                max_rounds=5,prepared=Path(e['state']).parent)
        except Exception as exc:
            result=runner.freeze_interruption(folder,state,exc,e['search'])
        result.update(id=e['id'],registered_id=e['id'],case_id=e['case_id'],seed=e['seed'],search_strategy=e['search'],strategy=e['strategy'],policy=e['policy'],version='research198')
        dump(folder/'outcome.json',result);return result
    entries=copy.deepcopy(p['entries']);random.Random(19801).shuffle(entries);dump(out/'run_order.json',[e['id'] for e in entries]);done=[]
    with ThreadPoolExecutor(max_workers=2) as pool:
        for f in as_completed([pool.submit(worker,e) for e in entries]):
            r=f.result();done.append(r);dump(out/'progress.json',done);print('FROZEN',r['registered_id'],r.get('actual_model_calls'),flush=True)
    if len(done)!=36 or not all(r['status']=='frozen' for r in done):raise ValueError('incomplete_population')
    dump(out/'outcome.json',dict(status='completed_all_versions_frozen',population=36,reserved_calls=len(backend.calls),maximum_calls=backend.limit,
        independent_inputs_constructed=False,search_cost='Archived R197 acquisition: shared source, zero new physical searches; report historical logical cost separately.'))

if __name__=='__main__':
    p=argparse.ArgumentParser()
    for k in ('prepared','authorization','out'):p.add_argument('--'+k,type=Path,required=True)
    a=p.parse_args();run(a.prepared,a.authorization,a.out)
