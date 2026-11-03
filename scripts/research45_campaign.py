"""Bounded real refinement -> fresh holdout -> isolated four-arm pilot.

Prepare performs no model calls. Run requires an explicit eleven-call grant:
pilot <=3; only after native/history/new holdout pass, A/B/C/D <=2 each.
No shared proposals, no hidden-history feedback to A/B, no old successful SVA.
"""
import argparse
import copy
import json
from pathlib import Path
import shutil
import research17_loop as loop
import research43_paired_ablation as previous
import research44_interface as interface
import research31_gate as gate
import research32_runtime as extension
from research20_remote import RemoteModel
from research35_campaign import holdout, join_results
from research38_history_feedback import complete_feedback
from research17_report import cost_audit
from research30_ablation_report import metrics

ROOT=loop.ROOT
read,dump=loop.read,loop.dump
P43=interface.PREP
PILOT_SEED=4401
COMPARISON_SEED=4411
MAX_CALLS=11


def settings(seed, rounds):
    value=previous.settings(seed)
    value.update(max_model_calls=rounds,max_tokens=400000,max_wall_seconds=7200)
    value['options']['num_predict']=2048
    value['expression_format']='recursive_ast_reason_metadata_v2'
    return value


class Model(RemoteModel):
    def __init__(self, folder, config, request):
        super().__init__(folder,config)
        self.assemble=interface.assemble
        self.request=copy.deepcopy(request)
        # The payload override defines the actual token cap; avoid the inherited
        # transport's old 1024-cap metadata falsely describing a 2048 request.
        path=self.out/'remote_transport_config.json'
        metadata=read(path);metadata['max_output_tokens']=2048;dump(path,metadata)

    def _payload(self,*args,**kwargs):
        return copy.deepcopy(self.request)

    def save_decoded_output(self,folder,value,current,secret):
        interface.assemble(value,current)
        dump(folder/'rendered_edit.json',interface.rendered(value))
        dump(folder/'metadata_diagnostic.json',dict(reason_characters=len(value['reason']),
            saved_verbatim=True,reason_over_previous_limit=len(value['reason'])>128,
            explanation_is_not_executable_gate=True))
        return super().save_decoded_output(folder,value,current,secret)


def request_from(source,initial,seed,diagnostic=None):
    request=copy.deepcopy(source)
    body=json.loads(request['messages'][1]['content'])
    body['output_schema']=interface.schema(initial)
    # Uniformly remove old explanation prose from the executable initial set.
    # Some old reasons claimed checks that their actual predicates did not do.
    body['current_assertions']=[{k:v for k,v in a.items() if k!='reason'} for a in initial['assertions']]
    body['explanation_policy']='Only the property/AST determines executable behavior. Explanations are metadata, not proof that an obligation is checked; new reason strings are saved verbatim.'
    body['iteration_policy']='Review the actual native per-property observations and independent obligation checks. If an earlier proposal still misses an observed violation, compare the obligation-check sample with its antecedent and consequent before choosing another edit. No evaluator will fill in operands, fix timing or shorten your proposal. Keep is allowed but cannot resolve an observed missed target.'
    if diagnostic is not None:body['actual_previous_attempt']=diagnostic
    request['messages'][1]['content']=json.dumps(body)
    request.update(seed=seed,max_tokens=2048)
    return request


def feedback(result,decision,call,edit,previous_edit=None):
    value=complete_feedback(result,decision,call)
    value['previous_actual_model_edit']=edit
    value['repeated_actual_ast']=bool(edit and previous_edit and
        {k:v for k,v in edit.items() if k!='reason'}=={k:v for k,v in previous_edit.items() if k!='reason'})
    value['counts']=result.get('counts') if result else None
    value['no_predicate_answer_supplied']=True
    return value


