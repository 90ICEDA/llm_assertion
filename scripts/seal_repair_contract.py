import json,sys,subprocess,os,concurrent.futures
from pathlib import Path
from run_repair_contract import ROOT,OUT,read,dump,sha

checks=read(OUT/'audit.json');cross=read(OUT/'legacy_checker_crosscheck.json');summary=read(OUT/'summary.json')
assert checks['all_pass'], 'resolve audit mismatches before delivery'
assert cross['all_match'], 'resolve independent legacy-checker mismatches before delivery'
assert len(read(OUT/'method_freeze.json')['rows'])==48
assert len(read(OUT/'parent_results.json'))==48
known_runs=read(OUT/'all_runs.json');assert len(known_runs)==summary['rtl_runs']
legality=read(OUT/'input_legality_audit.json');assert all(x['legal'] for x in legality['rows'])
native=[]
for k in ['onehot','filter','fifo','spill','stat','intr']:
 for slot in range(3):
  p=OUT/'model_calls/pool'/k/str(slot)/'result.json';r=read(p)
  assert p.exists();native.append({'case':k,'original_slot':slot,'status':r['status'],'request':r['request']})
dump(OUT/'final_inventory_checks.json',{'original_pool_slots':native,'method_parent_cells':48,'audit_checks':checks['count'],'legacy_crosschecks':cross['count'],'all_pass':True})
dump(OUT/'runtime_python.json',{'executable':sys.executable,'version':sys.version,'platform':sys.platform})
equiv=read(OUT/'equivalence_checks.json');assert not any(r['status']=='mismatch' for r in equiv)
variants=[]
for r in known_runs:
 if '/legal_variant/' not in r['run_id'] or r['case']!='onehot':continue
 ref=next((x for x in known_runs if x['run_id']==r['run_id'].replace('/legal_variant/','/legal_variant_reference/')),None)
 diffs=[]
 if r['status']=='ok' and ref and ref['status']=='ok':
  a,b=read(ROOT/r['trace']),read(ROOT/ref['trace'])
  diffs=[{'cycle':x['cycle'],'StrictCheck_0_err_o':x['err_o'],'StrictCheck_1_err_o':y['err_o']} for x,y in zip(a,b) if x['err_o']!=y['err_o']]
 variants.append({'run':r['run_id'],'reference':ref['run_id'] if ref else None,'status':r['status'],'actual_output_differences':diffs,'source_spec':'prim_onehot_check parameter StrictCheck comments in frozen/onehot/correct.v','target_violations':r.get('obligation_violation_cycles')})
dump(OUT/'legal_variant_checks.json',variants)
assert any(v['actual_output_differences'] for v in variants)
report=OUT/'REPORT.md';text=report.read_text().replace('equal_information_control 一开始得到相同三拍历史权限','equal_information_control 从首次修复起得到相同三拍历史权限')
text=text.replace('交易增量','事务增量')
text=text.split('\n<!-- FINAL_SEAL -->',1)[0].split('\n最终人工驱动抽查完成',1)[0]+'\n<!-- FINAL_SEAL -->\n'
parents=read(OUT/'parent_results.json')
pass_sets={m:sorted(r['case'] for r in parents if r['method']==m and r['complete_pass'] is True) for m in sorted({r['method'] for r in parents})}
dump(OUT/'mechanism_analysis.json',{'complete_pass_cases':pass_sets,'finding':'All six repair arms complete only onehot. The obligation arm has no unique passing parent beyond generic feedback, ablations or equal-information control. Baseline onehot is unsupported, so observed executability improvement is not evidence of obligation-specific superiority. Different unknown populations prevent naive rate comparison.','history_refinement_scope':'Conflict elimination measured on saved trajectories only; filter needs depth 3 in this checked set, stat depth 2, spill and interrupt depth 1; no global proof.'})
text+='\n机制归因核对：六个修复/消融/等信息臂完整通过的父案例均只有 onehot；义务闭环没有取得其他臂未取得的完整通过。onehot 的首候选/选择基线因语法不支持为未知，修复后的可执行性提升不能归因于义务约束的独有效果。filter 的实际观察冲突在 3 拍历史、stat 在 2 拍、spill/中断在 1 拍时于本次有限轨迹集合中消失；这也不等于模型找到了合格断言。\n'
text+='\n最终人工驱动抽查完成：audit.json 中 '+str(checks['count'])+' 项一致性检查全部通过；独立 Python AST 与原始 slot 监视器的 '+str(cross['count'])+' 个交叉核验全部吻合。重放 onehot、filter、FIFO、spill 四个代表命令，重新编译及逐周期日志与记录一致。onehot 合法参数变体确实产生不同错误输出，见 legal_variant_checks.json。\n'
text+='\n最终交付入口：summary.json（规模/状态）、candidate_results.csv（逐候选运行）、parent_results.csv（父 bug 验收）、budgets.csv（实际预算）、all_physical_model_costs.json（包括失败尝试的实际消耗）、REPORT.md（范围与解释）。\n'
report.write_text(text)
files=[Path(folder)/name for folder,dirs,names in os.walk(OUT) for name in names if name not in ['artifact_manifest.json','ollama_server.log']]
files += list((ROOT/'scripts').glob('*contract*.py'))
with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
 hashes=list(executor.map(lambda p:(str(p.relative_to(ROOT)),sha(p)),files))
dump(OUT/'artifact_manifest.json',dict(hashes))
print(json.dumps({'summary':summary,'audit_checks':checks['count'],'crosschecks':cross['count'],'manifest_files':len(files),'equivalence':{s:sum(r['status']==s for r in equiv) for s in {r['status'] for r in equiv}},'legality_repaired_runs':legality['repaired_runs']},indent=2))
