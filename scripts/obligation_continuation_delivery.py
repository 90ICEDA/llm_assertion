"""Rebuild final results from raw frozen runs. Never changes experimental data."""
import argparse
import collections
import concurrent.futures
import json
from pathlib import Path
import obligation_continuation as cont
from obligation_continuation import x, PRIOR

DELIVERY=None


def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def lines(p):return [json.loads(s) for s in p.read_text().splitlines() if s.strip()]


def integrity():
    x.OUT=x.ROOT/'deliverables'/cont.NAME
    files=read(PRIOR/'delivery/final_artifact_manifest.json')['files']
    def check(item):
        p,h=item;f=x.ROOT/p
        return None if f.exists() and x.sha(f)==h else p
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
        changed=[p for p in pool.map(check,files.items()) if p]
    x.dump(x.OUT/'historical_integrity.json',dict(checked=len(files),changed=changed,manifest_sha256=x.sha(PRIOR/'delivery/final_artifact_manifest.json')))
    assert not changed,changed
    print('HISTORICAL INTEGRITY',len(files),'unchanged',flush=True)


def physical():
    commands=[];groups=collections.defaultdict(lambda:dict(compiles=0,simulations=0,other_commands=0,command_wall_seconds=0.,sampled_cycles=0,statuses=collections.Counter(),cpu_seconds=None))
    for p in x.OUT.rglob('*.command.json'):
        r=read(p);relative=p.relative_to(x.OUT);part=relative.parts
        stage=part[1] if part[0]=='runs' else part[0]
        c=groups[stage];c['command_wall_seconds']+=r.get('wall_seconds',0)
        c['statuses'][r.get('status','exit_'+str(r.get('exit_code')))]+=1
        c['compiles' if p.name=='compile.command.json' else 'simulations' if p.name=='simulate.command.json' else 'other_commands']+=1
        commands.append(dict(path=x.rel(p),stage=stage,**r))
    for p in (x.OUT/'runs').rglob('trace.json'):
        stage=p.relative_to(x.OUT).parts[1];groups[stage]['sampled_cycles']+=len(read(p))
    x.dump(DELIVERY/'physical_commands.json',commands)
    x.dump(DELIVERY/'physical_costs.json',dict(stages=dict(groups),native_additional_commands=read(x.OUT/'native_modelsim/commands.json'),
        wall_sums_are_not_elapsed_time=True,model_costs_separate=True,formal_solver_calls=0,cpu_seconds=None,
        native_retry1_retry2_wall_seconds=None,native_compile_version_probe_wall_seconds=None,
        missing_costs='Command CPU, memory, monetary cost, two exploratory native retries and version/extra compile probes not instrumented. Query CPU is separately available in query_costs.json.'))
    return groups


def models():
    rows=[]
    for prefix,stage in [('interface_preflight','preflight'),('formal','formal'),('historical_generation','historical_generation_failed_v1'),('historical_generation_v2','historical_generation_v2'),('historical_formal','historical_formal')]:
        for p in (x.OUT/prefix/'models').glob('*/*/*/result.json'):
            r=read(p);k,arm,rnd=p.parts[-4:-1]
            rows.append(dict(stage=stage,case=k,arm=arm,round=rnd,path=x.rel(p),**{n:r.get(n) for n in ('status','model','digest','prompt_tokens','completion_tokens','wall_seconds','retries','error')}))
    summary=[]
    for stage in sorted({r['stage'] for r in rows}):
        rs=[r for r in rows if r['stage']==stage]
        summary.append(dict(stage=stage,calls=len(rs),statuses=dict(collections.Counter(r['status'] for r in rs)),
            prompt_tokens_known=sum(r['prompt_tokens'] or 0 for r in rs),completion_tokens_known=sum(r['completion_tokens'] or 0 for r in rs),
            unavailable_token_calls=sum(r['prompt_tokens'] is None or r['completion_tokens'] is None for r in rs),
            wall_seconds=sum(r['wall_seconds'] for r in rs),retries=sum(r['retries'] or 0 for r in rs)))
    x.dump(DELIVERY/'model_costs.json',dict(calls=rows,summary=summary))
    return rows,summary


