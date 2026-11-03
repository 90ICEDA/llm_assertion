from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
THREAD_ID = "019ed9f6-87cf-7830-adb8-595fe2ae140d"
RAW_RECHECK = ROOT / "outputs" / THREAD_ID / "golden_recheck_raw.csv"
INVENTORY = ROOT / "docs" / "real_rtl_scaleout" / "dataset_inventory_30cases.csv"
CLEAN_MASTER = ROOT / "docs" / "real_rtl_scaleout" / "assertion_clean_master_iv12.csv"
OUTPUT_DIR = ROOT / "outputs" / THREAD_ID / "golden_analysis_data"

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
TEMPORAL_ORDER = [
    "same_cycle",
    "next_cycle",
    "multi_cycle_delay",
    "throughout_hold",
    "until_ready",
    "eventually",
    "stability",
    "onehot",
    "counter_boundary",
    "fifo_boundary",
    "fsm_transition",
]


def safe_bool_series(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series.fillna(False)
    lowered = series.fillna(False).astype(str).str.strip().str.lower()
    return lowered.isin(["true", "1", "yes"])


def clean_expr(text: str) -> str:
    text = str(text or "").strip()
    text = re.sub(r"\s+", " ", text)
    return text


def classify_temporal_type(row: pd.Series) -> str:
    case_name = str(row["case_name"])
    bug_type = str(row["bug_type"]).lower()
    assertion = str(row["assertion_line"])
    antecedent = str(row.get("antecedent_text", ""))
    consequent = str(row.get("consequent_text", ""))
    combined = " ".join([case_name.lower(), bug_type, assertion.lower(), antecedent.lower(), consequent.lower()])

    if "oh_i" in combined or "onehot" in combined:
        return "onehot"
    if any(token in combined for token in ["depth_o", "wptr_o", "rptr_o", "full_o", "empty_o", "fifo"]):
        return "fifo_boundary"
    if any(token in combined for token in ["counter-based", "thresh_i", "filter_ctr", "ctr_"]):
        return "counter_boundary"
    if any(token in combined for token in ["hold-until-clear", "not_sticky", "event_overwrite", "intr_event_not_sticky"]):
        return "throughout_hold"
    if "|=>" in assertion:
        return "next_cycle"
    if "state" in combined and "transition" in bug_type:
        return "fsm_transition"
    if "stable" in bug_type or "stale" in bug_type:
        return "same_cycle"
    return "same_cycle"


def explain_intent(row: pd.Series) -> str:
    ant = clean_expr(row.get("antecedent_text", ""))
    cons = clean_expr(row.get("consequent_text", ""))
    bug_type = str(row["bug_type"])
    temporal_type = str(row["temporal_type"])

    if temporal_type == "onehot":
        tail = "确保 onehot / 地址一致性检查不会把合法请求放过，也不会把非法请求漏掉。"
    elif temporal_type == "fifo_boundary":
        tail = "确保 FIFO 在空、满、清零和回绕等边界条件下状态一致。"
    elif temporal_type == "counter_boundary":
        tail = "确保计数阈值附近的接受/旁路行为不会早一拍或晚一拍。"
    elif temporal_type == "throughout_hold":
        tail = "确保状态一旦置位且保持条件仍成立，就不会提前掉下去。"
    elif temporal_type == "next_cycle":
        tail = "确保触发事件后的下一拍行为不会过早或过晚。"
    else:
        tail = "确保输出在当前采样拍就反映设计应有的边界或脉冲行为。"

    if ant and cons:
        return f"当 `{ant}` 时，`{cons}` 必须成立，以防止“{bug_type}”这类错误；它的设计意图是{tail}"
    return f"这条 golden assertion 用来防止“{bug_type}”这类错误；它的设计意图是{tail}"


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    golden_df = pd.read_csv(RAW_RECHECK)
    inventory_df = pd.read_csv(INVENTORY)
    clean_df = pd.read_csv(CLEAN_MASTER)

    bool_cols = [
        "compile_ok",
        "correct_pass",
        "fail_on_buggy",
        "antecedent_hit_correct",
        "antecedent_hit_buggy",
        "non_vacuous_correct",
        "non_vacuous_buggy",
        "heldout_correct_pass",
        "heldout_buggy_fail",
        "heldout_antecedent_hit",
        "golden_ok_strict",
    ]
    for col in bool_cols:
        golden_df[col] = safe_bool_series(golden_df[col])

    case_meta = inventory_df.rename(
        columns={
            "case_name": "case_name",
            "source_module": "module",
            "bug_type": "bug_name",
            "bug_class": "bug_class",
        }
    )[["case_name", "module", "bug_name", "bug_class"]]
    golden_df = golden_df.merge(case_meta, on="case_name", how="left")
    golden_df["temporal_type"] = golden_df.apply(classify_temporal_type, axis=1)
    golden_df["natural_language_intent"] = golden_df.apply(explain_intent, axis=1)
    golden_df["case_id"] = golden_df["case_name"]

    strict_cols = [
        "compile_ok",
        "correct_pass",
        "fail_on_buggy",
        "antecedent_hit_correct",
        "antecedent_hit_buggy",
        "non_vacuous_correct",
        "non_vacuous_buggy",
        "heldout_correct_pass",
        "heldout_buggy_fail",
        "heldout_antecedent_hit",
    ]
    golden_df["strict_check_all_true"] = golden_df[strict_cols].all(axis=1)

    clean_bool_cols = strict_cols
    for col in clean_bool_cols:
        clean_df[col] = safe_bool_series(clean_df[col])
    clean_df["llm_robust_success"] = clean_df[clean_bool_cols].all(axis=1)

    llm_success_rows = clean_df[clean_df["llm_robust_success"]].copy()
    llm_case_method = (
        llm_success_rows.groupby(["case_id", "method"], dropna=False)
        .size()
        .reset_index(name="robust_success_assertion_count")
    )

    llm_case_summary_rows = []
    for case_id, group in llm_case_method.groupby("case_id", dropna=False):
        row = {"case_id": case_id}
        any_success = False
        best_count = 0
        best_methods = []
        for method in METHOD_ORDER:
            count = int(group.loc[group["method"] == method, "robust_success_assertion_count"].sum())
            row[f"{method}_robust_success_count"] = count
            row[f"{method}_has_robust_success"] = count > 0
            if count > 0:
                any_success = True
            if count > best_count:
                best_count = count
                best_methods = [METHOD_LABEL[method]]
            elif count > 0 and count == best_count:
                best_methods.append(METHOD_LABEL[method])
        row["any_llm_robust_success"] = any_success
        row["best_llm_methods"] = ", ".join(best_methods)
        llm_case_summary_rows.append(row)
    llm_case_summary_df = pd.DataFrame(llm_case_summary_rows)

    golden_case_df = golden_df.merge(llm_case_summary_df, on="case_id", how="left")
    golden_case_df["llm_case_present"] = golden_case_df["case_id"].isin(clean_df["case_id"].unique())
    for method in METHOD_ORDER:
        for suffix in ["robust_success_count", "has_robust_success"]:
            col = f"{method}_{suffix}"
            if col not in golden_case_df.columns:
                golden_case_df[col] = 0 if suffix == "robust_success_count" else False
    golden_case_df["any_llm_robust_success"] = safe_bool_series(
        golden_case_df.get("any_llm_robust_success", pd.Series([False] * len(golden_case_df)))
    )
    golden_case_df["best_llm_methods"] = golden_case_df.get("best_llm_methods", "").fillna("")

    temporal_rows = []
    for temporal_type in TEMPORAL_ORDER:
        sub = golden_case_df[golden_case_df["temporal_type"] == temporal_type]
        if sub.empty:
            continue
        row = {
            "temporal_type": temporal_type,
            "golden_case_count": int(len(sub)),
            "strict_golden_pass_count": int(sub["strict_check_all_true"].sum()),
            "strict_golden_fail_count": int((~sub["strict_check_all_true"]).sum()),
            "llm_case_present_count": int(sub["llm_case_present"].sum()),
            "llm_missing_case_count": int((~sub["llm_case_present"]).sum()),
            "any_llm_robust_success_case_count": int(sub["any_llm_robust_success"].sum()),
        }
        row["llm_success_rate_vs_all_goldens"] = round(
            row["any_llm_robust_success_case_count"] / row["golden_case_count"], 4
        )
        row["llm_success_rate_vs_strict_goldens"] = round(
            (
                row["any_llm_robust_success_case_count"] / row["strict_golden_pass_count"]
                if row["strict_golden_pass_count"]
                else 0.0
            ),
            4,
        )
        row["gap_vs_all_goldens"] = row["golden_case_count"] - row["any_llm_robust_success_case_count"]
        row["gap_vs_strict_goldens"] = row["strict_golden_pass_count"] - row["any_llm_robust_success_case_count"]
        for method in METHOD_ORDER:
            row[f"{method}_success_case_count"] = int(sub[f"{method}_has_robust_success"].sum())
        temporal_rows.append(row)
    temporal_summary_df = pd.DataFrame(temporal_rows)
    temporal_summary_df["temporal_type"] = pd.Categorical(
        temporal_summary_df["temporal_type"], TEMPORAL_ORDER, ordered=True
    )
    temporal_summary_df = temporal_summary_df.sort_values("temporal_type").reset_index(drop=True)

    hardest_df = temporal_summary_df.sort_values(
        ["llm_success_rate_vs_strict_goldens", "gap_vs_strict_goldens", "golden_case_count"],
        ascending=[True, False, False],
    ).reset_index(drop=True)

    summary_payload = {
        "golden_case_count": int(len(golden_case_df)),
        "strict_golden_pass_count": int(golden_case_df["strict_check_all_true"].sum()),
        "strict_golden_fail_cases": golden_case_df.loc[
            ~golden_case_df["strict_check_all_true"], "case_id"
        ].tolist(),
        "llm_robust_success_case_count": int(golden_case_df["any_llm_robust_success"].sum()),
        "llm_missing_cases": golden_case_df.loc[
            ~golden_case_df["llm_case_present"], "case_id"
        ].tolist(),
        "hardest_temporal_types": hardest_df["temporal_type"].head(5).tolist(),
    }

    export_cols = [
        "case_id",
        "module",
        "bug_name",
        "bug_class",
        "bug_type",
        "temporal_type",
        "assertion_line",
        "antecedent_text",
        "consequent_text",
        "compile_ok",
        "correct_pass",
        "fail_on_buggy",
        "antecedent_hit_correct",
        "antecedent_hit_buggy",
        "non_vacuous_correct",
        "non_vacuous_buggy",
        "heldout_correct_pass",
        "heldout_buggy_fail",
        "heldout_antecedent_hit",
        "correct_antecedent_hits",
        "buggy_antecedent_hits",
        "heldout_correct_antecedent_hits",
        "heldout_buggy_antecedent_hits",
        "correct_fail_count",
        "buggy_fail_count",
        "heldout_correct_fail_count",
        "heldout_buggy_fail_count",
        "strict_check_all_true",
        "failure_reason",
        "natural_language_intent",
        "llm_case_present",
        "any_llm_robust_success",
        "best_llm_methods",
        "spec_only_robust_success_count",
        "spec_plus_rtl_robust_success_count",
        "spec_rtl_raw_trace_robust_success_count",
        "spec_rtl_trace_summary_robust_success_count",
    ]
    golden_case_df[export_cols].sort_values("case_id").to_csv(
        OUTPUT_DIR / "golden_selfcheck_full.csv", index=False, encoding="utf-8"
    )
    temporal_summary_df.to_csv(OUTPUT_DIR / "golden_temporal_type_summary.csv", index=False, encoding="utf-8")
    hardest_df.to_csv(OUTPUT_DIR / "golden_temporal_type_hardest.csv", index=False, encoding="utf-8")
    golden_case_df[
        [
            "case_id",
            "module",
            "bug_name",
            "bug_class",
            "temporal_type",
            "natural_language_intent",
        ]
    ].sort_values("case_id").to_csv(
        OUTPUT_DIR / "golden_explanations.csv", index=False, encoding="utf-8"
    )
    golden_case_df[
        [
            "case_id",
            "temporal_type",
            "strict_check_all_true",
            "failure_reason",
            "llm_case_present",
            "any_llm_robust_success",
            "best_llm_methods",
        ]
        + [f"{method}_has_robust_success" for method in METHOD_ORDER]
    ].sort_values("case_id").to_csv(
        OUTPUT_DIR / "golden_llm_gap_case_map.csv", index=False, encoding="utf-8"
    )
    (OUTPUT_DIR / "golden_summary.json").write_text(
        json.dumps(summary_payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(OUTPUT_DIR)


if __name__ == "__main__":
    main()
