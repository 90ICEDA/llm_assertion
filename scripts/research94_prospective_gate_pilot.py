"""Prospective three-rule pilot: shared new proposal, independent continuations.

O: ordinary; H: same-history absolute; R: obligation preservation.
No proposal selection after seeing outcomes. Max4 physical remote calls: one
shared first proposal and at most one independent continuation per rejected arm.
"""
import argparse
import copy
import json
import shutil
import time
from pathlib import Path
import research92_remote_recovery as prior

x=prior.x
ROOT,read,dump,sha=prior.ROOT,prior.read,prior.dump,prior.sha
ARMS=('O','H','R');SEED=9407
SOURCE=ROOT/'deliverables/research92_prepare_20261025_r01'


def decisions(ev):
    return dict(O=bool(ev['ordinary']['accepted']),H=bool(ev['full_absolute']),R=bool(ev['history']['accepted']))


def feedback(ev,records,history):
    cohorts=('alignment','search','history') if history else ('alignment','search')
    counts={c:records[c]['counts'] for c in cohorts};examples=[]
    for cohort in cohorts:
        info=x.old.acceptance.inspect(records[cohort]['ledger']);seen=set()
        for kind in ('false_positives','misses','unknown'):
            for key in sorted(info[kind]):
                row=info['rows'][key];s=row['sample'];w=s['instruction']
                group=(kind,w&127,(w>>28)&1,s['instr_new'],row['obligation'])
                if group in seen:continue
                seen.add(group)
                examples.append(dict(cohort=cohort,kind=kind,evidence_id=key,sample=s,
                    configuration=row['configuration'],revision=row['revision'],obligation=row['obligation'],
                    expected=row['expected'],observed=row['observed'],native=row['native']))
                if len(seen)>=6:break
            if len(seen)>=6:break
    return dict(visible_counts=counts,development_counterexamples=examples,
        required_untriggered={c:len(records[c]['required_untriggered']) for c in cohorts})


def payload(current,visible,round_index):
    req=prior.p.request(current,visible,round_index)
    body=json.loads(req['messages'][1]['content'])
    body['task']='Generate an OP assertion edit that repairs the visible missed checks and preserves legal behavior. Select all predicates and timing yourself. Keep the already generated BRANCH component unchanged. Use the original RTL, shared confirmed rule and only the supplied development observations.'
    body['acceptance']='All arms use identical interface, independent RTL/reference semantics and public current9/search36 checks. The evaluator also measures hidden historical protection. Do not ignore required first or held samples, or introduce false alarms. No independent-test result is provided.'
    req['messages'][1]['content']=json.dumps(body,separators=(',',':'))
    return dict(model=prior.transport.DEFAULT_MODEL,messages=req['messages'],stream=True,
        stream_options={'include_usage':True},response_format={'type':'json_object'},
        temperature=0.2,seed=SEED+round_index,max_tokens=1024)


def public_eligibility(ev,records):
    return dict(runtime_healthy=all(records[c]['healthy'] for c in records),
        actual_public_op_misses=sum(records[c]['counts']['misses'] for c in ('alignment','search')),
        initial_is_partial=True,baseline_branch_detections=sum(r['counts']['detections'] for c,r in records.items() if c in ('history','search')),
        status='Task eligible for repair; initial whole assertion set is not accepted.')


def protected_snapshot():
    root=ROOT/'deliverables/research92_real_20261025_r01'
    paths=[root/'freeze.json',root/'generation.json',root/'independent_cases.json',root/'independent_summary.json']
    paths += [root/'frozen'/a/n for a in ('A','B') for n in ('candidate.json','summary.json')]
    # Hashes only; independent outcomes and accepted predicates never parsed.
    return {f.relative_to(ROOT).as_posix():sha(f) for f in paths}


