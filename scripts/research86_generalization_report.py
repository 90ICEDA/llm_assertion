"""Report transfer denominators separately from mechanism causal claims."""
import argparse
from pathlib import Path
import research84_generalization as fifo
import research85_historical_transfer as hist

ROOT,read,dump=fifo.ROOT,fifo.read,fifo.dump


def report(search,history,audit,out):
    fifo.b.verify(search);hist.verify(history)
    assert read(search/'outcome.json')['status']=='completed'
    a=read(audit/'audit.json');assert a['passed']
    s=read(search/'summary.json');h=read(history/'summary.json')
    q=read(search/'qualification.json');units=read(search/'units.json');paired=read(search/'paired.json')
    out.mkdir(parents=True,exist_ok=False)
    costs={n:read(p/'cost.json')['total'] for n,p in [('search',search),('historical',history)]}
    milestone=dict(new_model_calls=0,new_model_accepted_versions=0,new_generation_success_rate=None,
        new_search_candidate_tasks=sum(x['selected'] for x in q),qualification_passes=sum(x['qualified'] for x in q),qualification_denominator=len(q),
        search_seeds=list(fifo.SEEDS),original_ibex166_independent_passes=h['independent166_passes'],
        original_ibex166_independent_denominator=3,original_ibex54_model_closed_loop=False,
        new_same_budget_recovery_successes=0,new_recovery_experiments=0,
        critical_unknown_search={m:r['unknown'] for m,r in s['methods'].items()},
        new_formal_proofs=0)
    public_rows=[r for p in read(search/'public_feedback.json').values() for r in p['results']]
    milestone['public_qualification_critical_unknown']=sum(r['unknown'] for r in public_rows)
    milestone['public_qualification_later_unknown']=sum(r['later_attribution_unknown'] for r in public_rows)
    dump(out/'milestones.json',milestone);dump(out/'cost.json',costs)
    findings=[]
    for m,r in s['methods'].items():
        c=[v for v in paired if v['comparator']==m]
        pairs=sorted({u['pair'] for u in units if u['method']==m})
        findings.append(dict(method=m,**r,candidate_denominator=len(pairs),
            candidates_with_discovery=sum(any(u['found'] for u in units if u['pair']==p and u['method']==m) for p in pairs),
            candidates_found_all_seeds=sum(all(u['found'] for u in units if u['pair']==p and u['method']==m) for p in pairs),
            earlier_tied_later=[sum(v[k] for v in c) for k in ('earlier','tied','later')],
            contract_only_task_seed_gaps=sum(len(v['contract_only']) for v in c),other_only_task_seed_gaps=sum(len(v['other_only']) for v in c)))
    dump(out/'search_results.json',findings)
    reference=read(search/'reference_costs.json');queries=read(search/'records.json')
    method_costs={}
    first_costs=[]
    for m in fifo.METHODS:
        rr=[r for r in queries if r['method']==m]
        cc=[r for r in reference if r.get('stage')=='search' and r.get('method')==m]
        method_costs[m]=dict(native_executions=sum(r['native_executions'] for r in rr),
            query_wall_seconds=sum(r['query_wall_seconds'] for r in rr),
            selector_wall_seconds=sum(r['selector_seconds'] for r in rr),
            reference={k:dict(calls=sum(c['kind']==k for c in cc),seconds=sum(c['wall_seconds'] for c in cc if c['kind']==k))
                for k in ('transaction_reference','sampling_reference','paired_obligation_judge')})
    for u in units:
        for key,first in u['first_query'].items():
            rr=[r for r in queries if (r['pair'],r['seed'],r['method'])==(u['pair'],u['seed'],u['method']) and r['query']<first]
            cc=[r for r in reference if r.get('stage')=='search' and
                (r['pair'],r['seed'],r['method'])==(u['pair'],u['seed'],u['method']) and r['query']<first]
            first_costs.append(dict(pair=u['pair'],seed=u['seed'],method=u['method'],key=key,first_query=first,
                fresh_native_executions=sum(r['native_executions'] for r in rr),
                common_public_executions=40,query_wall_seconds=sum(r['query_wall_seconds'] for r in rr),
                reference_calls=len(cc),reference_seconds=sum(r['wall_seconds'] for r in cc)))
    dump(out/'method_costs.json',method_costs);dump(out/'first_discovery_costs.json',first_costs)
    example=next((r for r in queries if r['method']=='contract_novelty' and r['first_new_keys']),None)
    if example:
        primary=example['pair'].split('__')[0]
        dump(out/'case_trace.json',dict(selection='First contract new-key query in fixed execution order, not selected for favorable comparative result',
            candidate=read(search/'candidates'/f'{primary}.json'),query=example,
            actual_selector=read(search/'queries'/example['pair']/f"s{example['seed']}"/example['method']/f"q{example['query']}/selection.json"),
            comparator_units=[u for u in units if u['pair']==example['pair'] and u['seed']==example['seed']],
            model_edit=None,recovery=None,scope='Actual search witness only; no invented edit/recovery trajectory.'))
    mechanism_exposure={}
    all_queries=[]
    for pair,pub in read(search/'public_feedback.json').items():
        all_queries += [(search/'public'/pair/f'q{i}',r) for i,r in enumerate(pub['results'])]
    all_queries += [(search/'queries'/r['pair']/f"s{r['seed']}"/r['method']/f"q{r['query']}",r) for r in read(search/'records.json')]
    for folder,r in all_queries:
        for mode in fifo.MODES[1:]:
            j=read(folder/'judgements'/f'{mode}.json')
            info=fifo.b.loop.inspect(j['target_rows'])
            row=mechanism_exposure.setdefault(mode,dict(queries=0,first_causal_detections=0,first_causal_misses=0,
                critical_unknown=0,excluded_later=0,valid_public_unexposed_gap_keys=set()))
            row['queries']+=1;row['first_causal_detections']+=len(info['detections']);row['first_causal_misses']+=len(info['misses'])
            row['critical_unknown']+=len(info['unknown']);row['excluded_later']+=len(j['exclusions'])
            row['valid_public_unexposed_gap_keys'].update(g['key'] for g in r['gaps'] if g.get('mode')==mode and g['key'] in r.get('public_unexposed_keys',[]))
    for row in mechanism_exposure.values():row['valid_public_unexposed_gap_keys']=sorted(row['valid_public_unexposed_gap_keys'])
    dump(out/'fault_exposure.json',mechanism_exposure)
    family54={}
    for r in h['results']:
        if r['case']=='ibex54':
            for f in r['families']:
                row=family54.setdefault(f['family'],dict(vectors=0,exposure=0,unknown=0,unexposed_seeds=0))
                row['vectors']+=f['observed'];row['exposure']+=f['target_exposure'];row['unknown']+=f['unknown'];row['unexposed_seeds']+=f['observed']==0
    dump(out/'ibex54_exposure.json',family54)
    excluded54=set(read(history/'ibex54/excluded_low16.json'))
    domain={f:dict(total=0,previously_used=0,remaining=0) for f in ('slli_hint','li_hint','lui_hint','right_shift_hint')}
    for word in range(65536):
        f=hist.family54(word)
        if f in domain:
            domain[f]['total']+=1
            domain[f]['previously_used']+=word in excluded54
            domain[f]['remaining']+=word not in excluded54
    dump(out/'ibex54_target_domain.json',dict(families=domain,
        scope='Enumeration of the declared semantic low16 input strata and exclusion membership only. Not a new native exhaustive proof or model-generation result.',
        next_valid_option='Existing target encodings may be explicit regression/development data, never new unseen targets. A different historical repair is needed for new target-mechanism generalization.'))
    dump(out/'claim_limits.json',dict(search_extra_over_all=s['extra_over_all'],
        generation='Not measured: archived proposals frozen, zero new calls. Never present search-seed success as model-seed success.',
        search_transfer='Additional archived candidates, depth2, three fixed seeds and expanded known mutation set, still one parent FIFO. Zero global novelty inferred.',
        history_gate='Prior retrospective extra rejection remains valid within its evidence. No new paired or multiround recovery trial here; no generalizable rejection/recovery success rate.',
        historical='Ibex166 tests frozen learned properties on original before/after RTL; Ibex54 tests engineering properties only. Neither measures search-policy advantage on that historical module.',
        sampling='Source-order selection and two-task budget cap, not random population sample. Candidate eligibility and target discovery use different denominators.',
        unavailable=['New-model generation success rate','Cross-parent controlled search increment','Prospective cross-parent same-budget recovery success rate','Whole-core correctness','Formal proof'],
        legacy_unknown=['stat provenance/timing specification unresolved in this campaign','original FIFO presented witness not established by synthetic axis_fifo faults']))
    lines=['# research84–86：推广复现及适用范围','',
        '本轮新增本地实跑；旧记录、候选性质及独立结果保持不变。没有远程调用，也没有新接受模型版本。归档候选重放不能代替新模型生成稳定性。','',
        f"FIFO 公共资格：{sum(x['qualified'] for x in q)}/{len(q)}；按预封存顺序选取 {sum(x['selected'] for x in q)} 个未参加 research82 的合格候选，其余失败或预算未选项完整保留。Depth=2、pipeline=1，3种子、5策略、每策略3查询。资格仅要求可执行和公共合法控制无误报，不等于整个案例或历史保护通过。公共阶段关键unknown共{milestone['public_qualification_critical_unknown']}条、后续归因unknown共{milestone['public_qualification_later_unknown']}条，未删除。",'',
        '两个新增比较故障为 corrupt 和 duplicate_payload，来自已有人工变异器；不是新发现的历史Bug。全部策略访问相同故障、候选和激励范围，公共反馈已曝光缺口先扣除；普通无重复策略用于区分通用避重与契约收益。','',
        '|策略|有新缺口的任务×种子|去重候选缺口|查询|关键unknown|后续归因unknown|重复动作|',
        '|---|---:|---:|---:|---:|---:|---:|']
    for r in findings:
        lines.append(f"|{r['method']}|{r['successful_tasks']}/{r['tasks']}|{len(r['keys'])}|{r['queries']}|{r['unknown']}|{r['later_unknown']}|{r['repeats']}|")
    lines+=['',f"契约相对所有对照并集独有缺口：**{len(s['extra_over_all'])}**。任务成功表示预算内至少发现一个公共反馈未曝光缺口，不表示整个案例保护通过。种子及波形变体不另算独立Bug。",'',
        f"新增比较机制的实际曝光：corrupt 检出{mechanism_exposure['corrupt']['first_causal_detections']}个、duplicate_payload 检出{mechanism_exposure['duplicate_payload']['first_causal_detections']}个首违例归因记录，两者首违例漏报均为{mechanism_exposure['corrupt']['first_causal_misses']}/{mechanism_exposure['duplicate_payload']['first_causal_misses']}。这些含各策略重复回放，不是独立Bug数；两种机制未带来公共反馈之外的新漏报，不能声称已在多个失效机制上验证搜索增量。完整曝光和后续归因unknown见fault_exposure.json。",'',
        '|对照|共同缺口中契约更早/相同/更晚|契约独有任务×种子缺口|对照独有|','|---|---|---:|---:|']
    for r in findings:
        if r['method']!='contract_novelty':lines.append(f"|{r['method']}|{'/'.join(map(str,r['earlier_tied_later']))}|{r['contract_only_task_seed_gaps']}|{r['other_only_task_seed_gaps']}|")
    lines+=['','未在3查询内发现为右删失，不虚构发现时间；编译和公共资格成本另列。参考判定逐次计时，含事后测量；契约额外消费自身判定选择下一动作。并行运行历史任务，墙钟耗时仅描述实际成本，不能当严格运行速度优势。','',
        f"原始 Ibex #166：冻结 research62 的真实模型集合，排除343个既有编码后，3种子各96词、跨种子不重叠，4配置，独立批次通过 **{h['independent166_passes']}/3**。",'',
        '|种子|指令数|检出证据点|漏报|误报|关键unknown|必要未触发|通过|','|---|---:|---:|---:|---:|---:|---:|---|']
    for r in h['results']:
        if r['case']=='ibex166':
            c=r['counts'];lines.append(f"|{r['seed']}|96|{c['detections']}|{c['misses']}|{c['false_positives']}|{c['unknown']}|{r.get('required_untriggered','不可用')}|{r['passed']}|")
    lines+=['','两项义务按真实时序曝光：OP首周期及保持阶段；BRANCH保持阶段违例，首周期检查正确输出与触发。全部性质误报检查、逐配置曝光和义务映射见各种子 summary.json。这里只验证原始 decoder 模块，不是整核或形式化证明。','',
        'Ibex #54 是另一原始历史模块，但仅为工程性质与独立编码参考的边界复现，不计入真实模型生成／搜索／细化闭环成功。旧 low16 编码全部排除，上16位变化不算新样本。','',
        '|#54编码族|新编码|原始违例曝光|unknown|无剩余新编码的种子|','|---|---:|---:|---:|---:|']
    for f,r in family54.items():lines.append(f"|{f}|{r['vectors']}|{r['exposure']}|{r['unknown']}|{r['unexposed_seeds']}|")
    lines+=['','未曝光项保留；控制输入无违例不等于目标曝光。三个新种子并非三个历史Bug。','',
        '|成本|原生编译|原生执行|编译秒|执行秒|','|---|---:|---:|---:|---:|']
    for n,c in costs.items():lines.append(f"|{n}|{c['native_compile_calls']}|{c['native_execute_calls']}|{c['native_compile_wall_seconds']:.3f}|{c['native_execute_wall_seconds']:.3f}|")
    lines+=['',f"FIFO 另重算 {a['native_replays_verified']} 份原生记录及事务／采样／配对判定；审计成本与发现成本分开。本轮新增模型调用/tokens/形式化查询均0；归档候选的原始生成成本保留在来源实验账本，不将其追计为免费生成。历史来源提交保存在 source_binding.json 与 source_protocol.json；项目Git号仍不可用，以内容哈希绑定。",'',
        '本轮没有新增防退化后续恢复实验。已有选定提案的额外拒绝证据不能推广为稳定恢复效果，也不能把冻结旧成功版本重放当成本轮恢复。下一步需要在另外的合格真实提案/父案例上固定普通接受与历史门控、固定预算，实际测量额外拒绝和拒绝后恢复；若普通规则本就拒绝，额外拒绝不成立。', '',
        '剩余的推广缺口：跨历史父案例的四类搜索受控比较；新增模型种子上的生成/多轮恢复成功率；#54完整真实模型闭环；更广FIFO参数/故障交叉复现。stat和原始FIFO presented既有unknown没有被本轮结果解决。不能将本轮描述为两个机制已具普遍优势。','',
        '复现（使用新输出目录，避免覆盖）：','```powershell',
        'wsl -- python3 scripts/research84_generalization.py prepare --out deliverables/research84_NEW',
        'wsl -- python3 scripts/research84_generalization.py run --out deliverables/research84_NEW',
        'wsl -- python3 scripts/research84_generalization.py audit --out deliverables/research84_NEW --audit-out deliverables/research84_NEW_audit',
        'wsl -- python3 scripts/research85_historical_transfer.py prepare --out deliverables/research85_NEW',
        'wsl -- python3 scripts/research85_historical_transfer.py run --out deliverables/research85_NEW','```','',
        '再次运行相同固定种子是复现，不是新的独立批次。若利用本批失败调整算法/候选，整批转开发，再封存新协议与新测试。']
    (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    paths=[search/'summary.json',search/'qualification.json',search/'units.json',search/'paired.json',search/'cost.json',history/'summary.json',history/'cost.json',audit/'audit.json']
    dump(out/'input_hashes.json',{p.relative_to(ROOT).as_posix():fifo.b.digest(p) for p in paths})
    print('REPORT86',milestone,flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    for n in ('search','history','audit','out'):ap.add_argument('--'+n,type=Path,required=True)
    a=ap.parse_args();report(a.search.resolve(),a.history.resolve(),a.audit.resolve(),a.out.resolve())
