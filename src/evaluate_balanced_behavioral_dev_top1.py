from __future__ import annotations
import argparse,hashlib,json,sys,time
from pathlib import Path
from evaluate_frozen_top1_v1 import derived,false_result,primitive_bools,run_case_eval,tool_version,visible_signals
from evaluate_pilot_v2_frozen_ast_top1 import render

ROOT=Path(__file__).resolve().parents[1]; BASE=ROOT/"outputs/behavioral_preference_pilot_v2/balanced_behavioral_objective_v1"
DEV=BASE/"dev_top1_v1"; MANIFEST=DEV/"query_manifest.json"; OUT=DEV/"execution_evaluation_v1"
DEFINITIONS=ROOT/"outputs/behavioral_preference_pilot_v1/frozen_top1_v1/frozen_metric_definitions_v1.json"
EXPECTED="74a90578c44d1b8055c19e27e481447a51e358882526e4f01103da0224234d38"
VARIANTS=("anchor_10","anchor_20","anchor_25"); BASELINES=("scalar_score_dpo","full_disagreement_dominance_dpo"); METHODS=VARIANTS+BASELINES
KEYS=("antecedent_signal","antecedent_polarity","consequent_signal","implication","relation")
CASE_ROOTS={"case135_prim_intr_enable_mask_ignored":"rtl_cases_real_scale210_independent","case438_cc_fifo_protocol_suppress_2":"rtl_cases_real_scale210_independent","case465_axis_srl_fifo_simultaneous_occupancy":"rtl_cases_real_scale210_independent_next","case492_axis_async_fifo_gray_visibility":"rtl_cases_real_scale210_independent_next","case494_axis_ram_switch_response_pipeline":"rtl_cases_real_scale210_independent_next","case504_cc_cdc_fifo_gray_pointer_visible_early":"rtl_cases_real_scale210_independent_next"}
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(p,x): Path(p).parent.mkdir(parents=True,exist_ok=True); Path(p).write_text(json.dumps(x,indent=2)+"\n")
def generation_dir(method,case): return DEV/("generations" if method in VARIANTS else "baseline_generations")/method/case
def clock_reset(signals):
    clock=next((x for x in ("clk_i","clk","clock","i_clk","wr_clk","rd_clk") if x in signals),None)
    reset=next((x for x in ("rst_ni","rst_n","reset_n","aresetn","rst","reset") if x in signals),None)
    return clock,reset
def preflight():
    if sha(MANIFEST)!=EXPECTED: raise RuntimeError("dev query manifest hash mismatch")
    manifest=json.loads(MANIFEST.read_text()); records=manifest["records"]; problems=[]; adapters={}
    if len(records)!=6 or manifest.get("selection_scope")!="six parents frozen before balanced training; no OOD queries or outcomes": raise RuntimeError("unexpected dev universe")
    for method in METHODS:
        hashes=set()
        for row in records:
            directory=generation_dir(method,row["case_id"]); evidence=directory/"evidence.json"; raw=directory/"raw_response.txt"; ast_path=directory/"ast.json"
            if not all(x.is_file() for x in (evidence,raw,ast_path)): problems.append(f"missing {method}/{row['case_id']}"); continue
            e=json.loads(evidence.read_text()); ast=json.loads(ast_path.read_text())
            valid=e.get("status")=="complete" and e.get("prompt_sha256")==row["prompt_sha256"] and e.get("schema_keys_valid") is True and e.get("ended_on_eos") is True and e.get("hit_max_new_tokens") is False and tuple(ast)==KEYS and sha(raw)==e.get("raw_response_sha256") and sha(ast_path)==e.get("ast_sha256")
            if not valid: problems.append(f"mismatch {method}/{row['case_id']}")
            hashes.add(e.get("adapter_sha256"))
        if len(hashes)!=1: problems.append(f"adapter hash count {method}={len(hashes)}")
        else: adapters[method]=next(iter(hashes))
    for row in records:
        case=ROOT/CASE_ROOTS[row["case_id"]]/row["case_id"]
        if not all((case/x).is_file() for x in ("correct.v","buggy.v","tb.v")): problems.append(f"case assets missing {row['case_id']}")
    if problems: raise RuntimeError("; ".join(problems[:10]))
    return {"status":"pass","query_manifest_sha256":sha(MANIFEST),"metric_definitions_sha256":sha(DEFINITIONS),"query_count":6,"variant_count":3,"baseline_count":2,"generation_count":30,"adapter_hashes":adapters,"selection_input_scope":"frozen six-parent train dev only; OOD outcomes not read","deletion_policy":"all 30 one-shot records retained; failures score false","repair":False,"reranker":False,"selector":False,"tool_versions":{"python":sys.version.split()[0],"wsl_iverilog":tool_version(["wsl","bash","-lc","iverilog -V 2>&1 | grep -m1 'Icarus Verilog version'"]),"wsl_vvp":tool_version(["wsl","bash","-lc","vvp -V 2>&1 | grep -m1 'Icarus Verilog runtime version'"])}},records