def prepare(out):
    x.verify(SOURCE);out.mkdir(parents=True,exist_ok=False)
    for n in ('initial.json','source_binding.json','history_cases.json','search_cases.json'):
        shutil.copy2(SOURCE/n,out/n)
    for rev in ('before','after'):shutil.copytree(SOURCE/rev,out/rev)
    baseline=read(SOURCE/'baseline_full.json');dump(out/'baseline_full.json',baseline)
    initial=read(out/'initial.json')
    ev,records=x.evaluate(initial,out/'baseline_native',baseline)
    assert x.paired.aggregate(records['history'],records['search'])==baseline
    eligibility=public_eligibility(ev,records)
    assert eligibility['runtime_healthy'] and eligibility['actual_public_op_misses']>0
    assert eligibility['baseline_branch_detections']==270
    dump(out/'task_eligibility.json',eligibility)
    dump(out/'initial_public_feedback.json',feedback(ev,records,False))
    req=payload(initial,read(out/'initial_public_feedback.json'),0)
    dump(out/'request.preview.json',req)
    # Same initial request for all policies, and identical visible input for H/R.
    for arm in ARMS:dump(out/'arms'/arm/'request.preview.json',req)
    checks=[]
    # Positive control is a declared local fixture, NEVER generation or a prompt.
    controls=dict(positive=read(x.P/'qualification/local_positive/candidate.json'),
        known_overbroad=read(SOURCE/'proposal.json'))
    for name,candidate in controls.items():
        dump(out/'controls'/name/'candidate.json',candidate)
        ce,cr=x.evaluate(candidate,out/'controls'/name/'native',baseline)
        expected=dict(O=True,H=True,R=True) if name=='positive' else dict(O=True,H=False,R=False)
        assert decisions(ce)==expected,(name,decisions(ce))
        checks.append(dict(name=name,decisions=decisions(ce),counts=ce['counts'],
            new_false_alarms=len(ce['new_false_alarm_ids']),not_model_output=True))
    assert decisions(ev)==dict(O=False,H=False,R=False)
    assert feedback(ev,records,True)==feedback(ev,records,True)
    assert 'history' not in read(out/'initial_public_feedback.json')['visible_counts']
    exclusions=set(read(SOURCE/'excluded_words.json'))
    # Input words only for collision exclusion; no outcome/accepted property read.
    exclusions.update(t['instruction'] for t in read(ROOT/'deliverables/research92_real_20261025_r01/independent_cases.json'))
    dump(out/'excluded_words.json',sorted(exclusions));dump(out/'protected93.json',protected_snapshot())
    protocol=dict(name='research94_prospective_three_rule_pilot',parent='original Ibex #166 decoder',
        retrospective_task_selection='Known OP repair task and initial partial BRANCH baseline. Future model outputs are not selected or filtered after observation. Not a new historical bug sample.',
        first_proposal='ONE fresh shared real response. No reuse of research61/92 success or failure responses as the first proposal. Initial request byte-identical O/H/R.',
        arms=dict(O='R0: current9 sampling/trigger/all-property + search36 acceptance; history is measurement only.',
            H='R0 plus absolute full151: native healthy, zero false alarms/misses/critical unknown and complete required triggers.',
            R='R0 plus existing obligation-preservation gate and all-property history guard; same151 evidence and same strict full scope.'),
        contrasts='Paired first-proposal decision effect separately from independently sampled second-round policy outcomes. H/R receive exactly the same historical facts and message construction; decision rules alone differ.',
        comparator_overlap='R already includes full absolute acceptance. On complete identity-preserving fixed evidence H/R may be equivalent. Agreement is not relative-comparator gain. No weakening H to force discrimination.',
        feedback='O only current9/search36 raw diagnostics. H/R same current9/search36/history115 diagnostics. No arm names, hidden gate results, other responses or independent outcomes in prompts.',
        maximum_calls=4,maximum_per_trajectory=2,first_shared_physical_calls=1,
        maximum_independent_continuations_per_arm=1,model=prior.transport.DEFAULT_MODEL,
        endpoint=prior.transport.DEFAULT_URL,seeds=[SEED,SEED+1],temperature=0.2,
        token_cap=120000,output_token_cap=1024,timeout_seconds=300,retries=0,
        maximum_native_compile_run=30,maximum_native_execute_run=30,
        preparation_native_compiles=18,
        stopping='Accepting arms stop; each rejected arm gets at most one independent continuation. Any transport failure stops entire pilot. No duplicate-call retry, replenishment, field-specific plan loop or automatic next seed.',
        qualification='Baseline executes, has real public OP gap and270 BRANCH protections. Native positive/negative decision controls pass. This is preflight, not successful model generation.',
        terminal='All arms stop and freeze before one fresh96-word four-config test batch. Only run holdout if at least one arm accepts; failed/fallback arms remain in denominator. Same words do not become independent samples by being replayed for3 arms.',
        expansion_gate='All arms complete without infrastructure error; shared fresh proposal ordinary-accepts but a historical rule extra-rejects; that SAME rejected historical arm subsequently accepts within2 logical calls and passes new independent tests. Otherwise stop, keep negative/non-discriminating result. Passing does NOT authorize expansion.',
        scope='One prospective pilot on known task; no stable generation or recovery rate, no formal proof. Old research93 tests protected and not used to tune rules.',
        created=time.time())
    dump(out/'protocol.json',protocol)
    config=dict(remote_url=prior.transport.DEFAULT_URL,remote_model=prior.transport.DEFAULT_MODEL,
        max_model_calls=4,max_tokens=120000,max_wall_seconds=2400,call_timeout=300,
        options=dict(seed=SEED,temperature=0.2,num_predict=1024))
    dump(out/'model_config.json',config)
    dump(out/'checks.json',dict(passed=True,native_controls=checks,baseline=decisions(ev),
        all_first_requests_identical=len({sha(out/'arms'/a/'request.preview.json') for a in ARMS})==1,
        response_selection_after_results=False,model_calls=0,protected93_unchanged=protected_snapshot()==read(out/'protected93.json')))
    dump(out/'preparation_cost.json',x.costs.native_cost(out))
    dump(out/'code_versions.json',{f.relative_to(ROOT).as_posix():sha(f) for f in (ROOT/'scripts').glob('*.py')})
    paths=list(out.glob('*.json'))+list(out.glob('before/*.sv'))+list(out.glob('after/*.sv'))+list(out.glob('arms/*/*.json'))
    dump(out/'sealed.json',{f.relative_to(out).as_posix():sha(f) for f in paths})
    print('PREPARED94',eligibility,'controls',len(checks),'remote calls0',flush=True)


