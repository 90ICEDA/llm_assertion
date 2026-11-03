"""Prospective, pilot-gated search / paired-decision / independent-policy protocol.

Existing experiments remain immutable. seal/search/qualify never read a credential
or call a model. pilot requires its own explicit maximum-three-call grant.
Research63 is protected with byte hashes only, never decoded for this experiment.
"""
import argparse
import copy
import json
import shutil
import time
from pathlib import Path

import research64_search_value as search
import research65_search_policy as policy
import research43_paired_ablation as paired
import research45_campaign as campaign
import research44_interface as interface
import research31_gate as gate
from research35_campaign import holdout, join_results

ROOT=search.ROOT
read,dump=search.read,search.dump
loop,extension=search.loop,search.extension
PILOT=6703
SEEDS=(6711,6719,6733)
METHODS=('ordinary','candidate_disagreement','raw_difference','contract_novelty','ordinary_no_repeat')
PAIR=('bounded','valid')
PAIR_NAME='bounded__valid'
BUDGET=4


def protected():
    # Do not deserialize independent cases, predictions or outcomes.
    root=ROOT/'deliverables/research63_independent_20261023_r02'
    return {p.relative_to(ROOT).as_posix():search.digest(p) for p in root.rglob('*.json')
            if 'obj_dir' not in p.parts}


