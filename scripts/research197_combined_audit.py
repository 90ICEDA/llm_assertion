"""Audit the additional six-call grant and authoritative 72-version freeze."""
from datetime import datetime,timezone
import json
from pathlib import Path
from research194_refinement_runner import ROOT,read,dump,file_hash
from research194_refinement import digest


def run():
    d=ROOT/'deliverables';report=d/'reguard_mechanisms_20261104_r07';prepared=d/'research197_typed_contract_fix_20261104_r01'
    execution=d/'research197_typed_execute_20261104_r01';main=d/'research197_refinement_execute_20261104_r01'
    combined=d/'research197_combined_independent_20261104_r01';registration=d/'research197_combined_registration_20261104_r01'
    failures=[];count=0
    def check(value,reason,detail=None):
        nonlocal count
        count+=1
        if not value:failures.append(dict(reason=reason,detail=detail))
    original=read(report/'final_audit.json');check(original['status']=='passed','original_audit_failed')
    p=read(prepared/'protocol.json');auth=read(prepared/'authorization.json');seal=file_hash(prepared/'protocol.json')
    check(seal==read(prepared/'seal.json')['protocol_sha256']==auth['protocol_sha256'],'corrected_authorization_seal')
    check(auth['approved'] and auth['maximum_model_calls']==6 and auth['endpoint']==p['endpoint'] and auth['model']==p['model'],'corrected_authorization_scope')
    check(auth['workers']==2 and auth['retries']==0,'corrected_execution_limits')
    for path,h in p['source_bindings'].items():check(file_hash(path)==h,'corrected_source_changed',path)
    entries={e['id']:e for e in p['entries']};ledger=read(execution/'ledger.json');markers=list(execution.glob('*/*/*/refinement/round*/model_call/attempt.json'))
    check(len(markers)<=len(ledger)<=6,'corrected_call_budget');check(len({(r['id'],r['round']) for r in ledger})==len(ledger),'duplicate_corrected_reservations')
    check(len(markers)==len(ledger)==len(entries)==6,'corrected_registered_trials_not_dispatched')
    known=0;unknown=0
    for marker in markers:
        identity='/'.join(marker.relative_to(execution).parts[:3]);e=entries[identity];request=read(marker.parent/'request.json')
        check(marker.parent.parent.name=='round01','corrected_second_round',identity)
        check(digest(request)==e['request_sha256'] and request==read(e['request']),'corrected_dispatched_request',identity)
        check(request['model']==p['model'] and request['seed']==e['seed'] and request['max_tokens']==2048,'corrected_parameters',identity)
        before=json.loads(read(e['original_request'])['messages'][-1]['content']);after=json.loads(request['messages'][-1]['content'])
        before.pop('output_contract');contract=after.pop('output_contract')
        check(before==after,'corrected_non_contract_information_changed',identity)
        check('replace_field' not in json.dumps(contract) and set(contract['operations'])==set(contract['operations_allowed']),'corrected_contract_still_conflicting',identity)
        attempt=read(marker);check(attempt['retries']==0 and attempt['timeout_seconds']<=300,'corrected_timeout_or_retry',identity)
        start=datetime.strptime(attempt['started_utc'],'%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc).timestamp()
        check(start+1>=(main/'outcome.json').stat().st_mtime,'cohorts_overlapped',identity)
        result=read(marker.parent/'result.json') if (marker.parent/'result.json').exists() else {}
        a,b=result.get('prompt_tokens'),result.get('completion_tokens')
        if type(a)is int and type(b)is int:known+=a+b
        else:unknown+=1
    freeze=read(combined/'freeze.json');reg=read(registration/'registration.json');plan=combined/'native/plan.json'
    check(freeze['expected']==len(freeze['entries'])==72 and freeze['all_trajectories_closed'],'combined_population')
    check(file_hash(registration/'registration.json')==read(registration/'seal.json')['sha256']==freeze['registration_sha256'],'combined_registration_binding')
    for path,h in reg['source_bindings'].items():check(file_hash(path)==h,'combined_registered_source_changed',path)
    for e in freeze['entries']:
        check(file_hash(ROOT/e['path'])==e['sha256'] and digest(read(ROOT/e['path']))==e['candidate_sha256'],'combined_frozen_candidate_changed',e['id'])
    for path in (main/'outcome.json',execution/'outcome.json',combined/'freeze.json',d/'research197_typed_analysis_20261104_r01/cost/registration.json',d/'research197_corrected_cards_20261104_r01/selection.json'):
        check(path.stat().st_mtime_ns<plan.stat().st_mtime_ns,'late_freeze_or_selection',str(path))
    aa=read(combined/'native/results.json');ids={e['id'] for e in freeze['entries']}|{e['id'] for e in freeze['controls']}
    check({r['id'] for r in aa}==ids and len(ids)==75 and len(aa)==150,'combined_acceptance_membership')
    check(len({(r['id'],r['fault']) for r in aa})==150,'duplicate_version_fault_records')
    view=read(d/'research197_independent_20261104_r01/native/results.json');check(len(view)==138 and all(r in aa for r in view),'original_view_changed_measurements')
    for cohort in ('research197_typed_cards_20261104_r01','research197_corrected_cards_20261104_r01'):
        data=read(d/cohort/'diagnostics.json');check(len(data['cards'])==6,'missing_typed_trial_cards',cohort)
        check(all(len(c['independent_acceptance'])==4 for c in data['cards']),'missing_typed_trial_acceptance',cohort)
    for name,n in (('temporal_operation_coverage.json',162),('temporal_operation_coverage_corrected.json',6)):
        coverage=read(report/name);check(len(coverage['rows'])==n,'overwritten_operation_coverage',name)
    additional=read(report/'corrected_isolation.json')
    check(additional['corrected_dispatches']==len(markers) and additional['corrected_known_tokens']==known and additional['corrected_unknown_usage_calls']==unknown,'corrected_report_cost')
    check(original['actual_model_calls']+len(markers)<=168,'combined_budget')
    result=dict(status='failed' if failures else 'passed',checks=count,failures=failures,original_audit_checks=original['checks'],
        original_calls=original['actual_model_calls'],additional_calls=len(markers),maximum_authorized_calls=168,
        total_known_tokens=original['known_tokens']+known,total_unknown_usage_calls=original['unknown_usage_calls']+unknown,
        frozen_versions=72,initial_controls=3,version_fault_records=len(aa),model_calls_during_acceptance=read(combined/'native/outcome.json')['model_calls'],
        physical_acceptance_compiles=read(combined/'native/outcome.json')['physical_compiles'],
        audit_source_sha256=file_hash(__file__),note='Original and corrected cohorts are distinct; shared physical acceptance cost is counted once. No superiority follows from audit success.')
    dump(report/'combined_audit.json',result);print(result,flush=True)
    if failures:raise SystemExit(1)


if __name__=='__main__':run()