def grant_check(auth,prep,out):
    assert auth['purpose']=='research94_prospective_gate_pilot'
    assert type(auth['authorized_calls']) is int and auth['authorized_calls']==4
    assert auth['endpoint']==prior.transport.DEFAULT_URL and auth['model']==prior.transport.DEFAULT_MODEL
    assert auth['prepared_sha256']==sha(prep/'sealed.json') and auth['run_output']==out.relative_to(ROOT).as_posix()


class Model(prior.Model):
    def _payload(self,current,target,feedback,phase):return copy.deepcopy(self.pending_request)


def run(prep,out,grant):
    x.verify(prep);auth=read(grant);grant_check(auth,prep,out)
    assert protected_snapshot()==read(prep/'protected93.json')
    out.mkdir(parents=True,exist_ok=False);dump(out/'authorization.json',auth)
    dump(out/'protocol.json',read(prep/'protocol.json'))
    initial=read(prep/'initial.json');base=read(prep/'baseline_full.json')
    model=Model(out/'service',read(prep/'model_config.json'));model.fixed=initial
    active={a:initial for a in ARMS};states={a:dict(accepted=False,logical_calls=0) for a in ARMS}
    budget=[];first=None;first_records=None;first_candidate=None;stopped=False;tests=None

    def call(folder,current,visible,round_index,seen):
        req=payload(current,visible,round_index)
        if round_index==0:assert req==read(prep/'request.preview.json')
        assert len(budget)<4
        budget.append(dict(path=folder.relative_to(out).as_posix(),reserved_at=time.time(),request_sha256=x.old.acceptance.sha(req)))
        dump(out/'budget_ledger.json',budget);model.pending_request=req
        transport,candidate=model.call(folder/'model_call',current,'op_bit28_illegal',visible,'pilot')
        ev=records=None;reason=dict(kind='transport_or_interface',actual=transport)
        if candidate is not None:
            if x.signature(candidate) in seen:reason=dict(kind='repeated_executable_proposal');candidate=None
            else:
                ev,records=x.evaluate(candidate,folder/'native',base);reason=dict(kind='native_measured')
        dump(folder/'measurement.json',dict(decisions=decisions(ev) if ev else {a:False for a in ARMS},reason=reason))
        return transport,candidate,ev,records,reason

    try:
        transport,first_candidate,first,first_records,reason=call(out/'shared/v0',initial,read(prep/'initial_public_feedback.json'),0,{x.signature(initial)})
        first_reason=copy.deepcopy(reason)
        admitted=decisions(first) if first else {a:False for a in ARMS}
        for arm in ARMS:
            active[arm]=x.journal(out/'arms'/arm/'v0',initial,first_candidate,admitted[arm],dict(shared_proposal='shared/v0',rule=arm,accepted=admitted[arm],reason=reason))
            states[arm]=dict(accepted=admitted[arm],logical_calls=1,initial_extra_rejection=bool(first and admitted['O'] and not admitted[arm]))
        stopped=transport['status']!='response_received'
        for arm in ARMS:
            if stopped or states[arm]['accepted']:continue
            current=first_candidate or initial
            if first_records:visible=feedback(first,first_records,arm!='O')
            else:visible=dict(prior_public_feedback=read(prep/'initial_public_feedback.json'),actual_rejection=first_reason,
                actual_model_text=read(out/'shared/v0/model_call/response.assembled.json')['message']['content'])
            transport,candidate,ev,records,reason=call(out/'arms'/arm/'v1',current,visible,1,{x.signature(initial),x.signature(current)})
            accepted=decisions(ev)[arm] if ev else False
            active[arm]=x.journal(out/'arms'/arm/'v1/transition',active[arm],candidate,accepted,dict(rule=arm,accepted=accepted,reason=reason))
            states[arm].update(accepted=accepted,logical_calls=2)
            stopped=transport['status']!='response_received'
            dump(out/'states.json',states)
        dump(out/'states.json',states)
        dump(out/'terminal_versions.json',{a:x.old.acceptance.sha(c) for a,c in active.items()})
        for a,c in active.items():dump(out/'terminal'/a/'candidate.json',c)
        if not stopped and any(s['accepted'] for s in states.values()):
            prior.p.independent(prep,out,active);tests=read(out/'independent_summary.json')
        ready=bool(not stopped and tests and any(states[a]['initial_extra_rejection'] and states[a]['accepted'] and tests[a]['passed'] for a in ('H','R')))
        dump(out/'pilot_decision.json',dict(eligible_to_request_multiseed=ready,automatic_expansion=False,
            status='qualified_for_separately_authorized_replication' if ready else ('transport_stop' if stopped else 'completed_no_qualified_rejection_recovery_chain'),
            first_shared_decisions=admitted,states=states,independent={a:t['passed'] for a,t in tests.items()} if tests else None,
            scope='No new seed or extra call may be launched by this runner.'))
    finally:
        dump(out/'cost.json',x.costs.native_cost(out))
        dump(out/'outcome.json',dict(actual_model_calls=len(model.calls),accepted_arms=sum(s['accepted'] for s in states.values()),
            unique_accepted_versions=len({x.old.acceptance.sha(active[a]) for a in ARMS if states[a]['accepted']}),
            transport_stopped=stopped,independent_executed=tests is not None))
        x.verify(prep);assert protected_snapshot()==read(prep/'protected93.json')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run'])
    p.add_argument('--out',type=Path,required=True);p.add_argument('--prepared',type=Path);p.add_argument('--authorization',type=Path)
    a=p.parse_args()
    if a.action=='prepare':prepare(a.out.resolve())
    else:run(a.prepared.resolve(),a.out.resolve(),a.authorization.resolve())
