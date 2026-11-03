"""Independent recount, transaction labels, bounded observation search, reporting."""
import csv,json,math,re,statistics,time,itertools,random,shlex
from pathlib import Path
from run_repair_contract import ROOT,OUT,IDS,definition,read,dump,sha,report,natural

def transactions(d,rows):
 result=[];number=0;prev=None;pending=None
 for i,r in enumerate(rows):
  start=False;accepted=False;kind='idle';k=d['key']
  if r[d['rst']]:
   if k=='onehot':start=prev is None or any(r[n]!=prev[n] for n in d['inputs']);accepted=start;kind='input_episode'
   elif k=='filter':start=prev is None or r['filter_i']!=prev['filter_i'];accepted=start;kind='polarity_episode'
   elif k=='fifo':start=bool(r['push_i'] and (pending is None));accepted=bool(r['push_i'] and r['pop_i']);kind='fifo_transfer'
   elif k=='spill':start=accepted=bool(r['push_i'] or r['flush_i']);kind='sampled_command'
   elif k=='stat':start=accepted=bool(r['frame_done_i']);kind='frame_event'
   else:start=accepted=bool(r['event_intr_i'] or r['sw_clear'] or r['reg2hw_intr_test_qe_i']);kind='interrupt_register_event'
  else:pending=None;kind='reset'
  if start:number+=1;pending=f'{k}:{number}'
  result.append({'cycle':i,'transaction_id':pending,'kind':kind,'new_transaction':start,'accepted':accepted,'input':r})
  if k=='fifo' and accepted:pending=None
  prev=r
 return result

def recount():
 results=[];legacy_checks=[]
 for p in (OUT/'runs').rglob('result.json'):
  r=read(p);d=definition(r['case']);rows=read(ROOT/r['input']);tx=transactions(d,rows)
  dump(p.parent/'transactions.json',tx);r['transactions']=str((p.parent/'transactions.json').relative_to(ROOT));r['accepted_transactions']=sum(x['accepted'] for x in tx)
  if r['status']!='ok':
   r['candidates']=[{'id':c['id'],'provenance':c['provenance'],'trigger_count':None,'fail_hit':None,'first_failure_cycle':None,'first_failure_transaction':None,'failure_cycles':[],'trigger_cycles':[],'false_positive_cycles':[],'missed_violation_cycles':[],'covered_violation_cycles':[],'status':r['status'],'classification':'unknown','nonempty':None} for c in read(p.parent/'candidates.json')]
  if r['status']=='ok':
   tr=read(ROOT/r['trace']);ob=read(ROOT/r['obligations']);viols={x['cycle'] for x in ob if x['violations']}
   candidate_defs={c['id']:c for c in read(p.parent/'candidates.json')}
   for c in r['candidates']:
    # Fix early pilot adjudication which counted buggy off-target failures as FP.
    c['false_positive_cycles']=[x for x in c['failure_cycles'] if x not in viols] if r['variant']=='correct' else []
    first=c['first_failure_cycle'];delay={'spill':1,'stat':2,'intr':1}.get(d['key'],0)
    c['first_failure_target_transaction']=tx[max(0,first-delay)]['transaction_id'] if first is not None else None
    antecedent_delay=candidate_defs[c['id']]['delay']
    c['first_failure_transaction']=tx[max(0,first-antecedent_delay)]['transaction_id'] if first is not None else None
    c['first_failure_trigger_cycle']=max(0,first-antecedent_delay) if first is not None else None
    c['first_failure_transaction_rule']='assertion antecedent transaction; separate target transaction uses independent obligation latency; null/idle means no accepted transaction can be assigned'
    if c['id'].startswith('slot_'):
     evidence=next(x for x in natural(d['key']) if x['id']==c['id']);e=read(ROOT/evidence['evidence']);a=e['ast'];last=False;fails=[];ants=[]
     for t in tr:
      if not t[d['rst']]:last=False;continue
      s=t.get(a['antecedent_signal'],t.get('valid_o') if a['antecedent_signal']=='q_o' else None)
      v=t.get(a['consequent_signal'],t.get('valid_o') if a['consequent_signal']=='q_o' else None)
      if s is None or v is None:break
      ant=(bool(s) if a['antecedent_polarity']=='high' else not bool(s)) and e['slot']!=8
      cons={'high':bool(v),'low':not bool(v),'equal':v==s,'not_equal':v!=s}[a['relation']]
      if ant:ants.append(t['cycle'])
      if (last if a['implication']=='|=>' else ant) and not cons:fails.append(t['cycle'])
      last=ant
     legacy_checks.append({'run':r['run_id'],'candidate':c['id'],'independent_ast_evaluation_matches':ants==c['trigger_cycles'] and fails==c['failure_cycles'],'python_failure_cycles':fails,'icarus_failure_cycles':c['failure_cycles']})
  dump(p,r);results.append(r)
 dump(OUT/'legacy_checker_crosscheck.json',{'checks':legacy_checks,'all_match':all(x['independent_ast_evaluation_matches'] for x in legacy_checks),'count':len(legacy_checks)})
 return results