def attempt_feedback(small,full,decision,call,edit,previous_edit=None):
    # The common scenario occurs in BOTH replays. Stable evidence identities
    # cannot be ledger-merged across different physical source directories.
    # Keep both actual records in separately scoped feedback instead.
    value=feedback(small,decision,call,edit,previous_edit)
    if full is not None:
        value['historical_replay']=complete_feedback(full,decision,call)
        value['historical_replay']['counts']=full.get('counts')
    return value


def extra_exclusions():
    values=set(read(P43/'excluded_tests.json')['input_hashes'])
    old_values,_=previous.prior_test_hashes();values.update(old_values)
    # research43's hash-shared evaluations live one level deeper than old trials.
    for path in (ROOT/'deliverables').glob('research*/evaluation/*/independent/split.json'):
        split=read(path)
        values.update(loop.sha(c['rows']) for c in split['boundary_cases']+split['drain_cases'])
    return values


def prepare(qualification,out):
    qualified=read(qualification/'qualification.json');assert qualified['passed']
    loop.prepare(out)
    initial=read(P43/'shared_initial.json')
    history=read(P43/'history_cases.json')
    dump(out/'shared_initial.json',initial);dump(out/'history_cases.json',history)
    shutil.copy2(P43/'history_binding.json',out/'history_binding.json')
    dump(out/'excluded_tests.json',dict(input_hashes=sorted(extra_exclusions()),usage='Hash-only exclusion; no old independent samples or outcomes in prompts.'))
    dump(out/'protected.json',previous.protected())
    bootstrap=qualification/'core/s4211/search'
    result=read(bootstrap/'native/result.json');decision=read(bootstrap/'decision.json')
    edit=read(bootstrap/'original_model_edit.json')
    assert result['healthy'] and result['counts']['misses']==2 and not decision['accepted']
    diagnostic=feedback(result,decision,dict(status='historical_response_replayed_under_new_interface',
        candidate_status='assembled_without_semantic_rewrite'),edit)
    dump(out/'pilot/bootstrap_diagnostic.json',diagnostic)
    dump(out/'bootstrap_binding.json',dict(path=str(bootstrap),result_sha256=previous.digest(bootstrap/'native/result.json'),
        edit_sha256=previous.digest(bootstrap/'original_model_edit.json'),scope='Pilot only. Never supplied to ablation arms.'))
    preview={}
    for name,source_seed,stream,seed in [('pilot',4211,'search',PILOT_SEED)]+[
        (f'arms/{name}',4217,'search' if value['search'] else 'ordinary',COMPARISON_SEED)
        for name,value in previous.ARMS.items()]:
        source=read(P43/f's{source_seed}/{stream}/request.preview.json')
        req=request_from(source,initial,seed,diagnostic if name=='pilot' else None)
        dump(out/name/'request.preview.json',req)
        preview[name]=req
        dump(out/name/'cases.json',[history[0]]+(read(P43/f's{source_seed}/acquired_cases.json') if stream=='search' else []))
        common_path=P43/'core/qualification/common/result.json'
        target_path=P43/f's{source_seed}/core/qualification/acquired/result.json' if stream=='search' else None
        dump(out/name/'baseline_binding.json',dict(common=str(common_path),common_sha256=previous.digest(common_path),
            target=str(target_path) if target_path else None,target_sha256=previous.digest(target_path) if target_path else None))
    assert preview['arms/A']==preview['arms/C'] and preview['arms/B']==preview['arms/D']
    initial_keys=('rtl_and_common_contract','current_assertions','confirmed_obligations','output_schema','temporal_semantics')
    bodies={k:json.loads(v['messages'][1]['content']) for k,v in preview.items() if k.startswith('arms/')}
    assert all(bodies['arms/A'][k]==b[k] for b in bodies.values() for k in initial_keys)
    for name in ('arms/A','arms/C'):
        assert not bodies[name]['actual_observations']
        assert 'actual_previous_attempt' not in bodies[name]
        for case in read(P43/'s4217/acquired_cases.json'):assert case['id'] not in json.dumps(preview[name])
    for req in preview.values():
        assert not any(x in json.dumps(req) for x in ('research40','research41','independent_test','all_five_pass_on_first_attributed_evidence'))
    dump(out/'qualification.json',dict(passed=True,model_calls=0,credential_read=False,
        prior_interface_qualification=str(qualification),native_bootstrap_misses=2,
        paired_first_requests_identical=True,common_information_equal=True,ordinary_search_isolation=True,
        pilot_diagnostics_excluded_from_ablation=True,old_independent_inputs_excluded=True))
    dump(out/'protocol.json',dict(maximum_model_calls=MAX_CALLS,pilot_maximum=3,arm_maximum=2,
        pilot_seed=PILOT_SEED,ablation_seed=COMPARISON_SEED,arms=previous.ARMS,
        endpoint=settings(PILOT_SEED,3)['remote_url'],model=settings(PILOT_SEED,3)['remote_model'],
        temperature=0.2,max_output_tokens=2048,retries=0,
        interface='Reason text saved without semantic length rejection. AST fields, signal and arity restrictions unchanged. No predicate rewriting.',
        sequence='Pilot bounded refinement, strict current+105-history gate, freeze, fresh56 holdout. Stop on any failure. Only on pilot holdout pass run four independent arms, each <=2 calls, same old initial candidate.',
        isolation='A/C and B/D first requests byte-identical but calls independent. Gate diagnostics only C/D subsequent requests; search witnesses only B/D. No pilot output enters any arm. A/B history is measurement after all freeze.',
        measurement='All arm versions freeze before common fresh56 holdout and hidden-history audit. All failures retained. Actual unequal token/native costs reported. Same candidate hash may share measurement, not sample counts.',
        scope='Single-case, single-seed small causal pilot, not a multiseed stability claim. Continuation after successful pilot is explicitly conditional; outcomes need not favor either mechanism.',
        budget='All previous general-purpose grants exhausted. New explicit maximum11 grant required; prior research41 restricted remainder is not transferred.'))
    previous.snapshot(out)
    dump(out/'prepared_hashes.json',{p.relative_to(out).as_posix():previous.digest(p) for p in previous.files(out)
        if p.suffix=='.json' and 'source_snapshot' not in p.parts})
    print('PREPARED_PILOT_THEN_FOUR_ARMS',dict(maximum_calls=11,checks='passed'),flush=True)


