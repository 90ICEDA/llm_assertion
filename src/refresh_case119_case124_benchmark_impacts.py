from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Any

import pandas as pd

SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from run_trace_abstraction_prototype import (  # noqa: E402
    CASES_ROOT,
    parse_allowed_signals,
    read_text,
    run_case_eval,
)


ROOT = Path(__file__).resolve().parents[1]
THREAD_ID = "019ed9f6-87cf-7830-adb8-595fe2ae140d"
OUTPUT_ROOT = ROOT / "outputs" / THREAD_ID

STRICT_REPORT = ROOT / "rtl_cases_real_admitted_20260619" / "strict_eval_report_iv12.csv"
TRACE_ABS_RAW = OUTPUT_ROOT / "trace_abstraction_data" / "trace_abstraction_results_raw.csv"
TRACE_ABS_SUMMARY = OUTPUT_ROOT / "trace_abstraction_data" / "trace_abstraction_summary.csv"
ANT_REPAIR_CAND = OUTPUT_ROOT / "antecedent_repair_data" / "antecedent_repair_candidate_results.csv"
ANT_REPAIR_CASE = OUTPUT_ROOT / "antecedent_repair_data" / "antecedent_repair_case_summary.csv"
PROMPT_ABL_RAW = OUTPUT_ROOT / "prompt_ablation_data" / "prompt_ablation_results_raw.csv"
PROMPT_ABL_SUMMARY = OUTPUT_ROOT / "prompt_ablation_data" / "prompt_ablation_summary_by_prompt.csv"
PROMPT_ABL_CASE_SUMMARY = OUTPUT_ROOT / "prompt_ablation_data" / "prompt_ablation_case_prompt_summary.csv"
TRACESEL_RAW = OUTPUT_ROOT / "trace_selection_data" / "high_vs_low_quality_trace_results_raw.csv"
TRACESEL_SUMMARY = OUTPUT_ROOT / "trace_selection_data" / "high_vs_low_quality_trace_summary.csv"
TRACESEL_COMPARISON = OUTPUT_ROOT / "trace_selection_data" / "high_vs_low_quality_case_comparison.csv"

CASE119 = "case119_prim_filter_ctr_late_accept"
CASE124 = "case124_prim_fifo_clear_ignored"
TARGET_CASES = {CASE119, CASE124}

PROMPT_FILE_MAP = {
    "spec_only": "prompt_1_spec_only.txt",
    "spec_plus_rtl": "prompt_2_spec_plus_rtl.txt",
    "spec_rtl_raw_trace": "prompt_3_spec_rtl_raw_trace.txt",
    "spec_rtl_trace_summary": "prompt_4_spec_rtl_trace_summary.txt",
}


def is_true(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, float) and math.isnan(value):
        return False
    return str(value).strip().lower() in {"true", "1", "yes"}


def prompt_signal_names(case_id: str, method: str) -> list[str]:
    prompt_file = CASES_ROOT / case_id / "experiment" / "prompts" / PROMPT_FILE_MAP[method]
    return parse_allowed_signals(read_text(prompt_file))


def blank_if_false(flag: bool, text: str) -> str:
    return text if flag else ""


def safe_eval(
    *,
    case_id: str,
    assertion_text: str,
    signal_names: list[str],
    use_property: bool,
    runtime_dir: Path,
) -> dict[str, Any]:
    try:
        return run_case_eval(
            case_id=case_id,
            assertion_text=assertion_text,
            signal_names=signal_names,
            use_property=use_property,
            runtime_dir=runtime_dir,
        )
    except Exception as exc:  # pragma: no cover - recovery path
        return {
            "compile_ok": False,
            "correct_pass": False,
            "buggy_fail": False,
            "antecedent_hit": False,
            "non_vacuous": False,
            "heldout_correct_pass": False,
            "heldout_buggy_fail": False,
            "heldout_antecedent_hit": False,
            "heldout_non_vacuous": False,
            "trace_overfit": False,
            "seen_good_ant_hits": 0,
            "seen_bad_ant_hits": 0,
            "heldout_good_ant_hits": 0,
            "heldout_bad_ant_hits": 0,
            "seen_good_fail_hits": 0,
            "seen_bad_fail_hits": 0,
            "heldout_good_fail_hits": 0,
            "heldout_bad_fail_hits": 0,
            "compile_stderr_seen_good": str(exc),
            "compile_stderr_seen_bad": str(exc),
            "compile_stderr_holdout_good": str(exc),
            "compile_stderr_holdout_bad": str(exc),
            "sim_stdout_seen_good": "",
            "sim_stdout_seen_bad": "",
            "sim_stdout_holdout_good": "",
            "sim_stdout_holdout_bad": "",
        }


