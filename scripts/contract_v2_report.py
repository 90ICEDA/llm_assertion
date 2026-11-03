"""Regenerate every aggregate from saved checker logs, traces and API responses."""
import collections,csv,itertools,json,re,shutil,subprocess,time,datetime
from run_contract_v2 import OUT,OLD,ROOT,read,dump,rel,sha,definition,IDS,ARMS,check_freeze,validated,allowed,stamp
from contract_v2_spec import views,components,branches,trigger_branches,adjudicate,legality

def table(name,rows):
    dump(OUT/(name+'.json'),rows)
    if rows:
        keys=list(dict.fromkeys(k for r in rows for k in r))
        with (OUT/(name+'.csv')).open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in r.items()} for r in rows)

def due_cycle(k,branch,o,view):
    if k=='stat':return o['cycle']+2
    if k=='intr' and branch=='mask_falling' and view=='registered_mask':return o['cycle']+1
    return o['cycle']

def evaluate_saved(e):
    k=e['case'];d=definition(k);rr=[read(ROOT/p/'result.json') for p in e['run_ids']];results=[];component_rows=[];branch_rows=[]
    for view in views(k):
        unknown=[];fp=miss=detected=violations=0;branch_seen=set();trigger_seen=set();component_activated=set();total_ants=0;run_evidence=[]
        for r in rr:
            if r['status']!='ok':
                unknown.append(r['status'])
                for name in components(k):component_rows.append({'case':k,'parent_bug_id':IDS[k],'expression_signature':e['expression_signature'],'view':view,'run':r['run_id'],'component':name,'checked_cycles':None,'violation_cycles':None,'detected_cycles':None,'missed_cycles':None,'activated':None,'status':r['status']})
                for branch in branches(k):branch_rows.append({'case':k,'parent_bug_id':IDS[k],'expression_signature':e['expression_signature'],'view':view,'run':r['run_id'],'branch':branch,'condition_witnesses':None,'requires_assertion_trigger':branch in trigger_branches(k),'status':r['status']})
                continue
            tr=read(ROOT/r['trace']);obs=adjudicate(d,tr,view);c=r['candidates'][0];defs=read(ROOT/r['run_id']/'candidates.json');delay=defs[0]['delay'];fails=set(c['failure_cycles']);ants=set(c['trigger_cycles']);total_ants+=len(ants)
            violation_set={o['cycle'] for o in obs if o['violations']};fps=sorted(fails-violation_set) if r['variant']=='correct' else []
            misses=sorted(violation_set-fails);caught=sorted(violation_set&fails)
            fp+=len(fps);miss+=len(misses);detected+=len(caught);violations+=len(violation_set)
            if c['status']=='unknown':unknown.append('checker_unknown')
            pending=[p for p in obs[-1]['pending'] if p['due_cycle']>=len(obs)]
            if pending:unknown.append('pending_out_of_window')
            run_evidence.append({'run':r['run_id'],'fp':fps,'miss':misses,'caught':caught,'pending':pending})
            for name in components(k):
                checked=[o['cycle'] for o in obs if name in o['checks']];bad=[o['cycle'] for o in obs if name in o['violations']]
                if bad:component_activated.add(name)
                component_rows.append({'case':k,'parent_bug_id':IDS[k],'expression_signature':e['expression_signature'],'view':view,'run':r['run_id'],'component':name,'checked_cycles':checked,'violation_cycles':bad,'detected_cycles':sorted(set(bad)&fails),'missed_cycles':sorted(set(bad)-fails),'activated':bool(bad),'status':'measured','controlled_mutation':r.get('component_control',{}).get('name'),'attribution':'same-cycle observations; isolation evaluated separately'})
            for branch in branches(k):
                oo=[o for o in obs if branch in o['branches']];seen=[o['cycle'] for o in oo]
                if seen:branch_seen.add(branch)
                pairs=[]
                for o in oo:
                    due=due_cycle(k,branch,o,view);ant=due-delay
                    pairs.append({'condition_cycle':o['cycle'],'expected_result_cycle':due,'assertion_antecedent_cycle':ant,'antecedent_hit':ant in ants,'assertion_failure_at_result':due in fails,'target_violation_at_result':due in violation_set,'reference_false_alarm_at_result':due in fps})
                if any(x['antecedent_hit'] for x in pairs):trigger_seen.add(branch)
                branch_rows.append({'case':k,'parent_bug_id':IDS[k],'expression_signature':e['expression_signature'],'view':view,'run':r['run_id'],'branch':branch,'condition_witnesses':pairs,'requires_assertion_trigger':branch in trigger_branches(k),'status':'measured'})
        missing_branches=sorted(set(branches(k))-branch_seen);empty_branches=sorted(set(trigger_branches(k))-trigger_seen);missing_components=sorted(set(components(k))-component_activated)
        if missing_branches:unknown.append('missing_required_condition_witness')
        if missing_components:unknown.append('missing_target_component_activation')
        # Trigger absence is a measured failure only when that condition occurred.
        not_triggered=sorted(set(empty_branches)&branch_seen)
        conditional_unknown=sorted(set(unknown));conditional_pass=None if conditional_unknown else not(fp or miss or not_triggered)
        results.append({'case':k,'parent_bug_id':IDS[k],'view':view,'expression_signature':e['expression_signature'],'false_positive':fp>0,'miss':miss>0,'not_triggered':bool(not_triggered),
                        'fp_cycles':fp,'miss_cycles':miss,'detected_violation_cycles':detected,'violation_cycles':violations,'coverage':detected/violations if violations else None,
                        'nonempty_by_branch':{b:(b in trigger_seen) if b in branch_seen else None for b in trigger_branches(k)},'missing_condition_branches':missing_branches,'untriggered_condition_branches':not_triggered,'missing_activated_components':missing_components,
                        'unknown_reasons':conditional_unknown,'conditional_complete_pass':conditional_pass,'spec_status':'spec_unresolved' if k in ['spill','intr'] else 'scoped_contract','runs':run_evidence,
                        'scope':'all frozen independent scenario/control cells for this expression; per-branch antecedent at the expected result sample minus actual checker delay'})
    return results,component_rows,branch_rows

