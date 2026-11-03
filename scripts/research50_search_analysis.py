"""Per-gap cost and incremental-evidence comparison of the audited42 runs."""
import json
from pathlib import Path
import research17_loop as loop
import research43_paired_ablation as common


def main():
    source=loop.ROOT/'deliverables/research50_search_audit_20261022_r01/results.json'
    out=source.parent
    result=loop.read(source);assert result['all_checks_passed']
    comparisons=[];table=[]
    for seed in result['per_seed']:
        methods=seed['methods'];contract=methods['contract_coverage']
        for method,value in methods.items():
            assert value['queries']==4 and value['native_executions']==24
            first={key:dict(query_count=q+1,native_executions_through_discovery=(q+1)*6)
                   for key,q in value['first_discovery_query'].items()}
            table.append(dict(seed=seed['seed'],method=method,gaps=value['unique_gap_count'],
                first_discovery=first,duplicates=value['duplicate_gap_observations'],
                unknown=value['current_unknown'],later_attribution_unknown=value['later_attribution_unknown']))
            if method=='contract_coverage':continue
            both=set(contract['gap_keys'])&set(value['gap_keys'])
            comparisons.append(dict(seed=seed['seed'],baseline=method,
                contract_extra_gap_keys=sorted(set(contract['gap_keys'])-set(value['gap_keys'])),
                baseline_extra_gap_keys=sorted(set(value['gap_keys'])-set(contract['gap_keys'])),
                contract_lower_query_cost_gap_keys=sorted(k for k in both if contract['first_discovery_query'][k]<value['first_discovery_query'][k]),
                contract_higher_query_cost_gap_keys=sorted(k for k in both if contract['first_discovery_query'][k]>value['first_discovery_query'][k])))
    loop.dump(out/'incremental_evidence_and_cost.json',dict(source_sha256=common.digest(source),per_method_seed=table,
        contrasts=comparisons,query_definition='One query=112 cycles,6 actual native executions; shared compile/smoke overhead listed separately in original report.',
        cost_scope='First-discovery query counts are directly measured; no claim about optimal implementations or asymptotic cost.',
        dedup='Frozen initial candidate hash/FN-or-FP/obligation/fault mechanism; not waveform count.',
        candidate_pairs=1,remaining_scope='The full11 historical candidate-pair suite and additional historical parent bugs are not covered by this experiment.'))
    lines=['# 逐缺口增量与首次发现成本','',
        '以下复用已审计的实际原生记录，未新增搜索或模型调用。首次发现按1起算；每查询6次原生执行，编译/冒烟另计。','',
        '|种子|方法|独立缺口|首次发现查询数|重复缺口观察|后续归因unknown|','|---|---|---:|---|---:|---:|']
    for row in table:
        hits=','.join(str(v) for v in sorted({v['query_count'] for v in row['first_discovery'].values()})) or '未发现'
        lines.append(f'|{row["seed"]}|{row["method"]}|{row["gaps"]}|{hits}|{row["duplicates"]}|{row["later_attribution_unknown"]}|')
    lines+=['','两类独立缺口都是stall_stability：long_valid_withdraw_stalled（持续背压撤销valid）与long_valid_withdraw_release（解除边界撤销valid）。'
        '原生触发存在但性质约束不足；独立事务oracle确认违例，不能仅凭波形或候选不一致判为Bug。',
        '','跨种子并集没有契约独有缺口；相对分歧、差分、固定覆盖，契约没有更多发现或更低首次发现查询成本。'
        '种子4211相对普通补测多2类有效缺口，但固定覆盖对照也得到相同结果，不能归因于契约语义特有收益。',
        '','范围是1对固定候选、3种子、两类已知人工故障，不是完整11对候选或真实历史父案例基准。']
    (out/'PER_GAP_COMPARISON.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    assert not any(c['contract_extra_gap_keys'] or c['contract_lower_query_cost_gap_keys'] for c in comparisons if c['baseline'] in ('candidate_disagreement','raw_difference','coverage_sweep'))
    print('SEARCH_CONTRASTS',len(comparisons),'no advantage beyond disagreement/difference/fixed coverage',flush=True)


if __name__=='__main__':main()
