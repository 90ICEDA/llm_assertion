"""Second audit block: preserve candidates, isolate unsupported expressions.

The r01 scripts are deliberately unchanged. Run init AFTER prepare and before
search. All phases have exclusive markers; a retry needs a new run directory.
"""
import argparse
import collections
import copy
import csv
import itertools
import json
from pathlib import Path
import resource
import shutil
import time

import run_obligation_evidence as x
import audit_obligation_evidence as audit
import finalize_obligation_evidence as final


def configure():
    x.engine.OUT = x.OUT
    x.engine.tb_text = x.checker.tb_text
    x.engine.sources = lambda d: (x.OUT/'frozen'/d['key']/'correct.v', x.OUT/'frozen'/d['key']/'buggy.v')


def cpu():
    a = resource.getrusage(resource.RUSAGE_SELF)
    b = resource.getrusage(resource.RUSAGE_CHILDREN)
    return a.ru_utime+a.ru_stime+b.ru_utime+b.ru_stime


def validate(d, candidates):
    accepted, rejected = [], []
    for c in candidates:
        try:
            x.checker.normalize(c, d, c.get('authorized_history_depth', 0))
            if c.get('syntax_status') == 'unsupported_syntax':
                raise AssertionError('historical_unsupported_status_retained')
            accepted.append(c)
        except (AssertionError, KeyError, TypeError) as exc:
            rejected.append(dict(candidate_id=c['id'], candidate_sha256=x.digest(c),
                                 status='unsupported_or_unpermitted', reason=str(exc)))
    return accepted, rejected


def init():
    (x.OUT/'block_r02').mkdir(exist_ok=False)
    prior = x.ROOT/'deliverables/obligation_evidence_20261013_r01'
    # This bounded manifest includes all prior raw evidence, not just successes.
    preservation = {x.rel(p): x.sha(p) for p in prior.rglob('*') if p.is_file()}
    x.dump(x.OUT/'block_r02/prior_artifact_hashes.json', preservation)
    files = [Path(__file__), *x.ROOT.joinpath('scripts').glob('*obligation*.py'),
             *x.ROOT.joinpath('scripts').glob('*contract*.py')]
    snapshots = [x.snapshot(p) for p in sorted(set(files))]
    x.dump(x.OUT/'block_r02/implementation_manifest.json', snapshots)
    public = {}
    for k in x.IDS:
        d = x.read(x.OUT/'frozen'/k/'definition.json')
        pool = x.read(x.OUT/'frozen'/k/'candidates.json')['candidates']
        cs, rejected = validate(d, pool)
        public[k] = dict(accepted=[c['id'] for c in cs], rejected=rejected,
                         candidate_text_changed=False, validation_attempts=len(pool))
    x.dump(x.OUT/'block_r02/shared_candidate_preflight.json', public)
    protocol = copy.deepcopy(x.read(x.OUT/'protocol.json'))
    protocol.update(version=2, block='isolate_unsupported_candidates_without_repair',
        only_executor_change='Validate each candidate separately against the same public grammar/permission policy; batch supported candidates only; retain unsupported candidates as unknown on every query. No text/history authorization changes.',
        accounting='Each submitted input including failure consumes one query. Static candidate validation charged per query; shared preflight separately listed. Two compiles/sims on supported pool. Unsupported candidates remain denominator entries, never pass.',
        cost_measurement='per-query process+child user/system CPU seconds and wall seconds; model/GPU cost not applicable to search',
        development_lineage='r01 search traces already seen; r02 is a reproducibility/executor correction block, not new independent generalization',
        invariants=['same candidate bytes as r01', 'same methods/seeds/24-cycle budgets as r01', 'no oracle labels drive ordinary or disagreement policy', 'unknowns not removed from denominators'])
    x.dump(x.OUT/'block_r02/protocol.json', protocol)
    final.obligations()
    audit.oracle_tests()
    hashes = {x.rel(p): x.sha(p) for p in [Path(__file__), x.OUT/'block_r02/protocol.json',
                x.OUT/'block_r02/shared_candidate_preflight.json', x.OUT/'obligation_catalog.json']}
    x.dump(x.OUT/'block_r02/freeze.json', hashes)
    print(json.dumps(dict(prior_files=len(preservation), candidates=public)), flush=True)


def guard():
    x.guard()
    assert all(x.sha(x.ROOT/p) == h for p, h in x.read(x.OUT/'block_r02/freeze.json').items())


