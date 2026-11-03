"""Prepared two-call remote recovery; explicit purpose-bound grant required."""
import argparse
import copy
import json
import shutil
import time
from pathlib import Path
import research90_text_recovery as p
import research69_deadline_transport as transport

x=p.x
ROOT,read,dump,sha=p.ROOT,p.read,p.dump,p.sha
P90=ROOT/'deliverables/research90_prepare_20261025_r01'
R90=ROOT/'deliverables/research90_real_20261025_r01'


def payload(current,feedback,iteration):
    req=p.request(current,feedback,iteration)
    return dict(model=transport.DEFAULT_MODEL,messages=req['messages'],stream=True,
        stream_options={'include_usage':True},response_format={'type':'json_object'},
        temperature=0.2,seed=9207+iteration,max_tokens=1024)


def validate_grant(auth,prep,out):
    assert auth['purpose']=='research92_remote_recovery'
    assert type(auth['authorized_calls']) is int and auth['authorized_calls']==2
    assert auth['endpoint']==transport.DEFAULT_URL and auth['model']==transport.DEFAULT_MODEL
    assert auth['prepared_sha256']==sha(prep/'sealed.json')
    assert auth['run_output']==out.relative_to(ROOT).as_posix()


class Model(transport.RemoteModel):
    def _payload(self,current,target,feedback,phase):return payload(current,feedback,len(self.calls))

    def save_decoded_output(self,folder,value,current,secret):
        candidate,mapping=p.TEXT_ADAPT(value,self.fixed)
        dump(folder/'candidate.json',candidate);dump(folder/'label_mapping.json',mapping)
        (folder/'candidate.sva').write_text('\n'.join(a['property'] for a in candidate['assertions'])+'\n')
        return candidate,'exact_text_expressions_plus_fixed_branch'


def prepare(out):
    x.verify(P90);assert read(R90/'outcome.json')['new_calls']==2
    out.mkdir(parents=True,exist_ok=False)
    for n in ('initial.json','proposal.json','baseline_full.json','source_binding.json','qualification.json','history_cases.json','search_cases.json'):
        shutil.copy2(P90/n,out/n)
    for rev in ('before','after'):shutil.copytree(P90/rev,out/rev)
    exclusions=set(read(P90/'excluded_words.json'))
    exclusions.update(t['instruction'] for t in read(R90/'independent_cases.json'))
    dump(out/'excluded_words.json',sorted(exclusions))
    feedback=read(P90/'initial_feedback.json')
    feedback['prior_local_attempts']=[dict(edit=read(R90/f'B/v{i}/model_call/model_edit.json'),
        actual_rejection=read(R90/f'B/v{i}/transition/transition.json')['reason']) for i in (0,1)]
    dump(out/'initial_feedback.json',feedback)
    req=payload(read(out/'proposal.json'),feedback,0);dump(out/'request.preview.json',req)
    config=dict(remote_url=transport.DEFAULT_URL,remote_model=transport.DEFAULT_MODEL,
        max_model_calls=2,max_tokens=60000,max_wall_seconds=1200,call_timeout=300,
        options=dict(seed=9207,temperature=0.2,num_predict=1024))
    dump(out/'model_config.json',config)
    protocol=read(P90/'protocol.json')
    protocol.update(created=time.time(),name='research92_remote_recovery',model=transport.DEFAULT_MODEL,
        endpoint=transport.DEFAULT_URL,seeds=[9207,9208],maximum_calls=2,
        prior_budget='research87 and90 remain failed2/2 local pilots; no pooling or retroactive extension.',
        terminal='Only after native acceptance freeze both arms and generate96 new words; exclude research90 inputs too. No independent result enters feedback.',
        authorization_required=True,retries=0,transport_failure_stops=True)
    protocol['budget'].update(new_local_calls=0,remote_calls=2,per_call_timeout=300,
        total_call_tokens=60000,per_call_output_tokens=1024,context='provider tokenizer unavailable')
    dump(out/'protocol.json',protocol)
    known=[p.PREVIOUS/'qualification/decision.json',P90/'sealed.json',R90/'B/v0/model_call/model_edit.json',
        R90/'B/v1/model_call/model_edit.json',P90/'initial_feedback.json']
    dump(out/'reused_bindings.json',{f.relative_to(ROOT).as_posix():sha(f) for f in known})
    checks=dict(no_remote_calls=True,credential_read=False,secret_logged=False,
        key_file_exists=(ROOT/'.secrets/qwen_api_key.txt').is_file(),
        unchanged_text_frontend=True,unchanged_native_acceptance=True,
        first_request_conservative_reservation=sum(len(m['content'].encode()) for m in req['messages'])+2048+1024,
        prior_independent_used_only_for_input_exclusion=True)
    try:validate_grant(dict(authorized_calls=0),out,out/'not_a_run')
    except (AssertionError,KeyError):checks['missing_grant_rejected_before_model_creation']=True
    else:raise AssertionError('grant accepted')
    assert checks['first_request_conservative_reservation']*2<=60000
    dump(out/'checks.json',checks)
    dump(out/'code_versions.json',{f.relative_to(ROOT).as_posix():sha(f) for f in (ROOT/'scripts').glob('*.py')})
    dump(out/'sealed.json',{f.relative_to(out).as_posix():sha(f) for f in list(out.glob('*.json'))+list(out.glob('before/*.sv'))+list(out.glob('after/*.sv'))})
    print('PREPARED92',checks,flush=True)


