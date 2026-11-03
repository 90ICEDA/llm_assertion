"""Append-only evidence-search experiment, independent of historical output dirs.

python3 scripts/run_obligation_evidence.py --run RUN {prepare,baseline,search,report}
Each action is exclusive; repeats require a new RUN. No model is called here.
"""
import argparse
import collections
import copy
import hashlib
import itertools
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import urllib.request

import run_repair_contract as engine
import contract_v3_checker as checker
import contract_v3_qualify as qualify
from contract_v2_spec import definition, contract, IDS
from obligation_evidence_monitor import monitor, evidence, check_inputs
import obligation_search_policy as policy

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT / 'deliverables/repair_contract_v3_20261010'
LEGACY = ROOT / 'deliverables/repair_contract_20261009'
read = engine.read
sha = engine.sha
rel = lambda p: str(Path(p).relative_to(ROOT)).replace('\\', '/')
OUT = None


def dump(p, x):
    p = Path(p); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(x, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def digest(x):
    return hashlib.sha256(json.dumps(x, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def append(p, x):
    with p.open('a', encoding='utf-8') as f: f.write(json.dumps(x, ensure_ascii=False) + '\n')


def command(argv, folder, name, timeout=45):
    return engine.command(argv, folder, name, timeout)


def snapshot(p):
    target = OUT / 'source_snapshot' / rel(p)
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists(): shutil.copy2(p, target)
    return dict(source=rel(p), snapshot=rel(target), sha256=sha(p))


def prepare():
    OUT.mkdir(parents=True, exist_ok=False)
    manifest = []
    for p in [*ROOT.joinpath('scripts').glob('*contract*.py'), ROOT/'README.md',
              Path(__file__), ROOT/'scripts/obligation_evidence_monitor.py', ROOT/'scripts/obligation_search_policy.py',
              OLD/'parent_results.json', OLD/'conditional_results.json', OLD/'hidden_evaluations.json',
              LEGACY/'collision_pairs.json']:
        manifest.append(snapshot(p))
    parents = read(OLD/'parent_results.json')
    pairs = read(LEGACY/'collision_pairs.json')
    counts = dict(collections.Counter('unknown' if r['unknown'] else 'pass' if r['complete_pass'] else 'failure' for r in parents))
    focused = [p for p in pairs if p['natural_pair'] and p['status']=='distinguished_on_checked_legal_inputs']
    dump(OUT/'lineage.json', dict(parent_count=len(IDS), method_parent_cells=len(parents), counts=counts,
        pairs_total=len(pairs), pairs_natural=sum(p['natural_pair'] for p in pairs), focused_pairs=len(focused),
        meaning='40 problematic method-parent cells in v3; 11 previously distinguished pairs from 25 v1 pairs; separate cohorts, not a one-to-one mapping',
        no_history_claim=True, git='no usable HEAD'))
    dump(OUT/'pairs_frozen.json', pairs)
    for k in IDS:
        folder = OUT/'frozen'/k
        d = read(OLD/'frozen'/k/'definition.json')
        dump(folder/'definition.json', d)
        c = contract(k)
        c.update(generator_visibility='only public_contract.json; reference implementation/answers never transmitted',
                 acceptance='All necessary obligations, legal negative controls and reachable target branches required. Any unresolved specification or checker status prevents whole-parent pass.',
                 full_functional_correctness_claim=False)
        sources = []
        for name in c['sources']:
            p=ROOT/name
            if p.exists():
                manifest.append(snapshot(p)); sources.append(dict(path=name, sha256=sha(p), numbered_text=[f'{i}: {s}' for i,s in enumerate(p.read_text().splitlines(),1)]))
        dump(folder/'spec_sources.json', sources)
        dump(folder/'contract.json', c)
        dump(folder/'public_contract.json', {n:c[n] for n in ['text','legal_inputs','reset_cancellation','parameters','status','target_scope']})
        for variant in ['correct','buggy']:
            p=OLD/'frozen'/k/(variant+'.v'); shutil.copy2(p,folder/(variant+'.v'));manifest.append(snapshot(p))
        # Old Qwen3 natural pool stays separate from filter's v2 natural model pool.
        cs=[z for z in engine.natural(k) if z['provenance']=='legacy_natural_model_output']
        cohort='legacy_qwen3_slots_01_07'
        if not cs:
            cs=read(OLD/'frozen'/k/'model_pool_v2.json');cohort='supplemental_v2_model_pool_no_legacy_pairs'
        for z in cs:
            z['authorized_history_depth']=0
            if 'evidence' in z: manifest.append(snapshot(ROOT/z['evidence']))
        dump(folder/'candidates.json',dict(cohort=cohort,candidates=cs,text_hashes=[digest(z) for z in cs]))
        # Quarantine is prepared before search. Not evaluated by this script.
        hidden = [policy.ordinary(d, 91261013+i*719+list(IDS).index(k)) for i in range(3)]
        dump(OUT/'quarantine'/k/'inputs.json',hidden)
    versions={}
    for cmd in [['python3','--version'],['iverilog','-V'],['vvp','-V'],['yosys','-V'],['ollama','--version']]:
        versions[cmd[0]]=command(cmd,OUT,'version_'+cmd[0],15)
    t=time.perf_counter()
    try:
        tags=json.load(urllib.request.urlopen('http://127.0.0.1:11434/api/tags',timeout=5))
        model=dict(status='service_available',tags=tags,generation_verified=False)
    except Exception as exc:model=dict(status='service_unavailable',error=repr(exc),generation_verified=False)
    model['wall_seconds']=time.perf_counter()-t;dump(OUT/'model_access.json',model)
    protocol=dict(version=1, created_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),seeds=[3113,3119,3121],
        methods=['ordinary','disagreement','obligation'], queries_per_parent_seed_method=12, cycles_per_query_variant=24,
        query_unit='One submitted 24-cycle input schedule evaluated on BOTH frozen RTL variants and the entire frozen candidate pool. Every submitted attempt, including invalid/error/timeout, consumes one query; no retries or outcome-dependent stopping.',
        charges='Two physical compiles and simulations per valid query; batched candidate checks separately counted by candidate x variant and active samples. No solver, no cache, no free pre-screen or offline candidate evaluation.',
        shared_preflight='baseline/qualification/old signature replay separately costed, never charged to arm and never used to tune search',
        ordinary='24-cycle seeded random width-correct stimuli, 0.4 hold probability, 0.06 reset probability; only environment legality constraints; four-cycle drain',
        disagreement='same initial ordinary draw; retain input with largest sum of candidate-pair per-cycle fail XOR; six seeded field mutations; explore fresh random at steps divisible by three; no oracle/obligation labels',
        obligation='round-robin public obligation templates, random legal idle spacing, FIFO stable-data backpressure, stat overlapping/captured-data episodes and explicit reset-cancellation subexperiments; no acceptance feedback used',
        attribution='Reference oracle first; FP only on legal reset-to-sample prefixes. FN only when candidate accepts complete prefix to first definite violation. Alarm/violation coincidence never counts as independently attributed detection.',
        dedup='Exact reset-to-evidence input+output prefix, obligation identities, kind, candidate text hash; cross-query ids excluded. Distinct traces are not independent bugs.',
        scope='Finite search on six synthetic parent bugs. Intr results conditional/unknown, spill common collision_empty only. Filter supplemental natural cohort reported separately.',
        fair_comparison='Same frozen candidate pool, input cycle cap, seeds and attempted query budget. CPU/wall costs also reported. No claim algorithms exhaust their design spaces.',
        stage3='not executed by this runner; historical eight arms do not implement requested A/B/C/D exactly',
        stage4='quarantine frozen now; no final revised assertion set yet, not evaluated',versions=versions)
    dump(OUT/'protocol.json',protocol)
    perturbations={
        'idle':dict(basis='No ready/spacing restrictions in stat/spill specs; FIFO environment contract; filter same-value samples count toward qualification', preserved='transaction payload/order for isolated stat events', changed='absolute deadlines remain relative to triggers; filter repeated values change qualification and are not stutter equivalent'),
        'backpressure':dict(basis='Depth=0 FIFO input contract: hold push/data until pop or reset',precondition='push and not pop',preserved='presented item/data',changed='acceptance time; no arbitrary backpressure for interfaces with no ready port'),
        'reset':dict(basis='active-low reset in source module contracts',precondition='reset explicitly asserted',preserved='no pre-reset obligation crosses epoch',changed='cancels pending transaction; not behavior-preserving equivalence')}
    dump(OUT/'perturbations.json',perturbations)
    dump(OUT/'source_manifest.json',manifest)
    paths=[p for p in (OUT/'frozen').rglob('*') if p.is_file()]+[p for p in (OUT/'quarantine').rglob('*') if p.is_file()]+[OUT/'protocol.json',OUT/'pairs_frozen.json',OUT/'perturbations.json',Path(__file__),ROOT/'scripts/obligation_evidence_monitor.py',ROOT/'scripts/obligation_search_policy.py']
    dump(OUT/'freeze.json',{rel(p):sha(p) for p in paths})
    print(json.dumps(read(OUT/'lineage.json')))


def guard():
    assert all(sha(ROOT/p)==h for p,h in read(OUT/'freeze.json').items()), 'frozen input changed; start a new run'


def parse_stdout(p):
    trace=[];checks=collections.defaultdict(list)
    for line in p.read_text().splitlines():
        if line.startswith('TRACE '):
            parts=line.split(); row={'cycle':int(parts[1])}
            for item in parts[2:]:
                n,v=item.split('=');row[n]=int(v) if re.fullmatch(r'-?\d+',v) else None
            trace.append(row)
        if line.startswith('CHECK '):
            _,j,t,a,f=line.split();checks[int(j)].append(dict(cycle=int(t),trigger=int(a) if a.isdigit() else None,fail=int(f) if f.isdigit() else None))
    return trace,checks


def adjudicate_folder(folder, d):
    trace,checks=parse_stdout(folder/'simulate.stdout')
    inp=read(folder/'input.json')
    complete=len(trace)==len(inp) and all(v is not None for row in trace if row[d['rst']] for v in row.values())
    cs=read(folder/'candidates.json')
    active=[r['cycle'] for r in trace if r[d['rst']]]
    complete &= all([r['cycle'] for r in checks[j]]==active and all(r['fail'] is not None and r['trigger'] is not None for r in checks[j]) for j in range(len(cs)))
    if not complete:return dict(status='checker_or_trace_unknown')
    oracle=monitor(d,trace)
    dump(folder/'independent_reference.json',oracle)
    ev=[evidence(d,trace,checks[j],oracle) for j in range(len(cs))]
    dump(folder/'independent_evidence.json',ev)
    dump(folder/'trace.json',trace)
    for j in range(len(cs)):dump(folder/f'checker_{j}_cycles.json',checks[j])
    return dict(status='ok', evidence=ev, pending=oracle['pending'], reference=rel(folder/'independent_reference.json'),
                valid_scoped_prefix=all(x['legal_prefix'] for x in oracle['events']),
                sim_cycles=len(trace),candidate_cycle_evaluations=len(active)*len(cs),candidate_variant_evaluations=len(cs))


def replay_one(source, target):
    target.mkdir(parents=True,exist_ok=False)
    for name in ['rtl.v','checker_tb.sv','input.json','candidates.json','definition.json','assertions.sva']:
        if (source/name).exists():shutil.copy2(source/name,target/name)
    old=read(source/'result.json')
    argv=old['compile']['argv']
    b=command(argv,target,'compile')
    s=command(['vvp','sim.out'],target,'simulate',15) if b['status']=='ok' and old.get('simulate') else None
    result=dict(source=rel(source),compile=b,simulate=s,original_status=old['status'],
                status=s['status'] if s else b['status'], old_run_id=old['run_id'],
                candidates_sha256=sha(target/'candidates.json'), checker_sha256=sha(target/'checker_tb.sv'))
    if s and s['status']=='ok':
        records=lambda p:sorted(l for l in p.read_text().splitlines() if l.startswith(('TRACE ','CHECK ')))
        result['identical_trace_check_records']=records(target/'simulate.stdout')==records(source/'simulate.stdout')
        result.update(adjudicate_folder(target,read(target/'definition.json')))
    elif old['status']!='ok':result['status']=old['status'];result['recheck_note']='raw compile outcome retained separately; original permission rejection retained'
    import shlex
    (target/'reproduce.sh').write_text('#!/bin/sh\nset -eu\ncd '+shlex.quote(str(target))+'\n'+shlex.join(argv)+'\nvvp sim.out\n')
    dump(target/'replay.json',result)
    return result


def baseline():
    guard();(OUT/'baseline').mkdir(exist_ok=False)
    # Existing hand-authored checker tests rerun into this run, not old artifacts.
    qualify.OUT=OUT/'baseline'; qualify.qualify()
    # Native concurrent SVA is an explicit capability probe, not a procedural pass.
    folder=OUT/'baseline/native_sva';folder.mkdir()
    (folder/'probe.sv').write_text('module tb; reg clk=0,a=0,b=0; always #5 clk=~clk; assert property (@(posedge clk) a |=> b); initial #30 $finish; endmodule\n')
    native=command(['iverilog','-g2012','-s','tb','-o','probe.out','probe.sv'],folder,'compile')
    dump(folder/'capability.json',dict(native_sva_available=native['status']=='ok',result=native,limitation='Only Icarus procedural monitor is used in experiments. This syntax probe cannot certify full native SVA semantics.'))
    conditional=read(OLD/'conditional_results.json')
    paths=sorted(set(z['run'] for r in conditional for z in r['runs']))
    mapping={}
    for i,name in enumerate(paths):
        target=OUT/'baseline/replays'/digest(name)[:20]
        result=replay_one(ROOT/name,target);result['new_run']=rel(target)
        mapping[name]=result
        append(OUT/'baseline/replay_index.jsonl',result)
        if i%20==0:print('BASELINE',i+1,len(paths),flush=True)
    dump(OUT/'baseline/replay_mapping.json',mapping)
    ledger=[]
    for p in read(OLD/'parent_results.json'):
        if p['complete_pass'] is True:continue
        k=p['case'];method=p['method'];final=read(OLD/'methods'/k/method/'final.json');candidate=final['candidate']
        cc=[c for c in conditional if c['case']==k and c['method']==method]
        runs=sorted(set(z['run'] for c in cc for z in c['runs']))
        refs=[];findings=[]
        for run in runs:
            m=mapping[run];refs.append(dict(original=run,replay=m['new_run'],status=m['status'],exact=m.get('identical_trace_check_records')))
            for group in m.get('evidence',[]):
                for ev in group:
                    if ev['kind'] in ['miss','false_positive']:findings.append(dict(**ev,run=m['new_run']))
        categories=[]
        if any(f['kind']=='miss' for f in findings):categories.append('candidate_omits_required_obligation')
        if any(f['kind']=='false_positive' for f in findings):categories.append('candidate_rejects_scoped_legal_behavior')
        if k=='stat' and any(f['kind']=='miss' and any(c['obligation']=='valid_latency' for c in f['obligations']) for f in findings):categories.append('timing_error')
        if any(m['status']!='ok' for m in refs):categories.append('checker_or_execution_problem')
        if k in ['spill','intr']:categories.append('specification_ambiguity')
        if not categories:categories.append('budget_or_evidence_insufficient')
        original='unknown' if p['unknown'] else 'known_failure'
        ledger.append(dict(record_id='CELL-'+digest([k,method])[:16],parent_bug=IDS[k],case=k,method=method,
            candidate_id=candidate['id'],candidate=candidate,candidate_content_sha256=digest(candidate),
            original_status=original,original_record=p,original_final=rel(OLD/'methods'/k/method/'final.json'),
            original_run_ids=runs, replays=refs, specification=rel(OUT/'frozen'/k/'spec_sources.json'),
            obligations=rel(OUT/'frozen'/k/'contract.json'), categories=categories,findings=findings,
            reclassified_status='unknown_full_contract' if k in ['spill','intr'] or any(m['status']!='ok' for m in refs) else 'confirmed_scoped_failure' if findings else 'unresolved',
            confidence='high for concrete replayed prefix; full-contract unknown retained',
            minimal_repro_status='shortest observed failing prefix; minimization is separate',
            initialization='two low-reset samples; see each input.json for subsequent reset; pre-NBA sampling',
            reproduce='sh <replay directory>/reproduce.sh',
            actual_cost=dict(physical_replay_shared=True,cost_index=rel(OUT/'baseline/replay_index.jsonl'),original_cost=p),
            unresolved=['No proof outside saved finite traces','Candidate alarm attribution not inferred from fail-hit',*(['spec needs owner resolution'] if k in ['spill','intr'] else [])]))
    dump(OUT/'problem_ledger.json',ledger)
    dump(OUT/'baseline/summary.json',dict(runs=len(mapping),identical=sum(m.get('identical_trace_check_records') is True for m in mapping.values()),
        mismatches=[k for k,m in mapping.items() if m.get('identical_trace_check_records') is False],statuses=dict(collections.Counter(m['status'] for m in mapping.values())),
        cells=len(ledger),original_states=dict(collections.Counter(x['original_status'] for x in ledger)),
        reclassified=dict(collections.Counter(x['reclassified_status'] for x in ledger))))
    print(json.dumps(read(OUT/'baseline/summary.json')))


def search():
    guard();(OUT/'search').mkdir(exist_ok=False)
    assert not read(OUT/'baseline/summary.json')['mismatches']
    engine.OUT=OUT
    engine.tb_text=checker.tb_text
    engine.sources=lambda d:(OUT/'frozen'/d['key']/'correct.v',OUT/'frozen'/d['key']/'buggy.v')
    protocol=read(OUT/'protocol.json')
    for k in IDS:
        d=read(OUT/'frozen'/k/'definition.json');pool=read(OUT/'frozen'/k/'candidates.json');cs=pool['candidates']
        for seed in protocol['seeds']:
            for method in protocol['methods']:
                incumbent=None;best=-1
                for step in range(protocol['queries_per_parent_seed_method']):
                    start=time.perf_counter();qseed=seed+step*1009
                    if method=='ordinary':rows=policy.ordinary(d,qseed)
                    elif method=='disagreement':rows=policy.disagreement(d,qseed,incumbent if step%3 else None)
                    else:rows=policy.guided(d,qseed,step)
                    qid=f'{k}/{seed}/{method}/{step:02d}'
                    q=dict(query_id=qid,case=k,parent_bug=IDS[k],seed=seed,method=method,step=step,attempted_queries=1,
                           input_content_sha256=digest(rows),cohort=pool['cohort'],cache_hits=0,retries=0,solver_calls=0,
                           model_calls=0,compile_attempts=0,simulation_attempts=0,sim_cycles=0,candidate_cycle_evaluations=0,candidate_variant_evaluations=0,
                           status='pending',runs=[],evidence=[],disagreement_score=0)
                    invalid=check_inputs(d,rows)
                    if invalid:q.update(status='invalid_input',errors=invalid)
                    else:
                        for variant in ['correct','buggy']:
                            label=f'search/{qid}'
                            raw=engine.execute_run(d,rows,cs,label,variant)
                            folder=ROOT/raw['run_id'];q['compile_attempts']+=1;q['simulation_attempts']+=int(raw['simulate'] is not None)
                            result=adjudicate_folder(folder,d) if raw['status']=='ok' else dict(status=raw['status'])
                            dump(folder/'adjudication.json',result);q['runs'].append(dict(run=rel(folder),variant=variant,status=result['status'],validation_wall_seconds=raw['validation_wall_seconds']))
                            for name in ['sim_cycles','candidate_cycle_evaluations','candidate_variant_evaluations']:q[name]+=result.get(name,0)
                            if result['status']=='ok':
                                tr=read(folder/'trace.json')
                                checks=[read(folder/f'checker_{j}_cycles.json') for j in range(len(cs))]
                                # Candidate disagreements drive only the disagreement policy.
                                q['disagreement_score']+=sum(sum(a['fail']!=b['fail'] for a,b in zip(checks[i],checks[j])) for i,j in itertools.combinations(range(len(cs)),2))
                                for j,evs in enumerate(result['evidence']):
                                    for ev in evs:
                                        if ev['kind'] not in ['miss','false_positive']:continue
                                        # Epoch prefix is the evidence identity; paths/stimulus IDs are excluded.
                                        t=ev['cycle'];reset=max(i for i in range(t+1) if not tr[i][d['rst']])
                                        prefix=[{n:v for n,v in r.items() if n!='cycle'} for r in tr[reset:t+1]]
                                        ed=dict(**ev,candidate_id=cs[j]['id'],candidate_sha256=digest(cs[j]),run=rel(folder),variant=variant,
                                                prefix_sha256=digest(prefix),scope='common_spill_validity_only' if k=='spill' else 'resolved_target_contract')
                                        ed['evidence_id']=digest([k,ed['candidate_sha256'],ev['kind'],[c['obligation'] for c in ev['obligations']],prefix])
                                        q['evidence'].append(ed)
                        q['status']='ok' if all(r['status']=='ok' for r in q['runs']) else 'execution_unknown'
                    q['wall_seconds']=time.perf_counter()-start
                    append(OUT/'search/queries.jsonl',q)
                    if method=='disagreement' and q['disagreement_score']>best:best=q['disagreement_score'];incumbent=rows
                print('SEARCH',k,seed,method,flush=True)


def report():
    ledger=read(OUT/'problem_ledger.json');qs=[json.loads(s) for s in (OUT/'search/queries.jsonl').read_text().splitlines()]
    summaries=[]
    for k in IDS:
        for method in ['ordinary','disagreement','obligation']:
            rows=[q for q in qs if q['case']==k and q['method']==method]
            evs=[e for q in rows for e in q['evidence']]
            gaps=set((e['candidate_id'],e['kind'],c['obligation']) for e in evs for c in e['obligations'] if not c.get('conditional') and (e['kind']=='false_positive' or not c['passed']))
            # False positives with no triggered reference obligation still count as legal-prefix rejection.
            gaps|={(e['candidate_id'],'false_positive','legal_prefix') for e in evs if e['kind']=='false_positive'}
            summaries.append(dict(case=k,parent_bug=IDS[k],method=method,seeds=len(set(q['seed'] for q in rows)),
                queries=len(rows),compile_attempts=sum(q['compile_attempts'] for q in rows),simulation_attempts=sum(q['simulation_attempts'] for q in rows),
                cycles=sum(q['sim_cycles'] for q in rows),candidate_cycle_evaluations=sum(q['candidate_cycle_evaluations'] for q in rows),
                wall_seconds=sum(q['wall_seconds'] for q in rows),statuses=dict(collections.Counter(q['status'] for q in rows)),
                raw_evidence=len(evs),unique_evidence=len(set(e['evidence_id'] for e in evs)),candidate_obligation_gaps=len(gaps),gaps=sorted(gaps),
                definite_fp_candidates=sorted(set(e['candidate_id'] for e in evs if e['kind']=='false_positive')),
                definite_miss_candidates=sorted(set(e['candidate_id'] for e in evs if e['kind']=='miss')),
                full_parent_pass='not_established',spec_unknown=k in ['spill','intr']))
    dump(OUT/'search/parent_method_results.json',summaries)
    paired=[]
    for p in read(OUT/'pairs_frozen.json'):
        if not p['natural_pair']:continue
        k=next(k for k,v in IDS.items() if v==p['parent_bug_id'])
        for method in ['ordinary','disagreement','obligation']:
            es=[e for q in qs if q['case']==k and q['method']==method for e in q['evidence']]
            defects={cid:sorted(set(e['kind'] for e in es if e['candidate_id']==cid)) for cid in [p['a'],p['b']]}
            signatures={cid:set((e['prefix_sha256'],e['kind']) for e in es if e['candidate_id']==cid) for cid in [p['a'],p['b']]}
            diff=signatures[p['a']]^signatures[p['b']]
            paired.append(dict(pair_id=p['pair_id'],case=k,method=method,focused_11=p['status']=='distinguished_on_checked_legal_inputs',
                a=p['a'],b=p['b'],defects=defects,distinguished=bool(diff),quality_order='unranked_both_defective' if all(defects.values()) else 'unranked_incomplete_coverage',
                scope='Different independently accepted witness sets; no whole-candidate correctness ordering',
                witnesses=[e for e in es if e['candidate_id'] in defects and (e['prefix_sha256'],e['kind']) in diff][:4]))
    dump(OUT/'search/pair_results.json',paired)
    parent_counts=[]
    for k in IDS:
        pp=[p for p in read(OLD/'parent_results.json') if p['case']==k]
        parent_counts.append(dict(case=k,pass_cells=sum(p['complete_pass'] is True for p in pp),failed_cells=sum(p['complete_pass'] is False and not p['unknown'] for p in pp),unknown_cells=sum(p['unknown'] for p in pp)))
    dump(OUT/'parent_accounting.json',parent_counts)
    lines=['# 义务指导证据搜索：实际运行报告','', '本轮未修改候选。自然旧池与 filter 补充自然池分开；六个父案例均为人工变异。所有数字由原始日志重算。', '',
        '## 统计来源与基线','',json.dumps(read(OUT/'lineage.json'),ensure_ascii=False),'',json.dumps(read(OUT/'baseline/summary.json'),ensure_ascii=False),'',
        '| 父案例 | 原通过单元 | 原失败单元 | 原未知单元 |','|---|---:|---:|---:|']
    for r in parent_counts:lines.append(f"| {r['case']} | {r['pass_cells']} | {r['failed_cells']} | {r['unknown_cells']} |")
    lines+=['','## 冻结候选搜索','', '每父案例每方法三个预定种子，每种子 12 次实际查询。查询包括双 RTL 执行，所有候选批量求值。错误/超时/无效输入也收费；无重试、缓存或求解器调用。', '',
        '| 父案例 | 方法 | 查询 | 编译 | 周期 | 原始/去重证据 | 候选义务缺口 | 秒 |','|---|---|---:|---:|---:|---:|---:|---:|']
    for r in summaries:lines.append(f"| {r['case']} | {r['method']} | {r['queries']} | {r['compile_attempts']} | {r['cycles']} | {r['raw_evidence']}/{r['unique_evidence']} | {r['candidate_obligation_gaps']} | {r['wall_seconds']:.2f} |")
    lines+=['','缺口数按候选 × 义务 × FP/FN 去重，不是独立 bug 数；完整证据另按 reset-to-witness 输入输出前缀去重。无反例不等于正确。spill 仅确认 collision_empty；intr 两解释未决，不并入明确收益。', '',
        '## 未完成和限制','', '第3项 A/B/C/D 新模型细化：未执行。历史八臂不是本次四臂，不替代本次结果。模型访问记录见 model_access.json。',
        '第4项最终断言独立泛化：未执行；quarantine 在搜索前封存，尚未提供给生成器或评估。旧 v3 hidden 已用于诊断，不能再声称是新泛化集。',
        '原生 SVA：见 baseline/native_sva/capability.json；实验使用 Icarus 过程 checker，非形式证明。',
        '所有同拍报警均未计作独立事务命中。候选双方有缺陷时不强行排序。工具故障不归为候选语义失败。', '',
        '## 复现','',f'`python3 scripts/run_obligation_evidence.py --run {OUT.name} report` 从查询日志重建统计；新运行使用新 --run，依次 prepare、baseline、search、report。',
        '每条新运行有 input.json、trace.json、wave.vcd、checker_*_cycles.json、independent_reference.json、independent_evidence.json、编译/仿真命令与 reproduce.sh。',
        '源文件原哈希及副本见 source_manifest.json / source_snapshot；问题台账见 problem_ledger.json；查询成本见 search/queries.jsonl。']
    (OUT/'REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(dict(queries=len(qs),compiles=sum(q['compile_attempts'] for q in qs),statuses=dict(collections.Counter(q['status'] for q in qs)),report=rel(OUT/'REPORT.md'))))


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--run',required=True);ap.add_argument('action',choices=['prepare','baseline','search','report']);args=ap.parse_args()
    assert re.fullmatch(r'[A-Za-z0-9_-]+',args.run)
    OUT=ROOT/'deliverables'/args.run
    globals()[args.action]()
