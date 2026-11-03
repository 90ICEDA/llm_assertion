"""Bounded genuine continuation of a retrospectively qualified regression.

Prepare is local only. Run requires a new explicit grant, never transfers unused
slots from research72. No archived successful proposal enters the request.
"""
import argparse
import json
import time
from pathlib import Path
import research73_discriminating as screen
import research72_policy as policy

b,ROOT,read,dump = policy.b,policy.ROOT,policy.read,policy.dump
SEED=7403
MAX_CALLS=2


def prepare(source,audit,out):
    assert read(audit/'audit.json')['passed']
    qualified=[r for r in read(audit/'qualified.json') if r['confirmed_loss']]
    assert qualified,'no confirmed lost-detection candidate'
    chosen=qualified[0];slot=f"c{chosen['index']:02d}"
    out.mkdir(parents=True,exist_ok=False)
    initial=read(source/'initial.json');folder=source/slot
    old=read(folder/'source.json');model_dir=(ROOT/old['path']).parent
    decision=read(folder/'decision.json')['full']
    assert decision['ordinary_accepted'] and decision['gate_incremental_rejection']
    small=read(folder/'public/result.json');full=read(folder/'history/result.json')
    call=read(model_dir/'result.json');edit=read(model_dir/'model_edit.json')
    diagnostic=policy.feedback_for(small,full,decision,call,edit,None,True)
    diagnostic['provenance']='Actual archived model proposal, freshly replayed in research73; retrospective qualification, not a fresh randomized arm.'
    source_request=read(policy.P/'ready/s6711/ordinary/request.preview.json')
    request=b.campaign.request_from(source_request,initial,SEED,diagnostic)
    dump(out/'request.preview.json',request)
    dump(out/'development_feedback.json',diagnostic)
    dump(out/'initial.json',initial)
    for name in ('cases.json','history_cases.json'):
        dump(out/name,read(source/name))
    dump(out/'bindings.json',dict(source=str(source),audit=str(audit),candidate_slot=slot,
        initial_hash=b.loop.sha(initial),
        files={str(p):b.search.digest(p) for p in (source/'baseline_public/result.json',source/'baseline_history/result.json',
            folder/'candidate.json',folder/'public/result.json',folder/'history/result.json',folder/'decision.json',audit/'audit.json')}))
    config=b.campaign.settings(SEED,MAX_CALLS)
    dump(out/'model_config.json',config)
    dump(out/'protocol.json',dict(maximum_calls=MAX_CALLS,seed=SEED,retries=0,
        endpoint=config['remote_url'],model=config['remote_model'],timeout_seconds=300,
        ordinary='Unchanged research43 current_decision on fixed14 public cases.',
        history='Unchanged research72 decision_for plus fixed105 historical cases and research31 applicability.',
        selection='First source-ordered archived proposal with ordinary pass and independently confirmed historical detection loss in research73 audit.',
        acceptance='Public target trigger/detection, no legal FP or critical unknown, full105 native health and historical gate all pass. Repetition rejected before native execution.',
        stop='Stop at first full acceptance or any transport failure; at most two independent attempts, no retries.',
        state='Reject keeps qualified partial baseline; accepted proposal frozen with hash. No historical rewrite.',
        estimand='Selected retrospective regression followed by prospective bounded repair; NOT randomized mechanism benefit or multiseed strategy estimate.',
        isolation='Only baseline, failed real proposal and development diagnostics. No archive success or old/new independent tests.',
        independent='Not performed by this acceptance-only runner. Any accepted new version requires a fresh post-freeze holdout before independent-success claims.',
        authorization='Requires NEW <=2 grant for this protocol. No research72 remainder transferred.'))
    # Reject accidental insertion of an archived success, test data, or secret.
    body=json.loads(request['messages'][1]['content'])
    assert body['current_assertions']==[{k:v for k,v in a.items() if k!='reason'} for a in initial['assertions']]
    assert body['actual_previous_attempt']['previous_actual_model_edit']==edit
    assert 'historical_replay' in body['actual_previous_attempt']
    assert not any(x in json.dumps(request) for x in ('research71','research72','research63','frozen_candidate','api_key','Authorization:'))
    dump(out/'checks.json',dict(passed=True,qualified_actual_regression=True,initial_unchanged=True,
        actual_edit_only=True,hidden_history_development_only=True,no_model_calls=True,credential_read=False))
    dump(out/'code_versions.json',{str(p):b.search.digest(p) for p in (ROOT/'scripts').glob('*.py')})
    dump(out/'sealed.json',{p.name:b.search.digest(p) for p in out.glob('*.json')})
    print('PREPARED',slot,'max_calls',MAX_CALLS,flush=True)