def history_search(runs):
 output=[]
 for k in IDS:
  d=definition(k);signals=d['observation_base'];samples=[]
  for r in runs:
   if r['case']!=k or r['status']!='ok' or not any(s in r['run_id'] for s in ['/e12/held_24/','/e12/hold_24/','/legacy_regression/']):continue
   tr=read(ROOT/r['trace']);ob=read(ROOT/r['obligations']);past=[]
   for t,o in zip(tr,ob):
    if not t[d['rst']]:past=[];continue
    past.append(tuple(t[s] for s in signals))
    samples.append({'run':r['run_id'],'cycle':t['cycle'],'label':bool(o['violations']),'history':list(past)})
  levels=[]
  for depth in [0,1,2,3,'complete']:
   groups={}
   for s in samples:
    hist=s['history'] if depth=='complete' else s['history'][-(depth+1):]
    # Length is observable after reset. Pad bounded initial memory with reset zeros.
    if depth!='complete':hist=[tuple(0 for _ in signals)]*max(0,depth+1-len(hist))+hist
    key=tuple(hist);groups.setdefault(key,[]).append(s)
   conflicts=[g for g in groups.values() if len({s['label'] for s in g})>1]
   witnesses=[]
   for g in conflicts[:3]:
    a=next(s for s in g if not s['label']);b=next(s for s in g if s['label']);witnesses.append({'legal':a,'violation':b})
   levels.append({'history_depth':depth,'status':'conflict_found' if conflicts else 'not_found_in_checked_executions','conflict_groups':len(conflicts),'witnesses':witnesses,'extra_register_bits':None if depth=='complete' else depth*sum({**d['inputs'],**d['outputs']}[s] for s in signals)})
  output.append({'parent_bug_id':IDS[k],'allowed_signals':signals,'initialization':'two reset samples; auxiliary history registers initialized zero','sample_count':len(samples),'levels':levels,'scope':'bounded observations include EVERY allowed signal for EVERY allowed history position; complete means full prefix since reset. No-conflict is not a global separability proof.'})
 dump(OUT/'history_refinement.json',output)

def budgets():
 if not (OUT/'method_freeze.json').exists():return
 rows=[]
 for m in read(OUT/'method_freeze.json')['rows']:
  if m['status']!='frozen':continue
  k=m['case'];ids=[f'pool/{k}/{i}' for i in range(m['pool_generation_calls_consumed'])]+[f'repair/{k}/{m["arm"]}/{i}' for i in range(m['repair_model_calls'])]
  calls=[read(OUT/'model_calls'/i/'result.json') for i in ids]
  for c,i in zip(calls,ids):
   raw=OUT/'model_calls'/i/'response.raw.json'
   if raw.exists():env=read(raw);c['prompt_tokens']=env.get('prompt_eval_count');c['completion_tokens']=env.get('eval_count')
  rows.append({'parent_bug_id':m['parent_bug_id'],'case':k,'method':m['arm'],'model':m.get('model','qwen2.5-coder:7b-instruct'),'logical_generation_calls':len(calls),'physical_generation_shared_initial':True,'prompt_tokens':sum(c.get('prompt_tokens') or 0 for c in calls),'completion_tokens':sum(c.get('completion_tokens') or 0 for c in calls),'model_wall_seconds':sum(c['wall_seconds'] for c in calls),'actual_candidate_rtl_checks':len(m['validation_runs']),'validation_wall_seconds':m['validation_seconds'],'additional_signal_bits':0,'additional_history_bits_permission':m['additional_history_bits_permission'],'actual_history_names_used':sorted(set(re.findall(r'\bp[123]_\w+',m['candidate']['antecedent']+' '+m['candidate']['consequent']))),'solver_seconds':None,'solver_status':'not_used','call_ids':ids,'run_ids':m['validation_runs']})
 dump(OUT/'budgets.json',rows)
 with (OUT/'budgets.csv').open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows([{k:json.dumps(v) if isinstance(v,list) else v for k,v in r.items()} for r in rows])

