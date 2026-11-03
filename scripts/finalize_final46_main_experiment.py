#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pandas as pd


REPO = Path(__file__).resolve().parents[1]
RUN = REPO / "outputs/final46_main_experiment/run"
OUT = REPO / "deliverables/final46_main_experiment_20260806"
FINAL_MANIFEST = REPO / "deliverables/final_dataset_acceptance_20260804/final_manifest.json"
K = 4
MODELS = {
    "GPT": "gpt-5.4",
    "Claude": "claude-opus-4-8",
    "Qwen": "qwen/qwen-2.5-72b-instruct",
}
METHODS = {
    "spec_only": "spec_only",
    "spec_rtl_full": "full_rtl",
    "spec_rtl_signal_list": "signal_list",
    "spec_rtl_sliced": "rtl_slice",
    "spec_rtl_raw_trace": "raw_trace",
    "spec_rtl_naive_summary": "naive_summary",
    "spec_rtl_event_abstraction": "event_abstraction",
    "spec_rtl_temporal_relation_abstraction": "temporal_abstraction",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, encoding="utf-8-sig", lineterminator="\n")


def bool_series(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.lower().isin({"1", "true", "yes"})


def aggregate(group: pd.DataFrame) -> dict:
    ordered = group.sort_values(["case_id", "candidate_index"])
    first = ordered.loc[ordered["candidate_index"] == 1]
    by_case = ordered.groupby(["case_id", "parent_bug_id"], as_index=False)["success"].any()
    by_parent = by_case.groupby("parent_bug_id", as_index=False)["success"].any()
    return {
        "candidate_count": len(ordered),
        "candidate_success_count": int(ordered["success"].sum()),
        "candidate_success_rate": float(ordered["success"].mean()),
        "first_candidate_case_count": len(first),
        "first_candidate_success_count": int(first["success"].sum()),
        "first_candidate_success_rate": float(first["success"].mean()),
        "case_count": len(by_case),
        "case_any_of_k_success_count": int(by_case["success"].sum()),
        "case_any_of_k_success_rate": float(by_case["success"].mean()),
        "parent_bug_count": len(by_parent),
        "parent_any_of_k_success_count": int(by_parent["success"].sum()),
        "parent_any_of_k_success_rate": float(by_parent["success"].mean()),
    }


def build_main(detail: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (model, model_id, method), group in detail.groupby(["model", "model_id", "method"], sort=True):
        rows.append({
            "model": model, "model_id": model_id, "method": method,
            "candidate_budget_k": K, **aggregate(group),
        })
    return pd.DataFrame(rows).sort_values(["model", "method"]).reset_index(drop=True)


def build_breakdown(detail: pd.DataFrame) -> pd.DataFrame:
    rows = []
    dimensions = {
        "model": "model",
        "bug_class": "bug_class",
        "project": "source_project",
        "family": "bug_family",
    }
    for dimension, column in dimensions.items():
        for keys, group in detail.groupby([column, "model", "model_id", "method"], sort=True):
            value, model, model_id, method = keys
            rows.append({
                "dimension": dimension, "dimension_value": value,
                "model": model, "model_id": model_id, "method": method,
                "candidate_budget_k": K, **aggregate(group),
            })
    return pd.DataFrame(rows).sort_values(["dimension", "dimension_value", "model", "method"]).reset_index(drop=True)


def build_parent(detail: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for keys, group in detail.groupby(["model", "model_id", "method", "parent_bug_id"], sort=True):
        model, model_id, method, parent = keys
        cases = sorted(group["case_id"].unique())
        first = group.loc[group["candidate_index"] == 1, "success"]
        rows.append({
            "model": model, "model_id": model_id, "method": method,
            "parent_bug_id": parent, "case_ids": ";".join(cases), "case_count": len(cases),
            "candidate_budget_k": K, "candidate_count": len(group),
            "candidate_success_count": int(group["success"].sum()),
            "first_candidate_success": bool(first.any()),
            "parent_any_of_k_success": bool(group["success"].any()),
            "dedup_key": "parent_bug_id",
            "trace_variants_count_as_independent": False,
        })
    return pd.DataFrame(rows).sort_values(["model", "method", "parent_bug_id"]).reset_index(drop=True)


def main() -> None:
    manifest = json.loads(FINAL_MANIFEST.read_text(encoding="utf-8"))
    metadata = {}
    for item in manifest["cases"]:
        metadata[item["name"]] = {
            "parent_bug_id": item["parent_bug_id"],
            "bug_class": item["bug_class"],
            "source_project": item["source_project"],
            "bug_family": item["bug_family"],
        }
    frames = []
    sources = []
    for model, model_id in MODELS.items():
        for family in ("context", "trace"):
            path = RUN / model / family / "multi_model_results_raw.csv"
            if not path.is_file():
                raise SystemExit(f"missing result shard: {path}")
            frame = pd.read_csv(path, encoding="utf-8-sig")
            frames.append(frame)
            sources.append({"model": model, "family": family, "path": str(path.relative_to(REPO)), "sha256": sha(path), "rows": len(frame)})
    detail = pd.concat(frames, ignore_index=True)
    detail = detail.rename(columns={"model_label": "model", "case_id": "case_id"})
    detail["model_id"] = detail["model"].map(MODELS)
    detail["method_native"] = detail["method"]
    detail["method"] = detail["method"].map(METHODS)
    if detail["method"].isna().any():
        raise SystemExit("unknown method in raw results")
    for field in ("parent_bug_id", "bug_class", "source_project", "bug_family"):
        detail[field] = detail["case_id"].map(lambda case: metadata[case][field])
    detail["candidate_index"] = pd.to_numeric(detail["candidate_index"], errors="raise").astype(int)
    detail["success"] = detail["failure_mode"].astype(str).eq("success")
    detail["success_recomputed"] = (
        bool_series(detail["compile_ok"])
        & bool_series(detail["correct_pass"])
        & bool_series(detail["buggy_fail"])
        & bool_series(detail["antecedent_hit_buggy"])
        & bool_series(detail["non_vacuous_buggy"])
        & bool_series(detail["heldout_correct_pass"])
        & bool_series(detail["heldout_buggy_fail"])
        & bool_series(detail["heldout_antecedent_hit"])
        & bool_series(detail["heldout_non_vacuous"])
    )
    detail["success_definition_matches"] = detail["success"] == detail["success_recomputed"]

    key = ["model", "case_id", "method", "candidate_index"]
    duplicates = int(detail.duplicated(key).sum())
    expected_rows = len(MODELS) * len(metadata) * len(METHODS) * K
    expected_cells = len(MODELS) * len(metadata) * len(METHODS)
    cells = detail.groupby(["model", "case_id", "method"])["candidate_index"].agg(list)
    bad_cells = [idx for idx, values in cells.items() if sorted(values) != list(range(1, K + 1))]
    locked_models_ok = all(
        set(detail.loc[detail["model"] == model, "model_name"].astype(str)) == {model_id}
        for model, model_id in MODELS.items()
    )
    completeness = {
        "expected_candidate_rows": expected_rows,
        "actual_candidate_rows": len(detail),
        "expected_cells": expected_cells,
        "actual_cells": len(cells),
        "duplicate_candidate_keys": duplicates,
        "bad_budget_cell_count": len(bad_cells),
        "candidate_budget_k": K,
        "model_ids_locked": locked_models_ok,
        "success_definition_mismatch_count": int((~detail["success_definition_matches"]).sum()),
    }
    if not (
        len(detail) == expected_rows and len(cells) == expected_cells and duplicates == 0
        and not bad_cells and locked_models_ok and completeness["success_definition_mismatch_count"] == 0
    ):
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "INCOMPLETE_RUN.json").write_text(json.dumps({**completeness, "bad_cells": [list(x) for x in bad_cells[:100]]}, indent=2) + "\n", encoding="utf-8")
        raise SystemExit(f"experiment incomplete: {completeness}")

    ordered_columns = [
        "model", "model_id", "method", "method_native", "case_id", "parent_bug_id",
        "bug_class", "source_project", "bug_family", "candidate_index", "assertion_text",
        "success", "compile_ok", "correct_pass", "buggy_fail", "antecedent_hit_buggy",
        "non_vacuous_buggy", "heldout_correct_pass", "heldout_buggy_fail",
        "heldout_antecedent_hit", "heldout_non_vacuous", "failure_mode", "failure_reason",
        "seen_good_ant_hits", "seen_bad_ant_hits", "heldout_bad_ant_hits",
        "seen_good_fail_hits", "seen_bad_fail_hits", "heldout_good_fail_hits", "heldout_bad_fail_hits",
    ]
    detail = detail[ordered_columns].sort_values(key).reset_index(drop=True)
    main_table = build_main(detail)
    breakdown = build_breakdown(detail)
    parents = build_parent(detail)

    OUT.mkdir(parents=True, exist_ok=True)
    write_csv(detail, OUT / "candidate_details.csv")
    write_csv(main_table, OUT / "unified_main_table.csv")
    write_csv(breakdown, OUT / "breakdown_by_model_bugclass_project_family.csv")
    write_csv(parents, OUT / "parent_deduplicated_results.csv")

    reloaded = pd.read_csv(OUT / "candidate_details.csv", encoding="utf-8-sig")
    reloaded["success"] = bool_series(reloaded["success"])
    recalculated = build_main(reloaded)
    comparison = main_table.merge(recalculated, on=["model", "model_id", "method"], suffixes=("_published", "_recomputed"))
    metric_cols = [col for col in main_table if col not in {"model", "model_id", "method"}]
    checks = []
    for _, row in comparison.iterrows():
        mismatches = []
        for col in metric_cols:
            left, right = row[f"{col}_published"], row[f"{col}_recomputed"]
            if pd.isna(left) and pd.isna(right):
                continue
            if isinstance(left, float) or isinstance(right, float):
                if abs(float(left) - float(right)) > 1e-12:
                    mismatches.append(col)
            elif left != right:
                mismatches.append(col)
        checks.append({
            "model": row["model"], "model_id": row["model_id"], "method": row["method"],
            "all_metrics_match": not mismatches, "mismatched_metrics": ";".join(mismatches),
        })
    check_df = pd.DataFrame(checks)
    write_csv(check_df, OUT / "main_table_recompute_check.csv")
    audit = {
        "schema_version": 1,
        "status": "complete" if check_df["all_metrics_match"].all() else "failed",
        "completeness": completeness,
        "source_shards": sources,
        "candidate_details_sha256": sha(OUT / "candidate_details.csv"),
        "unified_main_table_sha256": sha(OUT / "unified_main_table.csv"),
        "recompute_row_count": len(check_df),
        "recompute_all_match": bool(check_df["all_metrics_match"].all()),
        "parent_case_one_to_one": bool((parents["case_count"] == 1).all()),
        "trace_variants_count_as_independent": False,
    }
    (OUT / "recompute_audit.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    files = [p for p in sorted(OUT.iterdir()) if p.is_file() and p.name != "SHA256SUMS.txt"]
    (OUT / "SHA256SUMS.txt").write_text("\n".join(f"{sha(p)}  {p.name}" for p in files) + "\n", encoding="utf-8")
    print(json.dumps({"rows": len(detail), "main_rows": len(main_table), "breakdown_rows": len(breakdown), "parent_rows": len(parents), **audit}, indent=2))


if __name__ == "__main__":
    main()
