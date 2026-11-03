"""True 2x2 search x acceptance-gate experiment, isolated from sealed results.

Auxiliary procedural checker only: never report these runs as native SVA.
Run under existing WSL python3. No old artifact is modified.
"""
import argparse
import copy
import json
from pathlib import Path
import random
import shutil
import time

import obligation_continuation as cont
from obligation_continuation import x, iso, interface, public
import obligation_continuation_experiment as prior_exp
import research_acceptance_gate as gate

NAME = 'research_gate_20261014_r01'
OLD = x.ROOT/'deliverables/obligation_continuation_20261013_r01'
ARMS = {'A': (False, False), 'B': (True, False), 'C': (False, True), 'D': (True, True)}


def configure():
    source_manifest=x.OUT/'execution_source_manifest.json'
    if source_manifest.exists():
        assert all(x.sha(x.ROOT/p)==h for p,h in x.read(source_manifest).items()),'live_execution_source_changed'
    cont.configure()
    return x.read(x.OUT/'frozen/stat/definition.json')


def prepare():
    x.OUT.mkdir(exist_ok=False)
    shutil.copytree(OLD/'frozen/stat', x.OUT/'frozen/stat')
    cfg = x.read(OLD/'common_config.json')
    cfg.update(rounds=2, sampling=dict(cfg['sampling'], seed=20261014, num_predict=512),
               acceptance='gate.decide for C/D; executable-only for A/B',
               active_queries_per_round=2,query_budget_per_parent_arm=20,
               regression_queries_per_round=[4,6],
               final_selection='last accepted set; C/D require evidence gate; A/B executable-only',
               query_budget='2 common + 2 new acquisitions per round; all arms replay same number of own-history queries',
               execution_backend='Icarus procedural checker, not native SVA')
    x.dump(x.OUT/'config.json', cfg)
    d = configure()
    x.dump(x.OUT/'initial.json', x.read(OLD/'formal/initial/stat.json'))
    common = [x.policy.guided(d, 141071, 0), x.policy.guided(d, 141079, 1)]
    x.dump(x.OUT/'common.json', common)
    x.dump(x.OUT/'protocol.json', dict(arms=ARMS, factor_one='new contract-guided acquisition vs fixed common replay',
        factor_two='evidence-scoped accepting/rejecting gate vs executable-only acceptance',
        initial='same saved natural candidate', public_information='same pre/post RTL, prose, obligations, ports',
        model_budget_per_arm=2, retries=0, selection='last accepted set; proposals rejected by enabled gate are retained in artifacts',
        current_target='first acquired false positive or missed violation; fixed deterministic order',
        evidence_key='electrical input SHA256 / variant / cycle / obligation; variants of same semantic gap separately deduplicated for reporting',
        scope='stat engineered two-sample scoped contract, not upstream historical timing proof',
        native_sva=False, independent_test='new randomized 37-cycle schedules, only executed after final freeze; historical tests are development',
        unknown_policy='unknown prevents gate acceptance and parent pass; no assertion-oracle circularity'))
    # Private test inputs are saved before any new model call and never fed back.
    hidden=[]
    for i in range(6):
        rng=random.Random(1419931+i*7919)
        rows=[]
        for t in range(37):
            rows.append(dict(rst_ni=int(t>=2 and t not in (11+i, 25+i%3)),
                             frame_done_i=int(t<33 and rng.random()<.65),frame_len_i=rng.randrange(256)))
        hidden.append(x.policy.repair_environment(d,rows))
    x.dump(x.OUT/'quarantine/inputs.json', hidden)
    text=(x.OUT/'frozen/stat/correct.v').read_text()
    old='stat_len_o<=captured_len;'
    assert old in text
    (x.OUT/'quarantine/data_fault.v').write_text(text.replace(old, 'stat_len_o<=captured_len ^ 8\'d1;'))
    x.dump(x.OUT/'quarantine/provenance.json', dict(origin='new artificial payload fault; no historical RTL claim'))
    for p in (Path(__file__), Path(gate.__file__), Path(interface.__file__)):
        shutil.copyfile(p, x.OUT/p.name)
    x.dump(x.OUT/'execution_source_manifest.json',{x.rel(p):x.sha(p) for p in
        (Path(__file__),Path(gate.__file__),Path(interface.__file__),Path(cont.__file__),Path(iso.__file__),Path(prior_exp.__file__))})
    files=[p for p in x.OUT.rglob('*') if p.is_file()]
    x.dump(x.OUT/'freeze.json',{x.rel(p):x.sha(p) for p in files})
    print('PREPARED',x.OUT.name,flush=True)


def run_query(d, rows, cs, label):
    q=iso.evaluate(d,rows,cs,label)
    q.update(case='stat',label=label)
    x.append(x.OUT/'queries.jsonl',q)
    return q


