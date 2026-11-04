"""New seal-bound authorization required; at most 162 calls, no retries."""
import copy
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
import random
import threading
import research194_refinement_runner as common
import research197_cases as cases
from research197_refinement import runtime
from research197_search import session

class Backend:
    provenance='real_remote_model'
    def __init__(self,prepared,authorization,out):
        from research197_prepare import verify
        self.prepared=Path(prepared);self.protocol=verify(prepared);self.seal=common.file_hash(self.prepared/'protocol.json')
        auth=common.read(authorization)
        if not (auth.get('approved') is True and auth.get('version')=='research197' and auth.get('protocol_sha256')==self.seal and auth.get('endpoint')==common.ENDPOINT and auth.get('user_message_reference')):raise ValueError('new_seal_bound_authorization_required')
        self.limit=self.protocol['maximum_model_calls']
        if auth['maximum_model_calls']<self.limit or self.limit>162:raise ValueError('authorization_limit')
        self.root=Path(out).resolve();self.ledger=self.root/'ledger.json';self.entries={e['id']:e for e in self.protocol['entries'] if e['mode']=='ready'}
        if self.root.exists():raise ValueError('immutable_execution_no_restart')
        self.calls=[];self.lock=threading.RLock();common.dump(self.ledger,[])
    def __call__(self,request,folder):
        if common.file_hash(self.prepared/'protocol.json')!=self.seal:raise ValueError('protocol_changed')
        for p,h in self.protocol['source_bindings'].items():
            if common.file_hash(p)!=h:raise ValueError('source_changed:'+p)
        parts=Path(folder).resolve().relative_to(self.root).parts
        if len(parts)!=6 or parts[3]!='refinement' or parts[5]!='model_call':raise ValueError('unregistered_path')
        identity='/'.join(parts[:3]);entry=self.entries[identity];index=int(parts[4][5:])
        if not 1<=index<=entry['max_rounds']:raise ValueError('round_limit')
        if common.file_hash(entry['state'])!=entry['state_sha256']:raise ValueError('state_changed')
        if request!=common.read(Path(folder).parent/'request.preview.json'):raise ValueError('unarchived_request')
        if index==1 and common.r.digest(request)!=entry['request_sha256']:raise ValueError('first_request_changed')
        if request['model']!=self.protocol['model'] or request['max_tokens']!=2048 or request['seed']!=entry['seed']+(index-1)*1009 or request['temperature']!=.2:raise ValueError('model_parameters')
        current=common.read(Path(folder).parent/'current_measurement.json')
        for p,h in current['native_bindings'].items():
            if common.file_hash(p)!=h:raise ValueError('native_evidence_changed')
        with self.lock:
            if len(self.calls)>=self.limit or any(c['id']==identity and c['round']==index for c in self.calls):raise ValueError('duplicate_or_budget')
            row=dict(index=len(self.calls),id=identity,round=index,request_sha256=common.r.digest(request),status='reserved_no_retry')
            self.calls.append(row);common.dump(self.ledger,self.calls)
        import research69_deadline_transport as transport
        class Exact(transport.RemoteModel):
            def __init__(inner,*args):
                super().__init__(*args)
                path=inner.out/'remote_transport_config.json';metadata=common.read(path)
                metadata.update(max_output_tokens=2048,timeout_seconds=300,retries=0,parameter_source='Exact sealed R197 request and configured transport deadline')
                common.dump(path,metadata)
            def _payload(inner,*args):return copy.deepcopy(request)
            def save_decoded_output(inner,path,value,current,secret):
                common.dump(Path(path)/'model_edit.json',value);return value,'raw_json_no_semantic_rewrite'
        config=dict(remote_url=common.ENDPOINT,remote_model=request['model'],max_model_calls=1,
                    max_tokens=sum(len(m['content'].encode()) for m in request['messages'])+8192,max_wall_seconds=360,call_timeout=300,
                    options=dict(seed=request['seed'],temperature=.2,num_predict=2048))
        try:
            model=Exact(Path(folder).parent/'transport',config)
            result,value=model.call(folder,[],None,{},'research197_real_temporal_and_historical')
        except Exception as exc:
            with self.lock:row.update(status='transport_boundary_exception',error_type=type(exc).__name__);common.dump(self.ledger,self.calls)
            raise
        with self.lock:row.update(status=result['status'],model_calls=result.get('model_calls',1));common.dump(self.ledger,self.calls)
        return result,value

def run(prepared,authorization,out):
    backend=Backend(prepared,authorization,out);p=backend.protocol;out=Path(out).resolve()
    def worker(e):
        core,runner=runtime(e.get('arm'));adapter=cases.CaseAdapter(e['case_id']);state=common.read(e['state'])
        b=common.read(p['baselines'][e['case_id']]);folder=out/e['id']/'refinement'
        s=session(e['case_id'],e['search'],e['seed'],out/e['id']/'acquisition',baseline=b['measurement'],queries=b['queries'],cost_model=p['cost_models'][e['case_id']],max_queries=e['max_rounds'])
        if e['mode']=='blocked_unknown':
            common.dump(folder/'frozen.json',state['initial']);common.dump(folder/'terminal_measurement.json',state['first_measurement']);common.dump(folder/'trajectory_queries.json',state['queries'])
            result=dict(status='frozen',termination_reason='unknown_initial_evidence',actual_model_calls=0,accepted_rounds=0,provenance=backend.provenance,frozen_sha256=core.digest(state['initial']),causal_comparison_eligible=False)
        else:
            try:result=runner.run_trajectory(adapter,e['strategy'],e['seed'],folder,state['baseline'],b['queries'],s,backend,max_rounds=e['max_rounds'],prepared=Path(e['state']).parent)
            except Exception as exc:result=runner.freeze_interruption(folder,state,exc,e['search'])
        if (s.out/'budget_stop.json').exists():
            result['termination_reason']='registered_search_wall_budget_exhausted'
            result['budget_stop']=common.read(s.out/'budget_stop.json')
        result.update(case_id=e['case_id'],seed=e['seed'],strategy=e['strategy'],search_strategy=e['search'],registered_id=e['id'],arm=e.get('arm'),version='research197')
        common.dump(folder/'outcome.json',result);return result
    entries=copy.deepcopy(p['entries']);random.Random(19701).shuffle(entries);common.dump(out/'run_order.json',[e['id'] for e in entries]);done=[]
    with ThreadPoolExecutor(max_workers=2) as pool:
        for f in as_completed([pool.submit(worker,e) for e in entries]):
            r=f.result();done.append(r);common.dump(out/'progress.json',done);print('FROZEN',r['registered_id'],r.get('actual_model_calls'),flush=True)
    if len(done)!=len(entries) or not all(r['status']=='frozen' for r in done):raise ValueError('incomplete_population')
    common.dump(out/'outcome.json',dict(status='completed_all_versions_frozen',population=len(done),reserved_calls=len(backend.calls),maximum_calls=backend.limit,independent_inputs_constructed=False))

if __name__=='__main__':
    import argparse
    ap=argparse.ArgumentParser()
    for k in ('prepared','authorization','out'):ap.add_argument('--'+k,required=True,type=Path)
    a=ap.parse_args();run(a.prepared,a.authorization,a.out)
