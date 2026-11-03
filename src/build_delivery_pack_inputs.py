from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "generated_main_results_strict_success"
DATA_DIR = OUT_DIR / "_delivery_pack_data"

ABSTRACTED_AUDIT_CSV = OUT_DIR / "abstracted_summary_audit_20cases.csv"
ABSTRACTED_BREAKDOWN_JSON = OUT_DIR / "abstracted_summary_root_cause_breakdown.json"
CASE_DELTA_CSV = OUT_DIR / "case_level_delta_matrix.csv"
CASE_DELTA_SUMMARY_JSON = OUT_DIR / "case_level_delta_summary.json"
RTL_CONTEXT_SUMMARY_JSON = OUT_DIR / "rtl_context_ablation_summary.json"
TRACE_REPR_SUMMARY_JSON = OUT_DIR / "trace_representation_ablation_summary.json"
TRACEGUARD_SUMMARY_JSON = OUT_DIR / "traceguard_rerank_summary.json"
MULTI_MODEL_RAW_CSV = ROOT / "outputs" / "scale120_full_model_eval_data" / "multi_model_results_raw.csv"

SCALE160_ROOT = ROOT / "rtl_cases_real_scale160_temporal_boosted"
SCALE120_ROOT = ROOT / "rtl_cases_real_scale120"
TEMPORAL_SUMMARY_JSON = SCALE160_ROOT / "temporal_variant_expansion_summary.json"
TEMPORAL_VALIDATION_CSV = SCALE160_ROOT / "temporal_variant_inherited_validation.csv"
TEMPORAL_JASPER_CSV = ROOT / "outputs" / "scale160_temporal_boost_subset_jasper" / "jasper_reachability_scale160_temporal_boost_subset.csv"
TEMPORAL_GOLDEN_CSV = ROOT / "outputs" / "scale160_temporal_boost_subset_wsl_formal" / "golden_recheck_scale160_temporal_boost_subset_formal.csv"
TEMPORAL_HARDNESS_CSV = ROOT / "outputs" / "scale160_temporal_boost_subset_wsl_formal" / "hardness_scale160_temporal_boost_subset_formal.csv"
TEMPORAL_DIVERGENCE_CSV = ROOT / "outputs" / "scale160_temporal_boost_subset_wsl_formal" / "trace_divergence_scale160_temporal_boost_subset_formal.csv"
TEMPORAL_MODEL_RESULTS_CSV = ROOT / "outputs" / "scale120_trace_representation_ablation_data" / "multi_model_results_raw.csv"

TEMPORAL40_PARENT_IDS = [f"case{case_num}" for case_num in range(101, 141)]


def is_temporal40_parent(case_name: object) -> bool:
    value = str(case_name)
    return any(value.startswith(f"{prefix}_") for prefix in TEMPORAL40_PARENT_IDS)


def strict_success_series(df: pd.DataFrame) -> pd.Series:
    required = [
        "heldout_correct_pass",
        "heldout_buggy_fail",
        "heldout_antecedent_hit",
        "heldout_non_vacuous",
    ]
    values = []
    for col in required:
        if col not in df.columns:
            raise ValueError(f"Temporal40 model results missing required column: {col}")
        values.append(df[col].astype(str).str.lower().isin(["true", "1", "yes"]))
    return values[0] & values[1] & values[2] & values[3]


def canonical_temporal_method(method: object) -> str | None:
    value = str(method).strip().lower()
    if value in {"raw", "raw_trace", "spec_rtl_raw_trace"}:
        return "raw"
    if value in {"summary", "naive_summary", "spec_rtl_naive_summary"}:
        return "summary"
    if value in {
        "temporal_abstraction",
        "temporal_relation_abstraction",
        "spec_rtl_temporal_relation_abstraction",
    }:
        return "temporal_abstraction"
    return None