def supplement(runs):
 failures=[]
 for folder in ['failed_attempts','protocol_v1_missing_compile_feedback','protocol_v2_skipped_unsupported_slot','checker_lowering_v1']:
  for p in (OUT/folder).rglob('result.json'):
   r=read(p)
   if 'compile' in r:
    rd=p.parent;cmd=r['compile']['argv'];script='#!/bin/sh\nset -eu\ncd '+shlex.quote(str(rd))+'\n'+shlex.join(cmd)+'\n'+('vvp sim.out\n' if r.get('simulate') else '')
    (rd/'reproduce_archived.sh').write_text(script);failures.append({'kind':'archived_run','status':r['status'],'record':str(p.relative_to(ROOT)),'reproduce':str((rd/'reproduce_archived.sh').relative_to(ROOT))})
   elif 'call_id' in r:failures.append({'kind':'archived_model_call','status':r['status'],'record':str(p.relative_to(ROOT))})
 for p in (OUT/'failed_model_calls_gpu').rglob('result.json'):
  r=read(p);failures.append({'kind':'gpu_model_call','status':'tool_error','raw_status':r['status'],'record':str(p.relative_to(ROOT))})
 # A request with no final result is interrupted/unknown, not a completed call.
 for archive in ['protocol_v1_missing_compile_feedback','protocol_v2_skipped_unsupported_slot']:
  for p in (OUT/archive/'model_calls').rglob('request.json'):
   if not (p.parent/'result.json').exists():failures.append({'kind':'interrupted_call','status':'unknown_interrupted','request':str(p.relative_to(ROOT))})
 dump(OUT/'failure_ledger.json',failures)
 physical=[]
 for label,folder in [('final_protocol',OUT/'model_calls'),('gpu_failure',OUT/'failed_model_calls_gpu'),('missing_compile_feedback',OUT/'protocol_v1_missing_compile_feedback/model_calls'),('skipped_first_candidate',OUT/'protocol_v2_skipped_unsupported_slot/model_calls')]:
  for p in folder.rglob('request.json'):
   result=read(p.parent/'result.json') if (p.parent/'result.json').exists() else {};raw=read(p.parent/'response.raw.json') if (p.parent/'response.raw.json').exists() else {}
   physical.append({'phase':label,'request':str(p.relative_to(ROOT)),'status':result.get('status','unknown_interrupted'),'wall_seconds':result.get('wall_seconds'),'prompt_tokens':raw.get('prompt_eval_count',result.get('prompt_tokens')),'completion_tokens':raw.get('eval_count',result.get('completion_tokens'))})
 dump(OUT/'all_physical_model_costs.json',{'attempt_records':physical,'recorded_attempts':len(physical),'known_wall_seconds':sum(r['wall_seconds'] or 0 for r in physical),'unknown_duration_attempts':sum(r['wall_seconds'] is None for r in physical),'known_prompt_tokens':sum(r['prompt_tokens'] or 0 for r in physical),'known_completion_tokens':sum(r['completion_tokens'] or 0 for r in physical),'unknown_token_attempts':sum(r['completion_tokens'] is None for r in physical),'unknown_not_imputed':True})
 validation=[]
 for label in ['runs','failed_attempts','protocol_v1_missing_compile_feedback/runs','protocol_v2_skipped_unsupported_slot/runs','checker_lowering_v1']:
  for p in (OUT/label).rglob('result.json'):
   r=read(p)
   if 'compile' not in r:continue
   validation.append({'phase':label,'record':str(p.relative_to(ROOT)),'status':r['status'],'compile_seconds':r['compile']['wall_seconds'],'simulate_seconds':r['simulate']['wall_seconds'] if r.get('simulate') else None,'total_known_seconds':r['validation_wall_seconds']})
 dump(OUT/'all_physical_validation_costs.json',{'records':validation,'physical_attempts':len(validation),'total_known_seconds':sum(r['total_known_seconds'] for r in validation),'includes_archived_and_audit_replays':True,'note':'The four final command-replay spot checks have separate audit_replay.command.json durations; they are not method-budget checks.'})
 equivalence=[];reference_issues=[];window=[]
 for r in runs:
  if r['variant']=='correct' and r['status']=='ok' and r['obligation_violation_cycles']:
   reference_issues.append({'run':r['run_id'],'parent_bug_id':r['parent_bug_id'],'violation_cycles':r['obligation_violation_cycles'],'interpretation':'fixed RTL violates independent obligation on this stimulus; alarms here are not labelled false positives'})
  if '/equivalent_rewrite/' in r['run_id']:
   target=r['run_id'].replace('/equivalent_rewrite/','/equivalence_reference/');base=next((x for x in runs if x['run_id']==target),None)
   eq=None
   if base and r['status']==base['status']=='ok':eq=read(ROOT/r['trace'])==read(ROOT/base['trace']) and r['candidates']==base['candidates']
   equivalence.append({'run':r['run_id'],'reference':target,'observed_equivalent':eq,'status':'unknown' if eq is None else 'checked_match' if eq else 'mismatch'})
  if '/e12/hold_' in r['run_id'] or '/e12/more_' in r['run_id']:
   window.append({'run':r['run_id'],'parent_bug_id':r['parent_bug_id'],'accepted_transactions':r['accepted_transactions'],'sample_cycles':len(read(ROOT/r['input'])),'candidates':[{k:c.get(k) for k in ['id','trigger_count','fail_hit','first_failure_cycle','first_failure_transaction']} for c in r['candidates']],'independent_violation_count':'unknown'})
 dump(OUT/'equivalence_checks.json',equivalence);dump(OUT/'reference_contract_issues.json',reference_issues);dump(OUT/'window_transaction_results.json',window)
 cov=[]
 for r in runs:
  if '/controlled_coverage/' in r['run_id']:
   cov.append({'run':r['run_id'],'parent_bug_id':r['parent_bug_id'],'controlled_mutation':r.get('controlled_mutation'),'provenance':'new_controlled_RTL_mutation; assertions remain original natural candidates','status':r['status'],'obligation_violation_cycles':r.get('obligation_violation_cycles'),'candidates':r['candidates']})
 dump(OUT/'controlled_partial_coverage.json',cov)
 coverage=[]
 for r in runs:
  if r['status']!='ok':continue
  cycles=read(ROOT/r['obligations']);names=sorted({n for x in cycles for n in x['checks']})
  for c in r['candidates']:
   for name in names:
    evaluated=[x['cycle'] for x in cycles if name in x['checks']];violations=[x['cycle'] for x in cycles if name in x['violations']];caught=sorted(set(violations)&set(c['failure_cycles']))
    coverage.append({'run':r['run_id'],'parent_bug_id':r['parent_bug_id'],'candidate':c['id'],'obligation_component':name,'evaluated_cycles':evaluated,'violating_cycles':violations,'detected_at_same_cycle':caught,'coverage':len(caught)/len(violations) if violations else None,'attribution_limit':'same-cycle detection is not a proof of logical implication or isolated component causality; controlled_partial_coverage supplies isolated mutant checks'})
 dump(OUT/'obligation_coverage.json',coverage)
 # Cluster unit is parent; there is one output assertion per parent per method.
 parents=read(OUT/'parent_results.json');metrics=[];rng=random.Random(20261009)
 for method in sorted({r['method'] for r in parents}):
  allrows=[r for r in parents if r['method']==method];known=[r for r in allrows if r['complete_pass'] is not None];vals=[int(r['complete_pass']) for r in known];n=len(vals)
  boot=sorted(sum(rng.choices(vals,k=n))/n for _ in range(2000)) if n else []
  common={'model':'qwen2.5-coder:7b-instruct','method':method,'selection_scope':'first_candidate','k':1,'metric':'frozen_contract_success','value':sum(vals)/n if n else None,'candidate_observation_count':n,'case_count':n,'parent_bug_count':n,'unknown_parent_count':len(allrows)-n,'deduplicated':True,'dedup_key':'parent_bug_id','parent_aggregation':'all_observations','overlap_status':'non_overlap','sample_definition':'one frozen final assertion per independent parent; all hidden scenario cells; unknown excluded','ci_level':0.95,'ci_lower':boot[49] if boot else None,'ci_upper':boot[1949] if boot else None,'ci_method':'percentile_cluster_bootstrap','bootstrap_unit':'parent_bug_id','bootstrap_repetitions':2000,'random_seed':20261009,'selection_scope_note':'first and only FINAL frozen assertion; method field distinguishes raw first from selected/repaired','known_population':[r['parent_bug_id'] for r in known]}
  for unit in ['candidate','case','parent_bug']:metrics.append({**common,'aggregation_unit':unit})
 dump(OUT/'metrics.json',metrics)
 tests=[]
 for a,b in itertools.combinations(sorted({r['method'] for r in parents}),2):
  aa={r['parent_bug_id']:r for r in parents if r['method']==a and r['complete_pass'] is not None};bb={r['parent_bug_id']:r for r in parents if r['method']==b and r['complete_pass'] is not None};common=aa.keys()&bb.keys();n01=sum(not aa[k]['complete_pass'] and bb[k]['complete_pass'] for k in common);n10=sum(aa[k]['complete_pass'] and not bb[k]['complete_pass'] for k in common);discord=n01+n10
  tests.append({'method_a':a,'method_b':b,'paired_parent_count':len(common),'n01':n01,'n10':n10,'exact_two_sided_p':min(1,2*sum(math.comb(discord,j) for j in range(min(n01,n10)+1))/(2**discord)) if discord else 1,'paired_risk_difference':(n10-n01)/len(common) if common else None,'matched_odds_ratio':n10/n01 if n01 else None,'odds_ratio_note':'undefined when n01=0','parent_binary_rule':'all_observations','population':sorted(common)})
 dump(OUT/'paired_statistics.json',tests)

