"""Read-only completion audit of a sealed experiment; new evidence stays separate.

Run with python3 -B scripts/audit_obligation_completion.py --output <new-name>.
No model calls, candidate edits, old-run rewrites, or claims of new search gains.
"""
import argparse
import collections
from concurrent.futures import ThreadPoolExecutor
import datetime
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time

import obligation_evidence_monitor as reference

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'deliverables/obligation_evidence_20261013_r02'
KEYS = ('onehot', 'filter', 'fifo', 'spill', 'stat', 'intr')
METHODS = ('ordinary', 'disagreement', 'obligation')


def read(p):
    return json.loads(Path(p).read_text(encoding='utf-8'))


def lines(p):
    return [json.loads(s) for s in Path(p).read_text(encoding='utf-8').splitlines() if s.strip()]


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def save(p, data):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def relative(p):
    return str(p.relative_to(ROOT))


def gaps(queries):
    found = set()
    for q in queries:
        for e in q['evidence']:
            if e['kind'] == 'false_positive':
                found.add((e['candidate_id'], 'false_positive', 'legal_prefix'))
            elif e['kind'] == 'miss':
                found.update((e['candidate_id'], 'miss', c['obligation']) for c in e['obligations']
                             if not c['conditional'] and not c['passed'])
    return found


def command(argv, folder, label):
    started = time.perf_counter()
    try:
        p = subprocess.run(argv, cwd=folder, capture_output=True, timeout=60)
        code, stdout, stderr = p.returncode, p.stdout, p.stderr
        status = 'completed'
    except subprocess.TimeoutExpired as exc:
        code, stdout, stderr = None, exc.stdout or b'', exc.stderr or b''
        status = 'timeout'
    (folder / (label + '.stdout')).write_bytes(stdout)
    (folder / (label + '.stderr')).write_bytes(stderr)
    r = dict(argv=argv, cwd=str(folder), exit_code=code, status=status,
             wall_seconds=time.perf_counter()-started, cpu_seconds=None,
             stdout=relative(folder / (label + '.stdout')), stderr=relative(folder / (label + '.stderr')))
    save(folder / (label + '.command.json'), r)
    return r


def replay(source, dest):
    dest.mkdir(parents=True, exist_ok=False)
    # Keep generated RTL/checker bytes; compile in the new directory so sim.out
    # and wave.vcd cannot overwrite sealed historical artifacts.
    for name in ('rtl.v', 'checker_tb.sv', 'definition.json', 'candidates.json', 'input.json'):
        shutil.copyfile(source / name, dest / name)
    d = read(dest / 'definition.json')
    argv = ['iverilog', '-g2012', '-s', 'tb', '-I', str(SOURCE / 'frozen' / d['key']),
            '-I', str(ROOT / 'external/common_cells/include'), '-o', 'sim.out', 'rtl.v', 'checker_tb.sv']
    compile_result = command(argv, dest, 'compile')
    simulation = command(['vvp', 'sim.out'], dest, 'simulate') if compile_result['exit_code'] == 0 else None
    def trace_records(p):
        return sorted(s for s in p.read_text().splitlines() if s.startswith(('TRACE ', 'CHECK ')))
    exact = bool(simulation and simulation['exit_code'] == 0 and
                 trace_records(dest / 'simulate.stdout') == trace_records(source / 'simulate.stdout'))
    result = dict(source=relative(source), replay=relative(dest), compile=compile_result,
                  simulation=simulation, trace_and_checks_exact=exact)
    (dest / 'reproduce.sh').write_text('#!/bin/sh\nset -eu\ncd "' + str(dest) + '"\n' +
        ' '.join('"' + str(a) + '"' for a in argv) + '\nvvp sim.out\n')
    save(dest / 'comparison.json', result)
    return result


