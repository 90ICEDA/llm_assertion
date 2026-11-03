"""Selected temporal false-alarm recovery; two new authorized calls maximum."""
import argparse
import json
import shutil
import time
from pathlib import Path
import research100_presentation_pilot as old
import research103_temporal_feedback as temporal

p,x=old.p,old.x
ROOT,read,dump,sha=old.ROOT,old.read,old.dump,old.sha
SOURCE=ROOT/'deliverables/research100_prepare_20261025_r01'
VERSION=ROOT/'deliverables/research100_real_20261025_r01/T/v0'


def records(folder):return {c:read(folder/c/'result.json') for c in ('alignment','search','history')}


def prepare(out):
    old.verify(SOURCE);out.mkdir(parents=True,exist_ok=False)
    for n in ('initial.json','baseline_full.json','source_binding.json','history_cases.json','search_cases.json','excluded_words.json','protected93.json'):
        shutil.copy2(SOURCE/n,out/n)
    for rev in ('before','after'):shutil.copytree(SOURCE/rev,out/rev)
    proposal=read(VERSION/'model_call/candidate.json');dump(out/'proposal.json',proposal)
    rec=records(VERSION/'native');ev=read(VERSION/'native/decision.json')
    assert not ev['history']['accepted'] and sum(rec[c]['counts']['detections'] for c in ('history','search'))==690
    assert sum(rec[c]['counts']['false_positives'] for c in ('history','search'))==104
    req=temporal.request(proposal,rec,VERSION/'native',0);dump(out/'request.preview.json',req)
    reservation=sum(len(m['content'].encode()) for m in req['messages'])+2048+req['max_tokens']
    assert reservation<=40000
    protocol=dict(name='research104_temporal_binding_recovery',selection='Previously observed research100 T proposal; selected recovery, NOT randomized comparison or extension of research100 budget.',
        change='Add raw-marker-bound anchor/check/transaction-switch examples and actual detected first/held development controls. No predicate edits or forced timing choices.',
        acceptance='Unchanged current9 plus full151, all420 OP and270 BRANCH, required triggers, zero false alarms/misses/critical unknown and history all-property guard.',
        initial_active='Prior partial BRANCH baseline. Known rejected690-target proposal is edit context, never active accepted version.',
        maximum_calls=2,maximum_reserved_tokens_per_call=40000,token_budget=80000,seeds=[10407,10408],
        model=p.prior.transport.DEFAULT_MODEL,endpoint=p.prior.transport.DEFAULT_URL,temperature=0.2,output_token_cap=1024,
        timeout_seconds=300,max_wall_seconds=1200,retries=0,
        stopping='Accept immediately stops; transport failure stops; no retry, per-field plan loop, extra seed or quota transfer. Two calls maximum including invalid/repeated responses.',
        terminal='After full acceptance freeze and generate96 new independent words/four configs. Otherwise no new independent tests. Prior independent outcomes/accepted SVA never enter requests.',
        native_max_compile_execute_each=14,preparation_new_native=0,
        cost='This is a new separate budget; research100 remains failed4/4. Local preparation reuses its recorded native artifacts.',created=time.time())
    dump(out/'protocol.json',protocol)
    dump(out/'model_config.json',dict(remote_url=protocol['endpoint'],remote_model=protocol['model'],max_model_calls=2,
        max_tokens=80000,max_wall_seconds=1200,call_timeout=300,options=dict(seed=10407,temperature=0.2,num_predict=1024)))
    files=[SOURCE/'sealed.json',VERSION/'model_call/candidate.json',VERSION/'model_call/model_edit.json',VERSION/'native/decision.json']
    for c in ('alignment','search','history'):
        files+=[VERSION/'native'/c/'result.json']+[VERSION/'native'/c/r/'execute.log' for r in ('before','after')]
    dump(out/'reused_bindings.json',{f.relative_to(ROOT).as_posix():sha(f) for f in files})
    dump(out/'code_versions.json',{f.relative_to(ROOT).as_posix():sha(f) for f in (ROOT/'scripts').glob('*.py')})
    dump(out/'sealed.json',{f.relative_to(out).as_posix():sha(f) for f in list(out.glob('*.json'))+list(out.glob('before/*.sv'))+list(out.glob('after/*.sv'))})
    print('PREPARED104 max2 calls; reservation',reservation,flush=True)