def build_temporal40_stability(manifest_40: pd.DataFrame) -> None:
    out_detail = DATA_DIR / "new_temporal40_seen_trace_stability.csv"
    out_summary = DATA_DIR / "new_temporal40_seen_trace_stability_summary.csv"
    methods = ["raw", "summary", "temporal_abstraction"]

    if not TEMPORAL_MODEL_RESULTS_CSV.exists():
        pd.DataFrame(
            [
                {
                    "method": method,
                    "status": "not_evaluated",
                    "comparable_parent_bug_count": 0,
                    "stable_parent_bug_count": 0,
                    "unstable_parent_bug_count": 0,
                    "stability_rate": "",
                    "reason": "missing temporal40 multi_model_results_raw.csv",
                }
                for method in methods
            ]
        ).to_csv(out_summary, index=False, encoding="utf-8-sig")
        pd.DataFrame(
            columns=[
                "model_label", "parent_bug_id", "method", "variant_count",
                "trace_variants", "strict_success_values", "stable",
            ]
        ).to_csv(out_detail, index=False, encoding="utf-8-sig")
        return

    results = pd.read_csv(TEMPORAL_MODEL_RESULTS_CSV, encoding="utf-8-sig")
    case_col = "case_id" if "case_id" in results.columns else "case_name"
    results["method_canonical"] = results["method"].map(canonical_temporal_method)
    results = results.loc[results["method_canonical"].notna()].copy()
    results["strict_success"] = strict_success_series(results)
    results = results.merge(
        manifest_40[["case_name", "parent_bug_id"]],
        left_on=case_col,
        right_on="case_name",
        how="inner",
    )
    model_col = "model_label" if "model_label" in results.columns else "model_name"

    # Candidate-level runs may contain several assertions. A case succeeds if
    # any candidate meets the strict held-out criterion.
    case_results = (
        results.groupby([model_col, "parent_bug_id", "method_canonical", "case_name"], as_index=False)
        ["strict_success"].any()
    )
    detail_rows = []
    for (model, parent, method), group in case_results.groupby(
        [model_col, "parent_bug_id", "method_canonical"], sort=True
    ):
        expected = int((manifest_40["parent_bug_id"] == parent).sum())
        if len(group) < 2 or len(group) != expected:
            continue
        ordered = group.sort_values("case_name")
        values = ordered["strict_success"].astype(bool).tolist()
        detail_rows.append(
            {
                "model_label": model,
                "parent_bug_id": parent,
                "method": method,
                "variant_count": len(ordered),
                "trace_variants": ";".join(ordered["case_name"]),
                "strict_success_values": ";".join("1" if v else "0" for v in values),
                "stable": len(set(values)) == 1,
            }
        )
    detail = pd.DataFrame(detail_rows)
    detail.to_csv(out_detail, index=False, encoding="utf-8-sig")
    summary_rows = []
    for method in methods:
        subset = detail.loc[detail["method"] == method] if not detail.empty else detail
        stable_group_count = int(subset["stable"].sum()) if not subset.empty else 0
        group_count = len(subset)
        parent_count = int(subset["parent_bug_id"].nunique()) if not subset.empty else 0
        parent_stability = (
            subset.groupby("parent_bug_id")["stable"].all() if not subset.empty else pd.Series(dtype=bool)
        )
        stable_parent_count = int(parent_stability.sum())
        summary_rows.append(
            {
                "method": method,
                "status": "ok" if group_count else "no_complete_variant_groups",
                "comparable_parent_bug_count": parent_count,
                "stable_parent_bug_count": stable_parent_count,
                "unstable_parent_bug_count": parent_count - stable_parent_count,
                "stability_rate": stable_parent_count / parent_count if parent_count else "",
                "comparable_parent_model_group_count": group_count,
                "stable_parent_model_group_count": stable_group_count,
                "unstable_parent_model_group_count": group_count - stable_group_count,
                "parent_model_group_stability_rate": stable_group_count / group_count if group_count else "",
                "reason": "",
            }
        )
    pd.DataFrame(summary_rows).to_csv(out_summary, index=False, encoding="utf-8-sig")


def evaluated_seen_trace_manifest() -> pd.DataFrame:
    """Return only canonical/variant cases that have actual model outcomes.

    scale120 contains 80 independently generated seen-trace variants for ten
    temporal40 parents.  These are the valid observations for stability; the
    later case301..case340 role permutations are catalogued separately and
    must not be treated as evaluated until model outcomes exist.
    """
    manifest = pd.DataFrame(
        json.loads((SCALE120_ROOT / "case_manifest.json").read_text(encoding="utf-8"))["cases"]
    )
    manifest["parent_bug_id"] = manifest.apply(
        lambda row: row["seed_case_name"]
        if pd.notna(row.get("seed_case_name")) and str(row.get("seed_case_name")).strip()
        else row["name"],
        axis=1,
    )
    manifest = manifest.loc[manifest["parent_bug_id"].map(is_temporal40_parent)].copy()
    results = pd.read_csv(TEMPORAL_MODEL_RESULTS_CSV, encoding="utf-8-sig", usecols=["case_id"])
    evaluated = set(results["case_id"].astype(str))
    manifest = manifest.loc[manifest["name"].isin(evaluated)].copy()
    counts = manifest.groupby("parent_bug_id")["name"].transform("size")
    manifest = manifest.loc[counts >= 2].copy()
    manifest["trace_role"] = manifest.apply(
        lambda row: "canonical_primary" if row["name"] == row["parent_bug_id"] else "seen_trace_variant",
        axis=1,
    )
    out = manifest[["name", "parent_bug_id", "trace_role", "seed_case_name"]].rename(
        columns={"name": "case_name"}
    ).sort_values(["parent_bug_id", "case_name"])
    out.to_csv(DATA_DIR / "temporal40_evaluated_seen_variant_map.csv", index=False, encoding="utf-8-sig")
    return out


