"""Reconcile authorization, immutable freezes, costs and post-freeze acceptance."""
import argparse
from html.parser import HTMLParser
from pathlib import Path
from research194_refinement_runner import ROOT,read,dump,file_hash
from research194_refinement import digest


def audit(prepared,execution,acceptance,cost,cards,report,authorization):
    prepared,execution,acceptance,cost,cards,report,authorization=map(Path,(prepared,execution,acceptance,cost,cards,report,authorization))
    failures=[];checks=0
    def check(condition,reason,detail=None):
        nonlocal checks
        checks+=1
        if not condition:failures.append(dict(reason=reason,detail=detail))
    p=read(prepared/'protocol.json');auth=read(authorization);seal=read(prepared/'seal.json')['protocol_sha256']
    check(file_hash(prepared/'protocol.json')==seal==auth['protocol_sha256'],'protocol_authorization_binding')
    check(auth['approved'] and auth['maximum_model_calls']==118 and auth['retries']==0,'authorization_limits')
    for path,h in p['source_bindings'].items():check(file_hash(path)==h,'sealed_source_changed',path)
    ledger=read(execution/'ledger.json');check(len(ledger)<=118,'reservation_ceiling')
    check(len({(r['id'],r['round']) for r in ledger})==len(ledger),'duplicate_call_round')
    entries={e['id']:e for e in p['entries']};attempts=list(execution.glob('*/*/*/refinement/round*/model_call/attempt.json'))
    check(len(attempts)<=len(ledger),'submission_without_reservation')
    reserved={(r['id'],r['round']) for r in ledger};seen=set();known_tokens=0;unknown_tokens=0
    for marker in attempts:
        parts=marker.relative_to(execution).parts;identity='/'.join(parts[:3]);index=int(parts[4][-2:]);seen.add((identity,index))
        check((identity,index) in reserved and entries[identity]['mode']=='ready','unauthorized_or_unknown_call',identity)
        request=read(marker.parent/'request.json');preview=read(marker.parent.parent/'request.preview.json')
        check(request==preview,'sent_request_differs_from_archived_preview',str(marker))
        check(request['model']==p['model'] and request['max_tokens']==2048 and request['temperature']==.2 and request['seed']==entries[identity]['seed']+(index-1)*1009,'model_parameters',identity)
        if index==1:check(digest(request)==entries[identity]['request_sha256'],'first_request_not_sealed',identity)
        attempt=read(marker);check(attempt.get('retries')==0 and attempt.get('timeout_seconds',301)<=300,'transport_limits',identity)
        raw=(marker.parent/'request.json').read_text(encoding='utf-8')
        check(not any(s in raw for s in ('r196_grant_rotate','r196_overflow_slice','r196_idle_early','r196_stack_destination','research196_independent_20261104_r01')),'independent_payload_leak',identity)
        if (marker.parent/'result.json').exists():
            result=read(marker.parent/'result.json');a,b=result.get('prompt_tokens'),result.get('completion_tokens')
            if isinstance(a,int) and isinstance(b,int):known_tokens+=a+b
            else:unknown_tokens+=1
        else:unknown_tokens+=1
    check(len(seen)==len(attempts),'duplicate_submissions')
    final=read(execution/'outcome.json');check(final['status']=='completed_all_versions_frozen' and final['population']==64,'incomplete_model_population')
    freeze=read(acceptance.parent/'freeze.json');frozen={r['id']:r for r in freeze['entries']}
    check(set(frozen)==set(entries),'acceptance_population_changed')
    accepted=0
    for identity,e in entries.items():
        folder=execution/identity/'refinement';candidate=read(folder/'frozen.json');terminal=read(folder/'outcome.json')
        check(terminal['status']=='frozen' and digest(candidate)==terminal['frozen_sha256']==frozen[identity]['candidate_sha256'],'frozen_candidate_changed',identity)
        check(file_hash(folder/'frozen.json')==frozen[identity]['sha256'],'acceptance_freeze_file_changed',identity)
        rounds=read(folder/'rounds.json') if (folder/'rounds.json').exists() else []
        if e['mode']=='blocked_unknown':check(not any(i==identity for i,_ in seen),'blocked_initial_called',identity)
        for r in rounds:
            if r.get('status')!='accepted':continue
            accepted+=1;d=r['decision'];g=d.get('component_guard',{})
            check(g.get('enabled') and g.get('passed') and not d.get('critical_unknown'),'accepted_without_qualified_component_gate',identity)
            check(all(c['verdict']=='confirmed_active' and c['confirmed_activity_evidence_ids'] for c in g.get('components',[])),'accepted_inactive_component',identity)
            if e['strategy'] in ('R2','R3'):check(not d['lost_ids'] and not d['historical_any_cycle_lost_ids'] and not d['new_false_positive_ids'],'history_regression_accepted',identity)
    aa=read(acceptance/'results.json');check(read(acceptance/'outcome.json')['status']=='completed','independent_incomplete')
    expected=set(entries)|{c+'/initial_control' for c in p['case_ids']}
    check({r['id'] for r in aa}==expected,'missing_acceptance_versions')
    for r in aa:
        check(len(r['target_ids'])==len(set(r['target_ids']))==r['target_transaction_obligations'],'duplicate_target_credit',r['id'])
        if r['full_planned_transaction_scope_pass']:
            check(r['native_complete'] and r['reference_complete'] and not r['unknown_records'] and not r['no_exposure_queries'] and not r['false_positive_records'] and not r['transaction_misses'],'invalid_scope_pass',r['id'])
    check((cost/'registration.json').stat().st_mtime_ns<(acceptance/'plan.json').stat().st_mtime_ns,'cost_selection_not_before_acceptance')
    check((cards/'selection.json').stat().st_mtime_ns<(acceptance/'plan.json').stat().st_mtime_ns,'card_selection_not_before_acceptance')
    compat=ROOT/'deliverables/research196_finish_compat_20261104_r01'
    repair=read(compat/'protocol.json')
    check(repair['model_calls']==0 and repair['qualification']['definitions_unchanged'] and repair['qualification']['shared_registry_unchanged'],'compatibility_repair_scope')
    check((compat/'protocol.json').stat().st_mtime_ns<(acceptance/'plan.json').stat().st_mtime_ns,'compatibility_repair_not_registered_before_inputs')
    for path,h in repair['source_bindings'].items():check(file_hash(path)==h,'postprocessing_source_changed',path)
    check(read(compat/'status.json')['status']=='local_phases_completed','postprocessing_incomplete')
    check(read(cost/'evaluation_outcome.json')['model_calls']==0,'unexpected_cost_model_calls')
    summary=read(report/'summary.json')
    check(summary['actual_model_calls']==len(attempts) and summary['known_tokens']==known_tokens and summary['unknown_usage_calls']==unknown_tokens,'report_cost_mismatch')
    check(summary['accepted_rounds']==accepted,'acceptance_count_mismatch')
    class Links(HTMLParser):
        def __init__(self,base):super().__init__();self.base=base
        def handle_starttag(self,tag,attrs):
            values=dict(attrs);href=values.get('href') if tag=='a' else values.get('src') if tag=='img' else None
            if href and '://' not in href and not href.startswith('#'):check((self.base/href).resolve().is_file(),'broken_report_link',href)
    for html in (report/'report.html',cards/'cards.html'):Links(html.parent).feed(html.read_text(encoding='utf-8'))
    result=dict(status='passed' if not failures else 'failed',checks=checks,failures=failures,actual_model_calls=len(attempts),reserved_calls=len(ledger),maximum_authorized_calls=118,
        known_tokens=known_tokens,unknown_usage_calls=unknown_tokens,frozen_versions=64,accepted_rounds=accepted,independent_version_fault_records=len(aa),
        note='Audit completion is not full-scope acceptance or proof of algorithm superiority.')
    dump(report/'final_audit.json',result);print(result,flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser()
    for k in ('prepared','execution','acceptance','cost','cards','report','authorization'):ap.add_argument('--'+k,type=Path,required=True)
    a=ap.parse_args();audit(a.prepared,a.execution,a.acceptance,a.cost,a.cards,a.report,a.authorization)
