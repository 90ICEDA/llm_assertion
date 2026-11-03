"""Bounded continuation of the authorized FIFO pilot; two unsent call slots.

Compact public evidence, same RTL/AST/spec/model, actual opener error capture.
No research63 tests are decoded. Old runs and old source files remain immutable.
"""
import argparse
import copy
from contextlib import contextmanager
import io
import json
from pathlib import Path
import time
import urllib.error
import urllib.request
from unittest.mock import patch
import research67_controlled_campaign as base
import research67_preflight as previous

ROOT,read,dump=base.ROOT,base.read,base.dump
ORIGIN=ROOT/'deliverables/research67_controlled_20261024_r01'
PREP=ORIGIN/'prepared_v4/s6703'


@contextmanager
def capture(folder):
    original=urllib.request.OpenerDirector.open
    def wrapped(opener,request,*args,**kwargs):
        try:return original(opener,request,*args,**kwargs)
        except urllib.error.HTTPError as error:
            raw=error.read(65537);body=raw[:65536].decode('utf-8',errors='replace')
            auth=next((v for k,v in request.header_items() if k.lower()=='authorization'),'')
            for token in (auth,auth.removeprefix('Bearer ')):
                if token:body=body.replace(token,'[REDACTED_CREDENTIAL]')
            dump(Path(folder)/'service_error_response.json',dict(status=error.code,body=body,truncated=len(raw)>65536))
            raise
    with patch.object(urllib.request.OpenerDirector,'open',wrapped):yield


class Model(base.campaign.Model):
    def call(self,folder,*args,**kwargs):
        with capture(folder):return super().call(folder,*args,**kwargs)


def compact(request):
    value=copy.deepcopy(request);body=json.loads(value['messages'][1]['content'])
    public=body['ordinary_observations']
    rows=[]
    for record in public['native_diagnostic']:
        d=record['diagnostic']
        rows.append(dict(scenario=record['scenario'],
            target_evidence=d.get('target_evidence',[]),
            fixed={k:d.get('fixed',{}).get(k) for k in ('mode','native_summary','oracle_summary') if k in d.get('fixed',{})},
            mutant={k:d.get('mutant',{}).get(k) for k in ('mode','native_summary','oracle_summary') if k in d.get('mutant',{})}))
    body['ordinary_observations']=dict(scenario=public['scenario'],counts=public['counts'],native_diagnostic=rows,
        projection='Deterministic per-scenario target records and summaries; exact adjacent target samples remain in actual_observations. Full local raw records are retained, not repeatedly inlined.')
    value['messages'][1]['content']=json.dumps(body,separators=(',',':'))
    return value


def local_checks(out,request):
    checks=[];settings=base.campaign.settings(base.PILOT,2)
    model=Model(out/'transport_fixture',settings,request)
    secret='fixture-not-an-authentication-key'
    key=out/'fixture_key.txt';key.parent.mkdir(parents=True,exist_ok=True);key.write_text(secret)
    model.key_file=key
    called=[]
    def fail(opener,req,*args,**kwargs):
        called.append(1)
        raise urllib.error.HTTPError(req.full_url,400,'fixture',{},io.BytesIO(('fixture '+secret).encode()))
    # Exact inherited RemoteModel.call path, fake opener only. Never real network.
    with patch.object(urllib.request.OpenerDirector,'open',fail):
        call,candidate=model.call(out/'transport_fixture/call',read(PREP/'shared_initial.json'),'stall_stability',{},'local_fixture')
    saved=read(out/'transport_fixture/call/service_error_response.json')
    assert len(called)==1 and call['status']=='service_http_error' and candidate is None
    assert secret not in json.dumps(saved) and '[REDACTED_CREDENTIAL]' in saved['body']
    assert saved['status']==400
    checks.extend(['actual opener path captured','exact inherited call returned HTTP failure','single fixture send','credential redacted','no fixture candidate'])
    # Both requests contain unchanged semantic payload; only the common verbose
    # diagnostic representation is compressed, equally for every prospective arm.
    for stream in ('ordinary','search'):
        original=read(PREP/stream/'request.preview.json');modified=compact(original)
        a=json.loads(original['messages'][1]['content']);b=json.loads(modified['messages'][1]['content'])
        for key in a:
            if key!='ordinary_observations':assert a[key]==b[key],key
        checks.append(stream+' semantic fields preserved')
        assert a['ordinary_observations']['counts']==b['ordinary_observations']['counts']
        checks.append(stream+' counts preserved')
    return checks