def ledger():
    old=read(PRIOR/'diagnostics/problem_ledger.json');mins={r['record_id']:r for r in read(x.OUT/'minimization/index.json')}
    unknown={r['record_id']:r for r in read(x.OUT/'unresolved_diagnostics/records.json')};checks=[]
    assert len(old)==40 and len(mins)==31 and len(unknown)==9 and not mins.keys()&unknown.keys()
    for r in old:
        rid=r['record_id'];r['prior_record']=x.rel(PRIOR/'diagnostics/problem_ledger.json')+'#'+rid
        r['continuation']=mins.get(rid,unknown.get(rid));assert r['continuation'] is not None
        if rid in mins:
            m=mins[rid];new=[e for a in read(x.ROOT/m['minimal_run']/'independent_evidence.json') for e in a if e['kind']==m['kind']]
            expected={(z['obligation'],z['branch'],z['expected'],z['actual']) for z in r['expected_and_actual']}
            match=[e for e in new if {(z['obligation'],z['branch'],z['expected'],z['actual']) for z in e['obligations']}==expected]
            checks.append(dict(record_id=rid,values_and_kind_preserved=bool(match)))
            assert match,(rid,expected,new)
            r['continuation']['expected_and_actual']=match[-1]['obligations']
            r['continuation']['waveform']=m['minimal_run']+'/wave.vcd';r['continuation']['cycle_trace']=m['minimal_run']+'/trace.json'
        if r['case'] in ('spill','intr'):
            r['continuation']['formal_spec_status']='unresolved_by_explicit_user_decision'
            r['continuation']['decision']='user_spec_decision.json'
    x.dump(DELIVERY/'problem_ledger.json',old);x.dump(DELIVERY/'minimization_preservation.json',checks)
    return old


def acceptance(block):
    path=x.OUT/block;rs=read(path/'acceptance/results.json');qs=lines(path/'acceptance/queries.jsonl')
    assert len(rs)==len(qs)
    records=[]
    for r,q in zip(rs,qs):
        m=r['metrics'];den=dict(legal_cycles=0,first_target_events=0,later_target_events=0)
        for run in q['runs']:
            oracle=read(x.ROOT/run['run']/'independent_reference.json')
            if run['variant']=='correct':den['legal_cycles']+=sum(e['legal_prefix'] for e in oracle['events'])
            else:
                for e in oracle['events']:
                    if any(not c['conditional'] and not c['passed'] for c in e['checks']):
                        den['first_target_events' if e['first_violation'] else 'later_target_events']+=1
        records.append(dict(block=block,**{k:r[k] for k in ('case','arm','version','scenario')},cohort=r.get('cohort','real_historical'),
            **den,**{n:len(m[n]) for n in ('fp','first_misses','later_misses','causal_detections','attribution_unknown')},
            raw_fail_hit=m['raw_fail_hit'],status=m['status'],antecedent_hits=m['antecedent_hits'],obligations_checked=m['obligations_checked'],
            causal_obligations=sorted({c['obligation'] for e in m['causal_detections'] for c in e['transaction_obligations']})))
    totals=[]
    for key in sorted({(r['case'],r['arm'],r['version'],r['cohort']) for r in records}):
        sel=[r for r in records if (r['case'],r['arm'],r['version'],r['cohort'])==key]
        row=dict(zip(('case','arm','version','cohort'),key));row['scenarios']=len(sel)
        for n in ('legal_cycles','first_target_events','later_target_events','fp','first_misses','later_misses','causal_detections','attribution_unknown','raw_fail_hit'):row[n]=sum(r[n] for r in sel)
        row['unknown_scenarios']=sum(r['status']!='ok' for r in sel)
        row['causal_obligations']=sorted({o for r in sel for o in r['causal_obligations']})
        row['checked_branches']=dict(sum((collections.Counter(r['obligations_checked']) for r in sel),collections.Counter()))
        row['antecedent_hits']=sum(sum(r['antecedent_hits'].values()) for r in sel)
        hits=sum((collections.Counter(r['antecedent_hits']) for r in sel),collections.Counter())
        names={name for r in sel for name in r['antecedent_hits']}
        row['untriggered_variant_assertions']=sorted(name for name in names if hits[name]==0)
        totals.append(row)
    obligations=collections.defaultdict(collections.Counter)
    for r in rs:
        if r['version']!='final':continue
        for kind in ('first_misses','later_misses','causal_detections','attribution_unknown'):
            for e in r['metrics'][kind]:
                for c in e['transaction_obligations']:
                    obligations[(r['case'],r['arm'],r.get('cohort','real_historical'),c['obligation'],str(c['branch']))][kind]+=1
    details=[dict(zip(('case','arm','cohort','obligation','branch'),key),**dict(counts)) for key,counts in sorted(obligations.items())]
    x.dump(DELIVERY/f'{block}_acceptance_detail.json',dict(records=records,totals=totals,obligation_results=details,
        counts='an event violating multiple obligations appears once per obligation; never sum these as independent parent bugs'))
    return totals


