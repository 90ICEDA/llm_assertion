"""Audit paid dispatches, immutable candidates, gates and independent records."""
import argparse
from html.parser import HTMLParser
import json
from pathlib import Path
from urllib.parse import urlsplit,unquote
from research194_refinement_runner import read,dump,file_hash
from research194_refinement import digest

def run(prepared,execution,acceptance,cost,cards,report,finish):
    prepared,execution,acceptance,cost,cards,report,finish=map(Path,(prepared,execution,acceptance,cost,cards,report,finish))
    p=read(prepared/'protocol.json');auth=read(prepared/'authorization.json');errors=[];checks=0
    def check(value,reason,detail=None):
        nonlocal checks
        checks+=1
        if not value:errors.append(dict(reason=reason,detail=detail))
    check(file_hash(prepared/'protocol.json')==read(prepared/'seal.json')['protocol_sha256']==auth['protocol_sha256'],'protocol_auth_seal')
    check(auth['approved'] and auth['version']=='research198' and auth['endpoint']==p['endpoint'] and auth['model']==p['model'],'authorization_scope')
    for key in ('maximum_model_calls','workers','retries','max_output_tokens','timeout_seconds'):check(auth[key]==p[key],'authorization_parameter',key)
    for path,h in p['source_bindings'].items():check(file_hash(path)==h,'sealed_source_changed',path)
    for path,h in read(finish/'protocol.json')['source_bindings'].items():check(file_hash(path)==h,'postprocessing_source_changed',path)
    entries={e['id']:e for e in p['entries']};ledger=read(execution/'ledger.json');reserved={(r['id'],r['round']) for r in ledger}
    markers=list(execution.glob('*/*/*/refinement/round*/model_call/attempt.json'))
    check(len(reserved)==len(ledger)<=p['maximum_model_calls']==180,'budget_or_duplicate')
    seen=set();tokens=0;unknown=0
    for marker in markers:
        parts=marker.relative_to(execution).parts;identity='/'.join(parts[:3]);index=int(parts[4][5:]);key=(identity,index)
        check(key in reserved and key not in seen,'unregistered_dispatch',key);seen.add(key)
        e=entries[identity];check(1<=index<=e['max_rounds'],'round_budget',key)
        request=read(marker.parent/'request.json');preview=read(marker.parent.parent/'request.preview.json')
        check(request==preview,'unarchived_request',key)
        check(request['model']==p['model'] and request['max_tokens']==2048 and request['temperature']==.2 and request['seed']==e['seed']+(index-1)*1009,'request_parameters',key)
        if index==1:check(digest(request)==e['request_sha256'],'first_request_changed',identity)
        text=json.dumps(request)
        for fault in read(prepared/'acceptance_registration.json')['faults'].values():check(fault['id'] not in text,'reserved_fault_sent',key)
        result=marker.parent/'result.json'
        if result.exists():
            r=read(result);tokens+=(r.get('prompt_tokens') or 0)+(r.get('completion_tokens') or 0)
            unknown+=r.get('prompt_tokens') is None or r.get('completion_tokens') is None
        else:unknown+=1
    check(len(markers)<=len(ledger),'dispatch_without_reservation')
    for e in p['entries']:
        folder=execution/e['id']/'refinement';state=read(e['state']);outcome=read(folder/'outcome.json');frozen=read(folder/'frozen.json')
        check(file_hash(e['state'])==e['state_sha256'],'state_binding',e['id'])
        check(outcome['status']=='frozen' and digest(frozen)==outcome['frozen_sha256'],'frozen_hash',e['id'])
        rounds=read(folder/'rounds.json') if (folder/'rounds.json').exists() else []
        active=state['initial']
        for r in rounds:
            rd=folder/f"round{r['round']:02}"
            if r.get('status')=='accepted':
                d=r['decision'];check(not d['critical_unknown'] and not d['new_false_positive_ids'],'accepted_bad_gate',e['id'])
                if e['strategy']=='R3':check(not d['lost_ids'] and not d['historical_any_cycle_lost_ids'],'accepted_history_regression',e['id'])
                check(d['component_guard']['passed'],'accepted_inactive_component',e['id'])
                active=read(rd/'proposal.json')
        check(digest(active)==digest(frozen),'frozen_not_last_accepted',e['id'])
        history=read(folder/'controller_history.json') if (folder/'controller_history.json').exists() else []
        historical_active=state['initial']
        for r in history:
            if r.get('event')=='structural_local_domain_empty':
                certificate=r['certificate'];declared={o for a in historical_active for o in a['obligations']}
                check(certificate['active_sha256']==digest(historical_active) and bool(certificate['missing_obligations'])
                    and not declared.intersection(certificate['missing_obligations']) and bool(certificate['confirmed_target_ids'])
                    and bool(certificate['native_bindings']),'invalid_structural_certificate',e['id'])
                for path,h in certificate['native_bindings'].items():check(file_hash(path)==h,'structural_evidence_changed',path)
            receipt=r.get('fallback_receipt')
            if receipt:
                check(r['decision']['semantic_failure'] and not r['decision']['critical_unknown'] and not r['decision']['accepted'],'invalid_fallback',e['id'])
                check(receipt['active_sha256']==r['retained_sha256'] and receipt['proposal_sha256']==r['proposal_sha256'],'fallback_binding',e['id'])
                for path,h in receipt['native_bindings'].items():check(file_hash(path)==h,'native_receipt_changed',path)
            if r.get('event')=='native_measured' and r['decision']['accepted']:
                historical_active=read(folder/f"round{r['round']:02}"/'proposal.json')
        costs=read(folder/'cost_components.json') if (folder/'cost_components.json').exists() else []
        check(all(c.get('native_compile_attempts',0)==0 and c.get('wall_seconds')==0 for c in costs if c['purpose']=='acquisition'),'reused_search_charged_as_new',e['id'])
    aa=read(acceptance/'native/results.json');freeze=read(acceptance/'freeze.json')
    check(len(freeze['entries'])==36,'frozen_population');check(len(aa)==78,'independent_population')
    check(len({(r['id'],r['fault']) for r in aa})==len(aa),'duplicate_acceptance_records')
    for r in aa:
        if r['full_planned_transaction_scope_pass']:
            check(r['native_complete'] and r['reference_complete'] and r['valid_reachable_fault'] and not r['unknown_records'] and not r['no_exposure_queries'] and not r['false_positive_records'] and not r['transaction_misses'],'invalid_full_scope_pass',r['id'])
    check(read(acceptance/'native/outcome.json')['model_calls']==0,'acceptance_model_calls')
    for path in (cost/'registration.json',cards/'selection.json'):
        check(path.stat().st_mtime_ns<(acceptance/'native/plan.json').stat().st_mtime_ns,'selection_after_acceptance',str(path))
    check(read(cost/'evaluation_outcome.json')['model_calls']==0,'cost_evaluation_model_calls')
    summary=read(report/'summary.json')
    check(summary['model_calls']==len(markers) and summary['known_tokens']==tokens and summary['unknown_usage_calls']==unknown,'reported_cost_mismatch')
    class Links(HTMLParser):
        def __init__(self,path):super().__init__();self.path=path
        def handle_starttag(self,tag,attrs):
            attrs=dict(attrs);href=attrs.get('href') if tag=='a' else attrs.get('src') if tag=='img' else None
            if not href:return
            uri=urlsplit(href)
            if not uri.scheme and not uri.netloc and uri.path:check((self.path.parent/unquote(uri.path)).resolve().is_file(),'broken_link',href)
    for path in (report/'report.html',cards/'cards.html'):Links(path).feed(path.read_text(encoding='utf-8'))
    result=dict(status='failed' if errors else 'passed',checks=checks,failures=errors,model_calls=len(markers),reserved=len(ledger),maximum_calls=180,
        known_tokens=tokens,unknown_usage_calls=unknown,frozen_versions=36,independent_version_fault_records=len(aa),
        actual_full_three_stage_paths=summary['full_native_three_stage_paths'],accepted_local=summary['accepted_local'],
        partial_improvement_structural_three_stage_paths=summary['partial_improvement_structural_three_stage_paths'],
        independent_full_scope_pass_records=summary['independent_full_scope_pass_records'],audit_source_sha256=file_hash(__file__),
        note='Audit success is record consistency, not algorithm superiority or universal coverage.')
    dump(report/'final_audit.json',result);print(result,flush=True)
    if errors:raise SystemExit(1)

if __name__=='__main__':
    p=argparse.ArgumentParser()
    for k in ('prepared','execution','acceptance','cost','cards','report','finish'):p.add_argument('--'+k,type=Path,required=True)
    a=p.parse_args();run(a.prepared,a.execution,a.acceptance,a.cost,a.cards,a.report,a.finish)