def evaluate(d, rows, candidates, label):
    """No candidate edits; errors isolated before tool invocation.

    Public result includes per-candidate unknowns. The private oracle result
    remains in files and is never imported by a public search policy.
    """
    start, start_cpu = time.perf_counter(), cpu()
    cs, rejected = validate(d, candidates)
    q = dict(attempted_queries=1, runs=[], evidence=[], status='pending',
             cache_hits=0, retries=0, solver_calls=0, model_calls=0,
             compile_attempts=0, simulation_attempts=0, sim_cycles=0,
             candidate_cycle_evaluations=0, candidate_variant_evaluations=0,
             static_validation_attempts=len(candidates), unsupported_candidates=rejected,
             candidate_count=len(candidates), executable_candidate_count=len(cs),
             disagreement_score=0, input_content_sha256=x.digest(rows))
    errors = x.check_inputs(d, rows)
    if errors:
        q.update(status='invalid_input', errors=errors)
    elif not cs:
        q['status'] = 'all_candidates_unknown'
    else:
        for variant in ('correct', 'buggy'):
            raw = x.engine.execute_run(d, rows, cs, label, variant)
            folder = x.ROOT/raw['run_id']
            q['compile_attempts'] += 1
            q['simulation_attempts'] += int(raw['simulate'] is not None)
            a = x.adjudicate_folder(folder, d) if raw['status']=='ok' else dict(status=raw['status'])
            x.dump(folder/'adjudication.json', a)
            q['runs'].append(dict(run=x.rel(folder), variant=variant, status=a['status'],
                                 candidate_ids=[c['id'] for c in cs], validation_wall_seconds=raw['validation_wall_seconds']))
            for n in ('sim_cycles', 'candidate_cycle_evaluations', 'candidate_variant_evaluations'):
                q[n] += a.get(n, 0)
            if a['status'] != 'ok':
                continue
            tr = x.read(folder/'trace.json')
            checks = [x.read(folder/f'checker_{j}_cycles.json') for j in range(len(cs))]
            q['disagreement_score'] += sum(sum(a['fail'] != b['fail'] for a,b in zip(checks[i],checks[j]))
                                          for i,j in itertools.combinations(range(len(cs)),2))
            for j, events in enumerate(a['evidence']):
                for ev in events:
                    if ev['kind'] not in ('miss', 'false_positive'):
                        continue
                    t = ev['cycle']
                    reset = max(i for i in range(t+1) if not tr[i][d['rst']])
                    prefix = [{n:v for n,v in r.items() if n!='cycle'} for r in tr[reset:t+1]]
                    ed = dict(**ev, candidate_id=cs[j]['id'], candidate_sha256=x.digest(cs[j]),
                              run=x.rel(folder), variant=variant, prefix_sha256=x.digest(prefix),
                              scope='common_spill_validity_only' if d['key']=='spill' else 'resolved_target_contract')
                    ed['evidence_id'] = x.digest([d['key'], ed['candidate_sha256'], ev['kind'],
                                                 [c['obligation'] for c in ev['obligations']], prefix])
                    q['evidence'].append(ed)
        q['status'] = ('partial_candidate_unknown' if rejected else 'ok') if all(r['status']=='ok' for r in q['runs']) else 'execution_unknown'
    q.update(wall_seconds=time.perf_counter()-start, cpu_seconds=cpu()-start_cpu)
    return q


def search():
    guard(); configure()
    assert x.read(x.OUT/'oracle_qualification.json')['passed']
    assert x.read(x.OUT/'baseline/qualification.json')['passed']
    assert not x.read(x.OUT/'baseline/summary.json')['mismatches']
    (x.OUT/'search').mkdir(exist_ok=False)
    p = x.read(x.OUT/'block_r02/protocol.json')
    for k in x.IDS:
        d = x.read(x.OUT/'frozen'/k/'definition.json')
        pool = x.read(x.OUT/'frozen'/k/'candidates.json')
        for seed in p['seeds']:
            for method in p['methods']:
                incumbent, best = None, -1
                for step in range(p['queries_per_parent_seed_method']):
                    s = seed+step*1009
                    if method=='ordinary': rows=x.policy.ordinary(d,s)
                    elif method=='disagreement': rows=x.policy.disagreement(d,s,incumbent if step%3 else None)
                    else: rows=x.policy.guided(d,s,step)
                    qid=f'{k}/{seed}/{method}/{step:02d}'
                    # Write-ahead attempt survives a tool/process interruption.
                    x.append(x.OUT/'search/attempts.jsonl',dict(query_id=qid, status='submitted', input_sha256=x.digest(rows)))
                    q=evaluate(d,rows,pool['candidates'],'search/'+qid)
                    q.update(query_id=qid,case=k,parent_bug=x.IDS[k],seed=seed,method=method,step=step,cohort=pool['cohort'])
                    x.append(x.OUT/'search/queries.jsonl',q)
                    if method=='disagreement' and q['disagreement_score']>best:
                        incumbent,best=rows,q['disagreement_score']
                print('SEARCH',k,seed,method,flush=True)


def gaps(qs):
    out=set()
    for q in qs:
        for e in q['evidence']:
            if e['kind']=='false_positive':out.add((e['candidate_id'],'false_positive','legal_prefix'))
            else:out.update((e['candidate_id'],'miss',c['obligation']) for c in e['obligations'] if not c['passed'] and not c['conditional'])
    return out