def eval_reason(eval_result: dict[str, Any]) -> str:
    reasons: list[str] = []
    if not eval_result["heldout_correct_pass"]:
        reasons.append("heldout_correct_failed")
    if not eval_result["heldout_buggy_fail"]:
        reasons.append("heldout_buggy_not_detected")
    if not eval_result["heldout_antecedent_hit"]:
        reasons.append("heldout_antecedent_not_triggered")
    return "; ".join(reasons)


def classify_failure_type(row: pd.Series) -> str:
    if str(row.get("failure_type", "")) == "template_mismatch":
        return "template_mismatch"
    if not is_true(row.get("analysis_supported", True)):
        return str(row.get("failure_type", "")) or "template_mismatch"
    if not is_true(row.get("compile_ok", False)):
        return "compile_fail"
    if is_true(row.get("trace_overfit", False)):
        return "trace_overfit"
    if not is_true(row.get("pass_on_correct", False)):
        return "false_positive_on_correct"
    if not is_true(row.get("antecedent_triggered", False)):
        return "antecedent_not_triggered"
    if not is_true(row.get("fail_on_buggy", False)):
        return "bug_not_detected_on_buggy"
    if not is_true(row.get("heldout_antecedent_triggered", False)):
        return "vacuous"
    return "semantic_unreviewed"


def strict_success_flag(row: pd.Series) -> bool:
    semantic_ok = is_true(row.get("semantic_reasonable", False))
    return bool(
        is_true(row.get("compile_ok"))
        and is_true(row.get("pass_on_correct"))
        and is_true(row.get("fail_on_buggy"))
        and is_true(row.get("antecedent_triggered"))
        and is_true(row.get("heldout_compile_ok"))
        and is_true(row.get("heldout_pass_on_correct"))
        and is_true(row.get("heldout_fail_on_buggy"))
        and is_true(row.get("heldout_antecedent_triggered"))
        and semantic_ok
    )


