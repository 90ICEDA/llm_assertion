"""Four-policy frozen-pool search pilot; procedural diagnostics, NOT native SVA.

WSL: python3 scripts/research_search_compare.py prepare|run|report [--case CASE]
Outputs are exclusive and old experiments are read-only. Run cases independently.
"""
import argparse
import collections
import copy
import csv
import json
from pathlib import Path
import shutil
import time

import run_obligation_evidence as x
import obligation_isolated_search as isolated

OUT = x.ROOT / 'deliverables/research_search_20261014_r01'
OLD = x.ROOT / 'deliverables/obligation_evidence_20261013_r02'
METHODS = ['ordinary', 'disagreement', 'differential', 'contract']
SEEDS = [3113, 3119, 3121]
CASES = list(x.IDS)


def setup():
    x.OUT = OUT
    isolated.configure()


def prepare():
    OUT.mkdir(exist_ok=False)
    shutil.copytree(OLD / 'frozen', OUT / 'frozen')
    for name in ['pairs_frozen.json', 'obligation_catalog.json']:
        shutil.copy2(OLD / name, OUT / name)
    protocol = dict(
        methods=METHODS, seeds=SEEDS, queries_per_case_seed_method=12,
        cycles_per_variant=24, parents=CASES,
        scope='six synthetic parents; original frozen candidate pool; diagnostic procedural checker only',
        common_information='same frozen RTL variants, port widths, public specifications, candidates and input constraints accessible; no holdout or historical evidence fed to policies',
        feedback_used=dict(ordinary='none', disagreement='candidate fail XOR count only',
            differential='buggy/fixed output mismatch count only; NOT bug adjudication',
            contract='independent scoped obligation checks, trigger coverage, verified gap identity'),
        algorithms=dict(ordinary='unchanged seeded public random generator',
            disagreement='unchanged incumbent mutation, fresh draw every third query',
            differential='same mutation and exploration as disagreement, reward is output differences',
            contract='round-robin repair-differential, legal transaction perturbation, obligation-gap scheduling; least observed template selected on gap steps; retain highest distinct verified-gap/repair-witness score'),
        query_accounting='Every submitted 24-cycle input costs 1, including failures; both RTLs and whole supported frozen candidate pool evaluated; two physical compiles/sims; no cache/retry/solver/model',
        evidence_rule='Input legality first, independent reference next. Repair witness requires buggy first obligation violation and fixed legal prefix plus same obligation satisfied. FP requires legal whole prefix, FN full prefix accepted to first violation. Waveform difference alone is never evidence.',
        gap_dedup='case, candidate bytes hash, FP/FN, obligation; all FP prefixes grouped as legal_prefix. Waveform variants never independent discoveries. Branches recorded but do not multiply gaps.',
        trace_dedup='exact reset-to-evidence input/output prefix excluding absolute cycle and stimulus labels + candidate hash + kind + violated obligation IDs; separate from gap metric',
        independence='all runs development data; no independence or heldout claim; six parent units remain denominator',
        stat_scope='local spec confirms isolated event latency 2 and captured length. It does not explicitly authorize overlap. Entire queries with overlapping frame_done events (spacing <=2 before reset) are unknown_spec and excluded from verified evidence; retained raw diagnostics.',
        unknowns='intr timing unknown; spill only collision_empty; filter unsupported candidates remain denominator; fifo original presented defect repair witness may remain absent',
        full_parent_pass='not established for any parent by this experiment',
        native_sva=False, formal_proof=False,
        frozen_at_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()))
    x.dump(OUT/'protocol.json', protocol)
    files = [Path(__file__), x.ROOT/'scripts/obligation_search_policy.py',
             x.ROOT/'scripts/obligation_evidence_monitor.py',
             x.ROOT/'scripts/obligation_isolated_search.py',
             x.ROOT/'scripts/run_obligation_evidence.py',
             x.ROOT/'scripts/run_repair_contract.py',
             x.ROOT/'scripts/contract_v3_checker.py']
    for p in files:
        q=OUT/'source_snapshot'/p.name;shutil.copy2(p,q) if q.parent.exists() else (q.parent.mkdir(),shutil.copy2(p,q))
    frozen=[p for p in (OUT/'frozen').rglob('*') if p.is_file()]+files+[OUT/'protocol.json',OUT/'pairs_frozen.json']
    x.dump(OUT/'freeze.json',{x.rel(p):x.sha(p) for p in frozen})
    for cmd in [['python3','--version'],['iverilog','-V'],['vvp','-V']]:
        x.command(cmd,OUT,'version_'+cmd[0],15)
    print('PREPARED', x.rel(OUT),flush=True)


def guard():
    assert all(x.sha(x.ROOT/p)==h for p,h in x.read(OUT/'freeze.json').items()), 'frozen dependency changed'


