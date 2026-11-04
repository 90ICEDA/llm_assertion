"""Bounded R196 execution; fresh authorization, no retry and no implicit resume."""
import argparse
import copy
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
import random
import threading
import research194_refinement_runner as common
from research196_campaign import adapter_runtime,verify
from research196_active_search import Session,BudgetExhausted
import research196_cases as cases


class AuthorizedBackend:
    provenance='real_remote_model'
    def __init__(self,prepared,authorization,ledger):
        self.prepared=Path(prepared);self.protocol,self.seal=verify(prepared)
        auth=common.read(authorization)
        if (auth.get('version')!='research196' or auth.get('protocol_sha256')!=self.seal or auth.get('endpoint')!=common.ENDPOINT
            or auth.get('approved') is not True or not auth.get('user_message_reference')):
            raise ValueError('new_R196_explicit_seal_bound_authorization_required')
        self.limit=min(128,self.protocol['maximum_model_calls'],auth['maximum_model_calls'])
        if self.limit<self.protocol['maximum_model_calls']:raise ValueError('authorization_smaller_than_sealed_campaign')
        self.ledger=Path(ledger).resolve();self.root=self.ledger.parent
        if self.ledger.exists():raise ValueError('ledger_exists_no_resume_or_retry')
        self.entries={e['id']:e for e in self.protocol['entries'] if e['mode']=='ready'}
        self.calls=[];self.lock=threading.RLock();common.dump(self.ledger,self.calls)

    def __call__(self,request,folder):
        # Full population verification runs at construction. Recheck the sealed
        # protocol/code and this trajectory at each dispatch, without repeatedly
        # parsing all other large native histories for every model call.
        if common.file_hash(self.prepared/'protocol.json')!=self.seal:raise ValueError('protocol_changed')
        for path,h in self.protocol['source_bindings'].items():
            if common.file_hash(path)!=h:raise ValueError('sealed_source_changed:'+path)
        folder=Path(folder).resolve()
        parts=folder.relative_to(self.root).parts
        if len(parts)!=6 or parts[3]!='refinement' or parts[4] not in ('round01','round02') or parts[5]!='model_call':raise ValueError('unregistered_call_path')
        identity='/'.join(parts[:3]);entry=self.entries[identity];round_index=int(parts[4][-2:]);h=common.r.digest(request)
        if common.file_hash(entry['state'])!=entry['state_sha256']:raise ValueError('trajectory_state_changed')
        current=common.read(folder.parent/'current_measurement.json')
        for path,value in current['native_bindings'].items():
            if common.file_hash(path)!=value:raise ValueError('development_native_evidence_changed')
        if request!=common.read(folder.parent/'request.preview.json'):raise ValueError('request_not_saved_before_dispatch')
        if round_index==1 and h!=entry['request_sha256']:raise ValueError('first_request_changed')
        if request.get('model')!='deepseek/deepseek-v3-0324' or request.get('max_tokens')!=2048 or request.get('seed')!=entry['seed']+(round_index-1)*1009:raise ValueError('sealed_model_configuration_changed')
        with self.lock:
            if len(self.calls)>=self.limit or any(c['id']==identity and c['round']==round_index for c in self.calls):raise ValueError('budget_or_duplicate_round')
            row=dict(index=len(self.calls),id=identity,round=round_index,request_sha256=h,status='reserved_no_retry',folder=str(folder))
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
            model=Exact(folder.parent/'transport',config)
            meta_path=folder.parent/'transport/remote_transport_config.json';meta=common.read(meta_path)
            meta.update(timeout_seconds=300,max_output_tokens=2048,timeout_metadata_version='research196_actual_deadline');common.dump(meta_path,meta)
            result,value=model.call(folder,[],None,{},'research196_paired_latest_mechanisms')
        except Exception as exc:
            with self.lock:row.update(status='transport_boundary_exception',error_type=type(exc).__name__);common.dump(self.ledger,self.calls)
            raise
        with self.lock:row.update(status=result['status'],model_calls=result.get('model_calls',1));common.dump(self.ledger,self.calls)
        return result,value


class BoundedSession(Session):
    def acquire(self,*args,**kwargs):
        record=super().acquire(*args,**kwargs)
        if record is None:raise BudgetExhausted('registered_actual_wall_budget_stop')
        return record


def run(prepared,authorization,out):
    out=Path(out).resolve()
    if out.exists():raise ValueError('immutable_execution_destination_exists')
    backend=AuthorizedBackend(prepared,authorization,out/'ledger.json');p=backend.protocol
    paid=common.read(Path(p['acquisitions'])/'protocol.json')
    def worker(e):
        core,runner=adapter_runtime();adapter=runner.CaseAdapter(e['case_id']);state=common.read(e['state'])
        folder=out/e['id']/'refinement';base=common.read(paid['baselines'][e['case_id']])
        session=BoundedSession(e['case_id'],e['search'],e['seed'],out/e['id']/'acquisition',initial_queries=base['queries'],
            initial_evidence=base['measurement']['evidence'],max_queries=2,adapter=cases,cost_model=p['cost_models'][e['case_id']],wall_budget=120)
        if e['mode']=='blocked_unknown':
            common.dump(folder/'frozen.json',state['initial']);common.dump(folder/'terminal_measurement.json',state['first_measurement']);common.dump(folder/'trajectory_queries.json',state['queries'])
            result=dict(status='frozen',termination_reason='unknown_initial_evidence',actual_model_calls=0,accepted_rounds=0,
                provenance='real_remote_model',causal_comparison_eligible=False,frozen_sha256=core.digest(state['initial']))
        else:
            try:result=runner.run_trajectory(adapter,e['strategy'],e['seed'],folder,state['baseline'],base['queries'],session,backend,max_rounds=2,prepared=Path(e['state']).parent)
            except Exception as exc:result=runner.freeze_interruption(folder,state,exc,e['search'])
        if (session.out/'budget_stop.json').exists():
            # The legacy runner catches acquisition exceptions; retain its raw record,
            # but distinguish this declared budget stop from an infrastructure error.
            result['termination_reason']='registered_search_wall_budget_exhausted'
            result['budget_stop']=common.read(session.out/'budget_stop.json')
        result.update(case_id=e['case_id'],seed=e['seed'],strategy=e['strategy'],search_strategy=e['search'],registered_id=e['id'],version='research196')
        common.dump(folder/'outcome.json',result);return result
    entries=copy.deepcopy(p['entries']);random.Random(19601).shuffle(entries);common.dump(out/'run_order.json',[e['id'] for e in entries])
    outcomes=[]
    with ThreadPoolExecutor(max_workers=2) as pool:
        for future in as_completed([pool.submit(worker,e) for e in entries]):
            outcomes.append(future.result());common.dump(out/'progress.json',outcomes)
            print('FROZEN',outcomes[-1]['registered_id'],outcomes[-1].get('actual_model_calls'),flush=True)
    if len(outcomes)!=64 or not all(o['status']=='frozen' for o in outcomes):raise ValueError('incomplete_registered_population')
    common.dump(out/'outcome.json',dict(status='completed_all_versions_frozen',population=64,actual_reserved_calls=len(backend.calls),
        maximum_calls=backend.limit,protocol_sha256=backend.seal,independent_inputs_constructed=False,new_independent_acceptance='pending_after_all_frozen'))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--prepared',type=Path,required=True);p.add_argument('--authorization',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();run(a.prepared,a.authorization,a.out)
