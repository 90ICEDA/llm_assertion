"""Offline audit of real local model stream and original RTL phase/full gates."""
import argparse
import json
from pathlib import Path
import research60_local_phase as trial
g=trial.g


def run(root,out):
    out.mkdir(parents=True,exist_ok=False);checks=[];calls=[];versions=[];accepted=None;feedback=None
    def check(n,ok):checks.append(dict(name=n,passed=bool(ok)));assert ok,n
    prep=trial.P;current=g.read(prep/'shared_initial.json');known=g.read(prep/'known_rejected_sets.json')
    for n,h in g.read(prep/'sealed.json').items():check('prep/'+n,g.old.digest(prep/n)==h)
    for n,h in g.read(prep/'source_hashes.json').items():check('code/'+n,g.old.digest(g.ROOT/'scripts'/n)==h)
    check('runner_snapshot',g.old.digest(root/'runner_snapshot.py')==g.old.digest(Path(trial.__file__)))
    request_builder=trial.request
    candidate_adapter=g.prior.diagnostic.adapt
    if (root/'context_adapter_snapshot.py').exists():
        import research60_compact_local as compact
        request_builder=compact.request
        check('context_adapter_snapshot',g.old.digest(root/'context_adapter_snapshot.py')==g.old.digest(Path(compact.__file__)))
    if (root/'refinement_adapter_snapshot.py').exists():
        import research60_local_refine as refine
        request_builder=refine.request
        check('refinement_adapter_snapshot',g.old.digest(root/'refinement_adapter_snapshot.py')==g.old.digest(Path(refine.__file__)))
        for n,h in g.read(root/'feedback_sources.json').items():check('feedback_source/'+n,g.old.digest(g.ROOT/n)==h)
    if (root/'model_adapter_snapshot.py').exists():
        import research60_deepseek as alternative
        request_builder=alternative.request
        check('model_adapter_snapshot',g.old.digest(root/'model_adapter_snapshot.py')==g.old.digest(Path(alternative.__file__)))
    if (root/'contrast_adapter_snapshot.py').exists():
        import research61_contrast_refine as contrast
        request_builder=contrast.request
        check('contrast_adapter_snapshot',g.old.digest(root/'contrast_adapter_snapshot.py')==g.old.digest(Path(contrast.__file__)))
        check('decoded_pairs',g.read(root/'decoded_development_pairs.json')==contrast.decoded_table())
        extra=contrast.previous_rejections()
        check('cross_run_rejections',g.read(root/'extra_known_rejections.json')==json.loads(json.dumps(extra)))
        known.extend(extra)
    if (root/'ast_adapter_snapshot.py').exists():
        import research61_ast_local as ast_trial
        request_builder=ast_trial.request;candidate_adapter=ast_trial.adapt
        check('ast_adapter_snapshot',g.old.digest(root/'ast_adapter_snapshot.py')==g.old.digest(Path(ast_trial.__file__)))
        extra=ast_trial.prior.previous_rejections()
        check('ast_cross_run_rejections',g.read(root/'extra_known_rejections.json')==json.loads(json.dumps(extra)))
        known.extend(extra)
    if (root/'ast_feedback_snapshot.py').exists():
        import research61_ast_feedback as ast_feedback
        request_builder=ast_feedback.request
        check('ast_feedback_snapshot',g.old.digest(root/'ast_feedback_snapshot.py')==g.old.digest(Path(ast_feedback.__file__)))
        extra=ast_feedback.extra_rejections()
        check('ast_feedback_rejections',g.read(root/'feedback_rejections.json')==json.loads(json.dumps(extra)))
        check('ast_feedback_examples',g.read(root/'feedback_representatives.json')==ast_feedback.representatives())
        for n,h in g.read(root/'feedback_sources.json').items():check('ast_feedback_source/'+n,g.old.digest(g.ROOT/n)==h)
        known.extend(extra)
    if (root/'category_adapter_snapshot.py').exists():
        import research62_category as category_trial
        request_builder=category_trial.request;candidate_adapter=category_trial.adapt
        check('category_adapter_snapshot',g.old.digest(root/'category_adapter_snapshot.py')==g.old.digest(Path(category_trial.__file__)))
        extra=category_trial.ast.prior.previous_rejections()+category_trial.previous.extra_rejections()
        check('category_rejections',g.read(root/'extra_known_rejections.json')==json.loads(json.dumps(extra)))
        known.extend(extra)
    if (root/'comparison_adapter_snapshot.py').exists():
        import research62_comparison as comparison_trial
        request_builder=comparison_trial.request;candidate_adapter=comparison_trial.adapt
        check('comparison_adapter_snapshot',g.old.digest(root/'comparison_adapter_snapshot.py')==g.old.digest(Path(comparison_trial.__file__)))
        extra=comparison_trial.ast.prior.previous_rejections()+comparison_trial.category.previous.extra_rejections()
        check('comparison_rejections',g.read(root/'extra_known_rejections.json')==json.loads(json.dumps(extra)))
        known.extend(extra)
    load=g.read(root/'model_load/response.json');check('load_not_generation',load['done'] and load.get('response','')=='')
    for folder in sorted(root.glob('v[0-9]*')):
        path=folder/'model_call'
        if not (path/'result.json').exists():continue
        call=g.read(path/'result.json');calls.append(call)
        check(folder.name+'/stop_after_acceptance',accepted is None)
        req=g.read(path/'request.json')
        check(folder.name+'/actual_request',req==request_builder(prep,feedback,6001+int(folder.name[1:])))
        check(folder.name+'/local_endpoint',call.get('retries')==0 and req['model'] in ('qwen2.5-coder:7b-instruct','deepseek-coder:6.7b-instruct'))
        pre=g.read(folder/'context_preflight/result.json')
        check(folder.name+'/context_fit',pre['fits_with_output_reserve'] and pre['conservative_input_estimate']+pre['output_reserved_tokens']<pre['context_tokens'])
        stream=[json.loads(s) for s in (path/'response.stream.jsonl').read_text().splitlines()]
        content=''.join(s.get('message',{}).get('content','') for s in stream)
        response=g.read(path/'response.raw.json')
        check(folder.name+'/raw_content',content==response['message']['content'])
        check(folder.name+'/transport_result',call==g.read(path/'transport_result.json'))
        if call['status']!='response_received':
            check(folder.name+'/no_candidate_on_failed_transport',not (path/'candidate.json').exists())
            versions.append(dict(version=folder.name,transport=call));continue
        done=[s for s in stream if s.get('done')]
        check(folder.name+'/terminal',len(done)==1 and stream[-1]==done[0]==response['service_done'])
        check(folder.name+'/actual_tokens',call['prompt_tokens']==done[0]['prompt_eval_count'] and call['completion_tokens']==done[0]['eval_count'])
        check(folder.name+'/no_context_truncation',abs(call['prompt_tokens']-pre['rendered_prompt_tokens'])<=pre['wrapper_margin_tokens'])
        value=json.loads(content);check(folder.name+'/actual_model_json',value==g.read(path/'model_edit.json'))
        try:
            candidate,labels=candidate_adapter(value,current)
        except (ValueError,TypeError,KeyError,AssertionError) as exc:
            decision=dict(accepted=False,reasons=[dict(kind='interface_rejected',detail=str(exc))])
            check(folder.name+'/interface_rejection_reproduced',decision==g.read(folder/'decision.json'))
            check(folder.name+'/no_invalid_candidate',not (path/'candidate.json').exists())
            check(folder.name+'/no_native_after_interface_failure',not (folder/'alignment').exists() and not (folder/'history').exists())
            feedback=dict(actual_model_text=content,decision=decision)
            versions.append(dict(version=folder.name,decision=decision));continue
        check(folder.name+'/no_rewritten_predicates',candidate==g.read(path/'candidate.json'))
        if (root/'ast_adapter_snapshot.py').exists():
            check(folder.name+'/syntax_only_render',ast_trial.render(value)==g.read(path/'rendered_edit.json'))
        if (root/'category_adapter_snapshot.py').exists():
            check(folder.name+'/independent_category_gate',category_trial.validate(value)==g.read(path/'category_gate.json'))
            composed=category_trial.composed(value)
            check(folder.name+'/actual_model_composition',composed==g.read(path/'composed_model_ast.json'))
            check(folder.name+'/category_syntax_only_render',category_trial.ast.render(composed)==g.read(path/'rendered_edit.json'))
        if (root/'comparison_adapter_snapshot.py').exists():
            converted=comparison_trial.to_category(value)
            check(folder.name+'/comparison_conversion',converted==g.read(path/'category_ast.json'))
            check(folder.name+'/comparison_gate',comparison_trial.category.validate(converted)==g.read(path/'category_gate.json'))
            composed=comparison_trial.category.composed(converted)
            check(folder.name+'/comparison_composition',composed==g.read(path/'composed_model_ast.json'))
            check(folder.name+'/comparison_syntax_only_render',comparison_trial.ast.render(composed)==g.read(path/'rendered_edit.json'))
        check(folder.name+'/labels',labels==g.read(path/'label_mapping.json'))
        novelty=g.prior.prior.previous.novelty(candidate,known)
        check(folder.name+'/novelty',json.loads(json.dumps(novelty))==g.read(path/'novelty.json'))
        if not novelty['accepted']:
            check(folder.name+'/no_repeat_native',not (folder/'alignment').exists())
            decision=dict(accepted=False,reasons=novelty['reasons']);feedback=dict(actual_model_text=content,decision=decision)
            check(folder.name+'/repeat_decision',decision==g.read(folder/'decision.json'))
            versions.append(dict(version=folder.name,decision=decision));continue
        known.append(dict(source=str(path/'candidate.json'),signature=g.prior.prior.previous.op_signature(candidate)))
        native=g.read(folder/'alignment/result.json');gate=g.read(folder/'alignment/alignment_gate.json')
        check(folder.name+'/native',g.prior.diagnostic.audit_native(folder/'alignment',candidate,prep,'alignment')==240)
        focus=g.focus_gate(native,g.read(prep/'focus.private.json'))
        check(folder.name+'/focus',focus==gate['focus12']==g.read(folder/'alignment/focus_gate.json'))
        guard=g.prior.prior.native_flow.prior.all_property_guard(native,{rev:g.read(folder/'alignment'/rev/'result.json') for rev in ('before','after')},candidate)
        check(folder.name+'/guard',guard==gate['all_property_guard'])
        check(folder.name+'/gate',gate['accepted']==(g.old.admissible(native) and guard['accepted'] and focus['accepted'] and all(b['accepted'] for b in gate['bindings'])))
        decision=dict(accepted=False,reasons=[dict(kind='native_small_gate_failure')])
        feedback=dict(actual_model_proposal=value,native_counts=native['counts'],first_and_held=focus['phases'],required_untriggered=gate['required_untriggered'],actual_evidence=g.old.evidence(native))
        item=dict(version=folder.name,focus=focus['phases'],small_counts=native['counts'],required_untriggered=gate['required_untriggered'])
        if gate['accepted']:
            results={};guards={}
            for cohort in ('history','search'):
                results[cohort]=g.read(folder/cohort/'result.json')
                check(folder.name+'/'+cohort+'/native',g.prior.diagnostic.audit_native(folder/cohort,candidate,prep,cohort)==len(results[cohort]['ledger']))
                guards[cohort]=g.prior.prior.native_flow.prior.all_property_guard(results[cohort],{rev:g.read(folder/cohort/rev/'result.json') for rev in ('before','after')},candidate)
            combined=g.prior.prior.common.combine(results['history'],results['search'])
            protected=g.read(prep/'target_preservation.private.json');decision=g.prior.preserve(g.read(prep/'baseline_full.json'),combined,protected,g.old.decide)
            for cohort,guard in guards.items():
                if not guard['accepted']:decision['accepted']=False;decision['reasons'].append(dict(kind='all_property_false_alarm_or_unknown',cohort=cohort,details=guard))
            check(folder.name+'/full_guard',guards==g.read(folder/'all_property_guard.json'))
            check(folder.name+'/mapping',g.read(folder/'mapping.json')==dict(history=results['history']['mapping'],search=results['search']['mapping']))
            feedback=dict(actual_model_proposal=value,history=g.old.evidence(results['history']),search=g.old.evidence(results['search']),decision=g.prior.prior.common.gate_feedback(decision))
            item['full_counts']=combined['counts'];item['preservation']=decision['target_preservation']
            if decision['accepted']:accepted=candidate
        else:check(folder.name+'/no_full_after_failure',not (folder/'history').exists())
        check(folder.name+'/decision',decision==g.read(folder/'decision.json'));item['decision']=decision;versions.append(item)
    outcome=g.read(root/'outcome.json')
    check('call_count',outcome['calls']==len(calls)<=2 and outcome['remote_calls']==0)
    check('status',outcome['status']==('accepted_development_only' if accepted else 'no_accepted_sva'))
    check('accepted_hash',outcome['accepted_candidate_sha256']==(g.old.acceptance.sha(accepted) if accepted else None))
    if accepted:check('accepted_file',g.read(root/'accepted_candidate.json')==accepted)
    check('no_independent',outcome['independent_test']=='not_run' and not (root/'independent').exists())
    cost=g.old.cost_audit(root,[p for p in root.rglob('*') if p.is_file()]);check('cost',cost==g.read(root/'cost.json'))
    check('local_service_shutdown',g.read(root/'service_shutdown.json')['returncode'] is not None)
    g.dump(out/'audit.json',dict(passed=True,checks=checks,model_calls=0,new_native_calls=0))
    g.dump(out/'versions.json',versions);g.dump(out/'status.json',outcome)
    g.dump(out/'cost_roles.json',dict(generation_calls=len(calls),local_model_management_calls=1,
        prompt_tokens=sum(c['prompt_tokens'] for c in calls) if all(c.get('prompt_tokens') is not None for c in calls) else None,
        completion_tokens=sum(c['completion_tokens'] for c in calls) if all(c.get('completion_tokens') is not None for c in calls) else None,
        native_compile_calls=cost['total']['native_compile_calls'],native_execute_calls=cost['total']['native_execute_calls'],remote_calls=0,formal_calls=0))
    print('LOCAL_PHASE_AUDIT',len(checks),'passed',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();run(a.run.resolve(),a.out.resolve())
