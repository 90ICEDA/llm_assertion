"""Six explicitly authorized, fixed-request proposals; twelve paired decisions.

Reuses real transport, native runners, current/history gates and holdout. No
retry, semantic rewrite, candidate selection or policy-arm model calls.
"""
import argparse
import copy
import io
import json
from pathlib import Path
import time
import urllib.error
import urllib.request
from unittest.mock import patch
import research70_multiseed_prepare as prepared
import research69_deadline_pilot as pilot

b=prepared.b
ROOT,read,dump=b.ROOT,b.read,b.dump
P=ROOT/'deliverables/research70_multiseed_20261024_r01'
A=ROOT/'deliverables/research70_audit_20261024_r01'
STREAMS=(('ordinary',('A','C')),('search',('B','D')))
KEYS={f's{s}/{a}' for s in b.SEEDS for a in 'ABCD'}


class TransportStop(RuntimeError):
    pass


def send_once(model,folder,initial):
    call,proposal=model.call(folder,initial,'stall_stability',{},'paired_single_step_review')
    if call['status']!='response_received':raise TransportStop(call['status'])
    return call,proposal


def barrier(decisions):
    assert set(decisions)==KEYS,'all_twelve_arms_must_freeze_before_tests'
    assert all(d.get('frozen_hash') for d in decisions.values()),'missing_freeze_hash'


def exclusions():
    prior=ROOT/'deliverables/research69_exclusion_index_20261024_r01'
    assert read(prior/'comparison.json')['passed']
    old=ROOT/'deliverables/research69_pilot_20261024_r01/exclusion_manifest.json'
    assert b.search.digest(old)==read(prior/'comparison.json')['original_manifest_sha256']
    values=set(read(old)['input_hashes']);sources=[dict(path=str(old),sha256=b.search.digest(old))]
    # Hash-only exclusion. Neither test values nor outcomes enter any request.
    path=ROOT/'deliverables/research69_pilot_20261024_r01/independent/split.json'
    split=read(path);values.update(b.loop.sha(c['rows']) for c in split['boundary_cases']+split['drain_cases'])
    sources.append(dict(path=str(path),sha256=b.search.digest(path),usage='input hashes only'))
    for seed in b.SEEDS:
        root=P/'search'/f's{seed}'
        pub=read(root/'public_feedback.json')[b.PAIR_NAME]['results']
        records=[(root/'public'/b.PAIR_NAME/f'q{i}',r) for i,r in enumerate(pub)]
        records += [(root/'queries'/b.PAIR_NAME/f's{seed}'/r['method']/f"q{r['query']}",r)
                    for r in read(root/'records.json')]
        for folder,_ in records:
            for candidate in b.PAIR:
                for mode in b.search.MODES:
                    p=folder/candidate/(mode+'_stimulus')/'stimulus.json';v=read(p)
                    values.add(b.loop.sha(v['rows'] if isinstance(v,dict) else v))
                    sources.append(dict(path=str(p),sha256=b.search.digest(p)))
        prep=P/'ready'/f's{seed}'
        for name in ('history_cases.json','common_cases.json','search_cases.json'):
            values.update(b.loop.sha(c['rows']) for c in read(prep/name))
    return dict(input_hashes=sorted(values),sources=sources,scope='No outcomes used to choose candidates or change rules')


def local_checks(out):
    checks=[];initial=read(P/'shared_initial.json')
    request=read(P/'ready/s6711/ordinary/request.preview.json')
    settings=read(P/'ready/s6711/model_config.json');settings['max_model_calls']=1
    model=pilot.Model(out/'fixture',settings,request)
    key=out/'fixture_key.txt';key.parent.mkdir(parents=True,exist_ok=True);key.write_text('fixture-not-a-real-key')
    model.key_file=key;calls=[]
    def fail(opener,req,*args,**kwargs):
        calls.append(json.loads(req.data))
        assert calls[-1]==request,'real transport altered sealed request'
        raise urllib.error.HTTPError(req.full_url,400,'fixture',{},io.BytesIO(b'fixture-not-a-real-key'))
    with patch.object(urllib.request.OpenerDirector,'open',fail):
        try:send_once(model,out/'fixture/call',initial)
        except TransportStop as exc:assert str(exc)=='service_http_error'
        else:raise AssertionError('transport_failure_did_not_stop')
    assert len(calls)==1 and len(model.calls)==1
    assert 'fixture-not-a-real-key' not in json.dumps(read(out/'fixture/call/service_error_response.json'))
    checks+=['actual transport preserves exact sealed request','HTTP error stops before next request',
             'one fake transport attempt only; not experimental','credential echo redacted']
    valid={k:dict(frozen_hash='fixture_hash_not_a_candidate') for k in KEYS};barrier(valid)
    for key in KEYS:
        missing=copy.deepcopy(valid);del missing[key]
        try:barrier(missing)
        except AssertionError:pass
        else:raise AssertionError('incomplete_freeze_permitted')
        checks.append('holdout rejects missing '+key)
    for seed in b.SEEDS:
        prep=P/'ready'/f's{seed}'
        before=b.campaign.baseline(prep,'ordinary')
        keep=dict(operation='keep',assertion_id='',assertions=[],reason='Local gate fixture, not model output')
        assert not b.paired.current_decision(before,before,keep)['accepted']
        checks.append(f's{seed} unchanged initial misses cannot be accepted')
    return checks


