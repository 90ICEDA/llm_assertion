#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from parent_cluster_statistics import build_confidence, build_pairwise


METHODS = [
    "spec_only",
    "spec_rtl_full",
    "spec_rtl_interface",
    "spec_rtl_signal_list",
    "spec_rtl_sliced",
    "spec_rtl_signal_list_small_slice",
]


def as_bool(series: pd.Series) -> pd.Series:
    return series.astype(str).str.lower().isin(["true", "1", "yes"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("raw_csv", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--k", type=int, required=True)
    parser.add_argument("--repetitions", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=20260719)
    parser.add_argument("--parent-outcome", choices=["all_observations", "any_observation", "majority"], default="all_observations")
    args = parser.parse_args()
    raw = pd.read_csv(args.raw_csv, encoding="utf-8-sig")
    missing_methods = sorted(set(METHODS) - set(raw["method"]))
    if missing_methods:
        raise ValueError(f"Missing fixed RTL-context methods: {missing_methods}")
    if "parent_bug_id" not in raw.columns:
        raise ValueError("Raw RTL-context results must include parent_bug_id")
    for col in ["heldout_correct_pass", "heldout_buggy_fail", "heldout_antecedent_hit", "heldout_non_vacuous"]:
        if col not in raw.columns:
            raise ValueError(f"Missing held-out generalization column: {col}")
    raw = raw.loc[raw["method"].isin(METHODS)].copy()
    raw["success"] = (
        as_bool(raw["heldout_correct_pass"])
        & as_bool(raw["heldout_buggy_fail"])
        & as_bool(raw["heldout_antecedent_hit"])
        & as_bool(raw["heldout_non_vacuous"])
    )
    raw = raw.rename(columns={"model_label": "model"})
    parent_sets = raw.groupby(["model", "method"])["parent_bug_id"].apply(lambda s: frozenset(s)).tolist()
    overlap_status = "overlap" if parent_sets and all(value == parent_sets[0] for value in parent_sets) else "mixed"
    sample_definition = "fixed_six_rtl_context_methods; heldout_strict_success; primary_context_to_heldout_trace"
    args.output_dir.mkdir(parents=True, exist_ok=True)
    build_confidence(
        raw,
        k=args.k,
        repetitions=args.repetitions,
        seed=args.seed,
        metric="heldout_strict_success",
        overlap_status=overlap_status,
        sample_definition=sample_definition,
    ).to_csv(args.output_dir / "rtl_context_generalization_with_parent_bootstrap_ci.csv", index=False, encoding="utf-8-sig")
    build_pairwise(
        raw, k=args.k, parent_rule=args.parent_outcome, metric="heldout_strict_success"
    ).to_csv(args.output_dir / "rtl_context_paired_mcnemar_effect_sizes.csv", index=False, encoding="utf-8-sig")
    print(args.output_dir)


if __name__ == "__main__":
    main()