def stat_ambiguous(rows):
    last=None
    for r in rows:
        if not r['rst_ni']:last=None
        elif r['frame_done_i']:
            if last is not None and r['cycle']-last<=2:return True
            last=r['cycle']
    return False


def augment(d, rows, q):
    start=time.perf_counter()
    q['raw_diagnostic_evidence_count']=len(q['evidence'])
    q['spec_status']='unknown_overlap_permission' if d['key']=='stat' and stat_ambiguous(rows) else 'unknown_mask_timing' if d['key']=='intr' else 'scoped'
    if q['spec_status']!='scoped':
        q['excluded_diagnostic_evidence']=q['evidence'];q['evidence']=[]
    runs={r['variant']:r for r in q['runs'] if r['status']=='ok'}
    q.update(difference_score=0,repair_witnesses=[],obligation_coverage=[],transactions=[],pair_witnesses=[])
    if len(runs)!=2:return
    traces={v:x.read(x.ROOT/r['run']/'trace.json') for v,r in runs.items()}
    refs={v:x.read(x.ROOT/r['run']/'independent_reference.json') for v,r in runs.items()}
    q['difference_score']=sum(a[n]!=b[n] for a,b in zip(traces['correct'],traces['buggy']) if a[d['rst']] for n in d['outputs'])
    q['reset_cancellations']={v:r['cancelled'] for v,r in refs.items()}
    fix={r['cycle']:r for r in refs['correct']['events']}
    for event in refs['buggy']['events']:
        t=event['cycle'];f=fix[t]
        for c in event['checks']:
            q['transactions'].append(dict(variant='buggy',**c))
            if q['spec_status']=='scoped' and not c['conditional']:
                q['obligation_coverage'].append(c['obligation'])
                fc=next((z for z in f['checks'] if z['obligation']==c['obligation'] and z['trigger_cycle']==c['trigger_cycle']),None)
                if event['first_violation'] and not c['passed'] and f['legal_prefix'] and fc and fc['passed']:
                    q['repair_witnesses'].append(dict(obligation=c['obligation'],cycle=t,transaction_id=c['transaction_id'],trigger_cycle=c['trigger_cycle'],buggy=c,fixed=fc))
    if d['key']=='fifo':
        q['handshake_records']=[dict(cycle=r['cycle'],presented=bool(r['push_i']),accepted=bool(r['push_i'] and r['pop_i']),payload=r['data_i'],reset_cancels=not bool(r[d['rst']])) for r in rows]
    for e in q['evidence']:
        trace=traces[e['variant']];t=e['cycle'];reset=max(i for i in range(t+1) if not trace[i][d['rst']])
        prefix=[{n:v for n,v in r.items() if n not in ('cycle','stimulus_id')} for r in trace[reset:t+1]]
        obs=sorted(c['obligation'] for c in e['obligations'] if not c['passed'] and not c['conditional'])
        e['canonical_trace_id']=x.digest([d['key'],e['candidate_sha256'],e['kind'],obs,prefix])
        e['gap_keys']=[[d['key'],e['candidate_sha256'],e['kind'],ob] for ob in (obs if e['kind']=='miss' else ['legal_prefix'])]
    for pair in x.read(OUT/'pairs_frozen.json'):
        if not (pair['natural_pair'] and pair['status']=='distinguished_on_checked_legal_inputs' and pair['parent_bug_id']==d['parent_bug_id']):continue
        if q['spec_status']!='scoped':continue
        for v,r in runs.items():
            ids=r['candidate_ids']
            if pair['a'] not in ids or pair['b'] not in ids:continue
            checks={cid:{z['cycle']:z for z in x.read(x.ROOT/r['run']/f'checker_{ids.index(cid)}_cycles.json')} for cid in [pair['a'],pair['b']]}
            oracles={z['cycle']:z for z in refs[v]['events']};alarms={pair['a']:False,pair['b']:False}
            for row in traces[v]:
                t=row['cycle']
                if not row[d['rst']]:alarms=dict.fromkeys(alarms,False);continue
                for cid in alarms:alarms[cid]|=bool(checks[cid][t]['fail'])
                ref=oracles[t]
                if alarms[pair['a']]!=alarms[pair['b']] and (ref['legal_prefix'] or ref['first_violation']):
                    kind='false_positive' if ref['legal_prefix'] else 'miss'
                    candidate=next(cid for cid,alarm in alarms.items() if alarm==(kind=='false_positive'))
                    obs=['legal_prefix'] if kind=='false_positive' else [z['obligation'] for z in ref['checks'] if not z['passed'] and not z['conditional']]
                    q['pair_witnesses'].append(dict(pair_id=pair['pair_id'],candidate_id=candidate,kind=kind,obligations=obs,run=r['run'],cycle=t,variant=v))
    q['obligation_coverage']=sorted(set(q['obligation_coverage']))
    q['audit_wall_seconds']=time.perf_counter()-start