def permission_audit():
    records=[]
    for p in (OUT/'model_calls').rglob('request.json'):
        req=read(p);ctx=json.loads(req['messages'][1]['content']);k=p.parent.parts[-3] if 'repair' in p.parts else p.parent.parts[-2]
        # Directory layout is model_calls/{pool|repair}/case/[arm]/step.
        relative=p.relative_to(OUT/'model_calls').parts;k=relative[1];d=definition(k)
        permission=read(p.parent/'permission_check.json');depth=permission['history_depth'];issues=[]
        if len(req['messages'])!=2 or set(req)-{'model','stream','format','messages','options'}:issues.append('unexpected_request_channel')
        if ctx['allowed_identifiers']!=allowed(d,depth):issues.append('wrong_signal_permission')
        if read(p.parent/'visible_context.json')!=ctx:issues.append('saved_context_differs_from_actual_request')
        if 'second_new_sample_dbg' in json.dumps(req):issues.append('debug_leak')
        if 'current_property' in ctx and 'antecedent' in ctx['current_property']:
            try:validated(ctx['current_property'],d,depth)
            except Exception:issues.append('unallowed_candidate_identifier_in_context')
        for item in ctx.get('feedback',{}).get('evidence',[]):
            for row in item.get('allowed_history',[]):
                if set(row)!=set(d['observation_base']):issues.append('waveform_not_whitelisted')
        for item in ctx.get('feedback',{}).get('differences',[]):
            if set(item)!=set(['reference','changed']):issues.append('unexpected_diff_channel')
            for row in item.values():
                if set(row)!=set(d['observation_base']):issues.append('diff_signal_not_whitelisted')
        if p.parent.parent.name=='no_fp_check' and 'fp' in ctx.get('feedback',{}):issues.append('fp_feedback_in_ablated_arm')
        records.append({'request':rel(p),'sha256':sha(p),'pass':not issues,'issues':issues,'all_model_input_channels':'exact stateless HTTP JSON; no tools/files/history context ids; raw RTL and compiler logs never transmitted'})
    dump(OUT/'permission_audit.json',records)
    return records

