from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]

CURRENT_MULTI_MODEL_RAW = ROOT / "outputs" / "scale120_full_model_eval_data" / "multi_model_results_raw.csv"
CURRENT_MULTI_MODEL_META = ROOT / "outputs" / "scale120_full_model_eval_data" / "multi_model_run_meta.json"
SCALE120_MANIFEST = ROOT / "rtl_cases_real_scale120" / "case_manifest.json"

OUTPUT_DIR = ROOT / "generated_main_results_strict_success"
MATRIX_CSV = OUTPUT_DIR / "case_level_delta_matrix.csv"
MATRIX_XLSX = OUTPUT_DIR / "case_level_delta_matrix.xlsx"
SUMMARY_JSON = OUTPUT_DIR / "case_level_delta_summary.json"
README_MD = OUTPUT_DIR / "case_level_delta_readme.md"

PRIMARY_MODEL = "GPT"
MODEL_ORDER = ["GPT", "Claude", "Qwen"]
CURRENT_METHOD_ORDER = [
    "spec_only",
    "spec_plus_rtl",
    "spec_rtl_raw_trace",
    "spec_rtl_trace_summary",
]
ABSTRACTED_METHOD = "spec_rtl_abstracted_trace_summary"
METHOD_LABEL = {
    "spec_only": "spec_only",
    "spec_plus_rtl": "spec+RTL",
    "spec_rtl_raw_trace": "raw_trace",
    "spec_rtl_trace_summary": "summary",
    "spec_rtl_abstracted_trace_summary": "abstracted",
}

# Higher index = lower priority. We prefer reasons that point to a more concrete failure mode
# when multiple reasons tie in frequency.
FAILURE_REASON_PRIORITY = [
    "Candidate does not compile across the evaluation benches.",
    "Flags buggy behavior but also hurts correct behavior.",
    "Antecedent triggers on buggy trace but consequent does not distinguish buggy behavior.",
    "Antecedent never triggers on buggy trace.",
    "Seen-trace success does not generalize to held-out behavior.",
    "Neither preserves correct behavior nor cleanly catches buggy behavior.",
    "Passes correct and fails buggy.",
]


def strict_success_mask(df: pd.DataFrame) -> pd.Series:
    return (
        df["heldout_correct_pass"].astype(bool)
        & df["heldout_buggy_fail"].astype(bool)
        & df["heldout_antecedent_hit"].astype(bool)
        & df["heldout_non_vacuous"].astype(bool)
    )


def choose_failure_reason(sub: pd.DataFrame) -> str:
    success_mask = strict_success_mask(sub)
    if bool(success_mask.any()):
        return "success"

    reasons = sub["failure_reason"].fillna("").astype(str).str.strip()
    reasons = reasons.loc[reasons != ""]
    if reasons.empty:
        return "no_failure_reason_recorded"

    counts = reasons.value_counts()
    best_count = int(counts.iloc[0])
    tied = [reason for reason, count in counts.items() if int(count) == best_count]
    priority = {reason: idx for idx, reason in enumerate(FAILURE_REASON_PRIORITY)}
    tied.sort(key=lambda reason: priority.get(reason, len(FAILURE_REASON_PRIORITY)))
    return tied[0]


def summarize_cell(sub: pd.DataFrame) -> dict[str, object]:
    success = bool(strict_success_mask(sub).any())
    return {
        "success": success,
        "candidate_count": int(len(sub)),
        "success_candidate_count": int(strict_success_mask(sub).sum()),
        "compile_ok_candidate_count": int(sub["compile_ok"].astype(bool).sum()),
        "failure_reason": choose_failure_reason(sub),
    }


def method_success_lookup(df: pd.DataFrame) -> dict[tuple[str, str, str], dict[str, object]]:
    lookup: dict[tuple[str, str, str], dict[str, object]] = {}
    for (model_label, case_id, method), sub in df.groupby(["model_label", "case_id", "method"], sort=False):
        lookup[(str(model_label), str(case_id), str(method))] = summarize_cell(sub)
    return lookup


