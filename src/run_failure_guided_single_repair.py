from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
from pathlib import Path

import pandas as pd

from build_seen_only_candidate_reranker import (
    DEFAULT_CASES, DEFAULT_PARENT_MAP, parser_support, referenced_signals, signal_inventory,
)
from run_multi_model_small_eval import MODEL_SPECS, extract_sva_candidates, literal_hardcoding_flag, post_model_chat
from run_trace_abstraction_prototype import run_case_eval


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SELECTED = ROOT / "outputs/dev_locked_score_reranker/selected_candidates.csv"
DEFAULT_TEMPORAL = ROOT / "outputs/formal_temporal_abstractions/temporal_abstractions.json"
DEFAULT_OUT = ROOT / "outputs/failure_guided_single_repair"
CATEGORIES = [
    "compile_fail", "unsupported", "vacuity", "antecedent_not_triggered", "too_strong",
    "too_weak", "signal_missing", "reset_misuse", "hardcoding",
]
FEEDBACK = {
    "compile_fail": "The assertion did not compile.",
    "unsupported": "The assertion uses syntax unsupported by the evaluation parser.",
    "vacuity": "The assertion was vacuous on the seen executions.",
    "antecedent_not_triggered": "The antecedent did not trigger on the seen buggy execution.",
    "too_strong": "The assertion failed on the seen correct execution.",
    "too_weak": "The assertion did not fail on the seen buggy execution.",
    "signal_missing": "The assertion references a signal absent from the allowed interface.",
    "reset_misuse": "Reset handling is inconsistent with the allowed reset convention.",
    "hardcoding": "The assertion relies on trace-specific literal hardcoding.",
}


def truth(value) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def diagnoses(row: pd.Series) -> list[str]:
    result = []
    if not truth(row["compile_ok"]): result.append("compile_fail")
    if not truth(row["parser_support"]): result.append("unsupported")
    if not truth(row["non_vacuous"]): result.append("vacuity")
    if not truth(row["seen_antecedent_hit"]): result.append("antecedent_not_triggered")
    if not truth(row["seen_good_pass"]): result.append("too_strong")
    if truth(row["seen_good_pass"]) and not truth(row["seen_bad_fail"]): result.append("too_weak")
    if not truth(row["signal_exists"]): result.append("signal_missing")
    if not truth(row["reset_usage"]): result.append("reset_misuse")
    if truth(row["literal_hardcoding"]): result.append("hardcoding")
    return result


def waveform_text(path: Path, max_rows: int = 80) -> str:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))[: max_rows + 1]
    return "\n".join(",".join(row) for row in rows)


def allowed_signals(case_dir: Path) -> list[str]:
    with (case_dir / "waveform_good.csv").open(encoding="utf-8-sig", newline="") as handle:
        header = next(csv.reader(handle))
    return [re.sub(r"\[.*$", "", x.strip()) for x in header if x.strip() != "time_ps"]


def reset_usage(assertion: str, case_dir: Path) -> bool:
    _, resets = signal_inventory(case_dir)
    lower = assertion.lower()
    combinational = "@(*)" in lower or "@*" in lower
    return combinational if not resets else "disable iff" in lower and any(re.search(rf"\b{re.escape(x.lower())}\b", lower) for x in resets)


def signal_exists(assertion: str, case_dir: Path) -> bool:
    inventory, _ = signal_inventory(case_dir)
    refs = referenced_signals(assertion)
    return bool(refs) and refs.issubset(inventory)