def gaps(qs):
    return {tuple(g) for q in qs for e in q['evidence'] for g in e['gap_keys']}


def run(case):
    guard();setup()
    cases=[case] if case else CASES
    for k in cases:
        folder=OUT/'search'/k;folder.mkdir(parents=True,exist_ok=False)
        d=x.read(OUT/'frozen'/k/'definition.json');pool=x.read(OUT/'frozen'/k/'candidates.json')
        for seed in SEEDS:
            for method in METHODS:
                incumbent,best=None,-1;seen=[];template_use=collections.Counter()
                for step in range(12):
                    s=seed+step*1009;category='random'
                    if method=='ordinary':rows=x.policy.ordinary(d,s)
                    elif method in ('disagreement','differential'):
                        rows=x.policy.disagreement(d,s,incumbent if step%3 else None)
                    else:
                        category=['repair_differential','legal_perturbation','obligation_gap'][step%3]
                        if category=='legal_perturbation':rows=x.policy.disagreement(d,s,incumbent)
                        else:
                            # The public contract's four template variants expose different branches.
                            # Coverage prioritization is deliberately finite, not a solver completeness claim.
                            variant=min(range(4),key=lambda v:(template_use[v],v)) if category=='obligation_gap' else (step//3)%4
                            rows=x.policy.guided(d,s,variant);template_use[variant]+=1
                    qid=f'{k}/{seed}/{method}/{step:02d}'
                    x.append(folder/'attempts.jsonl',dict(query_id=qid,input_sha256=x.digest(rows),submitted_utc=time.time()))
                    q=isolated.evaluate(d,rows,pool['candidates'],'search/'+qid)
                    q.update(query_id=qid,case=k,parent_bug=x.IDS[k],seed=seed,method=method,step=step,category=category)
                    augment(d,rows,q);seen.append(q)
                    score=q['disagreement_score'] if method=='disagreement' else q['difference_score'] if method=='differential' else len(gaps([q]))+len({z['obligation'] for z in q['repair_witnesses']})
                    if score>best:incumbent,best=rows,score
                    q['search_reward']=score;x.append(folder/'queries.jsonl',q)
                print('SEARCH_COMPLETE',k,seed,method,flush=True)


def report():
    guard()
    qs=[json.loads(s) for k in CASES for s in (OUT/'search'/k/'queries.jsonl').read_text().splitlines()]
    assert len(qs)==864 and len({q['query_id'] for q in qs})==864
    summaries=[];pair_rows=[];gains=[]
    pairs=[p for p in x.read(OUT/'pairs_frozen.json') if p['natural_pair'] and p['status']=='distinguished_on_checked_legal_inputs']
    assert len(pairs)==11
    for k in CASES:
        for method in METHODS:
            sub=[q for q in qs if (q['case'],q['method'])==(k,method)];ev=[e for q in sub for e in q['evidence']]
            gs=gaps(sub);trace_ids={e['canonical_trace_id'] for e in ev}
            summaries.append(dict(case=k,method=method,queries=len(sub),gap_count=len(gs),gaps=sorted(gs),
                fp_gaps=sum(g[2]=='false_positive' for g in gs),fn_gaps=sum(g[2]=='miss' for g in gs),raw_evidence=len(ev),unique_traces=len(trace_ids),duplicate_trace_evidence=len(ev)-len(trace_ids),
                waveform_variants_beyond_gap_count=max(0,len(trace_ids)-len(gs)),
                repair_obligations=sorted({w['obligation'] for q in sub for w in q['repair_witnesses']}),
                repair_witness_count=sum(len(q['repair_witnesses']) for q in sub),
                covered_obligations=sorted({ob for q in sub for ob in q['obligation_coverage']}),
                unknown_spec_queries=sum(q['spec_status']!='scoped' for q in sub),
                unsupported_candidate_query_entries=sum(len(q['unsupported_candidates']) for q in sub),
                query_statuses=dict(collections.Counter(q['status'] for q in sub)),
                costs={n:sum(q.get(n,0) for q in sub) for n in ['compile_attempts','simulation_attempts','sim_cycles','wall_seconds','cpu_seconds','audit_wall_seconds','model_calls','solver_calls']},
                native_sva_status='not_run_procedural_diagnostic_only',whole_parent_pass=False))
        for seed in SEEDS:
            sets={m:gaps([q for q in qs if (q['case'],q['seed'],q['method'])==(k,seed,m)]) for m in METHODS}
            for m in METHODS[:-1]:gains.append(dict(case=k,seed=seed,comparator=m,contract_only=sorted(sets['contract']-sets[m]),comparator_only=sorted(sets[m]-sets['contract'])))
    for p in pairs:
        by={m:[dict(query_id=q['query_id'],**w) for q in qs if q['method']==m for w in q['pair_witnesses'] if w['pair_id']==p['pair_id']] for m in METHODS}
        canonical=lambda ws:{(w['candidate_id'],w['kind'],ob) for w in ws for ob in w['obligations']}
        for m,ws in by.items():
            gs=canonical(ws)
            pair_rows.append(dict(pair_id=p['pair_id'],parent_bug=p['parent_bug_id'],a=p['a'],b=p['b'],method=m,distinguished=bool(ws),gap_keys=sorted(gs),gap_count=len(gs),raw_witnesses=len(ws),representative_witnesses=ws[:2],new_vs_ordinary=sorted(gs-canonical(by['ordinary']))))
    x.dump(OUT/'parent_method_results.json',summaries);x.dump(OUT/'pair_results.json',pair_rows);x.dump(OUT/'paired_gain.json',gains)
    x.dump(OUT/'summary.json',dict(queries=len(qs),parents=6,focused_pairs=11,native_sva=False,model_calls=0,
        per_method={m:dict(gaps=sum(r['gap_count'] for r in summaries if r['method']==m),pairs=sum(r['distinguished'] for r in pair_rows if r['method']==m),unknown_spec_queries=sum(r['unknown_spec_queries'] for r in summaries if r['method']==m)) for m in METHODS},
        total_costs={n:sum(q.get(n,0) for q in qs) for n in ['compile_attempts','simulation_attempts','sim_cycles','wall_seconds','cpu_seconds','audit_wall_seconds']},full_parent_passes=0))
    lines=['# Four-policy search pilot (2026-10-14)','',
        'All 864 queries are new physical runs. Same frozen pool, three seeds and 12-query budgets. Diagnostic Icarus procedural checks, not native SVA or formal proof. All evidence is development data.',
        '', '| Parent | Method | Distinct FP / FN gaps | Repair witness obligations | Unknown spec queries |', '|---|---|---|---|---|']
    for r in summaries:lines.append(f"| {r['case']} | {r['method']} | {r['fp_gaps']} / {r['fn_gaps']} | {', '.join(r['repair_obligations']) or 'none'} | {r['unknown_spec_queries']}/36 |")
    lines+=['','## Focused 11 pairs','','| Pair | Parent | ordinary / disagreement / differential / contract gap counts |','|---|---|---|']
    for p in pairs:lines.append(f"| {p['pair_id']} | {p['parent_bug_id']} | {' / '.join(str(next(r['gap_count'] for r in pair_rows if r['pair_id']==p['pair_id'] and r['method']==m)) for m in METHODS)} |")
    lines+=['','`pair_results.json` contains each method\'s exact gap IDs, added gaps versus ordinary and raw witness locations. `paired_gain.json` preserves both positive and negative differences for each seed. A distinct candidate gap is not an independent bug.',
        '', 'Stat timing: frozen spec_sources.json cites the local spec (two-entry pipeline, original captured length). Overlap permission is not explicit; all overlap-bearing query evidence is unknown and excluded. No upstream historical stat fix is established. Spill invalid data and intr mask timing remain unresolved. FIFO Depth=0 is a regression case and absent original-target witness remains absent.',
        '', 'Contract search is a finite three-category policy pilot. Gap template scheduling uses exposure counts, not a general constraint solver; no completeness claim or mechanism-superiority claim. The native-SVA/model refinement chain is outside this runner.',
        '', 'Commands: `python3 scripts/research_search_compare.py prepare`; `python3 scripts/research_search_compare.py run`; `python3 scripts/research_search_compare.py report`. Use WSL with Icarus. Existing output is append-protected; a second run needs a new directory constant and freeze.',
        '', 'Historical Ibex #54 remains separate: prior actual original-RTL reproduction is in `deliverables/obligation_evidence_20261013_r02/historical_screening/ibex_54`. Upstream PR https://github.com/lowRISC/ibex/pull/54 and issue https://github.com/lowRISC/ibex/issues/51. This runner neither reexecutes nor claims new model validation on Ibex.']
    (OUT/'REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    with (OUT/'results.csv').open('w',newline='') as f:
        keys=['case','method','queries','gap_count','fp_gaps','fn_gaps','raw_evidence','unique_traces','duplicate_trace_evidence','repair_witness_count','unknown_spec_queries','unsupported_candidate_query_entries']
        w=csv.DictWriter(f,fieldnames=keys,extrasaction='ignore');w.writeheader();w.writerows(summaries)
    print(json.dumps(x.read(OUT/'summary.json')),flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=['prepare','run','report']);ap.add_argument('--case',choices=CASES);args=ap.parse_args();setup()
    if args.action=='prepare':prepare()
    elif args.action=='run':run(args.case)
    else:report()
