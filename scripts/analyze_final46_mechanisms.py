#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import re
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
BASE = REPO / "deliverables/final46_main_experiment_20260806/candidate_details.csv"
CONTROL = REPO / "outputs/final46_mechanism_controls"
CASES = REPO / "rtl_cases_real_scale210_independent_next"
TEMPORAL_SUMMARIES = REPO / "outputs/final46_main_experiment/temporal_abstractions.json"
OUT = REPO / "deliverables/final46_mechanism_analysis_20260808"
MODELS = ["GPT", "Claude", "Qwen"]

TRACE_MAP = {
    "raw_trace": "raw_good_bad",
    "temporal_abstraction": "temporal_full",
    "spec_rtl_trace_good_only": "good_only",
    "spec_rtl_trace_bad_only": "bad_only",
    "spec_rtl_trace_local_window": "local_window",
    "spec_rtl_trace_signal_subset": "signal_subset",
    "spec_rtl_trace_noise_signals": "noise_signals",
    "spec_rtl_trace_format_perturbed": "format_perturbed",
    "spec_rtl_trace_wrong_pairing": "wrong_pairing",
    "spec_rtl_temporal_no_trigger": "temporal_no_trigger",
    "spec_rtl_temporal_no_delay": "temporal_no_delay",
    "spec_rtl_temporal_no_polarity": "temporal_no_polarity",
    "spec_rtl_temporal_no_duration": "temporal_no_duration",
    "spec_rtl_temporal_strict_no_trigger": "temporal_strict_no_trigger",
    "spec_rtl_temporal_strict_no_delay": "temporal_strict_no_delay",
    "spec_rtl_temporal_strict_no_polarity": "temporal_strict_no_polarity",
    "spec_rtl_temporal_strict_no_duration": "temporal_strict_no_duration",
}
RTL_MAP = {
    "full_rtl": "full_rtl",
    "signal_list": "signal_list",
    "rtl_slice": "legacy_line_slice",
    "spec_rtl_interface": "interface",
    "spec_rtl_one_hop_slice": "one_hop_slice",
    "spec_rtl_two_hop_slice": "two_hop_slice",
    "spec_rtl_signal_list_two_hop_slice": "signal_list_plus_two_hop",
    "spec_rtl_random_slice": "random_slice_control",
    "spec_rtl_wrong_signal_list": "wrong_signal_list_control",
}


def bools(series: pd.Series) -> pd.Series:
    return series.astype(str).str.lower().isin({"true", "1", "yes"})


def load_controls(family: str) -> pd.DataFrame:
    frames = []
    for model in MODELS:
        path = CONTROL / family / model / "multi_model_results_raw.csv"
        if not path.is_file():
            raise SystemExit(f"missing control shard: {path}")
        frame = pd.read_csv(path, encoding="utf-8-sig")
        valid_methods = {k for k in (TRACE_MAP if family == "trace" else RTL_MAP) if k.startswith("spec_rtl_")}
        frame = frame.loc[
            frame["model_label"].astype(str).eq(model)
            & frame["method"].astype(str).isin(valid_methods)
        ].copy()
        frame["candidate_index"] = pd.to_numeric(frame["candidate_index"], errors="coerce")
        frame = frame.loc[frame["candidate_index"].isin([1, 2, 3, 4])].copy()
        frame["candidate_index"] = frame["candidate_index"].astype(int)
        frame = frame.drop_duplicates(
            ["model_label", "case_id", "method", "candidate_index"], keep="last"
        )
        frame["model"] = frame["model_label"]
        frame["success"] = frame["failure_mode"].astype(str).eq("success")
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def load_family(family: str) -> pd.DataFrame:
    base = pd.read_csv(BASE, encoding="utf-8-sig")
    base["success"] = bools(base["success"])
    mapping = TRACE_MAP if family == "trace" else RTL_MAP
    baseline_native = {k for k in mapping if not k.startswith("spec_rtl_")}
    base = base.loc[base["method"].isin(baseline_native)].copy()
    controls = load_controls(family)
    keep = sorted(set(base.columns).union(controls.columns))
    base = base.reindex(columns=keep)
    controls = controls.reindex(columns=keep)
    detail = pd.concat([base, controls], ignore_index=True)
    detail["method_native"] = detail["method"]
    detail["mechanism"] = detail["method"].map(mapping)
    if detail["mechanism"].isna().any():
        raise SystemExit(f"unmapped {family} methods: {sorted(detail.loc[detail.mechanism.isna(), 'method'].unique())}")
    detail["candidate_index"] = pd.to_numeric(detail["candidate_index"], errors="raise").astype(int)
    return detail


def exact_mcnemar(b: int, c: int) -> float:
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(min(b, c) + 1)) / (2**n)
    return min(1.0, 2 * tail)


