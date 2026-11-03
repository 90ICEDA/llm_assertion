from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
THREAD_ID = "019ed9f6-87cf-7830-adb8-595fe2ae140d"
SOURCE_CLEAN = ROOT / "docs" / "real_rtl_scaleout" / "assertion_clean_master_iv12.csv"
OUTPUT_DIR = ROOT / "outputs" / THREAD_ID / "vacuity_analysis_data"

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
PAPER_BUCKET_ORDER = [
    "vacuous_miss",
    "non_vacuous_miss",
    "too_weak",
    "trace_overfit",
    "semantic_wrong",
    "unsupported_analysis",
]


def strip_wrapping_parens(text: str) -> str:
    text = str(text or "").strip()
    while text.startswith("(") and text.endswith(")"):
        depth = 0
        balanced = True
        for idx, ch in enumerate(text):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0 and idx != len(text) - 1:
                    balanced = False
                    break
            if depth < 0:
                balanced = False
                break
        if not balanced or depth != 0:
            break
        text = text[1:-1].strip()
    return text


def split_top_level_implication(body: str) -> tuple[str, str]:
    for op in ("|->", "|=>"):
        depth = 0
        i = 0
        while i < len(body) - 2:
            ch = body[i]
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            if depth == 0 and body[i : i + 3] == op:
                return body[:i].strip(), body[i + 3 :].strip()
            i += 1
    return body.strip(), ""


def extract_parts(assertion: str) -> tuple[str, str]:
    text = str(assertion or "").strip().rstrip(";")
    if not text:
        return "", ""
    match = re.match(
        r"^assert property\s*\(@\(posedge clk\)\s*disable iff\s*\(!rst_n\)\s*(.*)\)$",
        text,
        flags=re.IGNORECASE,
    )
    body = match.group(1).strip() if match else text
    ant, cons = split_top_level_implication(body)
    return strip_wrapping_parens(ant), strip_wrapping_parens(cons)


def safe_bool(value) -> bool:
    if pd.isna(value):
        return False
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() == "true"


def has_text(value: str, needle: str) -> bool:
    return needle.lower() in str(value or "").lower()


def classify_row(row: pd.Series) -> tuple[str, str, str]:
    failure_reason = str(row.get("failure_reason", "") or "")
    failure_type = str(row.get("failure_type", "") or "")

    compile_ok = safe_bool(row.get("compile_ok"))
    analysis_supported = safe_bool(row.get("analysis_supported"))
    antecedent_hit_buggy = safe_bool(row.get("antecedent_hit_buggy"))
    correct_pass = safe_bool(row.get("correct_pass"))
    trace_overfit = safe_bool(row.get("trace_overfit"))
    literal_hardcoding = safe_bool(row.get("literal_hardcoding"))
    semantic_reasonable = row.get("semantic_reasonable")
    semantic_false = (not pd.isna(semantic_reasonable)) and (str(semantic_reasonable).strip().lower() == "false")

    correct_side_issue = ""
    if not correct_pass:
        correct_side_issue = "too_strong_on_correct"

    if (not compile_ok) or (not analysis_supported):
        return "unsupported_analysis", "compile_fail_or_unsupported", correct_side_issue

    if semantic_false or has_text(failure_type, "semantic") or has_text(failure_reason, "semantic"):
        return "semantic_wrong", "semantic_unreasonable", correct_side_issue

    if trace_overfit or literal_hardcoding or has_text(failure_reason, "trace-only literal") or has_text(failure_reason, "observed trace literals"):
        return "trace_overfit", "seen_trace_only", correct_side_issue

    if not antecedent_hit_buggy:
        return "vacuous_miss", "antecedent_not_triggered", correct_side_issue

    if correct_pass and antecedent_hit_buggy:
        if failure_type == "bug_not_detected_on_buggy":
            return "too_weak", "consequent_not_discriminative", correct_side_issue
        return "non_vacuous_miss", "consequent_not_discriminative", correct_side_issue

    if (not correct_pass) and antecedent_hit_buggy:
        return "non_vacuous_miss", "too_strong_and_non_discriminative", correct_side_issue

    return "non_vacuous_miss", "unclassified_non_vacuous_miss", correct_side_issue


