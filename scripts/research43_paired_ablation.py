"""Precommitted single-step paired 2x2 treatment, six real calls / twelve arms.

The same actual proposal is evaluated with/without the historical gate. This
controls proposal randomness for the gate contrast, not for the search contrast.
No response templates; no archived good/bad proposals enter prompts or results.
"""
import argparse
import copy
import json
import os
from pathlib import Path
import shutil

import research17_loop as loop
import research17_model as base
import research30_ablation as old
import research31_gate as gate
import research32_runtime as extension
import research41_fresh_campaign as interface
from research20_remote import RemoteModel
from research34_applicability import native_target_gate
from research34_campaign import digest
from research35_campaign import holdout, join_results
from research30_ablation_report import metrics
from research17_report import cost_audit

ROOT=loop.ROOT
read,dump=loop.read,loop.dump
SEEDS=(4201,4211,4217)
HISTORY=ROOT/'deliverables/research30_ablation_prepare_20261020_r02'
INITIAL=ROOT/'deliverables/research41_prepare_20261022_r01/s4103/shared_initial.json'
ARMS=dict(A=dict(search=False,gate=False),B=dict(search=True,gate=False),
          C=dict(search=False,gate=True),D=dict(search=True,gate=True))


def files(folder):
    # os.walk reuses directory entry metadata instead of two remote stat calls
    # per artifact on the Windows/WSL filesystem. Do not follow symlinks.
    found=[]
    def visit(path):
        with os.scandir(path) as entries:
            for entry in entries:
                if entry.is_symlink():continue
                if entry.is_dir(follow_symlinks=False):visit(entry.path)
                elif entry.is_file(follow_symlinks=False):found.append(Path(entry.path))
    visit(folder)
    return sorted(found)


def schema(initial):
    s=interface.schema(initial)
    s['properties']['operation']['enum']=['keep','replace_one']
    s['properties']['assertion_id']['enum'].insert(0,'')
    s['properties']['assertions']['minItems']=0
    s['description']='keep requires empty assertion_id and empty assertions; replace_one requires exactly one stall-stability edit.'
    return s


def assemble(value,initial):
    assert type(value) is dict and set(value)=={'operation','assertion_id','assertions','reason'}
    assert type(value['reason']) is str and len(value['reason'])<=128
    if value['operation']=='keep':
        assert value['assertion_id']=='' and value['assertions']==[]
        return copy.deepcopy(initial)
    return interface.assemble(value,initial)


class Model(RemoteModel):
    def __init__(self,out,settings,request):
        super().__init__(out,settings)
        self.request=copy.deepcopy(request)
        self.assemble=assemble

    def _payload(self,*args,**kwargs):return copy.deepcopy(self.request)

    def save_decoded_output(self,folder,value,current,secret):
        assemble(value,current)
        dump(folder/'rendered_edit.json',value if value['operation']=='keep' else interface.render_edit(value,current))
        return super().save_decoded_output(folder,value,current,secret)


def settings(seed):
    s=old.config(1)
    s.update(expression_format='recursive_ast_reset_variadic_keep_v1',direct_property=False)
    s['options'].update(seed=seed,temperature=0.2,num_predict=1024)
    return s