def baseline(prep,name):
    binding=read(prep/name/'baseline_binding.json')
    common=gate.portable(binding['common']);assert previous.digest(common)==binding['common_sha256']
    parts=[read(common)]
    if binding['target']:
        target=gate.portable(binding['target']);assert previous.digest(target)==binding['target_sha256']
        parts.append(read(target))
    return join_results(parts) if len(parts)>1 else parts[0]


def run_arm(prep,out,name,seed,rounds,use_gate,models,budget):
    initial=read(prep/'shared_initial.json');current=initial
    before=baseline(prep,name);cases=read(prep/name/'cases.json')
    history=read(prep/'history_cases.json');binding=read(prep/'history_binding.json')
    path=gate.portable(binding['path']);assert previous.digest(path)==binding['sha256']
    historic=read(path)
    request=read(prep/name/'request.preview.json')
    model=Model(out/'model',settings(seed,rounds),request);models.append(model)
    past_edit=None;accepted=False;decisions=[]
    for iteration in range(rounds):
        folder=out/'core'/f'v{iteration}'
        if (folder/'model_call/result.json').exists():
            # Resume a completed call, never repeat it or reset its cost.
            assert read(folder/'model_call/request.json')==model.request,'resume_request_changed'
            call=read(folder/'model_call/result.json');model.calls.append(call)
            proposal=read(folder/'model_call/candidate.json') if (folder/'model_call/candidate.json').exists() else None
        else:
            assert not (folder/'model_call').exists(),'incomplete_call_requires_terminal_audit_not_retry'
            budget['reserved']+=1;assert budget['reserved']<=MAX_CALLS
            dump(budget['path'],{k:v for k,v in budget.items() if k!='path'})
            call,proposal=model.call(folder/'model_call',current,'stall_stability',{},'bounded_numeric_refinement')
        edit_path=folder/'model_call/model_edit.json'
        edit=read(edit_path) if edit_path.exists() else None
        small=(read(folder/'visible_native/result.json') if (folder/'visible_native/result.json').exists()
            else loop.replay(proposal,folder/'visible_native',cases)) if proposal else None
        plain=previous.current_decision(before,small,edit) if proposal else dict(accepted=False,reasons=[dict(kind='model_or_interface_failure')])
        if (folder/'plain_decision.json').exists():assert read(folder/'plain_decision.json')==plain
        else:dump(folder/'plain_decision.json',plain)
        full=(read(folder/'history_native/result.json') if (folder/'history_native/result.json').exists()
            else loop.replay(proposal,folder/'history_native',history)) if proposal and use_gate else None
        historical=(gate.decide(historic['group']['ledger'],full['group']['ledger'])
            if full and full.get('group') else dict(accepted=False,reasons=[dict(kind='history_not_executed')]))
        if use_gate:
            if (folder/'history_gate.json').exists():assert read(folder/'history_gate.json')==historical
            else:dump(folder/'history_gate.json',historical)
        reasons=list(plain['reasons'])
        if use_gate:
            reasons+=historical['reasons']
            if full and not full['healthy']:reasons.append(dict(kind='history_native_unhealthy'))
        accepted=bool(plain['accepted'] and (not use_gate or (full and full['healthy'] and historical['accepted'])))
        decision=dict(accepted=accepted,reasons=reasons,use_gate=use_gate,
            candidate_hash=loop.sha(proposal) if proposal else None,
            current=metrics(small) if small and small.get('group') else None,
            history=metrics(full) if full and full.get('group') else None,
            plain_accepted=plain['accepted'],call=call)
        if (folder/'decision.json').exists():assert read(folder/'decision.json')==decision
        else:dump(folder/'decision.json',decision)
        decisions.append(decision)
        print('REFINE',name,iteration,'accepted',accepted,'reason_count',len(reasons),flush=True)
        if accepted:current=proposal;break
        # Full history reaches this path only for gated arms. No duplicate-ID
        # ledger merge; current and historical numeric observations stay scoped.
        diagnostic=attempt_feedback(small,full,decision,call,edit,past_edit)
        dump(folder/'next_feedback.json',diagnostic)
        model.request=request_from(request,current,seed,diagnostic)
        past_edit=edit
    loop.freeze(out/'core',current,'bounded_terminal_before_independent_inputs')
    result=dict(accepted=accepted,new_executable_version=interface.executable_hash(current)!=interface.executable_hash(initial),
        candidate_hash=loop.sha(current),calls=len(model.calls),decisions=decisions)
    dump(out/'outcome.json',result)
    return current,result