def prepare(out):
    prepared.verify(P);assert read(A/'audit.json')['all_three_seeds_qualified']
    out.mkdir(parents=True,exist_ok=False)
    hashes={}
    for seed in b.SEEDS:
        src=P/'ready'/f's{seed}'
        for rel,h in read(src/'sealed.json').items():assert b.search.digest(src/rel)==h
        for stream,_ in STREAMS:
            p=src/stream/'request.preview.json';hashes[str(p)]=b.search.digest(p)
            dump(out/f's{seed}'/stream/'request.preview.json',read(p))
    dump(out/'request_bindings.json',hashes)
    checks=local_checks(out/'local_checks')
    dump(out/'checks.json',dict(passed=True,checks=checks,real_model_calls=0,fixture_is_not_experiment=True))
    dump(out/'excluded_inputs.json',exclusions())
    config=read(P/'ready/s6711/model_config.json')
    dump(out/'protocol.json',dict(seeds=list(b.SEEDS),physical_call_cap=6,logical_arms=12,
        call_order=[f's{s}/{stream}' for s in b.SEEDS for stream,_ in STREAMS],
        endpoint=config['remote_url'],model=config['remote_model'],timeout_seconds=300,retries=0,
        total_conservative_token_budget=400000,per_request_output_tokens=2048,
        paired='One real proposal shared A/C or B/D. Ordinary decision saved before hidden history.',
        gates='Unchanged research43 current native gate and research31 reset-aware history gate; unknown rejects.',
        repeated='An unchanged executable non-keep proposal is rejected before compile; across-seed proposals never cached.',
        failure='Any transport failure terminates remaining calls. No retry or independent test on incomplete arms.',
        independent='All12 arms freeze first; fresh shared56-case batch. Exact candidate hashes share physical replay with bindings.',
        helpers='Same research44 AST/interface, component generation,300s transport, native cycle gates and sealed public projection in every arm.',
        no_policy_experiment=True,old_successful_candidates_or_independent_tests_in_requests=False,
        request_hashes=hashes,prior_protocol_sha256=b.search.digest(P/'continuation_protocol.json'),sealed_at=time.time()))
    dump(out/'code_versions.json',{p.relative_to(ROOT).as_posix():b.search.digest(p) for p in (ROOT/'scripts').glob('*.py')})
    dump(out/'sealed.json',{p.relative_to(out).as_posix():b.search.digest(p) for p in out.rglob('*.json')})
    print('PREPARED',len(checks),'checks;6 unchanged requests;0 real calls',flush=True)


def verify(prep):
    prepared.verify(P)
    for rel,h in read(prep/'sealed.json').items():assert b.search.digest(prep/rel)==h,rel
    for rel,h in read(prep/'code_versions.json').items():assert b.search.digest(ROOT/rel)==h,rel
    for p,h in read(prep/'request_bindings.json').items():assert b.search.digest(Path(p))==h,p


