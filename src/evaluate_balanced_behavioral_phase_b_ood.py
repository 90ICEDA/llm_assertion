from __future__ import annotations
import argparse,json,time
from pathlib import Path
from evaluate_frozen_top1_v1 import derived,false_result,primitive_bools,run_case_eval,summarize,visible_signals
from evaluate_pilot_v2_frozen_ast_top1 import render,sha,dump
ROOT=Path(__file__).resolve().parents[1]; BASE=ROOT/"outputs/behavioral_preference_pilot_v2/balanced_behavioral_objective_v1/phase_b_refit_all30_v1"; TOP=BASE/"frozen_ood_top1_v1"; MANIFEST=TOP/"query_manifest.json"; OUT=ROOT/"outputs/phase_b_ood_eval_v1"; OLD=ROOT/"outputs/behavioral_preference_pilot_v2/frozen_top1_ast_v2/execution_evaluation_v1/frozen_top1_metrics.json"; DEFINITIONS=ROOT/"outputs/behavioral_preference_pilot_v1/frozen_top1_v1/frozen_metric_definitions_v1.json"; EXPECTED_SOURCE="137a58c4b891ff7df1104ac73a7c0e42d39fd3bc856af90c8958fbfcf9fd8aa3"; EXPECTED_ADAPTER="c1bc4c54f64a50acbdec3288de3325cffb6a05ed61a94a3c7a6df0ffd34bdb3a"; KEYS=("antecedent_signal","antecedent_polarity","consequent_signal","implication","relation")
def clock_reset(record): return record.get("clock"),record.get("reset")
def preflight():
    m=json.loads(MANIFEST.read_text()); problems=[]
    if m["status"]!="frozen_before_any_phase_b_ood_generation" or m["source_query_manifest_sha256"]!=EXPECTED_SOURCE or len(m["records"])!=48 or m["adapter"]["adapter_sha256"]!=EXPECTED_ADAPTER: raise RuntimeError("frozen Phase B OOD input mismatch")
    for r in m["records"]:
        d=TOP/"generations"/r["case_id"]; e=d/"evidence.json"; raw=d/"raw_response.txt"; ast=d/"ast.json"
        if not all(x.is_file() for x in (e,raw,ast)): problems.append(f"missing {r['case_id']}"); continue
        x=json.loads(e.read_text()); obj=json.loads(ast.read_text()); valid=x.get("status")=="complete" and x.get("prompt_sha256")==r["prompt_sha256"] and x.get("adapter_sha256")==EXPECTED_ADAPTER and x.get("schema_keys_valid") is True and x.get("ended_on_eos") is True and x.get("hit_max_new_tokens") is False and tuple(obj)==KEYS and sha(raw)==x.get("raw_response_sha256") and sha(ast)==x.get("ast_sha256") and sha(ROOT/r["prompt_path"])==r["prompt_sha256"]
        if not valid: problems.append(f"mismatch {r['case_id']}")
    if problems: raise RuntimeError("; ".join(problems[:10]))
    return m,{"status":"pass","query_count":48,"generation_count":48,"query_manifest_sha256":sha(MANIFEST),"source_query_manifest_sha256":EXPECTED_SOURCE,"adapter_sha256":EXPECTED_ADAPTER,"deletion_policy":"all 48 retained; failures false","repair":False,"reranker":False,"selector":False,"heldout_information":False}