def prepare(out):
    previous.verify(ORIGIN,PREP)
    out.mkdir(parents=True,exist_ok=False)
    oldcall=read(ORIGIN/'pilot_run/refinement/core/v0/model_call/transport_result.json')
    assert read(ORIGIN/'pilot_run/outcome.json')['calls']==1
    for stream in ('ordinary','search'):dump(out/stream/'request.preview.json',compact(read(PREP/stream/'request.preview.json')))
    tests=local_checks(out/'local_checks',read(out/'search/request.preview.json'))
    a=json.loads(read(out/'ordinary/request.preview.json')['messages'][1]['content'])
    b=json.loads(read(out/'search/request.preview.json')['messages'][1]['content'])
    for k in ('ordinary_observations','rtl_and_common_contract','output_schema','current_assertions','temporal_semantics'):assert a[k]==b[k]
    selected=read(PREP/'search_cases.json')
    assert all(c['id'] in json.dumps(b['actual_observations']) and c['id'] not in json.dumps(a) for c in selected)
    settings=base.campaign.settings(base.PILOT,2)
    settings['max_tokens']-=oldcall['token_budget_reservation']
    dump(out/'model_config.json',settings)
    dump(out/'protocol.json',dict(previous_protocol_hash=base.search.digest(ORIGIN/'protocol.json'),
        previous_preparation_hash=base.search.digest(PREP/'sealed.json'),maximum_calls=2,
        previous_actual_calls=1,total_pilot_cap=3,prior_unknown_token_reservation=oldcall['token_budget_reservation'],
        new_token_budget=settings['max_tokens'],seed=base.PILOT,transport_retries=0,
        authority='Latest user instruction to resolve service rejection and continue this same pilot, within the two unused slots of the explicit three-call grant. No multiseed grant inferred.',
        common_helper_amendment='Compact duplicate public diagnostics equally for ordinary/search, same original RTL, specifications, AST, operands, actual target windows, model/sampling. Applied before continuation calls, not claimed as core-mechanism benefit.',
        transport='Capture OpenerDirector.open errors, redact credential, preserve bounded upstream body; non-response_received stops immediately; no automatic service retry.',
        stages='Visible target and required trigger check, then105 history. Accept only both pass; freeze accepted set, generate fresh independent cases. Any failure stops multiseed.',
        scope='Continuation after observed service failure, not a fresh untouched prospective pilot or a mechanism efficacy comparison.',
        status='sealed_before_new_calls',prepared_at=time.time()))
    dump(out/'checks.json',dict(passed=True,checks=tests,fixture_calls_not_experimental=True,
        bytes={s:len(json.dumps(read(out/s/'request.preview.json')).encode()) for s in ('ordinary','search')}))
    dump(out/'code_versions.json',{p.relative_to(ROOT).as_posix():base.search.digest(p) for p in (ROOT/'scripts').glob('*.py')})
    dump(out/'sealed.json',{p.relative_to(out).as_posix():base.search.digest(p) for p in out.rglob('*.json')})
    print('PREPARED',read(out/'checks.json'),flush=True)


def verify(prep):
    previous.verify(ORIGIN,PREP)
    for p,h in read(prep/'sealed.json').items():assert base.search.digest(prep/p)==h,p
    for p,h in read(prep/'code_versions.json').items():assert base.search.digest(ROOT/p)==h,p


