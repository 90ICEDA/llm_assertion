"""New-authorization-only R195 bounded execution. No retries or implicit resume."""
import argparse
import copy
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
import threading
from research195_refinement_adapter import runtime
from research195_refinement_fixtures import FixtureAdapter
from research195_refinement_prepare import verify
import research194_refinement_runner as common


class AuthorizedBackend:
    provenance='real_remote_model'
    def __init__(self,prepared,authorization,ledger):
        self.prepared=Path(prepared);self.protocol,self.seal=verify(prepared)
        auth=common.read(authorization)
        if (auth.get('version')!='research195' or auth.get('protocol_sha256')!=self.seal or auth.get('endpoint')!=common.ENDPOINT
            or auth.get('approved') is not True or not auth.get('user_message_reference')):
            raise ValueError('new_R195_explicit_seal_bound_authorization_required')
        self.limit=min(24,self.protocol['maximum_model_calls'],auth['maximum_model_calls'])
        self.ledger=Path(ledger)
        if self.ledger.exists():raise ValueError('ledger_exists_no_resume_or_retry')
        self.calls=[];self.lock=threading.RLock()
        self.allowed={e['request_sha256']:e['id'] for e in self.protocol['entries'] if e['mode']=='ready'}
        common.dump(self.ledger,self.calls)
    def __call__(self,request,folder):
        verify(self.prepared)
        from research194_refinement import digest
        request_hash=digest(request)
        if request_hash not in self.allowed:raise ValueError('request_not_in_authorized_exact_seal')
        with self.lock:
            if len(self.calls)>=self.limit or any(c['request_sha256']==request_hash for c in self.calls):raise ValueError('budget_or_duplicate_request')
            row=dict(index=len(self.calls),id=self.allowed[request_hash],request_sha256=request_hash,status='reserved_no_retry',folder=str(folder))
            self.calls.append(row);common.dump(self.ledger,self.calls)
        import research69_deadline_transport as transport
        class Exact(transport.RemoteModel):
            def _payload(inner,*args):return copy.deepcopy(request)
            def save_decoded_output(inner,path,value,current,secret):
                common.dump(Path(path)/'model_edit.json',value);return value,'raw_json_no_semantic_rewrite'
        config=dict(remote_url=common.ENDPOINT,remote_model=request['model'],max_model_calls=1,
            max_tokens=sum(len(m['content'].encode()) for m in request['messages'])+8192,
            max_wall_seconds=360,call_timeout=300,options=dict(seed=request['seed'],temperature=.2,num_predict=2048))
        try:
            model=Exact(Path(folder).parent/'transport',config)
            metadata=Path(folder).parent/'transport/remote_transport_config.json'
            meta=common.read(metadata);meta.update(timeout_seconds=300,max_output_tokens=2048,timeout_metadata_version='research195_actual_deadline')
            common.dump(metadata,meta)
            result,value=model.call(folder,[],None,{},'research195_single_round_typed_refinement')
        except Exception as exc:
            with self.lock:row.update(status='transport_boundary_exception',error_type=type(exc).__name__);common.dump(self.ledger,self.calls)
            raise
        with self.lock:row.update(status=result['status'],model_calls=result.get('model_calls',1));common.dump(self.ledger,self.calls)
        return result,value


def run(prepared,authorization,out):
    out=Path(out)
    if out.exists():raise ValueError('immutable_execution_destination_exists')
    backend=AuthorizedBackend(prepared,authorization,out/'ledger.json')
    def worker(entry):
        core,runner=runtime(entry['arm']);adapter=FixtureAdapter(entry['fixture']);state=common.read(entry['state'])
        folder=out/entry['id']/'refinement'
        class Session:
            strategy='fixed_development_evidence'
            def reuse_acquisition(self,record,candidate):
                if core.digest(candidate)!=record['measurement']['candidate_sha256']:raise ValueError('replay_candidate_mismatch')
                return copy.deepcopy(record)
        if entry['mode']=='blocked_unknown':
            common.dump(folder/'frozen.json',state['initial']);common.dump(folder/'terminal_measurement.json',state['first_measurement'])
            common.dump(folder/'trajectory_queries.json',state['queries'])
            result=dict(status='frozen',termination_reason='unknown_initial_evidence',actual_model_calls=0,accepted_rounds=0,
                provenance='real_remote_model',causal_comparison_eligible=False,frozen_sha256=core.digest(state['initial']))
        else:
            try:result=runner.run_trajectory(adapter,'R3',entry['seed'],folder,state['baseline'],state['queries'],Session(),backend,max_rounds=1,prepared=Path(entry['state']).parent)
            except Exception as exc:result=runner.freeze_interruption(folder,state,exc,Session.strategy)
        result.update(arm=entry['arm'],fixture=entry['fixture'],seed=entry['seed'],case_id=entry['case_id'],registered_id=entry['id'],version='research195')
        rounds=common.read(folder/'rounds.json') if (folder/'rounds.json').is_file() else []
        last=rounds[-1] if rounds else {}
        result['classification']=('not_attempted_unknown_initial' if entry['mode']=='blocked_unknown' else
            'accepted' if last.get('status')=='accepted' else
            'interface_failure' if last.get('status')=='interface_rejected' else
            'no_change' if last.get('status')=='no_change' else
            'native_unknown' if last.get('decision',{}).get('critical_unknown') else
            'native_rejected' if last.get('status')=='rejected' else
            'generation_or_execution_failure')
        common.dump(folder/'outcome.json',result);return result
    outcomes=[]
    with ThreadPoolExecutor(max_workers=2) as pool:
        for future in as_completed([pool.submit(worker,e) for e in backend.protocol['entries']]):
            outcomes.append(future.result());common.dump(out/'progress.json',outcomes)
    if len(outcomes)!=24 or not all(o['status']=='frozen' for o in outcomes):raise ValueError('incomplete_registered_population')
    common.dump(out/'outcome.json',dict(status='completed_all_versions_frozen',population=24,
        actual_reserved_calls=len(backend.calls),maximum_calls=backend.limit,protocol_sha256=backend.seal,
        independent_inputs_constructed=False,new_independent_acceptance='pending_after_all_frozen'))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prepared',type=Path,required=True)
    p.add_argument('--authorization',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    args=p.parse_args();run(args.prepared,args.authorization,args.out)