def build_explanation(row: pd.Series) -> str:
    case_id = row["case_id"]
    ant = row["antecedent_text"]
    cons = row["consequent_text"]
    bucket = row["paper_bucket"]
    detail = row["buggy_miss_detail"]
    correct_issue = row["correct_side_issue"]

    if bucket == "unsupported_analysis":
        return f"{case_id} 中，这条断言在编译/分析阶段就失败了，因此既无法完成 vacuity 判断，也不能用于检测 buggy 行为。"

    if bucket == "trace_overfit":
        return f"{case_id} 中，模型把条件钉在 seen trace 的字面值上（antecedent: {ant}），因此该断言只对观测过的轨迹有效，离开 seen trace 后就失去检测能力。"

    if bucket == "vacuous_miss":
        if correct_issue == "too_strong_on_correct":
            return f"{case_id} 中，模型生成的 antecedent 是 {ant}，但 buggy trace 中该条件从未触发，因此这条断言对 bug 检测是 vacuous 的；同时它在 correct 上还有 too-strong 误报。"
        return f"{case_id} 中，模型生成的 antecedent 是 {ant}，但 buggy trace 中该条件从未触发，因此 assertion 虽然 pass，却无法检测 bug。"

    if bucket == "too_weak":
        return f"{case_id} 中，antecedent {ant} 在 buggy trace 中确实触发，但 consequent {cons} 没有把 correct 和 buggy 区分开，因此这是 non-vacuous miss，更接近 too weak。"

    if bucket == "non_vacuous_miss":
        if correct_issue == "too_strong_on_correct":
            return f"{case_id} 中，antecedent {ant} 在 buggy trace 中会触发，但 consequent {cons} 没能区分 correct/buggy，而且该断言在 correct 上还会误报，说明它同时带有 too-strong 问题。"
        return f"{case_id} 中，antecedent {ant} 在 buggy trace 中已经触发，但 consequent {cons} 没有形成 correct/buggy 区分，因此它不是 vacuous failure，而是 non-vacuous miss。"

    if bucket == "semantic_wrong":
        return f"{case_id} 中，这条断言的语义关系本身不合理，因此即使形式上可运行，也不能对应目标 bug。"

    return f"{case_id} 中，这条断言未能检测到 buggy 行为，需要结合 antecedent/consequent 进一步复核。"


