"""Pre-registered four-arm local-model pilot on three non-onehot parents.

This process alone builds prompts. Only public contract/ports/candidates and
explicit development feedback cross the model boundary. Hidden inputs and the
private reference monitor never appear in requests. No hand-edited repairs.
"""
import argparse
import collections
import copy
import json
from pathlib import Path
import time
import urllib.request

import obligation_isolated_search as iso
from obligation_isolated_search import x

BLOCK=None
KEYS=('filter','fifo','stat')
ARMS=('A','B','C','D')


def private_schedule(d, seed, boundary=False):
    rows=x.policy.ordinary(d,seed)
    if boundary:
        # Distinct, frozen transaction combinations with a reset cancellation
        # boundary. All interfaces obey their published environment contract.
        for i in range(2,24):rows[i][d['rst']]=int(i!=13)
        k=d['key']
        if k=='filter':
            for i,r in enumerate(rows):r.update(thresh_i=2,enable_i=int(i not in (8,9,10)),filter_i=int((i//4)%2))
        elif k=='fifo':
            for i,r in enumerate(rows):r.update(push_i=int(i%7 not in (0,1)),pop_i=int(i%7>=5),data_i=(i//7)*61+3)
        else:
            for i,r in enumerate(rows):r.update(frame_done_i=int(i in (3,4,7,11,12,15,16,17)),frame_len_i=(i*37+seed)%256)
        rows=x.policy.repair_environment(d,rows)
    return rows


def init():
    BLOCK.mkdir(exist_ok=False)
    probe=x.read(x.OUT/'model_probe/result.json')
    assert probe['status']=='available'
    for k in KEYS:
        d=x.read(x.OUT/'frozen'/k/'definition.json')
        pool=x.read(x.OUT/'frozen'/k/'candidates.json')['candidates']
        cid='pool_filter_1' if k=='filter' else 'slot_01'
        c=next(c for c in pool if c['id']==cid)
        x.dump(BLOCK/'initial'/f'{k}.json',[c])
        common=[x.policy.guided(d,740031,0),x.policy.guided(d,740039,1)]
        x.dump(BLOCK/'common'/f'{k}.json',common)
        hidden=[private_schedule(d,9817301+i*883,i==2) for i in range(3)]
        # Exact input and reset-epoch transaction sequence identities exclude
        # data-identical reuse. This is not a proof of arbitrary equivalence.
        x.dump(BLOCK/'quarantine'/f'{k}.json',hidden)
    p=dict(model=probe['model'],model_digest=probe['digest'],parents=list(KEYS),arms=list(ARMS),
        selection='pre-registered non-onehot pilot: filter/fifo/stat; same natural initial candidate across all arms; spill/intr unresolved and excluded from refinement only',
        sampling=dict(seed=20261013,temperature=0,num_predict=384,num_ctx=8192,num_gpu=0,num_thread=8),
        rounds=2,active_queries_per_round=4,common_initial_queries=2,regression_queries_per_round=2,
        actual_query_budget_per_parent_arm=14,model_call_budget_per_parent_arm=2,timeout_seconds=180,
        A='fixed common development stimuli, historical FP/TP signature (fixed-safe gate); no active input search',
        B='ordinary initial draw plus generic six-field mutation; retain maximum independently classified FP+FN evidence count; no obligation scheduling',
        C='four obligation-guided target queries, actively return misses only; common initial/legal/regression checks still return FP and FN',
        D='two obligation-guided target queries plus two explicit legal-boundary queries; return both FP and FN',
        sole_variation='development query scheduling/objective and resulting acquired feedback; model, grammar, public contract, initial candidates, common tests, feedback schema, query/model budgets identical',
        feedback_schema='legacy FP/TP counts, execution status, public prefix witness records, unknown candidates; A acquired queries contain only legacy counts, C acquired queries expose FN witnesses, common checks identical',
        candidate_language='1..4 assertions; antecedent/consequent SV expressions, delay 0..2; p1/p2/p3 zero-initialized sampled history available to all arms, popcount declared unsigned signal; active-low reset, pre-NBA; no private state',
        acceptance='No whole-parent pass unless all necessary obligations, reachability, legal boundaries and transaction-attributed violation protection verified. Counterexample-free finite traces alone are insufficient.',
        heldout='three schedules per parent, including new transaction combinations and legal/reset boundary; frozen before refinement; do not modify candidates after heldout',
        cost='all attempted queries, compiler/simulator calls, cycles, CPU/wall, actual model tokens; unavailable model cost null; common physical preflight separately counted',
        retries=0,human_clarifications=0,human_cost='not available',history_patches_visible=False)
    x.dump(BLOCK/'protocol.json',p)
    files=[Path(__file__),BLOCK/'protocol.json',*BLOCK.glob('initial/*.json'),*BLOCK.glob('common/*.json'),*BLOCK.glob('quarantine/*.json')]
    x.dump(BLOCK/'freeze.json',{x.rel(f):x.sha(f) for f in files})
    x.snapshot(Path(__file__))
    print(json.dumps(dict(status='frozen',parents=KEYS,model=p['model'],calls=24,queries=168)))


def guard():
    assert all(x.sha(x.ROOT/p)==h for p,h in x.read(BLOCK/'freeze.json').items())


def combined(q):
    """Assertion SET rejects a prefix if any assertion rejects it.

    Do not count one conjunct's miss if another conjunct already rejects.
    Retain coincident alarms as unknown attribution, not successful protection.
    """
    events=[];legacy=[]
    for rr in q['runs']:
        if rr['status']!='ok':continue
        f=x.ROOT/rr['run'];d=x.read(f/'definition.json');tr=x.read(f/'trace.json')
        cs=x.read(f/'candidates.json')
        checks=[x.read(f/f'checker_{j}_cycles.json') for j in range(len(cs))]
        merged=[dict(cycle=z[0]['cycle'],trigger=int(any(t['trigger'] for t in z)),fail=int(any(t['fail'] for t in z))) for z in zip(*checks)]
        oracle=x.read(f/'independent_reference.json')
        es=x.evidence(d,tr,merged,oracle)
        for e in es:
            if e['kind'] in ('miss','false_positive'):
                events.append(dict(**e,run=rr['run'],variant=rr['variant']))
        legacy.append(dict(variant=rr['variant'],fail_hits=sum(t['fail'] for t in merged),trigger_hits=sum(t['trigger'] for t in merged)))
    return dict(events=events,legacy=legacy,execution=q['status'],unknown=q['unsupported_candidates'])


def public_feedback(q, mode='both'):
    c=combined(q)
    if mode=='legacy':c['events']=[]
    if mode=='miss':c['events']=[e for e in c['events'] if e['kind']=='miss']
    # An explicit bounded development API, identical schema for every arm.
    out=[]
    seen=set()
    for e in c['events']:
        identity=(e['kind'],tuple(z['obligation'] for z in e['obligations']))
        if identity in seen:continue
        seen.add(identity)
        f=x.ROOT/e['run'];tr=x.read(f/'trace.json');t=e['cycle']
        out.append(dict(kind=e['kind'],cycle=t,obligations=e['obligations'],
                        recent_samples=tr[max(0,t-4):t+1]))
        if len(out)==2:break
    fixed=next((z for z in c['legacy'] if z['variant']=='correct'),None)
    bug=next((z for z in c['legacy'] if z['variant']=='buggy'),None)
    signature=dict(fp=bool(fixed and fixed['fail_hits']),tp=bool(fixed and bug and not fixed['fail_hits'] and bug['fail_hits']))
    return dict(status=c['execution'],unknown_candidates=c['unknown'],legacy_signature=signature,witnesses=out,
                limits='Finite development prefixes. Coincident alarm is not independent detection. Fixed RTL is not itself an oracle.')


def call_model(k, arm, round_no, candidates, feedback):
    p=x.read(BLOCK/'protocol.json');folder=BLOCK/'models'/k/arm/str(round_no);folder.mkdir(parents=True,exist_ok=False)
    d=x.read(x.OUT/'frozen'/k/'definition.json')
    public=x.read(x.OUT/'frozen'/k/'public_contract.json')
    prompt=dict(task='Improve this assertion set from the public design obligations and development feedback. Preserve existing protection and avoid legal-behavior false alarms. Return only JSON {"assertions":[{"antecedent":"...","consequent":"...","delay":0}]} with 1 to 4 assertions.',
                contract=public,ports={n:w for n,w in {**d['inputs'],**d['outputs']}.items() if n in d['observation_base']},
                expression_rules=p['candidate_language'],current=[{n:c[n] for n in ('antecedent','consequent','delay')} for c in candidates],feedback=feedback)
    request=dict(model=p['model'],stream=False,format='json',messages=[dict(role='user',content=json.dumps(prompt))],options=p['sampling'])
    x.dump(folder/'request.json',request)
    # Pin actual service digest before each call. Never silently switch models.
    tags=json.load(urllib.request.urlopen('http://127.0.0.1:11434/api/tags',timeout=5))
    entry=next(z for z in tags['models'] if z['name']==p['model'])
    assert entry['digest']==p['model_digest'],'model changed: start another complete block'
    start=time.perf_counter();result=dict(model=p['model'],digest=entry['digest'],model_calls=1,prompt_tokens=None,completion_tokens=None,candidates=None)
    x.dump(folder/'attempt.json',dict(status='submitted',request_sha256=x.sha(folder/'request.json')))
    try:
        req=urllib.request.Request('http://127.0.0.1:11434/api/chat',data=json.dumps(request).encode(),headers={'Content-Type':'application/json'})
        body=urllib.request.urlopen(req,timeout=p['timeout_seconds']).read();(folder/'response.raw.json').write_bytes(body)
        r=json.loads(body);result.update(prompt_tokens=r.get('prompt_eval_count'),completion_tokens=r.get('eval_count'),service_total_ns=r.get('total_duration'))
        parsed=json.loads(r['message']['content']);items=parsed.get('assertions')
        assert isinstance(items,list) and 1<=len(items)<=4,'model must return 1..4 assertions'
        cs=[]
        for j,c in enumerate(items):
            x.checker.normalize(c,d,3)
            cs.append(dict(antecedent=c['antecedent'],consequent=c['consequent'],delay=c['delay'],
                id=f'{k}_{arm}_r{round_no}_a{j}',provenance='actual_local_model_refinement',authorized_history_depth=3))
        result.update(status='parsed',candidates=cs)
    except Exception as exc:result.update(status='failed_or_unsupported',error=repr(exc))
    result['wall_seconds']=time.perf_counter()-start;x.dump(folder/'result.json',result)
    return result


def query(k,arm,phase,i,rows,cs):
    ident=f'{k}/{arm}/{phase}/{i}'
    x.append(BLOCK/'query_attempts.jsonl',dict(id=ident,input_sha256=x.digest(rows)))
    q=iso.evaluate(x.read(x.OUT/'frozen'/k/'definition.json'),rows,cs,'refinement/'+ident)
    q.update(id=ident,case=k,arm=arm,phase=phase)
    x.append(BLOCK/'queries.jsonl',q)
    return q


def develop():
    guard();iso.configure()
    assert x.read(x.OUT/'analysis_r02/audit.json')['passed'],'stabilize search before model refinement'
    (BLOCK/'development').mkdir(exist_ok=False)
    for k in KEYS:
        d=x.read(x.OUT/'frozen'/k/'definition.json');common=x.read(BLOCK/'common'/f'{k}.json')
        for arm in ARMS:
            cs=x.read(BLOCK/'initial'/f'{k}.json')
            initial=[query(k,arm,'initial',i,rows,cs) for i,rows in enumerate(common)]
            common_feedback=[public_feedback(q) for q in initial]
            checkpoints=[]
            for round_no in range(2):
                acquired=[];incumbent=None;best=-1
                for i in range(4):
                    seed=771001+round_no*7919+i*1009
                    if arm=='A':rows=common[i%2]
                    elif arm=='B':rows=x.policy.disagreement(d,seed,incumbent)
                    elif arm=='C' or i<2:rows=x.policy.guided(d,seed,round_no*4+i)
                    else:
                        # Public legal-boundary objectives: qualification stability,
                        # FIFO release after backpressure, isolated stat transactions.
                        rows=x.policy.guided(d,seed,0)
                        if k=='filter':
                            for j,r in enumerate(rows):r['enable_i']=int(j%5!=0)
                        rows=x.policy.repair_environment(d,rows)
                    q=query(k,arm,f'round{round_no}_acquire',i,rows,cs);acquired.append(q)
                    score=len(combined(q)['events'])
                    if arm=='B' and score>best:best=score;incumbent=rows
                feedback=common_feedback+[public_feedback(q,'legacy' if arm=='A' else 'miss' if arm=='C' else 'both') for q in acquired]
                response=call_model(k,arm,round_no,cs,feedback)
                before=copy.deepcopy(cs)
                if response['candidates'] is not None:cs=response['candidates']
                regression=[query(k,arm,f'round{round_no}_regression',i,rows,cs) for i,rows in enumerate(common)]
                common_feedback=[public_feedback(q) for q in regression]
                checkpoint=dict(round=round_no,before=before,after=cs,before_sha256=x.digest(before),after_sha256=x.digest(cs),
                    model_status=response['status'],regression=[combined(q) for q in regression],
                    change_basis=x.rel(BLOCK/'models'/k/arm/str(round_no)/'request.json'))
                checkpoints.append(checkpoint)
                x.dump(BLOCK/'development'/k/arm/f'checkpoint_{round_no}.json',checkpoint)
                print('REFINE',k,arm,round_no,response['status'],flush=True)
            x.dump(BLOCK/'development'/k/arm/'final.json',dict(candidates=cs,sha256=x.digest(cs),initial_sha256=x.digest(x.read(BLOCK/'initial'/f'{k}.json'))))
    x.dump(BLOCK/'final_freeze.json',{x.rel(p):x.sha(p) for p in BLOCK.glob('development/*/*/final.json')})


def heldout():
    guard();iso.configure();freeze=x.read(BLOCK/'final_freeze.json')
    assert len(freeze)==12 and all(x.sha(x.ROOT/p)==h for p,h in freeze.items())
    (BLOCK/'heldout').mkdir(exist_ok=False)
    development=[json.loads(s) for s in (BLOCK/'queries.jsonl').read_text().splitlines()]
    dev_hashes={q['input_content_sha256'] for q in development}
    result=[]
    for k in KEYS:
        hidden=x.read(BLOCK/'quarantine'/f'{k}.json')
        assert all(x.digest(rows) not in dev_hashes for rows in hidden),'exact heldout leakage'
        for arm in ARMS:
            initial=x.read(BLOCK/'initial'/f'{k}.json');final=x.read(BLOCK/'development'/k/arm/'final.json')['candidates']
            for version,cs in [('initial',initial),('final',final)]:
                for i,rows in enumerate(hidden):
                    q=query(k,arm,'heldout_'+version,i,rows,cs)
                    result.append(dict(case=k,arm=arm,version=version,scenario=i,input_sha256=x.digest(rows),evaluation=combined(q),query=q['id']))
    x.dump(BLOCK/'heldout/results.json',result)
    summary=[]
    for k in KEYS:
        for arm in ARMS:
            metrics={}
            for version in ('initial','final'):
                rs=[r for r in result if (r['case'],r['arm'],r['version'])==(k,arm,version)]
                ev=[e for r in rs for e in r['evaluation']['events']]
                metrics[version]=dict(false_positive_events=sum(e['kind']=='false_positive' for e in ev),
                    missed_first_violation_events=sum(e['kind']=='miss' for e in ev),
                    missed_components=sorted({z['obligation'] for e in ev if e['kind']=='miss' for z in e['obligations'] if not z['passed']}),
                    unknown_scenarios=sum(r['evaluation']['execution'] not in ('ok',) for r in rs))
            summary.append(dict(case=k,arm=arm,metrics=metrics,parent_pass='not_established',
                reason='finite sampled schedules; positive causal alarm attribution and complete necessary-branch coverage not established'))
    x.dump(BLOCK/'heldout/summary.json',summary)
    print(json.dumps(summary))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);p.add_argument('action',choices=['init','develop','heldout'])
    a=p.parse_args();x.OUT=x.ROOT/'deliverables'/a.run;BLOCK=x.OUT/'refinement_r02';globals()[a.action]()