def evidence(d,q,cs):
    """Port-only oracle plus paired first-violation attribution; set-level replay."""
    r=dict(status=q['status'],false_positives=[],detections=[],effective_triggers=[],misses=[],resolved_keys=[],mapping=[])
    if q['status']!='ok':return r
    metrics=prior_exp.paired_metrics(d,q,cs)
    ident=q['input_content_sha256']
    for t in metrics['fp']:
        r['false_positives'].append(f'{ident}/correct/{t}/legal')
    for hit in metrics['causal_detections']:
        for o in hit['transaction_obligations']:
            r['detections'].append(f"{ident}/buggy/{hit['cycle']}/{o['obligation']}")
    for hit in metrics['first_misses']:
        for o in hit['transaction_obligations']:
            r['misses'].append(f"{ident}/buggy/{hit['cycle']}/{o['obligation']}")
    byvariant={v['variant']:x.ROOT/v['run'] for v in q['runs']}
    legal=byvariant['correct']
    oracle=x.read(legal/'independent_reference.json')
    checks=[{z['cycle']:z for z in x.read(legal/f'checker_{j}_cycles.json')} for j in range(len(cs))]
    for e in oracle['events']:
        t=e['cycle']
        if e['legal_prefix'] and not any(z.get(t,{}).get('fail') for z in checks):
            r['resolved_keys'].append(f'{ident}/correct/{t}/legal')
        for o in e['checks']:
            # Syntactic output relevance plus effective temporal antecedent;
            # evidence map is not a claim that the implication entails obligation.
            output='stat_valid_o' if o['obligation']=='valid_latency' else 'stat_len_o'
            active=[c['id'] for j,c in enumerate(cs) if output in c['consequent'] and
                    checks[j].get(t-c['delay'],{}).get('trigger') and e['legal_prefix'] and
                    not checks[j].get(t,{}).get('fail')]
            key=f"{ident}/correct/{t}/{o['obligation']}"
            if active:r['effective_triggers'].append(key)
            r['mapping'].append(dict(obligation=o['obligation'],transaction_id=o['transaction_id'],
                due_cycle=t,assertions=active,evidence_key=key,scope='effective evaluation only, not semantic entailment'))
    r['resolved_keys']+=r['detections']
    return r


def call_model(d,arm,round_no,cs,feedback,previous_decision):
    cfg=x.read(x.OUT/'config.json');folder=x.OUT/'models'/arm/str(round_no)
    names=list(d['observation_base'])
    prompt=dict(task='Repair or add complementary assertions. Return only JSON {"assertions":[{"antecedent":"...","consequent":"...","delay":0}]} (1..4 assertions).',
        bug_description='Early status pulse; ensure two-sample latency and captured payload, overlapping requests and reset cancellation.',
        rtl_before=(x.OUT/'frozen/stat/buggy.v').read_text(),rtl_after=(x.OUT/'frozen/stat/correct.v').read_text(),
        specification=x.read(x.OUT/'frozen/stat/public_contract.json'),
        confirmed_scoped_obligations=x.read(x.OUT/'frozen/stat/contract.json')['target_components'],
        allowed_identifiers=names+[d['rst']]+[f'p{n}_{v}' for n in (1,2,3) for v in names],
        semantics='pre-NBA sampling; delay 0/1/2 exact cycles; p1/p2/p3 zero-initialized history since reset, no $past, no properties or statements; implicit reset cancels pending checks. Public ports only.',
        current=[{k:c[k] for k in ('antecedent','consequent','delay')} for c in cs],
        acquired_feedback=feedback,previous_acceptance_feedback=previous_decision)
    req=dict(model=cfg['model'],stream=True,format='json',messages=[dict(role='user',content=json.dumps(prompt))],options=cfg['sampling'])
    result,content=interface.stream_call(req,folder,x.dump,cfg['model_digest'],cfg['timeout_seconds'])
    result['candidates']=None
    if result['status']=='response_received':
        try:result.update(candidates=interface.extract(content,d,f'{arm}_{round_no}'),status='parsed')
        except (AssertionError,ValueError,KeyError,TypeError) as exc:result.update(status='candidate_language_error',error=str(exc))
    x.dump(folder/'result.json',result)
    return result


