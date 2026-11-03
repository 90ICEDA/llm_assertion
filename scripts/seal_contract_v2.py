"""Seal final records after successful independent replay; never modify old evidence."""
import json
from run_contract_v2 import OUT,OLD,ROOT,read,dump,sha,rel,stamp,check_freeze
check_freeze();audit=read(OUT/'audit.json');assert audit['pass']
summary=read(OUT/'summary.json');assert summary['permission_failures']==0
parents=read(OUT/'parent_results.json');assert len(parents)==48
assert not any(r['complete_pass'] for r in parents if r['case'] in ['spill','intr'])
original_manifest=read(OLD/'artifact_manifest.json')
original_check=[]
for p,h in original_manifest.items():
    if p.startswith('scripts/') or p in [rel(OLD/n) for n in ['REPORT.md','summary.json','all_runs.json','method_freeze.json','collision_pairs.json','observation.json']]:
        original_check.append({'path':p,'pass':sha(ROOT/p)==h})
assert all(x['pass'] for x in original_check)
dump(OUT/'original_evidence_unchanged.json',{'checked':original_check,'scope':'all original sealed script entries plus principal original results; complete original 46001-file verification was already supplied by the prior audit, not claimed repeated here'})
ledger={'main_compile_invocations':summary['physical_compile_invocations'],'main_simulation_invocations':summary['physical_simulation_invocations'],
        'main_compile_and_sim_wall_seconds':summary['physical_compile_and_sim_seconds'],'new_model_calls':summary['physical_model_calls'],'new_model_wall_seconds':summary['physical_new_model_wall_seconds'],
        'successful_final_audit_replay_compile_invocations':len(audit['replays']),'successful_final_audit_replay_simulation_invocations':len(audit['replays']),'final_audit_replay_combined_seconds':audit['extra_audit_replay_wall_seconds'],
        'pre_serialization_error_replay_compile_invocations':4,'pre_serialization_error_replay_simulation_invocations':4,'pre_serialization_error_replay_seconds':None,
        'unknown_cost_reason':'four completed replay invocations preceded NameError before duration record serialization; raw checker/RTL/stdout/wave evidence retained',
        'model_and_method_phase_wall_seconds':read(OUT/'phase_wall_times.json')['model_and_method_phase']['elapsed_seconds'],
        'main_physical_costs_include_window_repair_and_calibration':True,'logical_reused_pool_costs':'budget_ledger.json','no_full_dimensional_budget_equality_claim':True}
dump(OUT/'total_physical_costs.json',ledger)
failures=[{'stage':'model','id':p.parent.as_posix(),'status':read(p)['status'],'evidence':rel(p)} for p in (OUT/'model_calls').rglob('result.json') if read(p)['status']!='generated']
failures += [{'stage':'checker','id':r['run_id'],'status':r['status'],'evidence':r['run_id']+'/result.json'} for r in read(OUT/'run_results.json') if r['status']!='ok']
failures += [{'stage':'audit','status':'interrupted_for_io_optimization','evidence':rel(OUT/'audit_interruption.json')},{'stage':'audit','status':'tool_error_corrected_and_replayed','evidence':rel(OUT/'audit_serialization_failure.json')},{'stage':'hidden_window','status':'pending_obligations_closed_and_replayed','evidence':rel(OUT/'window_closure_amendment.json')}]
dump(OUT/'failure_ledger.json',failures)
dump(OUT/'delivery_status.json',{'time':stamp(),'implemented_and_executed':True,'global_complete_contract_claim':False,'unresolved':['spill payload observability','interrupt same-sample versus registered-mask specification','FIFO contract limited to Depth=0 adapter target, no full upstream equivalence','no historical repair provenance available','Ollama complete prompt-cache accounting unavailable','some unsupported generated expressions prevent semantic verdicts'],'negative_findings':['zero complete passing method-parent cells','no obligation-specific superiority','no full-history conflict found under default full-port observation in checked executions'],'audit_pass':audit['pass'],'unknown_parent_cells':summary['unknown_parent_cells']})
paths=[p for p in OUT.rglob('*') if p.is_file() and p.name not in ['artifact_manifest.json','ollama_server.log']]
scripts=[ROOT/'scripts'/n for n in ['run_contract_v2.py','contract_v2_spec.py','amend_contract_v2_preexecution.py','contract_v2_observations.py','contract_v2_hidden.py','contract_v2_report.py','contract_v2_calibration.py','contract_v2_close_windows.py','contract_v2_audit.py','seal_contract_v2.py']]
manifest={rel(p):sha(p) for p in paths+scripts};dump(OUT/'artifact_manifest.json',manifest)
print(json.dumps({'files_sealed':len(manifest),'audit_pass':audit['pass'],'runs':summary['runs'],'unknown_parent_cells':summary['unknown_parent_cells'],'complete_pass_parent_cells':summary['complete_pass_parent_cells']},indent=2),flush=True)
