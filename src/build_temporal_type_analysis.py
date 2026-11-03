from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
THREAD_ID = "019ed9f6-87cf-7830-adb8-595fe2ae140d"
SOURCE_CLEAN = ROOT / "docs" / "real_rtl_scaleout" / "assertion_clean_master_iv12.csv"
OUTPUT_DIR = ROOT / "outputs" / THREAD_ID / "temporal_type_analysis_data"

TEMPORAL_ORDER = [
    "multi_cycle_delay",
    "hold_until_ready",
    "stability",
    "counter_boundary",
    "fifo_boundary",
    "onehot",
    "fsm_transition",
]
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
CASE_TEMPORAL_TYPE = {
    "case101_prim_onehot_multihot_suppressed": "onehot",
    "case102_prim_onehot_enable_mismatch_suppressed": "onehot",
    "case103_prim_onehot_addr_mismatch_suppressed": "onehot",
    "case104_prim_fifo_full_early": "fifo_boundary",
    "case105_prim_fifo_empty_late": "fifo_boundary",
    "case106_prim_fifo_depth_off_by_one": "fifo_boundary",
    "case110_prim_intr_event_overwrite": "hold_until_ready",
    "case111_prim_intr_output_or_mask": "stability",
    "case112_prim_intr_test_pulse_dropped": "multi_cycle_delay",
    "case113_prim_edge_posedge_misdecoded": "fsm_transition",
    "case114_prim_edge_negedge_misdecoded": "fsm_transition",
    "case115_prim_edge_both_edges_collapsed": "fsm_transition",
    "case116_prim_filter_late_accept": "multi_cycle_delay",
    "case117_prim_filter_bypass_stale": "stability",
    "case118_prim_filter_ctr_early_accept": "counter_boundary",
    "case119_prim_filter_ctr_late_accept": "counter_boundary",
    "case120_prim_filter_ctr_bypass_stale": "counter_boundary",
    "case124_prim_fifo_clear_ignored": "fifo_boundary",
    "case125_prim_fifo_wrap_late": "fifo_boundary",
    "case126_prim_regwe_enable_gap": "onehot",
    "case128_prim_intr_event_mask_stall": "multi_cycle_delay",
    "case129_prim_onehot_zero_enabled_suppressed": "onehot",
    "case130_prim_fifo_empty_early": "fifo_boundary",
    "case131_prim_filter_disabled_bypass_stale_alt": "stability",
    "case132_prim_edge_posedge_missing": "fsm_transition",
    "case133_prim_edge_negedge_missing": "fsm_transition",
    "case134_prim_intr_event_not_sticky": "hold_until_ready",
    "case135_prim_intr_enable_mask_ignored": "stability",
    "case136_prim_filter_ctr_disabled_bypass_stale_alt": "counter_boundary",
    "case137_prim_onehot_addr_false_positive": "onehot",
}
CURATED_EXAMPLES = {
    "multi_cycle_delay": {
        "case_id": "case112_prim_intr_test_pulse_dropped",
        "method": "spec_rtl_trace_summary",
        "failure_type": "antecedent_not_triggered",
    },
    "hold_until_ready": {
        "case_id": "case134_prim_intr_event_not_sticky",
        "method": "spec_plus_rtl",
        "failure_type": "false_positive_on_correct",
    },
    "stability": {
        "case_id": "case111_prim_intr_output_or_mask",
        "method": "spec_only",
        "failure_type": "false_positive_on_correct",
    },
    "counter_boundary": {
        "case_id": "case118_prim_filter_ctr_early_accept",
        "method": "spec_only",
        "failure_type": "bug_not_detected_on_buggy",
    },
    "fifo_boundary": {
        "case_id": "case104_prim_fifo_full_early",
        "method": "spec_rtl_trace_summary",
        "failure_type": "false_positive_on_correct",
    },
    "onehot": {
        "case_id": "case101_prim_onehot_multihot_suppressed",
        "method": "spec_rtl_raw_trace",
        "failure_type": "antecedent_not_triggered",
    },
    "fsm_transition": {
        "case_id": "case113_prim_edge_posedge_misdecoded",
        "method": "spec_only",
        "failure_type": "antecedent_not_triggered",
    },
}


