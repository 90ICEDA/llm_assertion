"""Audit research59 streams, native phase windows and full acceptance if reached."""
import argparse
import json
from pathlib import Path
from unittest.mock import patch
import research58_result_audit as base
import research59_phase_gate as g


def run(prep,root,out):
    if any(g.read(p)['status']=='transport_timeout' for p in root.glob('v*/model_call/result.json')):
        return audit_with_timeout(prep,root,out)
    original=g.prior.payload
    def payload(*args):
        with patch.object(g.prior,'payload',original):
            return g.payload(*args)
    with patch.object(g.prior,'payload',payload):
        base.run(prep,root,out)
    report=g.read(out/'audit.json');checks=report['checks'];versions=[]
    def check(name,ok):checks.append(dict(name=name,passed=bool(ok)));assert ok,name
    manifest=g.read(prep/'focus.private.json')
    for folder in sorted(root.glob('v[0-9]*')):
        if not (folder/'alignment/result.json').exists():
            versions.append(dict(version=folder.name,native='not_run',decision=g.read(folder/'decision.json')))
            continue
        result=g.read(folder/'alignment/result.json');gate=g.read(folder/'alignment/alignment_gate.json')
        focus=g.focus_gate(result,manifest)
        check(folder.name+'/focus_exact',focus==gate['focus12']==g.read(folder/'alignment/focus_gate.json'))
        check(folder.name+'/focus_controls_entry',not gate['accepted'] or focus['accepted'])
        check(folder.name+'/no_full_after_failed_focus',focus['accepted'] or not (folder/'history').exists())
        versions.append(dict(version=folder.name,focus=focus,counts=result['counts'],required_untriggered=gate['required_untriggered'],decision=g.read(folder/'decision.json')))
    report['scope']='Real research59 exact model streams, native first3/held9 sampling and triggers; original all9 and full151/690 checks retained.'
    g.dump(out/'audit.json',report);g.dump(out/'phase_results.json',versions)
    print('PHASE_RESULT_AUDIT',len(checks),'passed',flush=True)