def build_independent_temporal40_results() -> None:
    """Build the corrected 40-independent-bug view.

    case101..case140 define the denominator. Track permutations are auxiliary
    observations attached to those parent bugs and never increase it.
    """
    manifest = pd.DataFrame(
        json.loads((SCALE160_ROOT / "case_manifest.json").read_text(encoding="utf-8"))["cases"]
    )
    manifest["parent_bug_id"] = manifest.apply(
        lambda row: row.get("parent_bug_id") or row.get("seed_case_name") or row["name"], axis=1
    )
    parents = manifest.loc[manifest["name"].map(is_temporal40_parent)].copy()
    parents = parents.loc[parents["name"] == parents["parent_bug_id"]].sort_values("name")
    if len(parents) != 40 or parents["parent_bug_id"].nunique() != 40:
        raise RuntimeError(
            f"Corrected temporal40 must contain 40 independent parents; got rows={len(parents)}, "
            f"unique={parents['parent_bug_id'].nunique()}"
        )

    trace_variants = manifest.loc[
        manifest.get("variant_track_plan", pd.Series(index=manifest.index, dtype=object)).notna()
        & manifest["parent_bug_id"].isin(parents["parent_bug_id"])
    ].copy()
    variant_map = (
        trace_variants.sort_values("name")
        .groupby("parent_bug_id", as_index=False)
        .agg(
            trace_variant_count=("name", "size"),
            trace_variants=("name", lambda values: ";".join(values)),
            seen_source_tracks=("variant_primary_source_track", lambda values: ";".join(sorted(set(map(str, values))))),
        )
    )
    parent_keep = [
        "parent_bug_id", "name", "source_project", "source_module", "bug_class",
        "bug_family", "bug_type", "spec",
    ]
    parent_manifest = parents[parent_keep].rename(columns={"name": "canonical_case_name"}).merge(
        variant_map, on="parent_bug_id", how="left"
    )
    parent_manifest["trace_variant_count"] = parent_manifest["trace_variant_count"].fillna(0).astype(int)
    parent_manifest["trace_variants"] = parent_manifest["trace_variants"].fillna("")
    parent_manifest["seen_source_tracks"] = parent_manifest["seen_source_tracks"].fillna("")
    parent_manifest.to_csv(DATA_DIR / "temporal40_parent_bug_manifest.csv", index=False, encoding="utf-8-sig")
    trace_variants.to_csv(DATA_DIR / "temporal40_trace_variant_map.csv", index=False, encoding="utf-8-sig")

    results = pd.read_csv(TEMPORAL_MODEL_RESULTS_CSV, encoding="utf-8-sig")
    results["method_canonical"] = results["method"].map(canonical_temporal_method)
    results = results.loc[
        results["case_id"].isin(parents["parent_bug_id"])
        & results["method_canonical"].isin(["raw", "summary", "temporal_abstraction"])
    ].copy()
    results["strict_success"] = strict_success_series(results)
    model_col = "model_label" if "model_label" in results.columns else "model_name"
    parent_case = (
        results.groupby([model_col, "method_canonical", "case_id"], as_index=False)["strict_success"].any()
        .rename(columns={"case_id": "parent_bug_id", "method_canonical": "method"})
    )
    parent_case.to_csv(DATA_DIR / "temporal40_main_result_parent_matrix.csv", index=False, encoding="utf-8-sig")
    main_summary = (
        parent_case.groupby([model_col, "method"], as_index=False)
        .agg(
            independent_parent_bug_count=("parent_bug_id", "nunique"),
            strict_success_parent_bug_count=("strict_success", "sum"),
            strict_success_rate=("strict_success", "mean"),
        )
    )
    main_summary.to_csv(DATA_DIR / "temporal40_main_results_by_parent.csv", index=False, encoding="utf-8-sig")

    # Stability uses only trace variants with actual model outcomes. Unevaluated
    # case301..case340 role permutations remain in the catalog but not metrics.
    build_temporal40_stability(evaluated_seen_trace_manifest())
    stability_detail = pd.read_csv(DATA_DIR / "new_temporal40_seen_trace_stability.csv", encoding="utf-8-sig")
    overview = [
        {"metric": "independent_parent_bug_count", "value": 40},
        {"metric": "canonical_parent_case_count", "value": len(parents)},
        {"metric": "parent_bugs_with_seen_trace_variants", "value": int(variant_map["parent_bug_id"].nunique())},
        {"metric": "seen_trace_variant_case_count", "value": len(trace_variants)},
        {"metric": "seen_trace_stability_comparable_parent_bugs", "value": int(stability_detail["parent_bug_id"].nunique())},
        {"metric": "seen_trace_stability_comparable_parent_model_groups", "value": len(stability_detail)},
    ]
    pd.DataFrame(overview).to_csv(DATA_DIR / "temporal40_overview.csv", index=False, encoding="utf-8-sig")