def rep_priority(row: pd.Series, mode: str) -> tuple:
    # mode = vacuity or diagnostic
    bucket = row["paper_bucket"]
    detail = row["buggy_miss_detail"]
    reason_present = 0 if str(row.get("failure_reason", "") or "").strip() else 1
    literal_penalty = 0 if safe_bool(row.get("literal_hardcoding")) else 1
    length_penalty = len(str(row.get("assertion_text", "")))

    if mode == "vacuity":
        order = {
            "vacuous_miss": 0,
            "trace_overfit": 1,
            "too_weak": 2,
            "non_vacuous_miss": 3,
            "unsupported_analysis": 4,
            "semantic_wrong": 5,
        }
    else:
        order = {
            "trace_overfit": 0,
            "too_weak": 1,
            "non_vacuous_miss": 2,
            "unsupported_analysis": 3,
            "semantic_wrong": 4,
            "vacuous_miss": 5,
        }
    return (
        order.get(bucket, 99),
        reason_present,
        literal_penalty,
        length_penalty,
        str(detail),
    )


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(SOURCE_CLEAN)
    miss = df[df["fail_on_buggy"] == False].copy()
    miss["method_label"] = miss["method"].map(METHOD_LABEL).fillna(miss["method"])
    miss[["antecedent_text", "consequent_text"]] = miss["assertion_text"].apply(
        lambda text: pd.Series(extract_parts(text))
    )

    classified = miss.apply(lambda r: pd.Series(classify_row(r)), axis=1)
    classified.columns = ["paper_bucket", "buggy_miss_detail", "correct_side_issue"]
    miss = pd.concat([miss, classified], axis=1)
    miss["buggy_antecedent_zero"] = ~miss["antecedent_hit_buggy"].fillna(False).astype(bool)
    miss["representative_explanation"] = miss.apply(build_explanation, axis=1)

    bucket_counts = (
        miss.groupby(["paper_bucket", "method", "method_label"], dropna=False)
        .size()
        .reset_index(name="assertion_count")
    )
    bucket_counts["method"] = pd.Categorical(bucket_counts["method"], METHOD_ORDER, ordered=True)
    bucket_counts["paper_bucket"] = pd.Categorical(
        bucket_counts["paper_bucket"], PAPER_BUCKET_ORDER, ordered=True
    )
    bucket_counts = bucket_counts.sort_values(["paper_bucket", "method"]).reset_index(drop=True)

    method_summary = (
        miss.groupby(["method", "method_label"], dropna=False)
        .agg(
            fail_assertion_count=("case_id", "size"),
            vacuous_miss_count=("paper_bucket", lambda s: int((s == "vacuous_miss").sum())),
            non_vacuous_miss_count=("paper_bucket", lambda s: int((s == "non_vacuous_miss").sum())),
            too_weak_count=("paper_bucket", lambda s: int((s == "too_weak").sum())),
            trace_overfit_count=("paper_bucket", lambda s: int((s == "trace_overfit").sum())),
            semantic_wrong_count=("paper_bucket", lambda s: int((s == "semantic_wrong").sum())),
            unsupported_analysis_count=("paper_bucket", lambda s: int((s == "unsupported_analysis").sum())),
            buggy_antecedent_zero_count=("buggy_antecedent_zero", "sum"),
            fail_case_count=("case_id", "nunique"),
        )
        .reset_index()
    )
    method_summary["vacuous_share"] = (
        method_summary["vacuous_miss_count"] / method_summary["fail_assertion_count"]
    ).round(4)
    method_summary["method"] = pd.Categorical(method_summary["method"], METHOD_ORDER, ordered=True)
    method_summary = method_summary.sort_values("method").reset_index(drop=True)

    case_summary = (
        miss.groupby(["case_id", "module", "bug_name", "bug_class"], dropna=False)
        .agg(
            fail_assertion_count=("case_id", "size"),
            vacuous_miss_count=("paper_bucket", lambda s: int((s == "vacuous_miss").sum())),
            non_vacuous_miss_count=("paper_bucket", lambda s: int((s == "non_vacuous_miss").sum())),
            too_weak_count=("paper_bucket", lambda s: int((s == "too_weak").sum())),
            trace_overfit_count=("paper_bucket", lambda s: int((s == "trace_overfit").sum())),
            semantic_wrong_count=("paper_bucket", lambda s: int((s == "semantic_wrong").sum())),
            unsupported_analysis_count=("paper_bucket", lambda s: int((s == "unsupported_analysis").sum())),
            buggy_antecedent_zero_count=("buggy_antecedent_zero", "sum"),
        )
        .reset_index()
    )
    case_summary["vacuous_dominant"] = case_summary["vacuous_miss_count"] > 0
    case_summary["vacuous_share"] = (
        case_summary["vacuous_miss_count"] / case_summary["fail_assertion_count"]
    ).round(4)
    case_summary = case_summary.sort_values(["buggy_antecedent_zero_count", "fail_assertion_count"], ascending=[False, False]).reset_index(drop=True)

    antecedent_zero_summary = (
        miss[miss["buggy_antecedent_zero"]]
        .groupby(["case_id", "method", "method_label"], dropna=False)
        .agg(
            assertion_count=("case_id", "size"),
            example_antecedent=("antecedent_text", "first"),
            example_assertion=("assertion_text", "first"),
        )
        .reset_index()
    )
    antecedent_zero_summary["method"] = pd.Categorical(
        antecedent_zero_summary["method"], METHOD_ORDER, ordered=True
    )
    antecedent_zero_summary = antecedent_zero_summary.sort_values(["case_id", "method"]).reset_index(drop=True)

    vacuity_reps = []
    diagnostic_reps = []
    for case_id, group in miss.groupby("case_id", dropna=False):
        vac_row = sorted(group.to_dict("records"), key=lambda r: rep_priority(pd.Series(r), "vacuity"))[0]
        diag_row = sorted(group.to_dict("records"), key=lambda r: rep_priority(pd.Series(r), "diagnostic"))[0]
        vacuity_reps.append(vac_row)
        diagnostic_reps.append(diag_row)

    vacuity_rep_df = pd.DataFrame(vacuity_reps)[
        [
            "case_id",
            "module",
            "bug_name",
            "bug_class",
            "method",
            "method_label",
            "paper_bucket",
            "buggy_miss_detail",
            "correct_side_issue",
            "antecedent_text",
            "consequent_text",
            "assertion_text",
            "failure_type",
            "failure_reason",
            "representative_explanation",
        ]
    ].sort_values("case_id").reset_index(drop=True)

    diagnostic_rep_df = pd.DataFrame(diagnostic_reps)[
        [
            "case_id",
            "module",
            "bug_name",
            "bug_class",
            "method",
            "method_label",
            "paper_bucket",
            "buggy_miss_detail",
            "correct_side_issue",
            "antecedent_text",
            "consequent_text",
            "assertion_text",
            "failure_type",
            "failure_reason",
            "representative_explanation",
        ]
    ].sort_values("case_id").reset_index(drop=True)

    overall_summary = {
        "fail_assertion_count": int(len(miss)),
        "fail_case_count": int(miss["case_id"].nunique()),
        "buggy_antecedent_zero_count": int(miss["buggy_antecedent_zero"].sum()),
        "buggy_antecedent_zero_case_count": int(miss.loc[miss["buggy_antecedent_zero"], "case_id"].nunique()),
        "paper_bucket_counts": miss["paper_bucket"].value_counts().reindex(PAPER_BUCKET_ORDER, fill_value=0).to_dict(),
        "method_summary": method_summary.to_dict(orient="records"),
        "classification_rule": {
            "unsupported_analysis": "compile_ok == False or analysis_supported == False",
            "semantic_wrong": "semantic_reasonable == False or semantic-like failure markers",
            "trace_overfit": "trace_overfit == True or literal_hardcoding == True or trace-only literal reason",
            "vacuous_miss": "antecedent_hit_buggy == 0 after excluding the above",
            "too_weak": "antecedent_hit_buggy == 1 and correct_pass == 1 and failure_type == bug_not_detected_on_buggy",
            "non_vacuous_miss": "remaining antecedent_hit_buggy == 1 misses; correct-side too-strong issue kept in correct_side_issue",
        },
    }

    cols = [
        "case_id",
        "module",
        "bug_name",
        "bug_class",
        "method",
        "method_label",
        "paper_bucket",
        "buggy_miss_detail",
        "correct_side_issue",
        "buggy_antecedent_zero",
        "compile_ok",
        "analysis_supported",
        "correct_pass",
        "fail_on_buggy",
        "antecedent_hit_correct",
        "antecedent_hit_buggy",
        "non_vacuous_correct",
        "non_vacuous_buggy",
        "trace_overfit",
        "literal_hardcoding",
        "failure_type",
        "failure_reason",
        "antecedent_text",
        "consequent_text",
        "assertion_text",
        "normalized_assertion",
        "representative_explanation",
    ]
    miss[cols].sort_values(["case_id", "method"]).to_csv(OUTPUT_DIR / "vacuity_failure_rows.csv", index=False)
    bucket_counts.to_csv(OUTPUT_DIR / "vacuity_bucket_counts_by_method.csv", index=False)
    method_summary.to_csv(OUTPUT_DIR / "vacuity_method_summary.csv", index=False)
    case_summary.to_csv(OUTPUT_DIR / "vacuity_case_summary.csv", index=False)
    antecedent_zero_summary.to_csv(OUTPUT_DIR / "antecedent_zero_summary.csv", index=False)
    vacuity_rep_df.to_csv(OUTPUT_DIR / "representative_failures_vacuity_priority.csv", index=False)
    diagnostic_rep_df.to_csv(OUTPUT_DIR / "representative_failures_diagnostic_priority.csv", index=False)
    (OUTPUT_DIR / "vacuity_summary.json").write_text(
        json.dumps(overall_summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"Wrote vacuity analysis data to {OUTPUT_DIR}")
    print(f"fail_assertion_count={len(miss)}")
    print(f"buggy_antecedent_zero_count={int(miss['buggy_antecedent_zero'].sum())}")


if __name__ == "__main__":
    main()
