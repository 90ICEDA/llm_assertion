from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
THREAD_ID = "019ed9f6-87cf-7830-adb8-595fe2ae140d"
OUTPUT_DIR = ROOT / "outputs" / THREAD_ID / "quadrant_analysis_data"
SOURCE_CLEAN = ROOT / "docs" / "real_rtl_scaleout" / "assertion_clean_master_iv12.csv"
INVENTORY = ROOT / "docs" / "real_rtl_scaleout" / "dataset_inventory_30cases.csv"

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
QUADRANT_ORDER = ["真成功", "太弱", "太强", "无效"]
PRIMARY_ORDER = ["真成功", "太弱", "太强", "无效"]
SPECIAL_NO_ASSERTION = "无clean断言"
BUG_CLASS_PRIORITY = ["combination_same_cycle", "temporal_cross_cycle"]


def quadrant_from_flags(correct_pass, fail_on_buggy) -> str:
    key = (bool(correct_pass), bool(fail_on_buggy))
    mapping = {
        (True, True): "真成功",
        (True, False): "太弱",
        (False, True): "太强",
        (False, False): "无效",
    }
    return mapping[key]


def ordered_bug_classes(values) -> list[str]:
    values = [str(v) for v in values if pd.notna(v) and str(v).strip()]
    seen = []
    for cls in BUG_CLASS_PRIORITY:
        if cls in values and cls not in seen:
            seen.append(cls)
    for cls in sorted(values):
        if cls not in seen:
            seen.append(cls)
    return seen