def execute(prepared,out,authorization):
    for name,h in read(prepared/'sealed.json').items():assert b.search.digest(prepared/name)==h,name
    for name,h in read(prepared/'code_versions.json').items():assert b.search.digest(Path(name))==h,name
    bindings=read(prepared/'bindings.json')
    for name,h in bindings['files'].items():assert b.search.digest(Path(name))==h,name
    auth=read(authorization);protocol=read(prepared/'protocol.json')
    assert auth['authorized_calls']==MAX_CALLS and auth['endpoint']==protocol['endpoint'] and auth['model']==protocol['model']
    assert auth['prepared_sha256']==b.search.digest(prepared/'sealed.json') and auth['run_output']==out.relative_to(ROOT).as_posix()
    out.mkdir(parents=True,exist_ok=False)
    dump(out/'authorization.json',auth);dump(out/'protocol.json',protocol)
    source=Path(bindings['source']);initial=read(prepared/'initial.json');current=initial
    before=read(source/'baseline_public/result.json');historical=read(source/'baseline_history/result.json')
    request=read(prepared/'request.preview.json');config=read(prepared/'model_config.json')
    model=policy.Model(out/'model',config,request);seen={b.interface.executable_hash(initial),b.interface.executable_hash(read(source/bindings['candidate_slot']/'candidate.json'))}
    decisions=[];accepted=False;status='exhausted';last_edit=None
    with b.extension.installed():
        for iteration in range(MAX_CALLS):
            folder=out/'core'/f'v{iteration}'
            dump(out/'attempt_budget.json',dict(reserved=iteration+1,maximum=MAX_CALLS,started=time.time()))
            call,proposal=model.call(folder/'model_call',current,'stall_stability',{},'bounded_regression_recovery')
            edit=read(folder/'model_call/model_edit.json') if (folder/'model_call/model_edit.json').exists() else None
            if call['status']!='response_received':
                status='transport_stopped'
                b.journal(folder,current,None,dict(accepted=False,reasons=[dict(kind='transport_terminal',status=call['status'])]));break
            repeated=bool(proposal and b.interface.executable_hash(proposal) in seen)
            if proposal:seen.add(b.interface.executable_hash(proposal))
            small=b.loop.replay(proposal,folder/'public',read(prepared/'cases.json')) if proposal and not repeated else None
            plain=b.paired.current_decision(before,small,edit) if small else dict(accepted=False,reasons=[dict(kind='repeated_executable' if repeated else 'interface_failure')])
            full=b.loop.replay(proposal,folder/'history',read(prepared/'history_cases.json')) if small and small.get('group') else None
            decision=policy.decision_for(plain,full,historical,True)
            dump(folder/'decision.json',decision);current=b.journal(folder,current,proposal,decision)
            decisions.append(decision);accepted=decision['accepted']
            print('RECOVERY',iteration,accepted,flush=True)
            if accepted:status='accepted';break
            diagnostic=policy.feedback_for(small,full,decision,call,edit,last_edit,True)
            dump(folder/'next_feedback.json',diagnostic)
            if iteration+1<MAX_CALLS:
                model.request=b.campaign.request_from(request,current,SEED,diagnostic)
                dump(folder/'next_request.preview.json',model.request)
            last_edit=edit
    b.loop.freeze(out/'core',current,'bounded_regression_recovery_terminal')
    dump(out/'outcome.json',dict(status=status,accepted=accepted,calls=len(model.calls),decisions=decisions,
        frozen_hash=b.loop.sha(current),independent_performed=False))
    from research17_report import cost_audit
    dump(out/'cost.json',cost_audit(out,b.paired.files(out)))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','run']);p.add_argument('--source',type=Path);p.add_argument('--audit',type=Path);p.add_argument('--prepared',type=Path);p.add_argument('--authorization',type=Path);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    if a.action=='prepare':prepare(a.source.resolve(),a.audit.resolve(),a.out.resolve())
    else:execute(a.prepared.resolve(),a.out.resolve(),a.authorization.resolve())