def summary(rows,method):
    group=[x for x in rows if x["method"]==method]; n=len(group); families={x["bug_family"] for x in group}; recalled={x["bug_family"] for x in group if x["strict_success"]}; primary=sum(x["primary_success"] for x in group); overfit=sum(x["trace_overfit"] for x in group)
    return {"query_count":n,"compile_rate":sum(x["compile_ok"] for x in group)/n,"SCS@1":sum(x["strict_success"] for x in group)/n,"Fixed-Safe":sum(x["fixed_safe"] for x in group)/n,"Target Detect":sum(x["target_detect"] for x in group)/n,"Family Recall":len(recalled)/len(families),"Non-vacuity":sum(x["non_vacuity_metric"] for x in group)/n,"TOR":overfit/primary if primary else None,"counts":{"strict_success":sum(x["strict_success"] for x in group),"fixed_safe":sum(x["fixed_safe"] for x in group),"target_detect":sum(x["target_detect"] for x in group),"non_vacuous":sum(x["non_vacuity_metric"] for x in group)}}
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--preflight-only",action="store_true"); ap.add_argument("--resume",action="store_true"); args=ap.parse_args(); audit,records=preflight(); OUT.mkdir(parents=True,exist_ok=True); dump(OUT/"pre_execution_audit.json",audit)
    if args.preflight_only: print(json.dumps(audit,sort_keys=True)); return
    began=time.perf_counter()
    for method in METHODS:
        for i,row in enumerate(records,1):
            output=OUT/"records"/method/row["case_id"]/"evaluation.json"
            if args.resume and output.is_file(): continue
            directory=generation_dir(method,row["case_id"]); e=json.loads((directory/"evidence.json").read_text()); ast=json.loads((directory/"ast.json").read_text()); case=ROOT/CASE_ROOTS[row["case_id"]]/row["case_id"]; signals=visible_signals(case); clock,reset=clock_reset(signals); candidate=render(ast,clock,reset)
            rendered=OUT/"rendered"/method/row["case_id"]/"candidate.sva"; rendered.parent.mkdir(parents=True,exist_ok=True); rendered.write_text(candidate+"\n"); started=time.perf_counter()
            try: result=run_case_eval(case_id=row["case_id"],assertion_text=candidate,signal_names=signals,use_property=False,runtime_dir=OUT/"runtime"/method/row["case_id"],cases_root=case.parent)
            except Exception as exc: result=false_result(f"evaluation_exception: {type(exc).__name__}: {exc}")
            record={"status":"complete","method":method,"query_id":row["query_id"],"case_id":row["case_id"],"parent_bug_id":row["parent_bug_id"],"bug_family":row["bug_family"],"source_project":row["source_project"],"prompt_sha256":row["prompt_sha256"],"adapter_sha256":e["adapter_sha256"],"raw_response_sha256":e["raw_response_sha256"],"ast_sha256":e["ast_sha256"],"candidate_sva_sha256":sha(rendered),"rendered_candidate_path":str(rendered.relative_to(ROOT)).replace("\\","/"),**primitive_bools(result),**derived(result),"evaluation_error":result.get("evaluation_error"),"compile_duration_sec":result.get("compile_duration_sec",0),"verification_duration_sec":result.get("verification_duration_sec",0),"wall_clock_seconds":time.perf_counter()-started,"raw_evaluation":result}; dump(output,record); print(f"[{method} {i}/6] {row['case_id']} compile={record['compile_ok']} strict={record['strict_success']}",flush=True)
    rows=[json.loads(p.read_text()) for p in sorted((OUT/"records").rglob("evaluation.json"))]
    if len(rows)!=30: raise RuntimeError(f"expected 30 rows, found {len(rows)}")
    summaries={m:summary(rows,m) for m in METHODS}; scalar=summaries["scalar_score_dpo"]; full=summaries["full_disagreement_dominance_dpo"]
    eligible=[v for v in VARIANTS if summaries[v]["Fixed-Safe"]>=scalar["Fixed-Safe"] and summaries[v]["Target Detect"]>=full["Target Detect"]]
    eligible.sort(key=lambda v:(-summaries[v]["SCS@1"],-summaries[v]["Fixed-Safe"],-summaries[v]["Target Detect"],int(v.split("_")[1])))
    selection={"status":"selected" if eligible else "no_eligible_variant","constraints":{"fixed_safe_floor_method":"scalar_score_dpo","fixed_safe_floor":scalar["Fixed-Safe"],"target_detect_floor_method":"full_disagreement_dominance_dpo","target_detect_floor":full["Target Detect"]},"eligible_variants":eligible,"selected_variant":eligible[0] if eligible else None,"ranking":"SCS@1 desc, Fixed-Safe desc, Target Detect desc, anchor fraction asc","next_action":"phase_b_refit_all30" if eligible else "NO-GO; do not refit all30; do not access OOD"}
    result={"status":"complete","query_manifest_sha256":sha(MANIFEST),"metric_definitions_sha256":sha(DEFINITIONS),"record_count":30,"summaries":summaries,"selection":selection,"wall_clock_seconds":time.perf_counter()-began}; dump(OUT/"dev_metrics_and_selection.json",result); dump(OUT/"evaluation_artifact_hashes.json",{str(p.relative_to(ROOT)).replace("\\","/"):sha(p) for p in sorted(OUT.rglob("*")) if p.is_file() and p.name!="evaluation_artifact_hashes.json"}); print(json.dumps(result,sort_keys=True))
if __name__=="__main__": main()
