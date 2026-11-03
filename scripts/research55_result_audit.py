"""Audit research55 real proposals, native observations and stage decisions offline."""
import argparse
import json
import re
from pathlib import Path
import research55_native_plan_alignment as g


def run(prep, root, out):
    out.mkdir(parents=True,exist_ok=False);checks=[];calls=[];native=[];versions=[]
    def check(name,ok):checks.append(dict(name=name,passed=bool(ok)));assert ok,name
    for n,h in g.read(prep/'sealed.json').items():check('sealed/'+n,g.old.digest(prep/n)==h)
    for n,h in g.read(prep/'source_hashes.json').items():
        check('source/'+n,g.old.digest(g.ROOT/'scripts'/n)==h)
        check('run_source/'+n,g.old.digest(root/'source_snapshot'/n)==h)
    for n,h in g.read(prep/'failure_binding.json').items():check('failure_binding/'+n,g.old.digest(g.ROOT/n)==h)
    g.prior.components(prep)
    auth=g.read(root/'authorization.json');protocol=g.read(prep/'protocol.json')
    check('auth_scope',auth['scope']==protocol['scope'] and auth['authorized_calls']==2)
    check('auth_request',auth['request_sha256']==g.old.digest(prep/'request.preview.json'))
    check('auth_endpoint',auth['endpoint']==protocol['endpoint'])
    check('auth_output',auth['run_output']==root.relative_to(g.ROOT).as_posix())

    def native_check(folder,candidate,cohort):
        result=g.read(folder/'result.json');tx=g.read(prep/(cohort+'_cases.json'));rows=g.old.samples(tx,cohort)
        prefix=str(folder.relative_to(root))+'/'
        check(prefix+'inputs',g.read(folder/'samples.json')==rows and g.read(folder/'transactions.json')==tx)
        traces={};marks={};natives={}
        for rev in ('before','after'):
            path=folder/rev;nr=g.read(path/'result.json');native.append(nr);natives[rev]=nr
            check(prefix+rev+'/exact_bench',path.joinpath('tb.sv').read_text()==g.old.bench(candidate,rows,g.old.CONFIGS,folder/'stimulus.txt'))
            check(prefix+rev+'/original_rtl',all(str(prep/rev/n) in nr['compile']['argv'] for n in ('ibex_decoder.sv','ibex_defines.sv')))
            # A failed native run is a valid negative experiment, not passing evidence.
            if nr['execution_status']=='completed':
                traces[rev]=g.common.trace(path/'execute.log')
                log=path.joinpath('execute.log').read_text()
                marks[rev]={k:{(m[0],int(m[1])) for m in re.findall(r'^'+k+r' (\w+) cycle=(-?\d+)$',log,re.M)} for k in ('TRIGGER','ASSERT_FAIL')}
        healthy=all(n['compile_status']=='passed' and n['execution_status']=='completed' for n in natives.values()) and all(len(traces.get(v,{}))==len(rows) for v in ('before','after'))
        check(prefix+'health_status',result['healthy']==healthy)
        issues=[];reference=[]
        if healthy:
            for rev in traces:check(prefix+rev+'/wave', (folder/rev/'wave.vcd').stat().st_size>0)
            for s in rows:
                sid=s['sample_id']
                for ci,cfg in enumerate(g.old.CONFIGS):
                    expected=g.old.historical.oracle(s['instruction'],s['instr_new'],cfg)
                    actual={v:(int(traces[v][sid]['observed'],2)>>ci)&1 for v in traces}
                    reference.append(dict(**s,configuration=cfg,expected=expected,actual=actual,obligation=g.old.obligation(s)))
            for row in result['ledger']:
                s=row['sample'];sid=s['sample_id'];cfg=row['configuration'];ci=g.old.CONFIGS.index(cfg);rev=row['revision']
                observed={v:(int(traces[v][sid]['observed'],2)>>ci)&1 for v in traces}
                exp=g.old.historical.oracle(s['instruction'],s['instr_new'],cfg)
                ok=rows[sid]==s and row['expected']==exp and row['observed']==observed[rev]
                for v in traces:
                    t=traces[v][sid]
                    ok &= int(t['instr'],16)==s['instruction'] and int(t['new'])==s['instr_new'] and int(t['txn'])==s['transaction_id'] and int(t['phase'])==s['phase']
                for a in row['native']['assertions']:
                    p=next(p for p in candidate['assertions'] if p['id']==a['id']);name=a['id']+f'_c{ci}'
                    trigger=(name,sid-p['delay']) in marks[rev]['TRIGGER'];failed=(name,sid) in marks[rev]['ASSERT_FAIL']
                    detected=rev=='before' and observed[rev]!=exp and observed['after']==exp and trigger and failed and (name,sid) not in marks['after']['ASSERT_FAIL']
                    ok &= (trigger,failed,detected)==(a['trigger'],a['failed'],a['causal_detection'])
                if not ok:issues.append(row['evidence_id'])
        check(prefix+'raw_reference',reference==result['reference'])
        check(prefix+'raw_ledger',not issues and len(result['ledger'])==(len(rows)*6 if healthy else 0))
        info=g.old.acceptance.inspect(result['ledger'])
        check(prefix+'counts_mapping',not info['errors'] and result['counts']=={k:len(info[k]) for k in result['counts']} and result['mapping']==info['mapping'])
        check(prefix+'required_triggers',set(result['required_untriggered'])=={k for k,r in info['rows'].items() if r['required'] and k not in info['triggers']})
        guard=g.prior.all_property_guard(result,natives,candidate)
        return result,guard

    current=g.read(prep/'shared_initial.json');baseline=g.read(prep/'baseline_full.json')
    feedback=g.read(prep/'initial_feedback.json');decisions=[];seen=set();accepted=None;predicate_sets=[]
    for folder in sorted(root.glob('v[0-9]*')):
        check('stop_after_acceptance/'+folder.name,accepted is None)
        base=folder/'model_call';call=g.read(base/'result.json');calls.append(call)
        check(folder.name+'/exact_request',g.read(base/'request.json')==g.payload(prep,current,feedback))
        if call['status']=='service_http_error':
            check(folder.name+'/http_error_record',call['error']['type']=='HTTPError' and isinstance(call['error']['http_status'],int))
            check(folder.name+'/no_http_retry',call['retries']==0)
            check(folder.name+'/no_candidate_after_http_error',call['candidate_status']=='not_generated' and not (base/'candidate.json').exists() and not (base/'model_edit.json').exists())
            check(folder.name+'/usage_unavailable',not call['usage_available'] and call['prompt_tokens'] is None and call['completion_tokens'] is None)
            check(folder.name+'/no_native_after_http_error',not any((folder/n).exists() for n in ('alignment','history','search')))
            diag=dict(call=call)
            decision=dict(accepted=False,reasons=[dict(kind='interface_or_transport_rejected',details=diag)])
            check(folder.name+'/http_rejection_decision',decision==g.read(folder/'decision.json'))
            feedback=dict(previous_feedback=feedback,actual_model_proposal=None,actual_interface_diagnosis=diag,call=call)
            versions.append(dict(version=folder.name,transport=call,decision=decision,raw_model_edit=None))
            decisions.append(dict(version=int(folder.name[1:]),accepted=False))
            continue
        events=[json.loads(line) for line in (base/'response.events.jsonl').read_text().splitlines()]
        raw_events=[];terminal=False
        for line in (base/'response.stream.raw').read_text().splitlines():
            if not line.startswith('data:'):continue
            data=line[5:].strip()
            if data=='[DONE]':terminal=True
            elif data:raw_events.append(json.loads(data))
        check(folder.name+'/raw_events',raw_events==events and terminal)
        content=''.join(c.get('delta',{}).get('content') or '' for e in events for c in e.get('choices',[]) if c.get('index',0)==0)
        check(folder.name+'/assembled_stream',content==g.read(base/'response.assembled.json')['message']['content'])
        value=json.loads(content)
        check(folder.name+'/actual_model_edit',value==g.read(base/'model_edit.json'))
        check(folder.name+'/actual_usage',any(e.get('usage',{}).get('prompt_tokens')==call['prompt_tokens'] and e.get('usage',{}).get('completion_tokens')==call['completion_tokens'] for e in events if e.get('usage')))
        check(folder.name+'/no_retry',call['retries']==0 and call['stream_terminal_received'])
        check(folder.name+'/actual_model',call['actual_server_model']==protocol['model'])
        candidate,interface=g.frontend(value,current)
        check(folder.name+'/interface_gate',interface==g.read(base/'interface_gate.json'))
        item=dict(version=folder.name,raw_model_edit=value,interface=interface)
        if candidate is None:
            decision=dict(accepted=False,reasons=[dict(kind='interface_or_transport_rejected',details=interface)])
            feedback=dict(previous_feedback=feedback,actual_model_proposal=value,actual_interface_diagnosis=interface,call=call)
            check(folder.name+'/no_native_on_interface_failure',not (folder/'alignment').exists())
        elif g.old.acceptance.sha(candidate) in seen:
            decision=dict(accepted=False,reasons=[dict(kind='repeated_rejected_candidate')])
            feedback=dict(previous_feedback=feedback,actual_model_proposal=value,decision=decision)
            check(folder.name+'/no_duplicate_native',not (folder/'alignment').exists())
        else:
            seen.add(g.old.acceptance.sha(candidate))
            check(folder.name+'/exact_model_predicates',candidate==g.read(base/'candidate.json'))
            check(folder.name+'/unchanged_branch',candidate['assertions'][0]==g.read(prep/'protected_branch.json'))
            signatures=sorted(set(g.common.signature(a) for a in candidate['assertions']))
            item['same_normalized_predicate_set_as_prior_version']=signatures in predicate_sets
            predicate_sets.append(signatures)
            aligned,guard=native_check(folder/'alignment',candidate,'alignment')
            gate=g.read(folder/'alignment/alignment_gate.json')
            expected=g.prior.previous.source_check(prep)['expected'];expected={w['id']:w for w in expected['windows']}
            bindings=[]
            for w in g.read(prep/'windows.public.json'):
                refs=[r for r in aligned['reference'] if r['transaction_id']==w['transaction_id'] and r['phase']==w['phase'] and r['configuration']==w['configuration']]
                ref=refs[0] if len(refs)==1 else None
                match=ref is not None and ref['instruction']==int(w['instruction_hex'],16) and ref['instr_new']==w['instr_new'] and all(ref['actual'][v]==w[v+'_illegal'] for v in ('before','after'))
                rows=[r for r in aligned['ledger'] if ref and r['sample']['sample_id']==ref['sample_id'] and r['configuration']==w['configuration']]
                triggered=len(rows)==2 and all(any(a['trigger'] for a in r['native']['assertions'] if a['id']!='a0') for r in rows)
                required=expected[w['id']]['op_applicable']
                bindings.append(dict(window=w['id'],source_sample_id=w['sample_id'],replay_sample_id=ref['sample_id'] if ref else None,
                    original_sampling_matches=bool(match),op_required=required,op_triggered_on_both_revisions=triggered,accepted=bool(match and (not required or triggered))))
            check(folder.name+'/bound_window_results',bindings==gate['bindings'])
            check(folder.name+'/alignment_decision',gate['accepted']==(g.old.admissible(aligned) and guard['accepted'] and all(b['accepted'] for b in bindings)) and gate['all_property_guard']==guard)
            item['alignment']=gate
            if not gate['accepted']:
                decision=dict(accepted=False,reasons=[dict(kind='native_applicability_or_target_failure')])
                feedback=dict(actual_model_proposal=value,native_alignment_gate=gate,native_evidence=g.old.evidence(aligned),previous_full_development_feedback=g.read(prep/'initial_feedback.json')['native_development_feedback'])
                check(folder.name+'/full151_not_run_after_failed_gate',not (folder/'history').exists() and not (folder/'search').exists())
            else:
                h,hg=native_check(folder/'history',candidate,'history');s,sg=native_check(folder/'search',candidate,'search')
                decision=g.old.decide(baseline,g.common.combine(h,s));guards=dict(history=hg,search=sg)
                for cohort,gr in guards.items():
                    if not gr['accepted']:
                        decision['accepted']=False;decision['reasons'].append(dict(kind='all_property_false_alarm_or_unknown',cohort=cohort,details=gr))
                check(folder.name+'/global_false_alarm_gate',guards==g.read(folder/'all_property_guard.json'))
                check(folder.name+'/mapping',g.read(folder/'mapping.json')==dict(history=h['mapping'],search=s['mapping']))
                feedback=dict(actual_model_proposal=value,history=g.old.evidence(h),search=g.old.evidence(s),decision=g.common.gate_feedback(decision))
                item.update(history=h['counts'],search=s['counts'])
                if decision['accepted']:accepted=candidate
        check(folder.name+'/decision',decision==g.read(folder/'decision.json'))
        item['decision']=decision;versions.append(item);decisions.append(dict(version=int(folder.name[1:]),accepted=decision['accepted']))
    outcome=g.read(root/'outcome.json')
    check('decisions',outcome['decisions']==decisions)
    check('budget',outcome['calls']==len(calls)<=2)
    check('accepted_hash',outcome['accepted_candidate_sha256']==(g.old.acceptance.sha(accepted) if accepted else None))
    check('status',outcome['status']==('accepted_development_only' if accepted else 'no_accepted_sva'))
    if accepted:check('accepted_file',g.read(root/'accepted_candidate.json')==accepted)
    else:check('no_accepted_file',not (root/'accepted_candidate.json').exists())
    check('independent_not_run',outcome['independent_test']=='not_run' and not (root/'independent').exists())
    cost=g.old.cost_audit(root,[p for p in root.rglob('*') if p.is_file()])
    check('physical_cost',cost==g.read(root/'cost.json'))
    check('native_cost_count',len(native)==cost['total']['native_compile_calls'])
    g.dump(out/'audit.json',dict(passed=True,checks=checks,model_calls=0,new_native_calls=0))
    g.dump(out/'versions.json',versions)
    usage_missing=sum(c['prompt_tokens'] is None or c['completion_tokens'] is None for c in calls)
    g.dump(out/'cost_roles.json',dict(model_calls=len(calls),
        prompt_tokens=None if usage_missing else sum(c['prompt_tokens'] for c in calls),
        completion_tokens=None if usage_missing else sum(c['completion_tokens'] for c in calls),
        prompt_tokens_known_subtotal=sum(c['prompt_tokens'] or 0 for c in calls),
        completion_tokens_known_subtotal=sum(c['completion_tokens'] or 0 for c in calls),usage_unavailable_calls=usage_missing,
        model_wall_seconds=sum(c['wall_seconds'] for c in calls),native_compile_calls=len(native),
        native_full_execute_calls=cost['total']['native_execute_calls'],dedicated_smoke_calls=0,
        native_compile_wall_seconds=cost['total']['native_compile_wall_seconds'],native_execute_wall_seconds=cost['total']['native_execute_wall_seconds'],
        formal_calls=0,remaining_calls=2-len(calls),monetary_cost=None))
    g.dump(out/'status.json',outcome)
    print('RESULT_AUDIT',len(checks),outcome['status'],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prepared',type=Path,required=True);p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();run(a.prepared.resolve(),a.run.resolve(),a.out.resolve())
