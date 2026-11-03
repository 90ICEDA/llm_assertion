"""Read-only raw-data aggregation for v3; no model or simulation calls."""
import collections,csv,itertools,json,math,random
import run_contract_v3 as x
import contract_v2_report as old_report

OUT=x.OUT;ROOT=x.ROOT;read=x.read;dump=x.dump;rel=x.rel;v=x.v
# Replay records can carry an explicit null control descriptor; it means no control.
def compat_read(p):
    r=read(p)
    if isinstance(r,dict) and r.get('component_control','absent') is None:r.pop('component_control')
    return r
old_report.read=compat_read

def table(name,rows):
    dump(OUT/(name+'.json'),rows)
    if rows:
        keys=list(dict.fromkeys(k for r in rows for k in r))
        with (OUT/(name+'.csv')).open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=keys);w.writeheader()
            w.writerows({k:json.dumps(z,ensure_ascii=False) if isinstance(z,(dict,list)) else z for k,z in r.items()} for r in rows)

def parent(item,results):
    cp=item['checkpoint'];k=item['case'];unknown=set(z for r in results for z in r['unknown_reasons'])
    if k in ['spill','intr']:unknown.add('spec_unresolved')
    return {'case':k,'parent_bug_id':v.IDS[k],'method':item['arm'],'step':cp['step'],'final':item['final'],
      'complete_pass':None if unknown else all(r['conditional_complete_pass'] for r in results),'unknown':bool(unknown),'unknown_reasons':sorted(unknown),
      'false_positive':any(r['false_positive'] for r in results),'miss':any(r['miss'] for r in results),'not_triggered':any(r['not_triggered'] for r in results),
      'fp_cycles_by_view':{r['view']:r['fp_cycles'] for r in results},'miss_cycles_by_view':{r['view']:r['miss_cycles'] for r in results},
      'coverage_by_view':{r['view']:r['coverage'] for r in results},'nonempty_by_branch':{r['view']:r['nonempty_by_branch'] for r in results},
      'expression_signature':item['evaluation']['expression_signature'],'historical_fix':False,
      **{n:cp.get(n) for n in ['compile_invocations','simulation_invocations','effective_simulations','effective_cycles','active_cycles','transactions','prompt_tokens','completion_tokens','logical_model_calls','logical_model_wall_seconds','validation_wall_seconds','history_bits_permission']}}

def workload(cp,runs):
    grouped=collections.Counter()
    for name in cp['run_ids']:
        r=runs[name]
        if not r.get('effective_simulation'):continue
        key=(r['case'],r['variant'],r['input_sha256'],r['rtl_sha256'],json.dumps(r['parameters'],sort_keys=True),r['sampled_cycles'],r['transactions'])
        grouped[key]+=1
    return [{'case':k[0],'variant':k[1],'input_sha256':k[2],'rtl_sha256':k[3],'parameters':json.loads(k[4]),'cycles_per_simulation':k[5],'transactions_per_simulation':k[6],'multiplicity':n} for k,n in sorted(grouped.items())]

def matched(index,cp_results,runs):
    protocol=read(OUT/'protocol.json');result=[]
    bykey={(r['case'],r['method'],r['step']):r for r in cp_results}
    for resource in ['effective_simulations','effective_cycles']:
        for k in v.IDS:
            for threshold in protocol['checkpoints'][resource]:
                chosen={}
                for arm in v.ARMS:
                    candidates=[it for it in index if it['case']==k and it['arm']==arm and it['checkpoint'][resource]==threshold]
                    chosen[arm]=min(candidates,key=lambda it:it['checkpoint']['step']) if candidates else None
                available=[a for a,z in chosen.items() if z];cohort=[bykey[(k,a,z['checkpoint']['step'])] for a,z in chosen.items() if z]
                for arm,it in chosen.items():
                    base={'resource':resource,'checkpoint':threshold,'case':k,'parent_bug_id':v.IDS[k],'method':arm,'reached':bool(it),'all_eight_reached':len(available)==8,'available_methods':available,'rule':'first completed evaluation at exact resource; no last-under-limit substitution'}
                    if it:
                        cp=it['checkpoint'];r=bykey[(k,arm,cp['step'])]
                        base.update({key:r[key] for key in ['step','complete_pass','unknown','unknown_reasons','false_positive','miss','not_triggered','effective_simulations','effective_cycles','transactions','compile_invocations','prompt_tokens','completion_tokens','logical_model_calls','validation_wall_seconds']})
                        base['workload']=workload(cp,runs)
                    else:base.update(complete_pass=None,unknown=True,unknown_reasons=['checkpoint_not_reached'])
                    result.append(base)
    return result