def report():
    guard()
    folder=x.OUT/'analysis_r02';folder.mkdir(exist_ok=False)
    qs=[json.loads(s) for s in (x.OUT/'search/queries.jsonl').read_text().splitlines()]
    attempts=[json.loads(s) for s in (x.OUT/'search/attempts.jsonl').read_text().splitlines()]
    assert [q['query_id'] for q in qs]==[q['query_id'] for q in attempts]
    assert len(set(q['query_id'] for q in qs))==648==len(qs)
    # Existing pair implementation compares whole reset-prefix decisions and
    # only uses legacy pools (filter has no pair). No ambiguous hit credit.
    pairs=final.verify_pairs(qs)
    summaries=[];seed_results=[];curves=[];gain=[]
    methods=['ordinary','disagreement','obligation']
    for k in x.IDS:
        for m in methods:
            qq=[q for q in qs if q['case']==k and q['method']==m]
            assert len(qq)==36
            ev=[e for q in qq for e in q['evidence']]
            summaries.append(dict(case=k,method=m,queries=len(qq),gaps=sorted(gaps(qq)),gap_count=len(gaps(qq)),
                raw_evidence=len(ev),unique_evidence=len({e['evidence_id'] for e in ev}),
                pair_count=sum(p['distinguished'] for p in pairs if p['case']==k and p['method']==m and p['focused_11']),
                statuses=dict(collections.Counter(q['status'] for q in qq)),
                costs={n:sum(q[n] for q in qq) for n in ('compile_attempts','simulation_attempts','sim_cycles','candidate_cycle_evaluations','static_validation_attempts','wall_seconds','cpu_seconds')},
                whole_parent_pass='not_established',scope='supplementary_natural' if k=='filter' else 'unresolved' if k=='intr' else 'common_part' if k=='spill' else 'legacy_natural'))
        for seed in (3113,3119,3121):
            ss={}
            for m in methods:
                qq=sorted([q for q in qs if (q['case'],q['seed'],q['method'])==(k,seed,m)],key=lambda q:q['step'])
                assert [q['step'] for q in qq]==list(range(12))
                ss[m]=gaps(qq)
                seed_results.append(dict(case=k,seed=seed,method=m,gaps=sorted(ss[m])))
                for i in range(1,13):
                    curves.append(dict(case=k,seed=seed,method=m,queries=i,gaps=len(gaps(qq[:i])),
                        wall_seconds=sum(q['wall_seconds'] for q in qq[:i]),cpu_seconds=sum(q['cpu_seconds'] for q in qq[:i])))
            for m in methods[:2]:
                gain.append(dict(case=k,seed=seed,comparator=m,guided_only=sorted(ss['obligation']-ss[m]),
                                 comparator_only=sorted(ss[m]-ss['obligation']),net=len(ss['obligation'])-len(ss[m])))
    x.dump(folder/'parent_method_results.json',summaries)
    x.dump(folder/'seed_results.json',seed_results);x.dump(folder/'paired_gain.json',gain)
    with (folder/'resource_curves.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(curves[0]));w.writeheader();w.writerows(curves)
    changed=[p for p,h in x.read(x.OUT/'block_r02/prior_artifact_hashes.json').items() if x.sha(x.ROOT/p)!=h]
    x.dump(folder/'audit.json',dict(passed=not changed,prior_files_changed=changed,actual_queries=len(qs),
        cost_recount=all(q['compile_attempts']==len(q['runs']) for q in qs),model_calls=0,heldout_evaluated=False))
    assert not changed
    lines=['# r02 实际复核与隔离执行实验','',
        '候选全文与 r01 相同。唯一执行器变更：逐候选权限/语法门控后批量执行可支持的子集，不支持候选继续记未知。此为开发复核，不是独立泛化。',
        '', '| 父案例 | 普通缺口 | 分歧缺口 | 义务缺口 | 普通/分歧/义务区分对数 |', '|---|---:|---:|---:|---|']
    for k in x.IDS:
        rs=[next(s for s in summaries if s['case']==k and s['method']==m) for m in methods]
        lines.append(f"| {k} | {rs[0]['gap_count']} | {rs[1]['gap_count']} | {rs[2]['gap_count']} | {' / '.join(str(s['pair_count']) for s in rs)} |")
    lines+=['','每格36次实际输入查询（3种子×12），每次24拍、双RTL；错误也收费。缺口按候选×FP/FN×义务去重，FP仅计一次 legal_prefix；不能解释为独立bug数。',
        'filter为补充自然候选，spill只确认valid清空部分，intr未决。未发现反例不表示通过。双方有缺陷不排序，未确认事务归属的报警不算命中。',
        '', '原始查询及波形：../search/queries.jsonl 与 ../runs/search；逐种子差集：paired_gain.json；资源曲线：resource_curves.csv；历史完整性：audit.json。',
        '原生SVA支持情况见 ../baseline/native_sva/capability.json。上述执行是过程checker加独立规格监视器。',
        '第3、4项另立实验区块，未运行时不得据此报告改善。']
    (folder/'REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(dict(queries=len(qs),costs={n:sum(q[n] for q in qs) for n in ('compile_attempts','simulation_attempts','wall_seconds','cpu_seconds')},report=x.rel(folder/'REPORT.md'))))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);p.add_argument('action',choices=['init','search','report'])
    a=p.parse_args();x.OUT=x.ROOT/'deliverables'/a.run;globals()[a.action]()
