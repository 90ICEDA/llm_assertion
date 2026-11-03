"""Research79's four presentation arms; one bounded pilot, no automatic expansion."""
import argparse
import copy
import json
from contextlib import contextmanager
from pathlib import Path
import research79_bottleneck_audit as presentation
from research80_budget import Budget,ARMS,tests

g=presentation.gate
b,ROOT,read,dump=g.b,g.ROOT,g.read,g.dump
P=ROOT/'deliverables/research79_bottleneck_20261024_r01'
BASE=presentation.BASE
SEED=7907


def verify(prep):
    g.old.verify(prep)
    protocol=read(prep/'protocol.json')
    assert protocol['seed']==7907 and protocol['maximum_calls']==8 and protocol['automatic_expansion'] is False


def prepare(out):
    g.old.verify(BASE)
    for name,h in read(P/'manifest.json').items():assert b.search.digest(P/name)==h,name
    assert read(P/'audit.json')['passed']
    out.mkdir(parents=True,exist_ok=False);checks=[]
    def check(name,ok):assert ok,name;checks.append(name)
    base_request=read(presentation.LAST/'plan/v0/model_call/request.json')
    base_body=json.loads(base_request['messages'][1]['content']);original_rows=read(BASE/'windows.private.json')
    arms=read(P/'representation_checks.json')
    for item in arms:
        arm=item['arm'];folder=out/'arms'/arm;aliases=item['aliases']
        req=read(P/f'protocol/previews/s7907/{arm}/request.preview.json')
        check(arm+': exact lossless source body',presentation.expand(req,aliases)==base_body)
        check(arm+': bounded request',sum(len(m['content']) for m in req['messages'])<=64000)
        check(arm+': fixed sampler',req['seed']==7907 and req['max_tokens']==2048 and req['temperature']==0.2)
        adapted=copy.deepcopy(original_rows)
        for row in adapted:
            row['id']=aliases.get(row['id'],row['id']);row['public']['id']=row['id'];row['expected']['id']=row['id']
        check(arm+': exact model-facing samples',json.loads(req['messages'][1]['content'])['windows']==[r['public'] for r in adapted])
        good=dict(**g.fixture_rules(),windows=[r['expected'] for r in adapted])
        check(arm+': positive local-only fixture passes',g.validate(good,adapted)['accepted'])
        rejected=read(presentation.LAST/'plan/v0/model_call/hold_plan.json')
        if aliases:rejected=presentation.remap(rejected,aliases)
        check(arm+': old wrong w1 still rejects',not g.validate(rejected,adapted)['accepted'])
        template=read(BASE/'sva_template.json');template['seed']=7907
        sva=g.unlock(template,good,g.validate(good,adapted),adapted)
        check(arm+': conditional SVA fits character cap',sum(len(m['content']) for m in sva['messages'])<=64000)
        cfg=read(BASE/'model_config.json');cfg['max_model_calls']=1
        # Both transport request seeds, not merely metadata, are fixed above.
        dump(folder/'request.preview.json',req);dump(folder/'windows.private.json',adapted)
        dump(folder/'aliases.json',aliases);dump(folder/'sva_template.json',template);dump(folder/'model_config.json',cfg)
    for name in ('initial.json','cases.json','history_cases.json','window_cases.json','excluded_inputs.json','protected.json'):
        dump(out/name,read(BASE/name))
    check('exact case inventories',all(len(read(out/n))==count for n,count in [('window_cases.json',5),('cases.json',14),('history_cases.json',105)]))
    dump(out/'budget_checks.json',tests(out/'local_budget_fixtures'))
    dump(out/'preflight.json',dict(passed=True,checks=checks,model_calls=0,native_calls=0))
    parent=read(P/'protocol/protocol.json');cfg=read(BASE/'model_config.json')
    dump(out/'protocol.json',dict(seed=SEED,arms=list(ARMS),maximum_calls=8,plan_calls=4,conditional_sva_calls=4,
        endpoint=cfg['remote_url'],model=cfg['remote_model'],temperature=0.2,max_output_tokens=2048,
        input_character_cap=64000,retries=0,automatic_expansion=False,
        arm_order=list(ARMS),slot_transfer=False,whole_plan_gate='unchanged research77 validate and unlock',
        acceptance='unchanged native windows,14 public,105 history. Critical unknown rejects.',
        independent='Only after ALL four terminal versions freeze, and at least one new native accepted version. One fresh56-scenario batch for all final hashes, no feedback, equal hashes replayed once with mapping.',
        stop='Transport or execution exception stops all remaining calls. Normal rejection stops its arm. No accepted+independent-pass version means pilot fails and stops; no new prompt/call budget automatically.',
        continuation='Never start seed7919 here, even after pilot pass. Report eligibility only; separate execution and authorization required.',
        protected='Prior independent inputs used only for exclusion, old artifacts unchanged.',
        parent_protocol_sha256=b.search.digest(P/'protocol/protocol.json'),parent_design=parent,
        scope='One observed development task, four presentation arms. Not the two core mechanism ablation; no causal gate/no-gate comparison.'))
    bindings=read(BASE/'source_bindings.json')
    for path in (P/'manifest.json',P/'protocol/protocol.json',BASE/'sealed.json'):
        bindings[str(path)]=b.search.digest(path)
    for arm in ARMS:
        path=P/f'protocol/previews/s7907/{arm}/request.preview.json';bindings[str(path)]=b.search.digest(path)
    dump(out/'source_bindings.json',bindings)
    dump(out/'code_versions.json',{str(p):b.search.digest(p) for p in (ROOT/'scripts').glob('*.py')})
    dump(out/'sealed.json',{p.relative_to(out).as_posix():b.search.digest(p) for p in out.rglob('*.json')})
    print('PREPARED',len(checks),'request checks',len(read(out/'budget_checks.json')['checks']),'budget checks',flush=True)