def main(name):
    out = ROOT / 'deliverables' / name
    out.mkdir(exist_ok=False)
    start = time.perf_counter()
    save(out / 'audit_protocol.json', dict(created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        source=relative(SOURCE), source_manifest_sha256=sha(SOURCE / 'delivery/final_artifact_manifest.json'),
        scope='Completion and reproducibility audit, not a new model/search comparison',
        model_calls=0, source_mutations=False, unavailable_cost=None))
    shutil.copyfile(__file__, out / 'audit_source.py')
    ledger = read(SOURCE / 'diagnostics/problem_ledger.json')
    parent = []
    for k in KEYS:
        rows = [r for r in ledger if r['case'] == k]
        parent.append(dict(case=k, original_failures=sum(r['original_status']=='known_failure' for r in rows),
            original_unknowns=sum(r['original_status']=='unknown' for r in rows),
            original_passes=8-len(rows), categories=dict(collections.Counter(c for r in rows for c in r['categories'])),
            fresh_prefix_reproductions=sum(bool(r.get('reproduction')) for r in rows),
            minimality='shortest observed truncated prefix, not deletion-minimal per historical cell',
            no_reproduction=[dict(record_id=r['record_id'], reasons=r['unresolved']) for r in rows if not r.get('reproduction')]))
    assert len(ledger)==40 and len({r['record_id'] for r in ledger})==40
    assert sum(r['original_failures'] for r in parent)==23
    assert sum(r['original_unknowns'] for r in parent)==17
    references = []
    for r in ledger:
        fields = ('specification', 'obligations', 'original_final', 'tool_versions')
        if r.get('reproduction'):
            fields += ('minimal_input', 'cycle_trace', 'waveform')
        for field in fields:
            references.append(dict(record=r['record_id'], field=field, path=r[field], exists=(ROOT/r[field]).is_file()))
    save(out/'ledger_audit.json',dict(records=40,parents=parent,links=references,
        missing_links=[r for r in references if not r['exists']]))

    queries = lines(SOURCE/'search/queries.jsonl')
    attempts = lines(SOURCE/'search/attempts.jsonl')
    assert [q['query_id'] for q in queries]==[a['query_id'] for a in attempts]
    assert len(queries)==len({q['query_id'] for q in queries})==648
    pairs = read(SOURCE/'search/verified_pair_results.json')
    search = []
    existing = read(SOURCE/'analysis_r02/parent_method_results.json')
    for k in KEYS:
        for method in METHODS:
            qs = [q for q in queries if (q['case'],q['method'])==(k,method)]
            assert len(qs)==36
            assert all(sum(q['seed']==s for q in qs)==12 for s in (3113,3119,3121))
            ev = [e for q in qs for e in q['evidence']]
            r = dict(case=k,method=method,queries=len(qs),gap_count=len(gaps(qs)),
                raw_evidence=len(ev),unique_evidence=len({e['evidence_id'] for e in ev}),
                focused_pairs_distinguished=sum(p['focused_11'] and p['distinguished'] for p in pairs if (p['case'],p['method'])==(k,method)),
                costs={n:sum(q[n] for q in qs) for n in ('compile_attempts','simulation_attempts','sim_cycles','wall_seconds','cpu_seconds')})
            old=next(s for s in existing if (s['case'],s['method'])==(k,method))
            assert r['gap_count']==old['gap_count'] and r['raw_evidence']==old['raw_evidence'] and r['unique_evidence']==old['unique_evidence']
            search.append(r)
    save(out/'search_recount.json',search)

    def rejudge(pair):
        q, rr = pair
        f = ROOT / rr['run']
        d, tr = read(f/'definition.json'), read(f/'trace.json')
        oracle = reference.monitor(d,tr)
        same_reference = oracle==read(f/'independent_reference.json')
        cs=read(f/'candidates.json')
        es=[reference.evidence(d,tr,read(f/f'checker_{j}_cycles.json'),oracle) for j in range(len(cs))]
        a=read(f/'adjudication.json')
        return dict(run=rr['run'],reference_matches=same_reference,evidence_matches=es==a['evidence'])
    with ThreadPoolExecutor(max_workers=16) as executor:
        judged=list(executor.map(rejudge,[(q,r) for q in queries for r in q['runs']]))
    save(out/'reference_rejudgment.json',dict(runs=len(judged),mismatches=[r for r in judged if not(r['reference_matches'] and r['evidence_matches'])],
        interpretation='Recomputed independent-spec adjudication from saved traces; no new simulator queries and not a second independent oracle implementation'))
    print('AUDIT ledger/search/reference recounted',flush=True)

    block=SOURCE/'refinement_r04'
    models=[read(p) for p in sorted((block/'models').glob('*/*/*/result.json'))]
    models_by_parent=[]
    for k in ('filter','fifo','stat'):
        rr=[read(p) for p in (block/'models'/k).glob('*/*/result.json')]
        models_by_parent.append(dict(case=k,calls=len(rr),accepted=sum(r['status']=='parsed' for r in rr),
            permission_rejections=sum('permission:identifier' in r.get('error','') for r in rr),
            timeouts=sum('TimeoutError' in r.get('error','') for r in rr)))
    model_queries=lines(block/'queries.jsonl')
    development=[q for q in model_queries if not q['phase'].startswith('heldout')]
    budgets=collections.Counter(q['case']+'/'+q['arm'] for q in development)
    assert len(budgets)==12 and all(n==14 for n in budgets.values())
    shared=[]
    for k in ('filter','fifo','stat'):
        prompts=[json.loads(read(block/'models'/k/a/'0/request.json')['messages'][0]['content']) for a in ('A','B','C','D')]
        common=[{n:p[n] for n in ('contract','ports','expression_rules','current')} | {'feedback':p['feedback'][:3]} for p in prompts]
        shared.append(dict(case=k,common_information_identical=all(p==common[0] for p in common)))
    save(out/'model_audit.json',dict(calls=len(models),by_parent=models_by_parent,budgets=dict(budgets),
        shared_initial_information=shared,prompt_tokens=sum(r.get('prompt_tokens') or 0 for r in models),
        completion_tokens=sum(r.get('completion_tokens') or 0 for r in models),
        unavailable_token_calls=sum(r.get('prompt_tokens') is None or r.get('completion_tokens') is None for r in models),
        model_wall_seconds=sum(r['wall_seconds'] for r in models),corrected_interface_full_comparison='not_executed',
        hidden=read(block/'heldout/summary.json'),regression=read(block/'regression_audit/summary.json')))

    # Recompile four representative witnesses in isolated fresh directories.
    repro=[]
    for row in read(SOURCE/'minimal_search/index.json'):
        witness=row['minimal_witness']
        repro.append(replay(ROOT/witness['run'],out/'replays'/row['case']))
    repro.append(replay(SOURCE/'runs/supplemental_qa/stat_overlap_minimal/stat/correct',out/'replays/stat_overlap'))
    save(out/'fresh_replays.json',repro)
    native=out/'native_sva';native.mkdir()
    shutil.copyfile(SOURCE/'baseline/native_sva/probe.sv',native/'probe.sv')
    native_result=command(['iverilog','-g2012','-s','tb','-o','probe.out','probe.sv'],native,'compile')
    save(native/'capability.json',dict(native_sva_available=native_result['exit_code']==0,result=native_result,
        scope='Syntax capability probe only; failing tool support is not an assertion defect'))
    print('AUDIT fresh witnesses and native capability checked',flush=True)

    manifest=read(SOURCE/'delivery/final_artifact_manifest.json')['files']
    def check(item):
        p,h=item
        try: observed=sha(ROOT/p)
        except FileNotFoundError: observed=None
        return dict(path=p,expected=h,observed=observed) if observed!=h else None
    with ThreadPoolExecutor(max_workers=16) as executor:
        changed=[r for r in executor.map(check,manifest.items()) if r]
    save(out/'sealed_integrity.json',dict(files_checked=len(manifest),changed=changed,passed=not changed))

    old_pair=read(SOURCE/'legacy_replay/summary.json')
    fixed_pair=read(SOURCE/'legacy_replay/corrected_feedback_summary.json')
    save(out/'authoritative_sources.json',dict(
        warning='Older intermediate summaries intentionally retained; do not mix definitions or denominators.',
        legacy_feedback=dict(superseded='legacy_replay/summary.json',authoritative='legacy_replay/corrected_feedback_summary.json',
                             original_equal=old_pair['equal'],corrected_equal=fixed_pair['equal'],reason=fixed_pair['correction']),
        baseline=dict(summary='baseline/summary.json describes the first 151 executable runs only',
                      authoritative='diagnostics/problem_ledger.json + problem_ledger_complete.json include nine unsupported runs'),
        model_status=dict(superseded='delivery/model_costs.json groups errors',authoritative='delivery/model_status_detail.json distinguishes 10 permissions from one timeout'),
        historical='historical_screening/ibex_54/reproduction.json top-level admitted/results supersede nested original source screening status'))

    statuses=[
        dict(item=1,status='partial',done='40-cell classification, obligation catalog, independent monitor qualification, baseline replay, 31 witness prefixes',
             remaining='Per-cell deletion minimization not complete; nine cells have no semantic witness; spill/intr incomplete spec; no native SVA cross-check; async checker extension not adopted in frozen experiments'),
        dict(item=2,status='completed_with_scope_limits',done='Frozen natural candidates, 11 old-signature collisions, 648 equal-budget queries plus separate 72-query reset sensitivity, evidence/cost/pair reports',
             remaining='No general superiority established; unsupported filter candidates and unresolved scopes remain; no new generalization claim'),
        dict(item=3,status='partial',done='24 actual calls, 168 development queries, 12 arm-parent finals, regression audit and costs',
             remaining='10 frontend permission rejections and one timeout; corrected-interface full four-arm rerun not executed'),
        dict(item=4,status='partial',done='Nine quarantined schedules and three artificial sibling faults; one historical Ibex fix reproduced with source commits/patch/tests',
             remaining='No whole-parent pass; semantic-equivalence exclusion not proved; real-history assertion generation/refinement comparison not executed')]
    save(out/'completion_matrix.json',statuses)
    summary=dict(records=40,original_failures=23,original_unknowns=17,search_queries=len(queries),
        reference_runs_rejudged=len(judged),reference_mismatches=sum(not(r['reference_matches'] and r['evidence_matches']) for r in judged),
        fresh_replays=len(repro),exact_replays=sum(r['trace_and_checks_exact'] for r in repro),
        native_sva_available=native_result['exit_code']==0,sealed_files=len(manifest),changed_files=len(changed),
        audit_compile_attempts=5,audit_simulation_attempts=sum(r['simulation'] is not None for r in repro),audit_model_calls=0,
        audit_wall_seconds=time.perf_counter()-start,audit_cpu_seconds=None,model_calls_verified=len(models))
    save(out/'summary.json',summary)
    report=['# 四项任务完成情况核查','',
        '本次从台账、原始查询、逐周期轨迹、模型请求和封存清单复核；没有新增模型调用或改写旧实验。',
        '', '| 项目 | 判定 | 尚未完成 |','|---|---|---|',
        '| 1 失败诊断与验收 | 部分完成 | 31条有截短前缀复现；不是40条均已最小化。9条无可判定语义见证；原生SVA和未决规格仍缺。 |',
        '| 2 冻结候选搜索 | 有限范围内已执行完成 | 648次主查询和72次补充查询；未证实义务搜索总体优越。 |',
        '| 3 四组模型细化 | 部分完成 | 24次调用受到10次接口拒绝和1次超时影响；修正接口后的完整重跑未执行。 |',
        '| 4 独立泛化与历史修复 | 部分完成 | 9条保留输入、3个人工故障、1个历史修复；真实案例生成/修复对照未执行。 |',
        '', '## 逐父案例台账（类别允许重叠）','',
        '| 父案例 | 原通过 | 已知失败 | 未知 | 新执行见证前缀 | 复核分类 |','|---|---:|---:|---:|---:|---|']
    labels={'candidate_omits_required_obligation':'遗漏义务','candidate_rejects_scoped_legal_behavior':'合法误报',
            'timing_error':'时序错误','checker_or_execution_problem':'执行问题','specification_ambiguity':'规格歧义','budget_or_evidence_insufficient':'证据/预算不足'}
    for r in parent:
        cats='；'.join(labels.get(c,c)+str(n) for c,n in r['categories'].items()) or '无原始问题单元'
        report.append(f"| {r['case']} | {r['original_passes']} | {r['original_failures']} | {r['original_unknowns']} | {r['fresh_prefix_reproductions']} | {cats} |")
    report+=['','onehot原8次通过不是本轮独立整体通过。40条是方法×父案例单元；11对碰撞来自另一个自然候选池。',
        '', '## 三种搜索与非onehot瓶颈','', '| 父案例 | 普通缺口 | 分歧缺口 | 义务缺口 | 当前瓶颈 |','|---|---:|---:|---:|---|']
    bottlenecks={'onehot':'已有局部区别，不能代表非onehot进展','filter':'自然池3条只有1条可执行；分歧打分无有效候选对，第二缺口不能归因于分歧目标',
        'fifo':'三法相同；必须同时保护空闲/接受/停顿，模型更改仍有回归',
        'spill':'仅collision_empty可判定，数据含义未决',
        'stat':'重叠事务暴露原correct RTL捕获错误；义务调度发现更少缺口，8次模型提案全部被接口拒绝',
        'intr':'mask采样时刻未定，0不是通过'}
    for k in KEYS:
        rs=[next(r for r in search if (r['case'],r['method'])==(k,m)) for m in METHODS]
        report.append(f"| {k} | {rs[0]['gap_count']} | {rs[1]['gap_count']} | {rs[2]['gap_count']} | {bottlenecks[k]} |")
    report+=['','缺口按候选×FP/FN×义务去重，FP每候选计legal_prefix；不是独立bug数。每方法216次实际查询。三法均局部区分9/11对；双方可能各有缺陷。',
        '逐种子：onehot义务臂相比分歧臂多2个缺口，相比普通臂无新增；spill有独有缺口但也漏掉对照缺口。不能只报新增不报遗漏。',
        '', '## 断言改善及独立支持','',
        'FIFO保留输入最终误报A/B/C/D=39/0/19/39；首次违例漏报=1/2/2/1。提前误报会屏蔽后续漏报，不能凭较小漏报数排名。',
        '同类人工FIFO故障中B、C各有1次满足因果归属条件的检测，D为0。filter、stat没有经过完整义务验收的改善。24个修改检查点有3个新增误报。',
        'stat的8次模型输出全部受接口拒绝；不能将其无改善归因为搜索机制无效。最后一轮11份可用模型输出在允许公开标量复位后均可执行，但未形成新的完整四组轨迹。',
        '当前没有父bug整体通过，也没有支持D相对B/C的一般优势。旧保留场景结果已查看；据此开发的新机制应另建独立场景。',
        '', '## 本次新复现和完整性','',
        f"重新编译执行4个代表性见证，{summary['exact_replays']}/4逐周期TRACE/CHECK一致；重算1296次运行的参考判定/证据，差异{summary['reference_mismatches']}。",
        f"核验封存{len(manifest)}个文件，变化{len(changed)}个。原生SVA语法探针仍不支持；结果属于过程checker+独立参考监视器。",
        'stat_overlap：两拍复位，t2长度19、t3长度73，t4应为19却为73。见replays/stat_overlap/reproduce.sh及simulate.stdout、wave.vcd。',
        '另复现filter 7拍漏报、stat 5拍漏报、fifo 3拍合法误报；输入值未全局最小化。',
        '', '## 下一步优先顺序','',
        '1. 先修正共同接口并做资格检查；把filter两条不可执行候选的语法/权限原因单独处理，不改动冻结搜索结果。',
        '2. 对stat完善合法重叠事务对照，补齐逐父bug必要义务验收清单；对有见证的历史记录继续最小化，未决规格保留未知。',
        '3. 新建区块，用同一模型、相同初始候选及预算重跑A/B/C/D；使用新的隔离保留场景。不要把诊断重放当完整模型实验。',
        '4. 将Ibex #54接入真实案例生成/修复对照；历史补丁和验收答案保持不可见。',
        '', '## 日志入口与口径','',
        '本目录summary.json、ledger_audit.json、search_recount.json、reference_rejudgment.json、model_audit.json、fresh_replays.json、sealed_integrity.json可重建本次结论。',
        'authoritative_sources.json说明旧中间汇总的替代关系：legacy_replay/summary.json的4/11是旧错误口径；corrected_feedback_summary.json才是11/11。历史文件不覆盖。',
        '原实验全部成本见../obligation_evidence_20261013_r02/delivery/physical_costs.json；搜索每父每方法成本也已重算到search_recount.json。模型成本见model_audit.json。未知tokens/CPU不是0。']
    (out/'REPORT.md').write_text('\n'.join(report)+'\n',encoding='utf-8')
    save(out/'manifest.json',{relative(p):sha(p) for p in out.rglob('*') if p.is_file()})
    print(json.dumps(summary),flush=True)
    assert not changed and not any(not(r['reference_matches'] and r['evidence_matches']) for r in judged)
    assert all(r['trace_and_checks_exact'] for r in repro)
    assert all(r['common_information_identical'] for r in shared)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True)
    main(p.parse_args().output)
