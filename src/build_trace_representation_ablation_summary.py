from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = ROOT / "outputs" / "scale120_trace_representation_ablation_data"
MANIFEST_JSON = ROOT / "rtl_cases_real_scale120" / "case_manifest.json"
DEFAULT_OUT_DIR = ROOT / "generated_main_results_strict_success"

MODEL_ORDER = ["GPT", "Claude"]
METHOD_ORDER = [
    "spec_rtl_raw_trace",
    "spec_rtl_naive_summary",
    "spec_rtl_event_abstraction",
    "spec_rtl_temporal_relation_abstraction",
]
METHOD_SHORT = {
    "spec_rtl_raw_trace": "raw_trace",
    "spec_rtl_naive_summary": "naive_summary",
    "spec_rtl_event_abstraction": "event_abstraction",
    "spec_rtl_temporal_relation_abstraction": "temporal_relation",
}
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
    if bool(strict_success_mask(sub).any()):
        return "success"
    reasons = sub["failure_reason"].fillna("").astype(str).str.strip()
    reasons = reasons.loc[reasons != ""]
    if reasons.empty:
        return "no_failure_reason_recorded"
    counts = reasons.value_counts()
    top_count = int(counts.iloc[0])
    tied = [reason for reason, count in counts.items() if int(count) == top_count]
    priority = {reason: idx for idx, reason in enumerate(FAILURE_REASON_PRIORITY)}
    tied.sort(key=lambda reason: priority.get(reason, len(FAILURE_REASON_PRIORITY)))
    return tied[0]


def load_manifest_df() -> pd.DataFrame:
    payload = json.loads(MANIFEST_JSON.read_text(encoding="utf-8"))
    rows = []
    for case in payload["cases"]:
        rows.append(
            {
                "case_id": str(case["name"]),
                "bug_class": str(case.get("bug_class", "")),
                "bug_type": str(case.get("bug_type", "")),
                "source_project": str(case.get("source_project", "")),
                "source_module": str(case.get("source_module", "")),
            }
        )
    return pd.DataFrame(rows)


def summarize_cell(sub: pd.DataFrame) -> dict[str, object]:
    success_mask = strict_success_mask(sub)
    return {
        "success": bool(success_mask.any()),
        "success_candidate_count": int(success_mask.sum()),
        "candidate_count": int(len(sub)),
        "compile_ok_candidate_count": int(sub["compile_ok"].astype(bool).sum()),
        "failure_reason": choose_failure_reason(sub),
    }


def build_cell_lookup(raw_df: pd.DataFrame) -> dict[tuple[str, str, str], dict[str, object]]:
    lookup: dict[tuple[str, str, str], dict[str, object]] = {}
    for (model_label, case_id, method), sub in raw_df.groupby(["model_label", "case_id", "method"], sort=False):
        lookup[(str(model_label), str(case_id), str(method))] = summarize_cell(sub)
    return lookup


def build_prompt_lookup(prompt_df: pd.DataFrame) -> dict[tuple[str, str, str], dict[str, object]]:
    lookup: dict[tuple[str, str, str], dict[str, object]] = {}
    for (model_label, case_id, method), sub in prompt_df.groupby(["model_label", "case_id", "method"], sort=False):
        row = sub.iloc[-1]
        lookup[(str(model_label), str(case_id), str(method))] = {
            "trace_representation_char_count": int(row.get("trace_representation_char_count", 0) or 0),
            "trace_representation_line_count": int(row.get("trace_representation_line_count", 0) or 0),
        }
    return lookup