def run(prep,out,authorization,resume=False):
    auth=read(authorization);protocol=read(prep/'protocol.json')
    assert auth['authorized_calls']==MAX_CALLS and auth['endpoint']==protocol['endpoint'] and auth['model']==protocol['model']
    assert auth['run_output']==out.relative_to(ROOT).as_posix()
    if resume:
        amendment=read(out/'amendments/feedback_scope_v1/amendment.json')
        assert read(out/'outcome.json')['status']=='execution_exception'
        for name,h in read(prep/'source_snapshot/hashes.json').items():
            expected=amendment['new_campaign_sha256'] if name=='research45_campaign.py' else h
            assert previous.digest(ROOT/'scripts'/name)==expected,name
        for name,h in read(prep/'prepared_hashes.json').items():assert previous.digest(prep/name)==h,name
        assert previous.protected()==read(prep/'protected.json')
        assert read(out/'authorization.json')==auth
    else:previous.check_sources(prep)
    binding=read(prep/'bootstrap_binding.json');bootstrap=gate.portable(binding['path'])
    assert previous.digest(bootstrap/'native/result.json')==binding['result_sha256']
    assert previous.digest(bootstrap/'original_model_edit.json')==binding['edit_sha256']
    if not resume:
        loop.prepare(out);previous.snapshot(out)
        shutil.copy2(authorization,out/'authorization.json');shutil.copy2(prep/'protocol.json',out/'protocol.json')
        dump(out/'prepared_source.json',dict(path=str(prep)))
    attempted=list(out.glob('pilot/core/v*/model_call/attempt.json'))+list(out.glob('arms/*/core/v*/model_call/attempt.json'))
    models=[];budget=dict(reserved=len(attempted),maximum=MAX_CALLS,path=out/'attempt_budget.json')
    status='running';arms={};excluded=set(read(prep/'excluded_tests.json')['input_hashes'])
    history=read(prep/'history_cases.json')
    development=history+read(prep/'pilot/cases.json')+read(prep/'arms/D/cases.json')
    try:
        with extension.installed():
            candidate,pilot=run_arm(prep,out/'pilot','pilot',PILOT_SEED,3,True,models,budget)
            if not pilot['accepted'] or not pilot['new_executable_version']:
                status='pilot_refinement_unresolved';return
            holdout(out/'pilot',candidate,development,excluded)
            if not read(out/'pilot/independent/summary.json')['all_five_pass_on_first_attributed_evidence']:
                status='pilot_new_independent_failed_no_ablation';return
            split=read(out/'pilot/independent/split.json')
            excluded.update(loop.sha(c['rows']) for c in split['boundary_cases']+split['drain_cases'])
            frozen={}
            for name,arm in previous.ARMS.items():
                frozen[name],arms[name]=run_arm(prep,out/'arms'/name,f'arms/{name}',COMPARISON_SEED,2,arm['gate'],models,budget)
            dump(out/'all_arms_freeze.json',{n:loop.sha(c) for n,c in frozen.items()})
            common_split=None;evaluated={}
            for name,candidate in frozen.items():
                h=loop.sha(candidate)
                if h not in evaluated:
                    dest=out/'evaluation'/h
                    loop.freeze(dest/'core',candidate,'all_arms_frozen_measurement_only')
                    full=loop.replay(candidate,dest/'history_native',history)
                    acquired=loop.replay(candidate,dest/'search_native',read(prep/'arms/D/cases.json')[1:])
                    dump(dest/'measurement.json',dict(history=metrics(full) if full.get('group') else None,
                        search=metrics(acquired) if acquired.get('group') else None))
                    holdout(dest,candidate,development,excluded,common_split)
                    if common_split is None:
                        common_split=read(dest/'independent/split.json');dump(out/'common_independent_split.json',common_split)
                    evaluated[h]=dest.relative_to(out).as_posix()
                dump(out/'arms'/name/'evaluation_binding.json',dict(candidate_hash=h,path=evaluated[h],shared_exact_hash=True))
            status='pilot_passed_four_arm_experiment_completed'
    except BaseException:
        status='execution_exception';raise
    finally:
        dump(out/'outcome.json',dict(status=status,reserved_calls=budget['reserved'],actual_calls=sum(len(m.calls) for m in models),
            max_calls=MAX_CALLS,arms=arms,feedback_scope_amendment=resume,
            protected_unchanged=previous.protected()==read(prep/'protected.json')))
        dump(out/'cost.json',cost_audit(out,previous.files(out)))
        print('TERMINAL',status,'calls',sum(len(m.calls) for m in models),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('prepare','run'))
    p.add_argument('--qualification',type=Path);p.add_argument('--prepared',type=Path);p.add_argument('--authorization',type=Path)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--resume',action='store_true');a=p.parse_args();out=a.out.resolve();assert ROOT in out.parents
    if a.action=='prepare':prepare(a.qualification.resolve(),out)
    else:run(a.prepared.resolve(),out,a.authorization.resolve(),a.resume)