def refresh_strict_report() -> None:
    df = pd.read_csv(STRICT_REPORT)
    signal_cache = {case_id: {} for case_id in TARGET_CASES}

    for idx, row in df.iterrows():
        case_id = str(row["case_name"])
        if case_id not in TARGET_CASES:
            continue
        if not is_true(row.get("analysis_supported", True)):
            continue
        assertion_text = str(row.get("assertion_line", "") or "").strip()
        if not assertion_text:
            continue
        method = str(row["method"])
        if method not in signal_cache[case_id]:
            signal_cache[case_id][method] = prompt_signal_names(case_id, method)
        eval_result = safe_eval(
            case_id=case_id,
            assertion_text=assertion_text,
            signal_names=signal_cache[case_id][method],
            use_property=False,
            runtime_dir=OUTPUT_ROOT / "_refresh_runtime" / "strict_report" / case_id / method / f"cand_{int(row['candidate_index']):02d}",
        )
        df.at[idx, "compile_ok"] = bool(eval_result["compile_ok"])
        df.at[idx, "pass_on_correct"] = bool(eval_result["correct_pass"])
        df.at[idx, "fail_on_buggy"] = bool(eval_result["buggy_fail"])
        df.at[idx, "non_vacuous"] = bool(eval_result["non_vacuous"])
        df.at[idx, "antecedent_triggered"] = bool(eval_result["antecedent_hit"])
        df.at[idx, "correct_antecedent_hits"] = int(eval_result["seen_good_ant_hits"])
        df.at[idx, "buggy_antecedent_hits"] = int(eval_result["seen_bad_ant_hits"])
        df.at[idx, "correct_fail_count"] = int(eval_result["seen_good_fail_hits"])
        df.at[idx, "buggy_fail_count"] = int(eval_result["seen_bad_fail_hits"])
        df.at[idx, "heldout_compile_ok"] = bool(eval_result["compile_ok"])
        df.at[idx, "heldout_pass_on_correct"] = bool(eval_result["heldout_correct_pass"])
        df.at[idx, "heldout_fail_on_buggy"] = bool(eval_result["heldout_buggy_fail"])
        df.at[idx, "heldout_non_vacuous"] = bool(eval_result["heldout_non_vacuous"])
        df.at[idx, "heldout_antecedent_triggered"] = bool(eval_result["heldout_antecedent_hit"])
        df.at[idx, "heldout_correct_antecedent_hits"] = int(eval_result["heldout_good_ant_hits"])
        df.at[idx, "heldout_buggy_antecedent_hits"] = int(eval_result["heldout_bad_ant_hits"])
        df.at[idx, "heldout_correct_fail_count"] = int(eval_result["heldout_good_fail_hits"])
        df.at[idx, "heldout_buggy_fail_count"] = int(eval_result["heldout_bad_fail_hits"])
        df.at[idx, "heldout_compile_error"] = "" if bool(eval_result["compile_ok"]) else str(
            eval_result.get("compile_stderr_holdout_bad", "") or row.get("heldout_compile_error", "") or ""
        )
        df.at[idx, "trace_overfit"] = bool(eval_result["trace_overfit"])
        df.at[idx, "trace_overfit_reason"] = blank_if_false(bool(eval_result["trace_overfit"]), eval_reason(eval_result))

    df["failure_type"] = df.apply(classify_failure_type, axis=1)
    df["strict_success"] = df.apply(strict_success_flag, axis=1)
    df.to_csv(STRICT_REPORT, index=False, encoding="utf-8-sig")


def refresh_trace_abstraction_raw() -> None:
    df = pd.read_csv(TRACE_ABS_RAW)
    signal_names = prompt_signal_names(CASE124, "spec_rtl_raw_trace")
    for idx, row in df[df["case_id"] == CASE124].iterrows():
        eval_result = safe_eval(
            case_id=CASE124,
            assertion_text=str(row["assertion_text"]),
            signal_names=signal_names,
            use_property=is_true(row.get("use_property_compile_mode", False)),
            runtime_dir=OUTPUT_ROOT / "_refresh_runtime" / "trace_abstraction" / f"{row['prompt_variant']}_cand_{int(row['candidate_index']):02d}",
        )
        for out_col, key in [
            ("compile_ok", "compile_ok"),
            ("correct_pass", "correct_pass"),
            ("buggy_fail", "buggy_fail"),
            ("antecedent_hit", "antecedent_hit"),
            ("non_vacuous", "non_vacuous"),
            ("heldout_correct_pass", "heldout_correct_pass"),
            ("heldout_buggy_fail", "heldout_buggy_fail"),
            ("trace_overfit", "trace_overfit"),
            ("heldout_antecedent_hit", "heldout_antecedent_hit"),
            ("heldout_non_vacuous", "heldout_non_vacuous"),
            ("seen_good_ant_hits", "seen_good_ant_hits"),
            ("seen_bad_ant_hits", "seen_bad_ant_hits"),
            ("heldout_bad_ant_hits", "heldout_bad_ant_hits"),
            ("seen_good_fail_hits", "seen_good_fail_hits"),
            ("seen_bad_fail_hits", "seen_bad_fail_hits"),
            ("heldout_good_fail_hits", "heldout_good_fail_hits"),
            ("heldout_bad_fail_hits", "heldout_bad_fail_hits"),
        ]:
            df.at[idx, out_col] = eval_result[key]
    df.to_csv(TRACE_ABS_RAW, index=False, encoding="utf-8-sig")

    summary_rows = []
    for (case_id, prompt_variant), sub in df.groupby(["case_id", "prompt_variant"], dropna=False):
        summary_rows.append(
            {
                "case_id": case_id,
                "prompt_variant": prompt_variant,
                "candidate_count": int(len(sub)),
                "compile_ok_count": int(sub["compile_ok"].astype(bool).sum()),
                "correct_pass_count": int(sub["correct_pass"].astype(bool).sum()),
                "buggy_fail_count": int(sub["buggy_fail"].astype(bool).sum()),
                "antecedent_hit_count": int(sub["antecedent_hit"].astype(bool).sum()),
                "non_vacuous_count": int(sub["non_vacuous"].astype(bool).sum()),
                "heldout_correct_pass_count": int(sub["heldout_correct_pass"].astype(bool).sum()),
                "heldout_buggy_fail_count": int(sub["heldout_buggy_fail"].astype(bool).sum()),
                "trace_overfit_count": int(sub["trace_overfit"].astype(bool).sum()),
                "semantic_reasonable_count": int(sub["semantic_reasonable"].astype(bool).sum()),
            }
        )
    pd.DataFrame(summary_rows).sort_values(["case_id", "prompt_variant"]).to_csv(
        TRACE_ABS_SUMMARY, index=False, encoding="utf-8-sig"
    )