def seal(out):
    out.mkdir(parents=True,exist_ok=False)
    for name in PAIR:
        dump(out/'candidates'/f'{name}.json',read(search.SOURCES[name]))
    initial=read(out/'candidates/bounded.json')
    assert initial==read(paired.HISTORY/'shared_initial.json')
    historic=read(paired.HISTORY/'core/history/result.json')
    assert historic['healthy'] and not any(historic['counts'][k] for k in ('misses','false_positives','unknown'))
    dump(out/'shared_initial.json',initial)
    dump(out/'history_cases.json',read(paired.HISTORY/'history_cases.json'))
    dump(out/'history_binding.json',dict(path=str(paired.HISTORY/'core/history/result.json'),
        sha256=search.digest(paired.HISTORY/'core/history/result.json'),cases=105,physical_new_runs=0))
    dump(out/'protected_research63.json',protected())
    shutil.copy2(extension.runtime.RTL,out/'axis_fifo.v')
    dump(out/'rtl_binding.json',dict(path=str(extension.runtime.RTL),sha256=search.digest(extension.runtime.RTL)))
    dump(out/'local_checks.json',dict(passed=True,checks=local_checks()))
    registry=search.historical_registry()
    for name in ('research64_search_value_20261023_r01','research65_search_value_20261024_r01'):
        path=ROOT/'deliverables'/name/'records.json'
        keys={k for r in read(path) for k in r['gap_keys']}
        registry['keys']=sorted(set(registry['keys'])|keys)
        registry['sources'].append(dict(path=str(path),sha256=search.digest(path),keys=sorted(keys)))
    dump(out/'historical_registry.json',registry)
    dump(out/'protocol.json',dict(experiment='research67',sealed_at=time.time(),pilot_seed=PILOT,
        conditional_seeds=SEEDS,search_methods=METHODS,search_queries_per_method=BUDGET,
        candidate_pair=PAIR,initial_hash=loop.sha(initial),depth=4,pipeline=1,modes=search.MODES,
        endpoint=campaign.settings(PILOT,3)['remote_url'],model=campaign.settings(PILOT,3)['remote_model'],
        temperature=0.2,max_output_tokens=2048,retries=0,pilot_maximum_calls=3,
        conditional_paired_maximum_calls=6,conditional_policy_maximum_calls=24,
        common_helpers=dict(interface='research44 recursive AST, reason metadata unrestricted',
            component_generation='keep or replace exactly one existing stall property; all other components fixed',
            model_cycle_planning='disabled equally in every arm; no archived successful model plan',
            native_cycle_check='same independent sampling qualification and research34 native_target_gate for every visible target',
            semantic_rewrite=False,model_configuration='same backend, sampler and output bound for all calls'),
        public_feedback='Two schedules: overlap seed67000 and backpressure duration1 seed67001, all eight modes and both candidates. Freeze all public gaps before search. Both candidate correct controls must pass.',
        allowed_information='All search methods share candidates, RTL, grammar, modes, public feedback. Ordinary chooser sees family only; disagreement sees whole-candidate failure XOR; raw difference sees output mismatch; contract sees own independent checks/triggers/protection/gaps; no-repeat sees actions only. Judge results are measurement-only for other choosers.',
        acquisition='research65 fixed contract_novelty. Confirmed gaps queued for refinement; executed actions excluded, including public actions. No parameter adaptation after results. Four queries, 16 real native runs per query.',
        stimuli='Same seed*100+query schedule generator for same chosen action. Public and comparison pools identical across methods.',
        dedup='candidate hash / FN or FP / obligation / mechanism; long/short variants collapsed. Subtract public gaps and own prior discoveries. Previously observed matches stay historically known; absent historical registry entries unknown.',
        treatment_selection='First valid public-unexposed stall FN for each deduplicated mechanism in contract chronological query order, at most two. No comparator results used to choose treatment. All selections remain development data. Stop unqualified if none.',
        arms=paired.ARMS,
        ordinary_rule='Same interface, visible legal/native/target detection and required-trigger gates. No hidden105 history. Keep accepted only if visible targets already resolved.',
        historical_rule='Ordinary rule AND native healthy105 replay AND fixed research31 history acceptance. Unknown rejects; compare against shared initial. Reject retains exact last accepted candidate, or qualified partial baseline if none.',
        pilot='At most3 real independent attempts, search+history enabled; no retries. Requires a new accepted executable, then freeze and generate fresh holdout. Any failed qualification, refinement or holdout stops all multi-seed work.',
        paired_estimand='After pilot passes: 3 fixed seeds, ordinary/search one real proposal each. A/C and B/D share exact proposal. Measure extra historical rejection only when ordinary accepts. No multi-round strategy claim.',
        policy_estimand='Separate real calls for all 3x4 trajectories, at most2 calls per arm. First A/C and B/D requests identical but no shared responses. Feedback uses only own visible evidence and, C/D only, history. Stop on acceptance; equal upper limits, unequal actual costs reported.',
        seed_scope='Seeds are model request seeds and search schedule seeds; remote determinism is unverified. One FIFO parent and known artificial faults; not multiple independent hardware bugs.',
        isolation='Pilot and paired outputs never supplied to policy arms. No successful archival SVA or model plan in prompts. Search witnesses only B/D. All planned arms freeze before any group test outcome is read.',
        independent='Fresh holdout generated only after freeze: existing56-case generator includes depths4/8, pipelines and five obligations with causal exposure. Shared post-all-freeze test batch; exact candidate duplicates may share physical evaluation but not statistical sample counts. Failures never select/refine in this protocol.',
        exclusions='Full used-development hashes plus previous FIFO holdout inventories; research63 byte-hash preservation only. Any future use of failed tests requires whole batch promotion and a new protocol.',
        accounting='Physical and logical model/token/native/reference/selector costs separate. Public qualification and audit charged separately. 16 native/query includes measurement oracle for all methods; not an optimized no-oracle baseline.',
        acceptance_of_research='Fair fixed protocol and auditable evidence, not mandatory positive gain. Historical research66 retrospective findings and research65 no-extra-union-gain remain unchanged.',
        authorization='No old budget transferred. Pilot requires new <=3 grant; paired/policy continuation requires separate explicit <=30 grant and recorded pilot pass.'))
    dump(out/'code_versions.json',{p.relative_to(ROOT).as_posix():search.digest(p) for p in (ROOT/'scripts').glob('*.py')})
    dump(out/'sealed.json',{p.relative_to(out).as_posix():search.digest(p) for p in out.rglob('*') if p.is_file()})
    dump(out/'status.json',dict(stage='sealed',model_calls=0))
    print('SEALED',out,flush=True)