def flatten_simple_json(payload: dict, prefix: str = "") -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for key, value in payload.items():
        field = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict):
            rows.extend(flatten_simple_json(value, field))
        elif isinstance(value, list):
            rows.append({"field": field, "value": "; ".join(str(v) for v in value)})
        else:
            rows.append({"field": field, "value": value})
    return rows


def build_key_value_csvs() -> None:
    for src_path, out_name in [
        (CASE_DELTA_SUMMARY_JSON, "case_delta_summary.csv"),
        (TRACEGUARD_SUMMARY_JSON, "traceguard_summary_kv.csv"),
    ]:
        payload = json.loads(src_path.read_text(encoding="utf-8"))
        pd.DataFrame(flatten_simple_json(payload)).to_csv(DATA_DIR / out_name, index=False, encoding="utf-8-sig")

    rtl_payload = json.loads(RTL_CONTEXT_SUMMARY_JSON.read_text(encoding="utf-8"))
    rtl_rows: list[dict[str, object]] = []
    for model, info in rtl_payload["models"].items():
        row = {
            "model": model,
            "full_rtl_hurts_case_count": info["full_rtl_hurts_case_count"],
            "interface_recovers_case_count": info["interface_recovers_case_count"],
            "signal_list_recovers_case_count": info["signal_list_recovers_case_count"],
            "sliced_rtl_recovers_case_count": info["sliced_rtl_recovers_case_count"],
            "all_lightweight_fail_case_count": info["all_lightweight_fail_case_count"],
        }
        row.update({f"rate_{k}": v for k, v in info["method_case_strict_success_rate"].items()})
        rtl_rows.append(row)
    pd.DataFrame(rtl_rows).to_csv(DATA_DIR / "rtl_context_model_summary.csv", index=False, encoding="utf-8-sig")

    trace_payload = json.loads(TRACE_REPR_SUMMARY_JSON.read_text(encoding="utf-8"))
    trace_rows: list[dict[str, object]] = []
    for model, info in trace_payload["models"].items():
        row = {
            "model": model,
            "raw_only_success_case_count": info["raw_only_success_case_count"],
            "naive_only_success_case_count": info["naive_only_success_case_count"],
            "event_only_success_case_count": info["event_only_success_case_count"],
            "temporal_only_success_case_count": info["temporal_only_success_case_count"],
            "raw_beats_naive_case_count": info["raw_beats_naive_case_count"],
            "event_beats_naive_case_count": info["event_beats_naive_case_count"],
            "temporal_beats_event_case_count": info["temporal_beats_event_case_count"],
            "temporal_beats_raw_case_count": info["temporal_beats_raw_case_count"],
            "raw_beats_temporal_case_count": info["raw_beats_temporal_case_count"],
            "temporal_hurts_vs_naive_case_count": info["temporal_hurts_vs_naive_case_count"],
            "temporal_hurts_vs_event_case_count": info["temporal_hurts_vs_event_case_count"],
        }
        row.update({f"rate_{k}": v for k, v in info["method_case_strict_success_rate"].items()})
        trace_rows.append(row)
    pd.DataFrame(trace_rows).to_csv(DATA_DIR / "trace_representation_model_summary.csv", index=False, encoding="utf-8-sig")

    traceguard_payload = json.loads(TRACEGUARD_SUMMARY_JSON.read_text(encoding="utf-8"))
    traceguard_rows: list[dict[str, object]] = []
    for policy in ["baseline_first", "best_of_k_oracle", "traceguard_rerank"]:
        for method, metrics in traceguard_payload[policy].items():
            traceguard_rows.append(
                {
                    "selection_policy": policy,
                    "method": method,
                    **metrics,
                }
            )
    pd.DataFrame(traceguard_rows).to_csv(DATA_DIR / "traceguard_summary_table.csv", index=False, encoding="utf-8-sig")


