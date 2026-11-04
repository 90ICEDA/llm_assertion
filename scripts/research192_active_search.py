"""S0-S3 fresh paired search on all six frozen parents and the original 11 pairs.

Reuses the original simulator, candidate checker and independent obligation
monitor. This legacy stratum is procedural diagnostics, NOT native SVA proof.
"""
import argparse
import collections
import concurrent.futures
import csv
import json
from pathlib import Path
import shutil
import time

import research_search_compare as old
import research_active_temporal as active

x, isolated = old.x, old.isolated
ROOT = x.ROOT
SOURCE = ROOT / 'deliverables/research_search_20261014_r01'
METHODS = ('S0', 'S1', 'S2', 'S3')
SEEDS = (19207, 19219, 19231)
BUDGET = 12


def setup(out):
    old.OUT = out
    x.OUT = out
    isolated.configure()


def prepare(out):
    out.mkdir(parents=True, exist_ok=False)
    shutil.copytree(SOURCE / 'frozen', out / 'frozen')
    for name in ('pairs_frozen.json', 'obligation_catalog.json'):
        shutil.copy2(SOURCE / name, out / name)
    x.dump(out / 'protocol.json', dict(methods=METHODS, seeds=SEEDS, queries_per_unit=BUDGET,
        parents=list(old.CASES), frozen_pairs=11, candidate_text_changed=False,
        S0='Unchanged ordinary public random generator',
        S1='Unchanged disagreement incumbent mutation, fresh exploration every third query; reward candidate XOR only',
        S2='Unchanged repair-contract three-category scheduling from research_search_compare',
        S3='Active structural dimensions, confirmed-protection deficit, confirmed-evidence novelty and measured query count cost; same public guided/random/mutation constructors',
        ranking_weights=dict(discrimination=2, deficit=2, novelty=1),
        candidate_analysis='Lexical/structural hypotheses only; no equivalence or semantic solver claim',
        constraints='Existing repair_environment enforces handshake persistence and threshold stability; original reset epochs and transaction monitor unchanged',
        novelty='Distinct parent/candidate-content/kind/obligation gaps; unknown excluded, FP legal-prefix grouping unchanged; seeds and cycles are not parents',
        oracle='Existing independent port/history reference, legal prefix and first violated obligation. stat overlap and intr mask timing remain unknown.',
        budget='Every submitted 24-cycle stimulus, including duplicate/unknown/failure, costs one query and two RTL compile/execute attempts; no free simulation during ranking',
        cost='Actual query/compile/simulation counts, wall and CPU; selector time separately measured. Wall under contention descriptive only.',
        outcomes='Development diagnostics only; evidence acquisition does not imply a repaired SVA or independent acceptance',
        version='v2 protection is separate from exposure; no protection credit inferred from legacy coverage alone',
        information='Same initial candidates and public contracts; baseline observation views unchanged; no independent/holdout artifacts read',
        native_sva=False, model_calls=0, tokens=0, workers=3, prepared_at=time.time()))
    files = [Path(__file__), Path(active.__file__), Path(old.__file__), Path(isolated.__file__),
             Path(x.__file__), Path(x.policy.__file__), ROOT/'scripts/obligation_evidence_monitor.py',
             ROOT/'scripts/contract_v3_checker.py', ROOT/'scripts/run_repair_contract.py']
    for file in files:
        target = out/'source_snapshot'/file.name
        target.parent.mkdir(exist_ok=True)
        shutil.copy2(file, target)
    x.dump(out/'sealed.json', {x.rel(p): x.sha(p) for p in out.rglob('*') if p.is_file()})
    x.dump(out/'outcome.json', dict(status='prepared'))


def guard(out):
    assert all(x.sha(ROOT/p) == h for p, h in x.read(out/'sealed.json').items())


def query_options(d, seed, incumbent, obligations):
    # This is a finite public grammar, not candidate execution or oracle lookahead.
    dimensions = {
        0: ['trigger', 'response', 'transaction'],
        1: ['window', 'response', 'trigger'],
        2: ['window', 'transaction', 'vacuity'],
        3: ['exception', 'window', 'transaction']}
    options = []
    for variant in range(4):
        options.append(dict(id=f'guided_{variant}', dimensions=dimensions[variant], obligations=obligations,
                            estimated_cost=1, rows=x.policy.guided(d, seed, variant),
                            constraints=['handshake_persistence', 'reset_epoch', 'transaction_reference_required']))
    options.extend([
        dict(id='random', dimensions=['trigger', 'vacuity'], obligations=obligations, estimated_cost=1,
             rows=x.policy.ordinary(d, seed)),
        dict(id='mutation', dimensions=['trigger', 'response'], obligations=obligations, estimated_cost=1,
             rows=x.policy.disagreement(d, seed, incumbent))])
    return options