def run(prep,out,authorization):
    verify(prep);protocol=read(prep/'protocol.json');auth=read(authorization)
    assert auth['authorized_calls']==6 and auth['purpose']=='research71_single_step_paired'
    assert auth['protocol_sha256']==b.search.digest(prep/'protocol.json')
    assert auth['run_output']==out.relative_to(ROOT).as_posix()
    out.mkdir(parents=True,exist_ok=False);dump(out/'authorization.json',auth);dump(out/'protocol.json',protocol)
    initial=read(P/'shared_initial.json');history=read(P/'history_cases.json')
    binding=read(P/'history_binding.json');hp=b.gate.portable(binding['path'])
    assert b.search.digest(hp)==binding['sha256'];historical=read(hp)
    models=[];decisions={};frozen={};reserved=0;status='running'
    try:
        with b.extension.installed():
            for seed in b.SEEDS:
                ready=P/'ready'/f's{seed}'
                for stream,names in STREAMS:
                    folder=out/'core'/f's{seed}'/stream
                    request=read(prep/f's{seed}'/stream/'request.preview.json')
                    config=read(ready/'model_config.json');config['max_model_calls']=1
                    spent=sum(c['prompt_tokens']+c['completion_tokens'] if c.get('prompt_tokens') is not None and c.get('completion_tokens') is not None
                              else c['token_budget_reservation'] for m in models for c in m.calls)
                    config['max_tokens']=protocol['total_conservative_token_budget']-spent
                    model=pilot.Model(folder/'model',config,request);models.append(model)
                    reserved+=1;assert reserved<=6
                    dump(out/'attempt_budget.json',dict(reserved=reserved,maximum=6,prior_token_charge=spent))
                    call,proposal=send_once(model,folder/'model_call',initial)
                    edit=read(folder/'model_call/model_edit.json') if proposal else None
                    repeated=bool(proposal and edit['operation']!='keep' and b.interface.executable_hash(proposal)==b.interface.executable_hash(initial))
                    before=b.campaign.baseline(ready,stream);cases=read(ready/stream/'cases.json')
                    after=b.loop.replay(proposal,folder/'visible_native',cases) if proposal and not repeated else None
                    plain=b.paired.current_decision(before,after,edit) if after else dict(accepted=False,reasons=[dict(kind='repeated_executable' if repeated else 'model_or_interface_failure')])
                    dump(folder/'plain_decision.json',plain)
                    ordinary,gated=names;key=f's{seed}/{ordinary}'
                    frozen[key]=b.journal(out/'arms'/key,initial,proposal,plain)
                    b.loop.freeze(out/'arms'/key,frozen[key],'ordinary_decision_before_hidden_history')
                    full=b.loop.replay(proposal,folder/'history_native',history) if proposal and not repeated else None
                    hg=b.gate.decide(historical['group']['ledger'],full['group']['ledger']) if full and full.get('group') else dict(accepted=False,reasons=[dict(kind='history_native_unavailable')])
                    dump(folder/'historical_gate.json',hg)
                    reasons=plain['reasons']+hg['reasons']
                    if full and not full['healthy']:reasons.append(dict(kind='history_native_or_legal_control_failure'))
                    gated_decision=dict(accepted=bool(plain['accepted'] and full and full['healthy'] and hg['accepted']),reasons=reasons)
                    kg=f's{seed}/{gated}';frozen[kg]=b.journal(out/'arms'/kg,initial,proposal,gated_decision)
                    b.loop.freeze(out/'arms'/kg,frozen[kg],'additional_history_gate_terminal')
                    summary=dict(proposal_hash=b.loop.sha(proposal) if proposal else None,call=call,
                        plain=plain,gated=gated_decision,history_counts=full['counts'] if full else None,
                        current_counts=after['counts'] if after else None,repeated_executable=repeated,
                        gate_incremental_rejection=bool(plain['accepted'] and not gated_decision['accepted']),
                        proposal_shared_by=list(names),single_real_call=True)
                    dump(folder/'pair_result.json',summary)
                    for name,d in ((ordinary,plain),(gated,gated_decision)):
                        k=f's{seed}/{name}';decisions[k]=dict(accepted=d['accepted'],frozen_hash=b.loop.sha(frozen[k]),
                            proposal_source=str(folder.relative_to(out)),proposal_hash=summary['proposal_hash'],search=stream=='search',gate=name==gated)
                        dump(out/'arms'/k/'decision.json',decisions[k])
                    print('PAIR',seed,stream,'ordinary',plain['accepted'],'history',gated_decision['accepted'],flush=True)
            barrier(decisions);dump(out/'all_arms_freeze.json',decisions)
            excluded=set(read(prep/'excluded_inputs.json')['input_hashes'])
            development=history+[c for s in b.SEEDS for n in ('common_cases.json','search_cases.json') for c in read(P/'ready'/f's{s}'/n)]
            common=None;evaluated={}
            for key,candidate in frozen.items():
                h=b.loop.sha(candidate)
                if h not in evaluated:
                    dest=out/'evaluation'/h;b.loop.freeze(dest/'core',candidate,'all12_arms_frozen_before_independent_generation')
                    b.holdout(dest,candidate,development,excluded,common)
                    if common is None:
                        common=read(dest/'independent/split.json');dump(out/'common_independent_split.json',common)
                    evaluated[h]=str(dest.relative_to(out))
                    print('INDEPENDENT',h,read(dest/'independent/summary.json')['all_five_pass_on_first_attributed_evidence'],flush=True)
                dump(out/'arms'/key/'evaluation_binding.json',dict(candidate_hash=h,physical_evaluation=evaluated[h],
                    shared_exact_candidate=True,logical_scenarios=56,unique_statistical_sample=False))
            status='six_proposals_twelve_paired_arms_completed'
    except TransportStop as exc:
        status='terminal_'+str(exc);dump(out/'transport_stop.json',dict(status=status,remaining_calls_not_sent=6-reserved,retry=False))
    except BaseException as exc:
        status='execution_exception';dump(out/'exception.json',dict(type=type(exc).__name__));raise
    finally:
        verify(prep)
        dump(out/'outcome.json',dict(status=status,calls=sum(len(m.calls) for m in models),reserved=reserved,max_calls=6,
            completed_arms=len(decisions),decisions=decisions,policy_experiment_started=False,research63_unchanged=True))
        dump(out/'cost.json',b.search.native_cost(out));print('TERMINAL',status,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('prepare','run'))
    p.add_argument('--out',type=Path,required=True);p.add_argument('--prepared',type=Path);p.add_argument('--authorization',type=Path)
    a=p.parse_args()
    if a.action=='prepare':prepare(a.out.resolve())
    else:run(a.prepared.resolve(),a.out.resolve(),a.authorization.resolve())