def run_arm(prep,out,name,budget,models):
    arm=prep/'arms'/name;folder=out/'arms'/name;initial=read(prep/'initial.json');current=initial
    rows=read(arm/'windows.private.json');status='plan_failed';accepted=False
    try:
        request=read(arm/'request.preview.json')
        budget.reserve(name,'plan',request,b.loop.sha(request))
        model=g.old.PlanModel(folder/'plan_model',read(arm/'model_config.json'),request);models.append(model)
        call,plan=model.call(folder/'plan/v0/model_call',initial,'stall_stability',{},'presentation_pilot_plan')
        if call['status']!='response_received':
            status='transport_stopped';budget.stop(status);return
        verdict=g.validate(plan,rows);dump(folder/'plan/v0/decision.json',verdict);budget.plan(name,verdict['accepted'])
        print(name,'PLAN',verdict['accepted'],flush=True)
        if not verdict['accepted']:return
        dump(folder/'accepted_plan.json',plan)
        request=g.unlock(read(arm/'sva_template.json'),plan,verdict,rows)
        dump(folder/'sva_request.preview.json',request)
        budget.reserve(name,'sva',request,b.loop.sha(request))
        model=g.old.policy.Model(folder/'sva_model',read(arm/'model_config.json'),request);models.append(model)
        version=folder/'core/v0'
        call,candidate=model.call(version/'model_call',initial,'stall_stability',{},'presentation_pilot_sva')
        if call['status']!='response_received':
            status='transport_stopped';budget.stop(status);return
        status='native_rejected'
        edit=read(version/'model_call/model_edit.json') if (version/'model_call/model_edit.json').exists() else None
        wr=None;small=None;full=None
        if candidate:
            budget.native(name,'windows',len(read(prep/'window_cases.json')))
            wr=b.loop.replay(candidate,version/'windows',read(prep/'window_cases.json'))
        wg=g.old.sem.native_windows(wr,rows,read(prep/'window_cases.json'),version/'windows')
        dump(version/'window_gate.json',wg)
        if wg['accepted']:
            budget.phase_pass(name,'windows');budget.native(name,'public',len(read(prep/'cases.json')))
            small=b.loop.replay(candidate,version/'public',read(prep/'cases.json'))
        before=read(g.old.sem.SOURCE/'baseline_public/result.json');historic=read(g.old.sem.SOURCE/'baseline_history/result.json')
        plain=b.paired.current_decision(before,small,edit) if small else dict(accepted=False,reasons=wg['reasons'])
        if plain['accepted']:
            budget.phase_pass(name,'public');budget.native(name,'history',len(read(prep/'history_cases.json')))
            full=b.loop.replay(candidate,version/'history',read(prep/'history_cases.json'))
        decision=g.old.policy.decision_for(plain,full,historic,True);dump(version/'decision.json',decision)
        current=b.journal(version,current,candidate,decision);accepted=decision['accepted']
        status='native_accepted' if accepted else 'native_rejected'
        print(name,'SVA',accepted,flush=True)
    except BaseException as exc:
        status='execution_exception';budget.stop(status)
        dump(folder/'exception.json',dict(type=type(exc).__name__,detail=str(exc)));raise
    finally:
        budget.finish(name,accepted)
        b.loop.freeze(folder/'core',current,'terminal_before_all_arms_independent')
        budget.freeze(name,b.loop.sha(current))
        dump(folder/'outcome.json',dict(status=status,plan_passed=budget.state['arms'][name]['plan_passed'],
            accepted=accepted,frozen_hash=b.loop.sha(current),independent_performed=False))


