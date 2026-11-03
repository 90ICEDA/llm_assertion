#!/usr/bin/env python3
from __future__ import annotations

import argparse
import itertools
import math
from pathlib import Path

import numpy as np
import pandas as pd

from unified_result_reporting import (
    SCOPES, UNITS, aggregate, bool_series, normalize_raw_results, select_scope,
)


def cluster_bootstrap_ci(
    group: pd.DataFrame,
    *, scope: str,
    unit: str,
    k: int,
    repetitions: int,
    seed: int,
) -> tuple[float, float, float]:
    selected = select_scope(group, scope, 1 if scope == "first_candidate" else k)
    estimate = aggregate(selected, unit)[0]
    # Once scope selection is fixed, every requested estimator is a ratio of
    # parent-cluster sums. Vectorizing those sums makes 10k parent bootstraps
    # exact for this estimator and avoids rebuilding DataFrames per draw.
    if unit == "candidate":
        contributions = selected.groupby("parent_bug_id")["success"].agg(["sum", "count"])
    else:
        case_scores = selected.groupby(["parent_bug_id", "case_id"], as_index=False)["success"].mean()
        if unit == "case":
            contributions = case_scores.groupby("parent_bug_id")["success"].agg(["sum", "count"])
        else:
            parent_scores = case_scores.groupby("parent_bug_id")["success"].mean()
            contributions = pd.DataFrame({"sum": parent_scores, "count": 1.0})
    numerators = contributions["sum"].to_numpy(dtype=float)
    denominators = contributions["count"].to_numpy(dtype=float)
    parent_count = len(contributions)
    if parent_count == 0:
        return estimate, float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    sampled = rng.integers(0, parent_count, size=(repetitions, parent_count))
    sampled_denominators = denominators[sampled].sum(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        boot = np.divide(
            numerators[sampled].sum(axis=1),
            sampled_denominators,
            out=np.full(repetitions, np.nan, dtype=float),
            where=sampled_denominators != 0,
        )
    boot = boot[np.isfinite(boot)]
    if len(boot) == 0:
        return estimate, float("nan"), float("nan")
    lower, upper = np.quantile(boot, [0.025, 0.975])
    return estimate, float(lower), float(upper)


def parent_binary(selected: pd.DataFrame, rule: str) -> pd.Series:
    by_parent = selected.groupby("parent_bug_id")["success"]
    if rule == "all_observations":
        return by_parent.all()
    if rule == "any_observation":
        return by_parent.any()
    if rule == "majority":
        return by_parent.mean() >= 0.5
    raise ValueError(rule)


def exact_mcnemar_p(n01: int, n10: int) -> float:
    discordant = n01 + n10
    if discordant == 0:
        return 1.0
    tail = min(n01, n10)
    probability = sum(math.comb(discordant, i) for i in range(tail + 1)) / (2 ** discordant)
    return min(1.0, 2.0 * probability)


def build_confidence(
    raw: pd.DataFrame, *, k: int, repetitions: int, seed: int, metric: str,
    overlap_status: str, sample_definition: str,
) -> pd.DataFrame:
    rows = []
    for group_index, ((model, method), group) in enumerate(raw.groupby(["model", "method"], sort=True)):
        for scope_index, scope in enumerate(SCOPES):
            scope_k = 1 if scope == "first_candidate" else k
            selected = select_scope(group, scope, scope_k)
            for unit_index, unit in enumerate(UNITS):
                estimate, lower, upper = cluster_bootstrap_ci(
                    group,
                    scope=scope,
                    unit=unit,
                    k=scope_k,
                    repetitions=repetitions,
                    seed=seed + group_index * 100 + scope_index * 10 + unit_index,
                )
                rows.append({
                    "model": model,
                    "method": method,
                    "selection_scope": scope,
                    "aggregation_unit": unit,
                    "k": scope_k,
                    "metric": metric,
                    "value": estimate,
                    "ci_level": 0.95,
                    "ci_lower": lower,
                    "ci_upper": upper,
                    "ci_method": "percentile_cluster_bootstrap",
                    "bootstrap_unit": "parent_bug_id",
                    "bootstrap_repetitions": repetitions,
                    "random_seed": seed,
                    "candidate_observation_count": int(selected["source_candidate_count"].sum()),
                    "case_count": selected["case_id"].nunique(),
                    "parent_bug_count": selected["parent_bug_id"].nunique(),
                    "deduplicated": unit != "candidate",
                    "dedup_key": "none" if unit == "candidate" else "case_id" if unit == "case" else "parent_bug_id",
                    "parent_aggregation": "macro_mean_cases",
                    "overlap_status": overlap_status,
                    "sample_definition": sample_definition,
                })
    return pd.DataFrame(rows)


def build_pairwise(raw: pd.DataFrame, *, k: int, parent_rule: str, metric: str) -> pd.DataFrame:
    rows = []
    for model, model_df in raw.groupby("model", sort=True):
        methods = sorted(model_df["method"].unique())
        for scope in SCOPES:
            scope_k = 1 if scope == "first_candidate" else k
            outcomes = {}
            for method in methods:
                selected = select_scope(model_df.loc[model_df["method"] == method], scope, scope_k)
                outcomes[method] = parent_binary(selected, parent_rule)
            for method_a, method_b in itertools.combinations(methods, 2):
                paired = pd.concat([outcomes[method_a], outcomes[method_b]], axis=1, join="inner")
                paired.columns = ["a", "b"]
                n00 = int((~paired.a & ~paired.b).sum())
                n01 = int((~paired.a & paired.b).sum())
                n10 = int((paired.a & ~paired.b).sum())
                n11 = int((paired.a & paired.b).sum())
                n = len(paired)
                rows.append({
                    "model": model,
                    "method_a": method_a,
                    "method_b": method_b,
                    "selection_scope": scope,
                    "aggregation_unit": "parent_bug",
                    "k": scope_k,
                    "metric": metric,
                    "parent_outcome_rule": parent_rule,
                    "paired_parent_count": n,
                    "n00": n00, "n01": n01, "n10": n10, "n11": n11,
                    "mcnemar_test": "exact_two_sided",
                    "mcnemar_p_value": exact_mcnemar_p(n01, n10),
                    "effect_size_paired_risk_difference": float(paired.b.mean() - paired.a.mean()) if n else np.nan,
                    "effect_size_matched_odds_ratio": (n01 + 0.5) / (n10 + 0.5),
                    "effect_direction": f"{method_b}_minus_{method_a}",
                    "pairing_unit": "parent_bug_id",
                    "variant_as_independent_sample": False,
                })
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_csv", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--k", type=int, required=True)
    parser.add_argument("--metric", default="strict_success")
    parser.add_argument("--repetitions", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=20260719)
    parser.add_argument("--parent-outcome", choices=["all_observations", "any_observation", "majority"], default="all_observations")
    parser.add_argument("--overlap-status", choices=["overlap", "non_overlap", "mixed", "unknown"], required=True)
    parser.add_argument("--sample-definition", required=True)
    parser.add_argument("--model-column", default="model_label")
    args = parser.parse_args()
    raw = normalize_raw_results(
        pd.read_csv(args.input_csv, encoding="utf-8-sig"), args.model_column
    )
    required = {"model", "method", "case_id", "parent_bug_id", "candidate_index", "success"}
    missing = sorted(required - set(raw.columns))
    if missing:
        raise ValueError(f"Missing columns: {missing}")
    raw["success"] = bool_series(raw["success"])
    raw["candidate_index"] = pd.to_numeric(raw["candidate_index"], errors="raise").astype(int)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    build_confidence(
        raw, k=args.k, repetitions=args.repetitions, seed=args.seed, metric=args.metric,
        overlap_status=args.overlap_status, sample_definition=args.sample_definition,
    ).to_csv(args.output_dir / "method_results_with_parent_bootstrap_ci.csv", index=False, encoding="utf-8-sig")
    build_pairwise(raw, k=args.k, parent_rule=args.parent_outcome, metric=args.metric).to_csv(
        args.output_dir / "paired_mcnemar_effect_sizes.csv", index=False, encoding="utf-8-sig"
    )
    print(args.output_dir)


if __name__ == "__main__":
    main()
