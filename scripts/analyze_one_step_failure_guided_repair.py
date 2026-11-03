from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"deliverables/one_step_failure_guided_repair_20260810"
CASES=ROOT/"rtl_cases_real_scale120"


def main():
    d=pd.read_csv(OUT/"one_step_repair_main.csv",encoding="utf-8-sig")
    assert len(d)==54 and not d.duplicated(["model","case_id","candidate_uid"]).any()
    assert d.model_call_count.eq(1).all()
    assert d.groupby("primary_failure").size().eq(6).all()
    assert d.groupby(["primary_failure","prompt_arm"]).size().eq(2).all()
    heldout_names=["heldout_correct_pass","heldout_buggy_fail","heldout_antecedent_hit","heldout_non_vacuous","trace_overfit"]
    leakage=[]
    for r in d.itertuples():
        prompt=str(r.repair_prompt)
        case_dir=CASES/r.case_id
        bad_rtl=(case_dir/"buggy.v").read_text(encoding="utf-8",errors="replace").strip()
        heldout_files=[case_dir/"waveform_good_holdout.csv",case_dir/"waveform_bad_holdout.csv"]
        leakage.append({
            "repair_id":r.repair_id,
            "prompt_sha256":hashlib.sha256(prompt.encode()).hexdigest(),
            "contains_heldout_column_name":any(x in prompt for x in heldout_names),
            "contains_full_buggy_rtl":bool(bad_rtl and bad_rtl in prompt),
            "contains_full_heldout_trace":any(p.is_file() and p.read_text(encoding="utf-8-sig",errors="replace").strip() in prompt for p in heldout_files),
            "golden_artifact_available_in_case":(case_dir/"golden.sva").exists(),
        })
    leak=pd.DataFrame(leakage);leak.to_csv(OUT/"prompt_leakage_audit.csv",index=False,encoding="utf-8-sig")
    assert not leak[["contains_heldout_column_name","contains_full_buggy_rtl","contains_full_heldout_trace","golden_artifact_available_in_case"]].any().any()
    arm=d.groupby("prompt_arm",as_index=False).agg(n=("repair_id","size"),primary_fixed=("primary_failure_fixed","sum"),primary_repair_rate=("primary_failure_fixed","mean"),seen_success=("after_seen_strict_success","sum"),seen_success_rate=("after_seen_strict_success","mean"),heldout_success=("after_heldout_strict_success","sum"),heldout_success_rate=("after_heldout_strict_success","mean"))
    arm.to_csv(OUT/"repair_prompt_arm_summary.csv",index=False,encoding="utf-8-sig")
    rates=pd.read_csv(OUT/"repair_rate_by_failure.csv",encoding="utf-8-sig")
    all_rates=rates[rates.prompt_arm.eq("ALL")]
    risk=pd.read_csv(OUT/"pre_post_false_positive_vacuity_overfit.csv",encoding="utf-8-sig")
    overall_risk=risk[risk.prompt_arm.eq("ALL")]
    report=["# One-step failure-guided repair","","## Protocol","","54 unique candidate identities were stratified as 9 failure types × 3 prompt arms × 2 models. Each candidate received exactly one repair call. Unified feedback gives a visible-check checklist; failure-specific feedback names the diagnosed visible failure; wrong-diagnosis supplies a deterministic incorrect category. No golden artifact, buggy RTL, held-out trace, or held-out result field is included in any prompt.","","## Prompt-arm results","","| Arm | n | Primary fixed | Seen strict success | Held-out strict success |","|---|---:|---:|---:|---:|"]
    for r in arm.itertuples(): report.append(f"| {r.prompt_arm} | {r.n} | {r.primary_repair_rate:.1%} | {r.seen_success_rate:.1%} | {r.heldout_success_rate:.1%} |")
    report += ["","The sample is deliberately small (2 candidates per failure×arm). Wrong diagnosis performing well on some cells is therefore a control result, not evidence that incorrect feedback is beneficial.","","## Repair rate by primary failure","","| Failure | n | Fixed | Rate |","|---|---:|---:|---:|"]
    for r in all_rates.itertuples(): report.append(f"| {r.primary_failure} | {r.target_count} | {r.fixed_count} | {r.repair_rate:.1%} |")
    report += ["","## Pre/post risk","","| Metric | Before | After | Change | Introduced | Resolved |","|---|---:|---:|---:|---:|---:|"]
    for r in overall_risk.itertuples(): report.append(f"| {r.metric} | {r.before_rate:.1%} | {r.after_rate:.1%} | {r.rate_change:+.1%} | {r.introduced_count} | {r.resolved_count} |")
    report += ["","False positive means a compiled assertion rejects held-out correct behavior. Vacuity means a compiled assertion has no held-out non-vacuous trigger. Overfit is the evaluator trace-overfit flag.","","## Complete cases","","`complete_cases_by_failure.csv` contains six full cases per failure type, including the complete prompt, original assertion, raw response, repaired assertion, visible/held-out outcomes, and pre/post risk flags. Four sparse static categories use explicitly marked constructed invalid candidates; semantic categories use naturally occurring candidates.",""]
    (OUT/"ONE_STEP_FAILURE_GUIDED_REPAIR.md").write_text("\n".join(report),encoding="utf-8")
    audit=json.loads((OUT/"repair_audit.json").read_text(encoding="utf-8"));audit.update({"unique_candidate_identity_count":int(d[["model","case_id","candidate_uid"]].drop_duplicates().shape[0]),"prompt_leakage_rows":int(leak[["contains_heldout_column_name","contains_full_buggy_rtl","contains_full_heldout_trace","golden_artifact_available_in_case"]].any(axis=1).sum()),"prompt_leakage_audit_sha256":hashlib.sha256((OUT/"prompt_leakage_audit.csv").read_bytes()).hexdigest()});(OUT/"repair_audit.json").write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding="utf-8")
    print(arm.to_string(index=False));print(overall_risk.to_string(index=False));print(json.dumps(audit,ensure_ascii=False,indent=2))

if __name__=="__main__":main()