def query_costs():
    stats=[]
    for p in sorted(x.OUT.rglob('*queries*.jsonl')):
        rs=lines(p)
        if not rs:continue
        paired='attempted_queries' in rs[0]
        for key in sorted({(r.get('case','mixed'),r.get('arm',r.get('method','all'))) for r in rs}):
            sel=[r for r in rs if (r.get('case','mixed'),r.get('arm',r.get('method','all')))==key]
            z=dict(log=x.rel(p),case=key[0],arm_or_method=key[1],records=len(sel),unit='one input/assertion-set evaluated on two RTL revisions' if paired else 'one branch diagnostic attempt; no equivalence to paired query',
                status_counts=dict(collections.Counter(r.get('status','unavailable') for r in sel)))
            for n in ('attempted_queries','compile_attempts','simulation_attempts','sim_cycles','candidate_cycle_evaluations','candidate_variant_evaluations','static_validation_attempts','cache_hits','retries','solver_calls','wall_seconds','cpu_seconds'):
                vals=[r[n] for r in sel if r.get(n) is not None]
                z[n]=sum(vals) if vals else None;z[n+'_unavailable_records']=len(sel)-len(vals)
            if 'cache_hit' in sel[0]:z['explicit_cache_hits']=sum(r['cache_hit'] for r in sel)
            stats.append(z)
    x.dump(DELIVERY/'query_costs.json',dict(records=stats,note='Do not add compile/simulation counts to physical_costs: these are two views of the same executions. Minimization cached rows have zero new physical execution; common/regression included in 14-query arm budget.'))
    return stats


def conditional_results():
    counts=collections.defaultdict(lambda:dict(checks=0,violations=0))
    for p in (x.OUT/'runs/unresolved/intr').glob('*/intr/*/independent_reference.json'):
        for e in read(p)['events']:
            for c in e['checks']:
                z=counts[p.parent.name+'/'+c['obligation']];z['checks']+=1;z['violations']+=not c['passed']
    spill=read(x.OUT/'specs_tools/spill_conditional_results.json')
    summary=dict(intr=dict(counts),spill=[dict(value=r['value'],alternate=r['invalid_payload_alternate'],
        common_valid_violations=r['common_valid_violations'],raw_zero_violations=len(r['raw_zero_interpretation_violations']),run=r['run']) for r in spill],
        formal_spec_unresolved=True,user_decision=x.rel(x.OUT/'user_spec_decision.json'),
        limit='Conditional scoped monitor checks; neither interpretation is promoted to formal specification. Raw-zero alternative is a stronger hypothetical bus constraint, not inferred from valid semantics.')
    x.dump(DELIVERY/'conditional_results.json',summary)
    return summary