def verify(out):
    search.verify(out)
    rtl=read(out/'rtl_binding.json');assert search.digest(gate.portable(rtl['path']))==rtl['sha256']
    assert protected()==read(out/'protected_research63.json'),'research63_changed'


def summarize_search(folder):
    records=read(folder/'records.json');pub=read(folder/'public_feedback.json')[PAIR_NAME]
    known=set(read(folder/'historical_registry.json')['keys']);items={}
    for method in METHODS:
        selected=[r for r in records if r['method']==method]
        p=policy.factory(method,selected[0]['seed']);history=[];seen=set(pub['gap_keys']);actions=set()
        for r in pub['results']:
            history.append(policy.update(p,method,r['family'],r));actions.add((r['family'],r['duration']))
        repeated=0;first={}
        for r in selected:
            q=r['query'];where=folder/'queries'/PAIR_NAME/f"s{r['seed']}"/method/f'q{q}'
            saved=read(where/'selection.json')
            assert saved['chosen']==policy.decision(p,method,r['seed'],q,history)
            assert saved['permitted_history']==history
            assert r['first_new_keys']==sorted(set(r['gap_keys'])-seen)
            for key in r['first_new_keys']:first[key]=q+1
            seen.update(r['gap_keys']);action=(r['family'],r['duration']);repeated+=action in actions;actions.add(action)
            history.append(policy.update(p,method,r['family'],r))
        if method in policy.NEW:assert repeated==0
        items[method]=dict(queries=len(selected),keys=sorted(first),first_query=first,repeated_actions=repeated,
            historical_novelty={k:'historically_known' if k in known else 'unknown_partial_registry' for k in first},
            zero_new_queries=sum(not r['first_new_keys'] for r in selected),
            unknown=sum(r['unknown'] for r in selected),later_attribution_unknown=sum(r['later_attribution_unknown'] for r in selected),
            failed_queries=sum(not r['healthy'] for r in selected),query_wall_seconds=sum(r['query_wall_seconds'] for r in selected))
    contract=set(items['contract_novelty']['keys'])
    dump(folder/'summary.json',dict(methods=items,contract_extra_vs_all=sorted(contract-set().union(
        *(set(x['keys']) for name,x in items.items() if name!='contract_novelty'))),
        contrasts={m:dict(contract_only=sorted(contract-set(v['keys'])),comparator_only=sorted(set(v['keys'])-contract)) for m,v in items.items()}))
    dump(folder/'cost.json',search.native_cost(folder))


