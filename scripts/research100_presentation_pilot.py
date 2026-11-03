"""Fixed two-presentation pilot, two calls per arm, no automatic expansion."""
import argparse
import copy
import json
import shutil
import time
from pathlib import Path
import research99_request_presentation as fmt

p=fmt.prior;x=p.x
ROOT,read,dump,sha=p.ROOT,p.read,p.dump,p.sha
SOURCE=ROOT/'deliverables/research94_prepare_20261025_r01'
ARMS=('C','T')


def initial_records():
    return {c:read(SOURCE/'baseline_native'/c/'result.json') for c in ('alignment','search','history')}


def prepare(out):
    x.verify(SOURCE);out.mkdir(parents=True,exist_ok=False)
    for n in ('initial.json','baseline_full.json','source_binding.json','history_cases.json','search_cases.json','excluded_words.json','protected93.json'):
        shutil.copy2(SOURCE/n,out/n)
    for rev in ('before','after'):shutil.copytree(SOURCE/rev,out/rev)
    records=initial_records();visible=p.feedback(None,records,False)
    dump(out/'initial_feedback.json',visible)
    for arm in ARMS:dump(out/arm/'request.preview.json',fmt.request(read(out/'initial.json'),visible,records,arm,0))
    protocol=dict(name='research100_paired_presentation_pilot',task='Original Ibex #166 known OP repair; same initial partial BRANCH baseline.',
        contrast='C old internal candidate fields and raw paired rows; T editable fields only and sample-bound decoded table. Both mark old candidate failed and state the identical output whitelist. This is a package contrast, not separate field/decoding causal attribution.',
        information='C/T same selected evidence IDs and complete paired native rows; T table expands exactly to C raw pairs. Both initially see current9/search36 only; rejected continuations see their own current9/search36/history115. Never the other arm response.',
        change_from94='Both arms explicitly receive paired revision rows; this is a new sealed experiment. Research94 is not the information-matched control. No reuse of research93 successful SVA or independent outcomes.',
        acceptance='Same x.evaluate, full151 + current9 first/held12, old preservation and all-property guards; no acceptance change or bit-text shortcut.',
        model=p.prior.transport.DEFAULT_MODEL,endpoint=p.prior.transport.DEFAULT_URL,
        seeds=[10007,10008],temperature=0.2,output_token_cap=1024,
        maximum_calls=4,maximum_calls_per_arm=2,maximum_reserved_tokens_per_call=30000,
        maximum_token_budget=120000,timeout_seconds=300,max_wall_seconds=2400,retries=0,
        call_order=['C0','T0','C1_if_rejected','T1_if_rejected'],
        stopping='Accepting arm stops. Transport failure globally stops. No retry, quota transfer or new seed. Interface/repeat rejection can use only its one remaining call. Exceptions stop; do not rerun output directory.',
        terminal='All arms terminal before freezing. If at least one new accepted version and no transport failure, generate96 fresh words, four configs, replay both terminal versions; no acceptance selection on test results.',
        native_budget=dict(maximum_compile_execute_each=28,preparation_new_native=0,reused_research94_preparation=18),
        scope='Single fixed seed presentation pilot; not two-core-mechanism benefit, not stable success rate. No automatic expansion even on success.',created=time.time())
    dump(out/'protocol.json',protocol)
    dump(out/'model_config.json',dict(remote_url=protocol['endpoint'],remote_model=protocol['model'],max_model_calls=4,
        max_tokens=120000,max_wall_seconds=2400,call_timeout=300,options=dict(seed=10007,temperature=0.2,num_predict=1024)))
    dump(out/'reused_bindings.json',{f.relative_to(ROOT).as_posix():sha(f) for f in [SOURCE/'sealed.json']+
        [SOURCE/'baseline_native'/c/'result.json' for c in ('alignment','search','history')]})
    dump(out/'code_versions.json',{f.relative_to(ROOT).as_posix():sha(f) for f in (ROOT/'scripts').glob('*.py')})
    paths=list(out.glob('*.json'))+list(out.glob('*/*.json'))+list(out.glob('before/*.sv'))+list(out.glob('after/*.sv'))
    dump(out/'sealed.json',{f.relative_to(out).as_posix():sha(f) for f in paths})
    print('PREPARED100 C/T max4 calls; no model call',flush=True)


def verify(prep):
    x.verify(prep);x.verify(SOURCE)
    for name,h in read(prep/'reused_bindings.json').items():assert sha(ROOT/name)==h
    assert p.protected_snapshot()==read(prep/'protected93.json')


