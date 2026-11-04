"""Read-only sealed request/ledger/transport audit; no backend import."""
import argparse
import hashlib
from pathlib import Path
import time
from research194_refinement_posthoc import read,dump,digest


def file_hash(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def analyze(campaign,main_prepared,aug_prepared,out):
    campaign=Path(campaign);protocol=read(campaign/'protocol.json');bundles=[];calls=[]
    for bundle,prepared,seal_key in [('base',main_prepared,'main_seal'),('augmentation',aug_prepared,'augmentation_seal')]:
        prepared=Path(prepared);p=read(prepared/'protocol.json');seal=read(prepared/'seal.json')
        source_mismatches=[path for path,sha in p['source_bindings'].items() if file_hash(path)!=sha]
        entries={}
        for entry in p['entries']:
            arm=entry['condition'] if bundle=='augmentation' else entry['search']+'_'+entry['strategy']
            entries[(entry['case_id'],str(entry['seed']),arm)]=entry
        ledger=read(campaign/bundle/'global_model_ledger.json',[]) or []
        reservations={x['folder']:x for x in ledger}
        records=[]
        for path in sorted((campaign/bundle).glob('*/*/*/refinement/round*/model_call/request.json')):
            case,seed,arm,_,rd,_,_=path.relative_to(campaign/bundle).parts
            entry=entries[(case,seed,arm)];request=read(path);result=read(path.parent/'result.json',{})
            attempt=read(path.parent/'attempt.json',{})
            reservation=reservations.get(str(path.parent),{})
            failures=[]
            if entry.get('mode')=='blocked_unknown':failures.append('blocked_entry_dispatched')
            if digest(request)!=reservation.get('request_sha256'):failures.append('reservation_payload_mismatch')
            if rd=='round01' and digest(request)!=entry.get('request_sha256'):failures.append('sealed_first_request_mismatch')
            if request.get('model')!=p['model']:failures.append('request_model')
            if request.get('max_tokens')!=p['max_output_tokens']:failures.append('request_max_tokens')
            if request.get('temperature')!=p['temperature']:failures.append('request_temperature')
            if request.get('seed')!=int(seed)+(int(rd.removeprefix('round'))-1)*1009:failures.append('paired_requested_seed_schedule')
            if attempt.get('timeout_seconds')!=p['timeout_seconds']:failures.append('attempt_timeout')
            if attempt.get('retries')!=0:failures.append('attempt_retry')
            if result and result.get('endpoint')!=p['endpoint']:failures.append('result_endpoint')
            if result and result.get('retries')!=0:failures.append('result_retry')
            if result and result.get('actual_server_model') not in (None,p['model']):failures.append('reported_server_model_changed')
            pt=result.get('prompt_tokens');ct=result.get('completion_tokens')
            row=dict(bundle=bundle,case_id=case,seed=int(seed),arm=arm,round=rd,
                request_path=str(path),request_sha256=digest(request),checks_failed=failures,
                sealed_exact_first=(not failures if rd=='round01' else None),result_present=bool(result),
                prompt_tokens=pt,completion_tokens=ct,known_tokens=pt+ct if isinstance(pt,int) and isinstance(ct,int) else None,
                provider_response_id=result.get('response_id'),status=result.get('status'),
                requested_seed=request.get('seed'),reported_server_model=result.get('actual_server_model'),
                submitted_attempt_present=bool(attempt),retry_count=result.get('retries',attempt.get('retries')))
            records.append(row);calls.append(row)
        bundles.append(dict(bundle=bundle,prepared=str(prepared),
            protocol_file_sha256=file_hash(prepared/'protocol.json'),
            seal_matches=file_hash(prepared/'protocol.json')==seal['protocol_sha256']==protocol[seal_key],
            sealed_source_files=len(p['source_bindings']),sealed_source_mismatches=source_mismatches,
            maximum_authorized_calls=p['maximum_model_calls'],reserved_calls=len(ledger),
            reservation_folders_unique=len(reservations)==len(ledger),
            within_call_cap=len(ledger)<=p['maximum_model_calls'],audited_requests=len(records),
            audited_exact_first_requests=sum(r['round']=='round01' for r in records),
            failing_request_records=sum(bool(r['checks_failed']) for r in records)))
    result=dict(snapshot_unix=time.time(),status='read_only_incremental_audit',bundles=bundles,calls=calls,
        maximum_campaign_calls=protocol['maximum_model_calls'],reserved_calls=sum(b['reserved_calls'] for b in bundles),
        known_tokens=sum(c['known_tokens'] or 0 for c in calls),unknown_usage_calls=sum(c['result_present'] and c['known_tokens'] is None for c in calls),
        new_model_calls=0,sealed_files_modified=False)
    dump(Path(out)/'sealed_model_call_audit.json',result)
    print(dict(bundles=bundles,known_tokens=result['known_tokens'],unknown_usage_calls=result['unknown_usage_calls']))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for arg in ('campaign','main-prepared','aug-prepared','out'):p.add_argument('--'+arg,type=Path,required=True)
    a=p.parse_args();analyze(a.campaign,a.main_prepared,a.aug_prepared,a.out)