def reports():
    x.check_freeze()
    runrows=[read(p) for p in sorted((OUT/'runs').rglob('result.json'))];runs={r['run_id']:r for r in runrows};table('run_results',runrows)
    index=read(OUT/'hidden_evaluations.json');cache={};obligations=[];branches=[];parents=[];checkpoints=[];conditional=[]
    for it in index:
        e=it['evaluation'];key=(e['case'],e['expression_signature'])
        if key not in cache:
            results,oo,bb=old_report.evaluate_saved(e);cache[key]=results;obligations+=oo;branches+=bb
        rr=cache[key];p=parent(it,rr);checkpoints.append(p)
        if it['final']:parents.append(p);conditional += [{**r,'method':it['arm']} for r in rr]
    table('obligation_acceptance',obligations);table('branch_acceptance',branches);table('parent_results',parents);table('conditional_results',conditional);table('checkpoint_results',checkpoints)
    matches=matched(index,checkpoints,runs);table('common_effective_budget_checkpoints',matches)
    budget_pairs=[]
    for resource in ['effective_simulations','effective_cycles']:
        for threshold in read(OUT/'protocol.json')['checkpoints'][resource]:
            records={(r['case'],r['method']):r for r in matches if r['resource']==resource and r['checkpoint']==threshold}
            for a,b in itertools.combinations(v.ARMS,2):
                both=[k for k in v.IDS if records[(k,a)]['reached'] and records[(k,b)]['reached']]
                known=[k for k in both if not records[(k,a)]['unknown'] and not records[(k,b)]['unknown']]
                budget_pairs.append({'resource':resource,'checkpoint':threshold,'method_a':a,'method_b':b,'both_reached_parents':both,'common_known_parents':known,'unknown_pairs':len(both)-len(known),'unreached_pairs':len(v.IDS)-len(both),
                  'a_success':sum(records[(k,a)]['complete_pass'] is True for k in known),'b_success':sum(records[(k,b)]['complete_pass'] is True for k in known),
                  'same_workload_all_common':all(records[(k,a)]['workload']==records[(k,b)]['workload'] for k in known) if known else None,
                  'a_prompt_tokens':sum(records[(k,a)]['prompt_tokens'] for k in both),'b_prompt_tokens':sum(records[(k,b)]['prompt_tokens'] for k in both),
                  'a_completion_tokens':sum(records[(k,a)]['completion_tokens'] for k in both),'b_completion_tokens':sum(records[(k,b)]['completion_tokens'] for k in both),
                  'a_compiles':sum(records[(k,a)]['compile_invocations'] for k in both),'b_compiles':sum(records[(k,b)]['compile_invocations'] for k in both),
                  'scope':'intersection only; unreached excluded and listed, no population-level rate claim'})
    table('common_budget_pairwise',budget_pairs)
    # Trace every physical cost, including syntax failures and pilot-retry archives.
    costs=[]
    for p in sorted(OUT.rglob('compile.command.json')):
        cc=read(p);ss=read(p.parent/'simulate.command.json') if (p.parent/'simulate.command.json').exists() else None
        rr=read(p.parent/'result.json') if (p.parent/'result.json').exists() else {}
        relative=p.relative_to(OUT).parts
        phase=('method' if '/runs/methods/' in str(p) else 'hidden_acceptance' if '/runs/hidden/' in str(p) else 'old_candidate_replay' if '/runs/replay/' in str(p) else relative[0])
        costs.append({'phase':phase,'directory':rel(p.parent),'compile_attempts':1,'compile_exit_code':cc['exit_code'],'compile_status':cc['status'],'compile_seconds':cc['wall_seconds'],
           'simulation_attempts':int(ss is not None),'simulation_status':ss['status'] if ss else None,'simulation_exit_code':ss['exit_code'] if ss else None,
           'simulation_seconds':ss['wall_seconds'] if ss else 0,'effective_simulation':rr.get('effective_simulation'),
           'sampled_cycles':rr.get('sampled_cycles'),'transactions':rr.get('transactions'),'retry':relative[0]=='failed_attempts'})
    table('physical_validation_costs',costs)
    models=[]
    for p in sorted((OUT/'model_calls').rglob('result.json')):
        r=read(p);raw=read(p.parent/'response.raw.json') if (p.parent/'response.raw.json').exists() else {}
        models.append({'call':rel(p.parent),'status':r['status'],'prompt_tokens':raw.get('prompt_eval_count'),'completion_tokens':raw.get('eval_count'),'wall_seconds':r['wall_seconds'],
           'server_total_duration_ns':raw.get('total_duration'),'load_duration_ns':raw.get('load_duration'),'retry':False,'server_prompt_cache':'unknown: API supplies no complete cache ledger','response_sha256':x.sha(p.parent/'response.raw.json') if raw else None})
    table('physical_model_costs',models)
    ledger=[]
    for it in index:
        cp=it['checkpoint'];unique={}
        for name in cp['run_ids']:
            r=runs[name]
            if r.get('effective_simulation'):unique[(r['checker_sha256'],r['rtl_sha256'],r['input_sha256'])]=r['sampled_cycles']
        ledger.append({**cp,'candidate':it['evaluation']['candidate'],'method':it['arm'],'final':it['final'],'workload':workload(cp,runs),
          'distinct_effective_checker_design_input_units':len(unique),'repeat_effective_executions':cp['effective_simulations']-len(unique),'distinct_effective_cycles':sum(unique.values()),
          'repeat_scope':'diagnostic only; identical proposals or pool slots re-evaluated by the frozen fixed-attempt algorithm, not extra padding to attain checkpoints; physical executions and novel evidence are distinguished'})
    table('budget_ledger',ledger)
    pool=read(OUT/'pool_freeze.json')['entries'];table('shared_pool_costs',[{'case':r['case'],'slot':r['slot'],'source':r['original_call'],'new_physical_calls':0,'original_prompt_tokens':r['prompt_tokens'],'original_completion_tokens':r['completion_tokens'],'original_seconds':r['original_wall_seconds'],'logical_charge':'each arm charged only consumed slots; shared generation originally paid once'} for r in pool])
    methods=[];metrics=[]
    for arm in v.ARMS:
        pp=[r for r in parents if r['method']==arm];known=[r for r in pp if not r['unknown']];n=len(known);s=sum(r['complete_pass'] is True for r in known)
        rng=random.Random(20261009);boots=sorted(sum(rng.choice(known)['complete_pass'] for _ in range(n))/n for _ in range(2000)) if n else []
        z={'method':arm,'parent_count':len(pp),'known_parents':n,'unknown_parents':len(pp)-n,'complete_pass':s,'success_rate_known':s/n if n else None,
           'false_positive_parent_flags':sum(r['false_positive'] for r in pp),'miss_parent_flags':sum(r['miss'] for r in pp),'not_triggered_parent_flags':sum(r['not_triggered'] for r in pp),
           **{key:sum(r[key] or 0 for r in pp) for key in ['effective_simulations','effective_cycles','compile_invocations','simulation_invocations','prompt_tokens','completion_tokens','logical_model_calls','logical_model_wall_seconds','validation_wall_seconds','history_bits_permission']}}
        z.update(model=v.MODEL,selection_scope='candidate_level',aggregation_unit='parent_bug',k=1,metric='finite_frozen_contract_success',value=s/n if n else None,
          candidate_observation_count=n,case_count=n,parent_bug_count=n,deduplicated=True,dedup_key='parent_bug_id',parent_aggregation='all_scenarios_for_one_parent',overlap_status='non_overlap',
          sample_definition='one frozen output per parent; unknown excluded; compare matched parent sets only',ci_level=0.95,ci_lower=boots[49] if boots else None,ci_upper=boots[1949] if boots else None,
          ci_method='percentile cluster bootstrap; small purposive cohort',bootstrap_unit='parent_bug_id',bootstrap_repetitions=2000,random_seed=20261009,
          failure_flag_scope='multiple flags allowed; includes conditionally observed failures in specification-unknown cells, without converting unknown status to failure')
        methods.append(z)
        for unit in ['candidate','case','parent_bug']:
            metrics.append({'model':v.MODEL,'method':arm,'selection_scope':'candidate_level','selection_scope_detail':'one frozen selected output of method, not any-of-k success','aggregation_unit':unit,'k':1,'metric':'finite_frozen_contract_success','value':s/n if n else None,'candidate_observation_count':n,'case_count':n,'parent_bug_count':n,'unknown_parent_count':len(pp)-n,
              'deduplicated':True,'dedup_key':'parent_bug_id','parent_aggregation':'all_scenarios_for_one_parent','overlap_status':'non_overlap','sample_definition':'one final assertion per parent; unknown excluded; no population generalization',
              'ci_level':0.95,'ci_lower':boots[49] if boots else None,'ci_upper':boots[1949] if boots else None,'ci_method':'percentile cluster bootstrap over known parent bugs; purposive small sample','bootstrap_unit':'parent_bug_id','bootstrap_repetitions':2000,'random_seed':20261009})
    table('method_comparison',methods);table('metrics',metrics)
    paired=[]
    for a,b in itertools.combinations(v.ARMS,2):
        aa={r['case']:r for r in parents if r['method']==a and not r['unknown']};bb={r['case']:r for r in parents if r['method']==b and not r['unknown']};common=sorted(aa.keys()&bb.keys())
        ab=sum(aa[k]['complete_pass'] and not bb[k]['complete_pass'] for k in common);ba=sum(bb[k]['complete_pass'] and not aa[k]['complete_pass'] for k in common);n=ab+ba
        paired.append({'method_a':a,'method_b':b,'common_known_parent_cases':common,'a_only_success':ab,'b_only_success':ba,'exact_p_two_sided':min(1,2*sum(math.comb(n,i) for i in range(min(ab,ba)+1))/2**n) if n else 1,'scope':'final outputs; actual costs differ, not a budget-matched superiority test'})
    table('paired_comparisons',paired)
    perms=old_report.permission_audit()
    mapping=read(OUT/'old_new_run_mapping.json');mapby={r['old_run']:r['new_run'] for r in mapping}
    table('old_new_run_mapping',mapping)
    unknown_details=[];old_index=read(x.PREV/'hidden_evaluations.json')
    for m in mapping:
        if m['old_status']=='ok':continue
        p=ROOT/m['new_run'];norm=read(p/'normalization.json');reasons=[z.get('reason') for z in norm if not z['supported']]
        if m['new_status']=='ok':category='implemented_operator_or_temporal_semantics'
        elif any(z and z.startswith('permission:') for z in reasons):category='candidate_uses_unpermitted_information'
        elif any(z and z.startswith('illegal:') for z in reasons):category='candidate_illegal_expression'
        elif any(z and z.startswith('parse:') for z in reasons):category='parse_or_missing_candidate'
        elif reasons:category='unsupported_expression_or_temporal_semantics'
        else:category='compile_error' if runs[m['new_run']]['compile']['exit_code'] else 'runtime_error'
        unknown_details.append({**{n:m[n] for n in ['old_run','new_run','case','old_status','new_status']},'category':category,'validation_reasons':reasons,'normalization':rel(p/'normalization.json'),'compile_log':rel(p/'compile.stderr'),
          'old_original_candidates':m['old_candidate'],'affected_old_methods':sorted({it['arm'] for it in old_index if m['old_run'] in it['evaluation']['run_ids']})})
    table('unknown_reason_detail',unknown_details)
    table('unknown_reason_summary',[{'category':k,'run_count':n,'unit':'old non-ok run, not independent parent'} for k,n in collections.Counter(r['category'] for r in unknown_details).items()])
    transitions=[];oldparents={(r['case'],r['method']):r for r in read(x.PREV/'parent_results.json')}
    for it in old_index:
        if not it['final']:continue
        e={**it['evaluation'],'run_ids':[mapby[p] for p in it['evaluation']['run_ids']]}
        rr,_,_=old_report.evaluate_saved(e);p=parent({**it,'evaluation':e},rr);old=oldparents[(p['case'],p['method'])]
        transitions.append({'case':p['case'],'parent_bug_id':p['parent_bug_id'],'method':p['method'],'old_complete_pass':old['complete_pass'],'old_unknown':old['unknown'],'old_unknown_reasons':old['unknown_reasons'],
          'replayed_complete_pass':p['complete_pass'],'replayed_unknown':p['unknown'],'replayed_unknown_reasons':p['unknown_reasons'],'replayed_false_positive':p['false_positive'],'replayed_miss':p['miss'],'replayed_not_triggered':p['not_triggered'],'run_ids':e['run_ids'],'interpretations':rr,
          'scope':'old frozen final candidates, SAME old hidden input/RTL; pure tool capability intervention; not fresh-model arm'})
    table('old_final_candidate_transitions',transitions)
    promoted=[r for r in transitions if r['old_unknown'] and not r['replayed_unknown']]
    transition_counts={'old_unknown_to_known':len(promoted),'to_pass':sum(r['replayed_complete_pass'] is True for r in promoted),'to_semantic_failure':sum(r['replayed_complete_pass'] is False for r in promoted),
      'false_positive_flags':sum(r['replayed_false_positive'] for r in promoted),'miss_flags':sum(r['replayed_miss'] for r in promoted),'not_triggered_flags':sum(r['replayed_not_triggered'] for r in promoted),'flags_can_overlap':True,'unit':'method x parent, not independent parents'}
    dump(OUT/'unknown_transition_counts.json',transition_counts)
    success_cases={arm:[r['case'] for r in parents if r['method']==arm and r['complete_pass'] is True] for arm in v.ARMS}
    unique_obligation=sorted(set(success_cases['obligation_loop'])-set().union(*(set(cases) for arm,cases in success_cases.items() if arm!='obligation_loop')))
    mechanism={'success_cases_by_method':success_cases,'obligation_unique_successes':unique_obligation,'matched_budget_reference':'common_budget_pairwise.json',
      'interpretation':'No unique complete-contract success for obligation loop in this cohort.' if not unique_obligation else 'Unique successes must be read with paired actual-budget and information controls; no population superiority inference.'}
    dump(OUT/'mechanism_analysis.json',mechanism)
    refinement=[{'case':m['case'],'method':m['arm'],'step':s['step'],'refinement':s.get('refinement'),'before_score':s.get('before_score')} for p in (OUT/'methods').glob('*/*/final.json') for m in [read(p)] for s in m['steps'] if 'refinement' in s]
    table('refinement_events',refinement)
    summary={'version':'3.0','parent_count':len(v.IDS),'method_count':len(v.ARMS),'runs':len(runrows),'run_status':dict(collections.Counter(r['status'] for r in runrows)),
      'effective_simulations':sum(r.get('effective_simulation',False) for r in runrows),'physical_model_calls':len(models),'physical_model_prompt_tokens':sum(r['prompt_tokens'] or 0 for r in models),'physical_model_completion_tokens':sum(r['completion_tokens'] or 0 for r in models),'model_seconds':sum(r['wall_seconds'] for r in models),
      'physical_compile_attempts':len(costs),'physical_simulation_attempts':sum(r['simulation_attempts'] for r in costs),'physical_validation_seconds':sum(r['compile_seconds']+r['simulation_seconds'] for r in costs),
      'old_runs_replayed':len(mapping),'old_unsupported':sum(r['old_status']=='unsupported_syntax' for r in mapping),'old_unsupported_now_ok':sum(r['old_status']=='unsupported_syntax' and r['new_status']=='ok' for r in mapping),
      'old_supported_regressions':sum(r['old_supported_trace_identical'] is False or r['old_supported_checks_identical'] is False or r['old_status']=='ok' and r['new_status']!='ok' for r in mapping),
      'old_unknown_parent_cells':sum(r['old_unknown'] for r in transitions),'old_unknown_now_known':sum(r['old_unknown'] and not r['replayed_unknown'] for r in transitions),
      'old_unknown_now_pass':sum(r['old_unknown'] and r['replayed_complete_pass'] is True for r in transitions),'old_unknown_now_semantic_fail':sum(r['old_unknown'] and r['replayed_complete_pass'] is False for r in transitions),
      'complete_pass_parent_cells':sum(r['complete_pass'] is True for r in parents),'known_failure_parent_cells':sum(r['complete_pass'] is False for r in parents),'unknown_parent_cells':sum(r['unknown'] for r in parents),
      'permission_requests_checked':len(perms),'permission_failures':sum(not r['pass'] for r in perms),'methods':methods,'solver_calls':0,'solver_seconds':None,'new_parent_bugs':0,'spec_unresolved':['spill','intr'],
      'qualification':read(OUT/'qualification.json'),'audit':read(OUT/'audit.json') if (OUT/'audit.json').exists() else None}
    events=[json.loads(line) for line in (OUT/'events.jsonl').read_text().splitlines()]
    phases=[]
    for name,start,end in [('method','model_request','method_frozen'),('hidden','hidden_access_started','hidden_access_finished')]:
        starts=[e['time'] for e in events if e['event']==start];ends=[e['time'] for e in events if e['event']==end]
        if starts and ends:
            import datetime
            seconds=(datetime.datetime.fromisoformat(max(ends).replace('Z','+00:00'))-datetime.datetime.fromisoformat(min(starts).replace('Z','+00:00'))).total_seconds()
            phases.append({'phase':name,'first_logged_event':min(starts),'last_logged_event':max(ends),'elapsed_seconds':seconds,'resolution_seconds':1,'scope':'logged-event wall envelope, not exact process instrumentation'})
    table('phase_wall_time_envelopes',phases)
    summary['extra_audit_compile_attempts']=len(summary['audit']['replays']) if summary['audit'] else 0
    summary['extra_audit_wall_seconds']=summary['audit']['extra_audit_wall_seconds'] if summary['audit'] else None
    dump(OUT/'summary.json',summary)
    lines=['# AssertionForge v3：表达能力修复与统一比较','',
      '本轮保留 v1/v2 封存数据。六个既有人工变异父 bug、八个方法，复用同一 18 槽初始池；无重新生成池、无新增父 bug。独立义务与两种未决规格解释延续 v2。模型版本 digest、配置、权限和隐藏输入在新请求前冻结。',
      '', '## checker 能力与边界','',
      '新增 popcount(允许的 unsigned packed signal)，宽度 1–256，32 位无符号返回值，X/Z 传播；任意表达式参数不支持。delay=2 使用真实两拍 antecedent 队列，consequent 在到期拍取值，未替换为一拍或捕获数据。复位清空队列；pN 是显式零填充历史。其余表达式用 Icarus SV 类型/位宽规则。11 组最小测试、664 条预期检查通过；独立 Python 逐位计数、事件到期表和手写失败周期作为依据。',
      '', '## 单纯能力修复（同一旧候选、旧输入、旧 RTL）','',
      f"重放 {len(mapping)} 条旧运行；原不支持 {summary['old_unsupported']} 条，其中 {summary['old_unsupported_now_ok']} 条现在可执行。旧已支持运行的非预期变化 {summary['old_supported_regressions']} 条。非法赋值、禁止历史、占位层级名等继续单列未知。",
      f"旧最终输出的 {summary['old_unknown_parent_cells']} 个未知 method×parent 单元中，{summary['old_unknown_now_known']} 个转为已知：{summary['old_unknown_now_pass']} 个有限合约通过，{summary['old_unknown_now_semantic_fail']} 个语义失败。多种误报/漏报/未触发标记见 old_final_candidate_transitions；这些标记可重叠，不能相加作为样本数。",
      f"上述转为已知的单元中，误报标记 {transition_counts['false_positive_flags']}、漏报标记 {transition_counts['miss_flags']}、必要条件未触发标记 {transition_counts['not_triggered_flags']}。",
      '', '## 新反馈下重新比较','',
      f"实际新模型请求 {len(models)} 次；最终 {summary['complete_pass_parent_cells']} 个通过、{summary['known_failure_parent_cells']} 个已知失败、{summary['unknown_parent_cells']} 个未知（48 个 method×parent 单元，只有 6 个独立父 bug）。",
      '', '| 方法 | 通过 | 已知 | 未知 | 有效仿真 | 周期 | 编译尝试 | 输入/输出 token |','|---|---:|---:|---:|---:|---:|---:|---:|']
    lines += [f"| {m['method']} | {m['complete_pass']} | {m['known_parents']} | {m['unknown_parents']} | {m['effective_simulations']} | {m['effective_cycles']} | {m['compile_invocations']} | {m['prompt_tokens']}/{m['completion_tokens']} |" for m in methods]
    if len({tuple(z) for z in success_cases.values()})==1:
        lines += ['', '所有方法通过的父案例相同：'+', '.join(next(iter(success_cases.values())))+'。本轮没有义务闭环独有的完整成功；恢复这些成功首先来自统一 checker 能力修复。共同预算的逐对结果见 common_budget_pairwise。']
    lines += ['', '表中资源只含方法侧（共享池生成按实际消耗槽逻辑归属）；隐藏验收、旧记录重放、能力测试和独立复现成本在 physical_validation_costs 中分开。无 SMT/形式求解；Ollama 完整缓存用量未知，原始 token/duration 保留。',
      '各方法的已知父集合可能不同，不能直接比较各自排除未知后的成功率。所有通过仅来自同一个父 bug；八个方法的八条成功不是八个独立成功样本。',
      '', '## 共同预算','',
      '主要资源为完整执行并产生全部 TRACE/CHECK 的有效仿真，未触发也计数。预定检查点为 2/4/6/8/12 次及 48/96/144/192/288 周期；只取首次恰好达到该点的完整候选评估输出。未到达明确记 unreached，未填平预算。每行保留设计、参数、输入哈希、周期与事务规模；no_fp 的工作负载缺少 fixed，是该消融定义，不能声称其同次数工作内容相同。token、编译失败和耗时同时报告，未声称全维度相等。',
      'first 在首个评估后停止；因此不存在所有方法都能到达的高预算点。比较须读取 common_effective_budget_checkpoints 的 reached、available_methods 和 workload，不能拿最终输出表直接宣称等有效预算优势。',
      '有效仿真的主计数是物理完整执行数；固定两次提案流程可能再次产生同一表达式。budget_ledger 同时列出按 checker/设计/输入内容去重的验证单位和重复执行数，重复执行不代表新增语义证据；没有为补齐检查点另外增加调用或验证。',
      '', '## 结论限制','',
      '工具修复能够把原来的部分语法未知转成可检验的语义结果。任何方法之间的收益都须与同父 bug、同实际资源检查点和权限对照一起解释；不预设义务闭环胜出。spill invalid payload 与中断采样时序仍规格未决，不计完整通过。所有通过仅限封存有限输入、参数和变异控制；没有新增历史修复样本或全状态证明。',
      'stat 原候选的当前输入比较与“捕获触发时长度”是不同语义；本轮保留原表达，通过独立义务暴露差异，没有人为改成 p2 值。隐藏验收结果未进入模型反馈。',
      'run_results.status 表示工具执行状态，旧执行器的单条候选分类只采用主解释；完整合约结论应读取 parent_results、conditional_results 和逐义务数据。继承的少量描述性标签澄清见 implementation_notes.json，冻结候选与协议原字节未改动。',
      '', '## 复现','',
      '```powershell',
      'wsl -d Ubuntu -- sh /mnt/d/AssertionForge-main1/deliverables/repair_contract_v3_20261010/qualification/popcount_w65/reproduce.sh',
      'wsl -d Ubuntu -- sh /mnt/d/AssertionForge-main1/deliverables/repair_contract_v3_20261010/qualification/delay_overlap_reset_boundary/reproduce.sh',
      'wsl -d Ubuntu -- python3 /mnt/d/AssertionForge-main1/scripts/contract_v3_report.py','```',
      '每条实际仿真目录另有 reproduce.sh；最终独立重编译和逐周期交叉核验见 audit.json。重新汇总不调用模型。']
    if summary['audit']:lines += ['',f"独立审计：{summary['audit']['check_count']} 项一致性检查，通过={summary['audit']['pass']}；表达式逐周期交叉核验 {summary['audit']['expression_counts']}。超出独立解释器的表达式单列，未冒充已核验。"]
    (OUT/'REPORT.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps({k:z for k,z in summary.items() if k not in ['methods','qualification','audit']},indent=2),flush=True)

if __name__=='__main__':reports()
