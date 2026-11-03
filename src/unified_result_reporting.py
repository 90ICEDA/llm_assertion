#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd


SCOPES = ("candidate_level", "first_candidate", "case_any_of_k")
UNITS = ("candidate", "case", "parent_bug")
OVERLAP_VALUES = ("overlap", "non_overlap", "mixed", "unknown")
REQUIRED_OUTPUT_COLUMNS = [
    "model", "method", "selection_scope", "aggregation_unit", "k", "metric", "value",
    "candidate_observation_count", "case_count", "parent_bug_count", "deduplicated",
    "dedup_key", "parent_aggregation", "overlap_status", "sample_definition",
]
CONFIDENCE_COLUMNS = [
    "ci_level", "ci_lower", "ci_upper", "ci_method", "bootstrap_unit",
    "bootstrap_repetitions", "random_seed",
]


def bool_series(values: pd.Series) -> pd.Series:
    return values.astype(str).str.strip().str.lower().isin(["1", "true", "yes", "pass", "passed"])


def normalize_raw_results(raw: pd.DataFrame, model_column: str = "model_label") -> pd.DataFrame:
    """Normalize evaluator-native rows without treating trace variants as parents."""
    raw = raw.rename(columns={model_column: "model"}).copy()
    def parent_of(case_id: object) -> str:
        text = str(case_id)
        match = re.search(r"_from_(case\d+_.+)$", text)
        return match.group(1) if match else text
    derived_parent = raw["case_id"].map(parent_of)
    if "parent_bug_id" not in raw.columns:
        raw["parent_bug_id"] = derived_parent
    else:
        missing_parent = raw["parent_bug_id"].isna() | raw["parent_bug_id"].astype(str).str.strip().isin({"", "nan", "None"})
        raw.loc[missing_parent, "parent_bug_id"] = derived_parent.loc[missing_parent]
    if "success" not in raw.columns:
        if "failure_mode" in raw.columns:
            raw["success"] = raw["failure_mode"].astype(str).str.strip().str.lower().eq("success")
        else:
            needed = ["compile_ok", "correct_pass", "buggy_fail", "heldout_correct_pass", "heldout_buggy_fail"]
            missing = [column for column in needed if column not in raw.columns]
            if missing:
                raise ValueError(f"Cannot derive strict success; missing columns: {missing}")
            success = pd.Series(True, index=raw.index)
            for column in needed:
                success &= bool_series(raw[column])
            for column in ("non_vacuous_buggy", "heldout_non_vacuous", "semantic_reasonable"):
                if column in raw.columns:
                    success &= bool_series(raw[column])
            raw["success"] = success
    return raw


def select_scope(group: pd.DataFrame, scope: str, k: int) -> pd.DataFrame:
    ordered = group.sort_values(["case_id", "candidate_index"]).copy()
    first_k = ordered.groupby("case_id", group_keys=False).head(k)
    if scope == "candidate_level":
        return first_k[["case_id", "parent_bug_id", "success"]].assign(
            observation_kind="candidate", source_candidate_count=1
        )
    if scope == "first_candidate":
        return (
            ordered.groupby("case_id", as_index=False).first()
            [["case_id", "parent_bug_id", "success"]]
            .assign(observation_kind="first_candidate", source_candidate_count=1)
        )
    if scope == "case_any_of_k":
        return (
            first_k.groupby(["case_id", "parent_bug_id"], as_index=False)
            .agg(success=("success", "any"), source_candidate_count=("candidate_index", "size"))
            .assign(observation_kind="case_any_of_k")
        )
    raise ValueError(scope)


def aggregate(selected: pd.DataFrame, unit: str) -> tuple[float, bool, str]:
    if unit == "candidate":
        return float(selected["success"].mean()), False, "none"
    case_scores = selected.groupby(["case_id", "parent_bug_id"], as_index=False)["success"].mean()
    if unit == "case":
        return float(case_scores["success"].mean()), True, "case_id"
    if unit == "parent_bug":
        parent_scores = case_scores.groupby("parent_bug_id", as_index=False)["success"].mean()
        return float(parent_scores["success"].mean()), True, "parent_bug_id"
    raise ValueError(unit)


def summarize(
    raw: pd.DataFrame,
    *,
    k: int,
    metric: str,
    overlap_status: str,
    sample_definition: str,
) -> pd.DataFrame:
    required = {"model", "method", "case_id", "parent_bug_id", "candidate_index", "success"}
    missing = sorted(required - set(raw.columns))
    if missing:
        raise ValueError(f"Missing input columns: {missing}")
    if overlap_status not in OVERLAP_VALUES:
        raise ValueError(f"Invalid overlap_status={overlap_status}")
    raw = raw.copy()
    raw["candidate_index"] = pd.to_numeric(raw["candidate_index"], errors="raise").astype(int)
    raw["success"] = bool_series(raw["success"])
    rows = []
    for (model, method), group in raw.groupby(["model", "method"], sort=True):
        for scope in SCOPES:
            scope_k = 1 if scope == "first_candidate" else k
            selected = select_scope(group, scope, scope_k)
            candidate_count = int(selected["source_candidate_count"].sum())
            for unit in UNITS:
                value, deduplicated, dedup_key = aggregate(selected, unit)
                rows.append(
                    {
                        "model": model,
                        "method": method,
                        "selection_scope": scope,
                        "aggregation_unit": unit,
                        "k": scope_k,
                        "metric": metric,
                        "value": value,
                        "candidate_observation_count": candidate_count,
                        "case_count": selected["case_id"].nunique(),
                        "parent_bug_count": selected["parent_bug_id"].nunique(),
                        "deduplicated": deduplicated,
                        "dedup_key": dedup_key,
                        "parent_aggregation": "macro_mean_cases",
                        "overlap_status": overlap_status,
                        "sample_definition": sample_definition,
                    }
                )
    return pd.DataFrame(rows, columns=REQUIRED_OUTPUT_COLUMNS)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_csv", type=Path)
    parser.add_argument("output_csv", type=Path)
    parser.add_argument("--k", type=int, required=True)
    parser.add_argument("--metric", default="strict_success")
    parser.add_argument("--overlap-status", choices=OVERLAP_VALUES, required=True)
    parser.add_argument("--sample-definition", required=True)
    parser.add_argument("--model-column", default="model_label")
    args = parser.parse_args()
    raw = normalize_raw_results(
        pd.read_csv(args.input_csv, encoding="utf-8-sig"), args.model_column
    )
    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    summarize(
        raw,
        k=args.k,
        metric=args.metric,
        overlap_status=args.overlap_status,
        sample_definition=args.sample_definition,
    ).to_csv(args.output_csv, index=False, encoding="utf-8-sig")
    print(args.output_csv)


if __name__ == "__main__":
    main()