@contextmanager
def independent_case_cap():
    original=b.loop.replay;count=0
    def limited(candidate,folder,cases,*args,**kwargs):
        nonlocal count
        assert Path(folder).name in ('boundary','drain')
        count+=len(cases);assert count<=56,'independent_case_cap'
        return original(candidate,folder,cases,*args,**kwargs)
    b.loop.replay=limited
    try:yield
    finally:b.loop.replay=original


def run(prep,out,authpath):
    verify(prep);protocol=read(prep/'protocol.json');auth=read(authpath)
    assert auth['authorized_calls']==8 and auth['prepared_sha256']==b.search.digest(prep/'sealed.json')
    assert auth['endpoint']==protocol['endpoint'] and auth['model']==protocol['model']
    assert auth['run_output']==out.relative_to(ROOT).as_posix() and auth['seed']==7907
    out.mkdir(parents=True,exist_ok=False);dump(out/'authorization.json',auth);dump(out/'protocol.json',protocol)
    budget=Budget(out/'budget.json',protocol['model']);models=[];completed=[];independent={};status='running'
    try:
        with b.extension.installed():
            for arm in ARMS:
                run_arm(prep,out,arm,budget,models);completed.append(arm)
                if budget.state['stopped']:break
            initial=read(prep/'initial.json')
            for arm in ARMS:
                if arm in completed:continue
                folder=out/'arms'/arm
                # An exception may already have frozen the failing arm in finally.
                if budget.state['arms'][arm]['frozen']:continue
                budget.finish(arm,False);b.loop.freeze(folder/'core',initial,'not_run_due_global_stop')
                budget.freeze(arm,b.loop.sha(initial));dump(folder/'outcome.json',dict(status='not_run_global_stop',accepted=False,plan_passed=False,frozen_hash=b.loop.sha(initial),independent_performed=False))
            frozen={a:read(out/'arms'/a/'core/frozen_candidate.json') for a in ARMS}
            dump(out/'all_frozen.json',dict(hashes={a:b.loop.sha(c) for a,c in frozen.items()},budget_events=len(budget.state['events'])))
            accepted=[a for a in ARMS if budget.state['arms'][a]['native_passed']]
            if budget.state['stopped']:status='stopped_no_expansion';return
            if not accepted:status='pilot_failed_no_accepted_version';return
            # A single common fresh batch begins only after all arms freeze.
            split=None;replayed={};development=sum((read(prep/n) for n in ('window_cases.json','cases.json','history_cases.json')),[])
            for arm in accepted+[a for a in ARMS if a not in accepted]:
                budget.native(arm,'independent',56);candidate=frozen[arm];h=b.loop.sha(candidate)
                if h not in replayed:
                    loc=out/'independent_by_hash'/h
                    with independent_case_cap():b.holdout(loc,candidate,development,set(read(prep/'excluded_inputs.json')['input_hashes']),fixed_split=split)
                    summary=read(loc/'independent/summary.json');assert summary['scenarios']==56
                    if split is None:
                        split=read(loc/'independent/split.json');dump(out/'common_independent_split.json',split)
                    replayed[h]=loc.relative_to(out).as_posix()
                path=replayed[h];summary=read(out/path/'independent/summary.json')
                independent[arm]=dict(path=path,candidate_hash=h,passed=summary['all_five_pass_on_first_attributed_evidence'],
                    new_accepted=arm in accepted,qualified=arm in accepted and summary['all_five_pass_on_first_attributed_evidence'])
                dump(out/'independent_mapping.json',independent)
            status='pilot_qualified_no_automatic_expansion' if any(v['qualified'] for v in independent.values()) else 'pilot_failed_independent_no_expansion'
    except BaseException as exc:
        status='execution_exception_no_expansion'
        if not budget.state['stopped']:budget.stop(status)
        dump(out/'exception.json',dict(type=type(exc).__name__,detail=str(exc)));raise
    finally:
        dump(out/'cost.json',g.old.cost_audit(out,b.paired.files(out)))
        dump(out/'outcome.json',dict(status=status,seed=7907,automatic_expansion=False,
            actual_model_calls=sum(len(m.calls) for m in models),reserved_slots=sum(len(s['calls']) for s in budget.state['arms'].values()),
            arms_completed=completed,new_accepted_versions=sum(s['native_passed'] for s in budget.state['arms'].values()),
            full_history_replays=sum('history' in s['phases'] for s in budget.state['arms'].values()),
            independent=independent,new_independent_passes=sum(v['qualified'] for v in independent.values()),
            core_mechanism_increment_evidence=0,protected_unchanged=g.old.old.screen.protected()==read(prep/'protected.json')))
        print('TERMINAL',status,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','run']);p.add_argument('--prepared',type=Path)
    p.add_argument('--authorization',type=Path);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    if a.action=='prepare':prepare(a.out.resolve())
    else:run(a.prepared.resolve(),a.out.resolve(),a.authorization.resolve())