def stat_impact():
    old=[q for q in lines(PRIOR/'search/queries.jsonl') if q['case']=='stat']
    new=lines(x.OUT/'stat_search_v2/queries.jsonl');results=[]
    for method in ('ordinary','disagreement','obligation'):
        a=[q for q in old if q['method']==method];b=[q for q in new if q['method']==method]
        ga,gb=cont.iso.gaps(a),cont.iso.gaps(b)
        rows=dict(method=method,old_queries=len(a),new_queries=len(b),old_gaps=len(ga),new_gaps=len(gb),
            added=sorted(gb-ga),removed=sorted(ga-gb),same_candidate_pool=True,comparison_across_RTL_versions_not_merged=True)
        for label,qs in [('old',a),('new',b)]:
            rows[label+'_cost']={n:sum(q[n] for q in qs) for n in ('wall_seconds','cpu_seconds','compile_attempts','simulation_attempts','sim_cycles')}
            evidence=[e for q in qs for e in q['evidence']]
            rows[label+'_raw_evidence']=len(evidence);rows[label+'_unique_evidence']=len({e['evidence_id'] for e in evidence})
        results.append(rows)
    x.dump(DELIVERY/'stat_version_impact.json',dict(results=results,old_records_relabelled=0,
        reason='Old independent monitor already marked original control overlap as a real design violation. Only new engineered legal-control comparison rerun; old legacy signatures remain version-specific.',
        deduplication='evidence_id includes candidate hash, obligation checks and exact reset-to-witness prefix; separate from candidate/kind/obligation gap grouping'))


