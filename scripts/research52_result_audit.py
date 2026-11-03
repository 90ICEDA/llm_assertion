"""Offline audit of real research52 calls and raw native evidence; no model calls."""
import argparse
import json
import re
from pathlib import Path
import research52_ibex_bit_gate as g


def run(prep,root,out):
    out.mkdir(parents=True,exist_ok=False);checks=[];calls=[];versions=[]
    def check(name,value):
        checks.append(dict(name=name,passed=bool(value)))
        assert value,name
    for n,h in g.read(prep/'sealed.json').items():check('seal/'+n,g.old.digest(prep/n)==h)
    for n,h in g.read(prep/'source_hashes.json').items():
        check('run_source/'+n,g.old.digest(root/'source_snapshot'/n)==h)
        check('current_source/'+n,g.old.digest(g.ROOT/'scripts'/n)==h)
    expected=g.source_check(prep)
    def response(folder,request):
        call=g.read(folder/'result.json');calls.append(call)
        check(str(folder.relative_to(root))+'/request',g.read(folder/'request.json')==request)
        assembled=g.read(folder/'response.assembled.json')
        events=[json.loads(s) for s in (folder/'response.events.jsonl').read_text().splitlines()]
        content=''.join(c.get('delta',{}).get('content') or '' for e in events for c in e.get('choices',[]) if c.get('index',0)==0)
        check(str(folder.relative_to(root))+'/raw_stream',content==assembled['message']['content'])
        check(str(folder.relative_to(root))+'/actual_usage',any(e.get('usage',{}).get('prompt_tokens')==call['prompt_tokens'] and e.get('usage',{}).get('completion_tokens')==call['completion_tokens'] for e in events if e.get('usage')))
        check(str(folder.relative_to(root))+'/no_retry',call['retries']==0 and call['stream_terminal_received'])
        value=json.loads(content);check(str(folder.relative_to(root))+'/raw_json',value==g.read(folder/'model_edit.json'))
        return call,value
    feedback=None;accepted_plan=None;plan_gate=None;decisions=[]
    for folder in sorted((root/'plan').glob('v*')):
        call,value=response(folder/'model_call',g.plan_payload(prep,feedback))
        verdict=g.validate(value,expected)
        check(folder.name+'/plan_verdict',verdict==g.read(folder/'decision.json'))
        check(folder.name+'/raw_model_plan',value==g.read(folder/'model_call/model_plan.json'))
        decisions.append(dict(stage='plan',version=int(folder.name[1:]),accepted=verdict['accepted']))
        versions.append(dict(stage='plan',version=folder.name,accepted=verdict['accepted'],reasons=verdict['reasons']))
        if verdict['accepted']:
            accepted_plan=value;plan_gate=verdict
        feedback=dict(actual_rejected_output=value,diagnosis=verdict,call=call)
    check('plan_budget',len(decisions)<=2)
    if accepted_plan is None:
        check('no_sva_without_plan',not (root/'sva').exists())
    else:
        check('accepted_plan_original',g.read(root/'accepted_plan.json')==accepted_plan)
        g.verified_plan(prep,accepted_plan,plan_gate)
    native=[]
    def native_check(folder,candidate,cohort):
        result=g.read(folder/'result.json');tx=g.read(prep/(cohort+'_cases.json'));rows=g.old.samples(tx,cohort)
        check(str(folder.relative_to(root))+'/inputs',g.read(folder/'samples.json')==rows and g.read(folder/'transactions.json')==tx)
        traces={};marks={}
        for rev in ('before','after'):
            base=folder/rev;nr=g.read(base/'result.json');native.append(nr)
            check(str(base.relative_to(root))+'/model_testbench',base.joinpath('tb.sv').read_text()==g.old.bench(candidate,rows,g.old.CONFIGS,folder/'stimulus.txt'))
            check(str(base.relative_to(root))+'/original_rtl',all(str(prep/rev/name) in nr['compile']['argv'] for name in ('ibex_decoder.sv','ibex_defines.sv')))
            check(str(base.relative_to(root))+'/native_complete',nr['compile_status']=='passed' and nr['execution_status']=='completed')
            traces[rev]=g.trace(base/'execute.log');check(str(base.relative_to(root))+'/complete_samples',set(traces[rev])==set(range(len(rows))))
            log=(base/'execute.log').read_text();marks[rev]={kind:set((m[0],int(m[1])) for m in re.findall(r'^'+kind+r' (\w+) cycle=(-?\d+)$',log,re.M)) for kind in ('TRIGGER','ASSERT_FAIL')}
            check(str(base.relative_to(root))+'/wave',base.joinpath('wave.vcd').stat().st_size>0)
        issues=[]
        for row in result['ledger']:
            s=row['sample'];sid=s['sample_id'];cfg=row['configuration'];ci=g.old.CONFIGS.index(cfg);rev=row['revision']
            check_sample=rows[sid]==s
            observed={v:(int(traces[v][sid]['observed'],2)>>ci)&1 for v in traces}
            exp=g.old.historical.oracle(s['instruction'],s['instr_new'],cfg)
            check_sample &= row['expected']==exp and row['observed']==observed[rev] and observed['after']==exp
            for v in traces:
                t=traces[v][sid]
                check_sample &= int(t['instr'],16)==s['instruction'] and int(t['new'])==s['instr_new'] and int(t['txn'])==s['transaction_id'] and int(t['phase'])==s['phase']
            for a in row['native']['assertions']:
                p=next(p for p in candidate['assertions'] if p['id']==a['id']);name=a['id']+f'_c{ci}'
                trigger=(name,sid-p['delay']) in marks[rev]['TRIGGER'];failed=(name,sid) in marks[rev]['ASSERT_FAIL']
                detected=rev=='before' and observed[rev]!=exp and observed['after']==exp and trigger and failed and (name,sid) not in marks['after']['ASSERT_FAIL']
                check_sample &= (trigger,failed,detected)==(a['trigger'],a['failed'],a['causal_detection'])
            if not check_sample:issues.append(row['evidence_id'])
        info=g.old.acceptance.inspect(result['ledger'])
        check(str(folder.relative_to(root))+'/raw_evidence',not issues and len(result['ledger'])==len(rows)*6)
        check(str(folder.relative_to(root))+'/counts_mapping',not info['errors'] and result['counts']=={k:len(info[k]) for k in result['counts']} and result['mapping']==info['mapping'])
        check(str(folder.relative_to(root))+'/required_triggers',set(result['required_untriggered'])=={k for k,r in info['rows'].items() if r['required'] and k not in info['triggers']})
        return result
    current=g.read(prep/'shared_initial.json');baseline=g.read(prep/'baseline_full.json');accepted=None
    feedback=dict(history=g.old.evidence(g.read(prep/'baseline/history/result.json')),search=g.old.evidence(g.read(prep/'baseline/search/result.json')),
        baseline_status='Unaccepted research51 candidate. OP lacks triggers; BRANCH protection must be retained.')
    for folder in sorted((root/'sva').glob('v*')):
        call,value=response(folder/'model_call',g.sva_payload(prep,accepted_plan,plan_gate,current,feedback))
        try:candidate=g.old.assemble(value,current)
        except (AssertionError,KeyError,TypeError):candidate=None
        duplicate=None
        if candidate is not None:
            check(folder.name+'/candidate_exact',candidate==g.read(folder/'model_call/candidate.json'))
            duplicate=g.duplicates(candidate,current,value['operation'])
            check(folder.name+'/duplicate_gate',duplicate==g.read(folder/'model_call/duplicate_gate.json'))
            if not duplicate['accepted']:candidate=None
        if candidate is None:
            decision=dict(accepted=False,reasons=[dict(kind='unusable_or_duplicate_proposal',details=duplicate)])
            check(folder.name+'/no_native_for_rejected_frontend',not (folder/'history').exists() and not (folder/'search').exists())
            feedback=dict(previous_actual_native_feedback=feedback,call=call,rejection=decision)
            versions.append(dict(stage='sva',version=folder.name,accepted=False,reasons=decision['reasons']))
        else:
            h=native_check(folder/'history',candidate,'history');s=native_check(folder/'search',candidate,'search')
            decision=g.old.decide(baseline,g.combine(h,s))
            feedback=dict(actual_proposed_assertions=candidate,history=g.old.evidence(h),search=g.old.evidence(s),decision=g.gate_feedback(decision))
            versions.append(dict(stage='sva',version=folder.name,accepted=decision['accepted'],history=h['counts'],search=s['counts'],
                history_mapping={ob:{k:len(v) for k,v in m.items()} for ob,m in h['mapping'].items()},
                search_mapping={ob:{k:len(v) for k,v in m.items()} for ob,m in s['mapping'].items()},reason_kinds=[r['kind'] for r in decision['reasons']]))
            if decision['accepted']:accepted=candidate
        check(folder.name+'/decision',decision==g.read(folder/'decision.json'))
        decisions.append(dict(stage='sva',version=int(folder.name[1:]),accepted=decision['accepted']))
    outcome=g.read(root/'outcome.json')
    check('decisions',decisions==outcome['decisions'])
    check('call_budget',len(calls)==outcome['calls']<=4 and sum(d['stage']=='sva' for d in decisions)<=2)
    check('accepted_lineage',outcome['accepted_candidate_sha256']==(g.old.acceptance.sha(accepted) if accepted else None))
    if accepted:check('accepted_file',g.read(root/'accepted_candidate.json')==accepted)
    check('independent_not_generated',outcome['independent_test']=='not_run' and not (root/'independent').exists())
    g.dump(out/'audit.json',dict(passed=True,checks=checks,model_calls=0,new_native_calls=0))
    g.dump(out/'versions.json',versions)
    g.dump(out/'cost_roles.json',dict(model_calls=len(calls),prompt_tokens=sum(c['prompt_tokens'] for c in calls),completion_tokens=sum(c['completion_tokens'] for c in calls),
        native_compile_calls=len(native),native_full_execute_calls=len(native),dedicated_smoke_calls=0,formal_calls=0,monetary_cost=None,
        remaining_total_calls=4-len(calls),scope='Remaining allocation retains original two-plan/two-SVA restrictions; no automatic transfer.'))
    print('RESULT_AUDIT',len(checks),outcome['status'],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prepared',type=Path,required=True);p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();run(a.prepared.resolve(),a.run.resolve(),a.out.resolve())
