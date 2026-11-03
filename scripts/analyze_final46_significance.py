#!/usr/bin/env python3
from __future__ import annotations

import itertools
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd


REPO = Path(__file__).resolve().parents[1]
DETAIL = REPO / "deliverables/final46_main_experiment_20260806/candidate_details.csv"
OUT = REPO / "deliverables/final46_significance_stability_20260807"
MODELS = ["GPT", "Claude", "Qwen"]
METHODS = ["spec_only", "full_rtl", "signal_list", "rtl_slice", "raw_trace", "naive_summary", "event_abstraction", "temporal_abstraction"]


def as_bool(s: pd.Series) -> pd.Series:
    return s.astype(str).str.lower().isin({"true", "1", "yes"})


def exact_mcnemar(b: int, c: int) -> float:
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(0, min(b, c) + 1)) / (2**n)
    return min(1.0, 2.0 * tail)


def paired_stats(a: np.ndarray, b: np.ndarray, rng: np.random.Generator) -> dict:
    diff = a.astype(float) - b.astype(float)
    indices = rng.integers(0, len(diff), size=(20000, len(diff)))
    boot = diff[indices].mean(axis=1)
    b10 = int(np.sum(a & ~b))
    b01 = int(np.sum(~a & b))
    matched_or = (b10 + 0.5) / (b01 + 0.5)
    pa, pb = float(a.mean()), float(b.mean())
    cohen_h = 2 * math.asin(math.sqrt(pa)) - 2 * math.asin(math.sqrt(pb))
    return {
        "n_parent_bugs": len(a), "a_success_count": int(a.sum()), "b_success_count": int(b.sum()),
        "a_rate": pa, "b_rate": pb, "paired_risk_difference": float(diff.mean()),
        "bootstrap_ci95_low": float(np.quantile(boot, 0.025)),
        "bootstrap_ci95_high": float(np.quantile(boot, 0.975)),
        "discordant_a_only": b10, "discordant_b_only": b01,
        "mcnemar_exact_p": exact_mcnemar(b10, b01), "matched_odds_ratio_haldane": matched_or,
        "cohen_h": cohen_h,
    }


def holm(frame: pd.DataFrame) -> pd.DataFrame:
    order = frame["mcnemar_exact_p"].sort_values().index.tolist()
    adjusted = {}
    running = 0.0
    n = len(order)
    for rank, idx in enumerate(order):
        value = min(1.0, float(frame.loc[idx, "mcnemar_exact_p"]) * (n - rank))
        running = max(running, value)
        adjusted[idx] = running
    frame["holm_adjusted_p"] = pd.Series(adjusted)
    frame["significant_0_05_holm"] = frame["holm_adjusted_p"] < 0.05
    frame["interpretation"] = np.where(
        frame["significant_0_05_holm"],
        np.where(frame["paired_risk_difference"] > 0, "A significantly better", "B significantly better"),
        np.where(frame["paired_risk_difference"].abs() > 0, "trend only", "no observed difference"),
    )
    return frame


def outcomes(detail: pd.DataFrame, k: int = 4) -> pd.DataFrame:
    use = detail.loc[detail["candidate_index"] <= k].copy()
    return use.groupby(["model", "method", "parent_bug_id"], as_index=False)["success"].any()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    detail = pd.read_csv(DETAIL, encoding="utf-8-sig")
    detail["success"] = as_bool(detail["success"])
    detail["candidate_index"] = pd.to_numeric(detail["candidate_index"]).astype(int)
    parent = outcomes(detail, 4)
    pivot = parent.pivot(index="parent_bug_id", columns=["model", "method"], values="success")
    rng = np.random.default_rng(20260807)
    rows = []
    for model in MODELS:
        for a, b in itertools.combinations(METHODS, 2):
            row = {"comparison_family": "within_model_methods", "model": model, "method": "",
                   "a_label": a, "b_label": b}
            row.update(paired_stats(pivot[(model, a)].to_numpy(bool), pivot[(model, b)].to_numpy(bool), rng))
            rows.append(row)
    for method in METHODS:
        for a, b in itertools.combinations(MODELS, 2):
            row = {"comparison_family": "within_method_models", "model": "", "method": method,
                   "a_label": a, "b_label": b}
            row.update(paired_stats(pivot[(a, method)].to_numpy(bool), pivot[(b, method)].to_numpy(bool), rng))
            rows.append(row)
    sig = holm(pd.DataFrame(rows))
    sig.to_csv(OUT / "statistical_significance_parent_level.csv", index=False, encoding="utf-8-sig")

    k_rows = []
    for k in range(1, 5):
        parent_k = outcomes(detail, k)
        for (model, method), group in parent_k.groupby(["model", "method"], sort=True):
            candidates = detail.loc[(detail.model == model) & (detail.method == method) & (detail.candidate_index <= k)]
            k_rows.append({
                "ablation_axis": "k", "condition": f"k={k}", "seed": 20260806,
                "temperature": "main_run_fallback_schedule", "k": k, "model": model, "method": method,
                "n_parent_bugs": group.parent_bug_id.nunique(),
                "candidate_success_rate": float(candidates.success.mean()),
                "parent_any_of_k_success_count": int(group.success.sum()),
                "parent_any_of_k_success_rate": float(group.success.mean()),
                "trace_variants_count_as_independent": False,
            })
    pd.DataFrame(k_rows).to_csv(OUT / "k_ablation_from_main_candidates.csv", index=False, encoding="utf-8-sig")
    summary = {
        "schema_version": 1, "analysis_unit": "parent_bug_id", "n_parent_bugs": int(detail.parent_bug_id.nunique()),
        "trace_variants_count_as_independent": False, "bootstrap_replicates": 20000,
        "mcnemar": "exact two-sided", "multiple_testing": "Holm across all 108 primary comparisons",
        "effect_sizes": ["paired risk difference", "matched odds ratio with Haldane correction", "Cohen h"],
        "comparison_count": len(sig), "significant_count_holm_0_05": int(sig.significant_0_05_holm.sum()),
    }
    (OUT / "significance_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
