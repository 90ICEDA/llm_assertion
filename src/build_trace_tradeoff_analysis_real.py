from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
THREAD_ID = "019ed9f6-87cf-7830-adb8-595fe2ae140d"
SOURCE_CLEAN = ROOT / "docs" / "real_rtl_scaleout" / "assertion_clean_master_iv12.csv"
INVENTORY = ROOT / "docs" / "real_rtl_scaleout" / "dataset_inventory_30cases.csv"
OUTPUT_DIR = ROOT / "outputs" / THREAD_ID / "trace_tradeoff_data"

METHOD_ORDER = [
    "spec_only",
    "spec_plus_rtl",
    "spec_rtl_raw_trace",
    "spec_rtl_trace_summary",
]
METHOD_LABEL = {
    "spec_only": "spec only",
    "spec_plus_rtl": "spec + RTL",
    "spec_rtl_raw_trace": "spec + RTL + raw trace",
    "spec_rtl_trace_summary": "spec + RTL + trace summary",
}
BUG_CLASS_PRIORITY = ["combination_same_cycle", "temporal_cross_cycle"]
METRICS = [
    ("correct_pass", "correct_pass"),
    ("fail_on_buggy", "fail_on_buggy"),
    ("antecedent_hit_buggy", "antecedent_hit"),
    ("non_vacuous_buggy", "non_vacuous"),
    ("heldout_success", "heldout_success"),
    ("trace_overfit", "trace_overfit"),
]


def ordered_bug_classes(values) -> list[str]:
    values = [str(v) for v in values if pd.notna(v) and str(v).strip()]
    seen: list[str] = []
    for cls in BUG_CLASS_PRIORITY:
        if cls in values and cls not in seen:
            seen.append(cls)
    for cls in sorted(values):
        if cls not in seen:
            seen.append(cls)
    return seen