def prompt(row: pd.Series, case_dir: Path, temporal_lookup: dict[str, str], errors: list[str]) -> str:
    representation = str(row["representation"])
    if representation == "raw":
        trace_context = "Seen good trace:\n" + waveform_text(case_dir / "waveform_good.csv") + "\n\nSeen bad trace:\n" + waveform_text(case_dir / "waveform_bad.csv")
    else:
        trace_context = "Seen temporal-relation abstraction:\n" + temporal_lookup[str(row["case_id"])]
    feedback = "\n".join(f"- {FEEDBACK[item]}" for item in errors)
    return f"""Repair the following SystemVerilog assertion exactly once.

Return exactly one complete `assert property` statement and no explanation.
Use only the allowed signals. Preserve the intended behavioral relation as much as possible.
Do not invent signals. Do not copy fixed trace cycles or trace-specific constants into a general rule.

Allowed signals:
{', '.join(allowed_signals(case_dir))}

Correct RTL context:
```systemverilog
{(case_dir / 'correct.v').read_text(encoding='utf-8', errors='replace')}
```

{trace_context}

Original assertion:
{row['assertion_text']}

Diagnostic feedback (only what is wrong; no golden property is provided):
{feedback}
"""


def model_spec(label: str) -> dict:
    matches = [x for x in MODEL_SPECS if x["model_label"] == label]
    if not matches: raise RuntimeError(f"Unknown model label: {label}")
    return matches[0]


def category_corrected(category: str, result: dict, static: dict[str, bool]) -> bool:
    return {
        "compile_fail": bool(result["compile_ok"]), "unsupported": static["parser_support"],
        "vacuity": bool(result["non_vacuous"]), "antecedent_not_triggered": bool(result["antecedent_hit"]),
        "too_strong": bool(result["correct_pass"]), "too_weak": bool(result["buggy_fail"]),
        "signal_missing": static["signal_exists"], "reset_misuse": static["reset_usage"],
        "hardcoding": not static["hardcoding"],
    }[category]