def develop():
    d=configure()
    assert all(x.sha(x.ROOT/p)==h for p,h in x.read(x.OUT/'freeze.json').items())
    (x.OUT/'development').mkdir(exist_ok=False)
    cont.ensure_service()
    common=x.read(x.OUT/'common.json')
    for arm,(search,guard) in ARMS.items():
        cs=x.read(x.OUT/'initial.json');history=copy.deepcopy(common);previous=None
        for rnd in range(2):
            acquired=[x.policy.guided(d,142003+rnd*419+i*71,2+rnd*2+i) if search else copy.deepcopy(common[i]) for i in range(2)]
            # De-duplicate storage only; replay calls remain explicitly costed.
            history+=acquired
            before_queries=[run_query(d,rows,cs,f'gate/{arm}/{rnd}/before/{i}') for i,rows in enumerate(history)]
            before_records=[evidence(d,q,cs) for q in before_queries]
            acquired_records=before_records[-2:]
            targets=sorted({v for r in acquired_records for n in ('false_positives','misses') for v in r[n]})[:1]
            feedback=[public.feedback(q) for q in before_queries]
            response=call_model(d,arm,rnd,cs,feedback,previous)
            proposal=response.get('candidates')
            if proposal:
                after_queries=[run_query(d,rows,proposal,f'gate/{arm}/{rnd}/proposal/{i}') for i,rows in enumerate(history)]
                after_records=[evidence(d,q,proposal) for q in after_queries]
                assessment=gate.decide(gate.merge(before_records),gate.merge(after_records),targets)
                executable=all(q['status']=='ok' for q in after_queries)
                accepted=executable and (assessment['accepted'] if guard else True)
            else:
                after_records=[];accepted=False
                assessment=dict(accepted=False,reasons=[dict(kind='model_or_candidate_error',status=response['status'])])
            checkpoint=dict(arm=arm,round=rnd,search=search,gate_enabled=guard,accepted=accepted,
                before=cs,proposal=proposal,after=proposal if accepted else cs,target_keys=targets,
                gate_assessment=assessment,model_status=response['status'],replay_before=before_records,replay_after=after_records,
                scope='procedural-checker evidence replay; native SVA not established')
            x.dump(x.OUT/'development'/arm/f'checkpoint_{rnd}.json',checkpoint)
            if accepted:cs=proposal
            # Detailed evidence stays in checkpoints. Bound feedback size and
            # send actual interface diagnostics to every arm, independent of gate.
            reasons=[dict(kind=r['kind'],evidence_count=len(r.get('evidence_keys',[])),
                          representative_keys=r.get('evidence_keys',[])[:3]) for r in assessment['reasons']]
            previous=dict(accepted=accepted,reasons=reasons if guard else [],scope=checkpoint['scope'],
                          interface_status=response['status'],interface_error=response.get('error'))
            print('GATE',arm,rnd,response['status'],'accepted',accepted,flush=True)
        x.dump(x.OUT/'development'/arm/'final.json',dict(candidates=cs,sha256=gate.digest(cs)))
    x.dump(x.OUT/'final_freeze.json',{x.rel(p):x.sha(p) for p in x.OUT.glob('development/*/final.json')})


def acceptance():
    d=configure()
    assert all(x.sha(x.ROOT/p)==h for p,h in x.read(x.OUT/'final_freeze.json').items())
    out=x.OUT/'independent';out.mkdir(exist_ok=False)
    hidden=x.read(x.OUT/'quarantine/inputs.json')
    dev=[json.loads(z) for z in (x.OUT/'queries.jsonl').read_text().splitlines()]
    dev_ids={q['input_content_sha256'] for q in dev}
    assert not ({x.digest(rows) for rows in hidden}&dev_ids)
    result=[]
    for arm in ARMS:
        for version in ('initial','final'):
            cs=x.read(x.OUT/'initial.json') if version=='initial' else x.read(x.OUT/'development'/arm/'final.json')['candidates']
            for cohort in ('original_target','new_payload_fault'):
                x.engine.sources=lambda d: (x.OUT/'frozen/stat/correct.v',x.OUT/('frozen/stat/buggy.v' if cohort=='original_target' else 'quarantine/data_fault.v'))
                for i,rows in enumerate(hidden):
                    q=run_query(d,rows,cs,f'independent/{arm}/{version}/{cohort}/{i}')
                    result.append(dict(arm=arm,version=version,cohort=cohort,scenario=i,metrics=prior_exp.paired_metrics(d,q,cs),evidence=evidence(d,q,cs)))
    x.dump(out/'results.json',result)
    x.dump(out/'isolation.json',dict(exact_input_overlap=0,final_hashes_verified=True,used_in_prompts=False,
        limitations='fresh input schedules only; same scoped artificial stat design; no global or native-SVA claim'))
    summary=[]
    for arm in ARMS:
        for cohort in ('original_target','new_payload_fault'):
            row=dict(arm=arm,cohort=cohort,parent_pass=False)
            for v in ('initial','final'):
                ms=[r['metrics'] for r in result if (r['arm'],r['cohort'],r['version'])==(arm,cohort,v)]
                row[v]={k:sum(len(m[k]) for m in ms) for k in ('fp','first_misses','later_misses','causal_detections','attribution_unknown')}
                row[v]['unknown_scenarios']=sum(m['status']!='ok' for m in ms)
            summary.append(row)
    x.dump(out/'summary.json',summary)
    print('INDEPENDENT',len(result),'paired replays',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','develop','acceptance']);p.add_argument('--run',default=NAME)
    a=p.parse_args();x.OUT=x.ROOT/'deliverables'/a.run;globals()[a.action]()