def payload(folder,initial,feedback,seed):
    # Reuse the actual RTL/context and numeric evidence projector, but replace
    # the old text schema and tailored repair instruction with a neutral review.
    request=old.Model(folder,settings(seed))._payload(initial,'stall_stability',feedback,'controlled_review')
    inherited=json.loads(request['messages'][1]['content'])
    common=inherited['rtl_and_common_contract']
    common['allowed_property_signals']=list(base.SIGNALS)+['rst']
    common['signals']['rst']='Active-high synchronous reset; sampled operand allowed; native wrapper supplies disable iff(rst).'
    common['syntax']='Use the recursive Boolean AST. Explicit rst is allowed; clk is wrapper-only. Logical &&/|| have 2..8 operands, other arities unchanged.'
    common['rtl_before']['runtime_fault_modes']={m:i for i,m in enumerate(extension.runtime.MODES) if i}
    observed=inherited['boundary_repair']
    body=dict(rtl_and_common_contract=common,confirmed_obligations=base.SPECS,
        current_assertions=initial['assertions'],requested_obligation='stall_stability',
        output_schema=schema(initial),
        instruction='Review the existing assertion set against the public specification and only the supplied observed development evidence. Keep it if no change is warranted, or replace one existing stall-stability property. Choose all operands and timing; no predicate is supplied or repaired. Keep uses empty assertion_id/assertions. All other properties remain exactly unchanged.',
        temporal_semantics='A previously presented valid output that was not accepted must retain valid and payload at the following sample, including a ready-rise boundary, unless reset cancels the requirement. Requests count only on handshake. This is the common specification, not a generated assertion.',
        actual_observations=observed['actual_observations'],
        legal_failure_observations=observed['legal_failure_observations'],
        ordinary_observations=feedback['ordinary_observations'],
        observation_scope='These are the only observed cases visible to this generation. Unobserved cases are not known passes. No independent test or prior successful repair is provided.',
        enforcement='Remote JSON-object output only; recursive syntax checked locally, all admitted properties compiled/executed natively. No semantic rewriting.')
    request['messages']=[dict(role='system',content='Review native SVA using the shared specification and actual observations. Return exactly the supplied JSON AST edit schema; keep or replace_one. Choose predicates and timing yourself.'),dict(role='user',content=json.dumps(body))]
    return request


def protected():
    paths=[]
    for root in (ROOT/'deliverables/research40_interface_continuation_20261022_r01',
                 *(ROOT/f'deliverables/research41_real_20261022_r01/s{s}' for s in (4103,4111,4127,4133))):
        paths += [root/'core/freeze.json',root/'core/frozen_candidate.json',
                  root/'independent/split.json',root/'independent/summary.json']
    return {p.relative_to(ROOT).as_posix():digest(p) for p in paths}


def prior_test_hashes():
    """Hash-only exclusion: never send test records, outcomes or candidates."""
    found=set();sources=[]
    for pattern in ('research*/independent/split.json','research*/s*/independent/split.json'):
        for path in sorted((ROOT/'deliverables').glob(pattern)):
            value=read(path)
            cases=value if isinstance(value,list) else value.get('cases',value.get('boundary_cases',[])+value.get('drain_cases',[]))
            hashes={loop.sha(c['rows']) for c in cases if isinstance(c,dict) and 'rows' in c}
            found.update(hashes)
            sources.append(dict(path=path.relative_to(ROOT).as_posix(),sha256=digest(path),input_hashes=sorted(hashes),
                input_rows_available=bool(hashes),scope='Direct row cases only; legacy seed-only splits additionally require existing holdout exclusion inventory.'))
    return found,sources


def snapshot(out):
    target=out/'source_snapshot';target.mkdir(exist_ok=True,parents=True)
    for p in (ROOT/'scripts').glob('research*.py'):shutil.copy2(p,target/p.name)
    dump(target/'hashes.json',{p.name:digest(p) for p in target.glob('*.py')})


def check_sources(prep):
    for n,h in read(prep/'source_snapshot/hashes.json').items():assert digest(ROOT/'scripts'/n)==h,n
    for n,h in read(prep/'prepared_hashes.json').items():assert digest(prep/n)==h,n
    assert protected()==read(prep/'protected.json')


