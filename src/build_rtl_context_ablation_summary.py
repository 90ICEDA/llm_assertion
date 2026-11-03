from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = ROOT / "outputs" / "scale120_rtl_context_ablation_data"
MANIFEST_JSON = ROOT / "rtl_cases_real_scale120" / "case_manifest.json"

DEFAULT_OUT_DIR = ROOT / "generated_main_results_strict_success"

MODEL_ORDER = ["GPT", "Claude"]
METHOD_ORDER = [
    "spec_only",
    "spec_rtl_full",
    "spec_rtl_interface",
    "spec_rtl_signal_list",
    "spec_rtl_sliced",
    "spec_rtl_signal_list_small_slice",
]
METHOD_SHORT = {
    "spec_only": "spec_only",
    "spec_rtl_full": "full_rtl",
    "spec_rtl_interface": "interface",
    "spec_rtl_signal_list": "signal_list",
    "spec_rtl_sliced": "sliced_rtl",
    "spec_rtl_signal_list_small_slice": "signal_list_small_slice",
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
            "rtl_context_char_count": int(row.get("rtl_context_char_count", 0) or 0),
            "rtl_context_line_count": int(row.get("rtl_context_line_count", 0) or 0),
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
                    "avg_rtl_context_char_count": (
                        sum(item["rtl_context_char_count"] for item in prompt_sizes) / len(prompt_sizes)
                        if prompt_sizes
                        else 0.0
                    ),
                    "avg_rtl_context_line_count": (
                        sum(item["rtl_context_line_count"] for item in prompt_sizes) / len(prompt_sizes)
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

            full_rtl_hurts = success_map["spec_only"] and not success_map["spec_rtl_full"]
            interface_recovers = full_rtl_hurts and success_map["spec_rtl_interface"]
            signal_list_recovers = full_rtl_hurts and success_map["spec_rtl_signal_list"]
            sliced_rtl_recovers = full_rtl_hurts and success_map["spec_rtl_sliced"]
            signal_list_small_slice_recovers = full_rtl_hurts and success_map["spec_rtl_signal_list_small_slice"]
            all_lightweight_fail = full_rtl_hurts and not (
                success_map["spec_rtl_interface"]
                or success_map["spec_rtl_signal_list"]
                or success_map["spec_rtl_sliced"]
                or success_map["spec_rtl_signal_list_small_slice"]
            )

            row[f"{model_label}_full_rtl_hurts"] = full_rtl_hurts
            row[f"{model_label}_interface_recovers"] = interface_recovers
            row[f"{model_label}_signal_list_recovers"] = signal_list_recovers
            row[f"{model_label}_sliced_rtl_recovers"] = sliced_rtl_recovers
            row[f"{model_label}_signal_list_small_slice_recovers"] = signal_list_small_slice_recovers
            row[f"{model_label}_all_lightweight_fail"] = all_lightweight_fail
            row[f"{model_label}_full_rtl_hurt_reason"] = (
                reason_map["spec_rtl_full"] if full_rtl_hurts else ""
            )
            row[f"{model_label}_recovery_tags"] = ",".join(
                [
                    tag
                    for tag, enabled in [
                        ("interface", interface_recovers),
                        ("signal_list", signal_list_recovers),
                        ("sliced_rtl", sliced_rtl_recovers),
                        ("signal_list_small_slice", signal_list_small_slice_recovers),
                    ]
                    if enabled
                ]
            )
        rows.append(row)
    return pd.DataFrame(rows).sort_values(["bug_class", "case_id"]).reset_index(drop=True)


def build_failure_reason_breakdown(case_matrix_df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    categories = [
        ("full_rtl_hurts", "full_rtl_hurts"),
        ("interface_recovers", "interface_recovers"),
        ("signal_list_recovers", "signal_list_recovers"),
        ("sliced_rtl_recovers", "sliced_rtl_recovers"),
        ("signal_list_small_slice_recovers", "signal_list_small_slice_recovers"),
        ("all_lightweight_fail", "all_lightweight_fail"),
    ]
    for model_label in MODEL_ORDER:
        reason_col = f"{model_label}_full_rtl_hurt_reason"
        for category_key, suffix in categories:
            flag_col = f"{model_label}_{suffix}"
            sub = case_matrix_df.loc[case_matrix_df[flag_col].astype(bool)].copy()
            if sub.empty:
                continue
            grouped = (
                sub.groupby(reason_col, dropna=False)["case_id"]
                .agg(case_count="nunique", case_ids=lambda s: ",".join(sorted(set(s.astype(str)))))
                .reset_index()
                .rename(columns={reason_col: "failure_reason"})
                .sort_values(["case_count", "failure_reason"], ascending=[False, True])
            )
            for row in grouped.itertuples(index=False):
                rows.append(
                    {
                        "model_label": model_label,
                        "category": category_key,
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
        "models": {},
    }
    for model_label in MODEL_ORDER:
        method_rows = method_summary_df.loc[method_summary_df["model_label"] == model_label].copy()
        if method_rows.empty:
            continue
        model_payload = {
            "full_rtl_hurts_case_count": int(case_matrix_df[f"{model_label}_full_rtl_hurts"].astype(bool).sum()),
            "interface_recovers_case_count": int(case_matrix_df[f"{model_label}_interface_recovers"].astype(bool).sum()),
            "signal_list_recovers_case_count": int(case_matrix_df[f"{model_label}_signal_list_recovers"].astype(bool).sum()),
            "sliced_rtl_recovers_case_count": int(case_matrix_df[f"{model_label}_sliced_rtl_recovers"].astype(bool).sum()),
            "signal_list_small_slice_recovers_case_count": int(case_matrix_df[f"{model_label}_signal_list_small_slice_recovers"].astype(bool).sum()),
            "all_lightweight_fail_case_count": int(case_matrix_df[f"{model_label}_all_lightweight_fail"].astype(bool).sum()),
            "method_case_strict_success_rate": {
                str(row.method): float(row.case_strict_success_rate)
                for row in method_rows.itertuples(index=False)
            },
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
) -> None:
    method_summary_csv = out_dir / "rtl_context_ablation_method_summary.csv"
    case_matrix_csv = out_dir / "rtl_context_ablation_case_matrix.csv"
    failure_reason_csv = out_dir / "rtl_context_ablation_failure_reasons.csv"
    summary_json = out_dir / "rtl_context_ablation_summary.json"
    out_xlsx = out_dir / "rtl_context_ablation_summary.xlsx"
    readme_md = out_dir / "rtl_context_ablation_readme.md"

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
                "# RTL Context Ablation Summary",
                "",
                "- Models: `GPT`, `Claude`.",
                "- Methods: `spec_only`, `spec_rtl_full`, `spec_rtl_interface`, `spec_rtl_signal_list`, `spec_rtl_sliced`, `spec_rtl_signal_list_small_slice`.",
                "- Success definition: `heldout_correct_pass && heldout_buggy_fail && heldout_antecedent_hit && heldout_non_vacuous`.",
                "- `full_rtl_hurts` means `spec_only=1` and `full_rtl=0` for the same model/case.",
                "- Recovery tags show whether `interface`, `signal_list`, `sliced_rtl`, or automatic `signal_list_small_slice` succeeds on a `full_rtl_hurts` case.",
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
    parser = argparse.ArgumentParser(description="Build summary tables for the RTL context ablation run.")
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