def summarize(detail: pd.DataFrame, family: str, baseline: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    keys = ["model", "case_id", "mechanism"]
    case = detail.groupby(keys, as_index=False).agg(
        candidate_count=("candidate_index", "count"),
        candidate_success_count=("success", "sum"),
        any_of_4_success=("success", "any"),
    )
    pivot = case.pivot(index=["model", "case_id"], columns="mechanism", values="any_of_4_success").reset_index()
    method_rows = []
    for (model, mechanism), group in case.groupby(["model", "mechanism"], sort=True):
        candidates = detail.loc[(detail.model == model) & (detail.mechanism == mechanism)]
        method_rows.append({
            "family": family, "model": model, "mechanism": mechanism,
            "n_cases": group.case_id.nunique(), "candidate_count": len(candidates),
            "candidate_success_count": int(candidates.success.sum()),
            "candidate_success_rate": float(candidates.success.mean()),
            "parent_any_of_4_success_count": int(group.any_of_4_success.sum()),
            "parent_any_of_4_success_rate": float(group.any_of_4_success.mean()),
        })
    comparisons = []
    for model in MODELS:
        sub = pivot.loc[pivot.model == model].set_index("case_id")
        a = sub[baseline].astype(bool)
        for mechanism in sorted(c for c in sub.columns if c not in {baseline, "model"}):
            b = sub[mechanism].astype(bool)
            gained = sorted(sub.index[(~a) & b].tolist())
            lost = sorted(sub.index[a & (~b)].tolist())
            comparisons.append({
                "family": family, "model": model, "baseline": baseline, "mechanism": mechanism,
                "n_parent_bugs": len(sub), "baseline_success_count": int(a.sum()),
                "mechanism_success_count": int(b.sum()),
                "paired_risk_difference": float(b.mean() - a.mean()),
                "discordant_mechanism_only": len(gained), "discordant_baseline_only": len(lost),
                "mcnemar_exact_p": exact_mcnemar(len(gained), len(lost)),
                "gained_case_ids": ";".join(gained), "lost_case_ids": ";".join(lost),
            })
    return pd.DataFrame(method_rows), pivot, pd.DataFrame(comparisons)


def case_text(case_id: str, name: str) -> str:
    path = CASES / case_id / name
    return path.read_text(encoding="utf-8").strip() if path.is_file() else ""


def load_temporal_summaries() -> dict[str, str]:
    payload = json.loads(TEMPORAL_SUMMARIES.read_text(encoding="utf-8"))
    return {
        str(item.get("case_id", "")).strip(): str(item.get("abstracted_summary", "")).strip()
        for item in payload
        if isinstance(item, dict) and str(item.get("case_id", "")).strip()
    }


def candidate_digest(group: pd.DataFrame) -> str:
    return " || ".join(
        f"c{int(row.candidate_index)}[{row.failure_mode}] {str(row.assertion_text).strip()}"
        for row in group.sort_values("candidate_index").itertuples()
    )


def primary_failure_category(group: pd.DataFrame, *, quadrant: str, control_row: pd.Series) -> tuple[str, str, str]:
    modes = group.failure_mode.astype(str).value_counts().to_dict()
    assertions = " ".join(group.assertion_text.astype(str))
    if quadrant == "temporal_success_raw_fail" and (
        bool(control_row.get("signal_subset", False)) or bool(control_row.get("local_window", False))
    ):
        return "context_noise", "trigger", "raw fails while a reduced raw arm succeeds"
    if modes.get("vacuity", 0) >= 2:
        return "vacuity", "trigger", "at least two candidates have unhit antecedents"
    if modes.get("too_strong", 0) >= 2:
        return "too_strong", "polarity", "at least two candidates reject correct/heldout-correct behavior"
    if re.search(r"\$past|\$stable|\|=>|##|\[\*", assertions):
        return "delay", "duration", "failed candidates encode explicit cross-cycle timing"
    if re.search(r"\b\d+'[bdh][0-9a-fx_z]+|==\s*\d+", assertions, re.I):
        return "hardcoding", "polarity", "failed candidates contain witnessed literal values"
    if modes.get("too_weak", 0) + modes.get("ineffective", 0) >= 2:
        return "trigger", "polarity", "candidates pass buggy behavior or fail to distinguish it"
    return "polarity", "duration", "remaining semantic mismatch after compile/vacuity checks"


def build_quadrants(base: pd.DataFrame, trace_pivot: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    temporal_summaries = load_temporal_summaries()
    raw = base.loc[base.method == "raw_trace"].copy()
    temporal = base.loc[base.method == "temporal_abstraction"].copy()
    rows, review = [], []
    for model in MODELS:
        for case_id in sorted(base.loc[base.model == model, "case_id"].unique()):
            rg = raw.loc[(raw.model == model) & (raw.case_id == case_id)]
            tg = temporal.loc[(temporal.model == model) & (temporal.case_id == case_id)]
            rs, ts = bool(rg.success.any()), bool(tg.success.any())
            quadrant = (
                "both_success" if rs and ts else "raw_success_temporal_fail" if rs else
                "temporal_success_raw_fail" if ts else "both_fail"
            )
            row = {
                "model": model, "case_id": case_id, "parent_bug_id": str(rg.parent_bug_id.iloc[0]),
                "bug_class": str(rg.bug_class.iloc[0]), "bug_family": str(rg.bug_family.iloc[0]),
                "quadrant": quadrant, "raw_success": rs, "temporal_success": ts,
                "raw_successful_candidate_indices": ";".join(map(str, rg.loc[rg.success, "candidate_index"].astype(int))),
                "temporal_successful_candidate_indices": ";".join(map(str, tg.loc[tg.success, "candidate_index"].astype(int))),
                "raw_candidate_digest": candidate_digest(rg), "temporal_candidate_digest": candidate_digest(tg),
            }
            rows.append(row)
            if quadrant != "both_success":
                control = trace_pivot.loc[(trace_pivot.model == model) & (trace_pivot.case_id == case_id)].iloc[0]
                failed = tg if quadrant == "raw_success_temporal_fail" else rg if quadrant == "temporal_success_raw_fail" else pd.concat([rg, tg])
                primary, secondary, basis = primary_failure_category(failed, quadrant=quadrant, control_row=control)
                review.append({
                    **row, "primary_failure_category": primary, "secondary_failure_category": secondary,
                    "coding_basis": basis, "spec_text": case_text(case_id, "spec.md"),
                    "golden_sva": case_text(case_id, "golden.sva"),
                    "temporal_abstraction": temporal_summaries.get(case_id, ""),
                    "control_successes": ";".join(
                        name for name in TRACE_MAP.values() if name in control.index and bool(control[name])
                    ),
                    "review_status": "structured_expert_review_queue",
                })
    return pd.DataFrame(rows), pd.DataFrame(review)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    trace = load_family("trace")
    rtl = load_family("rtl")
    expected_trace = 3 * 46 * len(TRACE_MAP) * 4
    expected_rtl = 3 * 46 * len(RTL_MAP) * 4
    if len(trace) != expected_trace or len(rtl) != expected_rtl:
        raise SystemExit(f"incomplete mechanism matrix: trace {len(trace)}/{expected_trace}, rtl {len(rtl)}/{expected_rtl}")
    key = ["model", "case_id", "mechanism", "candidate_index"]
    if trace.duplicated(key).any() or rtl.duplicated(key).any():
        raise SystemExit("duplicate mechanism candidate keys")

    trace_summary, trace_cases, trace_cmp = summarize(trace, "trace", "raw_good_bad")
    rtl_summary, rtl_cases, rtl_cmp = summarize(rtl, "rtl", "full_rtl")
    base = pd.read_csv(BASE, encoding="utf-8-sig")
    base["success"] = bools(base["success"])
    quadrants, review = build_quadrants(base, trace_cases)
    manual_path = REPO / "analysis/final46_manual_failure_annotations.json"
    manual = pd.DataFrame(json.loads(manual_path.read_text(encoding="utf-8")))
    if not manual.empty:
        manual = manual.rename(columns={"primary": "manual_primary", "secondary": "manual_secondary", "evidence": "manual_evidence"})
        review = review.merge(manual, on=["model", "case_id", "quadrant"], how="left")
        reviewed = review["manual_evidence"].notna()
        review.loc[reviewed, "primary_failure_category"] = review.loc[reviewed, "manual_primary"]
        review.loc[reviewed, "secondary_failure_category"] = review.loc[reviewed, "manual_secondary"]
        review.loc[reviewed, "coding_basis"] = review.loc[reviewed, "manual_evidence"]
        review.loc[reviewed, "review_status"] = "manually_reviewed"
        review = review.drop(columns=["manual_primary", "manual_secondary", "manual_evidence"])

    trace_summary.to_csv(OUT / "trace_control_summary.csv", index=False, encoding="utf-8-sig")
    trace_cases.to_csv(OUT / "trace_case_outcomes.csv", index=False, encoding="utf-8-sig")
    trace_cmp.to_csv(OUT / "trace_control_paired_comparisons.csv", index=False, encoding="utf-8-sig")
    rtl_summary.to_csv(OUT / "rtl_context_summary.csv", index=False, encoding="utf-8-sig")
    rtl_cases.to_csv(OUT / "rtl_case_outcomes.csv", index=False, encoding="utf-8-sig")
    rtl_cmp.to_csv(OUT / "rtl_context_paired_comparisons.csv", index=False, encoding="utf-8-sig")
    quadrants.to_csv(OUT / "raw_temporal_quadrants.csv", index=False, encoding="utf-8-sig")
    review.to_csv(OUT / "failure_analysis_review_packet.csv", index=False, encoding="utf-8-sig")
    review.loc[review.review_status == "manually_reviewed"].to_csv(
        OUT / "manual_failure_analysis.csv", index=False, encoding="utf-8-sig"
    )

    audit = {
        "status": "complete", "analysis_unit": "parent_bug_id", "parent_bug_count": 46,
        "models": MODELS, "candidates_per_cell": 4,
        "trace_expected_rows": expected_trace, "trace_actual_rows": len(trace),
        "rtl_expected_rows": expected_rtl, "rtl_actual_rows": len(rtl),
        "duplicate_keys": 0,
        "quadrant_counts": quadrants.quadrant.value_counts().to_dict(),
        "failure_review_rows": len(review),
        "manually_reviewed_rows": int((review.review_status == "manually_reviewed").sum()),
    }
    (OUT / "mechanism_audit.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