def ant_candidate_score(row: pd.Series) -> tuple:
    return (
        int(is_true(row["compile_ok"])),
        int(is_true(row["correct_pass"])),
        int(is_true(row["fail_on_buggy"])),
        int(is_true(row["antecedent_hit"])),
        int(is_true(row["heldout_correct_pass"])),
        int(is_true(row["heldout_buggy_fail"])),
        -int(is_true(row["trace_overfit"])),
        int(row.get("heldout_bad_ant_hits", 0) or 0),
        -int(row.get("seen_good_fail_hits", 0) or 0),
    )


def refresh_antecedent_repair() -> None:
    cand_df = pd.read_csv(ANT_REPAIR_CAND)
    case_df = pd.read_csv(ANT_REPAIR_CASE)
    allowed_signals = prompt_signal_names(CASE124, "spec_rtl_raw_trace")

    case124_rows = cand_df[cand_df["case_id"] == CASE124].copy()
    if case124_rows.empty:
        return

    original_assertion = str(case124_rows.iloc[0]["original_assertion"])
    original_eval = safe_eval(
        case_id=CASE124,
        assertion_text=original_assertion,
        signal_names=allowed_signals,
        use_property=False,
        runtime_dir=OUTPUT_ROOT / "_refresh_runtime" / "antecedent_repair" / "original",
    )

    for idx, row in cand_df[cand_df["case_id"] == CASE124].iterrows():
        eval_result = safe_eval(
            case_id=CASE124,
            assertion_text=str(row["repaired_assertion"]),
            signal_names=allowed_signals,
            use_property=False,
            runtime_dir=OUTPUT_ROOT / "_refresh_runtime" / "antecedent_repair" / f"cand_{int(row['candidate_index']):02d}",
        )
        updates = {
            "original_compile_ok": bool(original_eval["compile_ok"]),
            "original_correct_pass": bool(original_eval["correct_pass"]),
            "original_fail_on_buggy": bool(original_eval["buggy_fail"]),
            "original_antecedent_hit": bool(original_eval["antecedent_hit"]),
            "original_non_vacuous": bool(original_eval["non_vacuous"]),
            "original_heldout_correct_pass": bool(original_eval["heldout_correct_pass"]),
            "original_heldout_buggy_fail": bool(original_eval["heldout_buggy_fail"]),
            "original_trace_overfit": bool(original_eval["trace_overfit"]),
            "compile_ok": bool(eval_result["compile_ok"]),
            "correct_pass": bool(eval_result["correct_pass"]),
            "fail_on_buggy": bool(eval_result["buggy_fail"]),
            "antecedent_hit": bool(eval_result["antecedent_hit"]),
            "non_vacuous": bool(eval_result["non_vacuous"]),
            "heldout_correct_pass": bool(eval_result["heldout_correct_pass"]),
            "heldout_buggy_fail": bool(eval_result["heldout_buggy_fail"]),
            "heldout_antecedent_hit": bool(eval_result["heldout_antecedent_hit"]),
            "trace_overfit": bool(eval_result["trace_overfit"]),
            "correct_pass_preserved": bool(original_eval["correct_pass"] and eval_result["correct_pass"]),
            "fail_on_buggy_improved": bool((not original_eval["buggy_fail"]) and eval_result["buggy_fail"]),
            "antecedent_hit_improved": bool((not original_eval["antecedent_hit"]) and eval_result["antecedent_hit"]),
            "false_positive_introduced": bool(original_eval["correct_pass"] and (not eval_result["correct_pass"])),
            "heldout_failure_introduced": bool(
                (original_eval["heldout_correct_pass"] and (not eval_result["heldout_correct_pass"]))
                or (original_eval["heldout_buggy_fail"] and (not eval_result["heldout_buggy_fail"]))
            ),
            "seen_good_ant_hits": int(eval_result["seen_good_ant_hits"]),
            "seen_bad_ant_hits": int(eval_result["seen_bad_ant_hits"]),
            "heldout_bad_ant_hits": int(eval_result["heldout_bad_ant_hits"]),
            "seen_good_fail_hits": int(eval_result["seen_good_fail_hits"]),
            "seen_bad_fail_hits": int(eval_result["seen_bad_fail_hits"]),
            "heldout_good_fail_hits": int(eval_result["heldout_good_fail_hits"]),
            "heldout_bad_fail_hits": int(eval_result["heldout_bad_fail_hits"]),
        }
        for k, v in updates.items():
            cand_df.at[idx, k] = v

    cand_df.to_csv(ANT_REPAIR_CAND, index=False, encoding="utf-8-sig")

    best_sub = cand_df[cand_df["case_id"] == CASE124].copy()
    best_row = sorted(
        (row for _, row in best_sub.iterrows()),
        key=ant_candidate_score,
        reverse=True,
    )[0]

    case_idx = case_df.index[case_df["case_id"] == CASE124]
    if len(case_idx):
        i = case_idx[0]
        case_df.at[i, "best_repaired_antecedent"] = best_row["repaired_antecedent"]
        case_df.at[i, "best_repaired_assertion"] = best_row["repaired_assertion"]
        case_df.at[i, "original_correct_pass"] = bool(original_eval["correct_pass"])
        case_df.at[i, "repaired_correct_pass"] = bool(best_row["correct_pass"])
        case_df.at[i, "original_fail_on_buggy"] = bool(original_eval["buggy_fail"])
        case_df.at[i, "repaired_fail_on_buggy"] = bool(best_row["fail_on_buggy"])
        case_df.at[i, "original_antecedent_hit"] = bool(original_eval["antecedent_hit"])
        case_df.at[i, "repaired_antecedent_hit"] = bool(best_row["antecedent_hit"])
        case_df.at[i, "original_heldout_correct_pass"] = bool(original_eval["heldout_correct_pass"])
        case_df.at[i, "repaired_heldout_correct_pass"] = bool(best_row["heldout_correct_pass"])
        case_df.at[i, "original_heldout_buggy_fail"] = bool(original_eval["heldout_buggy_fail"])
        case_df.at[i, "repaired_heldout_buggy_fail"] = bool(best_row["heldout_buggy_fail"])
        case_df.at[i, "correct_pass_preserved"] = bool(best_row["correct_pass_preserved"])
        case_df.at[i, "fail_on_buggy_improved"] = bool(best_row["fail_on_buggy_improved"])
        case_df.at[i, "antecedent_hit_improved"] = bool(best_row["antecedent_hit_improved"])
        case_df.at[i, "false_positive_introduced"] = bool(best_row["false_positive_introduced"])
        case_df.at[i, "heldout_failure_introduced"] = bool(best_row["heldout_failure_introduced"])
        case_df.at[i, "best_candidate_index"] = int(best_row["candidate_index"])
        case_df.at[i, "generated_candidate_count"] = int(best_sub["candidate_index"].nunique())

    case_df.to_csv(ANT_REPAIR_CASE, index=False, encoding="utf-8-sig")


