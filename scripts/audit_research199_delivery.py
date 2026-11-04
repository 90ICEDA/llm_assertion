"""Additive, local-only audit of the sealed R199 execution and its products."""
import argparse
import json
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit, unquote
from research194_refinement_runner import read, dump, file_hash, ROOT
from research194_refinement import digest


def dependencies(prepared):
    path = prepared / 'postprocessing_dependencies.json'
    seal = read(prepared / 'postprocessing_dependencies.seal.json')
    assert file_hash(path) == seal['sha256'], 'dependency seal changed'
    data = json.loads(path.read_text(encoding='utf-8-sig'))
    assert data['parent_protocol_sha256'] == file_hash(prepared / 'protocol.json')
    for src, expected in data['source_bindings'].items():
        assert file_hash(ROOT / src) == expected, src
    return len(data['source_bindings'])


def run(prepared, execution, finish):
    count = dependencies(prepared)
    errors = []
    def check(ok, reason, detail=None):
        nonlocal count
        count += 1
        if not ok:
            errors.append(dict(reason=reason, detail=detail))
    p, auth = read(prepared/'protocol.json'), read(prepared/'authorization.json')
    check(file_hash(prepared/'protocol.json') == read(prepared/'seal.json')['protocol_sha256'] == auth['protocol_sha256'], 'protocol seal')
    check(auth['approved'] and auth['version']=='research199' and auth['endpoint']==p['endpoint'] and auth['model']==p['model'], 'authorization')
    for key in ('maximum_model_calls','workers','retries','max_output_tokens','timeout_seconds'):
        check(auth[key]==p[key], 'authorization limit', key)
    for path, h in p['source_bindings'].items():
        check(file_hash(path)==h, 'source changed', path)
    for path, h in read(finish/'protocol.json')['source_bindings'].items():
        check(file_hash(path)==h, 'postprocessing source changed', path)
    entries={e['id']:e for e in p['entries']}
    ledger=read(execution/'ledger.json')
    reserved={(r['id'],r['round']) for r in ledger}
    check(len(reserved)==len(ledger)<=144, 'duplicate reservation or budget')
    markers=list(execution.glob('*/*/*/refinement/round*/model_call/attempt.json'))
    seen=set(); tokens=0; unknown=0
    faults=read(prepared/'acceptance_registration.json')['faults']
    for marker in markers:
        parts=marker.relative_to(execution).parts
        identity='/'.join(parts[:3]); index=int(parts[4][5:]); key=(identity,index)
        check(key in reserved and key not in seen, 'unregistered dispatch', key); seen.add(key)
        e=entries[identity]
        check(1<=index<=3, 'round budget', key)
        req=read(marker.parent/'request.json')
        context=json.loads(req['messages'][-1]['content'])
        check(context['experiment']['version']=='research199' and context['experiment']['arm']==e['arm'], 'request experiment identity', key)
        check(req==read(marker.parent.parent/'request.preview.json'), 'request not archived', key)
        check(req['model']==p['model'] and req['max_tokens']==2048 and req['temperature']==.2 and req['seed']==e['seed']+(index-1)*1009, 'request parameters', key)
        if index==1:
            check(digest(req)==e['request_sha256'], 'first request changed', key)
        text=json.dumps(req)
        for fault in faults.values():
            check(fault['id'] not in text, 'independent fault sent', key)
        result=marker.parent/'result.json'
        if result.exists():
            r=read(result); tokens+=(r.get('prompt_tokens') or 0)+(r.get('completion_tokens') or 0)
            unknown+=r.get('prompt_tokens') is None or r.get('completion_tokens') is None
        else:
            unknown+=1
    check(len(markers)<=len(ledger), 'dispatch without reservation')
    online_queries=0; accepted=0; accepted_local=0
    for e in p['entries']:
        folder=execution/e['id']/'refinement'; state=read(e['state'])
        result=read(folder/'outcome.json'); frozen=read(folder/'frozen.json')
        check(file_hash(e['state'])==e['state_sha256'], 'initial state changed', e['id'])
        check(result['status']=='frozen' and digest(frozen)==result['frozen_sha256'], 'frozen binding', e['id'])
        active=state['initial']
        rounds=read(folder/'rounds.json') if (folder/'rounds.json').exists() else []
        for r in rounds:
            rd=folder/f"round{r['round']:02}"
            if (rd/'current_measurement.json').exists():
                current=read(rd/'current_measurement.json')
                check(current['candidate_sha256']==digest(active), 'round evaluated stale candidate', (e['id'],r['round']))
            if (rd/'request.preview.json').exists():
                request_context=json.loads(read(rd/'request.preview.json')['messages'][-1]['content'])
                check(digest(request_context['current_assertions'])==digest(active), 'model saw stale candidate', (e['id'],r['round']))
            if r.get('status')!='accepted':
                continue
            accepted+=1; accepted_local+=r.get('stage')=='local'; d=r['decision']
            check(not d['critical_unknown'] and not d['new_false_positive_ids'], 'accepted unknown or new false positive', e['id'])
            if e['strategy']=='R3':
                check(not d['lost_ids'] and not d['historical_any_cycle_lost_ids'], 'history regression', e['id'])
            check(d['component_guard']['passed'], 'component trigger guard', e['id'])
            active=read(folder/f"round{r['round']:02}"/'proposal.json')
        check(digest(active)==digest(frozen), 'frozen is not last accepted', e['id'])
        history=read(folder/'controller_history.json') if (folder/'controller_history.json').exists() else []
        retained=state['initial']
        for item in history:
            if item.get('event')=='structural_local_domain_empty':
                cert=item['certificate']; declared={o for a in retained for o in a['obligations']}
                check(cert['active_sha256']==digest(retained) and bool(cert['missing_obligations']) and not declared.intersection(cert['missing_obligations']) and bool(cert['confirmed_target_ids']) and bool(cert['native_bindings']), 'invalid structural fallback certificate', e['id'])
                for src,h in cert['native_bindings'].items():
                    check(file_hash(src)==h, 'structural evidence changed', src)
            receipt=item.get('fallback_receipt')
            if receipt:
                d=item['decision']
                check(d['semantic_failure'] and not d['critical_unknown'] and not d['accepted'], 'invalid rejected-proposal fallback', e['id'])
                check(receipt['active_sha256']==item['retained_sha256'] and receipt['proposal_sha256']==item['proposal_sha256'], 'fallback candidate binding', e['id'])
                for src,h in receipt['native_bindings'].items():
                    check(file_hash(src)==h, 'native fallback evidence changed', src)
            if item.get('event')=='native_measured' and item['decision']['accepted']:
                retained=read(folder/f"round{item['round']:02}"/'proposal.json')
        if e['cohort']=='online':
            for path in (execution/e['id']/'acquisition').glob('query*/acquisition.json'):
                acq=read(path)
                if acq.get('first_query_physical_reuse'):
                    continue
                online_queries+=1; link=acq['online_link']
                check(link['candidate_sha256']==acq['selection']['candidate_sha256'] and link['reselected'] and not link['heldout_access'], 'online candidate binding', str(path))
    acceptance=finish/'acceptance/native'; aa=read(acceptance/'results.json')
    check(read(execution/'outcome.json')['status']=='completed_all_versions_frozen', 'incomplete execution')
    check(len(read(finish/'acceptance/freeze.json')['entries'])==48, 'freeze population')
    check(len(aa)==102 and len({(r['id'],r['fault']) for r in aa})==len(aa), 'acceptance population')
    for r in aa:
        if r['full_planned_transaction_scope_pass']:
            check(r['native_complete'] and r['reference_complete'] and r['valid_reachable_fault'] and not r['unknown_records'] and not r['no_exposure_queries'] and not r['false_positive_records'] and not r['transaction_misses'], 'invalid full pass', r['id'])
    check(read(acceptance/'outcome.json')['model_calls']==0, 'acceptance model calls')
    check((finish/'cost/registration.json').stat().st_mtime_ns<(acceptance/'plan.json').stat().st_mtime_ns, 'cost registration after independent inputs')
    check(read(finish/'cost/evaluation_outcome.json')['model_calls']==0, 'cost model calls')
    for src in read(finish/'cost/projection_index.json').values():
        check(file_hash(src['path'])==src['sha256'], 'projection changed', src['path'])
    summary=read(finish/'report/summary.json')
    check(summary['actual_model_calls']==len(markers) and summary['known_tokens']==tokens and summary['unknown_usage_calls']==unknown, 'cost reporting mismatch')
    class Links(HTMLParser):
        def handle_starttag(self, tag, attrs):
            attrs=dict(attrs); url=attrs.get('href') if tag=='a' else attrs.get('src') if tag=='img' else None
            if not url: return
            uri=urlsplit(url)
            if not uri.scheme and not uri.netloc and uri.path:
                check((finish/'report'/unquote(uri.path)).resolve().is_file(), 'broken link', url)
    Links().feed((finish/'report/report.html').read_text(encoding='utf-8'))
    dependencies(prepared)
    result=dict(status='failed' if errors else 'passed',checks=count,failures=errors,actual_model_calls=len(markers),reserved_calls=len(ledger),maximum_calls=144,known_tokens=tokens,unknown_usage_calls=unknown,accepted_modifications=accepted,accepted_local=accepted_local,fresh_followup_online_queries=online_queries,frozen_versions=48,independent_version_fault_records=len(aa),audit_source_sha256=file_hash(__file__),note='Record consistency is not algorithm superiority or universal acceptance.')
    dump(finish/'report/final_audit.json',result); print(json.dumps(result,ensure_ascii=False),flush=True)
    if errors: raise SystemExit(1)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for key in ('prepared','execution','finish'): parser.add_argument('--'+key,type=Path,required=True)
    args=parser.parse_args(); run(args.prepared,args.execution,args.finish)
