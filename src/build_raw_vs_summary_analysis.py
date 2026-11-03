from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
THREAD_ID = "019ed9f6-87cf-7830-adb8-595fe2ae140d"
SOURCE_CLEAN = ROOT / "docs" / "real_rtl_scaleout" / "assertion_clean_master_iv12.csv"
INVENTORY = ROOT / "docs" / "real_rtl_scaleout" / "dataset_inventory_30cases.csv"
OUTPUT_DIR = ROOT / "outputs" / THREAD_ID / "raw_vs_summary_data"

METHODS = ["spec_rtl_raw_trace", "spec_rtl_trace_summary"]
METHOD_LABEL = {
    "spec_rtl_raw_trace": "raw trace",
    "spec_rtl_trace_summary": "trace summary",
}
METRICS = [
    "compile_ok",
    "correct_pass",
    "fail_on_buggy",
    "antecedent_hit_buggy",
    "non_vacuous_buggy",
    "heldout_success",
    "trace_overfit",
    "literal_hardcoding",
]


def safe_bool_series(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series.fillna(False)
    lowered = series.fillna(False).astype(str).str.strip().str.lower()
    return lowered.isin(["true", "1", "yes"])


def clean_text(text: str) -> str:
    text = "" if pd.isna(text) else str(text)
    return " ".join(text.strip().split())


def rate(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round(numerator / denominator, 4)


def signed(value: float) -> str:
    return f"{value:+.3f}"


def summarize_failure_reason(case_df: pd.DataFrame, method: str) -> tuple[str, str]:
    sub = case_df[(case_df["method"] == method) & (case_df["failure_flag"])].copy()
    if sub.empty:
        return "", ""
    type_counts = sub["failure_type"].fillna("unknown").value_counts()
    top_type = str(type_counts.index[0]) if not type_counts.empty else ""
    reason_rows = sub[sub["failure_reason"].fillna("").astype(str).str.strip() != ""]
    top_reason = ""
    if not reason_rows.empty:
        top_reason = clean_text(reason_rows.iloc[0]["failure_reason"])
    return top_type, top_reason


def classify_case(row: pd.Series) -> str:
    raw_present = bool(row["raw_present"])
    summary_present = bool(row["summary_present"])
    raw_score = float(row["raw_score"])
    summary_score = float(row["summary_score"])

    raw_cp = float(row["raw_correct_pass_rate"])
    sum_cp = float(row["summary_correct_pass_rate"])
    raw_fail = float(row["raw_fail_on_buggy_rate"])
    sum_fail = float(row["summary_fail_on_buggy_rate"])
    raw_ant = float(row["raw_antecedent_hit_rate"])
    sum_ant = float(row["summary_antecedent_hit_rate"])
    raw_hold = float(row["raw_heldout_success_rate"])
    sum_hold = float(row["summary_heldout_success_rate"])

    delta_cp = sum_cp - raw_cp
    delta_fail = sum_fail - raw_fail
    delta_hold = sum_hold - raw_hold

    if not raw_present:
        if summary_score >= 2.0 or sum_fail > 0.5 or sum_hold > 0:
            return "trace summary 更好"
        return "两者都不好"
    if not summary_present:
        if raw_score >= 2.0 or raw_fail > 0.5 or raw_hold > 0:
            return "raw trace 更好"
        return "两者都不好"

    if (
        max(raw_score, summary_score) < 1.5
        or (
            max(raw_hold, sum_hold) == 0
            and max(raw_fail, sum_fail) <= 0.5
            and max(raw_cp, sum_cp) <= 0.5
        )
        or (
            raw_cp == 0
            and sum_cp == 0
            and max(raw_fail, sum_fail) <= 1.0
            and max(raw_hold, sum_hold) == 0
        )
    ):
        return "两者都不好"

    tradeoff = (
        (delta_cp > 0.1 and delta_fail < -0.1)
        or (delta_cp < -0.1 and delta_fail > 0.1)
        or (delta_hold > 0.1 and delta_cp < -0.1)
        or (delta_hold < -0.1 and delta_cp > 0.1)
    )
    if tradeoff:
        return "两者表现相反"

    if abs(summary_score - raw_score) < 0.15:
        if raw_hold == sum_hold and raw_fail == sum_fail and raw_cp == sum_cp:
            if raw_hold > 0 and sum_hold > 0:
                return "trace summary 更好"
            if raw_cp == 0 and sum_cp == 0:
                return "两者都不好"
            if raw_fail == 0 and sum_fail == 0:
                return "两者都不好"
            return "trace summary 更好"
        if sum_ant > raw_ant:
            return "trace summary 更好"
        if raw_ant > sum_ant:
            return "raw trace 更好"

    if (
        summary_score - raw_score >= 0.6
        and float(row["summary_trace_overfit_rate"]) <= float(row["raw_trace_overfit_rate"]) + 0.2
        and float(row["summary_literal_hardcoding_rate"])
        <= float(row["raw_literal_hardcoding_rate"]) + 0.2
    ):
        return "trace summary 更好"
    if (
        raw_score - summary_score >= 0.6
        and float(row["raw_trace_overfit_rate"]) <= float(row["summary_trace_overfit_rate"]) + 0.2
        and float(row["raw_literal_hardcoding_rate"])
        <= float(row["summary_literal_hardcoding_rate"]) + 0.2
    ):
        return "raw trace 更好"

    if summary_score > raw_score:
        return "trace summary 更好"
    return "raw trace 更好"


def build_case_note(row: pd.Series) -> str:
    label = row["case_conclusion"]
    case_id = row["case_id"]
    raw_present = bool(row["raw_present"])
    summary_present = bool(row["summary_present"])

    raw_cp = float(row["raw_correct_pass_rate"])
    sum_cp = float(row["summary_correct_pass_rate"])
    raw_fail = float(row["raw_fail_on_buggy_rate"])
    sum_fail = float(row["summary_fail_on_buggy_rate"])
    raw_ant = float(row["raw_antecedent_hit_rate"])
    sum_ant = float(row["summary_antecedent_hit_rate"])
    raw_hold = float(row["raw_heldout_success_rate"])
    sum_hold = float(row["summary_heldout_success_rate"])
    raw_trace = float(row["raw_trace_overfit_rate"])
    sum_trace = float(row["summary_trace_overfit_rate"])
    raw_lit = float(row["raw_literal_hardcoding_rate"])
    sum_lit = float(row["summary_literal_hardcoding_rate"])

    raw_ft = row["raw_top_failure_type"]
    sum_ft = row["summary_top_failure_type"]
    raw_fr = row["raw_top_failure_reason"]
    sum_fr = row["summary_top_failure_reason"]

    if not raw_present and not summary_present:
        return f"{case_id}：两者都不好。当前 clean master 中 raw trace 和 trace summary 都没有保留下来的 clean assertion，因此无法形成有效对比，也可视为这两种 trace 输入在该 case 上都未产出可分析结果。"

    if not raw_present:
        tail = f"当前 clean master 里 raw trace 没有保留下来的断言，而 summary 至少达到 correct_pass={sum_cp:.1%}、fail_on_buggy={sum_fail:.1%}。"
        if sum_fr:
            tail += f" 它的主要问题仍是：{sum_fr}。"
        return f"{case_id}：{label}。{tail}"
    if not summary_present:
        tail = f"当前 clean master 里 trace summary 没有保留下来的断言，而 raw 至少达到 correct_pass={raw_cp:.1%}、fail_on_buggy={raw_fail:.1%}。"
        if raw_fr:
            tail += f" 它的主要问题仍是：{raw_fr}。"
        return f"{case_id}：{label}。{tail}"

    if label == "raw trace 更好":
        reason_bits = []
        if raw_fail > sum_fail:
            reason_bits.append(f"raw 的 fail_on_buggy 更高（{raw_fail:.1%} vs {sum_fail:.1%}）")
        if raw_ant > sum_ant:
            reason_bits.append(f"raw 的 antecedent_hit 更高（{raw_ant:.1%} vs {sum_ant:.1%}）")
        if raw_hold > sum_hold:
            reason_bits.append(f"raw 的 held-out success 更高（{raw_hold:.1%} vs {sum_hold:.1%}）")
        if raw_trace < sum_trace:
            reason_bits.append(f"raw 的 trace_overfit 更低（{raw_trace:.1%} vs {sum_trace:.1%}）")
        if raw_lit < sum_lit:
            reason_bits.append(f"raw 的 literal_hardcoding 更低（{raw_lit:.1%} vs {sum_lit:.1%}）")
        lead = "；".join(reason_bits) if reason_bits else "raw 在当前 case 上的综合分数更高"
        if sum_fr:
            lead += f"，而 summary 侧主要卡在：{sum_fr}"
        elif sum_ft:
            lead += f"，而 summary 侧主导失败类型是 {sum_ft}"
        return f"{case_id}：{label}。{lead}。"

    if label == "trace summary 更好":
        reason_bits = []
        if sum_fail > raw_fail:
            reason_bits.append(f"summary 的 fail_on_buggy 更高（{sum_fail:.1%} vs {raw_fail:.1%}）")
        if sum_ant > raw_ant:
            reason_bits.append(f"summary 的 antecedent_hit 更高（{sum_ant:.1%} vs {raw_ant:.1%}）")
        if sum_hold > raw_hold:
            reason_bits.append(f"summary 的 held-out success 更高（{sum_hold:.1%} vs {raw_hold:.1%}）")
        if sum_trace < raw_trace:
            reason_bits.append(f"summary 的 trace_overfit 更低（{sum_trace:.1%} vs {raw_trace:.1%}）")
        if sum_lit < raw_lit:
            reason_bits.append(f"summary 的 literal_hardcoding 更低（{sum_lit:.1%} vs {raw_lit:.1%}）")
        lead = "；".join(reason_bits) if reason_bits else "summary 在当前 case 上的综合分数更高"
        if raw_fr:
            lead += f"，而 raw 侧主要卡在：{raw_fr}"
        elif raw_ft:
            lead += f"，而 raw 侧主导失败类型是 {raw_ft}"
        return f"{case_id}：{label}。{lead}。"

    if label == "两者都不好":
        reason_bits = []
        if max(raw_hold, sum_hold) == 0:
            reason_bits.append("两边都没有 held-out success")
        if max(raw_fail, sum_fail) <= 0.5:
            reason_bits.append("两边的 fail_on_buggy 都偏低")
        if max(raw_cp, sum_cp) == 0:
            reason_bits.append("两边都会误伤 correct")
        if max(raw_ant, sum_ant) <= 0.5:
            reason_bits.append("antecedent 触发也不稳定")
        lead = "；".join(reason_bits) if reason_bits else "两边都没形成稳定、可泛化的断言"
        return f"{case_id}：{label}。{lead}。"

    trade_bits = []
    if sum_cp > raw_cp:
        trade_bits.append(f"summary 更保守/更容易过 correct（{sum_cp:.1%} vs {raw_cp:.1%}）")
    elif raw_cp > sum_cp:
        trade_bits.append(f"raw 更容易过 correct（{raw_cp:.1%} vs {sum_cp:.1%}）")
    if sum_fail > raw_fail:
        trade_bits.append(f"summary 的 bug 检测更强（{sum_fail:.1%} vs {raw_fail:.1%}）")
    elif raw_fail > sum_fail:
        trade_bits.append(f"raw 的 bug 检测更强（{raw_fail:.1%} vs {sum_fail:.1%}）")
    if sum_hold > raw_hold:
        trade_bits.append(f"summary 的 held-out success 更高（{sum_hold:.1%} vs {raw_hold:.1%}）")
    elif raw_hold > sum_hold:
        trade_bits.append(f"raw 的 held-out success 更高（{raw_hold:.1%} vs {sum_hold:.1%}）")
    if raw_lit != sum_lit:
        winner = "summary" if sum_lit < raw_lit else "raw"
        trade_bits.append(f"{winner} 的 literal hardcoding 更轻")
    return f"{case_id}：{label}。{'；'.join(trade_bits)}。"


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(SOURCE_CLEAN)
    inventory_df = pd.read_csv(INVENTORY)
    bool_cols = [
        "compile_ok",
        "correct_pass",
        "fail_on_buggy",
        "antecedent_hit_buggy",
        "non_vacuous_buggy",
        "heldout_correct_pass",
        "heldout_buggy_fail",
        "trace_overfit",
        "literal_hardcoding",
    ]
    for col in bool_cols:
        df[col] = safe_bool_series(df[col])

    df["heldout_success"] = df["heldout_correct_pass"] & df["heldout_buggy_fail"]
    df["compile_fail"] = ~df["compile_ok"]
    df["failure_flag"] = (~df["compile_ok"]) | (~df["correct_pass"]) | (~df["fail_on_buggy"])
    df["method_label"] = df["method"].map(METHOD_LABEL).fillna(df["method"])

    case_meta = (
        inventory_df[["case_name", "source_module", "bug_type", "bug_class"]]
        .rename(
            columns={
                "case_name": "case_id",
                "source_module": "module",
                "bug_type": "bug_name",
            }
        )
        .copy()
    )
    df["module"] = df["module"].fillna("")
    df["bug_name"] = df["bug_name"].fillna("")
    df["bug_class"] = df["bug_class"].fillna("")
    df = df.merge(
        case_meta.rename(
            columns={
                "module": "module_inventory",
                "bug_name": "bug_name_inventory",
                "bug_class": "bug_class_inventory",
            }
        ),
        on="case_id",
        how="left",
    )
    df["module"] = df["module"].replace("", pd.NA).fillna(df["module_inventory"]).fillna("")
    df["bug_name"] = df["bug_name"].replace("", pd.NA).fillna(df["bug_name_inventory"]).fillna("")
    df["bug_class"] = df["bug_class"].replace("", pd.NA).fillna(df["bug_class_inventory"]).fillna("")

    pair_df = df[df["method"].isin(METHODS)].copy()
    raw_cases = set(pair_df[pair_df["method"] == "spec_rtl_raw_trace"]["case_id"].unique().tolist())
    summary_cases = set(pair_df[pair_df["method"] == "spec_rtl_trace_summary"]["case_id"].unique().tolist())
    overlap_cases = sorted(raw_cases & summary_cases)
    all_cases = sorted(case_meta["case_id"].unique().tolist())
    union_cases = all_cases

    overall_rows = []
    for scope_name, scope_cases in [
        ("overall_union", union_cases),
        ("overlap_only", overlap_cases),
    ]:
        scope_df = pair_df[pair_df["case_id"].isin(scope_cases)].copy()
        for method in METHODS:
            sub = scope_df[scope_df["method"] == method].copy()
            assertion_count = int(len(sub))
            compile_ok_count = int(sub["compile_ok"].sum())
            overall_rows.append(
                {
                    "scope": scope_name,
                    "method": method,
                    "method_label": METHOD_LABEL[method],
                    "case_count": int(sub["case_id"].nunique()),
                    "assertion_count": assertion_count,
                    "compile_ok_count": compile_ok_count,
                    "compile_ok_rate": rate(compile_ok_count, assertion_count),
                    "compile_fail_count": assertion_count - compile_ok_count,
                    "correct_pass_count": int(sub["correct_pass"].sum()),
                    "correct_pass_rate": rate(int(sub["correct_pass"].sum()), assertion_count),
                    "fail_on_buggy_count": int(sub["fail_on_buggy"].sum()),
                    "fail_on_buggy_rate": rate(int(sub["fail_on_buggy"].sum()), assertion_count),
                    "antecedent_hit_count": int(sub["antecedent_hit_buggy"].sum()),
                    "antecedent_hit_rate": rate(int(sub["antecedent_hit_buggy"].sum()), assertion_count),
                    "non_vacuous_count": int(sub["non_vacuous_buggy"].sum()),
                    "non_vacuous_rate": rate(int(sub["non_vacuous_buggy"].sum()), assertion_count),
                    "heldout_success_count": int(sub["heldout_success"].sum()),
                    "heldout_success_rate": rate(int(sub["heldout_success"].sum()), assertion_count),
                    "trace_overfit_count": int(sub["trace_overfit"].sum()),
                    "trace_overfit_rate": rate(int(sub["trace_overfit"].sum()), assertion_count),
                    "literal_hardcoding_count": int(sub["literal_hardcoding"].sum()),
                    "literal_hardcoding_rate": rate(int(sub["literal_hardcoding"].sum()), assertion_count),
                }
            )
    overall_df = pd.DataFrame(overall_rows)
    overall_df.to_csv(OUTPUT_DIR / "raw_vs_summary_overall.csv", index=False)

    case_rows = []
    for case_id in union_cases:
        case_df = pair_df[pair_df["case_id"] == case_id].copy()
        meta = case_meta[case_meta["case_id"] == case_id].iloc[0]
        row = {
            "case_id": case_id,
            "module": meta["module"],
            "bug_name": meta["bug_name"],
            "bug_class": meta["bug_class"],
            "raw_present": case_id in raw_cases,
            "summary_present": case_id in summary_cases,
        }
        for method, prefix in [
            ("spec_rtl_raw_trace", "raw"),
            ("spec_rtl_trace_summary", "summary"),
        ]:
            sub = case_df[case_df["method"] == method].copy()
            row[f"{prefix}_assertion_count"] = int(len(sub))
            if sub.empty:
                for metric in [
                    "compile_ok_rate",
                    "compile_fail_rate",
                    "correct_pass_rate",
                    "fail_on_buggy_rate",
                    "antecedent_hit_rate",
                    "non_vacuous_rate",
                    "heldout_success_rate",
                    "trace_overfit_rate",
                    "literal_hardcoding_rate",
                ]:
                    row[f"{prefix}_{metric}"] = 0.0
                row[f"{prefix}_top_failure_type"] = ""
                row[f"{prefix}_top_failure_reason"] = ""
                row[f"{prefix}_representative_assertion"] = ""
                row[f"{prefix}_score"] = 0.0
                continue

            row[f"{prefix}_compile_ok_rate"] = round(float(sub["compile_ok"].mean()), 4)
            row[f"{prefix}_compile_fail_rate"] = round(float((~sub["compile_ok"]).mean()), 4)
            row[f"{prefix}_correct_pass_rate"] = round(float(sub["correct_pass"].mean()), 4)
            row[f"{prefix}_fail_on_buggy_rate"] = round(float(sub["fail_on_buggy"].mean()), 4)
            row[f"{prefix}_antecedent_hit_rate"] = round(float(sub["antecedent_hit_buggy"].mean()), 4)
            row[f"{prefix}_non_vacuous_rate"] = round(float(sub["non_vacuous_buggy"].mean()), 4)
            row[f"{prefix}_heldout_success_rate"] = round(float(sub["heldout_success"].mean()), 4)
            row[f"{prefix}_trace_overfit_rate"] = round(float(sub["trace_overfit"].mean()), 4)
            row[f"{prefix}_literal_hardcoding_rate"] = round(float(sub["literal_hardcoding"].mean()), 4)
            top_type, top_reason = summarize_failure_reason(case_df, method)
            row[f"{prefix}_top_failure_type"] = top_type
            row[f"{prefix}_top_failure_reason"] = top_reason

            rep = sub[
                sub["failure_reason"].fillna("").astype(str).str.strip() != ""
            ]
            if rep.empty:
                rep = sub[sub["failure_flag"]]
            if rep.empty:
                rep = sub
            row[f"{prefix}_representative_assertion"] = clean_text(rep.iloc[0]["assertion_text"])

            score = (
                row[f"{prefix}_correct_pass_rate"]
                + row[f"{prefix}_fail_on_buggy_rate"]
                + row[f"{prefix}_antecedent_hit_rate"]
                + row[f"{prefix}_non_vacuous_rate"]
                + 1.5 * row[f"{prefix}_heldout_success_rate"]
                - row[f"{prefix}_compile_fail_rate"]
                - 0.5 * row[f"{prefix}_trace_overfit_rate"]
                - 0.5 * row[f"{prefix}_literal_hardcoding_rate"]
            )
            row[f"{prefix}_score"] = round(score, 4)

        row["delta_correct_pass_rate"] = round(
            row["summary_correct_pass_rate"] - row["raw_correct_pass_rate"], 4
        )
        row["delta_fail_on_buggy_rate"] = round(
            row["summary_fail_on_buggy_rate"] - row["raw_fail_on_buggy_rate"], 4
        )
        row["delta_antecedent_hit_rate"] = round(
            row["summary_antecedent_hit_rate"] - row["raw_antecedent_hit_rate"], 4
        )
        row["delta_non_vacuous_rate"] = round(
            row["summary_non_vacuous_rate"] - row["raw_non_vacuous_rate"], 4
        )
        row["delta_heldout_success_rate"] = round(
            row["summary_heldout_success_rate"] - row["raw_heldout_success_rate"], 4
        )
        row["delta_trace_overfit_rate"] = round(
            row["summary_trace_overfit_rate"] - row["raw_trace_overfit_rate"], 4
        )
        row["delta_literal_hardcoding_rate"] = round(
            row["summary_literal_hardcoding_rate"] - row["raw_literal_hardcoding_rate"], 4
        )
        row["delta_score"] = round(row["summary_score"] - row["raw_score"], 4)
        row["summary_lost_temporal_info"] = (
            row["summary_antecedent_hit_rate"] < row["raw_antecedent_hit_rate"]
            or row["summary_fail_on_buggy_rate"] < row["raw_fail_on_buggy_rate"]
        )
        row["summary_more_conservative"] = (
            row["summary_correct_pass_rate"] > row["raw_correct_pass_rate"]
            and row["summary_fail_on_buggy_rate"] < row["raw_fail_on_buggy_rate"]
        ) or (
            row["summary_correct_pass_rate"] >= row["raw_correct_pass_rate"]
            and row["summary_antecedent_hit_rate"] < row["raw_antecedent_hit_rate"]
            and row["summary_fail_on_buggy_rate"] <= row["raw_fail_on_buggy_rate"]
        )
        row["summary_better_generalization"] = (
            row["summary_heldout_success_rate"] > row["raw_heldout_success_rate"]
            and row["summary_trace_overfit_rate"] <= row["raw_trace_overfit_rate"]
        )
        row["summary_reduces_hardcoding"] = (
            row["summary_literal_hardcoding_rate"] < row["raw_literal_hardcoding_rate"]
        )
        row["raw_more_literal_hardcoding"] = (
            row["raw_literal_hardcoding_rate"] > row["summary_literal_hardcoding_rate"]
        )
        row["summary_more_literal_hardcoding"] = (
            row["summary_literal_hardcoding_rate"] > row["raw_literal_hardcoding_rate"]
        )
        case_rows.append(row)

    case_df = pd.DataFrame(case_rows).sort_values("case_id").reset_index(drop=True)
    case_df["case_conclusion"] = case_df.apply(classify_case, axis=1)
    case_df["case_note"] = case_df.apply(build_case_note, axis=1)
    case_df.to_csv(OUTPUT_DIR / "raw_vs_summary_case_comparison.csv", index=False)

    overlap_case_df = case_df[case_df["raw_present"] & case_df["summary_present"]].copy()
    question_rows = []

    overall_lookup = overall_df.set_index(["scope", "method"])
    raw_overall = overall_lookup.loc[("overall_union", "spec_rtl_raw_trace")]
    sum_overall = overall_lookup.loc[("overall_union", "spec_rtl_trace_summary")]
    raw_overlap = overall_lookup.loc[("overlap_only", "spec_rtl_raw_trace")]
    sum_overlap = overall_lookup.loc[("overlap_only", "spec_rtl_trace_summary")]

    raw_lit_cases = int(overlap_case_df["raw_more_literal_hardcoding"].sum())
    sum_lit_cases = int(overlap_case_df["summary_more_literal_hardcoding"].sum())
    reduced_hardcoding_cases = int(overlap_case_df["summary_reduces_hardcoding"].sum())
    lost_temporal_cases = int(overlap_case_df["summary_lost_temporal_info"].sum())
    conservative_cases = int(overlap_case_df["summary_more_conservative"].sum())
    better_generalization_cases = int(overlap_case_df["summary_better_generalization"].sum())

    question_rows.append(
        {
            "question": "raw trace 是否更容易 literal hardcoding？",
            "short_answer": "不明显，至少不是系统性更高。",
            "evidence": (
                f"overall literal_hardcoding_rate: raw={raw_overall['literal_hardcoding_rate']:.1%}, "
                f"summary={sum_overall['literal_hardcoding_rate']:.1%}; "
                f"在 {len(overlap_case_df)} 个重叠 case 中，raw 更高 {raw_lit_cases} 个，summary 更高 {sum_lit_cases} 个。"
            ),
        }
    )
    question_rows.append(
        {
            "question": "trace summary 是否减少 hardcoding？",
            "short_answer": "只在少数 case 有所减少，但没有形成稳定总体改善。",
            "evidence": (
                f"summary 在 {reduced_hardcoding_cases}/{len(overlap_case_df)} 个重叠 case 上降低 literal_hardcoding；"
                f"但 overall literal_hardcoding_rate 仍几乎持平（raw={raw_overall['literal_hardcoding_rate']:.1%}, "
                f"summary={sum_overall['literal_hardcoding_rate']:.1%}）。"
            ),
        }
    )
    question_rows.append(
        {
            "question": "trace summary 是否丢失关键时序信息？",
            "short_answer": "是，丢时序触发信息是它最明显的问题之一。",
            "evidence": (
                f"在 {len(overlap_case_df)} 个重叠 case 中，summary 在 {lost_temporal_cases} 个 case 上 "
                f"出现 antecedent_hit 或 fail_on_buggy 下降；overlap-only 的 antecedent_hit_rate "
                f"从 {raw_overlap['antecedent_hit_rate']:.1%} 降到 {sum_overlap['antecedent_hit_rate']:.1%}，"
                f"fail_on_buggy_rate 从 {raw_overlap['fail_on_buggy_rate']:.1%} 降到 {sum_overlap['fail_on_buggy_rate']:.1%}。"
            ),
        }
    )
    question_rows.append(
        {
            "question": "trace summary 是否让 assertion 更保守？",
            "short_answer": "是，但这种保守往往伴随着 bug 检测下降。",
            "evidence": (
                f"在 {len(overlap_case_df)} 个重叠 case 中，有 {conservative_cases} 个 case 满足 "
                "summary 的 correct_pass 更高但 fail_on_buggy / antecedent_hit 更低；"
                f"overall_union 上 correct_pass_rate={sum_overall['correct_pass_rate']:.1%} 略高于 raw 的 "
                f"{raw_overall['correct_pass_rate']:.1%}，但 fail_on_buggy_rate 从 {raw_overall['fail_on_buggy_rate']:.1%} "
                f"降到 {sum_overall['fail_on_buggy_rate']:.1%}。"
            ),
        }
    )
    question_rows.append(
        {
            "question": "trace summary 是否提高 held-out generalization？",
            "short_answer": "没有，甚至整体更差。",
            "evidence": (
                f"overall_union 的 heldout_success_rate 从 raw 的 {raw_overall['heldout_success_rate']:.1%} 降到 "
                f"summary 的 {sum_overall['heldout_success_rate']:.1%}；overlap-only 也从 "
                f"{raw_overlap['heldout_success_rate']:.1%} 降到 {sum_overlap['heldout_success_rate']:.1%}。"
                f"虽然 trace_overfit_rate 从 {raw_overall['trace_overfit_rate']:.1%} 降到 {sum_overall['trace_overfit_rate']:.1%}，"
                f"但这没有换来更高的 held-out success；summary 真正优于 raw 的泛化 case 只有 {better_generalization_cases} 个。"
            ),
        }
    )
    questions_df = pd.DataFrame(question_rows)
    questions_df.to_csv(OUTPUT_DIR / "raw_vs_summary_questions.csv", index=False)

    conclusion_counts = (
        case_df["case_conclusion"].value_counts()
        .rename_axis("case_conclusion")
        .reset_index(name="case_count")
    )
    conclusion_counts.to_csv(OUTPUT_DIR / "raw_vs_summary_conclusion_counts.csv", index=False)

    summary = {
        "inventory_case_count": len(all_cases),
        "union_case_count": len(union_cases),
        "overlap_case_count": len(overlap_cases),
        "raw_only_case_count": len(raw_cases - summary_cases),
        "summary_only_case_count": len(summary_cases - raw_cases),
        "neither_present_case_count": len(set(all_cases) - (raw_cases | summary_cases)),
        "raw_only_cases": sorted(raw_cases - summary_cases),
        "summary_only_cases": sorted(summary_cases - raw_cases),
        "neither_present_cases": sorted(set(all_cases) - (raw_cases | summary_cases)),
        "question_answers": question_rows,
    }
    (OUTPUT_DIR / "raw_vs_summary_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(OUTPUT_DIR)
    print(OUTPUT_DIR / "raw_vs_summary_overall.csv")
    print(OUTPUT_DIR / "raw_vs_summary_case_comparison.csv")
    print(OUTPUT_DIR / "raw_vs_summary_questions.csv")


if __name__ == "__main__":
    main()