def run(prep,out):
    verify(prep);out.mkdir(parents=True,exist_ok=False)
    initial=read(PREP/'shared_initial.json');current=initial
    before=base.campaign.baseline(PREP,'search');cases=read(PREP/'search/cases.json')
    history=read(PREP/'history_cases.json');binding=read(PREP/'history_binding.json')
    path=base.gate.portable(binding['path']);assert base.search.digest(path)==binding['sha256'];historic=read(path)
    request=read(prep/'search/request.preview.json');model=Model(out/'model',read(prep/'model_config.json'),request)
    status='running';passed=False;accepted=False;previous_edit=None;seen={base.interface.executable_hash(initial)}
    dump(out/'authorization_binding.json',dict(original_grant=str(ORIGIN/'pilot_authorization.json'),original_calls=1,
        continuing_user_instruction='解决服务拒绝，再完成先导的目标检查、105场景历史回放和新独立验收；通过后才开展多种子两类消融。',
        maximum_new_calls=2,multiseed_calls_authorized=False,request_sha256=base.search.digest(prep/'search/request.preview.json')))
    try:
        with base.extension.installed():
            for i in range(2):
                folder=out/'core'/f'v{i}'
                # Do not count a reservation as a transmitted request. The
                # inherited transport creates attempt.json only after prechecks.
                call,proposal=model.call(folder/'model_call',current,'stall_stability',{},'service_fixed_pilot')
                dump(out/'attempt_budget.json',dict(actual_new_calls=len(model.calls),previous_actual_calls=1,total_cap=3))
                assert len(model.calls)+1<=3
                if call['status']!='response_received':
                    status='terminal_'+call['status'];dump(folder/'terminal_stop.json',dict(status=status,retry=False));break
                edit=read(folder/'model_call/model_edit.json') if (folder/'model_call/model_edit.json').exists() else None
                repeated=bool(proposal and edit['operation']!='keep' and base.interface.executable_hash(proposal) in seen)
                if proposal:seen.add(base.interface.executable_hash(proposal))
                small=base.loop.replay(proposal,folder/'target_native',cases) if proposal and not repeated else None
                plain=base.paired.current_decision(before,small,edit) if small else dict(accepted=False,reasons=[dict(kind='repeat' if repeated else 'interface_failure')])
                dump(folder/'target_gate.json',plain)
                # Only a target-qualified version enters the expensive105 check.
                full=base.loop.replay(proposal,folder/'history_native',history) if plain['accepted'] else None
                hg=base.gate.decide(historic['group']['ledger'],full['group']['ledger']) if full and full.get('group') else dict(accepted=False,reasons=[])
                accepted=bool(plain['accepted'] and full and full['healthy'] and hg['accepted'])
                reasons=plain['reasons']+hg['reasons']
                if full and not full['healthy']:reasons.append(dict(kind='history_native_unhealthy'))
                decision=dict(accepted=accepted,reasons=reasons,ordinary_accepted=plain['accepted'],history=hg,call=call)
                dump(folder/'decision.json',decision);current=base.journal(folder,current,proposal,decision)
                print('VERSION',i,'target',plain['accepted'],'accepted',accepted,flush=True)
                if accepted:break
                diagnostic=base.campaign.attempt_feedback(small,full,decision,call,edit,previous_edit)
                dump(folder/'next_feedback.json',diagnostic)
                model.request=base.campaign.request_from(request,current,base.PILOT,diagnostic);previous_edit=edit
            if not accepted:
                if status=='running':status='refinement_unresolved'
                dump(out/'retained_candidate.json',current);return
            base.loop.freeze(out/'core',current,'accepted_target_and105_before_new_test_generation')
            excluded,sources=previous.exclusions(ORIGIN)
            development=history+read(PREP/'common_cases.json')+read(PREP/'search_cases.json')
            dump(out/'exclusion_manifest.json',dict(input_hashes=sorted(excluded|{base.loop.sha(c['rows']) for c in development}),sources=sources))
            base.holdout(out,current,development,excluded)
            passed=read(out/'independent/summary.json')['all_five_pass_on_first_attributed_evidence']
            status='pilot_passed' if passed else 'independent_failed_no_multiseed'
    except BaseException as exc:
        status='execution_exception';dump(out/'exception.json',dict(type=type(exc).__name__,detail=str(exc)));raise
    finally:
        verify(prep)
        dump(out/'outcome.json',dict(status=status,accepted=accepted,pilot_passed=passed,
            actual_new_calls=len(model.calls),prior_calls=1,remaining_slots=2-len(model.calls),
            multiseed_started=False,research63_unchanged=base.protected()==read(ORIGIN/'protected_research63.json')))
        dump(out/'cost.json',base.search.native_cost(out))
        print('TERMINAL',status,'actual_new_calls',len(model.calls),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('prepare','run'));p.add_argument('--out',type=Path,required=True);p.add_argument('--prepared',type=Path)
    a=p.parse_args()
    if a.action=='prepare':prepare(a.out.resolve())
    else:run(a.prepared.resolve(),a.out.resolve())