def prepare(search,out,exposure):
    loop.prepare(out)
    initial=read(INITIAL);history=read(HISTORY/'history_cases.json')
    baseline=read(HISTORY/'core/history/result.json')
    assert initial==read(HISTORY/'shared_initial.json')
    assert baseline['healthy'] and not any(baseline['counts'][k] for k in ('misses','false_positives','unknown'))
    acquired=read(search/'acquired_cases.json')
    assert read(search/'outcome.json')['all_healthy']
    dump(out/'shared_initial.json',initial);dump(out/'history_cases.json',history)
    dump(out/'history_binding.json',dict(path=str(HISTORY/'core/history/result.json'),sha256=digest(HISTORY/'core/history/result.json'),
        cases=105,new_executions=0,scope='Previously executed qualified common history; actual source/cost retained. Fresh common-case replay below checks the current runtime.'))
    dump(out/'search_binding.json',dict(path=str(search),protocol_hash=digest(search/'protocol.json'),acquired_hash=digest(search/'acquired_cases.json')))
    excluded,sources=prior_test_hashes()
    search_exposure=read(exposure)
    entries=search_exposure['records'] if isinstance(search_exposure,dict) else search_exposure
    assert len(entries)==60,'all_48_search_and_12_sweep_queries_required'
    excluded.update(e['rows_sha256'] for e in entries)
    extra_dev=ROOT/'deliverables/research41_prepare_20261022_r01/s4103/full_cases.json'
    excluded.update(loop.sha(c['rows']) for c in read(extra_dev))
    dump(out/'excluded_tests.json',dict(input_hashes=sorted(excluded),sources=sources,
        search_exposure_path=str(exposure),search_exposure_sha256=digest(exposure),search_query_records=entries,
        additional_old_development=dict(path=str(extra_dev),sha256=digest(extra_dev)),
        unsupported_seed_only_splits=[s['path'] for s in sources if not s['input_rows_available']],
        usage='Hash overlap checks only; no test feedback or outcome selection. Earlier published input inventory is also checked by the reused holdout function.'))
    dump(out/'protected.json',protected())
    previews={};qualification=[]
    with extension.installed():
        common=loop.replay(initial,out/'core/qualification/common',[history[0]])
        assert common['healthy'] and not any(common['counts'][k] for k in ('misses','false_positives','unknown'))
        for seed in SEEDS:
            child=out/f's{seed}'
            selected=[c for c in acquired if c['source_seed']==seed]
            assert len(selected)==2 and len({c['mode'] for c in selected})==2
            dump(child/'acquired_cases.json',selected)
            target=loop.replay(initial,child/'core/qualification/acquired',selected)
            assert target['healthy'] and target['counts']['misses']>=2 and not any(target['counts'][k] for k in ('false_positives','unknown'))
            for stream,use_search in (('ordinary',False),('search',True)):
                visible=join_results([common,target]) if use_search else common
                feedback=dict(requested_obligations=['stall_stability'],counts=visible['counts'],
                    actual_native_evidence=visible['feedback'],
                    ordinary_observations=dict(scenario=history[0]['id'],counts=common['counts'],
                        native_diagnostic=common['feedback'][0]))
                dump(child/stream/'feedback.json',feedback)
                request=payload(child/stream/'preview',initial,feedback,seed)
                dump(child/stream/'request.preview.json',request)
                previews[f's{seed}/{stream}/request.preview.json']=digest(child/stream/'request.preview.json')
            a=read(child/'ordinary/request.preview.json');b=read(child/'search/request.preview.json')
            ca=json.loads(a['messages'][1]['content']);cb=json.loads(b['messages'][1]['content'])
            assert ca['rtl_and_common_contract']==cb['rtl_and_common_contract']
            assert ca['current_assertions']==cb['current_assertions']
            assert ca['ordinary_observations']==cb['ordinary_observations']
            for c in selected:assert c['id'] not in json.dumps(a)
            for r in (a,b):assert not any(x in json.dumps(r) for x in ('research40','research41','verified_model_applicability_plan'))
            assert cb['actual_observations'] and not ca['actual_observations']
            qualification.append(dict(seed=seed,search_cases=len(selected),search_misses=target['counts']['misses'],
                common_information_equal=True,ordinary_contains_no_search_cases=True))
    keep=dict(operation='keep',assertion_id='',assertions=[],reason='Qualification fixture only, no model call.')
    assert assemble(keep,initial)==initial
    for change in (dict(assertion_id='a2'),dict(assertions=[{}])):
        try:assemble({**keep,**change},initial)
        except AssertionError:pass
        else:raise AssertionError('malformed_keep_accepted')
    dump(out/'qualification.json',dict(passed=True,seeds=qualification,keep_preserves_hash=True,
        qualification_fixture_is_not_model_response=True,model_calls=0,credentials_read=False))
    dump(out/'protocol.json',dict(seeds=SEEDS,arms=ARMS,physical_model_calls=6,logical_arm_calls=12,
        proposal_pairing='A/C share ordinary real proposal; B/D share search real proposal. One call per stream, no retries, no choosing among outputs.',
        initial_hash=loop.sha(initial),history_cases=len(history),temperature=0.2,max_output_tokens=1024,
        endpoint=settings(SEEDS[0])['remote_url'],model=settings(SEEDS[0])['remote_model'],preview_hashes=previews,
        admission='plain visible-current gate is identical; gated acceptance additionally requires full-history healthy and reset-aware history gate. All rejected/keep versions retained and tested.',
        gate_benefit='Count only current-pass/full-history-reject proposals with concrete FP/lost detection/required trigger loss. Interface/current failures and unknown-only rejects reported separately.',
        background='Public RTL, all fault modes, specification, shared weak initial candidate and common case. No research36 applicability windows or research40/41 success outputs.',
        independent='All 12 arms freeze first, then one new shared 56-case batch; exact duplicate frozen candidates share physical replay with bindings. Never feedback or select.',
        search_cost='Research42 contract queries physically acquired once, logically charged to B and D. Ordinary arms do not access oracle/search evidence. Report setup and postdecision measurement separately.',
        limits='Known FIFO plus artificial faults; three model seed requests; one-step paired gate decision effect, not multi-round policy effect or a guarantee of advantage. Service seed behavior unverified.',
        authorization='New six-call grant required. Research41 unused three calls are not transferred.'))
    snapshot(out)
    dump(out/'prepared_hashes.json',{p.relative_to(out).as_posix():digest(p) for p in files(out)
        if p.suffix=='.json' and 'source_snapshot' not in p.parts})
    dump(out/'local_cost.json',cost_audit(out,files(out)))
    print('PREPARED_SIX_CALLS',qualification,flush=True)


