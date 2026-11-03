#!/usr/bin/env python3
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "deliverables/equal_budget_visible_selection_20260809"


def mcnemar_exact(a_only: int, b_only: int) -> float:
    n = a_only + b_only
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(0, min(a_only, b_only) + 1)) / (2 ** n)
    return min(1.0, 2 * tail)


def bootstrap_diff(a: np.ndarray, b: np.ndarray, seed: int) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    n = len(a)
    indices = rng.integers(0, n, size=(20000, n))
    diffs = b[indices].mean(axis=1) - a[indices].mean(axis=1)
    return float(np.quantile(diffs, 0.025)), float(np.quantile(diffs, 0.975))


def main() -> None:
    detail = pd.read_csv(OUT / "parent_deduplicated_results.csv", encoding="utf-8-sig")
    detail["heldout_strict_success"] = detail.heldout_strict_success.astype(str).str.lower().isin(["true", "1"])
    rows = []
    for (model, policy), group in detail.groupby(["model_label", "policy"], sort=True):
        pivot = group.pivot(index="parent_bug_id", columns="pool", values="heldout_strict_success")
        baseline = pivot["raw_k4"].to_numpy(dtype=bool)
        for pool in ["temporal_k4", "raw2_temporal2", "four_rep_one_each"]:
            arm = pivot[pool].to_numpy(dtype=bool)
            arm_only = int((arm & ~baseline).sum())
            base_only = int((baseline & ~arm).sum())
            lo, hi = bootstrap_diff(baseline.astype(float), arm.astype(float), seed=20260809 + len(rows))
            rows.append({
                "model": model, "policy": policy, "baseline_pool": "raw_k4", "comparison_pool": pool,
                "n_parents": len(pivot), "baseline_success_count": int(baseline.sum()),
                "comparison_success_count": int(arm.sum()),
                "paired_risk_difference": float(arm.mean() - baseline.mean()),
                "bootstrap_95ci_low": lo, "bootstrap_95ci_high": hi,
                "discordant_comparison_only": arm_only, "discordant_baseline_only": base_only,
                "mcnemar_exact_p": mcnemar_exact(arm_only, base_only),
                "comparison_only_parent_ids": ";".join(pivot.index[arm & ~baseline]),
                "baseline_only_parent_ids": ";".join(pivot.index[baseline & ~arm]),
            })
    comparisons = pd.DataFrame(rows)
    comparisons.to_csv(OUT / "equal_budget_paired_comparisons.csv", index=False, encoding="utf-8-sig")

    summary = pd.read_csv(OUT / "equal_budget_comparison.csv", encoding="utf-8-sig")
    primary = summary.loc[summary.scope.eq("parent_primary")].copy()
    macro = primary.groupby(["pool", "policy"], as_index=False).agg(
        model_count=("model", "nunique"), mean_coverage=("coverage", "mean"),
        mean_overall_success_rate=("overall_success_rate", "mean"),
        mean_conditional_success_rate=("conditional_success_rate", "mean"),
        min_overall_success_rate=("overall_success_rate", "min"),
        max_overall_success_rate=("overall_success_rate", "max"),
    )
    macro.to_csv(OUT / "equal_budget_macro_summary.csv", index=False, encoding="utf-8-sig")

    audit = json.loads((OUT / "heldout_invariance_audit.json").read_text(encoding="utf-8"))
    best = primary.loc[~primary.policy.eq("oracle_upper_bound")].sort_values(
        ["model", "overall_success_rate"], ascending=[True, False]
    ).groupby("model", as_index=False).first()
    report = [
        "# Equal-budget candidate pools and visible-only selection",
        "",
        "## Protocol",
        "",
        "All four pools contain exactly four distinct candidates for every model×case. The primary analysis uses 40 canonical parents; the 120-case table is retained only as a variant-level sensitivity view. Selection may read only compile, seen-good/bad behavior, antecedent hit, non-vacuity, signal legality, reset usage, hardcoding, and representation agreement. Held-out fields are joined after selection.",
        "",
        "## Main parent-deduplicated results",
        "",
        "| Model | Best visible-only pool/policy | Coverage | Overall strict success | Oracle ceiling |",
        "|---|---|---:|---:|---:|",
    ]
    for row in best.itertuples():
        oracle = primary.loc[(primary.model == row.model) & (primary.pool == row.pool) & (primary.policy == "oracle_upper_bound"), "overall_success_rate"].iloc[0]
        report.append(f"| {row.model} | {row.pool} / {row.policy} | {row.coverage:.1%} | {row.overall_success_rate:.1%} | {oracle:.1%} |")
    report += [
        "",
        "For Claude, raw_k4 + score_ranking reaches 77.5% (31/40), versus an 80.0% raw-k4 oracle ceiling. For GPT, raw_k4 + score_ranking reaches 62.5% (25/40), versus a 77.5% ceiling. Mixed raw2+temporal2 and four-representation pools do not beat raw_k4 under the same budget in this run.",
        "",
        "All visible policies except the explicitly named fallback arm abstain when a pool has zero hard-pass candidates. Fallback is labeled explicit_fallback_first; no repair was run. First/random remain baseline choice rules only when at least one hard-pass candidate exists in the pool.",
        "",
        "## Held-out isolation audit",
        "",
        f"Original visible selection hash: `{audit['original_visible_selection_sha256']}`",
        f"Held-out deleted hash: `{audit['heldout_deleted_selection_sha256']}`",
        f"Held-out shuffled hash: `{audit['heldout_shuffled_selection_sha256']}`",
        "",
        "All three hashes are identical. Oracle is deliberately excluded because it is an evaluation-only upper bound. Hard-filter and abstain return `abstain_no_hard_pass`; fallback uses the explicit label `explicit_fallback_first`; no repair was run.",
        "",
        "## Interpretation limits",
        "",
        "The random policy is deterministic for reproducibility, not an average over random seeds. Representation agreement is exact canonical-assertion agreement across representations, not semantic equivalence. McNemar and bootstrap intervals are model-specific and parent-paired; the comparison table is exploratory and uncorrected for multiple comparisons.",
    ]
    (OUT / "EQUAL_BUDGET_VISIBLE_SELECTION.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(best[["model", "pool", "policy", "coverage", "overall_success_rate"]].to_string(index=False))


if __name__ == "__main__":
    main()