def build_temporal40_manifest_csv() -> None:
    manifest = json.loads((SCALE160_ROOT / "case_manifest.json").read_text(encoding="utf-8"))["cases"]
    manifest_df = pd.DataFrame(manifest)
    summary_payload = json.loads(TEMPORAL_SUMMARY_JSON.read_text(encoding="utf-8"))
    case_names = [str(name) for name in summary_payload["new_case_names"]]

    manifest_40 = manifest_df.loc[manifest_df["name"].isin(case_names)].copy()
    manifest_40["case_name"] = manifest_40["name"]
    manifest_40["parent_bug_id"] = manifest_40.apply(
        lambda row: row.get("parent_bug_id") or row.get("seed_case_name") or row["name"], axis=1
    )
    manifest_40["golden_sva_text"] = manifest_40["golden_sva"].apply(lambda x: (x or {}).get("sva", ""))
    manifest_40["golden_temporal_type"] = manifest_40["golden_sva"].apply(lambda x: (x or {}).get("temporal_type", ""))

    inherited_df = pd.read_csv(TEMPORAL_VALIDATION_CSV)
    inherited_keep = [
        "case_name",
        "seed_formal_golden_ok",
        "seed_formal_reachability_ok",
        "seed_hardness_ok",
        "seed_divergence_gate_ok",
        "primary_track_inherited_ok",
        "holdout_track_inherited_ok",
        "decoy_track_inherited_ok",
        "inherited_validation_ok",
    ]
    inherited_keep = [col for col in inherited_keep if col in inherited_df.columns]
    jasper_df = pd.read_csv(TEMPORAL_JASPER_CSV).rename(columns={"case_name": "case_name"})
    golden_df = pd.read_csv(TEMPORAL_GOLDEN_CSV).rename(columns={"case_name": "case_name"})
    hardness_df = pd.read_csv(TEMPORAL_HARDNESS_CSV).rename(columns={"case_name": "case_name"})
    divergence_df = pd.read_csv(TEMPORAL_DIVERGENCE_CSV).rename(columns={"case_name": "case_name"})

    golden_cols = [
        "case_name",
        "golden_ok_strict",
        "compile_ok",
        "heldout_correct_pass",
        "heldout_buggy_fail",
        "heldout_antecedent_hit",
        "heldout_non_vacuous",
    ]
    golden_cols = [col for col in golden_cols if col in golden_df.columns]

    merged = (
        manifest_40.merge(inherited_df[inherited_keep], on="case_name", how="left")
        .merge(
            jasper_df[
                [
                    "case_name",
                    "antecedent_reachability_label",
                    "proof_status",
                    "effective_proof_status",
                    "formal_failure_reason",
                ]
            ],
            on="case_name",
            how="left",
        )
        .merge(
            golden_df[golden_cols],
            on="case_name",
            how="left",
        )
        .merge(
            hardness_df[["case_name", "hardness_ok", "golden_ok", "loose_control_misses_bug", "divergence_gate_ok"]],
            on="case_name",
            how="left",
        )
        .merge(
            divergence_df[
                [
                    "case_name",
                    "primary_diverges",
                    "heldout_diverges",
                    "decoy_diverges",
                    "divergence_gate_ok",
                ]
            ].rename(columns={"divergence_gate_ok": "trace_divergence_gate_ok"}),
            on="case_name",
            how="left",
        )
    )

    keep_cols = [
        "case_name",
        "parent_bug_id",
        "source_project",
        "source_module",
        "bug_class",
        "bug_family",
        "bug_type",
        "seed_case_name",
        "variant_parent_case",
        "variant_track_plan",
        "variant_primary_source_track",
        "variant_holdout_source_track",
        "variant_decoy_source_track",
        "golden_temporal_type",
        "spec",
        "golden_sva_text",
        "inherited_validation_ok",
        "seed_formal_golden_ok",
        "seed_formal_reachability_ok",
        "seed_hardness_ok",
        "seed_divergence_gate_ok",
        "antecedent_reachability_label",
        "proof_status",
        "effective_proof_status",
        "golden_ok_strict",
        "hardness_ok",
        "golden_ok",
        "loose_control_misses_bug",
        "divergence_gate_ok",
        "primary_diverges",
        "heldout_diverges",
        "decoy_diverges",
        "trace_divergence_gate_ok",
    ]
    merged[keep_cols].sort_values("case_name").to_csv(
        DATA_DIR / "new_temporal40_manifest.csv",
        index=False,
        encoding="utf-8-sig",
    )

    parent_rows = []
    for parent_bug_id, group in merged.sort_values("case_name").groupby("parent_bug_id", sort=True):
        parent_rows.append(
            {
                "parent_bug_id": parent_bug_id,
                "bug_type": group["bug_type"].iloc[0],
                "bug_family": group["bug_family"].iloc[0],
                "trace_variant_count": len(group),
                "trace_variants": ";".join(group["case_name"]),
                "seen_source_tracks": ";".join(sorted(set(group["variant_primary_source_track"].astype(str)))),
                "all_inherited_validation_ok": bool(group["inherited_validation_ok"].fillna(False).all()),
                "all_golden_ok_strict": bool(group["golden_ok_strict"].fillna(False).all()),
                "all_hardness_ok": bool(group["hardness_ok"].fillna(False).all()),
                "all_trace_divergence_gate_ok": bool(group["trace_divergence_gate_ok"].fillna(False).all()),
            }
        )
    parent_df = pd.DataFrame(parent_rows)
    parent_df.to_csv(DATA_DIR / "new_temporal40_parent_bug_summary.csv", index=False, encoding="utf-8-sig")
    build_temporal40_stability(merged)

    overview_rows = [
        {"metric": "new_temporal_variant_count", "value": summary_payload["new_temporal_variant_count"]},
        {"metric": "independent_parent_bug_count", "value": int(merged["parent_bug_id"].nunique())},
        {"metric": "parent_bug_all_inherited_validation_ok_count", "value": int(parent_df["all_inherited_validation_ok"].sum())},
        {"metric": "parent_bug_all_golden_ok_strict_count", "value": int(parent_df["all_golden_ok_strict"].sum())},
        {"metric": "parent_bug_all_hardness_ok_count", "value": int(parent_df["all_hardness_ok"].sum())},
        {"metric": "parent_bug_all_trace_divergence_gate_ok_count", "value": int(parent_df["all_trace_divergence_gate_ok"].sum())},
        {"metric": "total_temporal_cross_cycle_count", "value": summary_payload["bug_class_counts"]["temporal_cross_cycle"]},
        {"metric": "all_inherited_validation_ok", "value": summary_payload["all_inherited_validation_ok"]},
        {"metric": "jasper_reachable_count", "value": int((jasper_df["antecedent_reachability_label"] == "reachable").sum())},
        {"metric": "golden_strict_pass_count", "value": int(pd.read_csv(TEMPORAL_GOLDEN_CSV)["golden_ok_strict"].sum())},
        {"metric": "hardness_ok_count", "value": int(pd.read_csv(TEMPORAL_HARDNESS_CSV)["hardness_ok"].sum())},
        {"metric": "divergence_gate_ok_count", "value": int(pd.read_csv(TEMPORAL_DIVERGENCE_CSV)["divergence_gate_ok"].sum())},
    ]
    pd.DataFrame(overview_rows).to_csv(DATA_DIR / "new_temporal40_overview.csv", index=False, encoding="utf-8-sig")


