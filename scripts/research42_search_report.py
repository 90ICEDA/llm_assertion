"""Read-only search audit/report plus separately predeclared coverage-only control.

The control has no oracle/trace feedback; it tests whether the contract policy's
observed gain can be explained by a plain predeclared duration coverage sweep.
"""
import argparse
import random
import time
from collections import Counter
from pathlib import Path
import research42_search as search
from research17_report import artifacts, cost_audit

read,dump=search.read,search.dump
SWEEP='coverage_sweep'


def sweep_choice(method,query,rng,history):
    assert method==SWEEP
    return (0,1,4,16)[query]


def prepare_sweep(out):
    search.prepare(out)
    protocol=read(out/'protocol.json')
    protocol.update(methods=[SWEEP],diagnostic_only=True,
        information_views={SWEEP:'Query index only; no waveforms, candidate verdicts, oracle or scoring.'},
        policies={SWEEP:'Fixed duration sweep q0/1/2/3 = 0/1/4/16, set before main native search.'},
        accounting='12 queries, six fresh native executions each; separate two compiles/two smoke. No cache.',
        diagnostic_code_sha256=search.digest(Path(__file__)),
        purpose='Negative control for incremental contract semantic value beyond simple duration coverage. Same sweep as public contract buckets; no claim of unseen policy selection.')
    dump(out/'protocol.json',protocol)
    hashes={str(p.relative_to(out)):search.digest(p) for p in out.rglob('*')
            if p.is_file() and p.name not in ('prepared_hashes.json','outcome.json')}
    dump(out/'prepared_hashes.json',hashes)


def run_sweep(out):
    assert read(out/'protocol.json')['diagnostic_code_sha256']==search.digest(Path(__file__))
    old_methods,old_choose=search.METHODS,search.choose
    search.METHODS=(SWEEP,);search.choose=sweep_choice
    try: search.run(out)
    finally: search.METHODS,search.choose=old_methods,old_choose


def exposed_inputs(run,sweep,out):
    out.mkdir(parents=True,exist_ok=False)
    entries=[]
    for source in (run,sweep):
        if source is None:continue
        for r in read(source/'results.json'):
            p=source/'queries'/f's{r["seed"]}'/r['method']/f'q{r["query"]}'/'initial/correct_stimulus/stimulus.json'
            rows=read(p)
            entries.append(dict(path=str(p),rows_sha256=search.loop.sha(rows),
                seed=r['seed'],method=r['method'],query=r['query'],split='development'))
    dump(out/'exposed_inputs.json',entries)
    dump(out/'manifest.json',dict(entries=len(entries),distinct_inputs=len({e['rows_sha256'] for e in entries}),
        sha256=search.digest(out/'exposed_inputs.json'),scope='All executed main and coverage-control queries, including repeats and failures; no independent tests.'))
    print(read(out/'manifest.json'),flush=True)