def refresh_prompt_ablation() -> None:
    df = pd.read_csv(PROMPT_ABL_RAW)
    signal_names = prompt_signal_names(CASE124, "spec_rtl_raw_trace")

    for idx, row in df[df["case_id"] == CASE124].iterrows():
        eval_result = safe_eval(
            case_id=CASE124,
            assertion_text=str(row["assertion_text"]),
            signal_names=signal_names,
            use_property=is_true(row.get("use_property_compile_mode", False)),
            runtime_dir=OUTPUT_ROOT / "_refresh_runtime" / "prompt_ablation" / str(row["prompt_variant"]) / f"cand_{int(row['candidate_index']):02d}",
        )
        strict_success = bool(
            eval_result["compile_ok"]
            and eval_result["correct_pass"]
            and eval_result["buggy_fail"]
            and eval_result["heldout_correct_pass"]
            and eval_result["heldout_buggy_fail"]
            and eval_result["heldout_antecedent_hit"]
        )
        heldout_success = bool(
            eval_result["compile_ok"]
            and eval_result["heldout_correct_pass"]
            and eval_result["heldout_buggy_fail"]
        )
        updates = {
            "compile_ok": bool(eval_result["compile_ok"]),
            "correct_pass": bool(eval_result["correct_pass"]),
            "buggy_fail": bool(eval_result["buggy_fail"]),
            "antecedent_hit": bool(eval_result["antecedent_hit"]),
            "non_vacuous": bool(eval_result["non_vacuous"]),
            "heldout_correct_pass": bool(eval_result["heldout_correct_pass"]),
            "heldout_buggy_fail": bool(eval_result["heldout_buggy_fail"]),
            "heldout_antecedent_hit": bool(eval_result["heldout_antecedent_hit"]),
            "trace_overfit": bool(eval_result["trace_overfit"]),
            "strict_success": strict_success,
            "heldout_success": heldout_success,
            "seen_good_ant_hits": int(eval_result["seen_good_ant_hits"]),
            "seen_bad_ant_hits": int(eval_result["seen_bad_ant_hits"]),
            "heldout_bad_ant_hits": int(eval_result["heldout_bad_ant_hits"]),
            "seen_good_fail_hits": int(eval_result["seen_good_fail_hits"]),
            "seen_bad_fail_hits": int(eval_result["seen_bad_fail_hits"]),
            "heldout_good_fail_hits": int(eval_result["heldout_good_fail_hits"]),
            "heldout_bad_fail_hits": int(eval_result["heldout_bad_fail_hits"]),
        }
        for k, v in updates.items():
            df.at[idx, k] = v
    df.to_csv(PROMPT_ABL_RAW, index=False, encoding="utf-8-sig")

    prompt_summary_rows = []
    for prompt_variant, sub in df.groupby("prompt_variant", dropna=False):
        prompt_summary_rows.append(
            {
                "prompt_variant": prompt_variant,
                "constraint_family": sub["constraint_family"].iloc[0],
                "candidate_count": int(len(sub)),
                "case_count": int(sub["case_id"].nunique()),
                "compile_ok_rate": float(sub["compile_ok"].mean()),
                "correct_pass_rate": float(sub["correct_pass"].mean()),
                "buggy_fail_rate": float(sub["buggy_fail"].mean()),
                "antecedent_hit_rate": float(sub["antecedent_hit"].mean()),
                "non_vacuous_rate": float(sub["non_vacuous"].mean()),
                "heldout_correct_pass_rate": float(sub["heldout_correct_pass"].mean()),
                "heldout_buggy_fail_rate": float(sub["heldout_buggy_fail"].mean()),
                "heldout_antecedent_hit_rate": float(sub["heldout_antecedent_hit"].mean()),
                "heldout_success_rate": float(sub["heldout_success"].mean()),
                "strict_success_rate": float(sub["strict_success"].mean()),
                "trace_overfit_rate": float(sub["trace_overfit"].mean()),
                "literal_hardcoding_rate": float(sub["literal_hardcoding"].mean()),
                "semantic_reasonable_rate": float(sub["semantic_reasonable"].mean()),
                "uses_temporal_feature_rate": float(sub["uses_temporal_feature"].mean()),
                "strict_success_case_count": int(sub.groupby("case_id", dropna=False)["strict_success"].max().sum()),
                "heldout_success_case_count": int(sub.groupby("case_id", dropna=False)["heldout_success"].max().sum()),
            }
        )
    pd.DataFrame(prompt_summary_rows).sort_values(
        ["strict_success_rate", "heldout_success_rate", "buggy_fail_rate", "correct_pass_rate"],
        ascending=[False, False, False, False],
    ).reset_index(drop=True).to_csv(PROMPT_ABL_SUMMARY, index=False, encoding="utf-8-sig")

    case_prompt_rows = []
    for (case_id, prompt_variant), sub in df.groupby(["case_id", "prompt_variant"], dropna=False):
        best_assertion_text = next(
            iter(
                sub.sort_values(
                    [
                        "strict_success",
                        "heldout_success",
                        "buggy_fail",
                        "correct_pass",
                        "antecedent_hit",
                        "semantic_reasonable",
                    ],
                    ascending=[False, False, False, False, False, False],
                )["assertion_text"].tolist()
            ),
            "",
        )
        case_prompt_rows.append(
            {
                "case_id": case_id,
                "prompt_variant": prompt_variant,
                "constraint_family": sub["constraint_family"].iloc[0],
                "candidate_count": int(len(sub)),
                "compile_ok_rate": float(sub["compile_ok"].mean()),
                "correct_pass_rate": float(sub["correct_pass"].mean()),
                "buggy_fail_rate": float(sub["buggy_fail"].mean()),
                "antecedent_hit_rate": float(sub["antecedent_hit"].mean()),
                "heldout_success_rate": float(sub["heldout_success"].mean()),
                "strict_success_rate": float(sub["strict_success"].mean()),
                "trace_overfit_rate": float(sub["trace_overfit"].mean()),
                "literal_hardcoding_rate": float(sub["literal_hardcoding"].mean()),
                "uses_temporal_feature_rate": float(sub["uses_temporal_feature"].mean()),
                "best_assertion_text": best_assertion_text,
            }
        )
    pd.DataFrame(case_prompt_rows).sort_values(["case_id", "prompt_variant"]).reset_index(drop=True).to_csv(
        PROMPT_ABL_CASE_SUMMARY, index=False, encoding="utf-8-sig"
    )