def method_summary(rows,split):
    selected=rows if split=="union_overview" else [r for r in rows if split in r["memberships"]]; n=len(selected); families={r["bug_family"] for r in selected}; recalled={r["bug_family"] for r in selected if r["strict_success"]}; primary=sum(r["primary_success"] for r in selected); overfit=sum(r["trace_overfit"] for r in selected)
    return {"query_count":n,"compile_rate":sum(r["compile_ok"] for r in selected)/n,"SCS@1":sum(r["strict_success"] for r in selected)/n,"Fixed-Safe":sum(r["fixed_safe"] for r in selected)/n,"Target Detect":sum(r["target_detect"] for r in selected)/n,"Family Recall":len(recalled)/len(families),"Non-vacuity":sum(r["non_vacuity_metric"] for r in selected)/n,"TOR":overfit/primary if primary else None,"counts":{"strict_success":sum(r["strict_success"] for r in selected),"fixed_safe":sum(r["fixed_safe"] for r in selected),"target_detect":sum(r["target_detect"] for r in selected),"recalled_families":len(recalled),"families":len(families),"non_vacuous":sum(r["non_vacuity_metric"] for r in selected),"primary_success":primary,"trace_overfit":overfit}}
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--preflight-only",action="store_true"); ap.add_argument("--resume",action="store_true"); args=ap.parse_args(); manifest,audit=preflight(); OUT.mkdir(parents=True,exist_ok=True); dump(OUT/"pre_execution_audit.json",audit)
    if args.preflight_only: print(json.dumps(audit,sort_keys=True)); return
    began=time.perf_counter()
    for i,r in enumerate(manifest["records"],1):
        output=OUT/"records"/r["case_id"]/"evaluation.json"
        if args.resume and output.is_file(): continue
        d=TOP/"generations"/r["case_id"]; e=json.loads((d/"evidence.json").read_text()); ast=json.loads((d/"ast.json").read_text()); clock,reset=clock_reset(r); sva=render(ast,clock,reset); rendered=OUT/"rendered"/r["case_id"]/"candidate.sva"; rendered.parent.mkdir(parents=True,exist_ok=True); rendered.write_text(sva+"\n"); case=ROOT/r["dataset_root"]/r["case_id"]; started=time.perf_counter()
        try: result=run_case_eval(case_id=r["case_id"],assertion_text=sva,signal_names=visible_signals(case),use_property=False,runtime_dir=OUT/"runtime"/r["case_id"],cases_root=case.parent)
        except Exception as exc: result=false_result(f"evaluation_exception: {type(exc).__name__}: {exc}")
        row={"status":"complete","method":"phase_b_anchor_20_all30","query_id":r["query_id"],"case_id":r["case_id"],"parent_bug_id":r["parent_bug_id"],"bug_family":r["bug_family"],"memberships":r["memberships"],"prompt_sha256":r["prompt_sha256"],"adapter_sha256":e["adapter_sha256"],"raw_response_sha256":e["raw_response_sha256"],"ast_sha256":e["ast_sha256"],"candidate_sva_sha256":sha(rendered),**primitive_bools(result),**derived(result),"evaluation_error":result.get("evaluation_error"),"compile_duration_sec":result.get("compile_duration_sec",0),"verification_duration_sec":result.get("verification_duration_sec",0),"wall_clock_seconds":time.perf_counter()-started,"raw_evaluation":result}; dump(output,row); print(f"[{i}/48] {r['case_id']} compile={row['compile_ok']} strict={row['strict_success']}",flush=True)
    rows=[json.loads(p.read_text()) for p in sorted((OUT/"records").rglob("evaluation.json"))]
    if len(rows)!=48: raise RuntimeError(f"expected48, found{len(rows)}")
    summaries={s:method_summary(rows,s) for s in ("unseen_parent","unseen_bug_family","union_overview")}; old=json.loads(OLD.read_text())["summaries"]; comparisons={}
    nonbehavior=("ordinary_sft","pass_count_dpo","scalar_score_dpo")
    for split in ("unseen_parent","unseen_bug_family"):
        old_methods=old[split]["methods"]; strongest=max(nonbehavior,key=lambda m:(old_methods[m]["SCS@1"],old_methods[m]["Fixed-Safe"])); baseline=old_methods[strongest]; current=summaries[split]; comparisons[split]={"strongest_nonbehavior_baseline":strongest,"baseline":baseline,"phase_b":current,"scs_delta_pp":100*(current["SCS@1"]-baseline["SCS@1"]),"fixed_safe_not_decreased":current["Fixed-Safe"]>=baseline["Fixed-Safe"],"go_gate_pass":current["SCS@1"]-baseline["SCS@1"]>=.05 and current["Fixed-Safe"]>=baseline["Fixed-Safe"]}
    result={"status":"complete","record_count":48,"metric_definitions_sha256":sha(DEFINITIONS),"query_manifest_sha256":sha(MANIFEST),"summaries":summaries,"comparison_to_frozen_five_method_results":comparisons,"final_decision":"GO" if all(x["go_gate_pass"] for x in comparisons.values()) else "NO-GO","wall_clock_seconds":time.perf_counter()-began}; dump(OUT/"phase_b_ood_metrics_and_decision.json",result); print(json.dumps(result,sort_keys=True))
if __name__=="__main__": main()