def verify(prep):
    x.verify(prep);old.verify(SOURCE)
    for n,h in read(prep/'reused_bindings.json').items():assert sha(ROOT/n)==h


def grant_check(g,prep,out):
    assert g['purpose']=='research104_temporal_recovery' and type(g['authorized_calls']) is int and g['authorized_calls']==2
    assert g['endpoint']==p.prior.transport.DEFAULT_URL and g['model']==p.prior.transport.DEFAULT_MODEL
    assert g['prepared_sha256']==sha(prep/'sealed.json') and g['run_output']==out.relative_to(ROOT).as_posix()


def run(prep,out,authorization):
    verify(prep);grant=read(authorization);grant_check(grant,prep,out)
    out.mkdir(parents=True,exist_ok=False);dump(out/'authorization.json',grant);dump(out/'protocol.json',read(prep/'protocol.json'))
    initial=read(prep/'initial.json');active=initial;current=read(prep/'proposal.json');base=read(prep/'baseline_full.json')
    rec=records(VERSION/'native');native_folder=VERSION/'native';diagnostic=None
    model=p.Model(out/'service',read(prep/'model_config.json'));model.fixed=initial
    seen={x.signature(initial),x.signature(current)};budget=[];accepted=False;stopped=False;tests=None
    try:
        for i in range(2):
            req=temporal.request(current,rec,native_folder,i,diagnostic)
            if i==0:assert req==read(prep/'request.preview.json')
            reservation=sum(len(m['content'].encode()) for m in req['messages'])+2048+req['max_tokens'];assert reservation<=40000
            budget.append(dict(iteration=i,reservation=reservation,reserved_at=time.time(),request_sha256=x.old.acceptance.sha(req)))
            dump(out/'budget_ledger.json',budget);model.pending_request=req;folder=out/f'v{i}'
            call,candidate=model.call(folder/'model_call',current,'op_bit28_illegal',{},'temporal_recovery')
            reason=dict(kind='transport_or_interface',actual=call);ev=None
            if candidate is not None:
                if x.signature(candidate) in seen:reason=dict(kind='repeated_executable_proposal');candidate=None
                else:
                    seen.add(x.signature(candidate));ev,newrec=x.evaluate(candidate,folder/'native',base)
                    accepted=bool(ev['history']['accepted']);reason=dict(kind='native_measured',decision=ev)
                    current=candidate;rec=newrec;native_folder=folder/'native'
            if ev is None:diagnostic=dict(reason=reason,actual_model_text=read(folder/'model_call/response.assembled.json')['message']['content'])
            else:diagnostic=None
            active=x.journal(folder/'transition',active,candidate,accepted,reason)
            stopped=call['status']!='response_received';print('RECOVERY104',i,reason['kind'],accepted,flush=True)
            if accepted or stopped:break
        dump(out/'terminal/candidate.json',active)
        if accepted and not stopped:
            p.prior.p.independent(prep,out,dict(recovered=active));tests=read(out/'independent_summary.json')
    finally:
        dump(out/'cost.json',x.costs.native_cost(out))
        dump(out/'outcome.json',dict(actual_calls=len(model.calls),new_accepted_versions=int(accepted),transport_stopped=stopped,
            active_sha256=x.old.acceptance.sha(active),independent=tests,automatic_expansion=False))
        verify(prep)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('action',choices=['prepare','run'])
    ap.add_argument('--out',type=Path,required=True);ap.add_argument('--prepared',type=Path);ap.add_argument('--authorization',type=Path)
    a=ap.parse_args()
    if a.action=='prepare':prepare(a.out.resolve())
    else:run(a.prepared.resolve(),a.out.resolve(),a.authorization.resolve())