def run_search(root,seed):
    verify(root)
    assert seed in (PILOT,*SEEDS)
    if seed!=PILOT:assert read(root/'pilot_run/outcome.json')['pilot_passed']
    out=root/'search'/f's{seed}';out.mkdir(parents=True,exist_ok=False)
    for n in ('code_versions.json','historical_registry.json'):
        dump(out/n,read(root/n))
    candidates={n:read(root/'candidates'/f'{n}.json') for n in PAIR}
    for n,c in candidates.items():dump(out/'candidates'/f'{n}.json',c)
    dump(out/'protocol.json',dict(parent=str(root),parent_protocol_sha256=search.digest(root/'protocol.json'),seed=seed))
    dump(out/'sealed.json',{p.relative_to(out).as_posix():search.digest(p) for p in out.rglob('*') if p.is_file()})
    calls=[];records=[];pub=[]
    dump(out/'outcome.json',dict(status='running'))
    try:
        with extension.installed():
            builds={n:loop.runtime.build(c,out/'compiled'/n,4,1) for n,c in candidates.items()}
            assert all(b['native']['compile_status']=='passed' for b in builds.values())
            for q,(family,duration) in enumerate((('overlap',None),('backpressure',1))):
                pub.append(search.query(out/'public'/PAIR_NAME/f'q{q}',builds,candidates,PAIR,
                    search.schedule(67000+q,family,duration),dict(pair=PAIR_NAME,stage='public',method='common',seed=0,query=q,family=family,duration=duration),calls))
            public=dict(results=pub,gap_keys=sorted({k for r in pub for k in r['gap_keys']}))
            dump(out/'public_feedback.json',{PAIR_NAME:public})
            dump(out/'public_freeze.json',dict(sha256=search.digest(out/'public_feedback.json'),at=time.time()))
            okay=all(r['healthy'] and not r['unknown'] and all(r['correct_accepts'].values()) for r in pub)
            dump(out/'qualification.json',dict(qualified=okay,seed=seed))
            if not okay:
                dump(out/'outcome.json',dict(status='public_qualification_failed',model_calls=0));return
            for method in METHODS:
                p=policy.factory(method,seed);history=[];seen=set(public['gap_keys'])
                for r in pub:history.append(policy.update(p,method,r['family'],r))
                for q in range(BUDGET):
                    where=out/'queries'/PAIR_NAME/f's{seed}'/method/f'q{q}'
                    t=time.perf_counter();chosen=policy.decision(p,method,seed,q,history);elapsed=time.perf_counter()-t
                    dump(where/'selection.json',dict(chosen=chosen,permitted_history=history,selector_seconds=elapsed))
                    r=search.query(where,builds,candidates,PAIR,search.schedule(seed*100+q,chosen['family'],chosen['duration']),
                        dict(pair=PAIR_NAME,stage='search',method=method,seed=seed,query=q,family=chosen['family'],duration=chosen['duration']),calls)
                    r.update(public_unexposed_keys=sorted(set(r['gap_keys'])-set(public['gap_keys'])),
                        first_new_keys=sorted(set(r['gap_keys'])-seen),selector_seconds=elapsed)
                    r['repeated_observations']=len(r['gaps'])-len(r['first_new_keys'])
                    seen.update(r['gap_keys']);history.append(policy.update(p,method,r['family'],r))
                    dump(where/'result.json',r);records.append(r);dump(out/'records.json',records)
                    dump(out/'reference_costs.json',calls)
                    print('SEARCH',seed,method,q,chosen['family'],chosen['duration'],'new',len(r['first_new_keys']),flush=True)
        dump(out/'outcome.json',dict(status='completed',queries=len(records),model_calls=0,formal_calls=0))
        summarize_search(out)
    except BaseException as exc:
        dump(out/'outcome.json',dict(status='failed',error=repr(exc),queries=len(records)));raise
    finally:
        dump(out/'reference_costs.json',calls);verify(root)


def case_for(record,mode,scope):
    q=record['query'];family=record['family'];duration=record['duration']
    seed=67000+q if record['stage']=='public' else record['seed']*100+q
    return dict(id=f'{scope}:{q}:{family}:{duration}:{mode}',depth=4,pipeline=1,mode=mode,
        rows=search.schedule(seed,family,duration),split='development',source='research67_native_search')