def safe_bool_series(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series.fillna(False)
    lowered = series.fillna(False).astype(str).str.strip().str.lower()
    return lowered.isin(["true", "1", "yes"])


def int_or_none(value):
    if pd.isna(value):
        return None
    return int(value)


def build_case_note(row: pd.Series) -> str:
    correct_delta = int(row["delta_correct_pass_vs_spec_plus_rtl"])
    fail_delta = int(row["delta_fail_on_buggy_vs_spec_plus_rtl"])
    ant_delta = int(row["delta_antecedent_hit_vs_spec_plus_rtl"])
    heldout_delta = int(row["delta_heldout_success_vs_spec_plus_rtl"])
    overfit_delta = int(row["delta_trace_overfit_vs_spec_plus_rtl"])
    raw_overfit_delta = int(row["delta_trace_overfit_summary_vs_raw"])
    raw_literal_delta = int(row["delta_literal_hardcoding_summary_vs_raw"])

    pieces: list[str] = []
    if fail_delta > 0 and correct_delta < 0:
        pieces.append("trace summary 提升了 buggy 检测，但牺牲了 correct 通过率")
    elif fail_delta < 0 and correct_delta > 0:
        pieces.append("trace summary 更保守，correct 通过率上升，但 bug 检测能力下降")
    elif fail_delta > 0 and correct_delta >= 0:
        pieces.append("trace summary 同时改善了 bug 检测，且没有降低 correct 通过率")
    elif fail_delta < 0 and correct_delta <= 0:
        pieces.append("trace summary 同时损失了 correct/buggy 两侧效果")
    elif fail_delta == 0 and correct_delta > 0:
        pieces.append("trace summary 主要改善了 correct 侧稳定性")
    elif fail_delta == 0 and correct_delta < 0:
        pieces.append("trace summary 主要损伤了 correct 侧稳定性")
    elif fail_delta > 0 and correct_delta == 0:
        pieces.append("trace summary 在不影响 correct 的前提下提高了 bug 检测")
    elif fail_delta < 0 and correct_delta == 0:
        pieces.append("trace summary 在不改变 correct 的前提下降低了 bug 检测")
    else:
        pieces.append("trace summary 与 spec + RTL 基本持平")

    if ant_delta < 0:
        pieces.append("buggy 侧 antecedent 更少触发，像是摘要丢掉了触发条件")
    elif ant_delta > 0:
        pieces.append("buggy 侧 antecedent 触发更多，摘要帮助模型命中关键前提")

    if heldout_delta < 0:
        pieces.append("heldout 成功数下降，泛化变差")
    elif heldout_delta > 0:
        pieces.append("heldout 成功数上升，泛化更好")

    if overfit_delta > 0:
        pieces.append("相对 spec + RTL 新增了 trace_overfit 标记")

    if raw_overfit_delta < 0:
        pieces.append("raw trace 的过拟合比摘要更重")
    elif raw_literal_delta < 0:
        pieces.append("raw trace 至少表现出更强的 literal hardcoding 倾向")

    return "；".join(pieces) + "。"


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(SOURCE_CLEAN)
    inventory_df = pd.read_csv(INVENTORY)
    bool_columns = [
        "correct_pass",
        "fail_on_buggy",
        "antecedent_hit_buggy",
        "non_vacuous_buggy",
        "heldout_correct_pass",
        "heldout_buggy_fail",
        "trace_overfit",
        "literal_hardcoding",
    ]
    for col in bool_columns:
        df[col] = safe_bool_series(df[col])

    df["heldout_success"] = df["heldout_correct_pass"] & df["heldout_buggy_fail"]
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

    bug_class_order = ordered_bug_classes(case_meta["bug_class"].dropna().unique().tolist())

    metric_cols = [col for col, _alias in METRICS]
    overall_by_method = (
        df.groupby(["method", "method_label"], dropna=False)[metric_cols + ["literal_hardcoding"]]
        .sum()
        .reset_index()
    )
    overall_by_method["method"] = pd.Categorical(overall_by_method["method"], METHOD_ORDER, ordered=True)
    overall_by_method = overall_by_method.sort_values("method").reset_index(drop=True)

    overall_metric_rows = []
    for metric, metric_short in METRICS:
        lookup = overall_by_method.set_index("method")[metric]
        baseline = int(lookup.get("spec_plus_rtl", 0))
        summary = int(lookup.get("spec_rtl_trace_summary", 0))
        raw = int(lookup.get("spec_rtl_raw_trace", 0))
        spec_only = int(lookup.get("spec_only", 0))
        overall_metric_rows.append(
            {
                "metric": metric_short,
                "spec_only_count": spec_only,
                "spec_plus_rtl_count": baseline,
                "spec_rtl_raw_trace_count": raw,
                "spec_rtl_trace_summary_count": summary,
                "delta_summary_minus_spec_plus_rtl": summary - baseline,
                "delta_summary_minus_raw_trace": summary - raw,
            }
        )
    overall_metric_df = pd.DataFrame(overall_metric_rows)

    by_bug_class_method = (
        df.groupby(["bug_class", "method", "method_label"], dropna=False)[metric_cols + ["literal_hardcoding"]]
        .sum()
        .reset_index()
    )
    by_bug_class_method["bug_class"] = pd.Categorical(
        by_bug_class_method["bug_class"], bug_class_order, ordered=True
    )
    by_bug_class_method["method"] = pd.Categorical(
        by_bug_class_method["method"], METHOD_ORDER, ordered=True
    )
    by_bug_class_method = by_bug_class_method.sort_values(["bug_class", "method"]).reset_index(drop=True)

    bug_metric_rows = []
    for bug_class in bug_class_order:
        sub = by_bug_class_method[by_bug_class_method["bug_class"] == bug_class].set_index("method")
        for metric, metric_short in METRICS:
            baseline = int(sub[metric].get("spec_plus_rtl", 0))
            summary = int(sub[metric].get("spec_rtl_trace_summary", 0))
            raw = int(sub[metric].get("spec_rtl_raw_trace", 0))
            spec_only = int(sub[metric].get("spec_only", 0))
            bug_metric_rows.append(
                {
                    "bug_class": bug_class,
                    "metric": metric_short,
                    "spec_only_count": spec_only,
                    "spec_plus_rtl_count": baseline,
                    "spec_rtl_raw_trace_count": raw,
                    "spec_rtl_trace_summary_count": summary,
                    "delta_summary_minus_spec_plus_rtl": summary - baseline,
                    "delta_summary_minus_raw_trace": summary - raw,
                }
            )
    bug_metric_df = pd.DataFrame(bug_metric_rows)

    case_method = (
        df.groupby(["case_id", "module", "bug_name", "bug_class", "method", "method_label"], dropna=False)[
            metric_cols + ["literal_hardcoding"]
        ]
        .sum()
        .reset_index()
    )
    case_grid = (
        case_meta.assign(key=1)
        .merge(pd.DataFrame({"method": METHOD_ORDER, "key": 1}), on="key", how="outer")
        .drop(columns="key")
    )
    case_grid["method_label"] = case_grid["method"].map(METHOD_LABEL)
    case_method = case_grid.merge(
        case_method,
        on=["case_id", "module", "bug_name", "bug_class", "method", "method_label"],
        how="left",
    )
    for col in metric_cols + ["literal_hardcoding"]:
        case_method[col] = case_method[col].fillna(0).astype(int)
    case_method["method"] = pd.Categorical(case_method["method"], METHOD_ORDER, ordered=True)
    case_method["bug_class"] = pd.Categorical(case_method["bug_class"], bug_class_order, ordered=True)
    case_method = case_method.sort_values(["case_id", "method"]).reset_index(drop=True)

    case_rows = []
    for (case_id, module, bug_name, bug_class), group in case_method.groupby(
        ["case_id", "module", "bug_name", "bug_class"], dropna=False
    ):
        pivot = group.set_index("method")
        row = {
            "case_id": case_id,
            "module": module,
            "bug_name": bug_name,
            "bug_class": str(bug_class),
        }
        for method in METHOD_ORDER:
            for metric, metric_short in METRICS:
                row[f"{method}_{metric_short}"] = int(pivot[metric].get(method, 0))
            row[f"{method}_literal_hardcoding"] = int(pivot["literal_hardcoding"].get(method, 0))

        for metric_short in [alias for _metric, alias in METRICS]:
            row[f"delta_{metric_short}_vs_spec_plus_rtl"] = (
                row[f"spec_rtl_trace_summary_{metric_short}"] - row[f"spec_plus_rtl_{metric_short}"]
            )
            row[f"delta_{metric_short}_summary_vs_raw"] = (
                row[f"spec_rtl_trace_summary_{metric_short}"] - row[f"spec_rtl_raw_trace_{metric_short}"]
            )
        row["delta_literal_hardcoding_vs_spec_plus_rtl"] = (
            row["spec_rtl_trace_summary_literal_hardcoding"] - row["spec_plus_rtl_literal_hardcoding"]
        )
        row["delta_literal_hardcoding_summary_vs_raw"] = (
            row["spec_rtl_trace_summary_literal_hardcoding"] - row["spec_rtl_raw_trace_literal_hardcoding"]
        )
        row["raw_trace_more_trace_overfit_than_summary"] = (
            row["spec_rtl_raw_trace_trace_overfit"] > row["spec_rtl_trace_summary_trace_overfit"]
        )
        row["raw_trace_more_literal_hardcoding_than_summary"] = (
            row["spec_rtl_raw_trace_literal_hardcoding"] > row["spec_rtl_trace_summary_literal_hardcoding"]
        )
        row["summary_lost_useful_info_vs_spec_plus_rtl"] = (
            row["delta_fail_on_buggy_vs_spec_plus_rtl"] < 0
            or row["delta_antecedent_hit_vs_spec_plus_rtl"] < 0
            or row["delta_heldout_success_vs_spec_plus_rtl"] < 0
        )
        row["summary_helped_bug_detection_but_hurt_correct"] = (
            row["delta_fail_on_buggy_vs_spec_plus_rtl"] > 0
            and row["delta_correct_pass_vs_spec_plus_rtl"] < 0
        )
        row["summary_helped_correct_but_hurt_bug_detection"] = (
            row["delta_correct_pass_vs_spec_plus_rtl"] > 0
            and row["delta_fail_on_buggy_vs_spec_plus_rtl"] < 0
        )
        row["case_note"] = build_case_note(pd.Series(row))
        case_rows.append(row)

    case_tradeoff_df = pd.DataFrame(case_rows).sort_values(["bug_class", "case_id"]).reset_index(drop=True)

    contributor_rows = []
    for bug_class in bug_class_order:
        sub = case_tradeoff_df[case_tradeoff_df["bug_class"] == bug_class]
        for metric_short in [alias for _metric, alias in METRICS]:
            delta_col = f"delta_{metric_short}_vs_spec_plus_rtl"
            pos = (
                sub[sub[delta_col] > 0][["case_id", delta_col]]
                .sort_values(delta_col, ascending=False)
                .rename(columns={delta_col: "delta"})
            )
            neg = (
                sub[sub[delta_col] < 0][["case_id", delta_col]]
                .sort_values(delta_col, ascending=True)
                .rename(columns={delta_col: "delta"})
            )
            for direction, frame in [("positive", pos), ("negative", neg)]:
                for _idx, item in frame.iterrows():
                    contributor_rows.append(
                        {
                            "bug_class": bug_class,
                            "metric": metric_short,
                            "direction": direction,
                            "case_id": item["case_id"],
                            "delta": int(item["delta"]),
                        }
                    )
    contributor_df = pd.DataFrame(contributor_rows)

    signal_rows = []
    for bug_class in bug_class_order:
        sub = bug_metric_df[bug_metric_df["bug_class"] == bug_class].set_index("metric")
        correct_delta = int(sub.loc["correct_pass", "delta_summary_minus_spec_plus_rtl"])
        fail_delta = int(sub.loc["fail_on_buggy", "delta_summary_minus_spec_plus_rtl"])
        antecedent_delta = int(sub.loc["antecedent_hit", "delta_summary_minus_spec_plus_rtl"])
        non_vacuous_delta = int(sub.loc["non_vacuous", "delta_summary_minus_spec_plus_rtl"])
        heldout_delta = int(sub.loc["heldout_success", "delta_summary_minus_spec_plus_rtl"])
        overfit_delta = int(sub.loc["trace_overfit", "delta_summary_minus_spec_plus_rtl"])
        signal_rows.append(
            {
                "bug_class": bug_class,
                "correct_pass_delta": correct_delta,
                "fail_on_buggy_delta": fail_delta,
                "antecedent_hit_delta": antecedent_delta,
                "non_vacuous_delta": non_vacuous_delta,
                "heldout_success_delta": heldout_delta,
                "trace_overfit_delta": overfit_delta,
                "correct_up_fail_down": correct_delta > 0 and fail_delta < 0,
                "fail_up_correct_down": fail_delta > 0 and correct_delta < 0,
                "trace_summary_more_conservative": correct_delta > 0 and fail_delta <= 0,
                "trace_summary_more_aggressive": fail_delta > 0 and correct_delta <= 0,
            }
        )
    signal_df = pd.DataFrame(signal_rows)

    summary_payload = {
        "source_clean_master": str(SOURCE_CLEAN),
        "inventory_csv": str(INVENTORY),
        "row_count": int(len(df)),
        "case_count": int(case_tradeoff_df["case_id"].nunique()),
        "bug_classes": bug_class_order,
        "metric_definition": {
            "correct_pass": "assertion passes on correct design",
            "fail_on_buggy": "assertion fails on buggy design and therefore detects the bug",
            "antecedent_hit": "uses antecedent_hit_buggy for tradeoff analysis",
            "non_vacuous": "uses non_vacuous_buggy for tradeoff analysis",
            "heldout_success": "heldout_correct_pass == 1 and heldout_buggy_fail == 1",
            "trace_overfit": "clean assertion is marked as trace_overfit",
        },
        "overall_delta_summary_minus_spec_plus_rtl": {
            row["metric"]: int(row["delta_summary_minus_spec_plus_rtl"])
            for row in overall_metric_df.to_dict("records")
        },
        "bug_classes_correct_up_fail_down": signal_df.loc[
            signal_df["correct_up_fail_down"], "bug_class"
        ].tolist(),
        "bug_classes_fail_up_correct_down": signal_df.loc[
            signal_df["fail_up_correct_down"], "bug_class"
        ].tolist(),
        "raw_trace_more_overfit_cases": case_tradeoff_df.loc[
            case_tradeoff_df["raw_trace_more_trace_overfit_than_summary"], "case_id"
        ].tolist(),
        "raw_trace_more_literal_hardcoding_cases": case_tradeoff_df.loc[
            case_tradeoff_df["raw_trace_more_literal_hardcoding_than_summary"], "case_id"
        ].tolist(),
        "summary_lost_useful_info_cases": case_tradeoff_df.loc[
            case_tradeoff_df["summary_lost_useful_info_vs_spec_plus_rtl"], "case_id"
        ].tolist(),
        "summary_helped_bug_detection_but_hurt_correct_cases": case_tradeoff_df.loc[
            case_tradeoff_df["summary_helped_bug_detection_but_hurt_correct"], "case_id"
        ].tolist(),
        "summary_helped_correct_but_hurt_bug_detection_cases": case_tradeoff_df.loc[
            case_tradeoff_df["summary_helped_correct_but_hurt_bug_detection"], "case_id"
        ].tolist(),
    }

    overall_by_method.to_csv(OUTPUT_DIR / "tradeoff_overall_by_method.csv", index=False, encoding="utf-8")
    overall_metric_df.to_csv(OUTPUT_DIR / "tradeoff_overall_metric_delta.csv", index=False, encoding="utf-8")
    by_bug_class_method.to_csv(OUTPUT_DIR / "tradeoff_by_bug_class_method.csv", index=False, encoding="utf-8")
    bug_metric_df.to_csv(OUTPUT_DIR / "tradeoff_by_bug_class_metric_delta.csv", index=False, encoding="utf-8")
    signal_df.to_csv(OUTPUT_DIR / "tradeoff_bug_class_signals.csv", index=False, encoding="utf-8")
    case_method.to_csv(OUTPUT_DIR / "tradeoff_case_method_counts.csv", index=False, encoding="utf-8")
    case_tradeoff_df.to_csv(OUTPUT_DIR / "tradeoff_case_delta.csv", index=False, encoding="utf-8")
    contributor_df.to_csv(OUTPUT_DIR / "tradeoff_case_contributors.csv", index=False, encoding="utf-8")
    (OUTPUT_DIR / "trace_tradeoff_summary.json").write_text(
        json.dumps(summary_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(OUTPUT_DIR)


if __name__ == "__main__":
    main()