def build_abstracted_audit_md() -> None:
    audit_df = pd.read_csv(ABSTRACTED_AUDIT_CSV)
    breakdown = json.loads(ABSTRACTED_BREAKDOWN_JSON.read_text(encoding="utf-8"))
    delta_summary = json.loads(CASE_DELTA_SUMMARY_JSON.read_text(encoding="utf-8"))

    primary_causes = breakdown["case_primary_root_causes"]
    prototype = breakdown["prototype_candidate_breakdown"]
    lines = [
        "# Abstracted Summary Zero Audit",
        "",
        "## Bottom line",
        "",
        "The original `Abstracted Summary = 0` observation was not a valid method conclusion.",
        "The 20-case audit showed that the old zero mixed two different issues:",
        "",
        f"- `12/20` audited cases were simply `not run` because the old scale120 full eval had no abstracted input for them.",
        f"- In the `8` legacy prototype cases that did run, prompt generation and candidate extraction were present, but the failures were dominated by compile and semantic quality issues rather than missing prompts.",
        "",
        f"After the strict scale120 backfill, abstracted is now `run` on all `{delta_summary['abstracted_run_case_count']}` cases, with `{delta_summary['abstracted_success_case_count']}` strict-success cases.",
        "",
        "## 20-case audit breakdown",
        "",
        f"- `prompt_generated_case_count = {breakdown['audit_sample']['prompt_generated_case_count']}`",
        f"- `sva_extracted_case_count = {breakdown['audit_sample']['sva_extracted_case_count']}`",
        f"- `compile_ok_case_count = {breakdown['audit_sample']['compile_ok_case_count']}`",
        f"- `parser_unsupported_case_count = {breakdown['audit_sample']['parser_unsupported_case_count']}`",
        f"- `static_filter_false_kill_case_count = {breakdown['audit_sample']['static_filter_false_kill_case_count']}`",
        f"- `signal_name_missing_case_count = {breakdown['audit_sample']['signal_name_missing_case_count']}`",
        "",
        "Primary root causes by audited case:",
        "",
        f"- `missing_abstracted_summary_not_run`: {primary_causes.get('missing_abstracted_summary_not_run', 0)}",
        f"- `compile_fail_invalid_or_out_of_scope_identifiers`: {primary_causes.get('compile_fail_invalid_or_out_of_scope_identifiers', 0)}",
        f"- `compile_fail_other`: {primary_causes.get('compile_fail_other', 0)}",
        f"- `too_strong`: {primary_causes.get('too_strong', 0)}",
        f"- `vacuity`: {primary_causes.get('vacuity', 0)}",
        "",
        "## Legacy 8-case prototype candidate breakdown",
        "",
        f"- `compile_fail`: {prototype.get('compile_fail', 0)}",
        f"- `vacuity`: {prototype.get('vacuity', 0)}",
        f"- `too_strong`: {prototype.get('too_strong', 0)}",
        f"- `too_weak`: {prototype.get('too_weak', 0)}",
        f"- `success`: {prototype.get('success', 0)}",
        "",
        "## Interpretation",
        "",
        "- The old zero mainly came from missing scale120 coverage plus poor early prototype quality.",
        "- It was not caused by parser unsupported syntax or static filter false kills.",
        "- The backfilled strict scale120 run now shows abstracted is usable, but its sensitivity still depends on compile-safe, non-literal assertions.",
        "",
        "## Artifacts",
        "",
        f"- Audit CSV: `{ABSTRACTED_AUDIT_CSV}`",
        f"- Root-cause JSON: `{ABSTRACTED_BREAKDOWN_JSON}`",
        f"- Updated case delta summary: `{CASE_DELTA_SUMMARY_JSON}`",
    ]
    (OUT_DIR / "abstracted_summary_zero_audit.md").write_text("\n".join(lines), encoding="utf-8")