def grant_check(grant,prep,out):
    assert grant['purpose']=='research100_presentation_pilot'
    assert type(grant['authorized_calls']) is int and grant['authorized_calls']==4
    assert grant['endpoint']==p.prior.transport.DEFAULT_URL and grant['model']==p.prior.transport.DEFAULT_MODEL
    assert grant['prepared_sha256']==sha(prep/'sealed.json')
    assert grant['run_output']==out.relative_to(ROOT).as_posix()


def run(prep,out,authorization):
    verify(prep);grant=read(authorization);grant_check(grant,prep,out)
    out.mkdir(parents=True,exist_ok=False);dump(out/'authorization.json',grant);dump(out/'protocol.json',read(prep/'protocol.json'))
    initial=read(prep/'initial.json');base=read(prep/'baseline_full.json')
    model=p.Model(out/'service',read(prep/'model_config.json'));model.fixed=initial
    active={a:initial for a in ARMS};current={a:initial for a in ARMS}
    visible={a:read(prep/'initial_feedback.json') for a in ARMS};records={a:initial_records() for a in ARMS}
    diagnostics={a:None for a in ARMS};seen={a:{x.signature(initial)} for a in ARMS}
    states={a:dict(accepted=False,calls=0) for a in ARMS};budget=[];stopped=False;tests=None
    try:
        for iteration in range(2):
            for arm in ARMS:
                if stopped or states[arm]['accepted']:continue
                req=fmt.request(current[arm],visible[arm],records[arm],arm,iteration,diagnostics[arm])
                if iteration==0:assert req==read(prep/arm/'request.preview.json')
                reservation=sum(len(m['content'].encode()) for m in req['messages'])+2048+req['max_tokens']
                assert reservation<=30000 and len(budget)<4 and states[arm]['calls']<2
                folder=out/arm/f'v{iteration}';model.pending_request=req
                budget.append(dict(arm=arm,iteration=iteration,reserved_at=time.time(),reservation=reservation,
                    request_sha256=x.old.acceptance.sha(req)));dump(out/'budget_ledger.json',budget)
                call,candidate=model.call(folder/'model_call',current[arm],'op_bit28_illegal',visible[arm],'presentation')
                states[arm]['calls']+=1
                reason=dict(kind='transport_or_interface',actual=call);accepted=False;ev=None
                if candidate is not None:
                    if x.signature(candidate) in seen[arm]:reason=dict(kind='repeated_executable_proposal');candidate=None
                    else:
                        seen[arm].add(x.signature(candidate))
                        ev,rec=x.evaluate(candidate,folder/'native',base)
                        accepted=bool(ev['history']['accepted']);reason=dict(kind='native_measured',decision=ev)
                        current[arm]=candidate;records[arm]=rec;visible[arm]=p.feedback(ev,rec,True)
                if ev is None:
                    text=read(folder/'model_call/response.assembled.json')['message']['content']
                    diagnostics[arm]=dict(reason=reason,actual_model_text=text)
                else:diagnostics[arm]=None
                active[arm]=x.journal(folder/'transition',active[arm],candidate,accepted,reason)
                states[arm]['accepted']=accepted;dump(out/'states.json',states)
                stopped=call['status']!='response_received'
                print('PRESENTATION100',arm,iteration,call['status'],reason['kind'],accepted,flush=True)
            if stopped:break
        for arm,c in active.items():dump(out/'terminal'/arm/'candidate.json',c)
        dump(out/'terminal_versions.json',{a:x.old.acceptance.sha(c) for a,c in active.items()})
        if not stopped and any(s['accepted'] for s in states.values()):
            p.prior.p.independent(prep,out,active);tests=read(out/'independent_summary.json')
    finally:
        dump(out/'cost.json',x.costs.native_cost(out));dump(out/'states.json',states)
        dump(out/'outcome.json',dict(actual_calls=len(model.calls),states=states,transport_stopped=stopped,
            unique_new_accepted_versions=len({x.old.acceptance.sha(active[a]) for a in ARMS if states[a]['accepted']}),
            independent={a:t['passed'] for a,t in tests.items()} if tests else None,automatic_expansion=False))
        verify(prep)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('action',choices=['prepare','run'])
    ap.add_argument('--out',type=Path,required=True);ap.add_argument('--prepared',type=Path);ap.add_argument('--authorization',type=Path)
    a=ap.parse_args()
    if a.action=='prepare':prepare(a.out.resolve())
    else:run(a.prepared.resolve(),a.out.resolve(),a.authorization.resolve())