def load_manifest_rows() -> pd.DataFrame:
    payload = json.loads(SCALE120_MANIFEST.read_text(encoding="utf-8"))
    rows: list[dict[str, object]] = []
    for item in payload["cases"]:
        rows.append(
            {
                "case_id": str(item["name"]),
                "bug_class": str(item.get("bug_class", "")),
                "bug_type": str(item.get("bug_type", "")),
                "source_project": str(item.get("source_project", "")),
                "source_module": str(item.get("source_module", "")),
                "seed_case_name": str(item.get("seed_case_name", "") or ""),
                "is_seed_slot": not str(item.get("seed_case_name", "") or "").strip(),
            }
        )
    return pd.DataFrame(rows)


def join_non_empty(parts: list[str]) -> str:
    return " | ".join(part for part in parts if str(part).strip())


def build_matrix_df(
    manifest_df: pd.DataFrame,
    current_lookup: dict[tuple[str, str, str], dict[str, object]],
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for case in manifest_df.itertuples(index=False):
        row: dict[str, object] = {
            "case_id": case.case_id,
            "bug_class": case.bug_class,
            "bug_type": case.bug_type,
            "source_project": case.source_project,
            "source_module": case.source_module,
            "seed_case_name": case.seed_case_name,
            "is_seed_slot": bool(case.is_seed_slot),
        }

        primary_method_success: dict[str, bool] = {}
        primary_method_reason: dict[str, str] = {}
        for method in CURRENT_METHOD_ORDER:
            cell = current_lookup.get((PRIMARY_MODEL, case.case_id, method))
            label = METHOD_LABEL[method]
            if cell is None:
                row[f"{label}_success"] = False
                row[f"{label}_failure_reason"] = "missing_current_cell"
                primary_method_success[method] = False
                primary_method_reason[method] = "missing_current_cell"
            else:
                row[f"{label}_success"] = bool(cell["success"])
                row[f"{label}_failure_reason"] = str(cell["failure_reason"])
                row[f"{label}_candidate_count"] = int(cell["candidate_count"])
                row[f"{label}_compile_ok_candidate_count"] = int(cell["compile_ok_candidate_count"])
                row[f"{label}_success_candidate_count"] = int(cell["success_candidate_count"])
                primary_method_success[method] = bool(cell["success"])
                primary_method_reason[method] = str(cell["failure_reason"])

        abstracted_cell = current_lookup.get((PRIMARY_MODEL, case.case_id, ABSTRACTED_METHOD))
        if abstracted_cell is None:
            row["abstracted_status"] = "not_run"
            row["abstracted_success"] = False
            row["abstracted_failure_reason"] = "not_run_in_scale120_full_eval"
        else:
            row["abstracted_status"] = "run"
            row["abstracted_success"] = bool(abstracted_cell["success"])
            row["abstracted_failure_reason"] = str(abstracted_cell["failure_reason"])
            row["abstracted_candidate_count"] = int(abstracted_cell["candidate_count"])
            row["abstracted_compile_ok_candidate_count"] = int(abstracted_cell["compile_ok_candidate_count"])
            row["abstracted_success_candidate_count"] = int(abstracted_cell["success_candidate_count"])

        row["raw_only_success"] = (
            primary_method_success["spec_rtl_raw_trace"]
            and not primary_method_success["spec_only"]
            and not primary_method_success["spec_plus_rtl"]
            and not primary_method_success["spec_rtl_trace_summary"]
        )
        row["summary_only_success"] = (
            primary_method_success["spec_rtl_trace_summary"]
            and not primary_method_success["spec_only"]
            and not primary_method_success["spec_plus_rtl"]
            and not primary_method_success["spec_rtl_raw_trace"]
        )
        row["rtl_hurts"] = primary_method_success["spec_only"] and not primary_method_success["spec_plus_rtl"]
        row["trace_hurts"] = primary_method_success["spec_plus_rtl"] and not (
            primary_method_success["spec_rtl_raw_trace"] or primary_method_success["spec_rtl_trace_summary"]
        )

        qwen_hurt_methods: list[str] = []
        qwen_hurt_reason_parts: list[str] = []
        for method in CURRENT_METHOD_ORDER + [ABSTRACTED_METHOD]:
            qwen_cell = current_lookup.get(("Qwen", case.case_id, method))
            gpt_cell = current_lookup.get(("GPT", case.case_id, method))
            claude_cell = current_lookup.get(("Claude", case.case_id, method))
            qwen_success = bool(qwen_cell["success"]) if qwen_cell else False
            peer_success_models = [
                model
                for model, cell in [("GPT", gpt_cell), ("Claude", claude_cell)]
                if cell is not None and bool(cell["success"])
            ]
            if peer_success_models and not qwen_success:
                label = METHOD_LABEL[method]
                qwen_hurt_methods.append(label)
                qwen_reason = str(qwen_cell["failure_reason"]) if qwen_cell else "missing_current_cell"
                qwen_hurt_reason_parts.append(
                    f"{label}:Qwen={qwen_reason};peers={','.join(peer_success_models)}"
                )
        row["qwen_hurts"] = bool(qwen_hurt_methods)
        row["qwen_hurt_methods"] = ",".join(qwen_hurt_methods)
        row["qwen_hurt_reason_detail"] = " | ".join(qwen_hurt_reason_parts)

        row["delta_categories"] = join_non_empty(
            [
                "raw_only_success" if row["raw_only_success"] else "",
                "summary_only_success" if row["summary_only_success"] else "",
                "rtl_hurts" if row["rtl_hurts"] else "",
                "trace_hurts" if row["trace_hurts"] else "",
                "qwen_hurts" if row["qwen_hurts"] else "",
            ]
        )

        row["raw_only_failure_reasons"] = (
            join_non_empty(
                [
                    f"spec_only={primary_method_reason['spec_only']}",
                    f"spec+RTL={primary_method_reason['spec_plus_rtl']}",
                    f"summary={primary_method_reason['spec_rtl_trace_summary']}",
                ]
            )
            if row["raw_only_success"]
            else ""
        )
        row["summary_only_failure_reasons"] = (
            join_non_empty(
                [
                    f"spec_only={primary_method_reason['spec_only']}",
                    f"spec+RTL={primary_method_reason['spec_plus_rtl']}",
                    f"raw={primary_method_reason['spec_rtl_raw_trace']}",
                ]
            )
            if row["summary_only_success"]
            else ""
        )
        row["rtl_hurt_failure_reason"] = (
            primary_method_reason["spec_plus_rtl"] if row["rtl_hurts"] else ""
        )
        row["trace_hurt_failure_reasons"] = (
            join_non_empty(
                [
                    f"raw={primary_method_reason['spec_rtl_raw_trace']}",
                    f"summary={primary_method_reason['spec_rtl_trace_summary']}",
                ]
            )
            if row["trace_hurts"]
            else ""
        )

        rows.append(row)

    return pd.DataFrame(rows).sort_values(["bug_class", "case_id"]).reset_index(drop=True)


def build_category_summary(matrix_df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for category in ["raw_only_success", "summary_only_success", "rtl_hurts", "trace_hurts", "qwen_hurts"]:
        sub = matrix_df.loc[matrix_df[category].astype(bool)].copy()
        rows.append(
            {
                "category": category,
                "case_count": int(len(sub)),
                "case_ids": ",".join(sub["case_id"].astype(str).tolist()),
            }
        )
        by_bug = (
            sub.groupby("bug_class", dropna=False)["case_id"]
            .count()
            .reset_index(name="case_count")
            .sort_values(["case_count", "bug_class"], ascending=[False, True])
        )
        for bug_row in by_bug.itertuples(index=False):
            rows.append(
                {
                    "category": f"{category}__bug_class",
                    "bucket": str(bug_row.bug_class),
                    "case_count": int(bug_row.case_count),
                    "case_ids": ",".join(
                        sub.loc[sub["bug_class"] == bug_row.bug_class, "case_id"].astype(str).tolist()
                    ),
                }
            )
    return pd.DataFrame(rows)


def build_category_failure_reason_df(matrix_df: pd.DataFrame) -> pd.DataFrame:
    records: list[dict[str, object]] = []

    def append_reason_counts(category_name: str, sub: pd.DataFrame, column: str) -> None:
        exploded = (
            sub[["case_id", column]]
            .assign(reason_part=sub[column].fillna("").astype(str).str.split(r"\s*\|\s*"))
            .explode("reason_part")
        )
        exploded["reason_part"] = exploded["reason_part"].fillna("").astype(str).str.strip()
        exploded = exploded.loc[exploded["reason_part"] != ""].copy()
        if exploded.empty:
            return
        if "=" in "".join(exploded["reason_part"].tolist()):
            exploded[["compared_method", "failure_reason"]] = exploded["reason_part"].str.split(
                "=", n=1, expand=True
            )
        else:
            exploded["compared_method"] = column
            exploded["failure_reason"] = exploded["reason_part"]
        grouped = (
            exploded.groupby(["compared_method", "failure_reason"], dropna=False)["case_id"]
            .agg(case_count="nunique", case_ids=lambda s: ",".join(sorted(set(s.astype(str)))))
            .reset_index()
        )
        for row in grouped.itertuples(index=False):
            records.append(
                {
                    "category": category_name,
                    "compared_method": str(row.compared_method),
                    "failure_reason": str(row.failure_reason),
                    "case_count": int(row.case_count),
                    "case_ids": str(row.case_ids),
                }
            )

    append_reason_counts(
        "raw_only_success",
        matrix_df.loc[matrix_df["raw_only_success"].astype(bool)],
        "raw_only_failure_reasons",
    )
    append_reason_counts(
        "summary_only_success",
        matrix_df.loc[matrix_df["summary_only_success"].astype(bool)],
        "summary_only_failure_reasons",
    )
    append_reason_counts(
        "rtl_hurts",
        matrix_df.loc[matrix_df["rtl_hurts"].astype(bool)],
        "rtl_hurt_failure_reason",
    )
    append_reason_counts(
        "trace_hurts",
        matrix_df.loc[matrix_df["trace_hurts"].astype(bool)],
        "trace_hurt_failure_reasons",
    )
    append_reason_counts(
        "qwen_hurts",
        matrix_df.loc[matrix_df["qwen_hurts"].astype(bool)],
        "qwen_hurt_reason_detail",
    )
    return pd.DataFrame(records).sort_values(
        ["category", "case_count", "compared_method", "failure_reason"],
        ascending=[True, False, True, True],
    )


def build_qwen_method_summary(current_lookup: dict[tuple[str, str, str], dict[str, object]], case_ids: list[str]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for case_id in case_ids:
        for method in CURRENT_METHOD_ORDER:
            qwen_cell = current_lookup.get(("Qwen", case_id, method))
            gpt_cell = current_lookup.get(("GPT", case_id, method))
            claude_cell = current_lookup.get(("Claude", case_id, method))
            qwen_success = bool(qwen_cell["success"]) if qwen_cell else False
            peer_success_models = [
                model
                for model, cell in [("GPT", gpt_cell), ("Claude", claude_cell)]
                if cell is not None and bool(cell["success"])
            ]
            if peer_success_models and not qwen_success:
                rows.append(
                    {
                        "case_id": case_id,
                        "method": METHOD_LABEL[method],
                        "qwen_failure_reason": str(qwen_cell["failure_reason"]) if qwen_cell else "missing_current_cell",
                        "peer_success_models": ",".join(peer_success_models),
                    }
                )
    return pd.DataFrame(rows).sort_values(["method", "case_id"]).reset_index(drop=True)


def write_outputs(
    matrix_df: pd.DataFrame,
    category_summary_df: pd.DataFrame,
    category_failure_reason_df: pd.DataFrame,
    qwen_method_df: pd.DataFrame,
    summary_payload: dict[str, object],
) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    matrix_df.to_csv(MATRIX_CSV, index=False, encoding="utf-8-sig")

    with pd.ExcelWriter(MATRIX_XLSX) as writer:
        matrix_df.to_excel(writer, index=False, sheet_name="case_matrix")
        category_summary_df.to_excel(writer, index=False, sheet_name="category_summary")
        category_failure_reason_df.to_excel(writer, index=False, sheet_name="failure_reasons")
        qwen_method_df.to_excel(writer, index=False, sheet_name="qwen_hurts")

    SUMMARY_JSON.write_text(json.dumps(summary_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    README_MD.write_text(
        "\n".join(
            [
                "# Case-Level Delta Matrix",
                "",
                "- Primary matrix model: `GPT`.",
                "- Success definition: `heldout_correct_pass && heldout_buggy_fail && heldout_antecedent_hit && heldout_non_vacuous`.",
                "- `raw_only_success` means `raw_trace=1` while `spec_only=0`, `spec+RTL=0`, `summary=0` on GPT.",
                "- `summary_only_success` means `summary=1` while `spec_only=0`, `spec+RTL=0`, `raw_trace=0` on GPT.",
                "- `rtl_hurts` means `spec_only=1` and `spec+RTL=0` on GPT.",
                "- `trace_hurts` means `spec+RTL=1` and both `raw_trace=0` and `summary=0` on GPT.",
                "- `qwen_hurts` means at least one method where GPT or Claude succeeds but Qwen fails on the same case/method.",
                "- `abstracted_status` becomes `run` once `spec_rtl_abstracted_trace_summary` rows exist in the scale120 full eval output.",
                "",
                f"- Matrix CSV: `{MATRIX_CSV.relative_to(ROOT)}`",
                f"- Matrix XLSX: `{MATRIX_XLSX.relative_to(ROOT)}`",
                f"- Summary JSON: `{SUMMARY_JSON.relative_to(ROOT)}`",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> None:
    current_df = pd.read_csv(CURRENT_MULTI_MODEL_RAW)
    json.loads(CURRENT_MULTI_MODEL_META.read_text(encoding="utf-8"))
    manifest_df = load_manifest_rows()
    current_lookup = method_success_lookup(current_df)

    matrix_df = build_matrix_df(manifest_df, current_lookup)
    category_summary_df = build_category_summary(matrix_df)
    category_failure_reason_df = build_category_failure_reason_df(matrix_df)
    qwen_method_df = build_qwen_method_summary(current_lookup, matrix_df["case_id"].astype(str).tolist())
    abstracted_run_case_count = int((matrix_df["abstracted_status"].astype(str) == "run").sum())
    abstracted_success_case_count = int(matrix_df.get("abstracted_success", pd.Series(dtype=bool)).astype(bool).sum())
    if abstracted_run_case_count == 0:
        abstracted_status = "not_run_in_scale120_full_eval"
    elif abstracted_run_case_count < len(matrix_df):
        abstracted_status = "partial_backfill_in_scale120_full_eval"
    else:
        abstracted_status = "backfilled_in_scale120_full_eval"

    summary_payload = {
        "primary_model": PRIMARY_MODEL,
        "success_definition": "heldout_correct_pass && heldout_buggy_fail && heldout_antecedent_hit && heldout_non_vacuous",
        "current_multi_model_raw": str(CURRENT_MULTI_MODEL_RAW.relative_to(ROOT)),
        "matrix_case_count": int(len(matrix_df)),
        "raw_only_success_case_count": int(matrix_df["raw_only_success"].astype(bool).sum()),
        "summary_only_success_case_count": int(matrix_df["summary_only_success"].astype(bool).sum()),
        "rtl_hurts_case_count": int(matrix_df["rtl_hurts"].astype(bool).sum()),
        "trace_hurts_case_count": int(matrix_df["trace_hurts"].astype(bool).sum()),
        "qwen_hurts_case_count": int(matrix_df["qwen_hurts"].astype(bool).sum()),
        "abstracted_current_status": abstracted_status,
        "abstracted_run_case_count": abstracted_run_case_count,
        "abstracted_success_case_count": abstracted_success_case_count,
    }
    write_outputs(
        matrix_df=matrix_df,
        category_summary_df=category_summary_df,
        category_failure_reason_df=category_failure_reason_df,
        qwen_method_df=qwen_method_df,
        summary_payload=summary_payload,
    )
    print(MATRIX_CSV)
    print(MATRIX_XLSX)
    print(SUMMARY_JSON)


if __name__ == "__main__":
    main()