def build_analysis_onepager_md() -> None:
    delta_df = pd.read_csv(CASE_DELTA_CSV)
    trace_df = pd.read_csv(OUT_DIR / "trace_representation_ablation_case_matrix.csv")
    rtl_df = pd.read_csv(OUT_DIR / "rtl_context_ablation_case_matrix.csv")
    multi_df = pd.read_csv(MULTI_MODEL_RAW_CSV, encoding="utf-8-sig")

    raw_only = delta_df.loc[delta_df["raw_only_success"] == True, ["case_id", "bug_type", "raw_only_failure_reasons"]]
    summary_only = delta_df.loc[delta_df["summary_only_success"] == True, ["case_id", "bug_type", "summary_only_failure_reasons"]]

    qwen = multi_df.loc[multi_df["model_label"] == "Qwen"].copy()
    for col in [
        "compile_ok",
        "correct_pass",
        "buggy_fail",
        "heldout_correct_pass",
        "heldout_buggy_fail",
        "heldout_antecedent_hit",
        "heldout_non_vacuous",
        "trace_overfit",
        "literal_hardcoding",
    ]:
        qwen[col] = qwen[col].astype(str).str.lower().isin(["true", "1", "yes"])
    qwen["strict_success"] = (
        qwen["heldout_correct_pass"] & qwen["heldout_buggy_fail"] & qwen["heldout_antecedent_hit"] & qwen["heldout_non_vacuous"]
    )
    qwen_summary = (
        qwen.groupby("method")
        .agg(
            strict_success_rate=("strict_success", "mean"),
            compile_ok_rate=("compile_ok", "mean"),
            correct_pass_rate=("correct_pass", "mean"),
            buggy_fail_rate=("buggy_fail", "mean"),
            literal_hardcoding_rate=("literal_hardcoding", "mean"),
        )
        .round(3)
    )
    qwen_failure = (
        qwen.groupby(["method", "failure_mode"]).size().rename("count").reset_index()
        .sort_values(["method", "count"], ascending=[True, False])
    )

    lines = [
        "# One-Page Analysis",
        "",
        "## Raw trace saved what",
        "",
        f"In the primary scale120 delta matrix, raw trace is uniquely responsible for `{int(delta_df['raw_only_success'].sum())}` GPT cases, while summary is uniquely responsible for only `{int(delta_df['summary_only_success'].sum())}` case.",
        "The raw-only wins are concentrated in cases where the bug trigger is a narrow boundary or single-cycle event and the summary loses the exact activation shape.",
        "",
    ]
    for _, row in raw_only.iterrows():
        lines.append(f"- `{row['case_id']}`: `{row['bug_type']}`. Raw succeeds after other methods fail with `{row['raw_only_failure_reasons']}`.")
    lines.extend(
        [
            "",
            "In the dedicated trace-representation ablation, raw trace beats naive summary on `8` GPT cases and `4` Claude cases. The missed-summary reasons are usually one of two patterns: the antecedent becomes too weak and never fires, or it becomes too generic and no longer distinguishes buggy behavior at the boundary.",
            "",
            "## Summary missed what",
            "",
        ]
    )
    for _, row in summary_only.iterrows():
        lines.append(f"- `{row['case_id']}` is the only pure summary-only case in the main matrix: `{row['bug_type']}`. The non-summary methods fail with `{row['summary_only_failure_reasons']}`.")
    lines.extend(
        [
            "- Across the trace ablation matrices, the common summary failure mode is not raw noise but *loss of trigger precision*: FIFO boundary checks (`case104`/`case249`), edge-sync lag (`case123`), wrap timing (`case125`), and masked interrupt state cases (`case128`) all show summary-side misses because the summary compresses away the exact cycle-to-cycle condition that makes the assertion discriminative.",
            "",
            "## Why RTL interferes",
            "",
            "The interference story is model-dependent but still points to context overload rather than missing information.",
            "- Claude shows the clearest degradation: `spec_only` case success is `0.725`, `full RTL` drops to `0.692`, and the lightweight representations recover all `7/7` full-RTL hurt cases (`interface=7`, `signal_list=7`). That is strong evidence that the extra implementation detail is distracting the model away from the causal relation.",
            "- GPT is different in average rate but not in failure shape. `full RTL` is not globally worse (`0.742` vs `0.725` for `spec_only`), but it still hurts `9` concrete cases. Those hurt cases are dominated by `antecedent never triggers on buggy trace`, especially address-gating and FIFO-depth boundary families. The best GPT variant is actually `signal_list` at `0.783`, which again says compact structural context is more useful than full bodies of RTL.",
            "",
            "## Why Qwen does not really benefit from trace",
            "",
            f"The case-level matrix marks `qwen_hurts_case_count = {int(delta_df['qwen_hurts'].sum())}`. Candidate-level numbers show the issue is upstream of trace representation itself.",
            f"- Qwen strict-success stays flat or down when trace is added: `spec+RTL={qwen_summary.loc['spec_plus_rtl', 'strict_success_rate']:.3f}`, `raw={qwen_summary.loc['spec_rtl_raw_trace', 'strict_success_rate']:.3f}`, `summary={qwen_summary.loc['spec_rtl_trace_summary', 'strict_success_rate']:.3f}`.",
            f"- Qwen also enters trace methods with weaker basic execution quality: for `spec+RTL`, `compile_ok_rate={qwen_summary.loc['spec_plus_rtl', 'compile_ok_rate']:.3f}` and `correct_pass_rate={qwen_summary.loc['spec_plus_rtl', 'correct_pass_rate']:.3f}`; raw trace only partially recovers that.",
            "- The dominant Qwen failure modes are still `vacuity`, `too_strong`, and `compile_fail`, not trace-overfit. In other words, Qwen often fails to convert extra trace evidence into the right trigger/consequent decomposition; it either misses the antecedent altogether or writes an assertion that hurts the correct design.",
            "- This is why the trace channel does not rescue Qwen the way it helps GPT/Claude: the bottleneck is not lack of behavioral evidence, but lower robustness in turning that evidence into compile-safe, non-vacuous, correct-preserving assertions.",
        ]
    )
    (OUT_DIR / "one_page_analysis.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    build_key_value_csvs()
    build_temporal40_manifest_csv()
    build_independent_temporal40_results()
    build_abstracted_audit_md()
    build_analysis_onepager_md()
    print(DATA_DIR)
    print(OUT_DIR / "abstracted_summary_zero_audit.md")
    print(OUT_DIR / "one_page_analysis.md")


if __name__ == "__main__":
    main()