def document(runs):
 s=read(OUT/'summary.json');pairs=read(OUT/'collision_pairs.json');win=read(OUT/'window_results.json');hist=read(OUT/'history_refinement.json');obs=read(OUT/'observation.json')
 lines=['# AssertionForge 修复目标保护实验（2026-10-09）','', '本报告由逐次运行记录生成。统计单位是父 bug；窗口、输入轨迹和多条断言不会增加独立样本数。所有结果仅限实际仿真输入与检查范围。','', '## 设置与可复现范围','',f"冻结 {s['parent_bugs']} 个父案例：onehot、filter-counter（case122）、Depth=0 FIFO、spill/flush、统计流水线、中断使能。先完成前三例的 fixed/buggy 六次试运行，再冻结扩展集。旧自然候选来自已有 Qwen3 slot 01–07；slot 08 是人为矛盾控制。filter-counter 不在旧 slot 池，旧签名实验中它仅作为明确标注的工程控制。新方法比较使用另外冻结的 Qwen2.5 7B 候选池。",'', '仓库 `.git` 无有效 HEAD；版本用 SHA256 清单标识。已检索仓库及父目录，未找到 AGENTS.md；阅读 README、结果报告约束、旧碰撞审计与实际 checker。历史修复提交无法追溯，六例均按已有人工变异报告，不能称为历史修复样本。','', '工具：WSL Ubuntu、Python 3.12.3、Icarus 12.0；完整版本原始输出见 version_*.stdout/stderr。固定种子 20261009。Qwen CPU 实际配置见 runtime_amendment.json、每次 request.json 与 model_tags.json。GPU 18 次调用因 CUDA kernel image 错误失败，保留在 failed_model_calls_gpu；CPU 预检与失败调用不混入方法效果分母。','', '原始 assertion 与实际执行的 checker_tb.sv 分开保存。Icarus 执行显式过程监视器，不宣称原生 SVA/formal proof；支持当前与下一拍蕴含、明确 reset-to-zero 的 p1/p2/p3 观察寄存器。旧 slot AST 另由 Python 在保存的 RTL 轨迹上逐拍交叉核验。输入在下降沿驱动，上升沿 NBA 前采样。复位首样本的 X 不记有效违例，复位外 X 记未知。','', '## 1. 旧签名与语义差异','',f"对冻结父案例中的 {s['legacy_tied_pairs_checked']} 个旧 FP/TP 同签名对保留原始签名、两条 assertion 和来源。自然候选中 {s['natural_tied_pairs_distinguished']} 对在新合法输入上出现不同的合法行为接受集合或目标违例覆盖集合。这个数字表示集合差异，不是胜负或成功率；仅 fail-hit 大小不同不构成质量排序。slot 08 控制不计入自然候选结论。完整逐对依据见 collision_pairs.json。"]
 for p in pairs:
  if p['a']=='slot_06' and p['b']=='slot_07':
   lines+=['',f"- `{p['parent_bug_id']}`：{p['status']}；原文 A：`{p['assertion_a']}`；B：`{p['assertion_b']}`。"]
   if p['evidence']:
    e=next((x for x in p['evidence'] if '/held_24/' in x['run'] and x['run'].endswith('/correct')),p['evidence'][0]);lines.append(f"  证据 `{e['run']}`：A 首败 {e['a']['first_failure_cycle']}，B 首败 {e['b']['first_failure_cycle']}；A/B 误报周期 {e['a']['false_positive_cycles']} / {e['b']['false_positive_cycles']}；漏报周期 {e['a']['missed_violation_cycles']} / {e['b']['missed_violation_cycles']}。")
 lines+=['','## 2. 窗口与事务','',f"H=24、2H=48、4H=96；{len(win)} 个父案例×RTL 比较检查了尾段输入保持不变，其中按 fail-hit 排序发生变化的比较为 {s['window_rank_changed']}。交易增量对照独立执行 more_24/48/96。window_results.json 保存排名；每次 transactions.json 标注输入 episode 或接受事件，candidate_results.csv 给出首次失败周期与对应事务。",'', '独立违例数统一保留 unknown：可数的是义务违反采样点、触发和接口接受事务，不能可靠把相邻报警归为独立因果事件。保持输入不变也可能产生连续被接受事务，因此保持窗口组与真实新增事务组的区别需读取 accepted_transactions；尤其不把 held-flush 每拍重复命令视为一次事件。','', '## 3. 观察信息与表达能力','', 'observation.json 的实际执行对把观察限制为完整输入历史：相同输入驱动 fixed/buggy 而义务标签不同，增加输出信号后在已检查执行对上消除冲突。该受限观察实验与方法默认完整端口权限不同，不能据此宣称默认权限无解。history_refinement.json 则使用方法的全部允许端口，比较当前采样、1/2/3 拍记忆及完整复位后历史；每个冲突都保存两条实际执行引用与完整允许历史。','']
 for h in hist:lines.append('- '+h['parent_bug_id']+'：'+', '.join(f"history={v['history_depth']} 的冲突组={v['conflict_groups']}" for v in h['levels'])+'。')
 lines+=['',f"受控 onehot 抽象只观察 boolean(oh_i) 与 err_o，实际枚举 16 个输入向量、两种 RTL，并检查两 Boolean 输入上的全部 16 个真值函数：{obs['controlled_abstraction']['status']}。扩展到原始四位 oh_i 的检查错误数 {obs['controlled_abstraction']['refinement_errors']}。有限语法无解仅限这个列明的真值函数空间；其他未找到冲突/候选的地方不宣称 UNSAT。没有执行通用 SMT/formal 搜索，因此通用表达能力与求解时间为未知/未使用。",'', '## 4. 闭环与消融','', '所有方法的初始权限相同。第一候选只消耗一次初始生成；等预算选择使用三条冻结候选；现有反馈与各闭环使用一条初始候选加两次实际修复。闭环每次对训练与已积累 held 场景的 fixed/buggy 重查。义务闭环同时反馈漏报、合法参考误报与非空触发；消融分别使用通用 RTL diff、隐藏误报反馈并移除选择中的误报项、禁止历史细化。equal_information_control 一开始得到相同三拍历史权限。','', '比较以三次模型调用和 12 个验证单元为预算上限；语法失败会使实际仿真单元更少，token 与墙钟时间也不同。budgets.csv 逐方法报告实际消耗，不能声称等 token/等耗时，更不能将更大观察权限的收益全部归于机制。各方法重用已生成的同一个初始候选，物理模型调用只发生一次，逻辑归账明确标注。','', '| 方法 | 完整通过父 bug | 已知父 bug | 未知父 bug |','|---|---:|---:|---:|']
 for m,r in s['methods'].items():lines.append(f"| {m} | {r['pass']} | {r['known']} | {r['unknown']} |")
 lines+=['','完整通过要求全部已执行隐藏场景无合法参考误报、无目标漏报、至少一次触发且确有目标违例。未知不计成功或失败。此表为有限样本描述，不是统计显著改善结论。逐父结果与义务覆盖见 parent_results.csv；格式错误/无可执行属性保留未知。','', '## 5. 独立回归与限制','', '生成/选择/修复完成后冻结 assertion，随后加载此前未提供给模型的连续输入、背压/停顿、复位打断、中断测试/清除、0/最大值等场景。Depth=0 FIFO 的 DataWidth=4、filter 的 CntWidth=3（阈值5）实际重新编译并执行；不把 FIFO 专用适配器声称为其他 Depth 的测试。等价 RTL 内部重命名/无效线声明单列；spill invalid-data=0xA5 是行为不同的合法变体：valid_o=0 时总线无效，不能要求其一定清零。这个合法性解释记录于冻结义务；若外部协议要求零化，该变体需重新分类。','', '统计流水线在连续不同长度事件上，当前 fixed RTL 的长度寄存器会覆盖前一事件。独立义务检查可能判定 fixed 本身违约；对应报警不是误报。中断原始一句话规格与 FlopOutput=1 的采样时刻存在歧义，此实验明确使用寄存器后一拍的屏蔽义务，不能混同旧 same-cycle 标签。','', '六个父 bug 是按可检查义务和代表机制选择的小集合，未扩展为完整仓库总体。无可追溯历史修复样本。没有 JasperGold 形式证明，没有完整参数空间覆盖，没有把时序样本当独立 bug。工程控制只用于流程验证、受控语法空间或观察分析。','', '## 运行规模与复现','',f"当前重新编译运行记录 {s['rtl_runs']}，状态 {json.dumps(s['run_status'],ensure_ascii=False)}；候选观察 {s['candidate_observations']}。CPU 模型调用 {s['model_calls']}，状态 {json.dumps(s['model_status_counts'],ensure_ascii=False)}。模型墙钟累计 {s['model_wall_seconds']:.2f}s，编译+仿真累计 {s['validation_wall_seconds']:.2f}s；这不是形式求解耗时。",'', '最简抽查（仓库根目录，使用现有 WSL 虚拟环境）：','', '```powershell',"wsl -d Ubuntu -- bash -lc 'source /mnt/d/AssertionForge-main1/.venv-pilot/bin/activate && python /mnt/d/AssertionForge-main1/scripts/run_repair_contract.py audit'",'```','', '每个 runs/... 目录的 reproduce.sh 可直接重编译并仿真该原始输入与 checker；例如：','', '```powershell',"wsl -d Ubuntu -- sh /mnt/d/AssertionForge-main1/deliverables/repair_contract_20261009/runs/e12/held_24/spill/correct/reproduce.sh",'```','', '全流程 action 顺序：pilot → freeze → model-pool → experiments → methods → report → audit；脚本对已完成结果使用缓存，逐运行 reproduce.sh 才是强制实际重跑。GPU 环境故障恢复命令与配置见 recover_contract_model.py / runtime_amendment.json。最终补充表由 `python scripts/finish_repair_contract.py` 从运行记录生成。','', 'audit.json 是亲自执行复现命令、checker 哈希、fail-hit 重算的一致性结果；legacy_checker_crosscheck.json 是独立 AST 逐周期交叉核验。artifact_manifest.json 给出最终主要证据 SHA256。']
 text='\n'.join(lines)+'\n'
 text=text.replace('spill invalid-data=0xA5 是行为不同的合法变体：valid_o=0 时总线无效，不能要求其一定清零。这个合法性解释记录于冻结义务；若外部协议要求零化，该变体需重新分类。','onehot StrictCheck=0 是源模块文档明确允许的配置，实际改变 en_i=1、oh_i=0 时的错误输出，并重新构建运行。spill invalid-data=0xA5 只作为合法性尚未确定的探索控制：原始规格没有独立确认 invalid 数据是否可见，因此不把它当作已证实的合法变体，spill 完整合约结果全部记为未知。冻结的 validity-gated 义务解释保留作条件分析，不能据此主张完整保护。')
 text+='\n## 审计补充\n\n'
 text+='观察细化按预定协议在第二轮开放 p1/p2/p3 端口历史；未实现自动可观察性求解器。相同信息对照从第一轮起拥有相同权限。因此只能讨论这套已执行协议，不能把结果泛化为任意义务驱动修复器。\n\n'
 text+='义务覆盖是独立义务违例采样点与 assertion 报警的对应率，不能据此证明属性在未测试空间中逻辑蕴含完整契约。obligation_coverage.json 按义务分量给出检查、违反和报警周期；controlled_partial_coverage.json 则使用隔离义务的受控变异：统计案例 slot 06/07 均漏检后续有效脉冲缺失和长度破坏。\n\n'
 text+='第一轮方法运行因缺少具体编译诊断而中止，原始调用、checker 和日志保存在 protocol_v1_missing_compile_feedback，并提供 reproduce_archived.sh。修正后的整轮比较重新从原冻结池执行，归账独立。failure_ledger.json 列出工具失败、过程修复前尝试及中断调用，均不作为成功/失败性能样本。\n\n'
 text+='metrics.json 提供按父 bug 聚类的 95% bootstrap 区间（2000 次）；paired_statistics.json 只对双方均已知的父 bug 交集计算精确 McNemar。不同方法的已知集合可能不同，不能直接以各自分母的成功率声称优劣。少量且目的性选择的父 bug 不支持总体外推。\n\n'
 text+='没有调用 Claude Code；所有命令由本轮脚本实际执行并核查。没有下载新模型或依赖。\n'
 text+='\n候选装载器曾跳过统计案例 delay=2 的不支持输出；该轮归档于 protocol_v2_skipped_unsupported_slot。修正后第一候选严格指原始 slot 0，语法不支持仍占据其位置。受影响的统计案例按相同预算重新生成修复，其他父案例保留。全部物理调用（包括失败、被替代协议与中断）的已知耗时和未知 token 单列于 all_physical_model_costs.json。\n'
 text+='\nFIFO 固定输入计划末尾若撤销了仍在停顿中的项，会在 input_legality_audit.json 标出并插入一次合法接收后重跑；原计划与错误运行归档保留，训练输入未修改。FIFO 合法性范围明确是本案例的 Depth=0 兼容契约，不能套用上游通用 Depth>0 的 ASSERT_INIT / full-write 约束后仍声称适配等价。\n'
 text+='\n独立 AST 核验发现旧过程 checker 将多位 antecedent 直接赋给 1 位 ant_d，导致只取最低位。新 checker 改用显式非零布尔化，并重新执行全部可执行记录。旧 checker 与对应日志保留在 checker_lowering_v1；lowering_replay_audit.json 检查所有训练反馈是否不变，只有不变才保留已冻结模型选择。旧 FP/TP 签名仍按历史原值保存，不能用本次语义修正覆盖历史。\n'
 text+='\n逐方法 budgets.csv 记录方法决策时实际验证耗时；对应原始结果若因 checker 修复重放而归档，可在 checker_lowering_v1 的同相对路径查找。最终结果引用修正后的实际 checker。全部物理编译/仿真消耗（含修复流程、重放和被替代协议）见 all_physical_validation_costs.json，不能把这些排除在研究实际总成本之外。\n'
 (OUT/'REPORT.md').write_text(text)

if __name__=='__main__':
 runs=recount();history_search(runs);budgets();report();supplement(runs);document(runs)
 # Final checksums are sealed once, after the actual command replays.
