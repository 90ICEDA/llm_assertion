from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "outputs/formal_compliant_raw_temporal_dual/multi_model_results_raw.csv"
EXT = ROOT / "outputs/candidate_portfolio_k4_extension/multi_model_results_raw.csv"
OUT = ROOT / "outputs/candidate_portfolio_formal"
RAW = "spec_rtl_raw_trace"; TEMP = "spec_rtl_temporal_relation_abstraction"


def sha(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()
def norm(text: object) -> str: return re.sub(r"\s+", " ", str(text or "").strip()).lower()
def truth(series: pd.Series) -> pd.Series: return series.astype(str).str.strip().str.lower().isin(["true", "1", "yes"])
def strict(df: pd.DataFrame) -> pd.Series:
    return truth(df["heldout_correct_pass"]) & truth(df["heldout_buggy_fail"]) & truth(df["heldout_antecedent_hit"]) & truth(df["heldout_non_vacuous"])


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    base = pd.read_csv(BASE, encoding="utf-8-sig"); ext = pd.read_csv(EXT, encoding="utf-8-sig")
    base = base[base.method.isin([RAW, TEMP])].copy(); ext = ext[ext.method.isin([RAW, TEMP])].copy()
    all_rows = pd.concat([base, ext], ignore_index=True, sort=False)
    key = ["model_label", "provider", "model_name", "case_id", "method", "candidate_index"]
    if all_rows.duplicated(key).any(): raise RuntimeError("Duplicate source candidate keys")
    if len(all_rows) != 1920 or set(pd.to_numeric(all_rows.candidate_index).astype(int)) != {1,2,3,4}:
        raise RuntimeError(f"Expected 1920 raw/temporal k4 rows, got {len(all_rows)}")
    counts = all_rows.groupby(["model_label","case_id","method"]).candidate_index.nunique()
    if len(counts) != 480 or not (counts == 4).all(): raise RuntimeError("Every raw/temporal model-case arm must have k=4")
    all_rows["candidate_index"] = pd.to_numeric(all_rows.candidate_index).astype(int)
    strategies=[]
    for method, strategy in ((RAW,"raw_k4"),(TEMP,"temporal_k4")):
        part=all_rows[all_rows.method==method].copy(); part["method"]=strategy; strategies.append(part)
    raw2=all_rows[(all_rows.method==RAW)&(all_rows.candidate_index<=2)].copy(); raw2["method"]="portfolio_raw2_temporal2"
    temp2=all_rows[(all_rows.method==TEMP)&(all_rows.candidate_index<=2)].copy(); temp2["method"]="portfolio_raw2_temporal2"; temp2["candidate_index"] += 2
    strategies.extend([raw2,temp2]); portfolio=pd.concat(strategies,ignore_index=True,sort=False)
    portfolio_path=OUT/"portfolio_strategy_candidates.csv"; portfolio.to_csv(portfolio_path,index=False,encoding="utf-8-sig")
    common=["--k","4","--metric","strict_success","--overlap-status","overlap","--sample-definition","scale120 compliant raw/temporal; equal budget 4; portfolio raw2+temporal2 versus raw4 and temporal4"]
    report=OUT/"unified_three_scope_report.csv"; stats=OUT/"parent_statistics"
    subprocess.run([sys.executable,str(ROOT/"src/unified_result_reporting.py"),str(portfolio_path),str(report),*common],check=True)
    subprocess.run([sys.executable,str(ROOT/"src/parent_cluster_statistics.py"),str(portfolio_path),str(stats),*common,"--repetitions","10000","--seed","20260721","--parent-outcome","all_observations"],check=True)

    all_rows["strict_success"] = strict(all_rows); all_rows["normalized_assertion"] = all_rows.assertion_text.map(norm)
    details=[]
    for (model,case), group in all_rows.groupby(["model_label","case_id"],sort=True):
        r=group[group.method==RAW]; t=group[group.method==TEMP]; r2=r[r.candidate_index<=2]; t2=t[t.candidate_index<=2]
        texts=list(r2.normalized_assertion)+list(t2.normalized_assertion); duplicates=len(texts)-len(set(texts))
        raw2_ok=bool(r2.strict_success.any()); temp2_ok=bool(t2.strict_success.any()); portfolio_ok=raw2_ok or temp2_ok
        details.append({"model":model,"case_id":case,"raw_k4_success":bool(r.strict_success.any()),"temporal_k4_success":bool(t.strict_success.any()),"portfolio_success":portfolio_ok,"raw2_success":raw2_ok,"temporal2_success":temp2_ok,"portfolio_duplicate_candidate_count":duplicates,"raw2_unique_success":raw2_ok and not temp2_ok,"temporal2_unique_success":temp2_ok and not raw2_ok})
    detail=pd.DataFrame(details); detail.to_csv(OUT/"portfolio_case_detail.csv",index=False,encoding="utf-8-sig")
    summaries=[]
    for model,g in detail.groupby("model"):
        summaries.append({"model":model,"k_total":4,"case_count":len(g),"parent_count":40,"portfolio_successes":int(g.portfolio_success.sum()),"raw_k4_successes":int(g.raw_k4_success.sum()),"temporal_k4_successes":int(g.temporal_k4_success.sum()),"portfolio_rescued_vs_raw_k4":int((g.portfolio_success&~g.raw_k4_success).sum()),"portfolio_rescued_vs_temporal_k4":int((g.portfolio_success&~g.temporal_k4_success).sum()),"portfolio_lost_vs_raw_k4":int((~g.portfolio_success&g.raw_k4_success).sum()),"portfolio_lost_vs_temporal_k4":int((~g.portfolio_success&g.temporal_k4_success).sum()),"raw2_only_success_cases":int(g.raw2_unique_success.sum()),"temporal2_only_success_cases":int(g.temporal2_unique_success.sum()),"duplicate_candidate_slots":int(g.portfolio_duplicate_candidate_count.sum()),"cases_with_duplicate_portfolio_candidate":int((g.portfolio_duplicate_candidate_count>0).sum()),"deduplicated":False,"overlap":"same cases and parents across all strategies"})
    summary=pd.DataFrame(summaries); summary.to_csv(OUT/"portfolio_summary.csv",index=False,encoding="utf-8-sig")
    ci=stats/"method_results_with_parent_bootstrap_ci.csv"; paired=stats/"paired_mcnemar_effect_sizes.csv"
    freeze={"schema_version":1,"status":"frozen_candidate_portfolio","models":{"GPT":"gpt-5.4","Claude":"claude-opus-4-8"},"budget_per_model_case":4,"strategies":{"portfolio":"raw2+temporal2","raw":"raw4","temporal":"temporal4"},"case_count":120,"parent_count":40,"source_candidate_count":len(all_rows),"strategy_candidate_rows":len(portfolio),"bootstrap_unit":"parent_bug_id","bootstrap_repetitions":10000,"paired_test":"exact McNemar","effect_sizes":["paired risk difference","matched odds ratio"],"sha256":{str(p):sha(p) for p in [BASE,EXT,portfolio_path,report,ci,paired,OUT/"portfolio_case_detail.csv",OUT/"portfolio_summary.csv"]}}
    (OUT/"candidate_portfolio_freeze.json").write_text(json.dumps(freeze,indent=2,ensure_ascii=False),encoding="utf-8")
    print(summary.to_string(index=False)); print(json.dumps(freeze,indent=2,ensure_ascii=False))


if __name__ == "__main__": main()