def main() -> None:
    ap=argparse.ArgumentParser(); ap.add_argument("--selected",default=str(DEFAULT_SELECTED)); ap.add_argument("--cases-root",default=str(DEFAULT_CASES)); ap.add_argument("--temporal",default=str(DEFAULT_TEMPORAL)); ap.add_argument("--parent-map",default=str(DEFAULT_PARENT_MAP)); ap.add_argument("--out-dir",default=str(DEFAULT_OUT)); ap.add_argument("--generate-only",action="store_true"); args=ap.parse_args()
    selected_path,cases_root,temporal_path,parent_path,out_dir=Path(args.selected).resolve(),Path(args.cases_root).resolve(),Path(args.temporal).resolve(),Path(args.parent_map).resolve(),Path(args.out_dir).resolve();out_dir.mkdir(parents=True,exist_ok=True)
    selected=pd.read_csv(selected_path,encoding="utf-8-sig"); temporal_data=json.loads(temporal_path.read_text(encoding="utf-8")); temporal_lookup={x["case_id"]:x["abstracted_summary"] for x in temporal_data}
    targets=[]
    for _,row in selected.iterrows():
        errs=diagnoses(row)
        if errs: targets.append((row,errs))
    cache_path=out_dir/"repair_cache.json"; cache=json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    for index,(row,errs) in enumerate(targets,start=1):
        key=f"{row['model_label']}|{row['case_id']}"
        if key in cache:
            print(f"[SKIP {index:03d}/{len(targets):03d}] {key}",file=sys.stderr);continue
        print(f"[REPAIR {index:03d}/{len(targets):03d}] {key}: {','.join(errs)}",file=sys.stderr)
        case_dir=cases_root/str(row["case_id"]); repair_prompt=prompt(row,case_dir,temporal_lookup,errs)
        response=post_model_chat(model_spec(str(row["model_label"])),repair_prompt,temperature=0.2)
        candidates=extract_sva_candidates(response); repaired=candidates[0] if candidates else ""
        entry={"model_label":row["model_label"],"model_name":row["model_name"],"case_id":row["case_id"],"parent_bug_id":row["parent_bug_id"],"split":row["split"],"original_assertion":row["assertion_text"],"diagnoses":errs,"diagnostic_feedback":[FEEDBACK[x] for x in errs],"prompt":repair_prompt,"raw_response":response,"repaired_assertion":repaired,"model_call_count":1,"candidate_count":1 if repaired else 0}
        cache[key]=entry;cache_path.write_text(json.dumps(cache,indent=2,ensure_ascii=False),encoding="utf-8")
        if args.generate_only: continue
    if args.generate_only:
        print(cache_path);return
    for index,(key,entry) in enumerate(cache.items(),start=1):
        if "evaluation" in entry: continue
        assertion=entry["repaired_assertion"]; case_dir=cases_root/entry["case_id"]
        if not assertion:
            entry["evaluation_error"]="no assertion extracted"
        else:
            static={"parser_support":parser_support(assertion),"signal_exists":signal_exists(assertion,case_dir),"reset_usage":reset_usage(assertion,case_dir),"hardcoding":literal_hardcoding_flag(assertion)}
            result=run_case_eval(case_id=entry["case_id"],assertion_text=assertion,signal_names=allowed_signals(case_dir),use_property=False,runtime_dir=out_dir/"runtime"/entry["model_label"]/entry["case_id"],cases_root=cases_root)
            entry["static_evaluation"]=static;entry["evaluation"]=result
        cache_path.write_text(json.dumps(cache,indent=2,ensure_ascii=False),encoding="utf-8")
    original={(r.model_label,r.case_id):r for r in selected.itertuples()}; rows=[]; candidate_rows=[]
    for key,entry in cache.items():
        orig=original[(entry["model_label"],entry["case_id"])]; ev=entry.get("evaluation",{}); static=entry.get("static_evaluation",{})
        seen_success=bool(ev) and ev["compile_ok"] and ev["correct_pass"] and ev["buggy_fail"] and ev["antecedent_hit"] and ev["non_vacuous"] and static["parser_support"] and static["signal_exists"] and static["reset_usage"]
        heldout_success=bool(ev) and ev["heldout_correct_pass"] and ev["heldout_buggy_fail"] and ev["heldout_antecedent_hit"] and ev["heldout_non_vacuous"]
        new_fp=bool(ev) and truth(orig.heldout_correct_pass) and not ev["heldout_correct_pass"]
        new_vac=bool(ev) and truth(orig.non_vacuous) and not ev["non_vacuous"]
        new_ov=bool(ev) and not truth(orig.trace_overfit) and ev["trace_overfit"]
        corrected_map={category:(bool(ev) and category_corrected(category,ev,static)) for category in entry["diagnoses"]}
        candidate_rows.append({"model":entry["model_label"],"model_name":entry["model_name"],"case_id":entry["case_id"],"parent_bug_id":entry["parent_bug_id"],"split":entry["split"],"error_categories":";".join(entry["diagnoses"]),"all_diagnostics_corrected":all(corrected_map.values()),"any_diagnostic_corrected":any(corrected_map.values()),"seen_repair_success":seen_success,"heldout_repair_success":heldout_success,"new_false_positive":new_fp,"new_vacuity":new_vac,"new_overfit":new_ov,"single_model_call":entry["model_call_count"]==1})
        for category in entry["diagnoses"]:
            rows.append({"model":entry["model_label"],"model_name":entry["model_name"],"case_id":entry["case_id"],"parent_bug_id":entry["parent_bug_id"],"split":entry["split"],"error_category":category,"diagnostic_corrected":corrected_map[category],"seen_repair_success":seen_success,"heldout_repair_success":heldout_success,"new_false_positive":new_fp,"new_vacuity":new_vac,"new_overfit":new_ov,"single_model_call":entry["model_call_count"]==1})
    detail=pd.DataFrame(rows); detail_path=out_dir/"repair_outcomes_by_error.csv";detail.to_csv(detail_path,index=False,encoding="utf-8-sig")
    candidates=pd.DataFrame(candidate_rows);candidate_path=out_dir/"repair_outcomes_by_candidate.csv";candidates.to_csv(candidate_path,index=False,encoding="utf-8-sig")
    summary=[]
    for scope,scope_df in [("case",detail),("parent_primary",detail[detail.case_id==detail.parent_bug_id])]:
      for model in sorted(selected.model_label.unique()):
        for category in CATEGORIES:
            sub=scope_df[(scope_df.model==model)&(scope_df.error_category==category)] if not scope_df.empty else scope_df
            n=len(sub);summary.append({"scope":scope,"model":model,"k":1,"error_category":category,"target_count":n,"parent_count":int(sub.parent_bug_id.nunique()) if n else 0,"deduplicated":scope=="parent_primary","overlap":"multi-label error categories; same repair may appear in multiple category rows","diagnostic_corrected_count":int(sub.diagnostic_corrected.sum()) if n else 0,"diagnostic_repair_rate":float(sub.diagnostic_corrected.mean()) if n else None,"seen_repair_success_count":int(sub.seen_repair_success.sum()) if n else 0,"seen_repair_rate":float(sub.seen_repair_success.mean()) if n else None,"heldout_repair_success_count":int(sub.heldout_repair_success.sum()) if n else 0,"heldout_repair_rate":float(sub.heldout_repair_success.mean()) if n else None,"new_false_positive_count":int(sub.new_false_positive.sum()) if n else 0,"new_vacuity_count":int(sub.new_vacuity.sum()) if n else 0,"new_overfit_count":int(sub.new_overfit.sum()) if n else 0})
    summary_path=out_dir/"repair_rate_by_error.csv";pd.DataFrame(summary).to_csv(summary_path,index=False,encoding="utf-8-sig")
    overall=[]
    for scope,scope_df in [("case",candidates),("parent_primary",candidates[candidates.case_id==candidates.parent_bug_id])]:
      for model,sub in scope_df.groupby("model"):
        overall.append({"scope":scope,"model":model,"k":1,"target_count":len(sub),"parent_count":int(sub.parent_bug_id.nunique()),"deduplicated":scope=="parent_primary","overlap":"one unique row per repaired candidate","seen_repair_success_count":int(sub.seen_repair_success.sum()),"seen_repair_rate":float(sub.seen_repair_success.mean()),"heldout_repair_success_count":int(sub.heldout_repair_success.sum()),"heldout_repair_rate":float(sub.heldout_repair_success.mean()),"new_false_positive_count":int(sub.new_false_positive.sum()),"new_vacuity_count":int(sub.new_vacuity.sum()),"new_overfit_count":int(sub.new_overfit.sum())})
    overall_path=out_dir/"repair_overall_unique_candidate_summary.csv";pd.DataFrame(overall).to_csv(overall_path,index=False,encoding="utf-8-sig")
    protocol={"repair_limit_per_candidate":1,"retry_policy":"no semantic repair retry; transport retries may occur inside HTTP client without producing another candidate","target_selection":"seen/static diagnoses only","feedback_allowlist":FEEDBACK,"forbidden_feedback":["golden assertion","expected property","mutation line","buggy RTL line","heldout outcome"],"error_categories":CATEGORIES}
    protocol_path=out_dir/"repair_protocol.json";protocol_path.write_text(json.dumps(protocol,indent=2,ensure_ascii=False),encoding="utf-8")
    freeze_path=out_dir/"failure_guided_repair_freeze.json";frozen=[selected_path,temporal_path,parent_path,cache_path,detail_path,candidate_path,summary_path,overall_path,protocol_path]
    construction_manifest=out_dir/"construction_manifest.json"
    if construction_manifest.exists(): frozen.append(construction_manifest)
    freeze_path.write_text(json.dumps({"status":"frozen_failure_guided_single_repair","target_count":len(targets),"model_call_count":sum(x["model_call_count"] for x in cache.values()),"all_single_call":all(x["model_call_count"]==1 for x in cache.values()),"sha256":{str(p):sha(p) for p in frozen}},indent=2),encoding="utf-8");print(summary_path);print(freeze_path)


if __name__=="__main__":main()