def reports():
    index=read(OUT/'hidden_evaluations.json');cache={};components_all=[];branches_all=[]
    for item in index:
        e=item['evaluation'];key=(e['case'],e['expression_signature'])
        if key not in cache:
            result,cr,br=evaluate_saved(e);cache[key]=result;components_all+=cr;branches_all+=br
    table('obligation_acceptance',components_all);table('branch_acceptance',branches_all)
    conditional=[];parents=[];checkpoints=[]
    for item in index:
        e=item['evaluation'];rr=cache[(e['case'],e['expression_signature'])];k=item['case'];m=item['arm'];cp=item['checkpoint']
        unknown=set(x for r in rr for x in r['unknown_reasons'])
        if k in ['spill','intr']:unknown.add('spec_unresolved')
        row={'case':k,'parent_bug_id':IDS[k],'method':m,'step':item['step'],'final':item['final'],'expression_signature':e['expression_signature'],
             'complete_pass':None if unknown else all(r['conditional_complete_pass'] for r in rr),'unknown':bool(unknown),'unknown_reasons':sorted(unknown),
             'false_positive':any(r['false_positive'] for r in rr),'miss':any(r['miss'] for r in rr),'not_triggered':any(r['not_triggered'] for r in rr),
             'fp_cycles_by_view':{r['view']:r['fp_cycles'] for r in rr},'miss_cycles_by_view':{r['view']:r['miss_cycles'] for r in rr},
             'coverage_by_view':{r['view']:r['coverage'] for r in rr},'branch_nonempty_by_view':{r['view']:r['nonempty_by_branch'] for r in rr},
             'aggregation_unit':'parent_bug','selection_scope':'one_frozen_final_output' if item['final'] else 'last_completed_output_at_resource_checkpoint','historical_fix':False,
             'compile_invocations':cp['compile_invocations'],'simulation_invocations':cp['simulation_invocations'],'prompt_tokens':cp['prompt_tokens'],'completion_tokens':cp['completion_tokens'],
             'unknown_token_calls':cp['unknown_token_calls'],'logical_model_calls':cp['logical_model_calls'],'logical_model_wall_seconds':cp['logical_model_wall_seconds'],'validation_wall_seconds':cp['validation_wall_seconds'],'history_bits_permission':cp['history_bits_permission']}
        checkpoints.append(row)
        if item['final']:
            parents.append(row)
            conditional += [{**r,'method':m,'specification_interpretation_is_conditional':k in ['spill','intr']} for r in rr]
    table('parent_results',parents);table('conditional_results',conditional);table('checkpoint_results',checkpoints)
    methods=[]
    for arm in ARMS:
        pp=[r for r in parents if r['method']==arm];known=[r for r in pp if not r['unknown']]
        methods.append({'method':arm,'parent_count':len(pp),'known_parents':len(known),'unknown_parents':len(pp)-len(known),'complete_pass':sum(r['complete_pass'] is True for r in pp),'success_rate_known':sum(r['complete_pass'] is True for r in known)/len(known) if known else None,
                        'fp_parent_flags_known':sum(r['false_positive'] for r in known),'miss_parent_flags_known':sum(r['miss'] for r in known),'not_triggered_parent_flags_known':sum(r['not_triggered'] for r in known),
                        'conditional_failure_flags_in_unknown':sum(r['unknown'] and (r['false_positive'] or r['miss'] or r['not_triggered']) for r in pp),
                        'logical_prompt_tokens':sum(r['prompt_tokens'] for r in pp),'logical_completion_tokens':sum(r['completion_tokens'] for r in pp),'actual_compiles':sum(r['compile_invocations'] for r in pp),'actual_simulations':sum(r['simulation_invocations'] for r in pp),
                        'model_wall_seconds_including_logically_charged_pool':sum(r['logical_model_wall_seconds'] for r in pp),'method_validation_seconds':sum(r['validation_wall_seconds'] for r in pp),'unknown_excluded_from_success_denominator':True,'parent_failure_flags_may_overlap':True})
    table('method_comparison',methods)
    budgets=[];matches=[]
    for item in index:
        cp=item['checkpoint'];used=sorted(set(re.findall(r'\bp[123]_\w+',cp['candidate']['antecedent']+' '+cp['candidate']['consequent'])))
        budgets.append({**cp,'final':item['final'],'candidate_slots_consumed':cp['logical_model_calls'],'actual_history_names_used':used,'observer_cost_scope':'permission bits; testbench physically declares all p1/p2/p3 copies, unused registers are not a synthesized hardware area measurement','server_prompt_cache_usage':'unknown: Ollama raw response gives eval counts/durations but no complete cache-accounting field','total_method_wall_seconds':None,'total_method_wall_status':'not separately instrumented; exact model/compile/sim durations and artifact timestamp envelope are reported separately'})
    table('budget_ledger',budgets)
    for k in IDS:
        cc=[r for r in checkpoints if r['case']==k]
        for resource,limits,exact in [('compile_invocations',[2,4,6,8,12],True),('total_tokens',[2048,4096,8192,12864],False),('simulation_invocations',[0,2,4,8,12],False)]:
            value=lambda r:r['prompt_tokens']+r['completion_tokens'] if resource=='total_tokens' else r[resource]
            for limit in limits:
                rows=[]
                for arm in ARMS:
                    eligible=[r for r in cc if r['method']==arm and (value(r)==limit if exact else value(r)<=limit)]
                    selected=max(eligible,key=lambda x:x['step']) if eligible else None
                    rows.append({'case':k,'method':arm,'resource':resource,'checkpoint':limit,'mode':'exact_actual_resource' if exact else 'common_resource_envelope','available':selected is not None,
                                 'actual_primary_resource':value(selected) if selected else None,'unspent':limit-value(selected) if selected else None,'selected_result':selected})
                common=all(x['available'] for x in rows)
                for r in rows:r['all_eight_arms_have_output_at_checkpoint']=common
                matches+=rows
    table('resource_matched_comparisons',matches)
    calls=[]
    for p in (OUT/'model_calls').rglob('result.json'):
        r=read(p);calls.append({'path':rel(p),'status':r['status'],'prompt_tokens':r.get('prompt_tokens'),'completion_tokens':r.get('completion_tokens'),'wall_seconds':r['wall_seconds'],'retries':0,'physical_new_call':True,'raw_response':rel(p.parent/'response.raw.json') if (p.parent/'response.raw.json').exists() else None})
    table('physical_model_costs',calls)
    runs=[read(p) for p in (OUT/'runs').rglob('result.json')];table('run_results',runs)
    physical=[]
    for p in OUT.rglob('compile.command.json'):
        cr=read(p);sr=read(p.parent/'simulate.command.json') if (p.parent/'simulate.command.json').exists() else None
        physical.append({'directory':rel(p.parent),'compile_invocations':1,'simulation_invocations':int(sr is not None),'compile_seconds':cr['wall_seconds'],'simulate_seconds':sr['wall_seconds'] if sr else 0,'compile_exit':cr['exit_code'],'simulate_exit':sr['exit_code'] if sr else None,'archived':any(n in p.parts for n in ['failed_attempts','window_closure_archive'])})
    table('physical_validation_costs',physical)
    timing=[]
    for p in (OUT/'methods').glob('*/*/final.json'):
        m=read(p);initial=m['checkpoints'][0]['run_ids'];start=min((ROOT/r/'input.json').stat().st_mtime for r in initial);end=p.stat().st_mtime
        timing.append({'case':m['case'],'method':m['arm'],'first_input_file_mtime_epoch':start,'final_record_file_mtime_epoch':end,'artifact_envelope_seconds':end-start,'measurement':'filesystem timestamp envelope, not a separately instrumented exact method runtime; includes work between first input materialization and frozen result'})
    table('wall_time_envelopes',timing)
    events=[json.loads(line) for line in (OUT/'events.jsonl').read_text().splitlines() if line.strip()]
    first_call=next(x['time'] for x in events if x['event']=='model_request');last_method=[x['time'] for x in events if x['event']=='method_frozen'][-1]
    hidden_start=next(x['time'] for x in events if x['event']=='hidden_access_started');hidden_end=[x['time'] for x in events if x['event']=='hidden_access_finished'][-1]
    seconds=lambda a,b:(datetime.datetime.fromisoformat(b.replace('Z','+00:00'))-datetime.datetime.fromisoformat(a.replace('Z','+00:00'))).total_seconds()
    dump(OUT/'phase_wall_times.json',{'model_and_method_phase':{'start':first_call,'end':last_method,'elapsed_seconds':seconds(first_call,last_method)},'hidden_phase':{'start':hidden_start,'end':hidden_end,'elapsed_seconds':seconds(hidden_start,hidden_end)},'end_to_end_including_interphase_preparation':{'start':first_call,'end':hidden_end,'elapsed_seconds':seconds(first_call,hidden_end)},'timestamp_resolution_seconds':1,'logical_reused_generation_costs_not_new_physical_wall_time':True})
    perms=permission_audit();assert all(x['pass'] for x in perms)
    refinements=[]
    for p in (OUT/'methods').glob('*/*/final.json'):
        m=read(p)
        for s in m['steps']:
            if 'refinement' in s:refinements.append({'case':m['case'],'method':m['arm'],'step':s['step'],**s['refinement']})
    table('refinement_events',refinements)
    equivalents=[];legalvariants=[];isolations=[]
    for r in runs:
        if '/equivalent_rewrite/' in r['run_id']:
            reference=r['run_id'].replace('/equivalent_rewrite/','/transactions/')
            rr=next((x for x in runs if x['run_id']==reference),None)
            same=None
            if rr and r['status']==rr['status']=='ok':same=read(ROOT/r['trace'])==read(ROOT/rr['trace'])
            equivalents.append({'run':r['run_id'],'reference':reference,'same_observed_public_trace':same,'status':'matched' if same else 'unknown' if same is None else 'mismatch'})
        if '/legal_variant/' in r['run_id']:
            reference=r['run_id'].replace('/legal_variant/','/engineering_control/' if '/calibration/' in r['run_id'] else '/transactions/');rr=next((x for x in runs if x['run_id']==reference),None)
            differences=[]
            if rr and r['status']==rr['status']=='ok':differences=[a['cycle'] for a,b in zip(read(ROOT/r['trace']),read(ROOT/rr['trace'])) if a['err_o']!=b['err_o']]
            legalvariants.append({'run':r['run_id'],'reference':reference,'actual_behavior_difference_cycles':differences,'status':'verified_different' if differences else 'unknown_or_no_difference','parameters':r['parameters'],'engineering_control_only':'/calibration/' in r['run_id']})
        if r.get('component_control') and r['status']=='ok':
            d=definition(r['case']);tr=read(ROOT/r['trace'])
            for view in views(r['case']):
                obs=adjudicate(d,tr,view);target=set(r['component_control']['target_components'])
                isolated=[o['cycle'] for o in obs if set(o['violations'])==target]
                isolations.append({'run':r['run_id'],'view':view,'target':sorted(target),'isolated_violation_cycles':isolated,'other_violation_cycles':[o['cycle'] for o in obs if o['violations'] and set(o['violations'])!=target],'status':'isolated_witness_found' if isolated else 'not_activated_or_logically_coupled'})
    table('equivalence_checks',equivalents);table('legal_variant_checks',legalvariants);table('component_isolation_checks',isolations)
    original=read(OUT/'observations/original_20_adjudication.json');search=read(OUT/'observations/strict_history_search.json')
    summary={'generated_at':stamp(),'parents':6,'method_parent_cells':len(parents),'physical_model_calls':len(calls),'model_status':dict(collections.Counter(x['status'] for x in calls)),
             'physical_new_model_wall_seconds':sum(x['wall_seconds'] for x in calls),'logical_reused_initial_pool_slots':12,'runs':len(runs),'run_status':dict(collections.Counter(x['status'] for x in runs)),
             'physical_compile_invocations':len(physical),'physical_simulation_invocations':sum(x['simulation_invocations'] for x in physical),'physical_compile_and_sim_seconds':sum(x['compile_seconds']+x['simulate_seconds'] for x in physical),
             'permissions_checked':len(perms),'permission_failures':sum(not x['pass'] for x in perms),'original_witnesses':len(original),'strict_retained_all_interpretations':sum(x['disposition'].startswith('retained') for x in original),
             'strict_full_history_conflicts':sum(x['conflict_count'] for x in search if x['depth']=='complete'),'controlled_and_natural_witnesses_separately_tagged':True,
             'methods':methods,'spec_unresolved_parents':['spill','intr'],'solver':'not used; retained finite truth-function check only','historical_repair_parents':0,
             'unknown_parent_cells':sum(r['unknown'] for r in parents),'complete_pass_parent_cells':sum(r['complete_pass'] is True for r in parents)}
    dump(OUT/'summary.json',summary)
    gaps=[{'id':'F1','status':'fixed_and_rerun','evidence':'permission_audit.json','detail':'fresh stateless contexts; only whitelisted values and normalized categories; no polluted repair candidates reused'},
          {'id':'F2','status':'readjudicated_and_searched','evidence':'observations/original_20_adjudication.json','detail':'whole reset-to-sample prefix plus pending discharge; pointwise-only witnesses excluded; new controlled filter enumeration separate'},
          {'id':'F3','status':'resource_checkpoints_reported','evidence':'resource_matched_comparisons.json','detail':'exact common compiler-count comparisons where outputs exist; token/simulation envelopes show actual differences. No all-dimensional equality claimed.'},
          {'id':'F4','status':'partially_resolved_with_explicit_spec_unknown','evidence':'conditional_results.json','detail':'spill and interrupt interpretations separate; complete parent pass prohibited. FIFO only independent Depth=0 target contract, not full upstream FIFO equivalence.'},
          {'id':'F5','status':'final_candidates_rechecked_per_component_and_branch','evidence':'obligation_acceptance.json','detail':'separate condition, activation, antecedent and failure witnesses; FP/FN/nontrigger may overlap; missing witness unknown'},
          {'id':'F6','status':'controlled_implementation_rerun','evidence':'refinement_events.json','detail':'generic feedback only changes payload; same acceptance/evaluation/update. Existing baseline explicitly maps to prior sealed local existing_feedback arm, not all project historical workflows.'},
          {'id':'F7','status':'evidence_triggered_refinement_rerun','evidence':'refinement_events.json','detail':'miss plus strict training collision triggers minimum resolving history; equal-information control gets that entitlement from first repair'}]
    for g in gaps:g['reproduce']='wsl -d Ubuntu -- python3 /mnt/d/AssertionForge-main1/scripts/contract_v2_report.py'
    table('audit_gap_resolution',gaps)
    mechanisms={'full_pass_cases_by_method':{m:[r['case'] for r in parents if r['method']==m and r['complete_pass'] is True] for m in ARMS},
                'filter_results':[{k:r[k] for k in ['method','fp_cycles_by_view','miss_cycles_by_view','coverage_by_view','history_bits_permission','prompt_tokens','completion_tokens']} for r in parents if r['case']=='filter'],
                'common_exact_compiler_checkpoints':sorted({(r['case'],r['checkpoint']) for r in matches if r['mode']=='exact_actual_resource' and r['all_eight_arms_have_output_at_checkpoint']}),
                'conclusion':'No method has a complete passing parent in this frozen supplement. Extra history entitlement and lower cycle-miss counts are not a complete-contract improvement. Compare common-resource rows with their token/time differences; no causal superiority is established.'}
    dump(OUT/'mechanism_analysis.json',mechanisms)
    metrics=[]
    for m in methods:
        n=m['known_parents'];success=m['complete_pass']
        for unit in ['candidate','case','parent_bug']:
            metrics.append({'model':'qwen2.5-coder:7b-instruct','method':m['method'],'selection_scope':'candidate_level','selection_scope_note':'one frozen final output of the named method, not any-of-k original generations','aggregation_unit':unit,'k':1,'metric':'finite_frozen_contract_success','value':success/n if n else None,'candidate_observation_count':n,'case_count':n,'parent_bug_count':n,'unknown_parent_count':6-n,'deduplicated':True,'dedup_key':'parent_bug_id','parent_aggregation':'all_observations','overlap_status':'non_overlap','sample_definition':'one final assertion per parent; all independent scenario/control cells; unknown excluded','ci_level':0.95,'ci_lower':0 if n and success==0 else None,'ci_upper':1-0.025**(1/n) if n and success==0 else None,'ci_method':'Clopper-Pearson zero-success endpoint; purposive sample is not a population estimate','bootstrap_unit':'parent_bug_id','bootstrap_repetitions':0,'random_seed':20261009})
    table('metrics',metrics)
    paired=[]
    for a,b in itertools.combinations(ARMS,2):
        aa={r['parent_bug_id']:r for r in parents if r['method']==a and not r['unknown']};bb={r['parent_bug_id']:r for r in parents if r['method']==b and not r['unknown']};common=sorted(aa.keys()&bb.keys())
        paired.append({'method_a':a,'method_b':b,'common_known_parent_count':len(common),'parents':common,'discordant_success_pairs':sum(aa[k]['complete_pass']!=bb[k]['complete_pass'] for k in common),'status':'no_success_discordance' if common else 'no_common_known_parents','exact_McNemar_p':1 if common and all(aa[k]['complete_pass']==bb[k]['complete_pass'] for k in common) else None})
    table('paired_comparisons',paired)
    lines=['# AssertionForge 修复保护实验：修正协议补跑','','本报告从保存的请求、checker 结果、独立义务和预算记录重新生成。原封存目录保留。','',
      '## 设置与权限','',
      '冻结 6 个既有人工变异父 bug、8 个方法臂。模型为原 digest 的 Qwen2.5 coder 7B，CPU、seed=20261009、temperature=0.2、192 输出 token。复用 12 个通过权限核查的初始生成槽；spill/中断规格描述修订后重新生成 6 槽。所有修复均为新的二消息请求，无工具、文件、历史对话；原污染候选不参与。',
      '独立验收器可读完整波形和规格；模型只获得白名单接口字段、接口规格及允许的反馈。原始 compiler 日志、RTL、注释和 debug 波形不进入模型请求。实际请求审计见 permission_audit.json。',
      'run_results 的 status 表示工具执行状态；旧执行器 candidate 内的逐周期统计只对应主参考解释。多解释下的语义验收应读取 obligation_acceptance、conditional_results 和 parent_results，不能把仿真 ok 当作合约成功。本次未调用 Claude Code。',
      '协议 2.1 的唯一执行前澄清：合法负控制不强求目标 antecedent 触发；基础 delay=1 已有一位历史，因此细化搜索保守地从完整一拍端口历史开始。修订发生在首次新模型请求之前，旧冻结快照保留。','',
      '## 实际规模','',
      f"新物理模型调用 {len(calls)} 次，状态 {summary['model_status']}；运行记录 {len(runs)}，状态 {summary['run_status']}。新模型请求累计 {summary['physical_new_model_wall_seconds']:.2f}s；编译/仿真累计 {summary['physical_compile_and_sim_seconds']:.2f}s。这些不是形式求解时间。",'',
      '## 方法比较（父 bug；未知排除在成功率分母之外）','',
      '| 方法 | 通过 | 已知 | 未知 | 编译 | 仿真 | 输入 token | 输出 token |','|---|---:|---:|---:|---:|---:|---:|---:|']
    for m in methods:lines.append(f"| {m['method']} | {m['complete_pass']} | {m['known_parents']} | {m['unknown_parents']} | {m['actual_compiles']} | {m['actual_simulations']} | {m['logical_prompt_tokens']} | {m['logical_completion_tokens']} |")
    lines += ['', '成功仅指预封存有限场景/控制集合内的修复目标保护；不是全状态空间证明。每个父 bug 只计一次，规格未决、语法不支持、未激活义务或缺少必要见证都不能计完整通过。不同方法已知父集合可能不同，不能直接比较各自分母的成功率。多种失败标记保留。', '',
      '## 预算与消融','',
      '预算主轴为真实 compiler 调用，另报真实仿真、输入/输出 token、耗时、共享池成本和缓存。resource_matched_comparisons 给出所有臂都有输出的精确实际编译数检查点；token/仿真以共同额度取已完成输出，同时列实际消耗和余量。无公共正仿真检查点时保留不可比较；没有用无效调用或等待填满预算。相同编译数不等于相同语义验证量，也不等于 token/时间相等。',
      'generic-diff 只改反馈为允许端口上的 RTL 执行差异；接受规则和候选更新与义务闭环相同。no_fp 在方法侧不执行 fixed 验证或产生 FP 反馈；最终验收仍执行。no_observation 只关闭细化。额外历史由已有漏报和严格训练冲突触发，等信息臂从首次修复获得义务臂实际授权的历史深度。原始 refinement 证据和授权时点已保存。', '',
      '## 观察冲突及旧签名','',
      f"原 20 个见证已逐一裁定，所有列明解释下严格保留 {summary['strict_retained_all_interpretations']} 个；其余降级或列解释条件。新增 filter 控制枚举 128 条七位输入序列，实际运行两种 RTL。完整允许历史相同且严格标签相反的默认端口冲突数为 {summary['strict_full_history_conflicts']}，结论仅限检查集合。各有限历史深度的冲突、完整两侧输入/历史、pending 处理及细化成本见 observations/。输入-only 与 onehot Boolean 抽象仍单列控制；只有原列明的 16 个真值函数空间可称有限范围无解。", 
      '第 1 组复用未改变的原始 RTL/checker 波形，在修订义务的各解释下重裁同签名对；slot 06/07 和原 FP/TP 签名保留，slot 08 不进入自然候选结论。不同报警次数只标执行差异。第 2 组原 12 个窗口比较、0 排名变化保留：该执行层结论不受规格解释变化影响。', '',
      '## 回归和规格边界','',
      '最终断言与训练 checker 模板先冻结，之后才读取新的预封存 hidden 输入。最终输出及资源检查点输出使用同一独立验收集合；相同表达式可复用实际 checker 结果，映射和缓存单列。连续事务、FIFO 停顿、复位取消、IRQ 清除/测试、边界值、参数重编译、onehot StrictCheck 合法行为变体、等价结构改写均单列。隔离变异只用于对应父 bug 的义务验收，不增加父样本数。',
      'spill 的 invalid payload 可见性与中断同拍/寄存器后采样仍无法由现有文字唯一裁定，两种解释均有结果，父级保持规格未决。FIFO 仅限案例明确的 Depth=0 接口，不能宣称适配器与完整上游 FIFO 全功能等价。统计流水线 fixed 在连续不同长度下可能违反独立规格，不能把这些合法目标报警误标 FP。没有可追溯历史修复提交；6 例均为已有人工变异。', '',
      '补充工程控制在同一新输入上验证 onehot/FIFO 的检测能力及 StrictCheck 合法行为变化，单列 calibration_results，不进入任何模型方法的成功统计。所有方法本轮完整通过数为零；onehot 输出仍含不支持的 popcount，stat 多数输出仍使用不支持的两拍 delay，不能把语法未知改判为语义失败。FIFO 输出在 pop=1 分支缺少保护；filter 即使获得三拍历史仍存在误报或漏报。没有证据支持义务闭环独有收益。',
      '阶段总墙钟见 phase_wall_times（日志时间分辨率 1 秒）；逐方法另给实际产物时间区间，未冒充独立仪表测得的精确方法总时间。Ollama 未提供完整服务端 prompt 缓存统计，该项明确未知；请求/响应原始 eval token 与 duration 均保留。额外观察成本是授权位数及实际使用的历史名字，不是综合后的面积测量。', '',
      '## 复现','',
      '```powershell',
      'wsl -d Ubuntu -- python3 /mnt/d/AssertionForge-main1/scripts/contract_v2_report.py',
      'wsl -d Ubuntu -- python3 /mnt/d/AssertionForge-main1/scripts/contract_v2_audit.py',
      '```','',
      '重新生成汇总只读取保存的原始数据；audit 在独立目录实际重编译复现代表结果与观察冲突，不调用模型。每个 runs 目录另有 reproduce.sh。完整执行顺序：run_contract_v2.py freeze → pool → methods；contract_v2_observations.py；contract_v2_hidden.py；contract_v2_calibration.py；contract_v2_close_windows.py；contract_v2_report.py；contract_v2_audit.py。已有完成模型请求被缓存，不会冒充新调用。']
    if (OUT/'window_closure_amendment.json').exists():
        closure=read(OUT/'window_closure_amendment.json')
        lines+=['','### 收尾窗口修订','',f"中断原输入末尾持续 enable=0，每拍都产生下一拍待检义务。审计后对 {len(closure['runs'])} 个实际验收运行追加两拍 enable=1 的合法收尾，并重新编译仿真；原有输入前缀逐样本不变，原运行完整归档于 window_closure_archive。新尾段属于记录在案的后续 testbench 窗口修复，不能称作首次协议预封存内容。没有修改候选、模型调用、训练证据或通过规则；两种规格解释仍分别报告，中断父级仍是规格未决。"]
    if (OUT/'audit.json').exists():
        au=read(OUT/'audit.json')
        lines+=['','### 独立核验','',f"一致性检查 {au['check_count']} 项，全部通过={au['pass']}；独立表达式核对 {au['expression_crosscheck_counts']}；严格观察见证重核 {au['witness_count']} 对。四次独立重编译复现覆盖目标检测、合法参考误报和冲突双方。工程 onehot 控制使用算术/位运算，超出本次独立 Boolean 解释器的子集，其三条记录明确标作 audit_grammar_unsupported，并未据此宣称所有表达式已独立解释。",'审计器曾因重复目录扫描中止一次，并在四次重放后的结果写出阶段遇到漏导入 stamp 的 NameError；已修复并完整重跑。过程证据见 audit_interruption.json、audit_serialization_failure.json 和 audit_attempt_before_stamp_fix。前次重放耗时缺失保留未知，不记为零。']
    (OUT/'REPORT.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(summary,ensure_ascii=False,indent=2),flush=True)

if __name__=='__main__':reports()