def safe_bool_series(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series.fillna(False)
    lowered = series.fillna(False).astype(str).str.strip().str.lower()
    return lowered.isin(["true", "1", "yes"])


def clean_text(text: str) -> str:
    return " ".join(str(text or "").strip().split())


def rate(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round(numerator / denominator, 4)


def build_example_note(row: pd.Series) -> str:
    temporal_type = str(row["temporal_type"])
    failure_type = str(row.get("failure_type", "") or "")
    failure_reason = clean_text(row.get("failure_reason", ""))
    method_label = METHOD_LABEL.get(str(row["method"]), str(row["method"]))

    lead = f"{row['case_id']} 的 {method_label} 断言失败在于："
    if temporal_type == "multi_cycle_delay":
        body = (
            "模型知道这里需要跨拍约束，但把 antecedent 写成只在 seen trace 局部快照里出现的瞬时条件，"
            "buggy trace 上根本打不到真正的触发窗口，所以最后是 vacuous miss。"
        )
    elif temporal_type == "hold_until_ready":
        body = (
            "模型把“事件置位后应持续保持到清除/ready”为止的时序语义压缩成同拍蕴含，"
            "结果要么误伤 correct，要么覆盖不到真正的保持区间。"
        )
    elif temporal_type == "stability":
        body = (
            "模型把稳定性/掩码语义写成了一个过宽的当前拍输出条件，"
            "没有表达‘不该变化’或‘应保持不变’的历史约束，因此容易误伤 correct。"
        )
    elif temporal_type == "counter_boundary":
        body = (
            "模型虽然抓到阈值相关信号，但没有把 early/late accept 的精确边界时序写出来，"
            "而是退化成常数比较或同值检查，所以断言太弱，buggy 侧区分不出来。"
        )
    elif temporal_type == "fifo_boundary":
        body = (
            "模型被 FIFO 边界附近的局部数值吸住，把 seen trace 中的 depth/full 关系直接写死，"
            "既不泛化，也不能稳定表达真正的空满边界规律。"
        )
    elif temporal_type == "onehot":
        body = (
            "模型常把 onehot 语义写成 seen trace 值枚举或过度收紧的组合条件，"
            "导致 antecedent 在 buggy/held-out 上不再触发，或者直接出现 literal overfit。"
        )
    elif temporal_type == "fsm_transition":
        body = (
            "模型把边沿/FSM 转移类 bug 写成当前拍状态快照，而不是前后拍之间的转移关系，"
            "所以 antecedent 常常命不中真正的状态变化。"
        )
    else:
        body = "模型没有把该类设计意图写成能稳定区分 correct/buggy 的时序约束。"

    tail_bits: list[str] = []
    if failure_type:
        tail_bits.append(f"failure_type={failure_type}")
    if failure_reason:
        tail_bits.append(f"failure_reason={failure_reason}")
    if not bool(row["compile_ok"]):
        tail_bits.append("该断言甚至没有通过编译")
    elif not bool(row["correct_pass"]) and bool(row["fail_on_buggy"]):
        tail_bits.append("它会误伤 correct")
    elif bool(row["correct_pass"]) and not bool(row["fail_on_buggy"]):
        tail_bits.append("它在 buggy 侧没有形成有效区分")
    elif not bool(row["correct_pass"]) and not bool(row["fail_on_buggy"]):
        tail_bits.append("它同时误伤 correct 且抓不到 buggy")
    if not bool(row["antecedent_hit_buggy"]):
        tail_bits.append("buggy trace 上 antecedent 没有触发")
    if bool(row["trace_overfit"]):
        tail_bits.append("并且带有 trace-overfit 标记")
    if bool(row["literal_hardcoding"]):
        tail_bits.append("还能看到 literal hardcoding 倾向")
    tail = "；".join(tail_bits)
    return f"{lead}{body}" + (f" 具体表现为：{tail}。" if tail else "")


def pick_example(type_df: pd.DataFrame, temporal_type: str) -> pd.Series:
    preference = CURATED_EXAMPLES[temporal_type]
    curated = type_df[
        (type_df["case_id"] == preference["case_id"])
        & (type_df["method"] == preference["method"])
        & (type_df["failure_type"] == preference["failure_type"])
    ]
    if not curated.empty:
        return curated.iloc[0]

    ranked = type_df.copy()
    ranked["has_failure_reason"] = ranked["failure_reason"].fillna("").astype(str).str.len() > 0
    ranked["compile_fail_rank"] = (~ranked["compile_ok"]).astype(int)
    ranked["focus_method_rank"] = ranked["method"].map(
        {
            "spec_rtl_trace_summary": 4,
            "spec_rtl_raw_trace": 3,
            "spec_plus_rtl": 2,
            "spec_only": 1,
        }
    ).fillna(0)
    ranked["failure_rank"] = ranked["failure_type"].map(
        {
            "compile_fail": 6,
            "false_positive_on_correct": 5,
            "bug_not_detected_on_buggy": 4,
            "antecedent_not_triggered": 3,
            "vacuous": 2,
        }
    ).fillna(1)
    ranked = ranked.sort_values(
        ["has_failure_reason", "compile_fail_rank", "focus_method_rank", "failure_rank"],
        ascending=[False, False, False, False],
    )
    return ranked.iloc[0]


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(SOURCE_CLEAN)
    bool_columns = [
        "compile_ok",
        "correct_pass",
        "fail_on_buggy",
        "antecedent_hit_buggy",
        "heldout_correct_pass",
        "heldout_buggy_fail",
        "trace_overfit",
        "literal_hardcoding",
    ]
    for col in bool_columns:
        df[col] = safe_bool_series(df[col])

    df["temporal_type"] = df["case_id"].map(CASE_TEMPORAL_TYPE)
    missing_cases = sorted(df.loc[df["temporal_type"].isna(), "case_id"].dropna().unique().tolist())
    if missing_cases:
        raise ValueError(f"Missing temporal_type mapping for: {missing_cases}")

    df["method_label"] = df["method"].map(METHOD_LABEL).fillna(df["method"])
    df["antecedent_hit"] = df["antecedent_hit_buggy"]
    df["vacuity"] = ~df["antecedent_hit_buggy"]
    df["vacuous_fail"] = (~df["fail_on_buggy"]) & (~df["antecedent_hit_buggy"])
    df["heldout_success"] = df["heldout_correct_pass"] & df["heldout_buggy_fail"]
    df["failure_flag"] = (~df["compile_ok"]) | (~df["correct_pass"]) | (~df["fail_on_buggy"])
    df["robust_success"] = (
        df["compile_ok"]
        & df["correct_pass"]
        & df["fail_on_buggy"]
        & df["antecedent_hit_buggy"]
        & df["heldout_success"]
        & (~df["trace_overfit"])
    )

    by_type_rows = []
    for temporal_type in TEMPORAL_ORDER:
        sub = df[df["temporal_type"] == temporal_type].copy()
        if sub.empty:
            continue
        assertion_count = int(len(sub))
        case_count = int(sub["case_id"].nunique())
        compile_ok_count = int(sub["compile_ok"].sum())
        correct_pass_count = int(sub["correct_pass"].sum())
        fail_on_buggy_count = int(sub["fail_on_buggy"].sum())
        antecedent_hit_count = int(sub["antecedent_hit"].sum())
        vacuity_count = int(sub["vacuity"].sum())
        vacuous_fail_count = int(sub["vacuous_fail"].sum())
        heldout_success_count = int(sub["heldout_success"].sum())
        trace_overfit_count = int(sub["trace_overfit"].sum())
        robust_success_count = int(sub["robust_success"].sum())
        compile_fail_count = assertion_count - compile_ok_count

        by_type_rows.append(
            {
                "temporal_type": temporal_type,
                "case_count": case_count,
                "assertion_count": assertion_count,
                "compile_ok_count": compile_ok_count,
                "compile_ok_rate": rate(compile_ok_count, assertion_count),
                "compile_fail_count": compile_fail_count,
                "correct_pass_count": correct_pass_count,
                "correct_pass_rate": rate(correct_pass_count, assertion_count),
                "fail_on_buggy_count": fail_on_buggy_count,
                "fail_on_buggy_rate": rate(fail_on_buggy_count, assertion_count),
                "antecedent_hit_count": antecedent_hit_count,
                "antecedent_hit_rate": rate(antecedent_hit_count, assertion_count),
                "vacuity_count": vacuity_count,
                "vacuity_rate": rate(vacuity_count, assertion_count),
                "vacuous_fail_count": vacuous_fail_count,
                "vacuous_fail_rate": rate(vacuous_fail_count, assertion_count),
                "heldout_success_count": heldout_success_count,
                "heldout_success_rate": rate(heldout_success_count, assertion_count),
                "trace_overfit_count": trace_overfit_count,
                "trace_overfit_rate": rate(trace_overfit_count, assertion_count),
                "literal_hardcoding_count": int(sub["literal_hardcoding"].sum()),
                "robust_success_count": robust_success_count,
                "robust_success_rate": rate(robust_success_count, assertion_count),
                "failure_assertion_count": int(sub["failure_flag"].sum()),
            }
        )
    by_type_df = pd.DataFrame(by_type_rows)
    by_type_df["rank_fail_on_buggy_rate_asc"] = (
        by_type_df["fail_on_buggy_rate"].rank(method="dense", ascending=True).astype(int)
    )
    by_type_df["rank_heldout_success_rate_asc"] = (
        by_type_df["heldout_success_rate"].rank(method="dense", ascending=True).astype(int)
    )
    by_type_df["rank_vacuity_rate_desc"] = (
        by_type_df["vacuity_rate"].rank(method="dense", ascending=False).astype(int)
    )
    by_type_df = by_type_df.sort_values(
        ["rank_fail_on_buggy_rate_asc", "rank_heldout_success_rate_asc", "rank_vacuity_rate_desc", "temporal_type"]
    ).reset_index(drop=True)
    by_type_df.to_csv(OUTPUT_DIR / "temporal_type_overall.csv", index=False)

    grouped = (
        df.groupby(["temporal_type", "method", "method_label"], dropna=False)
        .agg(
            case_count=("case_id", "nunique"),
            assertion_count=("case_id", "size"),
            compile_ok_count=("compile_ok", "sum"),
            correct_pass_count=("correct_pass", "sum"),
            fail_on_buggy_count=("fail_on_buggy", "sum"),
            antecedent_hit_count=("antecedent_hit", "sum"),
            vacuity_count=("vacuity", "sum"),
            vacuous_fail_count=("vacuous_fail", "sum"),
            heldout_success_count=("heldout_success", "sum"),
            trace_overfit_count=("trace_overfit", "sum"),
            literal_hardcoding_count=("literal_hardcoding", "sum"),
            robust_success_count=("robust_success", "sum"),
        )
        .reset_index()
    )
    grouped["compile_ok_rate"] = grouped.apply(
        lambda row: rate(int(row["compile_ok_count"]), int(row["assertion_count"])), axis=1
    )
    grouped["correct_pass_rate"] = grouped.apply(
        lambda row: rate(int(row["correct_pass_count"]), int(row["assertion_count"])), axis=1
    )
    grouped["fail_on_buggy_rate"] = grouped.apply(
        lambda row: rate(int(row["fail_on_buggy_count"]), int(row["assertion_count"])), axis=1
    )
    grouped["antecedent_hit_rate"] = grouped.apply(
        lambda row: rate(int(row["antecedent_hit_count"]), int(row["assertion_count"])), axis=1
    )
    grouped["vacuity_rate"] = grouped.apply(
        lambda row: rate(int(row["vacuity_count"]), int(row["assertion_count"])), axis=1
    )
    grouped["vacuous_fail_rate"] = grouped.apply(
        lambda row: rate(int(row["vacuous_fail_count"]), int(row["assertion_count"])), axis=1
    )
    grouped["heldout_success_rate"] = grouped.apply(
        lambda row: rate(int(row["heldout_success_count"]), int(row["assertion_count"])), axis=1
    )
    grouped["trace_overfit_rate"] = grouped.apply(
        lambda row: rate(int(row["trace_overfit_count"]), int(row["assertion_count"])), axis=1
    )
    grouped["robust_success_rate"] = grouped.apply(
        lambda row: rate(int(row["robust_success_count"]), int(row["assertion_count"])), axis=1
    )
    grouped["compile_fail_count"] = grouped["assertion_count"] - grouped["compile_ok_count"]
    grouped["temporal_type"] = pd.Categorical(grouped["temporal_type"], TEMPORAL_ORDER, ordered=True)
    grouped["method"] = pd.Categorical(grouped["method"], METHOD_ORDER, ordered=True)
    grouped = grouped.sort_values(["temporal_type", "method"]).reset_index(drop=True)
    grouped.to_csv(OUTPUT_DIR / "temporal_type_by_method.csv", index=False)

    case_method = (
        df.groupby(["temporal_type", "case_id", "module", "bug_name", "bug_class", "method", "method_label"], dropna=False)
        .agg(
            assertion_count=("case_id", "size"),
            compile_ok_count=("compile_ok", "sum"),
            correct_pass_count=("correct_pass", "sum"),
            fail_on_buggy_count=("fail_on_buggy", "sum"),
            antecedent_hit_count=("antecedent_hit", "sum"),
            vacuity_count=("vacuity", "sum"),
            heldout_success_count=("heldout_success", "sum"),
            trace_overfit_count=("trace_overfit", "sum"),
            robust_success_count=("robust_success", "sum"),
        )
        .reset_index()
    )
    case_method["compile_ok_rate"] = case_method.apply(
        lambda row: rate(int(row["compile_ok_count"]), int(row["assertion_count"])), axis=1
    )
    case_method["correct_pass_rate"] = case_method.apply(
        lambda row: rate(int(row["correct_pass_count"]), int(row["assertion_count"])), axis=1
    )
    case_method["fail_on_buggy_rate"] = case_method.apply(
        lambda row: rate(int(row["fail_on_buggy_count"]), int(row["assertion_count"])), axis=1
    )
    case_method["antecedent_hit_rate"] = case_method.apply(
        lambda row: rate(int(row["antecedent_hit_count"]), int(row["assertion_count"])), axis=1
    )
    case_method["vacuity_rate"] = case_method.apply(
        lambda row: rate(int(row["vacuity_count"]), int(row["assertion_count"])), axis=1
    )
    case_method["heldout_success_rate"] = case_method.apply(
        lambda row: rate(int(row["heldout_success_count"]), int(row["assertion_count"])), axis=1
    )
    case_method["trace_overfit_rate"] = case_method.apply(
        lambda row: rate(int(row["trace_overfit_count"]), int(row["assertion_count"])), axis=1
    )
    case_method["temporal_type"] = pd.Categorical(case_method["temporal_type"], TEMPORAL_ORDER, ordered=True)
    case_method["method"] = pd.Categorical(case_method["method"], METHOD_ORDER, ordered=True)
    case_method = case_method.sort_values(["temporal_type", "case_id", "method"]).reset_index(drop=True)
    case_method.to_csv(OUTPUT_DIR / "temporal_type_case_method.csv", index=False)

    failures = df[df["failure_flag"]].copy()
    failures["failure_type"] = failures["failure_type"].fillna("unknown")
    failure_breakdown = (
        failures.groupby(["temporal_type", "failure_type"], dropna=False)
        .size()
        .reset_index(name="assertion_count")
    )
    total_by_type = failure_breakdown.groupby("temporal_type")["assertion_count"].transform("sum")
    failure_breakdown["share_within_temporal_type_failure"] = (
        failure_breakdown["assertion_count"] / total_by_type
    ).round(4)
    failure_breakdown["temporal_type"] = pd.Categorical(
        failure_breakdown["temporal_type"], TEMPORAL_ORDER, ordered=True
    )
    failure_breakdown = failure_breakdown.sort_values(
        ["temporal_type", "assertion_count", "failure_type"], ascending=[True, False, True]
    ).reset_index(drop=True)
    failure_breakdown.to_csv(OUTPUT_DIR / "temporal_type_failure_breakdown.csv", index=False)

    example_rows = []
    for temporal_type in TEMPORAL_ORDER:
        type_failures = failures[failures["temporal_type"] == temporal_type].copy()
        if type_failures.empty:
            continue
        picked = pick_example(type_failures, temporal_type).copy()
        example_rows.append(
            {
                "temporal_type": temporal_type,
                "case_id": picked["case_id"],
                "module": picked["module"],
                "bug_name": picked["bug_name"],
                "bug_class": picked["bug_class"],
                "method": picked["method"],
                "method_label": METHOD_LABEL.get(str(picked["method"]), str(picked["method"])),
                "assertion_text": clean_text(picked["assertion_text"]),
                "compile_ok": bool(picked["compile_ok"]),
                "correct_pass": bool(picked["correct_pass"]),
                "fail_on_buggy": bool(picked["fail_on_buggy"]),
                "antecedent_hit": bool(picked["antecedent_hit_buggy"]),
                "vacuity": bool(not picked["antecedent_hit_buggy"]),
                "heldout_success": bool(picked["heldout_success"]),
                "trace_overfit": bool(picked["trace_overfit"]),
                "literal_hardcoding": bool(picked["literal_hardcoding"]),
                "failure_type": picked["failure_type"],
                "failure_reason": clean_text(picked["failure_reason"]),
                "example_note": build_example_note(picked),
            }
        )
    examples_df = pd.DataFrame(example_rows)
    examples_df["temporal_type"] = pd.Categorical(examples_df["temporal_type"], TEMPORAL_ORDER, ordered=True)
    examples_df = examples_df.sort_values("temporal_type").reset_index(drop=True)
    examples_df.to_csv(OUTPUT_DIR / "temporal_type_examples.csv", index=False)

    summary = {
        "total_assertions": int(len(df)),
        "total_cases": int(df["case_id"].nunique()),
        "temporal_types": TEMPORAL_ORDER,
        "hardest_by_fail_on_buggy_rate": by_type_df.sort_values(
            ["fail_on_buggy_rate", "heldout_success_rate", "vacuity_rate"], ascending=[True, True, False]
        )["temporal_type"].head(3).tolist(),
        "hardest_by_heldout_success_rate": by_type_df.sort_values(
            ["heldout_success_rate", "fail_on_buggy_rate", "vacuity_rate"], ascending=[True, True, False]
        )["temporal_type"].head(3).tolist(),
        "highest_vacuity_rate": by_type_df.sort_values(
            ["vacuity_rate", "fail_on_buggy_rate"], ascending=[False, True]
        )["temporal_type"].head(3).tolist(),
        "mapping_note": (
            "temporal_type 使用 case 级人工映射而非 assertion 文本启发式，"
            "以避免同一设计意图在不同 prompt 下被错误分桶。"
        ),
    }
    (OUTPUT_DIR / "temporal_type_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(OUTPUT_DIR)
    print(OUTPUT_DIR / "temporal_type_overall.csv")
    print(OUTPUT_DIR / "temporal_type_by_method.csv")
    print(OUTPUT_DIR / "temporal_type_examples.csv")


if __name__ == "__main__":
    main()