def qualify(root,seed):
    verify(root);src=root/'search'/f's{seed}';dest=root/'prepared'/f's{seed}'
    assert not dest.exists();dest.mkdir(parents=True)
    assert read(src/'outcome.json')['status']=='completed'
    public=read(src/'public_feedback.json')[PAIR_NAME]
    common_cases=[case_for(r,m,'public67') for r in public['results'] for m in search.MODES]
    selected=[];keys=set();bindings=[]
    for r in read(src/'records.json'):
        if r['method']!='contract_novelty':continue
        for gap in r['gaps']:
            if (gap['kind']=='FN' and gap['obligation']=='stall_stability' and gap['key'] not in keys
                    and gap['key'] not in public['gap_keys'] and len(keys)<2):
                keys.add(gap['key']);selected.append(case_for(r,gap['mode'],f'search67:s{seed}'))
                bindings.append(dict(key=gap['key'],query=r['query'],evidence_id=gap['evidence']['evidence_id'],
                    replay_source=gap['replay_source'],validation=gap['validation'],trigger_class=gap['trigger_class']))
    dump(dest/'selected.json',dict(keys=sorted(keys),bindings=bindings,not_global_novelty=True))
    if not selected:
        dump(dest/'qualification.json',dict(passed=False,reason='no_public_unexposed_contract_stall_witness'));return
    initial=read(root/'shared_initial.json')
    for n in ('shared_initial.json','history_cases.json','history_binding.json'):dump(dest/n,read(root/n))
    dump(dest/'common_cases.json',common_cases);dump(dest/'search_cases.json',selected)
    with extension.installed():
        common=loop.replay(initial,dest/'native/common',common_cases)
        target=loop.replay(initial,dest/'native/search',selected)
    okay=all(r['healthy'] and not r['counts']['false_positives'] and not r['counts']['unknown'] for r in (common,target)) and target['counts']['misses']>=len(selected)
    if okay:
        for stream,use_search in (('ordinary',False),('search',True)):
            visible=join_results([common,target]) if use_search else common
            feedback=dict(requested_obligations=['stall_stability'],counts=visible['counts'],actual_native_evidence=visible['feedback'],
                ordinary_observations=dict(scenario='public67',counts=common['counts'],native_diagnostic=common['feedback']))
            request=paired.payload(dest/stream/'preview',initial,feedback,seed)
            request=campaign.request_from(request,initial,seed)
            dump(dest/stream/'request.preview.json',request)
            dump(dest/stream/'cases.json',common_cases+(selected if use_search else []))
            dump(dest/stream/'baseline_binding.json',dict(common=str(dest/'native/common/result.json'),
                common_sha256=search.digest(dest/'native/common/result.json'),
                target=str(dest/'native/search/result.json') if use_search else None,
                target_sha256=search.digest(dest/'native/search/result.json') if use_search else None))
        a=read(dest/'ordinary/request.preview.json');b=read(dest/'search/request.preview.json')
        aa=json.loads(a['messages'][1]['content']);bb=json.loads(b['messages'][1]['content'])
        for k in ('rtl_and_common_contract','confirmed_obligations','current_assertions','output_schema','temporal_semantics','ordinary_observations'):
            assert aa[k]==bb[k],k
        assert all(c['id'] not in json.dumps(a) for c in selected)
        assert all('research63' not in json.dumps(r) and 'verified_model_applicability_plan' not in json.dumps(r) for r in (a,b))
    dump(dest/'qualification.json',dict(passed=okay,common=common['counts'],target=target['counts'],selected_gaps=len(keys),
        shared_helpers_equal=okay,search_isolated=okay,model_calls=0,credentials_read=False))
    dump(dest/'sealed.json',{p.relative_to(dest).as_posix():search.digest(p) for p in dest.rglob('*.json')
        if not any(x in p.parts for x in ('obj_dir',))})
    print('QUALIFIED',seed,okay,'public',common['counts'],'search',target['counts'],flush=True)


def journal(folder,previous,proposal,decision):
    """Durable candidate identity transition, including rejection/partial baseline."""
    current=proposal if decision['accepted'] else previous
    entry=dict(previous_hash=loop.sha(previous),proposal_hash=loop.sha(proposal) if proposal else None,
        active_hash=loop.sha(current),accepted=decision['accepted'],reasons=decision['reasons'],at=time.time(),
        retained_on_rejection=not decision['accepted'],scope='Evidence-scoped, not globally correct')
    dump(folder/'active_candidate.json',current);dump(folder/'active_transition.json',entry)
    assert read(folder/'active_candidate.json')==current
    if not decision['accepted']:assert entry['active_hash']==entry['previous_hash']
    return current


