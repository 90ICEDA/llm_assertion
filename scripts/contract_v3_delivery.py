"""Final receipts and concise requirement/evidence map; no new experiments."""
import collections,json
import run_contract_v3 as x
from contract_v3_report import table

def main():
    summary=x.read(x.OUT/'summary.json');audit=x.read(x.OUT/'audit.json');assert audit['pass'];x.check_freeze()
    parents=x.read(x.OUT/'parent_results.json')
    assert summary['complete_pass_parent_cells']==sum(r['complete_pass'] is True for r in parents)
    assert summary['known_failure_parent_cells']==sum(r['complete_pass'] is False for r in parents)
    assert summary['unknown_parent_cells']==sum(r['unknown'] for r in parents)
    for p in (x.OUT/'failed_attempts').glob('*/reproduce.sh'):
        original=x.read(p.parent/'compile.command.json')['cwd'];(p.parent/'reproduce_archived.sh').write_text(p.read_text().replace(original,str(p.parent)))
    requirements=[
      {'id':'1','status':'completed','evidence':['unknown_inventory.json','unknown_reason_detail.csv','protocol.json','protocol_freeze.json','pool_freeze.json'],'detail':'v2 located; original failure expressions and logs classified; new frozen directory and unchanged 18-slot pool'},
      {'id':'2','status':'completed_in_declared_subset','evidence':['qualification.json','code_snapshot/contract_v3_checker.py','runs/*/normalization.json'],'detail':'generic unsigned signal popcount and exact delay 0/1/2; no label-based candidate edits; unsupported grammar retained'},
      {'id':'3','status':'completed_with_reference_scope_limit','evidence':['qualification/','independent_expression_crosscheck.json','audit_replays/','audit.json'],'detail':'11 tests / 664 expected checks; 1267 matched candidate runs; 3 legacy engineering expressions outside independent parser; 10 actual copied replays'},
      {'id':'4','status':'completed','evidence':['old_new_run_mapping.csv','model_calls/','method_freeze.json','permission_audit.json','hidden_evaluations.json'],'detail':'731 old-run replays plus all 8 methods x 6 parents; 72 fresh repair requests; no regenerated pool'},
      {'id':'5','status':'completed_with_explicit_unreached_points','evidence':['common_effective_budget_checkpoints.csv','common_budget_pairwise.csv','budget_ledger.csv','physical_model_costs.csv','physical_validation_costs.csv','phase_wall_time_envelopes.json'],'detail':'predeclared exact effective-execution and cycle points; repeated evidence separately counted; no_fp workload differs; no claim of simultaneous all-resource equality'},
      {'id':'6','status':'completed_for_frozen_six_parent_cohort','evidence':['parent_results.csv','obligation_acceptance.csv','branch_acceptance.csv','conditional_results.json','unknown_transition_counts.json','mechanism_analysis.json'],'detail':'only onehot succeeds across methods; spill/intr remain specification-unknown; additional independent parents not run within this round fixed budget'},
      {'id':'7','status':'completed','evidence':['REPORT.md','artifact_manifest.json','implementation_hashes.json','audit.json','delivery_status.json'],'detail':'raw input/checker/RTL/log/VCD/request/response preserved; independent replay and final raw-data reaggregation completed'}]
    for r in requirements:r['reproduce']='wsl -d Ubuntu -- python3 /mnt/d/AssertionForge-main1/scripts/contract_v3_report.py'
    table('requirement_resolution',requirements)
    validations=x.read(x.OUT/'physical_validation_costs.json');models=x.read(x.OUT/'physical_model_costs.json')
    byphase=[]
    for phase in sorted({r['phase'] for r in validations}):
        rows=[r for r in validations if r['phase']==phase]
        byphase.append({'phase':phase,'compile_attempts':len(rows),'simulation_attempts':sum(r['simulation_attempts'] for r in rows),'compile_plus_sim_seconds':sum(r['compile_seconds']+r['simulation_seconds'] for r in rows)})
    byphase.append({'phase':'independent_audit_replays','compile_attempts':len(audit['replays']),'simulation_attempts':sum(r['simulation_attempts'] for r in audit['replays']),'compile_plus_sim_seconds':None,'script_wall_seconds':audit['extra_audit_wall_seconds']})
    table('total_physical_costs_by_phase',byphase)
    x.dump(x.OUT/'delivery_status.json',{'time':x.v.stamp(),'experiment_execution_complete':True,'all_contracts_pass':False,'new_parent_bugs':0,'model_calls':len(models),'model_output_status':dict(collections.Counter(r['status'] for r in models)),
      'runs':summary['runs'],'effective_simulations':summary['effective_simulations'],'method_parent_outcomes':{k:summary[k] for k in ['complete_pass_parent_cells','known_failure_parent_cells','unknown_parent_cells']},
      'old_syntax_unknown_removed':summary['old_unsupported_now_ok'],'remaining_old_unsupported':summary['old_unsupported']-summary['old_unsupported_now_ok'],
      'physical_compile_attempts_including_audit':sum(r['compile_attempts'] for r in byphase),'physical_simulation_attempts_including_audit':sum(r['simulation_attempts'] for r in byphase),
      'audit_pass':audit['pass'],'audit_checks':audit['check_count'],'independent_replays':len(audit['replays']),
      'limits':['finite scenarios, one fixed local model and seed','spill and interrupt spec unresolved','58 old-run unsupported cases retained','3 old engineering expressions outside independent reference parser','no new independent parents or historical fixes this round','cycles and workload differences retained; no all-dimensional budget equality','full server prompt cache usage unknown'],
      'unexpected_pipeline_failures':[],'intentional_unsupported_retries':'two pilot filter compile failures were retried in full replay; archived and charged separately, not method-budget padding',
      'claude_code_used':False,'raw_reaggregation_complete':True,'command':'wsl -d Ubuntu -- python3 /mnt/d/AssertionForge-main1/scripts/contract_v3_report.py'})
    print(json.dumps(x.read(x.OUT/'delivery_status.json'),ensure_ascii=False,indent=2))

if __name__=='__main__':main()
