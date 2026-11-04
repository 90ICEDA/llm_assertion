"""Six separately authorized, exact corrected T requests; no adaptive follow-up."""
import argparse
import copy
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
import threading
from research194_refinement_runner import read,dump,file_hash
from research194_refinement import digest
from research197_execute import Backend as SealedTransport
from research197_cases import CaseAdapter
from research197_search import session
from research197_typed_contract_fix import runtime


class Backend(SealedTransport):
    def __init__(self,prepared,authorization,out):
        self.prepared=Path(prepared);self.protocol=read(self.prepared/'protocol.json');self.seal=file_hash(self.prepared/'protocol.json')
        p=self.protocol;auth=read(authorization)
        if self.seal!=read(self.prepared/'seal.json')['protocol_sha256']:raise ValueError('correction_seal_changed')
        if not(auth.get('approved') is True and auth.get('version')==p['version'] and auth.get('protocol_sha256')==self.seal and auth.get('endpoint')==p['endpoint'] and auth.get('maximum_model_calls')==6 and auth.get('user_message_reference')):raise ValueError('separate_six_call_authorization_required')
        if len(p['entries'])!=6 or p['maximum_model_calls']!=6:raise ValueError('population_changed')
        for path,h in p['source_bindings'].items():
            if file_hash(path)!=h:raise ValueError('source_changed:'+path)
        self.limit=6;self.root=Path(out).resolve();self.ledger=self.root/'ledger.json';self.calls=[];self.lock=threading.RLock()
        if self.root.exists():raise ValueError('immutable_no_retry')
        self.entries={e['id']:dict(e,state=e['original_state'],state_sha256=e['original_state_sha256'],max_rounds=1) for e in p['entries']}
        dump(self.ledger,[])


def run(prepared,original_prepared,original_execution,authorization,out):
    if read(Path(original_execution)/'outcome.json')['status']!='completed_all_versions_frozen':raise ValueError('original_campaign_must_end_first')
    original=read(Path(original_prepared)/'protocol.json');backend=Backend(prepared,authorization,out);out=backend.root
    if file_hash(Path(original_prepared)/'protocol.json')!=backend.protocol['original_protocol_sha256']:raise ValueError('original_protocol_binding')
    dump(out/'execution_sources.json',{str(Path(__file__).resolve()):file_hash(__file__)})
    def worker(e):
        state=copy.deepcopy(read(e['original_state']));request=read(e['request']);state['first_request_sha256']=digest(request)
        prep=out/'prepared_state'/e['id'];dump(prep/'state.json',state);dump(prep/'request.preview.json',request)
        core,runner=runtime();adapter=CaseAdapter(e['case_id']);base=read(original['baselines'][e['case_id']]);folder=out/e['id']/'refinement'
        s=session(e['case_id'],'S0',e['seed'],out/e['id']/'acquisition',baseline=base['measurement'],queries=base['queries'],cost_model=original['cost_models'][e['case_id']],max_queries=1)
        try:result=runner.run_trajectory(adapter,'R3',e['seed'],folder,state['baseline'],base['queries'],s,backend,max_rounds=1,prepared=prep)
        except Exception as exc:result=runner.freeze_interruption(folder,state,exc,'S0')
        result.update(case_id=e['case_id'],seed=e['seed'],strategy='R3',search_strategy='S0',registered_id=e['id']+'_corrected',arm='T_corrected',version='research197-typed-contract-fix')
        dump(folder/'outcome.json',result);return result
    done=[]
    with ThreadPoolExecutor(max_workers=2) as pool:
        for future in as_completed([pool.submit(worker,e) for e in backend.protocol['entries']]):
            result=future.result();done.append(result);dump(out/'progress.json',done);print('CORRECTED_FROZEN',result['registered_id'],flush=True)
    if len(done)!=6 or not all(r['status']=='frozen' for r in done):raise ValueError('incomplete_corrected_population')
    dump(out/'outcome.json',dict(status='completed_all_versions_frozen',population=6,reserved_calls=len(backend.calls),maximum_calls=6,
        original_results_replaced=False,independent_inputs_read=False,protocol_sha256=backend.seal))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for key in ('prepared','original-prepared','original-execution','authorization','out'):p.add_argument('--'+key,required=True,type=Path)
    a=p.parse_args();run(a.prepared,a.original_prepared,a.original_execution,a.authorization,a.out)