def summarize_case_method(group: pd.DataFrame) -> dict:
    counts = {q: int((group["quadrant"] == q).sum()) for q in QUADRANT_ORDER}
    seen = [q for q in QUADRANT_ORDER if counts[q] > 0]
    primary = seen[0] if seen else SPECIAL_NO_ASSERTION
    return {
        "clean_assertion_count": int(len(group)),
        "primary_quadrant": primary,
        "quadrants_seen": " + ".join(seen) if seen else SPECIAL_NO_ASSERTION,
        "mixed_quadrants": len(seen) > 1,
        "真成功_count": counts["真成功"],
        "太弱_count": counts["太弱"],
        "太强_count": counts["太强"],
        "无效_count": counts["无效"],
    }


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    clean_df = pd.read_csv(SOURCE_CLEAN)
    inventory_df = pd.read_csv(INVENTORY)

    case_meta = (
        inventory_df[["case_name", "source_module", "bug_type", "bug_class"]]
        .rename(
            columns={
                "case_name": "case_id",
                "source_module": "module_inventory",
                "bug_type": "bug_name_inventory",
                "bug_class": "bug_class_inventory",
            }
        )
        .copy()
    )

    df = clean_df.merge(case_meta, on="case_id", how="left")
    df["module"] = df["module"].fillna(df["module_inventory"]).fillna("")
    df["bug_name"] = df["bug_name"].fillna(df["bug_name_inventory"]).fillna("")
    df["bug_class"] = df["bug_class"].fillna(df["bug_class_inventory"]).fillna("")
    df["method_label"] = df["method"].map(METHOD_LABEL).fillna(df["method"])
    df["quadrant"] = df.apply(
        lambda r: quadrant_from_flags(r["correct_pass"], r["fail_on_buggy"]), axis=1
    )

    assertion_rows = df[
        [
            "case_id",
            "module",
            "bug_name",
            "bug_class",
            "method",
            "method_label",
            "prompt_type",
            "correct_pass",
            "fail_on_buggy",
            "quadrant",
            "assertion_text",
            "normalized_assertion",
        ]
    ].copy()

    overall_long = (
        df.groupby(["method", "method_label", "quadrant"], dropna=False)
        .agg(assertion_count=("quadrant", "size"), case_count=("case_id", "nunique"))
        .reset_index()
    )
    overall_long["method"] = pd.Categorical(overall_long["method"], METHOD_ORDER, ordered=True)
    overall_long["quadrant"] = pd.Categorical(
        overall_long["quadrant"], QUADRANT_ORDER, ordered=True
    )
    overall_long = overall_long.sort_values(["method", "quadrant"]).reset_index(drop=True)

    overall_matrix = (
        overall_long.pivot(index=["method", "method_label"], columns="quadrant", values="assertion_count")
        .reindex(columns=QUADRANT_ORDER)
        .reset_index()
        .fillna(0)
    )
    overall_matrix["total_assertions"] = overall_matrix[QUADRANT_ORDER].sum(axis=1).astype(int)
    for q in QUADRANT_ORDER:
        overall_matrix[f"{q}_share"] = (
            overall_matrix[q] / overall_matrix["total_assertions"]
        ).round(4)

    bug_class_order = ordered_bug_classes(df["bug_class"].unique())
    by_bug_class_long = (
        df.groupby(["bug_class", "method", "method_label", "quadrant"], dropna=False)
        .agg(assertion_count=("quadrant", "size"), case_count=("case_id", "nunique"))
        .reset_index()
    )
    by_bug_class_long["bug_class"] = pd.Categorical(
        by_bug_class_long["bug_class"], bug_class_order, ordered=True
    )
    by_bug_class_long["method"] = pd.Categorical(
        by_bug_class_long["method"], METHOD_ORDER, ordered=True
    )
    by_bug_class_long["quadrant"] = pd.Categorical(
        by_bug_class_long["quadrant"], QUADRANT_ORDER, ordered=True
    )
    by_bug_class_long = by_bug_class_long.sort_values(
        ["bug_class", "method", "quadrant"]
    ).reset_index(drop=True)

    by_bug_class_matrix = (
        by_bug_class_long.pivot(
            index=["bug_class", "method", "method_label"],
            columns="quadrant",
            values="assertion_count",
        )
        .reindex(columns=QUADRANT_ORDER)
        .reset_index()
        .fillna(0)
    )
    by_bug_class_matrix["total_assertions"] = by_bug_class_matrix[QUADRANT_ORDER].sum(axis=1).astype(int)

    case_method_rows = []
    for (case_id, method), group in df.groupby(["case_id", "method"], dropna=False):
        meta = group.iloc[0]
        summary = summarize_case_method(group)
        case_method_rows.append(
            {
                "case_id": case_id,
                "module": meta["module"],
                "bug_name": meta["bug_name"],
                "bug_class": meta["bug_class"],
                "method": method,
                "method_label": METHOD_LABEL.get(method, method),
                **summary,
            }
        )

    case_method_df = pd.DataFrame(case_method_rows)

    case_grid = (
        case_meta[["case_id", "module_inventory", "bug_name_inventory", "bug_class_inventory"]]
        .assign(key=1)
        .merge(pd.DataFrame({"method": METHOD_ORDER, "key": 1}), on="key", how="outer")
        .drop(columns="key")
        .rename(
            columns={
                "module_inventory": "module",
                "bug_name_inventory": "bug_name",
                "bug_class_inventory": "bug_class",
            }
        )
    )
    case_method_full = case_grid.merge(
        case_method_df,
        on=["case_id", "module", "bug_name", "bug_class", "method"],
        how="left",
        suffixes=("", "_y"),
    )
    case_method_full["method_label"] = case_method_full["method"].map(METHOD_LABEL)
    case_method_full["clean_assertion_count"] = case_method_full["clean_assertion_count"].fillna(0).astype(int)
    case_method_full["primary_quadrant"] = case_method_full["primary_quadrant"].fillna(
        SPECIAL_NO_ASSERTION
    )
    case_method_full["quadrants_seen"] = case_method_full["quadrants_seen"].fillna(
        SPECIAL_NO_ASSERTION
    )
    case_method_full["mixed_quadrants"] = case_method_full["mixed_quadrants"].fillna(False)
    for col in ["真成功_count", "太弱_count", "太强_count", "无效_count"]:
        case_method_full[col] = case_method_full[col].fillna(0).astype(int)

    case_method_full["method"] = pd.Categorical(case_method_full["method"], METHOD_ORDER, ordered=True)
    case_method_full["bug_class"] = pd.Categorical(
        case_method_full["bug_class"], bug_class_order, ordered=True
    )
    case_method_full = case_method_full.sort_values(["case_id", "method"]).reset_index(drop=True)

    case_summary_rows = []
    for case_id, group in case_method_full.groupby("case_id", dropna=False):
        first = group.iloc[0]
        row = {
            "case_id": case_id,
            "module": first["module"],
            "bug_name": first["bug_name"],
            "bug_class": first["bug_class"],
        }
        for method in METHOD_ORDER:
            sub = group[group["method"] == method].iloc[0]
            prefix = method
            row[f"{prefix}_primary_quadrant"] = sub["primary_quadrant"]
            row[f"{prefix}_quadrants_seen"] = sub["quadrants_seen"]
            row[f"{prefix}_clean_assertion_count"] = int(sub["clean_assertion_count"])
            row[f"{prefix}_mixed_quadrants"] = bool(sub["mixed_quadrants"])
        case_summary_rows.append(row)

    case_summary_df = pd.DataFrame(case_summary_rows).sort_values("case_id").reset_index(drop=True)

    primary_method_matrix = (
        case_method_full.groupby(["method", "primary_quadrant"], dropna=False)
        .size()
        .reset_index(name="case_count")
    )
    primary_method_matrix["method"] = pd.Categorical(
        primary_method_matrix["method"], METHOD_ORDER, ordered=True
    )
    primary_order_full = QUADRANT_ORDER + [SPECIAL_NO_ASSERTION]
    primary_method_matrix["primary_quadrant"] = pd.Categorical(
        primary_method_matrix["primary_quadrant"], primary_order_full, ordered=True
    )
    primary_method_matrix = primary_method_matrix.sort_values(["method", "primary_quadrant"]).reset_index(drop=True)

    summary = {
        "source_clean_csv": str(SOURCE_CLEAN),
        "inventory_csv": str(INVENTORY),
        "method_order": METHOD_ORDER,
        "method_labels": METHOD_LABEL,
        "quadrant_order": QUADRANT_ORDER,
        "primary_rule": "case-method 主象限按优先级判定：真成功 > 太弱 > 太强 > 无效；若该 case-method 没有 clean assertion，则记为 无clean断言。",
        "deduped_assertion_count": int(len(df)),
        "case_count": int(case_summary_df["case_id"].nunique()),
        "case_method_total": int(case_summary_df["case_id"].nunique() * len(METHOD_ORDER)),
        "case_method_with_clean_assertion": int((case_method_full["clean_assertion_count"] > 0).sum()),
        "case_method_without_clean_assertion": int((case_method_full["clean_assertion_count"] == 0).sum()),
        "mixed_case_method_count": int(case_method_full["mixed_quadrants"].sum()),
        "bug_classes": bug_class_order,
        "overall_assertion_counts": overall_matrix.to_dict(orient="records"),
        "primary_case_counts": primary_method_matrix.to_dict(orient="records"),
    }

    assertion_rows.to_csv(OUTPUT_DIR / "quadrant_assertion_rows.csv", index=False)
    overall_long.to_csv(OUTPUT_DIR / "quadrant_overall_long.csv", index=False)
    overall_matrix.to_csv(OUTPUT_DIR / "quadrant_overall_matrix.csv", index=False)
    by_bug_class_long.to_csv(OUTPUT_DIR / "quadrant_by_bug_class_long.csv", index=False)
    by_bug_class_matrix.to_csv(OUTPUT_DIR / "quadrant_by_bug_class_matrix.csv", index=False)
    case_method_full.to_csv(OUTPUT_DIR / "quadrant_case_method_full.csv", index=False)
    case_summary_df.to_csv(OUTPUT_DIR / "quadrant_case_summary.csv", index=False)
    primary_method_matrix.to_csv(OUTPUT_DIR / "quadrant_case_primary_method_counts.csv", index=False)
    (OUTPUT_DIR / "quadrant_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"Wrote analysis data to {OUTPUT_DIR}")
    print(f"deduped_assertion_count={len(df)}")
    print(f"case_method_without_clean_assertion={summary['case_method_without_clean_assertion']}")


if __name__ == "__main__":
    main()