def current_decision(before,after,edit):
    reasons=[];target_gate=None
    if not after or not after.get('group') or not after['healthy']:
        reasons.append(dict(kind='visible_native_or_legal_control_failure'))
    if after and after.get('group'):
        info=loop.inspect(after['group']['ledger'])
        for kind in ('misses','false_positives','unknown'):
            if info[kind]:reasons.append(dict(kind='visible_'+kind,evidence_keys=sorted(info[kind])))
        targets=loop.inspect(before['group']['ledger'])['misses']
        if targets:
            if edit['operation']=='keep':reasons.append(dict(kind='keep_leaves_current_targets'))
            else:
                target_gate=native_target_gate(before,after,edit['assertion_id'])
                reasons+=target_gate['reasons']
    return dict(accepted=not reasons,reasons=reasons,target_gate=target_gate)


def run(prep,out,authorization):
    auth=read(authorization);protocol=read(prep/'protocol.json')
    assert auth['authorized_calls']==6 and auth['endpoint']==protocol['endpoint'] and auth['model']==protocol['model']
    assert auth['run_output']==out.relative_to(ROOT).as_posix()
    check_sources(prep)
    loop.prepare(out);snapshot(out);shutil.copy2(authorization,out/'authorization.json')
    dump(out/'protocol.json',protocol);dump(out/'prepared_source.json',dict(path=str(prep)))
    initial=read(prep/'shared_initial.json');history=read(prep/'history_cases.json')
    binding=read(prep/'history_binding.json');history_path=gate.portable(binding['path'])
    assert digest(history_path)==binding['sha256'];historical=read(history_path)
    common=read(prep/'core/qualification/common/result.json')
    frozen={};decisions={};models=[];reserved=0;status='running'
    try:
        with extension.installed():
            for seed in SEEDS:
                selected=read(prep/f's{seed}/acquired_cases.json')
                target=read(prep/f's{seed}/core/qualification/acquired/result.json')
                for stream,names in (('ordinary',('A','C')),('search',('B','D'))):
                    folder=out/f's{seed}'/stream
                    request=read(prep/f's{seed}/{stream}/request.preview.json')
                    llm=Model(folder,settings(seed),request);models.append(llm)
                    reserved+=1;assert reserved<=6
                    dump(out/'attempt_budget.json',dict(reserved=reserved,maximum=6))
                    call,proposal=llm.call(folder/'model_call',initial,'stall_stability',{},'paired_single_step_review')
                    visible=[history[0]]+(selected if stream=='search' else [])
                    before=join_results([common,target]) if stream=='search' else common
                    after=loop.replay(proposal,folder/'visible_native',visible) if proposal else None
                    edit=read(folder/'model_call/model_edit.json') if (folder/'model_call/model_edit.json').exists() else None
                    plain=current_decision(before,after,edit) if proposal else dict(accepted=False,reasons=[dict(kind='model_or_interface_failure',detail=call.get('candidate_error'))],target_gate=None)
                    dump(folder/'plain_decision.json',plain)  # before reading hidden history
                    ordinary=names[0];gated=names[1]
                    key=f's{seed}/{ordinary}'
                    frozen[key]=proposal if plain['accepted'] else initial
                    loop.freeze(out/'arms'/key,frozen[key],'plain_decision_before_hidden_history')
                    full=loop.replay(proposal,folder/'history_native',history) if proposal else None
                    hg=gate.decide(historical['group']['ledger'],full['group']['ledger']) if full and full.get('group') else dict(accepted=False,reasons=[dict(kind='history_native_unavailable')])
                    dump(folder/'historical_gate.json',hg)
                    reasons=list(plain['reasons'])+list(hg['reasons'])
                    if full and not full['healthy']:
                        reasons.append(dict(kind='history_native_or_legal_control_failure',
                            failing_health=[h for h in full.get('health',[]) if not h['okay']]))
                    gated_ok=bool(plain['accepted'] and full and full['healthy'] and hg['accepted'])
                    key_gate=f's{seed}/{gated}'
                    frozen[key_gate]=proposal if gated_ok else initial
                    loop.freeze(out/'arms'/key_gate,frozen[key_gate],'additional_history_gate_terminal')
                    assert not gated_ok or plain['accepted']
                    summary=dict(proposal_hash=loop.sha(proposal) if proposal else None,call=call,
                        plain=plain,gated=dict(accepted=gated_ok,reasons=reasons),
                        history=metrics(full) if full and full.get('group') else None,
                        current=metrics(after) if after and after.get('group') else None,
                        gate_incremental_rejection=bool(plain['accepted'] and not gated_ok),
                        proposal_shared_by=list(names),single_real_call=True)
                    dump(folder/'pair_result.json',summary)
                    for name,decision in ((ordinary,plain),(gated,summary['gated'])):
                        k=f's{seed}/{name}';decisions[k]=dict(accepted=decision['accepted'],
                            frozen_hash=loop.sha(frozen[k]),proposal_source=folder.relative_to(out).as_posix(),
                            proposal_hash=summary['proposal_hash'],search=stream=='search',gate=name==gated)
                        dump(out/'arms'/k/'decision.json',decisions[k])
                    print('PAIRED',seed,stream,plain['accepted'],gated_ok,flush=True)
            dump(out/'all_arms_freeze.json',decisions)
            excluded=set(read(prep/'excluded_tests.json')['input_hashes'])
            development=history+[c for s in SEEDS for c in read(prep/f's{s}/acquired_cases.json')]
            common_split=None;evaluated={}
            for key,candidate in frozen.items():
                h=loop.sha(candidate)
                if h not in evaluated:
                    dest=out/'evaluation'/h
                    loop.freeze(dest/'core',candidate,'all_arms_already_frozen_measurement_only')
                    holdout(dest,candidate,development,excluded,common_split)
                    if common_split is None:
                        common_split=read(dest/'independent/split.json')
                        dump(out/'common_independent_split.json',common_split)
                    evaluated[h]=dest.relative_to(out).as_posix()
                    print('INDEPENDENT',h,read(dest/'independent/summary.json')['all_five_pass_on_first_attributed_evidence'],flush=True)
                dump(out/'arms'/key/'evaluation_binding.json',dict(candidate_hash=h,physical_evaluation=evaluated[h],
                    shared_exact_candidate=True,logical_scenarios=56,unique_statistical_sample=False))
            status='six_proposals_twelve_paired_arms_completed'
    except BaseException:
        status='campaign_execution_exception'
        raise
    finally:
        assert protected()==read(prep/'protected.json'),'protected_historical_artifact_changed'
        calls=[c for m in models for c in m.calls]
        dump(out/'outcome.json',dict(status=status,calls=len(calls),reserved=reserved,decisions=decisions,
            max_calls=6,protected_artifacts_unchanged=True))
        dump(out/'cost.json',cost_audit(out,files(out)))
        print('TERMINAL',status,'calls',len(calls),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('prepare','run'))
    p.add_argument('--search',type=Path);p.add_argument('--exposure',type=Path);p.add_argument('--prepared',type=Path);p.add_argument('--authorization',type=Path)
    p.add_argument('--out',type=Path,required=True);a=p.parse_args();out=a.out.resolve();assert ROOT in out.parents
    if a.action=='prepare':prepare(a.search.resolve(),out,a.exposure.resolve())
    else:run(a.prepared.resolve(),out,a.authorization.resolve())
