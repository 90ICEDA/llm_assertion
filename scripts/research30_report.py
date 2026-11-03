"""Summarize every search query, including negatives and actual costs."""
import argparse
from pathlib import Path
from collections import Counter
import hashlib
import shutil
import research17_loop as loop
import research17_report as costs

read,dump=loop.read,loop.dump


def main():
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True)
    args=p.parse_args();run=args.run.resolve()
    assert read(run/'outcome.json')['status']=='four_search_methods_completed'
    protocol=read(run/'protocol.json');records=read(run/'results.json')
    report=run/'report';report.mkdir(exist_ok=True)
    files=[p for p in run.rglob('*') if p.is_file() and 'report' not in p.relative_to(run).parts]
    cost=costs.cost_audit(run,files);dump(report/'cost.json',cost)
    methods={};seeds=[]
    for seed in protocol['seeds']:
        sets={m:set().union(*(set(r['unique_gap_keys']) for r in records if r['seed']==seed and r['method']==m))
              for m in protocol['methods']}
        common={m:set(r['unique_gap_keys']) for m in protocol['methods']
                for r in records if r['seed']==seed and r['method']==m and r['query']==0}
        seeds.append(dict(seed=seed,methods={m:dict(unique_gaps=sorted(s),new_vs_common=sorted(s-common[m]),
            additional_vs_ordinary=sorted(s-sets['ordinary']),
            absent_vs_ordinary=sorted(sets['ordinary']-s),
            first_discovery_query_count=next((r['query']+1 for r in records
                if r['seed']==seed and r['method']==m and r['unique_gap_keys']),None)) for m,s in sets.items()}))
    for method in protocol['methods']:
        rows=[r for r in records if r['method']==method]
        keys=set().union(*(set(r['unique_gap_keys']) for r in rows))
        first={}
        for r in rows:
            for gap in r['gaps']:
                first.setdefault(gap['gap_key'],dict(seed=r['seed'],query=r['query'],family=r['family'],**gap))
        methods[method]=dict(queries=len(rows),native_executions=sum(r['physical_native_executions'] for r in rows),
            simulated_cycles=sum(r['query_cycles'] for r in rows),
            unique_gap_keys=sorted(keys),unique_gaps=len(keys),examples=list(first.values()),
            valid_gap_rows=sum(len(r['gaps']) for r in rows),
            duplicate_gap_rows=sum(len(r['gaps']) for r in rows)-len(keys),
            gap_obligations=sorted({g['obligation'] for r in rows for g in r['gaps']}),
            false_positive_rows=sum(g['kind']=='FP' for r in rows for g in r['gaps']),
            false_negative_rows=sum(g['kind']=='FN' for r in rows for g in r['gaps']),
            unknown_rows=sum(r['unknown_rows'] for r in rows),
            later_attribution_unknown=sum(r['later_attribution_unknown'] for r in rows),
            non_ok_queries=sum(r['status']!='ok' for r in rows))
    universe={m:set(x['unique_gap_keys']) for m,x in methods.items()}
    for m in methods:
        methods[m]['additional_vs_each']={n:sorted(universe[m]-universe[n]) for n in methods if n!=m}
    fairness=dict(equal_query_counts=len({v['queries'] for v in methods.values()})==1,
        equal_native_executions=len({v['native_executions'] for v in methods.values()})==1,
        equal_simulated_cycles=len({v['simulated_cycles'] for v in methods.values()})==1,
        all_queries_retained=len(records)==len(protocol['seeds'])*len(protocol['methods'])*protocol['queries_per_method_seed'],
        two_distinct_whole_candidate_hashes=len({c['hash'] for c in protocol['frozen_candidates'].values()})==2)
    fairness['candidate_files_match_frozen_hashes']=all(loop.sha(read(run/'candidates'/f'{n}.json'))==c['hash']
        for n,c in protocol['frozen_candidates'].items())
    fairness['same_common_input_per_seed']=all(len({
        hashlib.sha256((run/'queries'/f's{seed}'/method/'q0/initial/correct_stimulus/stimulus.json').read_bytes()).hexdigest()
        for method in protocol['methods']})==1 for seed in protocol['seeds'])
    allowed=dict(ordinary={'family'},candidate_disagreement={'family','candidate_disagreement_count'},
        raw_difference={'family','raw_difference_count'},
        contract_coverage={'family','status','checks','triggers','protected','witnesses','protection_measure'})
    fairness['policy_observation_fields_restricted']=all(set(r['permitted_feedback_view'])==allowed[r['method']] for r in records)
    result=dict(methods=methods,seeds=seeds,fairness=fairness,cost=cost['total'],
        scope=protocol['exposure'],legacy_11_pairs=protocol['legacy_11_pairs'],
        interpretation='Known FIFO candidate-pair pilot, not independent unseen-case evaluation. Extra evidence, ties and misses all retained. No statistical superiority or model-refinement benefit inferred.')
    dump(report/'results.json',result)
    lines=['# Research30：四类搜索的原生候选对比较','',
        '固定 research27 与 research28 两个完整冻结集合；分歧是它们在相同原生执行上的集合报警周期 XOR。不是集合内部两条不同义务断言的分歧。',
        '三个固定种子，每方法每种子 4 次查询。每次查询执行两个候选 × 正确版本及七类既有人工故障，共 16 次执行；q0 是计入预算的共同 overlap 输入。Depth 4/Pipeline 1，每次 112 拍。',
        '所有方法具有同样的公共规格、候选和输入语法；仅策略使用的反馈不同。所有查询都由独立事务 oracle 统一事后判定，不将波形差异或候选分歧本身计为 Bug。','',
        '| 方法 | 查询 | 原生执行 | 独立缺口类 | 有效漏报记录 | 重复缺口记录 | 当前 unknown |',
        '|---|---:|---:|---:|---:|---:|---:|']
    for m,v in methods.items():
        lines.append(f"| {m} | {v['queries']} | {v['native_executions']} | {v['unique_gaps']} | {v['false_negative_rows']} | {v['duplicate_gap_rows']} | {v['unknown_rows']} |")
    lines+=['','去重按初始候选哈希、误报/漏报、义务和故障机制。种子、深度、周期和数据变体不增加独立缺口数量。','']
    for seed in seeds:
        lines.append(f"种子 {seed['seed']}：")
        for m,v in seed['methods'].items():
            lines.append(f"- {m}：新增于共同反馈 {len(v['new_vs_common'])} 类；相对普通补测额外 {len(v['additional_vs_ordinary'])} 类，缺少 {len(v['absent_vs_ordinary'])} 类；首次发现所用查询数 {v['first_discovery_query_count']}（None 为预算内未发现）。")
    lines+=['','逐项缺口、首次发现查询、事务证据和相对各基线新增项见 results.json；不得只看汇总数量。',
        f"公平性检查：`{fairness}`。",
        f"实际成本：`{cost['total']}`。",
        '这是已知修复前后候选对、已知人工故障上的回顾性机制试验。原 11 对候选的受限检查器结果没有被追认为原生结果；本轮只有一个真实原生 FIFO 候选对。三个种子也不能代表跨父案例稳定性。',
        '四组真实模型消融另行执行；本结果不代表防退化或细化收益。','']
    (report/'SUMMARY.md').write_text('\n'.join(lines),encoding='utf-8')
    shutil.copy2(__file__,report/'report_source.py')
    manifest={p.relative_to(run).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    dump(report/'manifest.json',manifest)
    failures=[n for n,h in manifest.items() if hashlib.sha256((run/n).read_bytes()).hexdigest()!=h]
    dump(report/'verification.json',dict(passed=not failures and all(fairness.values()),files=len(files),failures=failures,fairness=fairness))
    print(dict(methods={m:v['unique_gaps'] for m,v in methods.items()},fairness=fairness,files=len(files)),flush=True)


if __name__=='__main__':main()
