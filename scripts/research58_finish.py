"""Read-only final audit of research58's bounded two-call continuation."""
import argparse
import json
from pathlib import Path
import research58_continue as c
g=c.g


def run(prep,sealed,root,out):
    out.mkdir(parents=True,exist_ok=False);checks=[]
    def check(name,ok):checks.append(dict(name=name,passed=bool(ok)));assert ok,name
    first_audit=g.read(g.ROOT/'deliverables/research58_first_audit_20261023_r01/audit.json')
    check('first_call_audited',first_audit['passed'] and all(x['passed'] for x in first_audit['checks']))
    for n,h in g.read(sealed/'sealed.json').items():check('sealed/'+n,g.old.digest(sealed/n)==h)
    for n,h in g.read(sealed/'sources.json').items():check('source/'+n,g.old.digest(g.ROOT/n)==h)
    check('original_scope_preserved',g.read(root/'original_authorization.json')==g.read(c.FIRST/'authorization.json'))
    folder=root/'v1';callpath=folder/'model_call';call=g.read(callpath/'result.json')
    check('actual_request',g.read(callpath/'request.json')==g.read(sealed/'request.preview.json'))
    check('zero_retries',call['retries']==0)
    check('same_model',call['actual_server_model']==g.read(prep/'protocol.json')['model'])
    events=[json.loads(s) for s in (callpath/'response.events.jsonl').read_text().splitlines()]
    raw=[];terminal=False
    for s in (callpath/'response.stream.raw').read_text().splitlines():
        if s.startswith('data:'):
            x=s[5:].strip()
            if x=='[DONE]':terminal=True
            elif x:raw.append(json.loads(x))
    check('raw_stream',events==raw and terminal and call['stream_terminal_received'])
    content=''.join(x.get('delta',{}).get('content') or '' for e in events for x in e.get('choices',[]) if x.get('index',0)==0)
    check('assembled_response',g.read(callpath/'response.assembled.json')['message']['content']==content)
    value=json.loads(content);check('real_model_value',value==g.read(callpath/'model_edit.json'))
    check('actual_usage',any(e.get('usage',{}).get('prompt_tokens')==call['prompt_tokens'] and e.get('usage',{}).get('completion_tokens')==call['completion_tokens'] for e in events if e.get('usage')))
    candidate,labels=g.diagnostic.adapt(value,g.read(prep/'shared_initial.json'))
    check('exact_predicates',candidate==g.read(callpath/'candidate.json'))
    check('label_mapping',g.read(callpath/'label_mapping.json')==dict(labels=labels,predicates_rewritten=False))
    known=g.read(prep/'known_rejected_sets.json')
    known.append(dict(source=str(c.FIRST/'v0/model_call/candidate.json'),signature=g.prior.previous.op_signature(g.read(c.FIRST/'v0/model_call/candidate.json'))))
    novelty=g.prior.previous.novelty(candidate,known)
    check('novelty',json.loads(json.dumps(novelty))==g.read(callpath/'novelty_gate.json'))
    rows=0;counts={}
    if not novelty['accepted']:
        check('no_repeat_native',not (folder/'alignment').exists())
        decision=dict(accepted=False,reasons=[dict(kind='interface_or_transport_rejected',details=g.read(callpath/'interface_gate.json'))])
    else:
        for cohort in ('alignment','history','search'):
            if (folder/cohort).exists():
                rows+=g.diagnostic.audit_native(folder/cohort,candidate,prep,cohort)
                counts[cohort]=g.read(folder/cohort/'result.json')['counts']
        aligned=g.read(folder/'alignment/result.json');gate=g.read(folder/'alignment/alignment_gate.json')
        guard=g.prior.native_flow.prior.all_property_guard(aligned,{rev:g.read(folder/'alignment'/rev/'result.json') for rev in ('before','after')},candidate)
        check('native_alignment_guard',gate['all_property_guard']==guard)
        check('native_gate',gate['accepted']==(g.old.admissible(aligned) and guard['accepted'] and all(b['accepted'] for b in gate['bindings'])))
        if not gate['accepted']:
            check('no_full_after_failure',not (folder/'history').exists())
            decision=dict(accepted=False,reasons=[dict(kind='native_applicability_or_target_failure')])
        else:
            h=g.read(folder/'history/result.json');s=g.read(folder/'search/result.json')
            combined=g.prior.common.combine(h,s)
            decision=g.preserve(g.read(prep/'baseline_full.json'),combined,g.read(prep/'target_preservation.private.json'),g.old.decide)
            guards={cohort:g.prior.native_flow.prior.all_property_guard(r,{rev:g.read(folder/cohort/rev/'result.json') for rev in ('before','after')},candidate) for cohort,r in [('history',h),('search',s)]}
            for cohort,guard in guards.items():
                if not guard['accepted']:
                    decision['accepted']=False;decision['reasons'].append(dict(kind='all_property_false_alarm_or_unknown',cohort=cohort,details=guard))
            check('full_property_guards',guards==g.read(folder/'all_property_guard.json'))
            check('mapping',g.read(folder/'mapping.json')==dict(history=h['mapping'],search=s['mapping']))
    check('actual_decision',decision==g.read(folder/'decision.json'))
    outcome=g.read(root/'outcome.json')
    check('total_budget',outcome['calls']==1 and outcome['total_calls']==2 and g.read(c.FIRST/'outcome.json')['calls']==1)
    check('accepted_status',outcome['status']==('accepted_development_only' if decision['accepted'] else 'no_accepted_sva'))
    check('accepted_hash',outcome['accepted_candidate_sha256']==(g.old.acceptance.sha(candidate) if decision['accepted'] else None))
    check('no_holdout',outcome['independent_test']=='not_run' and not (root/'independent').exists())
    if decision['accepted']:check('accepted_file',g.read(root/'accepted_candidate.json')==candidate)
    else:check('no_accept_file',not (root/'accepted_candidate.json').exists())
    cost=g.old.cost_audit(root,[p for p in root.rglob('*') if p.is_file()])
    check('physical_cost',cost==g.read(root/'cost.json'))
    costs={phase:g.read(path/'cost.json')['total'] for phase,path in [('preparation',prep),('first',c.FIRST),('second',root)]}
    totals={k:sum(r.get(k,0) for r in costs.values()) for k in ('model_calls','prompt_tokens_known_subtotal','completion_tokens_known_subtotal','usage_unavailable_calls','native_compile_calls','native_execute_calls','formal_calls')}
    g.dump(out/'cost_roles.json',dict(phases=costs,total=totals,monetary_cost=None,remaining_authorized_calls=0,
        execution_note='compile_smoke_execute_calls in inherited cost records is an overlapping classification of complete executions; do not add it again.'))
    g.dump(out/'audit.json',dict(passed=True,checks=checks,first_call_checks=len(first_audit['checks']),second_native_rows_audited=rows,new_model_calls=0,new_native_calls=0))
    g.dump(out/'status.json',dict(outcome=outcome,second_counts=counts,first_gate=g.read(c.FIRST/'v0/alignment/alignment_gate.json'),second_gate=g.read(folder/'alignment/alignment_gate.json') if (folder/'alignment').exists() else None))
    print('FINAL_AUDIT',len(checks),'passed',outcome['status'],counts,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prepared',type=Path,required=True);p.add_argument('--sealed',type=Path,required=True);p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();run(a.prepared.resolve(),a.sealed.resolve(),a.run.resolve(),a.out.resolve())