def deliver(output_name='delivery'):
    global DELIVERY
    x.OUT=x.ROOT/'deliverables'/cont.NAME
    assert Path(output_name).name==output_name and output_name not in ('.','..')
    DELIVERY=x.OUT/output_name;DELIVERY.mkdir(exist_ok=False)
    for block,ncalls,nquery,naccept,nreg in [('formal',24,168,288,144),('historical_formal',8,56,48,48)]:
        b=x.OUT/block
        assert len(list((b/'models').glob('*/*/*/result.json')))==ncalls
        assert len(lines(b/'queries.jsonl'))==nquery
        assert len(lines(b/'acceptance/queries.jsonl'))==naccept
        assert len(lines(b/'postfreeze_regression/queries.jsonl'))==nreg
        groups=collections.Counter((q['case'],q['arm']) for q in lines(b/'queries.jsonl'))
        assert len(groups)==ncalls//2 and set(groups.values())=={14},groups
        for name in ('freeze.json','final_freeze.json'):
            assert all(x.sha(x.ROOT/p)==h for p,h in read(b/name).items()),(block,name)
    led=ledger();phys=physical();model_rows,model_summary=models();query_costs();conditional=conditional_results();stat_impact()
    initial_generation_calls=sum(r['stage'].startswith('historical_generation') for r in model_rows)
    assert initial_generation_calls==4 and len(model_rows)==35+initial_generation_calls
    all_totals=acceptance('formal')+acceptance('historical_formal')
    deltas=[]
    for after in [r for r in all_totals if r['version']=='final']:
        before=next(r for r in all_totals if (r['case'],r['arm'],r['cohort'],r['version'])==(after['case'],after['arm'],after['cohort'],'initial'))
        deltas.append(dict(case=after['case'],arm=after['arm'],cohort=after['cohort'],
            false_positive_initial=before['fp'],false_positive_final=after['fp'],false_positive_delta=after['fp']-before['fp'],
            causal_detection_initial=before['causal_detections'],causal_detection_final=after['causal_detections'],
            gained_causal_obligations=sorted(set(after['causal_obligations'])-set(before['causal_obligations'])),
            lost_causal_obligations=sorted(set(before['causal_obligations'])-set(after['causal_obligations'])),
            first_misses_initial=before['first_misses'],first_misses_final=after['first_misses'],
            warning='FP can censor miss observation; larger/smaller raw FN alone does not measure stronger/weaker protection'))
    x.dump(DELIVERY/'initial_final_deltas.json',deltas)
    regressions=[]
    for block in ('formal','historical_formal'):
        for r in read(x.OUT/block/'postfreeze_regression/results.json'):
            def causal(m):return {(e['cycle'],c['obligation']) for e in m['causal_detections'] for c in e['transaction_obligations']}
            before,after=causal(r['before']),causal(r['after'])
            regressions.append(dict(block=block,case=r['case'],arm=r['arm'],round=r['round'],source_query=r['source_query'],
                new_false_positive_witnesses=[e for e in r['new_witnesses'] if e[0]=='fp'],
                lost_causally_confirmed_protection=sorted(before-after),gained_causal_protection=sorted(after-before)))
    x.dump(DELIVERY/'regression_protection.json',regressions)
    comparison=[]
    for case,cohort in sorted({(r['case'],r['cohort']) for r in all_totals}):
        arms={r['arm']:r for r in all_totals if (r['case'],r['cohort'],r['version'])==(case,cohort,'final')}
        a,b,c,d=[arms[n] for n in 'ABCD']
        comparison.append(dict(case=case,cohort=cohort,D_minus_B_causal_obligation_count=len(d['causal_obligations'])-len(b['causal_obligations']),
            D_unique_vs_B=sorted(set(d['causal_obligations'])-set(b['causal_obligations'])),B_unique_vs_D=sorted(set(b['causal_obligations'])-set(d['causal_obligations'])),
            D_minus_C_false_positive_cycles=d['fp']-c['fp'],paired_scenarios=6,model_seed_blocks=1,formal_calls_per_arm=2,
            interpretation='bounded causal witnesses and legal false positives; not full necessary-obligation acceptance or statistical superiority'))
    x.dump(DELIVERY/'paired_comparisons.json',comparison)
    per_parent=[]
    for k in ('onehot','filter','fifo','spill','stat','intr','ibex'):
        cells=[r for r in led if r['case']==k];ms=[r for r in model_rows if r['case']==k]
        per_parent.append(dict(case=k,original_problem_cells=len(cells),original_known_failures=sum(r['original_status']=='known_failure' for r in cells),
            original_unknown=sum(r['original_status']=='unknown' for r in cells),minimized=sum(r['record_id'] in {m['record_id'] for m in read(x.OUT/'minimization/index.json')} for r in cells),
            category_counts=dict(collections.Counter(c for r in cells for c in r['categories'])),
            final_acceptance=[r for r in all_totals if r['case']==k and r['version']=='final'],
            model_calls_including_preflight=len(ms),prompt_tokens_known=sum(r['prompt_tokens'] or 0 for r in ms),completion_tokens_known=sum(r['completion_tokens'] or 0 for r in ms),
            model_wall_seconds=sum(r['wall_seconds'] for r in ms),unavailable_token_calls=sum(r['prompt_tokens'] is None for r in ms),
            parent_acceptance='not_established',
            limitation='not part of new refinement block; old scoped results retained' if k=='onehot' else 'spec unresolved; conditional experiments completed, no unconditional ranking' if k in ('spill','intr') else 'finite scoped traces; all required branch protections not established; native execution unavailable'))
    x.dump(DELIVERY/'parent_summary.json',per_parent)
    x.dump(DELIVERY/'completion.json',dict(interface_preflight='completed',historical_offline_proposals='23/23 executable; 10 infrastructure false rejections recovered; one historical timeout no response',
        stat_control='10/10 reference-confirmed; 108 same-budget affected queries completed',diagnostic_records='40/40 processed; 31 local minima; nine executed follow-ups',
        formal='24 model calls, 168 queries, 144 postfreeze regression queries completed',independent_acceptance='288 paired queries completed',
        real_historical=f'{initial_generation_calls} shared initial generation/syntax-repair calls, eight actual formal calls, 56 development queries, 48 regression queries, 48 heldout pairs completed',
        native_sva='tool restricted: compile supported but runtime unusable even without assertion',specification='spill/intr remain unresolved by explicit user choice',
        whole_parent_passes=0,unexecuted_due_to_external_conditions=['native SVA runtime cross-execution','unconditional spill payload and intr timing acceptance'],
        new_paid_resources=0,human_questions=2,human_response_messages=1,human_time_seconds=None))
    report=['# 设计义务指导搜索与断言细化：续作结果','',
        '本轮完成可执行的剩余实验，包括接口修复、40条逐项续诊、31条局部最小化、stat 修正对照、完整四组细化、新隔离验收，以及 Ibex #54 真实历史生成／修复对照。实验完成不等于断言验收通过；没有父 bug 整体验收通过，也不据局部命中宣称 D 总体优于对照。','',
        '## 范围与冻结','',
        '沿用历史648次主查询、72次补充查询和11/11反馈碰撞复现，不重做无关部分。旧三法均局部区分9/11对；filter自然池仍仅1/3可执行，未改池或冒称自然分歧目标有效。旧FIFO最终误报39/0/19/39仍为历史记录。新stat控制单独版本；108次必要补查得到11/11/11个缺口，旧13/13/8保留且不混计。','',
        '同一模型 qwen2.5-coder:7b-instruct，同一digest、温度0、种子20261013、384输出token、420秒超时、无重试；每父每臂2次模型调用、14次实际开发查询。A/B/C/D共同初始检查和每次修改后合法／违例回归不变。A固定补测与旧反馈；B普通变异搜索FP/FN；C义务查询且主动FN；D义务查询FP/FN。查询获得的信息按臂隔离。单个模型种子、两轮预算不支持总体统计优越性结论。','',
        '原三个人工父案例使用自然候选；其18条新保留输入、3个人工同类故障在正式细化前冻结。Ibex另外6条保留序列，64种新低16位编码，与开发及历史223条向量无编码交集；HINT架构等价不计为新独立bug。仅通过明确JSON接口发送公开契约和各臂开发反馈；私有监视器、补丁、保留输入及答案不发送。最终版本固定选择第二轮最后可执行提案，验收后未修断言。','',
        '## 接口、诊断与工具','',
        '10次历史接口拒绝均来自公开复位标量的权限遗漏；原提案不改写后23/23有响应提案可编译执行。1次180秒历史超时无响应和token，无法证明是服务故障还是资源耗尽。现有请求JSON、流式响应、AST提取、编译、执行、反馈、成本记录经3次真实调用全链预检；预检不混入正式结果。候选不支持的点号内部信号语法仍拒绝，不放宽语义制造成功。','',
        '31条见证均做到固定最初两拍复位、原目标和触发身份下的单样本删除局部最小；117次尝试＝60次物理执行＋57次显式缓存复用。输入值未最小化，不宣称全局最短。9条无语义见证逐条映射到48次分支执行尝试（24次filter静态语法拒绝、24次intr执行）及4次额外可达性配对查询：filter记录属于不支持语法，intr八条仍受采样规格限制。','',
        'spill invalid-payload与intr mask采样按用户明确决定保持未决；分别保存条件结果。RTL现状不替代规格。原生工具重新探测发现 Windows ModelSim 10.4 可编译探针，但推进时间即终止，不含断言的基准同样失败；因此属于执行环境限制。Icarus原生SVA语法探针失败；过程checker资格检查及异步历史复位检查完成，不能称原生SVA交叉验证完成。','',
        '## 独立验收：最终断言','',
        'FP分母为合法前缀采样；首次／后续FN分母为独立监视器判定的目标违例事件。此前已误报或未确认事务归属的fail-hit只进入“归属未知”，不算成功保护。相同合法控制在两个人工故障队列重复，不应相加为新的独立样本。','',
        '| 父案例 | 队列 | 组 | FP/合法拍 | 首次FN/目标 | 后续FN/目标 | 因果确认检测 | 归属未知 |','|---|---|---|---:|---:|---:|---:|---:|']
    for r in all_totals:
        if r['version']=='final':report.append(f"| {r['case']} | {r['cohort']} | {r['arm']} | {r['fp']}/{r['legal_cycles']} | {r['first_misses']}/{r['first_target_events']} | {r['later_misses']}/{r['later_target_events']} | {r['causal_detections']} | {r['attribution_unknown']} |")
    report+=['','## 主要配对比较','','D−B为因果确认义务种数差；不是整体必要义务通过数。D−C为误报拍数差，正数表示D更差。每行6对保留场景。','',
        '| 父案例 | 队列 | D−B义务种数 | D独有 | B独有 | D−C误报 |','|---|---|---:|---|---|---:|']
    for r in comparison:report.append(f"| {r['case']} | {r['cohort']} | {r['D_minus_B_causal_obligation_count']} | {','.join(r['D_unique_vs_B']) or '无'} | {','.join(r['B_unique_vs_D']) or '无'} | {r['D_minus_C_false_positive_cycles']} |")
    report+=['','初始到最终的全部配对变化见 `delivery/initial_final_deltas.json`。FIFO的A/B/C在新同类故障上从0增加到18次因果确认检测，合法误报从136降至0；原始目标仍有首次16次、后续16次漏报，不能称FIFO整体修好。filter没有改善；stat各组误报均高于初始60次，未建立保护增益。','',
            '逐次修改对全部已取得开发输入的回归见 `delivery/regression_protection.json`；明确保存新增误报及丢失的已确认因果保护，不将此前的误报屏蔽误当作保护。各义务／分支漏报、因果确认及归属未知见 `*_acceptance_detail.json` 的obligation_results；前件零触发单列untriggered_variant_assertions，不计空洞通过。']
    report+=['','## 实际模型成本','','未知tokens不记零；耗时为调用耗时之和，不是并行任务的总历时。编译、仿真、周期和失败成本另见physical_costs.json。','',
        '| 阶段 | 调用 | 状态 | 已知输入tokens | 已知输出tokens | tokens不可得调用 | 秒 |','|---|---:|---|---:|---:|---:|---:|']
    for r in model_summary:report.append(f"| {r['stage']} | {r['calls']} | {r['statuses']} | {r['prompt_tokens_known']} | {r['completion_tokens_known']} | {r['unavailable_token_calls']} | {r['wall_seconds']:.2f} |")
    report+=['','## 最小复现与日志入口','',
        'stat原始19/73复现：从仓库根目录运行 `sh deliverables/obligation_completion_audit_20261013_r01/replays/stat_overlap/reproduce.sh`。两拍复位后t2输入19、t3输入73，t4应输出19而旧RTL输出73。新对照见 `stat_control/patch.diff` 与 `runs/stat_control/19_73/stat/correct/reproduce.sh`；补丁属于本研究人工修复，不冒充真实历史提交。每笔事件按触发时捕获长度，期限trigger+2，复位取消，重叠分别配对。','',
        '最终FIFO B/D最小对照：两拍复位后push=1、pop=0、data=199，合法控制empty=0；新同类故障错误输出empty=1。B接受合法控制并报出目标违例，D反而误报合法控制。见 `final_examples/fifo_B_D.json`；运行 `sh deliverables/obligation_continuation_20261013_r01/runs/final_examples/fifo_B/fifo/buggy/reproduce.sh`。这2次配对查询是已消耗保留集的说明性复现，不是新增独立泛化证据。','',
        '逐条最小复现命令、输入、原见证、缩减见证、波形、逐周期独立判定及成本映射见 `delivery/problem_ledger.json`、`minimization/index.json`。义务来源及必要分支见 `frozen/*/contract.json`；新验收的义务／分支明细见 `delivery/*_acceptance_detail.json`，逐轮回归见两个区块的 `postfreeze_regression/`。','',
        '真实历史：`historical_formal/` 保存 Ibex #54来源、修复前后原始RTL、原始回归引用、独立旗标监视器资格检查、共享模型生成初始候选、8次正式调用、保留验收。生成器只见公开ISA契约和端口，不见修复补丁。范围为五类RV32C指令的合法性／压缩标志；解码数据补丁的原始回归单独保留，不宣称全ISA保护。','',
        '协议与哈希：`formal/freeze.json`、`historical_formal/freeze.json`及各自`final_freeze.json`。所有模型请求／响应、接口错误、候选修改、查询及回归均保留；`delivery/model_costs.json`、`physical_costs.json`按阶段分别计账。人工澄清2问、1条答复，人工耗时不可得。','',
        '## 完成状态与剩余外部条件','',
        '可执行的四组与真实案例实验已完整执行；方法失败、退化和未知照实保留。未完成的是可工作的原生SVA执行交叉验证，以及未决规格下的无条件验收；所需最小输入分别是能运行noassert.sv的原生工具环境、正式spill/intr规格决定。用户已要求后两项保持未决，故本轮不再请求擅定。没有以人工修复替代模型结果，也没有因结果不理想停止某组。','',
        '重建统计：从仓库根目录运行 `python3 scripts/obligation_continuation_delivery.py deliver --output-name rebuilt_01`；输出到新的目录，不覆盖封存报告。历史封存完整性见 `historical_integrity.json`。主实验脚本分别为 `obligation_continuation_experiment.py`、`obligation_ibex_experiment.py`；新实验须使用新的run编号，避免覆盖。','']
    parent_table=['## 逐父案例诊断与验收状态','','| 父案例 | 原已知失败 | 原未知 | 局部最小见证 | 本轮状态 |','|---|---:|---:|---:|---|']
    if initial_generation_calls>1:
        report[report.index('## 接口、诊断与工具')+2:report.index('## 接口、诊断与工具')+2]=[
            f'Ibex共享初始生成共{initial_generation_calls}次真实调用。v1的3次调用均因模型使用未声明imm6/bit12而正确拒绝，属于候选错误，该区块按预算结束失败。另建v2，只要求生成一条断言并强调概念字段名不是端口，同一模型生成首个可执行结果；所有组共享这个新候选。全部失败与初始生成成本单独保留，正式每组2次调用不变。','']
    for r in per_parent:
        status='历史范围保留；本轮无新增细化' if r['case']=='onehot' else '条件实验完成，规格未决' if r['case'] in ('spill','intr') else '完整四组与独立验收已执行；整体通过未建立'
        parent_table.append(f"| {r['case']} | {r['original_known_failures']} | {r['original_unknown']} | {r['minimized']} | {status} |")
    parent_table+=['','intr条件检查：','', '| RTL版本标签 | 条件解释 | 违例/检查 |','|---|---|---:|']
    for name,r in conditional['intr'].items():
        variant,obligation=name.split('/');parent_table.append(f"| {variant} | {obligation} | {r['violations']}/{r['checks']} |")
    parent_table+=['','spill全部8次运行的共同valid义务无违例；无效数据总线改动在raw-zero假设下产生差异，详见conditional_results.json。此处的correct/buggy只是版本标签，不是独立正确性结论。','']
    position=report.index('## 独立验收：最终断言');report[position:position]=parent_table
    report_path=x.OUT/'REPORT.md' if output_name=='delivery' else DELIVERY/'REPORT.md'
    assert not report_path.exists();report_path.write_text('\n'.join(report))
    x.dump(DELIVERY/'source_manifest.json',{x.rel(p):x.sha(p) for p in (x.ROOT/'scripts').glob('*obligation*continuation*.py')})
    print('DELIVERY complete',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['integrity','deliver']);p.add_argument('--output-name',default='delivery');a=p.parse_args()
    if a.action=='deliver':deliver(a.output_name)
    else:integrity()
