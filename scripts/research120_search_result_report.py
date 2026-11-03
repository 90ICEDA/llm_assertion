"""Research117 result, selection dependence and cost audit; no new queries."""
import argparse
import copy
from collections import defaultdict
from pathlib import Path
import research117_search_preparation as s

b = s.b
ROOT, read, dump, sha = b.ROOT, b.read, b.dump, b.digest
policy = s.previous.policy


def run(root, native_audit, out):
    b.verify(root)
    assert read(root / 'outcome.json')['status'] == 'completed'
    native = read(native_audit / 'audit.json'); assert native['passed']
    records = read(root / 'records.json'); public = read(root / 'public_feedback.json')
    summary = read(root / 'summary.json'); refs = read(root / 'reference_costs.json')
    qualification = read(root / 'qualification.json'); known = set(read(root / 'historical_registry.json')['keys'])
    grouped = defaultdict(list)
    for record in records: grouped[(record['pair'], record['seed'], record['method'])].append(record)
    assert len(records) <= 108
    selected = [r for r in qualification if r['selected']]
    assert len(grouped) == len(selected) * len(s.SEEDS) * len(s.METHODS)
    groups = []; probes = []; discovery = defaultdict(list); examples = {}; unknown = []
    exposure = defaultdict(lambda: dict(queries=0, first_violation_rows=0, detections=0, misses=0, unknown=0))
    modes = read(root / 'protocol.json')['modes']
    for (pair, seed, method), rr in grouped.items():
        rr.sort(key=lambda r: r['query']); state = policy.factory(method, seed)
        history = []; seen = set(public[pair]['gap_keys']); actions = set(); repeats = 0
        first = {}
        for r in public[pair]['results']:
            history.append(policy.update(state, method, r['family'], r)); actions.add((r['family'], r['duration']))
        assert len(rr) == 3
        for q, r in enumerate(rr):
            before = copy.deepcopy(state)
            choice = policy.decision(state, method, seed, q, history)
            folder = root / 'queries' / pair / f's{seed}' / method / f'q{q}'
            saved = read(folder / 'selection.json')
            for mode in modes[1:]:
                targets = read(folder / 'judgements' / (mode + '.json'))['target_rows']
                info = b.loop.inspect(targets)
                counter = exposure[pair + '/' + mode]
                counter['queries'] += 1; counter['first_violation_rows'] += len(targets)
                for kind in ('detections', 'misses', 'unknown'): counter[kind] += len(info[kind])
            assert choice == saved['chosen'] and history == saved['permitted_history']
            action = (r['family'], r['duration'])
            assert (choice['family'], choice.get('duration')) == action
            assert r['first_new_keys'] == sorted(set(r['gap_keys']) - seen)
            assert r['public_unexposed_keys'] == sorted(set(r['gap_keys']) - set(public[pair]['gap_keys']))
            for key in r['first_new_keys']:
                first[key] = q + 1
                discovery[key].append(dict(pair=pair, seed=seed, method=method, query=q + 1, family=r['family'], duration=r['duration']))
                if key not in examples:
                    gap = next(g for g in r['gaps'] if g['key'] == key)
                    name = pair.split('__')[0]; candidate = read(root / 'candidates' / (name + '.json'))
                    examples[key] = dict(key=key, historically_known=key in known, witness=gap,
                        query_result=(folder / 'result.json').relative_to(ROOT).as_posix(),
                        candidate_properties=[a for a in candidate['assertions'] if gap['obligation'] in a['obligations']],
                        first_observation=discovery[key][-1])
            seen.update(r['gap_keys']); repeats += action in actions; actions.add(action)
            if r['unknown'] or r['later_attribution_unknown']:
                unknown.append(dict(pair=pair, seed=seed, method=method, query=q + 1,
                    critical_unknown=r['unknown'], later_attribution_unknown=r['later_attribution_unknown'],
                    result=(folder / 'result.json').relative_to(ROOT).as_posix()))
            if method == 'contract_novelty':
                for field in ('exposed', 'checks', 'triggers', 'protected', 'all_contract_scores'):
                    altered = copy.deepcopy(before)
                    if field == 'all_contract_scores': altered.method = 'ordinary_no_repeat'
                    else: getattr(altered, field).clear()
                    d = altered.choose(); other = (d['family'], d.get('duration'))
                    probes.append(dict(pair=pair, seed=seed, query=q + 1, removed=field,
                        actual=list(action), alternative=list(other), changed=action != other,
                        scope='Single decision on actual state with same RNG. Counterfactual future not executed. Not discovery/cost benefit.'))
            history.append(policy.update(state, method, r['family'], r))
        cc = [r for r in refs if r.get('stage') == 'search' and (r.get('pair'), r.get('seed'), r.get('method')) == (pair, seed, method)]
        groups.append(dict(pair=pair, seed=seed, method=method, keys=sorted(first), first_query=first,
            query_count=len(rr), native_executions=sum(r['native_executions'] for r in rr), repeats=repeats,
            query_wall_seconds=sum(r['query_wall_seconds'] for r in rr), selector_seconds=sum(r['selector_seconds'] for r in rr),
            reference_calls=len(cc), reference_seconds=sum(r['wall_seconds'] for r in cc),
            unknown=sum(r['unknown'] for r in rr), later_unknown=sum(r['later_attribution_unknown'] for r in rr)))
    costs = {}
    for method in s.METHODS:
        gg = [g for g in groups if g['method'] == method]
        keys = sorted({k for g in gg for k in g['keys']})
        assert keys == summary['methods'][method]['keys']
        costs[method] = dict(keys=keys, public_unexposed_unique_gaps=len(keys), historical_unseen_keys=sorted(set(keys) - known),
            **{name: sum(g[name] for g in gg) for name in ('query_count', 'native_executions', 'repeats', 'query_wall_seconds', 'selector_seconds', 'reference_calls', 'reference_seconds', 'unknown', 'later_unknown')})
    extra = sorted(set(costs['contract_novelty']['keys']) - set().union(*(set(c['keys']) for m, c in costs.items() if m != 'contract_novelty')))
    assert extra == summary['extra_over_all']
    paired = read(root / 'paired.json')
    contrasts = {method: dict(
        common_contract_earlier=sum(r['earlier'] for r in paired if r['comparator'] == method),
        common_tied=sum(r['tied'] for r in paired if r['comparator'] == method),
        common_contract_later=sum(r['later'] for r in paired if r['comparator'] == method),
        contract_only_task_seed_keys=sum(len(r['contract_only']) for r in paired if r['comparator'] == method),
        comparator_only_task_seed_keys=sum(len(r['other_only']) for r in paired if r['comparator'] == method))
        for method in s.METHODS if method != 'contract_novelty'}
    physical = read(root / 'cost.json')['total']
    common_native = sum(r['native_executions'] for p in public.values() for r in p['results'])
    search_native = sum(r['native_executions'] for r in records)
    assert native['native_replays_verified'] == common_native + search_native
    assert physical['model_calls'] == physical['formal_calls'] == 0
    sensitivity = {field: dict(changed=sum(p['changed'] for p in probes if p['removed'] == field),
        decisions=sum(p['removed'] == field for p in probes)) for field in ('exposed', 'checks', 'triggers', 'protected', 'all_contract_scores')}
    inventory = [dict(key=k, historically_known=k in known, observations=discovery[k]) for k in sorted(discovery)]
    public_unknown = dict(critical=sum(r['unknown'] for p in public.values() for r in p['results']),
        later=sum(r['later_attribution_unknown'] for p in public.values() for r in p['results']))
    result = dict(passed=True, query_count=len(records), selected_pairs=[r['pair'] for r in selected],
        qualified_candidates=sum(r['qualified'] for r in qualification), inventory_candidates=len(qualification),
        public_unexposed_union_count=len(discovery), historical_unseen_union_count=len(set(discovery) - known),
        contract_exclusive_count=len(extra), contract_exclusive_keys=extra, methods=costs, contrasts=contrasts,
        sensitivity=sensitivity, public_unknown=public_unknown, recorded_physical_cost=physical,
        search_native_executions=search_native, common_public_native_executions=common_native,
        native_non_query_residual=physical['native_execute_calls'] - search_native - common_native,
        audit_native_replays_verified=native['native_replays_verified'], model_calls=0, formal_calls=0,
        new_accepted_assertion_versions=0, new_independent_assertion_tests=0,
        scope='Development search replication, Depth2 pipeline1 actual FIFO RTL plus artificial faults. Same2 candidate tasks across seeds, not independent parent bugs. Unknown preserved.',
        script_sha256=sha(Path(__file__)))
    out.mkdir(parents=True, exist_ok=False)
    for name, value in [('result', result), ('gap_inventory', inventory), ('examples', list(examples.values())),
                        ('selection_interventions', probes), ('unknown_queries', unknown), ('per_task_cost', groups), ('fault_exposure', dict(exposure))]:
        dump(out / (name + '.json'), value)
    names = dict(ordinary='普通补测', candidate_disagreement='候选对分歧', raw_difference='普通差分', coverage_sweep='固定覆盖', ordinary_no_repeat='普通避重', contract_novelty='契约搜索')
    lines = ['# research117 / 120：封存搜索比较实跑结果', '',
        f'完成 **{len(records)}/108** 次搜索查询；公共资格 **{result["qualified_candidates"]}/{len(qualification)}**，按封存顺序选中 **{len(selected)}** 个候选任务。三个固定种子、六策略、每任务每组3查询。新增模型调用、断言修改、独立断言验收均0。', '',
        '|策略|发现缺口的任务×种子|公共之外去重缺口|重复动作|查询|原生执行|关键unknown|后续归因unknown|', '|---|---:|---:|---:|---:|---:|---:|---:|']
    for m in s.METHODS:
        c = costs[m]; stats = summary['methods'][m]
        lines.append(f'|{names[m]}|{stats["successful_tasks"]}/{stats["tasks"]}|{len(c["keys"])}|{c["repeats"]}|{c["query_count"]}|{c["native_executions"]}|{c["unknown"]}|{c["later_unknown"]}|')
    lines += ['', f'契约相对所有对照并集独有缺口：**{len(extra)}**。公共之外缺口并集 **{len(discovery)}**，其中此前research82/84登记之外 **{len(set(discovery) - known)}**。新随机波形不重复计新缺口；历史已知缺口不称新发现Bug。', '',
        '|对照|共同缺口契约更早/相同/更晚|契约独有任务×种子缺口|对照独有|', '|---|---:|---:|---:|']
    for m, c in contrasts.items(): lines.append(f'|{names[m]}|{c["common_contract_earlier"]}/{c["common_tied"]}/{c["common_contract_later"]}|{c["contract_only_task_seed_keys"]}|{c["comparator_only_task_seed_keys"]}|')
    lines += ['', '以上为实际首次查询先后；三查询内未找到按预算删失，不能虚构发现时间。固定预算总查询相同，较早发现不等于总成本减少。候选×种子缺口不是独立Bug。', '',
        '|移除的契约信息|实际选择改变/决策点|', '|---|---:|']
    for field, value in sensitivity.items(): lines.append(f'|{field}|{value["changed"]}/{value["decisions"]}|')
    lines += ['', '敏感性只在实际历史状态及同一随机状态上作单步重算，未执行反事实未来轨迹。选择变化不是额外发现证明。all_contract_scores保留普通避重，以免把通用去重算为契约独有收益。', '',
        f'成本：搜索原生执行 **{search_native}**、公共资格执行 **{common_native}**；物理账本执行 **{physical["native_execute_calls"]}**，其中非查询残差 **{result["native_non_query_residual"]}**；原生编译 **{physical["native_compile_calls"]}**。参考模型调用 **{len(refs)}**，各类判定、选择、查询及首次发现成本见机器可读记录。参考时间包含在query墙钟内，不二次相加；固定执行顺序下墙钟只作描述，不声称严格速度优势。', '',
        f'原生审计复核 **{native["native_replays_verified"]}** 份执行日志、事务参考、触发/失败标记及波形；审计判定成本另列，不混入搜索成本。公共资格关键unknown **{public_unknown["critical"]}**、后续归因unknown **{public_unknown["later"]}**；所有未选、失败及unknown均保留。', '',
        '范围：实际axis_fifo，Depth=2、pipeline=1，加既有人工故障。任务与候选来自封存开发目录，不是新历史父Bug；本次不生成或细化SVA，不检验防退化恢复，也不进行冻结后独立断言验收。research113/116独立结果未参与选择或规则修改。', '',
        '完整逐缺口首次成本：运行目录first_discovery_actual_cost.json；逐候选资格：qualification.json；全部unknown与例子见本报告目录JSON。', '',
        '各候选/故障的首违例实际曝光、检出、漏报和unknown另存fault_exposure.json；这些含各方法重复回放，不是独立Bug。没有新增缺口不能代替完整保护或曝光证明。', '',
        '只读复核（不重新执行查询）：', '```powershell',
        f'wsl -- python3 scripts/research117_search_preparation.py audit --out {root.relative_to(ROOT).as_posix()} --audit-out deliverables/research117_native_audit_NEW',
        f'wsl -- python3 scripts/research120_search_result_report.py --run {root.relative_to(ROOT).as_posix()} --native-audit {native_audit.relative_to(ROOT).as_posix()} --out deliverables/research120_report_NEW', '```']
    (out / 'SUMMARY.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    example_lines = ['# 实际搜索见证', '', '全部去重缺口保存于examples.json；以下最多展示两个，未修改断言。', '']
    for e in list(examples.values())[:2]:
        w = e['witness']; observation = e['first_observation']
        example_lines += ['## ' + e['key'], '',
            f'首次保存位置：{observation["pair"]} / {observation["method"]} / seed{observation["seed"]} / query{observation["query"]}；激励{observation["family"]}，持续{observation["duration"]}。',
            f'义务：{w["obligation"]}；失效机制：{w["mechanism"]}；类型：{w["kind"]}；历史已知：{e["historically_known"]}。',
            '当前候选相关性质：', '```systemverilog']
        example_lines += [a['property'] for a in e['candidate_properties']] + ['```',
            '实际触发分类：' + str(w.get('trigger_class', '不适用/未提供')),
            '独立验证条件：' + str(w.get('validation', {}).get('conditions', '合法参考上的原生误报，见原始记录')),
            '原始查询记录：`' + e['query_result'] + '`', '原生回放及波形目录：`' + w['replay_source'] + '`', '']
        validation = w.get('validation', {})
        if validation.get('samples'):
            example_lines += ['原生采样片段：', '', '|cycle|rst|svalid|sready|mvalid|mready|mdata|', '|---:|---:|---:|---:|---:|---:|---:|']
            for sample in validation['samples'][:8]:
                example_lines.append('|' + '|'.join(str(sample[k]) for k in ('cycle', 'rst', 'svalid', 'sready', 'mvalid', 'mready', 'mdata')) + '|')
            example_lines += ['', '断言逐项触发与检出：' + str(validation.get('matching_assertions')), '',
                '请求按svalid&&sready计接受。完整事务对应、数据及响应周期保存在examples.json，不把呈现请求直接算作接受。', '']
    (out / 'CASE_TRACE.md').write_text('\n'.join(example_lines) + '\n', encoding='utf-8')
    files = [root / n for n in ('sealed.json', 'outcome.json', 'summary.json', 'records.json', 'cost.json', 'first_discovery_actual_cost.json')]
    files += [native_audit / 'audit.json']
    dump(out / 'bindings.json', {f.relative_to(ROOT).as_posix(): sha(f) for f in files})
    print('REPORT120', {k: result[k] for k in ('query_count', 'qualified_candidates', 'public_unexposed_union_count', 'historical_unseen_union_count', 'contract_exclusive_count', 'search_native_executions', 'audit_native_replays_verified')}, flush=True)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    for n in ('run', 'native-audit', 'out'): ap.add_argument('--' + n, type=Path, required=True)
    a = ap.parse_args(); run(a.run.resolve(), a.native_audit.resolve(), a.out.resolve())