def worker(args):
    out_s, case = args
    out = Path(out_s)
    guard(out); setup(out)
    folder = out/'search'/case
    folder.mkdir(parents=True, exist_ok=False)
    d = x.read(out/'frozen'/case/'definition.json')
    candidates = x.read(out/'frozen'/case/'candidates.json')['candidates']
    obligations = [r['obligation_id'] for r in x.read(out/'obligation_catalog.json') if r['case'] == case]
    x.dump(folder/'candidate_analysis.json', active.analyze_candidates(candidates))
    for seed_index, seed in enumerate(SEEDS):
        # Rotate group order without changing any policy or per-query stimulus seed.
        order = METHODS[seed_index:] + METHODS[:seed_index]
        for method in order:
            incumbent, best, seen = None, -1, []
            template_use = collections.Counter()
            selector = active.ActiveSelector(candidates, obligations)
            for step in range(BUDGET):
                s = seed + step*1009
                begin = time.perf_counter()
                decision = dict(policy=method)
                if method == 'S0': rows = x.policy.ordinary(d, s)
                elif method == 'S1': rows = x.policy.disagreement(d, s, incumbent if step % 3 else None)
                elif method == 'S2':
                    category = ['repair_differential', 'legal_perturbation', 'obligation_gap'][step % 3]
                    decision['category'] = category
                    if category == 'legal_perturbation': rows = x.policy.disagreement(d, s, incumbent)
                    else:
                        v = min(range(4), key=lambda z:(template_use[z], z)) if category == 'obligation_gap' else (step//3)%4
                        rows = x.policy.guided(d, s, v); template_use[v] += 1
                else:
                    decision = selector.select(query_options(d, s, incumbent, obligations))
                    rows = decision['chosen']['rows']
                    # Save the full ranking including byte-identical input proposals.
                elapsed = time.perf_counter() - begin
                qid = f'{case}/{seed}/{method}/{step:02d}'
                x.dump(out/'search'/qid/'selection.json', decision)
                x.append(folder/'attempts.jsonl', dict(query_id=qid, input_sha256=x.digest(rows), submitted_at=time.time()))
                q = isolated.evaluate(d, rows, candidates, 'search/'+qid)
                q.update(query_id=qid, case=case, parent_bug=x.IDS[case], seed=seed, method=method, step=step,
                         selector_seconds=elapsed)
                old.augment(d, rows, q)
                score = q['disagreement_score'] if method == 'S1' else len(old.gaps([q])) + len({z['obligation'] for z in q['repair_witnesses']})
                if score > best: incumbent, best = rows, score
                q['search_reward'] = score
                if method == 'S3':
                    selector.observe(decision['chosen']['id'],
                        'confirmed' if q['spec_status'] == 'scoped' and q['status'] in ('ok', 'partial_candidate_unknown') else 'unknown',
                        q['obligation_coverage'], [list(g) for g in old.gaps([q])], actual_cost=1)
                seen.append(q)
                q['first_gap_keys'] = sorted(old.gaps([q]) - old.gaps(seen[:-1]))
                x.append(folder/'queries.jsonl', q)
            print('COMPLETE192', case, seed, method, len(old.gaps(seen)), flush=True)
    return case


def report(out):
    guard(out)
    qs = [json.loads(s) for p in sorted((out/'search').glob('*/queries.jsonl')) for s in p.read_text().splitlines()]
    totals, curves, pairs = [], [], []
    sets = {m:old.gaps([q for q in qs if q['method'] == m]) for m in METHODS}
    for m in METHODS:
        rows = [q for q in qs if q['method'] == m]
        totals.append(dict(method=m, queries=len(rows), confirmed_gaps=len(sets[m]),
            fp_gaps=sum(g[2]=='false_positive' for g in sets[m]), fn_gaps=sum(g[2]=='miss' for g in sets[m]),
            exclusive_gaps=len(sets[m] - set().union(*(v for k,v in sets.items() if k != m))),
            gap_keys=sorted(sets[m]), unknown_spec_queries=sum(q['spec_status'] != 'scoped' for q in rows),
            failed_queries=sum(q['status'] not in ('ok', 'partial_candidate_unknown') for q in rows),
            unsupported_candidate_queries=sum(len(q['unsupported_candidates']) for q in rows),
            **{k:sum(q.get(k,0) for q in rows) for k in ('compile_attempts','simulation_attempts','sim_cycles','wall_seconds','cpu_seconds','selector_seconds')},
            model_calls=0, tokens=0, evidence_to_sva_improvement='not_evaluated_in_search_only_experiment'))
        for step in range(BUDGET):
            prefix = [q for q in rows if q['step'] <= step]
            curves.append(dict(method=m, queries_per_parent_seed=step+1, actual_queries=len(prefix),
                               actual_simulations=sum(q['simulation_attempts'] for q in prefix),
                               confirmed_gaps=len(old.gaps(prefix)), wall_seconds=sum(q['wall_seconds'] for q in prefix)))
    for case in old.CASES:
        for seed in SEEDS:
            ss = {m:old.gaps([q for q in qs if (q['case'],q['seed'],q['method']) == (case,seed,m)]) for m in METHODS}
            for m in METHODS[:-1]:
                pairs.append(dict(case=case, parent_bug=x.IDS[case], seed=seed, comparator=m,
                                  S3_only=sorted(ss['S3']-ss[m]), comparator_only=sorted(ss[m]-ss['S3'])))
    pair_rows=[]
    for p in x.read(out/'pairs_frozen.json'):
        if not (p['natural_pair'] and p['status']=='distinguished_on_checked_legal_inputs'): continue
        for m in METHODS:
            ws=[dict(query_id=q['query_id'], **w) for q in qs if q['method']==m for w in q['pair_witnesses'] if w['pair_id']==p['pair_id']]
            pair_rows.append(dict(pair_id=p['pair_id'], parent_bug=p['parent_bug_id'], method=m,
                                 distinguished=bool(ws), representative_witnesses=ws[:2]))
    for name, value in [('method_totals',totals),('cost_curve',curves),('paired_gain',pairs),('pair_results',pair_rows)]:
        x.dump(out/(name+'.json'), value)
    with (out/'cost_curve.csv').open('w', newline='', encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(curves[0]));w.writeheader();w.writerows(curves)
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig, ax=plt.subplots(figsize=(7,4))
        for m in METHODS:
            rr=[r for r in curves if r['method']==m]
            ax.step([r['actual_simulations'] for r in rr],[r['confirmed_gaps'] for r in rr],where='post',label=m)
        ax.set(xlabel='Actual RTL simulations (all parents and seeds)',ylabel='Distinct confirmed candidate gaps',title='Legacy 11-pair diagnostic search (6 parent bugs)')
        ax.legend();ax.grid(alpha=.2);fig.tight_layout();fig.savefig(out/'cost_curve.png',dpi=180);plt.close(fig)
    except ImportError:
        x.dump(out/'plot_status.json',dict(status='matplotlib_unavailable',data='cost_curve.csv'))
    lines=['# S0–S3: historical 11-pair diagnostic stratum', '',
           'Fresh simulation; same frozen candidates, 3 paired seeds, 12 queries per parent/seed/strategy. Procedural candidate diagnostic, not native SVA or formal proof.', '',
           '|Strategy|Queries|Distinct FP / FN gaps|Exclusive gaps|Unknown specification queries|Actual simulations|',
           '|---|---:|---:|---:|---:|---:|']
    for r in totals: lines.append(f"|{r['method']}|{r['queries']}|{r['fp_gaps']} / {r['fn_gaps']}|{r['exclusive_gaps']}|{r['unknown_spec_queries']}|{r['simulation_attempts']}|")
    lines.extend(['', 'Distinct candidate gaps are not independent bugs. Intr mask timing and overlapping stat transactions remain unknown. Every unknown and duplicate consumes budget. Existing evidence is immutable. Acquisition alone does not establish assertion improvement.', '',
                  'S3 estimates discrimination from structure, not symbolic semantics. The finite query grammar can miss relevant boundaries; identical candidate behavior and already-saturated obligations can remove its advantage. All paired positive and negative differences are retained in paired_gain.json.', '',
                  'No outcome-dependent reselection, seed changes or budget extensions; no LLM calls. A separate native FIFO stratum is needed for native SVA claims.'])
    (out/'REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    x.dump(out/'outcome.json',dict(status='completed' if len(qs)==len(old.CASES)*len(SEEDS)*len(METHODS)*BUDGET else 'partial',
                                 queries=len(qs),native_sva=False, model_calls=0))
    print(json.dumps(totals,ensure_ascii=False),flush=True)


if __name__ == '__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('action',choices=('prepare','run','report'));ap.add_argument('--out',type=Path,required=True)
    a=ap.parse_args();out=a.out.resolve()
    if a.action=='prepare':prepare(out)
    elif a.action=='report':report(out)
    else:
        guard(out)
        assert x.read(out/'outcome.json')['status']=='prepared'
        x.dump(out/'outcome.json',dict(status='running'))
        with concurrent.futures.ProcessPoolExecutor(max_workers=3) as pool:
            list(pool.map(worker,[(str(out),k) for k in old.CASES]))
        report(out)
