"""Frozen four-arm experiments and private acceptance, with bounded full costs."""
import argparse
import collections
import copy
import json
from pathlib import Path
import random
import shutil
import obligation_continuation as cont
from obligation_continuation import x, iso, ref, public, interface, PRIOR

KEYS=('filter','fifo','stat')
ARMS=('A','B','C','D')
BLOCK_NAME='formal'


def canonical(d,rows):
    return x.digest([[r[n] for n in sorted([d['rst'],*d['inputs']])] for r in rows])


def hidden_inputs(d, number):
    rng=random.Random(8101337+number*787+sum(map(ord,d['key'])))
    rows=[];k=d['key']
    for t in range(32):
        r={n:rng.randrange(1<<w) for n,w in d['inputs'].items()};r[d['rst']]=int(t>=2 and t not in (9+number%3,22))
        if k=='stat':r.update(frame_done_i=int(t in (2,3,4,7,8,10,11,16,17,18,21,24,27)),frame_len_i=187 if t%3==2 else (t*43+number*19)%256)
        elif k=='fifo':r.update(push_i=int(t%9 not in (0,1)),pop_i=int(t%9>=6),data_i=199+number)
        else:r.update(thresh_i=2,enable_i=int(t not in (5+number,18+number%3)),filter_i=int((t//(2+number%3)+number)%2))
        rows.append(r)
    return x.policy.repair_environment(d,rows)


def prepare():
    assert x.read(x.OUT/'interface_preflight/summary.json')['passed']
    assert x.read(x.OUT/'stat_control/summary.json')['all_legal_control_pass']
    block=x.OUT/'formal';block.mkdir(exist_ok=False)
    cfg=x.read(x.OUT/'common_config.json')
    protocol=dict(cfg,parents=KEYS,arms=ARMS,kind='formal_continuation',
        A='fixed common inputs, legacy feedback for acquired queries; common independently adjudicated checks identical',
        B='generic seeded mutation, select maximum acquired FP+FN evidence; no obligation templates',
        C='public obligation schedules; active miss witnesses only; common FP/FN and regression retained',
        D='two obligation target schedules plus two legal boundary schedules per round; FP/FN feedback',
        sole_variation='acquisition policy/objective and resulting acquired feedback; all other resources shared',
        initial_pool='unchanged natural initial candidate from r04; filter remains one executable candidate, no claim of candidate disagreement',
        changed_RTL='stat correct_v2 engineered payload pipeline; old mutant kept; old records not merged',
        initial_and_regression='two common 24-sample schedules, each on legal control and mutant',
        isolation='new 32-sample private scenarios and new artificial sibling mutants; no private code/answers in JSON model API',
        stopping='two rounds or recorded per-call failure; never extend one arm budget based on outcome',
        admission='parsed proposals must compile/execute in shared regression; if execution unsupported retain previous set; semantic regressions retained as outcomes',
        positive_detection='only accepted legal counterfactual, same visible prefix and single changed target output at first violation',
        later_violations='accepted violating prefix counts missed later transaction; prior rejected prefix makes later credit unknown, raw per-cycle alarms retained')
    x.dump(block/'protocol.json',protocol)
    replacements={
        'fifo':('assign empty_o=~push_i;','assign empty_o=~push_i | (push_i & ~pop_i & data_i[7]);'),
        'filter':("(filter_synced != filter_q) ? '0", "(filter_synced != filter_q) ? {{(CntWidth-2){1'b0}},2'b10}"),
        'stat':('stat_len_o<=captured_len;',"stat_len_o<=captured_len ^ ((captured_len == 8'd187) ? 8'd1 : 8'd0);")}
    for k in KEYS:
        d=x.read(x.OUT/'frozen'/k/'definition.json')
        x.dump(block/'initial'/f'{k}.json',x.read(PRIOR/'refinement_r04/initial'/f'{k}.json'))
        common=[x.policy.guided(d,740031,0),x.policy.guided(d,740039,1)]
        x.dump(block/'common'/f'{k}.json',common)
        rows=[hidden_inputs(d,i) for i in range(6)]
        assert not any(x.check_inputs(d,r) for r in rows)
        oldhidden=x.read(PRIOR/'refinement_r04/quarantine'/f'{k}.json')
        assert not ({canonical(d,r) for r in rows}&{canonical(d,r) for r in oldhidden+common})
        x.dump(block/'quarantine'/k/'inputs.json',rows)
        text=(x.OUT/'frozen'/k/'correct.v').read_text();a,b=replacements[k];assert text.count(a)==1
        (block/'quarantine'/k/'control.v').write_text(text)
        (block/'quarantine'/k/'sibling.v').write_text(text.replace(a,b))
        x.dump(block/'quarantine'/k/'provenance.json',dict(origin='new_artificial_sibling_not_historical',before=a,after=b,
            contract=x.rel(x.OUT/'frozen'/k/'spec_sources.json'),spec_preconditions=x.read(x.OUT/'frozen'/k/'contract.json')['legal_inputs'],
            independent_from='old r04 inputs retired; new transaction runs/lengths/reset locations and distinct mutation predicate',
            deadline_checked_before_alignment=True,generator_visible=False))
    sources=[Path(__file__),Path(cont.__file__),Path(interface.__file__),Path(public.__file__),Path(ref.__file__),Path(iso.__file__),Path(x.__file__),x.ROOT/'scripts/obligation_evidence_monitor.py',x.ROOT/'scripts/obligation_search_policy.py',x.ROOT/'scripts/contract_v3_checker.py',x.ROOT/'scripts/run_repair_contract.py']
    paths=sources+[x.OUT/'common_config.json',block/'protocol.json']+[p for p in (block).rglob('*') if p.is_file()]+[p for p in (x.OUT/'frozen').rglob('*') if p.is_file()]
    x.dump(block/'freeze.json',{x.rel(p):x.sha(p) for p in paths})
    for f in sources:shutil.copyfile(f,block/(f.name+'.snapshot'))
    print('FORMAL frozen: 24 calls, 168 development queries, 18 new hidden schedules, 3 new sibling mutants',flush=True)


def setup():
    cont.configure();ref.BLOCK=x.OUT/BLOCK_NAME;ref.public_feedback=public.feedback;ref.query=cont.query;ref.call_model=cont.call_model
    for p,h in x.read(ref.BLOCK/'freeze.json').items():assert x.sha(x.ROOT/p)==h,('freeze_changed',p)


def develop():
    setup();block=ref.BLOCK;(block/'development').mkdir(exist_ok=False)
    for k in KEYS:
        d=x.read(x.OUT/'frozen'/k/'definition.json');common=x.read(block/'common'/f'{k}.json')
        for arm in ARMS:
            cs=x.read(block/'initial'/f'{k}.json')
            initial=[cont.query(k,arm,'initial',i,rows,cs) for i,rows in enumerate(common)]
            common_feedback=[public.feedback(q) for q in initial]
            for round_no in range(2):
                acquired=[];incumbent=None;best=-1
                for i in range(4):
                    seed=771001+round_no*7919+i*1009
                    if arm=='A':rows=common[i%2]
                    elif arm=='B':rows=x.policy.disagreement(d,seed,incumbent)
                    elif arm=='C' or i<2:rows=x.policy.guided(d,seed,round_no*4+i)
                    else:
                        rows=x.policy.guided(d,seed,0)
                        if k=='filter':
                            for j,r in enumerate(rows):r['enable_i']=int(j%5!=0)
                        rows=x.policy.repair_environment(d,rows)
                    q=cont.query(k,arm,f'round{round_no}_acquire',i,rows,cs);acquired.append(q)
                    score=len(ref.combined(q)['events'])
                    if arm=='B' and score>best:best=score;incumbent=rows
                feedback=common_feedback+[public.feedback(q,'legacy' if arm=='A' else 'miss' if arm=='C' else 'both') for q in acquired]
                response=cont.call_model(k,arm,round_no,cs,feedback)
                before=copy.deepcopy(cs);proposed=response.get('candidates') or before
                regression=[cont.query(k,arm,f'round{round_no}_regression',i,rows,proposed) for i,rows in enumerate(common)]
                executable=all(q['status']=='ok' for q in regression)
                cs=proposed if executable else before
                common_feedback=[public.feedback(q) for q in regression]
                if not executable:common_feedback.append(dict(kind='compiler_feedback',message='Proposal execution failed; previous executable assertion set retained. Fix the proposal.',diagnostics=[q.get('unsupported_candidates',[]) for q in regression]))
                checkpoint=dict(round=round_no,before=before,proposed=proposed,after=cs,before_sha256=x.digest(before),after_sha256=x.digest(cs),
                    model_status=response['status'],execution_accepted=executable,regression=[ref.combined(q) for q in regression],change_basis=x.rel(block/'models'/k/arm/str(round_no)/'request.json'))
                x.dump(block/'development'/k/arm/f'checkpoint_{round_no}.json',checkpoint)
                print('FORMAL',k,arm,round_no,response['status'],'executed',executable,flush=True)
            x.dump(block/'development'/k/arm/'final.json',dict(candidates=cs,sha256=x.digest(cs),initial_sha256=x.digest(x.read(block/'initial'/f'{k}.json'))))
    x.dump(block/'final_freeze.json',{x.rel(p):x.sha(p) for p in block.glob('development/*/*/final.json')})


def paired_metrics(d,q,cs):
    result=dict(status=q['status'],fp=[],first_misses=[],later_misses=[],causal_detections=[],attribution_unknown=[],raw_fail_hit=0,antecedent_hits={},obligations_checked={},pending=0,cancelled=0)
    if q['status']!='ok':return result
    folders={r['variant']:x.ROOT/r['run'] for r in q['runs']}
    traces={v:x.read(f/'trace.json') for v,f in folders.items()};oracles={v:x.read(f/'independent_reference.json') for v,f in folders.items()}
    checks={v:{z[0]['cycle']:any(c['fail'] for c in z) for z in zip(*[x.read(f/f'checker_{j}_cycles.json') for j in range(len(cs))])} for v,f in folders.items()}
    for v,f in folders.items():
        raw=x.read(f/'result.json')
        for c in raw['candidates']:result['antecedent_hits'][v+'/'+c['id']]=c['trigger_count'];result['raw_fail_hit']+=c['fail_hit']
        result['pending']+=len(oracles[v]['pending']);result['cancelled']+=len(oracles[v]['cancelled'])
    control={e['cycle']:e for e in oracles['correct']['events']}
    for o in oracles['correct']['events']:
        for c in o['checks']:
            n=c['obligation']+':'+str(c['branch']);result['obligations_checked'][n]=result['obligations_checked'].get(n,0)+1
        if o['legal_prefix'] and checks['correct'][o['cycle']]:result['fp'].append(o['cycle'])
    for o in oracles['buggy']['events']:
        bad=[c for c in o['checks'] if not c['conditional'] and not c['passed']]
        if not bad:continue
        t=o['cycle'];start=max(i for i in range(t+1) if not traces['buggy'][i][d['rst']])
        prior=range(start+1,t);accepted=not any(checks['buggy'].get(i,False) for i in range(start+1,t+1))
        event=dict(cycle=t,transaction_obligations=bad)
        if accepted:result['first_misses' if o['first_violation'] else 'later_misses'].append(event);continue
        same=all(all(traces['correct'][i][n]==traces['buggy'][i][n] for n in d['observation_base']) for i in prior)
        legal=control[t]['legal_prefix'] and not any(checks['correct'].get(i,False) for i in range(start+1,t+1))
        changed=[n for n in d['observation_base'] if traces['correct'][t][n]!=traces['buggy'][t][n]]
        if o['first_violation'] and same and legal and len(changed)==1 and checks['buggy'][t]:result['causal_detections'].append(dict(event,changed_ports=changed))
        else:result['attribution_unknown'].append(dict(event,changed_ports=changed))
    return result


def acceptance():
    setup();block=ref.BLOCK
    assert all(x.sha(x.ROOT/p)==h for p,h in x.read(block/'final_freeze.json').items())
    out=block/'acceptance';out.mkdir(exist_ok=False)
    development=[json.loads(s) for s in (block/'queries.jsonl').read_text().splitlines()]
    results=[];overlap=[]
    for k in KEYS:
        d=x.read(x.OUT/'frozen'/k/'definition.json');hidden=x.read(block/'quarantine'/k/'inputs.json')
        old=[x.read(x.ROOT/q['runs'][0]['run']/'input.json') for q in development if q['case']==k and q['runs']]
        old+=x.read(PRIOR/'refinement_r04/quarantine'/f'{k}.json')
        for i,rows in enumerate(hidden):
            match=canonical(d,rows) in {canonical(d,r) for r in old};assert not match
            overlap.append(dict(case=k,scenario=i,exact_electrical_duplicate=match))
        for arm in ARMS:
            for version in ('initial','final'):
                cs=x.read(block/'initial'/f'{k}.json') if version=='initial' else x.read(block/'development'/k/arm/'final.json')['candidates']
                for cohort in ('original_target','new_artificial_sibling'):
                    if cohort=='original_target':x.engine.sources=lambda d:(x.OUT/'frozen'/d['key']/'correct.v',x.OUT/'frozen'/d['key']/'buggy.v')
                    else:x.engine.sources=lambda d:(block/'quarantine'/d['key']/'control.v',block/'quarantine'/d['key']/'sibling.v')
                    for i,rows in enumerate(hidden):
                        q=iso.evaluate(d,rows,cs,f'acceptance/{k}/{arm}/{version}/{cohort}/{i}')
                        x.append(out/'queries.jsonl',dict(case=k,arm=arm,version=version,cohort=cohort,scenario=i,**q))
                        results.append(dict(case=k,arm=arm,version=version,cohort=cohort,scenario=i,metrics=paired_metrics(d,q,cs)))
    x.dump(out/'results.json',results);x.dump(out/'overlap.json',dict(records=overlap,scope='exact input/reset values including deadline-bearing timing; no arbitrary semantic equivalence proof'))
    summary=[]
    for k in KEYS:
        for arm in ARMS:
            for cohort in ('original_target','new_artificial_sibling'):
                r=dict(case=k,arm=arm,cohort=cohort,scenarios=6,parent_acceptance='not_established')
                for version in ('initial','final'):
                    ms=[z['metrics'] for z in results if (z['case'],z['arm'],z['cohort'],z['version'])==(k,arm,cohort,version)]
                    r[version]={n:sum(len(z[n]) for z in ms) for n in ('fp','first_misses','later_misses','causal_detections','attribution_unknown')}
                    r[version]['unknown_scenarios']=sum(z['status']!='ok' for z in ms)
                    r[version]['causally_detected_obligations']=sorted({c['obligation'] for z in ms for e in z['causal_detections'] for c in e['transaction_obligations']})
                summary.append(r)
    x.dump(out/'summary.json',summary);print('ACCEPTANCE',len(results),'paired evaluations complete',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',default=cont.NAME);p.add_argument('action',choices=['prepare','develop','acceptance'])
    a=p.parse_args();x.OUT=x.ROOT/'deliverables'/a.run;globals()[a.action]()