def run(prep,out,grant):
    x.verify(prep);auth=read(grant);validate_grant(auth,prep,out)
    for n,h in read(prep/'reused_bindings.json').items():assert sha(ROOT/n)==h,n
    out.mkdir(parents=True,exist_ok=False)
    dump(out/'authorization.json',auth);dump(out/'protocol.json',read(prep/'protocol.json'))
    model=Model(out/'service',read(prep/'model_config.json'))
    initial=read(prep/'initial.json');proposal=read(prep/'proposal.json');active=initial
    model.fixed=initial;feedback=read(prep/'initial_feedback.json');accepted=False;budget=[]
    ordinary=x.journal(out/'A/initial',initial,proposal,True,'Unchanged R0 accepts initial proposal.')
    x.journal(out/'B/initial',initial,proposal,False,'Unchanged historical R1 rejects636 legal false alarms.')
    seen={x.signature(initial),x.signature(proposal)}
    try:
        for i in range(2):
            folder=out/'B'/f'v{i}'
            req=payload(proposal,feedback,i)
            if i==0:assert req==read(prep/'request.preview.json')
            budget.append(dict(iteration=i,reserved_at=time.time(),request_sha256=x.old.acceptance.sha(req)))
            dump(out/'budget_ledger.json',budget)
            call,candidate=model.call(folder/'model_call',proposal,'op_bit28_illegal',feedback,'recovery')
            accepted=False;decision=dict(accepted=False,reason='transport_or_interface_failure',actual=call)
            if candidate is not None:
                if x.signature(candidate) in seen:
                    decision=dict(accepted=False,reason='repeated_executable_proposal');candidate=None
                else:seen.add(x.signature(candidate))
            if candidate is not None:
                ev,records=x.evaluate(candidate,folder/'native',read(prep/'baseline_full.json'))
                accepted=ev['history']['accepted'];decision=ev
                proposal=candidate;feedback=x.diagnostics(ev,records)
            else:
                feedback=dict(actual_rejection=decision,actual_model_text=read(folder/'model_call/response.assembled.json')['message']['content'],previous_verified_diagnostics=feedback)
            active=x.journal(folder/'transition',active,candidate,accepted,decision)
            print('REMOTE92',i,call['status'],accepted,flush=True)
            if accepted or call['status']!='response_received':break
        if accepted:p.independent(prep,out,dict(A=ordinary,B=active))
        else:dump(out/'terminal_freeze.json',dict(A=x.old.acceptance.sha(ordinary),B=x.old.acceptance.sha(active),new_independent_not_started=True))
    finally:
        cost=x.costs.native_cost(out);dump(out/'cost.json',cost)
        tests=read(out/'independent_summary.json') if (out/'independent_summary.json').exists() else None
        dump(out/'outcome.json',dict(actual_model_calls=len(model.calls),new_accepted_versions=int(accepted),
            independent_passed=tests['B']['passed'] if tests else None,
            bounded_recovery_success=bool(accepted and tests and tests['B']['passed']),
            active_sha256=x.old.acceptance.sha(active),remote_calls=len(model.calls)))
        x.verify(prep)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('action',choices=['prepare','run'])
    ap.add_argument('--out',type=Path,required=True);ap.add_argument('--prepared',type=Path);ap.add_argument('--authorization',type=Path)
    a=ap.parse_args()
    if a.action=='prepare':prepare(a.out.resolve())
    else:run(a.prepared.resolve(),a.out.resolve(),a.authorization.resolve())