def audit_with_timeout(prep,root,out):
    """Do not reinterpret a timeout as an HTTP response or invent token usage."""
    out.mkdir(parents=True,exist_ok=False);checks=[];calls=[];versions=[];decisions=[];accepted=None
    def check(name,ok):checks.append(dict(name=name,passed=bool(ok)));assert ok,name
    for n,h in g.read(prep/'sealed.json').items():check('sealed/'+n,g.old.digest(prep/n)==h)
    for n,h in g.read(prep/'source_hashes.json').items():
        check('code/'+n,g.old.digest(g.ROOT/'scripts'/n)==h)
        check('run_code/'+n,g.old.digest(root/'source_snapshot'/n)==h)
    for n,h in g.read(prep/'failure_binding.json').items():check('evidence/'+n,g.old.digest(g.ROOT/n)==h)
    auth=g.read(root/'authorization.json');protocol=g.read(prep/'protocol.json')
    check('grant',auth['scope']==protocol['scope'] and auth['authorized_calls']==2 and auth['endpoint']==protocol['endpoint'])
    check('grant_request',auth['request_sha256']==g.old.digest(prep/'request.preview.json'))
    check('grant_output',auth['run_output']==root.relative_to(g.ROOT).as_posix())
    current=g.read(prep/'shared_initial.json');feedback=g.read(prep/'initial_feedback.json');known=g.read(prep/'known_rejected_sets.json')
    manifest=g.read(prep/'focus.private.json');protected=g.read(prep/'target_preservation.private.json')
    for folder in sorted(root.glob('v[0-9]*')):
        path=folder/'model_call';call=g.read(path/'result.json');calls.append(call)
        check(folder.name+'/stop_after_accept',accepted is None)
        check(folder.name+'/request',g.read(path/'request.json')==g.payload(prep,current,feedback))
        check(folder.name+'/retry_count',call['retries']==0)
        if call['status']=='transport_timeout':
            check(folder.name+'/timeout',call['error']['type']=='TimeoutError' and call['candidate_status']=='not_generated')
            check(folder.name+'/unavailable_usage',not call['usage_available'] and call['prompt_tokens'] is None and call['completion_tokens'] is None)
            check(folder.name+'/no_invented_response',call['partial_response_characters']==0 and not call['stream_terminal_received'] and not (path/'model_edit.json').exists())
            check(folder.name+'/no_native',not (folder/'alignment').exists())
            diag=dict(call=call);decision=dict(accepted=False,reasons=[dict(kind='interface_or_transport_rejected',details=diag)])
            feedback=dict(previous_feedback=feedback,actual_model_proposal=None,actual_interface_diagnosis=diag,call=call)
            item=dict(version=folder.name,status=call['status'],native='not_run')
        else:
            check(folder.name+'/complete_model_response',call['status']=='response_received' and call['stream_terminal_received'])
            events=[json.loads(s) for s in (path/'response.events.jsonl').read_text().splitlines()];raw=[];terminal=False
            for line in (path/'response.stream.raw').read_text().splitlines():
                if line.startswith('data:'):
                    data=line[5:].strip()
                    if data=='[DONE]':terminal=True
                    elif data:raw.append(json.loads(data))
            check(folder.name+'/stream',raw==events and terminal)
            content=''.join(c.get('delta',{}).get('content') or '' for e in events for c in e.get('choices',[]) if c.get('index',0)==0)
            check(folder.name+'/assembled',content==g.read(path/'response.assembled.json')['message']['content'])
            value=json.loads(content);check(folder.name+'/model_edit',value==g.read(path/'model_edit.json'))
            check(folder.name+'/usage',any(e.get('usage',{}).get('prompt_tokens')==call['prompt_tokens'] and e.get('usage',{}).get('completion_tokens')==call['completion_tokens'] for e in events if e.get('usage')))
            check(folder.name+'/actual_model',call['actual_server_model']==protocol['model'])
            candidate,labels=g.prior.diagnostic.adapt(value,current)
            check(folder.name+'/predicates',candidate==g.read(path/'candidate.json'))
            check(folder.name+'/labels',g.read(path/'label_mapping.json')==dict(labels=labels,predicates_rewritten=False))
            verdict=g.prior.prior.previous.novelty(candidate,known)
            check(folder.name+'/novelty',json.loads(json.dumps(verdict))==g.read(path/'novelty_gate.json'))
            known.append(dict(source=str(path/'candidate.json'),signature=g.prior.prior.previous.op_signature(candidate)))
            item=dict(version=folder.name,status=call['status'],raw_model_edit=value)
            if not verdict['accepted']:
                check(folder.name+'/no_duplicate_native',not (folder/'alignment').exists())
                diag=g.read(path/'interface_gate.json');decision=dict(accepted=False,reasons=[dict(kind='interface_or_transport_rejected',details=diag)])
                feedback=dict(previous_feedback=feedback,actual_model_proposal=value,actual_interface_diagnosis=diag,call=call)
            else:
                check(folder.name+'/raw_native',g.prior.diagnostic.audit_native(folder/'alignment',candidate,prep,'alignment')==240)
                result=g.read(folder/'alignment/result.json');gate=g.read(folder/'alignment/alignment_gate.json')
                focus=g.focus_gate(result,manifest);guard=g.prior.prior.native_flow.prior.all_property_guard(result,{rev:g.read(folder/'alignment'/rev/'result.json') for rev in ('before','after')},candidate)
                check(folder.name+'/focus',focus==gate['focus12']==g.read(folder/'alignment/focus_gate.json'))
                check(folder.name+'/native_guard',gate['all_property_guard']==guard)
                check(folder.name+'/native_gate',gate['accepted']==(g.old.admissible(result) and guard['accepted'] and focus['accepted'] and all(b['accepted'] for b in gate['bindings'])))
                item.update(focus=focus,counts=result['counts'],required_untriggered=gate['required_untriggered'])
                if not gate['accepted']:
                    check(folder.name+'/no_full_after_failed_gate',not (folder/'history').exists() and not (folder/'search').exists())
                    decision=dict(accepted=False,reasons=[dict(kind='native_applicability_or_target_failure')])
                    feedback=dict(actual_model_proposal=value,native_alignment_gate=gate,native_evidence=g.old.evidence(result),previous_full_development_feedback=g.read(prep/'initial_feedback.json')['native_development_feedback'])
                else:
                    results={};guards={}
                    for cohort in ('history','search'):
                        g.prior.diagnostic.audit_native(folder/cohort,candidate,prep,cohort)
                        results[cohort]=g.read(folder/cohort/'result.json')
                        guards[cohort]=g.prior.prior.native_flow.prior.all_property_guard(results[cohort],{rev:g.read(folder/cohort/rev/'result.json') for rev in ('before','after')},candidate)
                    combined=g.prior.prior.common.combine(results['history'],results['search'])
                    decision=g.prior.preserve(g.read(prep/'baseline_full.json'),combined,protected,g.old.decide)
                    for cohort,guard in guards.items():
                        if not guard['accepted']:
                            decision['accepted']=False;decision['reasons'].append(dict(kind='all_property_false_alarm_or_unknown',cohort=cohort,details=guard))
                    check(folder.name+'/full_guards',guards==g.read(folder/'all_property_guard.json'))
                    feedback=dict(actual_model_proposal=value,history=g.old.evidence(results['history']),search=g.old.evidence(results['search']),decision=g.prior.prior.common.gate_feedback(decision))
                    if decision['accepted']:accepted=candidate
        check(folder.name+'/decision',decision==g.read(folder/'decision.json'))
        decisions.append(dict(version=int(folder.name[1:]),accepted=decision['accepted']));item['decision']=decision;versions.append(item)
    outcome=g.read(root/'outcome.json')
    check('outcome_decisions',outcome['decisions']==decisions and outcome['calls']==len(calls)<=2)
    check('acceptance',outcome['status']==('accepted_development_only' if accepted else 'no_accepted_sva') and outcome['accepted_candidate_sha256']==(g.old.acceptance.sha(accepted) if accepted else None))
    check('accepted_file',g.read(root/'accepted_candidate.json')==accepted if accepted else not (root/'accepted_candidate.json').exists())
    check('no_independent',outcome['independent_test']=='not_run' and not (root/'independent').exists())
    cost=g.old.cost_audit(root,[p for p in root.rglob('*') if p.is_file()]);check('cost',cost==g.read(root/'cost.json'))
    totals=cost['total']
    g.dump(out/'cost_roles.json',dict(model_calls=len(calls),prompt_tokens=totals['prompt_tokens_total'],completion_tokens=totals['completion_tokens_total'],
        prompt_tokens_known_subtotal=totals['prompt_tokens_known_subtotal'],completion_tokens_known_subtotal=totals['completion_tokens_known_subtotal'],usage_unavailable_calls=totals['usage_unavailable_calls'],
        native_compile_calls=totals['native_compile_calls'],native_full_execute_calls=totals['native_execute_calls'],formal_calls=0,remaining_calls=2-len(calls),monetary_cost=None))
    g.dump(out/'audit.json',dict(passed=True,checks=checks,model_calls=0,new_native_calls=0,scope='Timeout retained explicitly; completed response and native first/held gate audited against immutable logs.'))
    g.dump(out/'phase_results.json',versions);g.dump(out/'status.json',outcome)
    print('PHASE_TIMEOUT_RESULT_AUDIT',len(checks),'passed',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prepared',type=Path,required=True);p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();run(a.prepared.resolve(),a.run.resolve(),a.out.resolve())