def build_method_summary(raw_df: pd.DataFrame, prompt_lookup: dict[tuple[str, str, str], dict[str, object]]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for model_label in MODEL_ORDER:
        model_df = raw_df.loc[raw_df["model_label"].astype(str) == model_label].copy()
        if model_df.empty:
            continue
        for method in METHOD_ORDER:
            sub = model_df.loc[model_df["method"].astype(str) == method].copy()
            if sub.empty:
                continue
            strict_mask = strict_success_mask(sub)
            case_success_rate = float(
                sub.assign(strict_success=strict_mask)
                .groupby("case_id", dropna=False)["strict_success"]
                .any()
                .mean()
            )
            prompt_sizes = [
                prompt_lookup[(model_label, str(case_id), method)]
                for case_id in sorted(sub["case_id"].astype(str).unique())
                if (model_label, str(case_id), method) in prompt_lookup
            ]
            rows.append(
                {
                    "model_label": model_label,
                    "method": method,
                    "method_label": METHOD_SHORT[method],
                    "candidate_count": int(len(sub)),
                    "case_count": int(sub["case_id"].nunique()),
                    "compile_ok_rate": float(sub["compile_ok"].astype(bool).mean()),
                    "heldout_correct_pass_rate": float(sub["heldout_correct_pass"].astype(bool).mean()),
                    "heldout_buggy_fail_rate": float(sub["heldout_buggy_fail"].astype(bool).mean()),
                    "heldout_antecedent_hit_rate": float(sub["heldout_antecedent_hit"].astype(bool).mean()),
                    "strict_success_rate": float(strict_mask.mean()),
                    "case_strict_success_rate": case_success_rate,
                    "overfit_suspect_rate": float((sub["failure_mode"] == "overfit_suspect").mean()),
                    "too_strong_rate": float((sub["failure_mode"] == "too_strong").mean()),
                    "too_weak_rate": float((sub["failure_mode"] == "too_weak").mean()),
                    "vacuity_rate": float((sub["failure_mode"] == "vacuity").mean()),
                    "compile_fail_rate": float((sub["failure_mode"] == "compile_fail").mean()),
                    "avg_trace_representation_char_count": (
                        sum(item["trace_representation_char_count"] for item in prompt_sizes) / len(prompt_sizes)
                        if prompt_sizes
                        else 0.0
                    ),
                    "avg_trace_representation_line_count": (
                        sum(item["trace_representation_line_count"] for item in prompt_sizes) / len(prompt_sizes)
                        if prompt_sizes
                        else 0.0
                    ),
                }
            )
    return pd.DataFrame(rows)


def build_case_matrix(
    manifest_df: pd.DataFrame,
    cell_lookup: dict[tuple[str, str, str], dict[str, object]],
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for case in manifest_df.itertuples(index=False):
        row: dict[str, object] = {
            "case_id": case.case_id,
            "bug_class": case.bug_class,
            "bug_type": case.bug_type,
            "source_project": case.source_project,
            "source_module": case.source_module,
        }
        for model_label in MODEL_ORDER:
            success_map: dict[str, bool] = {}
            reason_map: dict[str, str] = {}
            for method in METHOD_ORDER:
                cell = cell_lookup.get((model_label, case.case_id, method))
                short = METHOD_SHORT[method]
                if cell is None:
                    row[f"{model_label}_{short}_success"] = False
                    row[f"{model_label}_{short}_failure_reason"] = "missing_cell"
                    success_map[method] = False
                    reason_map[method] = "missing_cell"
                else:
                    row[f"{model_label}_{short}_success"] = bool(cell["success"])
                    row[f"{model_label}_{short}_failure_reason"] = str(cell["failure_reason"])
                    success_map[method] = bool(cell["success"])
                    reason_map[method] = str(cell["failure_reason"])

            raw = success_map["spec_rtl_raw_trace"]
            naive = success_map["spec_rtl_naive_summary"]
            event = success_map["spec_rtl_event_abstraction"]
            temporal = success_map["spec_rtl_temporal_relation_abstraction"]

            row[f"{model_label}_raw_only_success"] = raw and not naive and not event and not temporal
            row[f"{model_label}_naive_only_success"] = naive and not raw and not event and not temporal
            row[f"{model_label}_event_only_success"] = event and not raw and not naive and not temporal
            row[f"{model_label}_temporal_only_success"] = temporal and not raw and not naive and not event
            row[f"{model_label}_raw_beats_naive"] = raw and not naive
            row[f"{model_label}_event_beats_naive"] = event and not naive
            row[f"{model_label}_temporal_beats_event"] = temporal and not event
            row[f"{model_label}_temporal_beats_raw"] = temporal and not raw
            row[f"{model_label}_raw_beats_temporal"] = raw and not temporal
            row[f"{model_label}_temporal_hurts_vs_naive"] = naive and not temporal
            row[f"{model_label}_temporal_hurts_vs_event"] = event and not temporal
            row[f"{model_label}_raw_only_reason"] = reason_map["spec_rtl_raw_trace"] if row[f"{model_label}_raw_only_success"] else ""
            row[f"{model_label}_naive_only_reason"] = reason_map["spec_rtl_naive_summary"] if row[f"{model_label}_naive_only_success"] else ""
            row[f"{model_label}_event_only_reason"] = reason_map["spec_rtl_event_abstraction"] if row[f"{model_label}_event_only_success"] else ""
            row[f"{model_label}_temporal_only_reason"] = (
                reason_map["spec_rtl_temporal_relation_abstraction"]
                if row[f"{model_label}_temporal_only_success"]
                else ""
            )
            row[f"{model_label}_raw_missing_reason"] = reason_map["spec_rtl_raw_trace"] if not raw else ""
            row[f"{model_label}_naive_missing_reason"] = reason_map["spec_rtl_naive_summary"] if not naive else ""
            row[f"{model_label}_event_missing_reason"] = reason_map["spec_rtl_event_abstraction"] if not event else ""
            row[f"{model_label}_temporal_missing_reason"] = (
                reason_map["spec_rtl_temporal_relation_abstraction"] if not temporal else ""
            )
        rows.append(row)
    return pd.DataFrame(rows).sort_values(["bug_class", "case_id"]).reset_index(drop=True)


def build_failure_reason_breakdown(case_matrix_df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    categories = [
        ("raw_only_success", "raw_missing_reason"),
        ("naive_only_success", "naive_missing_reason"),
        ("event_only_success", "event_missing_reason"),
        ("temporal_only_success", "temporal_missing_reason"),
        ("raw_beats_naive", "naive_missing_reason"),
        ("event_beats_naive", "naive_missing_reason"),
        ("temporal_beats_event", "event_missing_reason"),
        ("temporal_beats_raw", "raw_missing_reason"),
        ("raw_beats_temporal", "temporal_missing_reason"),
        ("temporal_hurts_vs_naive", "temporal_missing_reason"),
        ("temporal_hurts_vs_event", "temporal_missing_reason"),
    ]
    for model_label in MODEL_ORDER:
        for category_key, reason_suffix in categories:
            flag_col = f"{model_label}_{category_key}"
            reason_col = f"{model_label}_{reason_suffix}"
            sub = case_matrix_df.loc[case_matrix_df[flag_col].astype(bool)].copy()
            if sub.empty:
                continue
            grouped = (
                sub.groupby(["bug_class", reason_col], dropna=False)["case_id"]
                .agg(case_count="nunique", case_ids=lambda s: ",".join(sorted(set(s.astype(str)))))
                .reset_index()
                .rename(columns={reason_col: "failure_reason"})
                .sort_values(["case_count", "bug_class", "failure_reason"], ascending=[False, True, True])
            )
            for row in grouped.itertuples(index=False):
                rows.append(
                    {
                        "model_label": model_label,
                        "category": category_key,
                        "bug_class": str(row.bug_class),
                        "failure_reason": str(row.failure_reason),
                        "case_count": int(row.case_count),
                        "case_ids": str(row.case_ids),
                    }
                )
    return pd.DataFrame(rows)


def build_summary_payload(
    case_matrix_df: pd.DataFrame,
    method_summary_df: pd.DataFrame,
    *,
    data_dir: Path,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "success_definition": "heldout_correct_pass && heldout_buggy_fail && heldout_antecedent_hit && heldout_non_vacuous",
        "data_dir": str(data_dir.relative_to(ROOT) if data_dir.is_relative_to(ROOT) else data_dir),
        "case_count": int(len(case_matrix_df)),
        "bug_class_counts": {
            str(k): int(v) for k, v in case_matrix_df["bug_class"].value_counts().sort_index().items()
        },
        "models": {},
    }
    for model_label in MODEL_ORDER:
        method_rows = method_summary_df.loc[method_summary_df["model_label"] == model_label].copy()
        if method_rows.empty:
            continue
        bug_class_payload: dict[str, dict[str, int]] = {}
        for bug_class in sorted(case_matrix_df["bug_class"].astype(str).unique()):
            sub = case_matrix_df.loc[case_matrix_df["bug_class"].astype(str) == bug_class].copy()
            bug_class_payload[bug_class] = {
                "raw_beats_naive_case_count": int(sub[f"{model_label}_raw_beats_naive"].astype(bool).sum()),
                "event_beats_naive_case_count": int(sub[f"{model_label}_event_beats_naive"].astype(bool).sum()),
                "temporal_beats_event_case_count": int(sub[f"{model_label}_temporal_beats_event"].astype(bool).sum()),
                "temporal_beats_raw_case_count": int(sub[f"{model_label}_temporal_beats_raw"].astype(bool).sum()),
                "raw_beats_temporal_case_count": int(sub[f"{model_label}_raw_beats_temporal"].astype(bool).sum()),
            }

        model_payload = {
            "raw_only_success_case_count": int(case_matrix_df[f"{model_label}_raw_only_success"].astype(bool).sum()),
            "naive_only_success_case_count": int(case_matrix_df[f"{model_label}_naive_only_success"].astype(bool).sum()),
            "event_only_success_case_count": int(case_matrix_df[f"{model_label}_event_only_success"].astype(bool).sum()),
            "temporal_only_success_case_count": int(case_matrix_df[f"{model_label}_temporal_only_success"].astype(bool).sum()),
            "raw_beats_naive_case_count": int(case_matrix_df[f"{model_label}_raw_beats_naive"].astype(bool).sum()),
            "event_beats_naive_case_count": int(case_matrix_df[f"{model_label}_event_beats_naive"].astype(bool).sum()),
            "temporal_beats_event_case_count": int(case_matrix_df[f"{model_label}_temporal_beats_event"].astype(bool).sum()),
            "temporal_beats_raw_case_count": int(case_matrix_df[f"{model_label}_temporal_beats_raw"].astype(bool).sum()),
            "raw_beats_temporal_case_count": int(case_matrix_df[f"{model_label}_raw_beats_temporal"].astype(bool).sum()),
            "temporal_hurts_vs_naive_case_count": int(case_matrix_df[f"{model_label}_temporal_hurts_vs_naive"].astype(bool).sum()),
            "temporal_hurts_vs_event_case_count": int(case_matrix_df[f"{model_label}_temporal_hurts_vs_event"].astype(bool).sum()),
            "method_case_strict_success_rate": {
                str(row.method): float(row.case_strict_success_rate)
                for row in method_rows.itertuples(index=False)
            },
            "by_bug_class": bug_class_payload,
        }
        payload["models"][model_label] = model_payload
    return payload


def write_outputs(
    method_summary_df: pd.DataFrame,
    case_matrix_df: pd.DataFrame,
    failure_reason_df: pd.DataFrame,
    summary_payload: dict[str, object],
    *,
    out_dir: Path,
) -> dict[str, Path]:
    method_summary_csv = out_dir / "trace_representation_ablation_method_summary.csv"
    case_matrix_csv = out_dir / "trace_representation_ablation_case_matrix.csv"
    failure_reason_csv = out_dir / "trace_representation_ablation_failure_reasons.csv"
    summary_json = out_dir / "trace_representation_ablation_summary.json"
    out_xlsx = out_dir / "trace_representation_ablation_summary.xlsx"
    readme_md = out_dir / "trace_representation_ablation_readme.md"

    out_dir.mkdir(parents=True, exist_ok=True)
    method_summary_df.to_csv(method_summary_csv, index=False, encoding="utf-8-sig")
    case_matrix_df.to_csv(case_matrix_csv, index=False, encoding="utf-8-sig")
    failure_reason_df.to_csv(failure_reason_csv, index=False, encoding="utf-8-sig")
    summary_json.write_text(json.dumps(summary_payload, indent=2, ensure_ascii=False), encoding="utf-8")

    with pd.ExcelWriter(out_xlsx) as writer:
        method_summary_df.to_excel(writer, index=False, sheet_name="method_summary")
        case_matrix_df.to_excel(writer, index=False, sheet_name="case_matrix")
        failure_reason_df.to_excel(writer, index=False, sheet_name="failure_reasons")

    readme_md.write_text(
        "\n".join(
            [
                "# Trace Representation Ablation Summary",
                "",
                "- Models: `GPT`, `Claude`.",
                "- Methods: `raw_trace`, `naive_summary`, `event_abstraction`, `temporal_relation_abstraction`.",
                "- Success definition: `heldout_correct_pass && heldout_buggy_fail && heldout_antecedent_hit && heldout_non_vacuous`.",
                "- `raw_beats_naive` means `raw_trace=1` and `naive_summary=0` for the same model/case.",
                "- `temporal_beats_event` isolates cases where explicit temporal-relation abstraction adds value beyond event-level phrasing.",
                "- `temporal_beats_raw` isolates cases where abstract temporal structure beats literal trace evidence.",
                "",
                f"- Method summary CSV: `{method_summary_csv.relative_to(ROOT) if method_summary_csv.is_relative_to(ROOT) else method_summary_csv}`",
                f"- Case matrix CSV: `{case_matrix_csv.relative_to(ROOT) if case_matrix_csv.is_relative_to(ROOT) else case_matrix_csv}`",
                f"- Failure reason CSV: `{failure_reason_csv.relative_to(ROOT) if failure_reason_csv.is_relative_to(ROOT) else failure_reason_csv}`",
                f"- XLSX workbook: `{out_xlsx.relative_to(ROOT) if out_xlsx.is_relative_to(ROOT) else out_xlsx}`",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    return {
        "method_summary_csv": method_summary_csv,
        "case_matrix_csv": case_matrix_csv,
        "failure_reason_csv": failure_reason_csv,
        "summary_json": summary_json,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build summary tables for the trace representation ablation run.")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help="Directory containing multi_model_results_raw.csv and multi_model_prompt_log.csv",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_OUT_DIR,
        help="Directory to write summary CSV/XLSX/JSON outputs",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    data_dir = args.data_dir.resolve()
    out_dir = args.out_dir.resolve()
    raw_csv = data_dir / "multi_model_results_raw.csv"
    prompt_csv = data_dir / "multi_model_prompt_log.csv"

    raw_df = pd.read_csv(raw_csv)
    prompt_df = pd.read_csv(prompt_csv)
    manifest_df = load_manifest_df()
    cell_lookup = build_cell_lookup(raw_df)
    prompt_lookup = build_prompt_lookup(prompt_df)
    method_summary_df = build_method_summary(raw_df, prompt_lookup)
    case_matrix_df = build_case_matrix(manifest_df, cell_lookup)
    failure_reason_df = build_failure_reason_breakdown(case_matrix_df)
    summary_payload = build_summary_payload(case_matrix_df, method_summary_df, data_dir=data_dir)
    written_paths = write_outputs(
        method_summary_df=method_summary_df,
        case_matrix_df=case_matrix_df,
        failure_reason_df=failure_reason_df,
        summary_payload=summary_payload,
        out_dir=out_dir,
    )
    print(written_paths["method_summary_csv"])
    print(written_paths["case_matrix_csv"])
    print(written_paths["failure_reason_csv"])
    print(written_paths["summary_json"])


if __name__ == "__main__":
    main()