def refresh_trace_selection() -> None:
    df = pd.read_csv(TRACESEL_RAW)
    signal_names = prompt_signal_names(CASE124, "spec_rtl_raw_trace")

    for idx, row in df[df["case_id"] == CASE124].iterrows():
        eval_result = safe_eval(
            case_id=CASE124,
            assertion_text=str(row["assertion_text"]),
            signal_names=signal_names,
            use_property=is_true(row.get("use_property_compile_mode", False)),
            runtime_dir=OUTPUT_ROOT / "_refresh_runtime" / "trace_selection" / str(row["selected_trace_quality"]) / f"cand_{int(row['candidate_index']):02d}",
        )
        for out_col, key in [
            ("compile_ok", "compile_ok"),
            ("correct_pass", "correct_pass"),
            ("buggy_fail", "buggy_fail"),
            ("antecedent_hit", "antecedent_hit"),
            ("non_vacuous", "non_vacuous"),
            ("heldout_correct_pass", "heldout_correct_pass"),
            ("heldout_buggy_fail", "heldout_buggy_fail"),
            ("heldout_antecedent_hit", "heldout_antecedent_hit"),
            ("trace_overfit", "trace_overfit"),
            ("seen_good_ant_hits", "seen_good_ant_hits"),
            ("seen_bad_ant_hits", "seen_bad_ant_hits"),
            ("heldout_bad_ant_hits", "heldout_bad_ant_hits"),
            ("seen_good_fail_hits", "seen_good_fail_hits"),
            ("seen_bad_fail_hits", "seen_bad_fail_hits"),
            ("heldout_good_fail_hits", "heldout_good_fail_hits"),
            ("heldout_bad_fail_hits", "heldout_bad_fail_hits"),
        ]:
            df.at[idx, out_col] = eval_result[key]
    df.to_csv(TRACESEL_RAW, index=False, encoding="utf-8-sig")

    summary_rows = []
    for (case_id, quality_name), sub in df.groupby(["case_id", "selected_trace_quality"], dropna=False):
        summary_rows.append(
            {
                "case_id": case_id,
                "selected_trace_quality": quality_name,
                "candidate_count": int(len(sub)),
                "compile_ok_count": int(sub["compile_ok"].astype(bool).sum()),
                "correct_pass_count": int(sub["correct_pass"].astype(bool).sum()),
                "buggy_fail_count": int(sub["buggy_fail"].astype(bool).sum()),
                "antecedent_hit_count": int(sub["antecedent_hit"].astype(bool).sum()),
                "non_vacuous_count": int(sub["non_vacuous"].astype(bool).sum()),
                "heldout_correct_pass_count": int(sub["heldout_correct_pass"].astype(bool).sum()),
                "heldout_buggy_fail_count": int(sub["heldout_buggy_fail"].astype(bool).sum()),
                "trace_overfit_count": int(sub["trace_overfit"].astype(bool).sum()),
                "semantic_reasonable_count": int(sub["semantic_reasonable"].astype(bool).sum()),
            }
        )
    pd.DataFrame(summary_rows).sort_values(["case_id", "selected_trace_quality"]).reset_index(drop=True).to_csv(
        TRACESEL_SUMMARY, index=False, encoding="utf-8-sig"
    )

    comparison_rows = []
    for case_id, sub in df.groupby("case_id", dropna=False):
        high = sub[sub["selected_trace_quality"] == "high_quality_trace"]
        low = sub[sub["selected_trace_quality"] == "low_quality_trace"]

        def rate(frame: pd.DataFrame, col: str) -> float:
            if frame.empty:
                return 0.0
            return float(frame[col].mean())

        comparison_rows.append(
            {
                "case_id": case_id,
                "high_quality_correct_pass_rate": rate(high, "correct_pass"),
                "low_quality_correct_pass_rate": rate(low, "correct_pass"),
                "delta_correct_pass": rate(high, "correct_pass") - rate(low, "correct_pass"),
                "high_quality_buggy_fail_rate": rate(high, "buggy_fail"),
                "low_quality_buggy_fail_rate": rate(low, "buggy_fail"),
                "delta_buggy_fail": rate(high, "buggy_fail") - rate(low, "buggy_fail"),
                "high_quality_antecedent_hit_rate": rate(high, "antecedent_hit"),
                "low_quality_antecedent_hit_rate": rate(low, "antecedent_hit"),
                "delta_antecedent_hit": rate(high, "antecedent_hit") - rate(low, "antecedent_hit"),
                "high_quality_heldout_buggy_fail_rate": rate(high, "heldout_buggy_fail"),
                "low_quality_heldout_buggy_fail_rate": rate(low, "heldout_buggy_fail"),
                "delta_heldout_buggy_fail": rate(high, "heldout_buggy_fail") - rate(low, "heldout_buggy_fail"),
                "high_quality_trace_overfit_rate": rate(high, "trace_overfit"),
                "low_quality_trace_overfit_rate": rate(low, "trace_overfit"),
                "delta_trace_overfit": rate(high, "trace_overfit") - rate(low, "trace_overfit"),
            }
        )
    pd.DataFrame(comparison_rows).sort_values(["case_id"]).reset_index(drop=True).to_csv(
        TRACESEL_COMPARISON, index=False, encoding="utf-8-sig"
    )


def main() -> None:
    refresh_strict_report()
    refresh_trace_abstraction_raw()
    refresh_antecedent_repair()
    refresh_prompt_ablation()
    refresh_trace_selection()
    print("refreshed case119/case124 benchmark impacts")


if __name__ == "__main__":
    main()