def run_arm(prep,out,stream,seed,rounds,use_gate,budget,models):
    initial=read(prep/'shared_initial.json');current=initial
    before=campaign.baseline(prep,stream);cases=read(prep/stream/'cases.json');history=read(prep/'history_cases.json')
    binding=read(prep/'history_binding.json');path=gate.portable(binding['path']);assert search.digest(path)==binding['sha256']
    historical=read(path);request=read(prep/stream/'request.preview.json')
    model=campaign.Model(out/'model',campaign.settings(seed,rounds),request);models.append(model)
    dump(out/'initial_state.json',dict(hash=loop.sha(initial),history_qualified=True,complete_protection=False))
    accepted=False;decisions=[];previous_edit=None;seen={interface.executable_hash(initial)}
    for iteration in range(rounds):
        folder=out/'core'/f'v{iteration}';assert not folder.exists(),'resume requires terminal audit, never resend'
        budget['reserved']+=1;assert budget['reserved']<=budget['maximum']
        dump(budget['path'],{k:v for k,v in budget.items() if k!='path'})
        call,proposal=model.call(folder/'model_call',current,'stall_stability',{},'research67_fixed_protocol')
        edit=read(folder/'model_call/model_edit.json') if (folder/'model_call/model_edit.json').exists() else None
        repeated=bool(proposal and edit['operation']!='keep' and interface.executable_hash(proposal) in seen)
        if proposal:seen.add(interface.executable_hash(proposal))
        small=loop.replay(proposal,folder/'visible_native',cases) if proposal and not repeated else None
        plain=paired.current_decision(before,small,edit) if small else dict(accepted=False,reasons=[dict(kind='repeated_executable' if repeated else 'model_or_interface_failure')])
        dump(folder/'ordinary_decision.json',plain)
        full=loop.replay(proposal,folder/'history_native',history) if proposal and not repeated and use_gate else None
        hg=gate.decide(historical['group']['ledger'],full['group']['ledger']) if full and full.get('group') else dict(accepted=False,reasons=[dict(kind='history_unavailable')])
        accepted=bool(plain['accepted'] and (not use_gate or (full and full['healthy'] and hg['accepted'])))
        reasons=list(plain['reasons'])+(hg['reasons'] if use_gate else [])
        if use_gate and full and not full['healthy']:reasons.append(dict(kind='history_native_unhealthy'))
        decision=dict(accepted=accepted,reasons=reasons,ordinary_accepted=plain['accepted'],use_gate=use_gate,
            historical=hg if use_gate else None,call=call,repeated_executable=repeated)
        dump(folder/'decision.json',decision);current=journal(folder,current,proposal,decision);decisions.append(decision)
        if accepted:break
        diagnostic=campaign.attempt_feedback(small,full,decision,call,edit,previous_edit)
        dump(folder/'next_feedback.json',diagnostic)
        model.request=campaign.request_from(request,current,seed,diagnostic);previous_edit=edit
    loop.freeze(out/'core',current,'terminal_before_new_independent_generation')
    result=dict(accepted=accepted,new_executable_version=interface.executable_hash(current)!=interface.executable_hash(initial),
        candidate_hash=loop.sha(current),calls=len(model.calls),decisions=decisions)
    dump(out/'outcome.json',result)
    return current,result


def exclusions(root):
    # Already-created development/hash-only FIFO inventories. Do not open research63.
    values=set(read(campaign.P43/'excluded_tests.json')['input_hashes'])
    sources=[]
    for name in ('research64_search_value_20261023_r01','research65_search_value_20261024_r01'):
        src=ROOT/'deliverables'/name
        for p in src.glob('**/bounded/correct_stimulus/stimulus.json'):
            v=read(p);values.add(loop.sha(v['rows'] if isinstance(v,dict) else v))
            sources.append(dict(path=str(p),sha256=search.digest(p)))
    for p in (root/'search').glob('**/bounded/correct_stimulus/stimulus.json'):
        v=read(p);values.add(loop.sha(v['rows'] if isinstance(v,dict) else v))
    # Legacy holdout helper adds its own published-case inventories. Restrict this
    # scan to FIFO layouts with boundary/drain fields, excluding research63 upfront.
    for p in (ROOT/'deliverables').glob('research*/**/independent/split.json'):
        if any(x.startswith('research63') for x in p.parts):continue
        v=read(p)
        if isinstance(v,dict):
            values.update(loop.sha(c['rows']) for c in v.get('boundary_cases',[])+v.get('drain_cases',[]) if 'rows' in c)
    return values,sources


