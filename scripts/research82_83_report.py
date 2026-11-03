"""Publish separately identifiable mechanism effects from audited local evidence."""
import argparse
from pathlib import Path
import research82_search_increment as search

b = search.b


def publish(root, search_audit, gate_audit, out):
    execution = b.read(root / 'outcome.json')
    assert execution['status'] == 'completed'
    sa, ga = b.read(search_audit / 'audit.json'), b.read(gate_audit / 'audit.json')
    assert sa['passed'] and ga['passed']
    rows = b.read(root / 'summary.json')
    totals = b.read(root / 'method_totals.json')
    paired = b.read(root / 'paired_increment.json')
    conclusion = b.read(root / 'increment_conclusion.json')
    gates = b.read(gate_audit / 'increment_results.json')
    selection = b.read(search_audit / 'selection_audit.json')
    records = b.read(root / 'records.json')
    assert len(records) == 252 and len(rows) == 63
    all_keys = sorted(set().union(*(set(v['keys']) for v in totals.values())))
    inventory = []
    for key in all_keys:
        entries = [dict(pair=r['pair'], seed=r['seed'], method=r['method'],
                        first_query=r['first_query'][key], historical_novelty=r['historical_novelty'][key])
                   for r in rows if key in r['first_query']]
        inventory.append(dict(key=key, candidate_hash=key.split('/')[0],
            kind=key.split('/')[1], obligation=key.split('/')[2], mechanism=key.split('/')[3],
            methods=[m for m in totals if key in totals[m]['keys']], observations=entries,
            independent_bug_count_credit=0))
    comparisons = {}
    for method in totals:
        if method == 'contract_novelty':
            continue
        rr = [r for r in paired if r['comparator'] == method]
        comparisons[method] = dict(
            **{k:sum(r[k] for r in rr) for k in ('earlier', 'tied', 'later')},
            contract_only=sum(len(r['contract_only']) for r in rr),
            comparator_only=sum(len(r['comparator_only']) for r in rr))
    acquisition_cost = {}
    for method, total in totals.items():
        rr = [r for r in rows if r['method'] == method]
        acquisition_cost[method] = dict(queries=total['queries'],
            native_executions=total['native_executions'],
            query_wall_seconds=sum(r['query_wall_seconds'] for r in rr),
            selector_seconds=sum(r['selector_seconds'] for r in rr),
            reference={k:dict(calls=sum(r['reference_cost'][k]['calls'] for r in rr),
                seconds=sum(r['reference_cost'][k]['wall_seconds'] for r in rr))
                for k in ('transaction_reference', 'sampling_reference', 'paired_obligation_judge')})
    out.mkdir(parents=True, exist_ok=False)
    # Retrospective extra control: hold historical information fixed and compare
    # the relative gate to an explicit absolute replay rule. This rule is not
    # credited as prospectively registered and does not alter any old decision.
    absolute_rule = dict(kind='retrospective_same_history_control',
        accepts='ordinary accepted AND full105 native healthy AND FP=0 AND FN=0 AND critical_unknown=0',
        condition='Only ordinary-accepted proposals enter the incremental rejection denominator.',
        limits='A minimal absolute replay rule, not global trigger equivalence; does not establish that relative preservation is unnecessary in other scenarios.',
        new_model_calls=0, new_native_queries=0)
    b.dump(out / 'same_history_absolute_rule.json', absolute_rule)
    equal_history = {}
    for experiment, proposals in (
            ('research71', b.read(gate_audit/'paired/proposals.json')),
            ('research73', b.read(gate_audit/'selected/results.json'))):
        comparisons_abs = []
        for p in proposals:
            ordinary = p['plain_accepted'] if experiment == 'research71' else p['ordinary_pass']
            if not ordinary:
                continue
            if experiment == 'research71':
                source = b.ROOT/'deliverables/research71_real_20261024_r01/core'/f"s{p['seed']}"/p['stream']/'history_native/result.json'
                gated = p['gated_accepted']
            else:
                source = b.ROOT/'deliverables/research73_discriminating_20261024_r01'/f"c{p['index']:02d}"/'history/result.json'
                gated = not p['extra_rejection']
            full = b.read(source)
            absolute = full['healthy'] and all(full['counts'][k] == 0 for k in ('false_positives','misses','unknown'))
            comparisons_abs.append(dict(source=str(source), source_hash=b.digest(source),
                ordinary_accepted=True, absolute_accepted=absolute, relative_gate_accepted=gated,
                relative_only_rejection=absolute and not gated, counts=full['counts']))
        equal_history[experiment] = dict(eligible_proposals=len(comparisons_abs),
            relative_only_rejections=sum(r['relative_only_rejection'] for r in comparisons_abs),
            absolute_rejections=sum(not r['absolute_accepted'] for r in comparisons_abs),
            relative_rejections=sum(not r['relative_gate_accepted'] for r in comparisons_abs),
            rows=comparisons_abs)
    b.dump(out / 'same_history_comparison.json', equal_history)
    claims = {
        'contract_changes_selection': dict(status='measured',
            changed_counterfactual_choices=selection['selection_changes'],
            probes=len(selection['probes']), not_discovery_credit=True),
        'contract_unique_over_all': dict(status='observed' if conclusion['extra_over_all_count'] else 'not_observed',
            count=conclusion['extra_over_all_count'], scope='3 fixed seeds, 3 directed candidate tasks, known synthetic mutations'),
        'contract_discovery_cost': dict(status='measured', comparisons=comparisons,
            scope='Paired first-query rank; missing discoveries right-censored at budget4, never imputed as5. Wall time descriptive only.'),
        'historical_extra_rejection': dict(status='supported_retrospectively',
            selected=gates['selected'], prospective_paired=gates['paired']),
        'historical_feedback_incremental_recovery': dict(status='not_demonstrated',
            multiround=gates['independent_multiround'], selected_continuation=gates['bounded_selected_recovery']),
        'cross_protocol_restoration': dict(status='descriptive_only', result=gates['cross_protocol_restoration']),
        'relative_gate_over_same_history_absolute_check': dict(status='retrospectively_measured', result=equal_history),
    }
    b.dump(out / 'claims.json', claims)
    b.dump(out / 'gap_inventory.json', inventory)
    uncertain = []
    for record in records:
        if not record['unknown']:
            continue
        folder = root/'queries'/record['pair']/f"s{record['seed']}"/record['method']/f"q{record['query']}"
        for path in sorted((folder/'judgements').glob('*.json')):
            for row in b.read(path)['unknown_rows']:
                uncertain.append(dict(pair=record['pair'], seed=record['seed'],
                    method=record['method'], query=record['query'],
                    source=str(path), evidence=row, discovery_credit=False))
    assert len(uncertain) == sum(r['unknown'] for r in records)
    b.dump(out / 'unknown_evidence.json', uncertain)
    example = None
    for record in records:
        if record['method'] != 'contract_novelty':
            continue
        for gap in record['gaps']:
            if gap['key'] in record['first_new_keys']:
                example = (record, gap)
                break
        if example:
            break
    if example:
        record, gap = example
        candidate = b.read(root / 'candidates' / (record['pair'].split('__')[0]+'.json'))
        sample = dict(selection='First actual contract record containing a public-unexposed gap, in execution order; not chosen for advantage.',
            pair=record['pair'], seed=record['seed'], query=record['query'], key=gap['key'],
            evidence=gap['evidence'], conditions=gap['validation']['conditions'],
            trigger_class=gap['trigger_class'], samples=gap['validation'].get('samples'),
            accepted_transactions=gap['validation'].get('transactions', [])[:5],
            properties=candidate['assertions'], replay_source=gap['replay_source'],
            same_seed_comparators=[dict(method=r['method'], first_query=r['first_query'].get(gap['key']),
                not_found_is_censored=gap['key'] not in r['first_query']) for r in rows
                if (r['pair'],r['seed']) == (record['pair'],record['seed'])])
        b.dump(out / 'search_case_trace.json', sample)
    b.dump(out / 'acquisition_cost_by_method.json', acquisition_cost)
    b.dump(out / 'milestones.json', dict(new_accepted_versions=0, new_independent_acceptances=0,
        new_model_calls=0, new_search_queries=len(records), completed_fixed_search_replications=1,
        recomputed_prior_mechanism_experiments=ga['source_audits'],
        extra_rejections_are_prior_not_new=True, no_automatic_model_expansion=True))
    b.dump(out / 'input_hashes.json', {str(p):b.digest(p) for p in
        (root/'sealed.json', root/'records.json', root/'cost.json', search_audit/'audit.json',
         search_audit/'selection_audit.json', gate_audit/'audit.json', gate_audit/'increment_results.json')})
    b.dump(out / 'script_hashes.json', {str(p):b.digest(p) for p in
        (Path(__file__), Path(search.__file__), b.ROOT/'scripts/research83_increment_audit.py')})
    names = dict(ordinary='普通补测', candidate_disagreement='真实候选对分歧',
        raw_difference='普通差分', contract_coverage='原契约策略',
        coverage_sweep='固定覆盖', contract_novelty='去重契约策略', ordinary_no_repeat='普通不重复补测')
    cost = b.read(root / 'cost.json')['total']
    b.dump(out / 'physical_search_cost.json', dict(native=cost,
        runner_elapsed_seconds=execution['elapsed_seconds'],
        query_wall_seconds=sum(r['query_wall_seconds'] for r in records),
        public_query_wall_seconds=sum(r['query_wall_seconds'] for group in
            b.read(root/'public_feedback.json').values() for r in group['results']),
        note='Runner elapsed includes compilation, persistence and verification through execution completion; report/audit time separate. Native/reference timings overlap query time. Parallel local audit workload prevents a controlled wall-clock speed claim.'))
    lines = ['# 两个机制的增量作用：分项实测与审计', '',
        '本轮新增接受版本0、新独立验收0、模型调用0。完成252次新搜索查询，并从原始记录复核五组既有门控／恢复实验。旧独立结果保持不变；没有为追求正结果追加同模型调用。', '',
        '## 契约搜索：发现与成本', '',
        '预先固定8203/8211/8221、3个有向候选任务、7策略、每组4查询。候选、公共反馈、合法激励池及查询计费一致；各策略只读取其协议允许的反馈。两个无向候选对、一个FIFO父案例，不能称为3个独立Bug或已有11对全部完成。', '',
        '|策略|公共外去重候选缺口|重复动作|搜索查询|原生执行|关键unknown|后续归因unknown|', '|---|---:|---:|---:|---:|---:|---:|']
    for m, t in totals.items():
        lines.append(f"|{names[m]}|{t['unique_candidate_gaps']}|{t['repeated_action_queries']}|{t['queries']}|{t['native_executions']}|{t['unknown']}|{t['later_attribution_unknown']}|")
    lines += ['', f"契约相对所有对照并集独有缺口：**{conclusion['extra_over_all_count']}**。公共已曝光项已扣除；同一候选、义务和失效机制的波形变体不重复计数。已知人工故障再发现不算新历史Bug。逐缺口见gap_inventory.json与搜索目录first_discovery_actual_cost.json。", '',
        '|对照|共同发现中契约更早/相同/更晚|契约独有任务×种子发现|对照独有|', '|---|---|---:|---:|']
    for m, c in comparisons.items():
        lines.append(f"|{names[m]}|{c['earlier']}/{c['tied']}/{c['later']}|{c['contract_only']}|{c['comparator_only']}|")
    lines += ['', '共同发现上的先后只用实际首次查询比较；未发现项保留预算内未找到，不伪造成本。固定完整预算下，各方法实际查询量相同；早发现不是总预算减少。运行顺序固定且本地审计可并行，墙钟耗时不具独立性能试验意义。', '',
        f"关键unknown共{len(uncertain)}条，完整采样、义务、原生归因状态见unknown_evidence.json；这些行未作为有效漏报或发现收益计分。编译/执行完成不代表归因可判定。", '',
        f"对真实策略状态逐步重放全部选择；仅移除已曝光字段的诊断对照改变{selection['selection_changes']}/{len(selection['probes'])}次选择。这一诊断不计发现收益；结果为0时，表示本批未证实该字段实际改变选择，不能据此宣称缺口降权产生了增量效果。普通不重复策略也达到0重复动作，通用去重收益不能归为契约独有价值。其他覆盖/触发字段仍保留，本诊断不等价于删除全部契约信息。", '',
        f"物理原生编译{cost['native_compile_calls']}、执行{cost['native_execute_calls']}（含启动自检）。参考事务模型、采样核验和义务判定逐次计数与计时；与query墙钟重叠，不二次相加。共同构建/公共查询、选择和审计成本分别保留。", '',
        '## 防退化：额外拒绝与后续恢复', '',
        '|证据|实测|能够支持的结论|', '|---|---|---|',
        '|research71单轮同提案对照|6真实提案中3普通接受，历史额外拒绝0/3|完成有限负结果；不是尚未运行|',
        '|research73回顾筛选|9真实提案中4普通接受，历史额外拒绝1/4|c04确实丢失31确认检出，新增46义务级误报、22关键unknown；拒绝后基线214历史检出保留|',
        '|research72独立多轮四组|A/B/C/D新独立通过1/3、2/3、0/3、0/3；21次调用|普通可接受的C/D提案为0，无法识别额外拒绝→恢复作用；不把0分母当成无效证据|',
        '|research74选定案例有界恢复|两次实际调用均未接受|失败结果保留，不能跨协议拼接成统一预算成功|',
        '|research81直接生成|恢复31/31、清除46/46；105历史214/214，既有新独立68/68|真实恢复已发生，但没有本组历史拒绝后细化，不能给历史反馈因果收益记分|', '',
        f"新增同历史绝对检查的回顾性对照：research71在{equal_history['research71']['eligible_proposals']}个普通接受提案中，相对门控独有拒绝{equal_history['research71']['relative_only_rejections']}；research73在{equal_history['research73']['eligible_proposals']}个普通接受提案中，相对门控独有拒绝{equal_history['research73']['relative_only_rejections']}。规则及每个决定见same_history_absolute_rule.json和same_history_comparison.json。", '',
        '上述对照将历史证据的增量与相对比较算子的增量分开。它是回顾性分析，不是新前瞻性消融，也不能推论相对检查在其他触发退化场景无用。有限证据点不是独立缺陷数。', '',
        '## 验收边界与下一步', '',
        '有限搜索比较、同提案决定对照、既有独立多轮负结果及恢复归因审计均已完成。尚未证明跨候选稳定的契约发现/成本优势，也未证明同预算下历史拒绝反馈提高最终保护。不能将这些“没有证明优势”重新写成所有实验未完成。', '',
        '若继续扩大验证，优先在生成前锁定多个具备退化机会的候选任务、相同组件接口和普通/历史规则，再按固定预算独立运行；保留全部失败分母。应把本轮“读取相同历史的绝对检查”回顾对照纳入新前瞻协议，区分历史证据与相对保护保持算子的贡献。先证明有普通可接受提案进入门控判别，才扩大种子；不得用本批独立结果反向挑候选。本轮不自动启动该扩展。', '',
        '所有后续归因unknown保留；当前范围仅实际FIFO及人工故障。既有Ibex历史案例不能为本轮FIFO机制对照代替样本。仿真没有发现违例不等于形式化证明。', '',
        '## 复制执行', '', '```powershell',
        'wsl -- python3 scripts/research82_search_increment.py prepare --out deliverables/research82_search_NEW',
        'wsl -- python3 scripts/research82_search_increment.py run --out deliverables/research82_search_NEW',
        'wsl -- python3 scripts/research82_search_increment.py audit --run deliverables/research82_search_NEW --out deliverables/research82_audit_NEW',
        'wsl -- python3 scripts/research83_increment_audit.py --out deliverables/research83_increment_audit_NEW',
        '```']
    (out / 'SUMMARY.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    print('MECHANISM_REPORT', out, flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--search', type=Path, required=True)
    p.add_argument('--search-audit', type=Path, required=True)
    p.add_argument('--gate-audit', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    publish(a.search.resolve(), a.search_audit.resolve(), a.gate_audit.resolve(), a.out.resolve())
