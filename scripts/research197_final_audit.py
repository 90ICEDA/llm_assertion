"""Reconcile R197 authorization, actual dispatches, frozen evidence and reports."""
import argparse
from html.parser import HTMLParser
from pathlib import Path
from research194_refinement_runner import read,dump,file_hash
from research194_refinement import digest


def audit(prepared,execution,acceptance,cost,cards,report,authorization):
    prepared,execution,acceptance,cost,cards,report,authorization=map(Path,(prepared,execution,acceptance,cost,cards,report,authorization))
    failures=[];checks=0
    def check(value,reason,detail=None):
        nonlocal checks
        checks+=1
        if not value:failures.append(dict(reason=reason,detail=detail))
    p=read(prepared/'protocol.json');auth=read(authorization);seal=read(prepared/'seal.json')['protocol_sha256']
    check(file_hash(prepared/'protocol.json')==seal==auth['protocol_sha256'],'authorization_seal')
    check(auth['approved'] and auth['maximum_model_calls']==162 and auth['model']==p['model'] and auth['endpoint']==p['endpoint'],'authorization_scope')
    check(p['workers']==auth['workers']==2 and p['retries']==auth['retries']==0,'parallelism_and_retry_policy')
    for path,h in p['source_bindings'].items():check(file_hash(path)==h,'sealed_source_changed',path)
    entries={e['id']:e for e in p['entries']};ledger=read(execution/'ledger.json')
    reserved={(r['id'],r['round']):r for r in ledger}
    check(len(reserved)==len(ledger)<=p['maximum_model_calls']<=162,'reservation_budget_and_uniqueness')
    for cid in p['case_ids']:
        for seed in p['seeds']:
            group=[read(entries[f'{cid}/{seed}/{a}']['state']) for a in ('F','P','T')]
            for key in ('initial','baseline','first_measurement','public_evidence'):
                check(len({digest(s[key]) for s in group})==1,'isolation_evidence_mismatch',dict(case_id=cid,seed=seed,key=key))
    markers=list(execution.glob('*/*/*/refinement/round*/model_call/attempt.json'));known=0;unknown=0;seen=set()
    check(len(markers)<=len(ledger),'dispatch_without_reservation')
    for marker in markers:
        parts=marker.relative_to(execution).parts;identity='/'.join(parts[:3]);index=int(parts[4][5:]);key=(identity,index)
        check(key in reserved and key not in seen,'unregistered_or_duplicate_dispatch',key);seen.add(key)
        e=entries[identity];check(e['mode']=='ready' and 1<=index<=e['max_rounds'],'invalid_round',key)
        request=read(marker.parent/'request.json');preview=read(marker.parent.parent/'request.preview.json')
        check(request==preview and digest(request)==reserved[key]['request_sha256'],'dispatched_preview_mismatch',key)
        check(request['model']==p['model'] and request['max_tokens']==2048 and request['seed']==e['seed']+(index-1)*1009 and request['temperature']==.2,'model_parameters',key)
        if index==1:check(digest(request)==e['request_sha256'],'first_request_mismatch',identity)
        attempt=read(marker);check(attempt['retries']==0 and attempt['timeout_seconds']<=300,'dispatch_limits',key)
        text=(marker.parent/'request.json').read_text(encoding='utf-8')
        check(not any(v in text for v in ('test_extra_delay','test_id_route','test_sticky_output_gate','research197_independent_20261104_r01')),'reserved_acceptance_payload_leak',key)
        result=read(marker.parent/'result.json') if (marker.parent/'result.json').exists() else {}
        a,b=result.get('prompt_tokens'),result.get('completion_tokens')
        if type(a)is int and type(b)is int:known+=a+b
        else:unknown+=1
    final=read(execution/'outcome.json');check(final['status']=='completed_all_versions_frozen' and final['population']==66,'model_population_not_closed')
    freeze=read(acceptance.parent/'freeze.json');frozen={r['id']:r for r in freeze['entries']}
    check(set(frozen)==set(entries),'acceptance_population')
    accepted=0;local=0
    for identity,e in entries.items():
        folder=execution/identity/'refinement';candidate=read(folder/'frozen.json');terminal=read(folder/'outcome.json')
        check(terminal['status']=='frozen' and digest(candidate)==terminal['frozen_sha256']==frozen[identity]['candidate_sha256'],'frozen_candidate_changed',identity)
        check(file_hash(folder/'frozen.json')==frozen[identity]['sha256'],'frozen_file_changed',identity)
        rounds=read(folder/'rounds.json') if (folder/'rounds.json').exists() else []
        check(len(rounds)<=e['max_rounds'],'round_ceiling',identity)
        for r in rounds:
            if r.get('status')!='accepted':continue
            accepted+=1;local+=r.get('stage')=='local';d=r['decision'];g=d.get('component_guard',{})
            check(g.get('enabled') and g.get('passed') and not d.get('critical_unknown'),'accepted_without_activity_gate',identity)
            check(all(c['verdict']=='confirmed_active' and c['confirmed_activity_evidence_ids'] for c in g.get('components',[])),'inactive_component_accepted',identity)
            if e['strategy'] in ('R2','R3'):check(not d['lost_ids'] and not d['historical_any_cycle_lost_ids'] and not d['new_false_positive_ids'],'history_regression_accepted',identity)
    aa=read(acceptance/'results.json');check(read(acceptance/'outcome.json')['status']=='completed','acceptance_incomplete')
    check({r['id'] for r in aa}==set(entries)|{cid+'/initial_control' for cid in p['case_ids']},'missing_acceptance_versions')
    for r in aa:
        check(len(set(r['target_ids']))==len(r['target_ids'])==r['target_transaction_obligations'],'duplicated_target_credit',r['id'])
        if r['full_planned_transaction_scope_pass']:
            check(r['native_complete'] and r['reference_complete'] and not r['unknown_records'] and not r['no_exposure_queries'] and not r['false_positive_records'] and not r['transaction_misses'],'invalid_full_scope_pass',r['id'])
    for path in (cost/'registration.json',cards/'selection.json'):
        check(path.stat().st_mtime_ns<(acceptance/'plan.json').stat().st_mtime_ns,'selection_after_acceptance',str(path))
    check(read(cost/'evaluation_outcome.json')['model_calls']==0,'cost_evaluation_model_calls')
    summary=read(report/'summary.json')
    check(summary['physical_dispatch_attempts']==len(markers) and summary['known_tokens']==known and summary['unknown_usage_calls']==unknown,'reported_call_cost_mismatch')
    check(summary['accepted_local']==local,'local_acceptance_count')
    class Links(HTMLParser):
        def __init__(self,base):super().__init__();self.base=base
        def handle_starttag(self,tag,attrs):
            data=dict(attrs);href=data.get('href') if tag=='a' else data.get('src') if tag=='img' else None
            if href and '://' not in href and not href.startswith('#'):check((self.base/href).resolve().is_file(),'broken_report_link',href)
    for html in (report/'report.html',cards/'cards.html'):Links(html.parent).feed(html.read_text(encoding='utf-8'))
    result=dict(status='failed' if failures else 'passed',checks=checks,failures=failures,actual_model_calls=len(markers),reserved_calls=len(ledger),
        maximum_authorized_calls=162,known_tokens=known,unknown_usage_calls=unknown,frozen_versions=66,accepted_rounds=accepted,accepted_local=local,
        independent_version_fault_records=len(aa),audit_source_sha256=file_hash(__file__),
        note='Audit completion is separate from full-scope acceptance and algorithm benefit.')
    dump(report/'final_audit.json',result);print(result,flush=True)
    if failures:raise SystemExit(1)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for key in ('prepared','execution','acceptance','cost','cards','report','authorization'):parser.add_argument('--'+key,required=True,type=Path)
    a=parser.parse_args();audit(a.prepared,a.execution,a.acceptance,a.cost,a.cards,a.report,a.authorization)