def pilot(root,authorization):
    verify(root);prep=root/'prepared'/f's{PILOT}';out=root/'pilot_run'
    assert read(prep/'qualification.json')['passed']
    for p,h in read(prep/'sealed.json').items():assert search.digest(prep/p)==h,p
    auth=read(authorization);protocol=read(root/'protocol.json')
    assert auth['authorized_calls']==3 and auth['purpose']=='research67_pilot'
    assert auth['endpoint']==protocol['endpoint'] and auth['model']==protocol['model']
    assert auth['protocol_sha256']==search.digest(root/'protocol.json')
    assert auth['run_output']==out.relative_to(ROOT).as_posix()
    assert not out.exists();out.mkdir(parents=True)
    dump(out/'authorization.json',auth)
    budget=dict(reserved=0,maximum=3,path=out/'attempt_budget.json');models=[];passed=False;status='running'
    try:
        with extension.installed():
            candidate,result=run_arm(prep,out/'refinement','search',PILOT,3,True,budget,models)
            if not result['accepted'] or not result['new_executable_version']:
                status='pilot_refinement_failed_stop_before_multiseed';return
            excluded,sources=exclusions(root)
            development=read(prep/'history_cases.json')+read(prep/'common_cases.json')+read(prep/'search_cases.json')
            dump(out/'exclusion_manifest.json',dict(input_hashes=sorted(excluded|{loop.sha(c['rows']) for c in development}),sources=sources))
            holdout(out/'refinement',candidate,development,excluded)
            passed=read(out/'refinement/independent/summary.json')['all_five_pass_on_first_attributed_evidence']
            status='pilot_passed_multiseed_still_requires_separate_grant' if passed else 'pilot_independent_failed_stop_before_multiseed'
    except BaseException as exc:
        status='execution_exception';dump(out/'exception.json',dict(error=repr(exc)));raise
    finally:
        verify(root)
        dump(out/'outcome.json',dict(status=status,pilot_passed=passed,calls=sum(len(m.calls) for m in models),reserved=budget['reserved']))
        dump(out/'cost.json',search.native_cost(out))
        print('PILOT',status,flush=True)


def local_checks():
    checks=policy.tests();keep=dict(operation='keep',assertion_id='',assertions=[],reason='local fixture, not a model result')
    initial=read(search.SOURCES['bounded']);assert interface.assemble(keep,initial)==initial
    checks.append('keep preserves candidate')
    for field,value in [('operation','invent'),('assertion_id','a2'),('assertions',[{}])]:
        try:interface.assemble(dict(keep,**{field:value}),initial)
        except (AssertionError,ValueError,KeyError):checks.append('reject malformed '+field)
        else:raise AssertionError(field)
    return checks


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=('test','seal','search','qualify','pilot'))
    p.add_argument('--out',type=Path);p.add_argument('--seed',type=int,default=PILOT);p.add_argument('--authorization',type=Path)
    a=p.parse_args()
    if a.action=='test':print('PASS',len(local_checks()))
    elif a.action=='seal':seal(a.out.resolve())
    elif a.action=='search':run_search(a.out.resolve(),a.seed)
    elif a.action=='qualify':qualify(a.out.resolve(),a.seed)
    else:pilot(a.out.resolve(),a.authorization.resolve())
