"""Interpret completed native search without reclassifying old findings as new."""
import argparse
from collections import Counter
from pathlib import Path
import research64_search_value as run


def report(root,audit,out):
    out.mkdir(parents=True,exist_ok=False)
    run.verify(root)
    audit_result=run.read(audit/'audit.json');assert audit_result['passed']
    rows=run.read(root/'summary.json');records=run.read(root/'records.json');unions=run.read(root/'method_unions.json')
    costs=run.read(root/'cost.json');calls=run.read(root/'reference_costs.json')
    comparisons=[];totals=[]
    for method in run.METHODS:
        ss=[s for s in rows if s['method']==method]
        totals.append(dict(method=method,candidate_specific_public_new=len(unions['candidate_gap_keys'][method]),
            mechanism_public_new=len(unions['mechanism_keys'][method]),
            reference_calls=sum(sum(c['calls'] for c in s['reference_cost'].values()) for s in ss),
            reference_seconds=sum(sum(c['wall_seconds'] for c in s['reference_cost'].values()) for s in ss),
            query_seconds=sum(s['query_wall_seconds'] for s in ss),native_executions=sum(s['native_executions'] for s in ss),
            repeat_observations=sum(s['repeated_observations'] for s in ss),
            unknown=sum(s['unknown'] for s in ss),later_unknown=sum(s['later_attribution_unknown'] for s in ss),
            failed_queries=sum(s['failed_queries'] for s in ss)))
    for s in rows:
        if s['method']!='contract_coverage':continue
        matching={x['method']:x for x in rows if x['pair']==s['pair'] and x['seed']==s['seed']}
        keys=sorted(set().union(*(set(x['first_query']) for x in matching.values())))
        for key in keys:
            first={m:x['first_query'].get(key) for m,x in matching.items()}
            comparisons.append(dict(pair=s['pair'],seed=s['seed'],key=key,first_query=first,
                native_executions_to_first={m:16*q if q is not None else None for m,q in first.items()},
                common_setup_native_executions=32,
                interpretation='First-query cost excludes identical 32-run public setup; absent witness remains null, not zero cost. All four queries are charged in final cost.'))
    novelty=Counter(v for s in rows for v in s['historical_novelty'].values())
    contract_rows=[s for s in rows if s['method']=='contract_coverage']
    sensitivity=sum(s['feedback_sensitivity_changed_queries'] for s in contract_rows)
    differs=sum(s['actual_choices_differ_from_fixed_sweep'] for s in contract_rows)
    role_cost={stage:{kind:dict(calls=sum(c['stage']==stage and c['kind']==kind for c in calls),
        seconds=sum(c['wall_seconds'] for c in calls if c['stage']==stage and c['kind']==kind))
        for kind in ('transaction_reference','sampling_reference','paired_obligation_judge')} for stage in ('public','search')}
    state=dict(status='completed_development_comparison',qualified_candidates=3,ordered_primary_tasks=3,
        unique_unordered_candidate_pairs=2,parent_cases=1,seeds=list(run.SEEDS),
        native_queries=len(records),contract_exclusive_candidate_gaps=unions['contract_extra_vs_all_baselines'],
        contract_choices=24,feedback_sensitive_choices=sensitivity,choices_differing_from_sweep=differs,
        historical_novelty_classification_counts=dict(novelty),globally_new_gap_claims=0,
        native_cost=costs['total'],reference_costs_by_role=role_cost,audit_cost=audit_result,
        scope='Known artificial FIFO mechanisms, exploratory policies, finite two-seed results. No new model refinement, independent test, or formal proof.')
    run.dump(out/'status.json',state);run.dump(out/'per_gap_first_cost.json',comparisons);run.dump(out/'method_totals.json',totals)
    lines=['# research64：搜索机制额外价值的实跑结论','',
        '三个不同真实模型候选全部通过公共场景资格检查。3个主候选方向、2个不计方向的候选对、1个父FIFO案例；2种子×5方法×4查询，共120个搜索查询。候选来自research20/27(41)/28，未读取research63独立测试。', '',
        '公共反馈先固定overlap与短背压场景，执行所有故障。两个旧候选的解除边界valid漏报已在公共反馈曝光，搜索再次发现不计新增；较完整候选公共缺口为空。长短valid撤销按相同义务/失效机制合并，数据和时长变体不增加发现数。', '',
        '|方法|公共之外的候选相关缺口|去候选后的机制/义务类|搜索原生执行|参考计算调用|参考计算秒|查询总秒|归因unknown|后续归因unknown|',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for t in totals:
        lines.append(f"|{t['method']}|{t['candidate_specific_public_new']}|{t['mechanism_public_new']}|{t['native_executions']}|{t['reference_calls']}|{t['reference_seconds']:.3f}|{t['query_seconds']:.3f}|{t['unknown']}|{t['later_unknown']}|")
    exclusive=unions['contract_extra_vs_all_baselines']
    lines+=['',f"契约相对所有基线并集的独有缺口：{len(exclusive)}。这不等同于逐种子比较；逐种子与逐缺口首发现成本保存在per_gap_first_cost.json。完整预算成本保留未发现、重复和unknown查询。", '',
        f"契约24次实际选择中，{differs}次选择与固定覆盖不同；保持随机状态不变、只改变已观测义务反馈的诊断中，{sensitivity}次会改变实际选样。这证明反馈参与选择，不证明性能优势。诊断反事实没有执行为搜索样本，也不计发现。", '',
        '缺口新颖性分两层：公共反馈之外可以由本轮记录完整确认；全历史索引仅覆盖已审计research30/42及覆盖对照，未命中一律unknown，不能写成新发现。已知人工故障名称本来就公开，本实验不声称发现未知硬件Bug。', '',
        '既有research42/50轨迹中，契约背压桶与固定扫描完全一致，没有额外发现或更低首次发现成本。本轮复用research15已有缺口计分，实际根据自己的义务检查、有效触发、目标检出与历史尝试次数改变场景选择；没有根据最终结果修改策略或替换候选。', '',
        f"本轮物理成本：{costs['total']['native_compile_calls']}次编译、{costs['total']['native_execute_calls']}次执行，模型调用/tokens/形式化均0；其中公共反馈96次执行，搜索1920次，编译启动冒烟3次。事务参考、采样参考、配对义务判定计时另列，查询总耗时包含日志和磁盘开销，不能与子阶段重复相加。只读审计的参考重算单列，不计成选择收益。", '',
        '全部组物理运行参考模型用于统一测量；契约组还用其结果选择下一查询。该端到端比较不等于经过优化、完全不运行参考模型的基线部署成本。历史模型生成成本不冒充本轮新增成本。', '',
        '所有故障是axis_fifo上的显式人工输出边界变异；重复候选方向/种子不增加独立父Bug数。旧11对程序检查候选未冒充新增原生候选。后续归因unknown保留，不能说整条事务轨迹均已确证。', '',
        '复核命令：', '```powershell',
        'wsl -- python3 scripts/research64_search_value.py report --out '+str(root.relative_to(run.ROOT)).replace('\\','/'),
        'wsl -- python3 scripts/research64_native_audit.py --run '+str(root.relative_to(run.ROOT)).replace('\\','/')+' --out deliverables/research64_audit_NEW',
        '```', '', '重新执行（新目录，不覆盖本次结果）：', '```powershell',
        'wsl -- python3 scripts/research64_search_value.py prepare --out deliverables/research64_search_NEW',
        'wsl -- python3 scripts/research64_search_value.py run --out deliverables/research64_search_NEW', '```']
    (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    trace=['# 具体选样和证据轨迹','', '以下仅展示真实开发查询，未用示例挑选最终候选。']
    for pair in ('pre_valid__valid','bounded__valid'):
        r=next(x for x in records if x['pair']==pair and x['seed']==6401 and x['method']=='contract_coverage' and x['query']==0)
        trace += ['',f"## {pair} / seed6401 / contract q0",'',
            f"公共反馈没有复位取消检查；根据真实检查/触发缺口选择 `{r['family']}`。本次公共之外新增键：",'```json',run.json.dumps(r['first_new_keys'],indent=2),'```']
        for g in r['gaps']:
            if g['key'] not in r['first_new_keys']:continue
            trace += ['',f"- {g['kind']} / {g['obligation']} / {g['mechanism']}"]
            if g['kind']=='FN':
                e=g['evidence'];v=g['validation']
                trace += [f"  周期{e['cycle']}，触发分类 `{g['trigger_class']}`；实际已接受事务数{v['accepted_transaction_count']}；合法激励、同握手、fixed满足、faulty违例与当前SVA漏报均经逐项核验。",
                          f"  原生回放：`{g['replay_source']}`。"]
        trace += ['', '同类缺口是否也由基线发现、首次查询与全部支出见per_gap_first_cost.json；该轨迹本身不能证明契约独有收益。']
    (out/'CASE_TRACE.md').write_text('\n'.join(trace)+'\n',encoding='utf-8')
    print('VALUE_REPORT',state['contract_exclusive_candidate_gaps'],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=Path,required=True);p.add_argument('--audit',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();report(a.run.resolve(),a.audit.resolve(),a.out.resolve())