def report(run,sweep,out):
    out.mkdir(parents=True,exist_ok=False)
    records=read(run/'results.json'); checks=[]
    def check(name,okay,**extra):checks.append(dict(name=name,passed=bool(okay),**extra))
    methods=search.METHODS
    sources=[run]
    if sweep:
        records+=read(sweep/'results.json');methods=(*methods,SWEEP);sources.append(sweep)
    for source in sources:
        protocol=read(source/'protocol.json');frozen=read(source/'prepared_hashes.json')
        check(str(source.name)+':terminal',read(source/'outcome.json')['status']=='native_search_completed')
        check(str(source.name)+':all_prepared_content_preserved',all(search.digest(source/p)==h for p,h in frozen.items()))
        check(str(source.name)+':two_distinct_candidates',search.loop.sha(read(source/'candidates/initial.json'))!=search.loop.sha(read(source/'candidates/repaired.json')))
        check(str(source.name)+':fixed_initial',protocol['candidates']['initial']['hash']==search.loop.sha(read(search.SOURCES['initial'])))
    summaries=[]
    for seed in search.SEEDS:
        keys={m:{key for r in records if r['seed']==seed and r['method']==m for key in r['independent_gap_keys']} for m in methods}
        entries={}
        for method in methods:
            rr=[r for r in records if r['seed']==seed and r['method']==method]
            check(f'{seed}:{method}:four_queries',len(rr)==4 and [r['query'] for r in rr]==list(range(4)))
            history=[];rng=random.Random(seed);seen=set(); first={};duplicates=0;repeatqueries=0
            exposed_checks=Counter();real_targets=set();triggered_obligations=set()
            for r in rr:
                q=r['query'];selection=(sweep if method==SWEEP else run)/'queries'/f's{seed}'/method/f'q{q}'/'selection.json'
                selected=read(selection)
                expected=sweep_choice(method,q,rng,history) if method==SWEEP else search.choose(method,q,rng,history)
                check(f'{seed}:{method}:{q}:policy_replay',r['duration']==expected and selected['permitted_history']==history)
                # Sweep currently receives a generic stored score view, but its chooser
                # explicitly only reads q; keep that fact distinct from access claims.
                allowed={'duration'} if method=='ordinary' else {'duration','maximum_stall'} if method=='contract_coverage' else {'duration','score'}
                check(f'{seed}:{method}:{q}:no_judge_feedback',set(r['permitted_view'])<=allowed)
                history.append(r['permitted_view'])
                check(f'{seed}:{method}:{q}:native_health',r['healthy'])
                check(f'{seed}:{method}:{q}:validated_misses',all(g['validation']['valid'] and all(g['validation']['conditions'].values()) for g in r['gaps']))
                query_folder=selection.parent
                control=read(query_folder/'initial/correct/replay.json')
                exposed_checks.update(c['obligation'] for c in control['oracle']['checks'])
                for g in r['gaps']:
                    real_targets.add(g['evidence']['obligation'])
                    if any(a['trigger'] for a in g['evidence']['native']['assertions']):
                        triggered_obligations.add(g['evidence']['obligation'])
                new=set(r['independent_gap_keys'])-seen
                if r['independent_gap_keys'] and not new:repeatqueries+=1
                for g in r['gaps']:
                    if g['key'] in seen:duplicates+=1
                    else:first[g['key']]=q
                    seen.add(g['key'])
            entries[method]=dict(unique_gap_count=len(keys[method]),gap_keys=sorted(keys[method]),
                first_discovery_query=first,durations=[r['duration'] for r in rr],
                duplicate_gap_observations=duplicates,repeated_gap_queries=repeatqueries,
                queries=4,native_executions=sum(r['native_executions'] for r in rr),
                gap_observations=sum(len(r['gaps']) for r in rr),
                false_positives=sum(len(r['false_positive_rows']) for r in rr),
                current_unknown=sum(r['unknown'] for r in rr),
                later_attribution_unknown=sum(r['later_attribution_unknown'] for r in rr),
                trigger_classes=dict(Counter(g['validation']['trigger_class'] for r in rr for g in r['gaps'])),
                ledger_obligation_projections=sorted({ob for r in rr for ob in r['covered_obligations']}),
                actual_correct_side_obligation_check_counts=dict(exposed_checks),
                confirmed_fault_obligations=sorted(real_targets),
                confirmed_gap_triggered_obligations=sorted(triggered_obligations),
                coverage_scope='Generic ledger projections are NOT proof of applicability or complete protection; actual oracle check counts and confirmed fault obligations are separate.',
                contract_extra_vs_this=sorted(keys['contract_coverage']-keys[method]),
                this_extra_vs_contract=sorted(keys[method]-keys['contract_coverage']))
        summaries.append(dict(seed=seed,methods=entries))
        if sweep:
            cc=[r for r in records if r['seed']==seed and r['method']=='contract_coverage']
            ss=[r for r in records if r['seed']==seed and r['method']==SWEEP]
            check(f'{seed}:coverage_control_identical_exposure',
                [r['duration'] for r in cc]==[r['duration'] for r in ss])
            check(f'{seed}:coverage_control_identical_gap_set',keys['contract_coverage']==keys[SWEEP])
        common=[]
        for method in methods:
            source=sweep if method==SWEEP else run
            schedule=read(source/'queries'/f's{seed}'/method/'q0/initial/correct_stimulus/stimulus.json')
            common.append(search.loop.sha(schedule))
        check(f'{seed}:common_initial_query_identical',len(set(common))==1)
    union={m:{key for r in records if r['method']==m for key in r['independent_gap_keys']} for m in methods}
    comparisons={m:dict(unique_gap_count=len(union[m]),gap_keys=sorted(union[m]),
        contract_extra=sorted(union['contract_coverage']-union[m]),baseline_extra=sorted(union[m]-union['contract_coverage'])) for m in methods}
    costs={source.name:cost_audit(source,artifacts(source)) for source in sources}
    for source,cost in costs.items():
        total=cost['total'];is_sweep=source==getattr(sweep,'name',None)
        check(source+':physical_cost',total['native_compile_calls']==2 and total['native_execute_calls']==(74 if is_sweep else 290) and total['model_calls']==0)
    examples=[]
    for mode in search.extension.MODES:
        g=next((g for r in records if r['method']=='contract_coverage' for g in r['gaps'] if g['case']['mode']==mode),None)
        if g:examples.append(g)
    result=dict(status='completed',seeds=list(search.SEEDS),per_seed=summaries,union=comparisons,
        checks=checks,all_checks_passed=all(c['passed'] for c in checks),
        scope='One known FIFO candidate pair and two artificial long-stall mechanisms; all data development. Repeated seeds/waves are not independent bugs. Later attribution unknown retained; no formal proof.',
        cost_files={k:str(out/'cost'/f'{k}.json') for k in costs})
    dump(out/'results.json',result);dump(out/'case_examples.json',examples)
    for name,cost in costs.items():dump(out/'cost'/f'{name}.json',cost)
    dump(out/'verification.json',dict(checks=checks,all_passed=result['all_checks_passed']))
    lines=['# research42 公平搜索复测','',
        '固定一个历史模型候选对、3 个预定种子、每方法每种子 4 查询、112 拍。全部结果属于开发数据。',
        '普通/候选分歧/原始差分策略不读取事务 oracle；契约策略只使用自身正确侧连续背压曝光。诊断对照按固定时长扫过同样的边界，不使用反馈。',
        '', '| 种子 | 普通 | 候选对分歧 | 原始差分 | 契约曝光 | 固定覆盖对照 |','|---|---:|---:|---:|---:|---:|']
    for entry in summaries:lines.append('| '+str(entry['seed'])+' | '+' | '.join(str(entry['methods'][m]['unique_gap_count']) for m in methods)+' |')
    lines+=['','按候选哈希/义务/故障机制跨种子去重，并集为：'+', '.join(f'{m}={len(union[m])}' for m in methods)+'。',
        '每种子的首次发现查询、重复观察、互相新增集合和 unknown 见 results.json；完整请求接受、响应、参考队列、原生触发及波形见每条 case 的 source 路径。',
        '', '## 解释与限制','',
        '本轮复测已知长背压人工故障族，公开覆盖策略与该故障族具有先验相关性，不能宣称发现新的硬件 Bug。若契约与固定覆盖对照相同，则当前增益可由覆盖调度解释，不能归因于契约语义特有优势。',
        '两种故障分别在长背压期间和解除边界撤销 valid。初始集合仅保持数据，原生 cover 触发仍可能没有 valid 约束；这与不触发必须分开记录。',
        'correct RTL 与故障输出包装使用相同被接受输入，由独立端口历史队列判断义务，不能仅用波形不同或候选差异证明功能错误。',
        '', '## 实际成本','']
    for name,cost in costs.items():
        t=cost['total'];lines.append(f'- {name}: 原生编译 {t["native_compile_calls"]}，执行 {t["native_execute_calls"]}（含 {t["compile_smoke_execute_calls"]} 次冒烟），模型/形式化 0。')
    lines+=['',f'审计通过 {sum(c["passed"] for c in checks)}/{len(checks)}。审计仅验证记录一致性。',
        '', '复现命令（请使用新目录）：','```powershell',
        'wsl -- python3 scripts/research42_search.py prepare --out deliverables/research42_search_NEW',
        'wsl -- python3 scripts/research42_search_report.py prepare-sweep --out deliverables/research42_search_sweep_NEW',
        'wsl -- python3 scripts/research42_search.py run --out deliverables/research42_search_NEW',
        'wsl -- python3 scripts/research42_search_report.py run-sweep --out deliverables/research42_search_sweep_NEW',
        'wsl -- python3 scripts/research42_search_report.py report --run deliverables/research42_search_NEW --sweep deliverables/research42_search_sweep_NEW --out deliverables/research42_search_report_NEW','```']
    (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(dict(all_checks_passed=result['all_checks_passed'],checks=len(checks),union=comparisons),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('prepare-sweep','run-sweep','exposed-inputs','report'))
    p.add_argument('--out',type=Path,required=True);p.add_argument('--run',type=Path);p.add_argument('--sweep',type=Path)
    a=p.parse_args();out=a.out.resolve();assert search.ROOT in out.parents
    if a.action=='prepare-sweep':prepare_sweep(out)
    elif a.action=='run-sweep':run_sweep(out)
    elif a.action=='exposed-inputs':exposed_inputs(a.run.resolve(),a.sweep.resolve() if a.sweep else None,out)
    else:report(a.run.resolve(),a.sweep.resolve() if a.sweep else None,out)
