from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
THREAD_ID = "019ed9f6-87cf-7830-adb8-595fe2ae140d"
SOURCE_CLEAN = ROOT / "docs" / "real_rtl_scaleout" / "assertion_clean_master_iv12.csv"
OUTPUT_DIR = ROOT / "outputs" / THREAD_ID / "trace_overfit_data"

METHOD_ORDER = ["spec_rtl_raw_trace", "spec_rtl_trace_summary"]
METHOD_LABEL = {
    "spec_rtl_raw_trace": "spec + RTL + raw trace",
    "spec_rtl_trace_summary": "spec + RTL + trace summary",
}
CLASS_ORDER = ["literal_overfit", "structural_overfit", "vacuous_overfit", "not_flagged"]

LITERAL_REASON_RE = re.compile(
    r"trace-only literal|observed trace literals|pinned to multiple observed trace literals",
    re.IGNORECASE,
)
ADDRESS_CONST_RE = re.compile(
    r"(addr\w*|wptr\w*|rptr\w*)\s*(?:==|!=)\s*(\d+'[bdh][0-9a-f_xz]+|\d+)",
    re.IGNORECASE,
)
COUNTER_CONST_RE = re.compile(
    r"((?:ctr|count|counter)\w*)\s*(?:==|!=|<=|>=|<|>)\s*(\d+'[bdh][0-9a-f_xz]+|\d+)",
    re.IGNORECASE,
)
STATE_CONST_RE = re.compile(
    r"(state\w*)\s*(?:==|!=)\s*(\d+'[bdh][0-9a-f_xz]+|\d+)",
    re.IGNORECASE,
)
DEPTH_CONST_RE = re.compile(
    r"(depth\w*)\s*(?:==|!=|<=|>=|<|>)\s*(\d+'[bdh][0-9a-f_xz]+|\d+)",
    re.IGNORECASE,
)
ONEHOT_CONST_RE = re.compile(
    r"(oh_\w*|onehot\w*)\s*(?:==|!=)\s*(\d+'[bdh][0-9a-f_xz]+|\d+)",
    re.IGNORECASE,
)
CYCLE_NUM_RE = re.compile(
    r"##\s*\d+|##\s*\[\d+:\d+\]|\[\*\s*\d+\]|\[->\s*\d+\]",
    re.IGNORECASE,
)
CONST_TOKEN_RE = re.compile(r"\b\d+'[bdh][0-9a-f_xz]+\b|\b\d+\b", re.IGNORECASE)


def safe_bool_series(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series.fillna(False)
    lowered = series.fillna(False).astype(str).str.strip().str.lower()
    return lowered.isin(["true", "1", "yes"])


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


def extract_constant_tokens(text: str) -> list[str]:
    tokens = CONST_TOKEN_RE.findall(str(text or ""))
    deduped: list[str] = []
    for token in tokens:
        if token not in deduped:
            deduped.append(token)
    return deduped


def is_specific_constant(token: str) -> bool:
    token = str(token or "").strip().lower()
    if not token:
        return False
    generic = {
        "0",
        "1",
        "1'b0",
        "1'b1",
        "1'd0",
        "1'd1",
        "1'h0",
        "1'h1",
    }
    if token in generic:
        return False
    dec = re.fullmatch(r"\d+", token)
    if dec:
        return int(token) > 1
    width = re.fullmatch(r"(\d+)'([bdh])([0-9a-f_xz]+)", token)
    if width:
        bits = int(width.group(1))
        digits = width.group(3)
        if bits <= 1 and set(digits) <= {"0", "1"}:
            return False
        return True
    return True


def classify_literal_flags(assertion_text: str, failure_reason: str, literal_hardcoding: bool) -> dict:
    text = str(assertion_text or "")
    reason = str(failure_reason or "")
    address_hits = ADDRESS_CONST_RE.findall(text)
    counter_hits = COUNTER_CONST_RE.findall(text)
    state_hits = STATE_CONST_RE.findall(text)
    depth_hits = DEPTH_CONST_RE.findall(text)
    onehot_hits = ONEHOT_CONST_RE.findall(text)
    cycle_hits = CYCLE_NUM_RE.findall(text)
    seen_only_constant = bool(LITERAL_REASON_RE.search(reason)) or bool(literal_hardcoding)

    def keep_specific(hits):
        return [(sig, tok) for sig, tok in hits if is_specific_constant(tok)]

    address_hits = keep_specific(address_hits)
    counter_hits = keep_specific(counter_hits)
    state_hits = keep_specific(state_hits)
    depth_hits = keep_specific(depth_hits)
    onehot_hits = keep_specific(onehot_hits)

    tokens: list[str] = []
    for hits in [address_hits, counter_hits, state_hits, depth_hits, onehot_hits]:
        for _sig, token in hits:
            if token not in tokens:
                tokens.append(token)
    for token in cycle_hits:
        if token not in tokens:
            tokens.append(token)
    if seen_only_constant:
        for token in extract_constant_tokens(reason):
            if token not in tokens:
                tokens.append(token)

    return {
        "specific_address_value": bool(address_hits),
        "specific_counter_value": bool(counter_hits),
        "specific_state_encoding": bool(state_hits),
        "specific_fifo_depth": bool(depth_hits),
        "specific_onehot_encoding": bool(onehot_hits),
        "specific_cycle_number": bool(cycle_hits),
        "seen_only_constant": seen_only_constant,
        "constant_tokens": ", ".join(tokens),
        "explicit_literal_evidence": bool(
            literal_hardcoding
            or seen_only_constant
            or address_hits
            or counter_hits
            or state_hits
            or depth_hits
            or onehot_hits
            or cycle_hits
        ),
    }


def classify_row(row: pd.Series) -> tuple[str, str]:
    assessable = bool(row["assessable"])
    seen_plausible = bool(row["seen_plausible"])
    heldout_ant = bool(row["heldout_antecedent_hit"])
    heldout_correct = bool(row["heldout_correct_pass"])
    heldout_buggy = bool(row["heldout_buggy_fail"])
    trace_overfit = bool(row["trace_overfit"])
    explicit_literal = bool(row["explicit_literal_evidence"])

    heldout_failure_any = assessable and ((not heldout_correct) or (not heldout_buggy) or (not heldout_ant))
    heldout_issue_from_seen_plausible = seen_plausible and (
        (not heldout_correct) or (not heldout_buggy) or (not heldout_ant)
    )

    if seen_plausible and (not heldout_ant):
        return "vacuous_overfit", "seen 上 antecedent 可触发，但 held-out 上 antecedent 不再触发"

    if assessable and explicit_literal and heldout_failure_any:
        return "literal_overfit", "断言含显式常数/seen-trace 字面量，且 held-out 上失效"

    if trace_overfit or heldout_issue_from_seen_plausible:
        return "structural_overfit", "没有明显字面量钉死，但 held-out 上暴露出局部结构适配"

    return "not_flagged", ""


def heldout_issue_label(row: pd.Series) -> str:
    issues: list[str] = []
    if bool(row["seen_plausible"]) and not bool(row["heldout_antecedent_hit"]):
        issues.append("heldout_antecedent_not_triggered")
    if bool(row["seen_plausible"]) and not bool(row["heldout_correct_pass"]):
        issues.append("heldout_false_positive_on_correct")
    if bool(row["seen_plausible"]) and not bool(row["heldout_buggy_fail"]):
        issues.append("heldout_bug_not_detected")
    if not issues:
        return ""
    return " + ".join(issues)


def build_reason(row: pd.Series) -> str:
    cls = row["overfit_class"]
    method_label = row["method_label"]
    if cls == "vacuous_overfit":
        return (
            f"{method_label} 这条断言在 seen 侧至少通过了 correct 检查，但 held-out 上 antecedent 不再触发，"
            "因此看起来有效、实则在新轨迹上变成 vacuous。"
        )
    if cls == "literal_overfit":
        consts = row["constant_tokens"] or "seen-trace 常数"
        return (
            f"{method_label} 这条断言把条件钉在 {consts} 这类常数上，"
            "held-out 上因此出现误伤或漏检，属于明显的 literal overfit。"
        )
    if cls == "structural_overfit":
        issue = row["heldout_issue_label"] or row["failure_reason"] or "held-out 泛化失效"
        return (
            f"{method_label} 这条断言没有明显字面量硬编码，但只适配了 seen trace 的局部行为结构；"
            f"在 held-out 上表现为：{issue}。"
        )
    return ""


def example_priority(row: pd.Series) -> tuple:
    cls = row["overfit_class"]
    seen_strict = bool(row["seen_success_strict"])
    reason_present = 0 if str(row.get("failure_reason", "") or "").strip() else 1
    literal_bonus = 0 if bool(row.get("literal_hardcoding")) else 1
    trace_bonus = 0 if bool(row.get("trace_overfit")) else 1
    token_penalty = -len(str(row.get("constant_tokens", "")).split(", ")) if row.get("constant_tokens") else 0
    length_penalty = len(str(row.get("assertion_text", "")))

    class_rank = {
        "literal_overfit": 0,
        "structural_overfit": 1,
        "vacuous_overfit": 2,
        "not_flagged": 9,
    }.get(cls, 9)

    return (
        class_rank,
        0 if seen_strict else 1,
        reason_present,
        literal_bonus,
        trace_bonus,
        token_penalty,
        length_penalty,
    )


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(SOURCE_CLEAN)
    df = df[df["method"].isin(METHOD_ORDER)].copy()

    bool_cols = [
        "compile_ok",
        "analysis_supported",
        "template_supported",
        "correct_pass",
        "fail_on_buggy",
        "heldout_correct_pass",
        "heldout_buggy_fail",
        "heldout_antecedent_hit",
        "trace_overfit",
        "literal_hardcoding",
    ]
    for col in bool_cols:
        df[col] = safe_bool_series(df[col])

    df["method"] = pd.Categorical(df["method"], METHOD_ORDER, ordered=True)
    df["method_label"] = df["method"].map(METHOD_LABEL)
    df["assessable"] = df["compile_ok"] & df["analysis_supported"] & df["template_supported"]
    df["seen_plausible"] = df["assessable"] & df["correct_pass"]
    df["seen_success_strict"] = df["assessable"] & df["correct_pass"] & df["fail_on_buggy"]
    df["heldout_success_strict"] = (
        df["assessable"] & df["heldout_correct_pass"] & df["heldout_buggy_fail"] & df["heldout_antecedent_hit"]
    )

    parts = df["assertion_text"].apply(lambda t: pd.Series(extract_parts(t)))
    parts.columns = ["antecedent_text", "consequent_text"]
    df = pd.concat([df, parts], axis=1)

    literal_flags = df.apply(
        lambda r: pd.Series(
            classify_literal_flags(r["assertion_text"], r.get("failure_reason", ""), bool(r["literal_hardcoding"]))
        ),
        axis=1,
    )
    df = pd.concat([df, literal_flags], axis=1)

    classified = df.apply(lambda r: pd.Series(classify_row(r)), axis=1)
    classified.columns = ["overfit_class", "overfit_basis"]
    df = pd.concat([df, classified], axis=1)
    df["heldout_issue_label"] = df.apply(heldout_issue_label, axis=1)
    df["overfit_suspect"] = df["overfit_class"] != "not_flagged"
    df["overfit_reason"] = df.apply(build_reason, axis=1)

    summary_rows = []
    for method in METHOD_ORDER:
        sub = df[df["method"] == method]
        summary_rows.append(
            {
                "method": method,
                "method_label": METHOD_LABEL[method],
                "assertion_count": int(len(sub)),
                "assessable_count": int(sub["assessable"].sum()),
                "seen_plausible_count": int(sub["seen_plausible"].sum()),
                "seen_success_strict_count": int(sub["seen_success_strict"].sum()),
                "heldout_success_strict_count": int(sub["heldout_success_strict"].sum()),
                "overfit_suspect_count": int(sub["overfit_suspect"].sum()),
                "literal_overfit_count": int((sub["overfit_class"] == "literal_overfit").sum()),
                "structural_overfit_count": int((sub["overfit_class"] == "structural_overfit").sum()),
                "vacuous_overfit_count": int((sub["overfit_class"] == "vacuous_overfit").sum()),
                "literal_hardcoding_flag_count": int(sub["literal_hardcoding"].sum()),
                "existing_trace_overfit_flag_count": int(sub["trace_overfit"].sum()),
            }
        )
    method_summary_df = pd.DataFrame(summary_rows)

    class_summary = (
        df.groupby(["method", "method_label", "overfit_class"], dropna=False)
        .agg(
            assertion_count=("case_id", "size"),
            strict_seen_success_count=("seen_success_strict", "sum"),
            seen_plausible_count=("seen_plausible", "sum"),
            literal_hardcoding_count=("literal_hardcoding", "sum"),
            existing_trace_overfit_count=("trace_overfit", "sum"),
        )
        .reset_index()
    )
    class_summary["method"] = pd.Categorical(class_summary["method"], METHOD_ORDER, ordered=True)
    class_summary["overfit_class"] = pd.Categorical(class_summary["overfit_class"], CLASS_ORDER, ordered=True)
    class_summary = class_summary.sort_values(["method", "overfit_class"]).reset_index(drop=True)

    literal_pattern_summary = (
        df[df["overfit_suspect"]]
        .groupby(["overfit_class", "method", "method_label"], dropna=False)
        .agg(
            assertion_count=("case_id", "size"),
            specific_address_value=("specific_address_value", "sum"),
            specific_counter_value=("specific_counter_value", "sum"),
            specific_state_encoding=("specific_state_encoding", "sum"),
            specific_fifo_depth=("specific_fifo_depth", "sum"),
            specific_onehot_encoding=("specific_onehot_encoding", "sum"),
            specific_cycle_number=("specific_cycle_number", "sum"),
            seen_only_constant=("seen_only_constant", "sum"),
        )
        .reset_index()
    )
    literal_pattern_summary["method"] = pd.Categorical(
        literal_pattern_summary["method"], METHOD_ORDER, ordered=True
    )
    literal_pattern_summary["overfit_class"] = pd.Categorical(
        literal_pattern_summary["overfit_class"], CLASS_ORDER, ordered=True
    )
    literal_pattern_summary = literal_pattern_summary.sort_values(
        ["overfit_class", "method"]
    ).reset_index(drop=True)

    example_rows = []
    for target_class in ["literal_overfit", "structural_overfit", "vacuous_overfit"]:
        sub = df[df["overfit_class"] == target_class].copy()
        ranked = sub.assign(_priority=sub.apply(example_priority, axis=1)).sort_values("_priority")
        chosen_rows = []
        seen_cases: set[str] = set()
        for _, row in ranked.iterrows():
            case_id = str(row["case_id"])
            if case_id in seen_cases and len(seen_cases) < 6:
                continue
            chosen_rows.append(row)
            seen_cases.add(case_id)
            if len(chosen_rows) >= 6:
                break
        chosen = pd.DataFrame(chosen_rows).drop(columns="_priority", errors="ignore")
        example_rows.append(chosen)
    example_df = pd.concat(example_rows, axis=0).reset_index(drop=True) if example_rows else pd.DataFrame()

    full_cols = [
        "case_id",
        "module",
        "bug_name",
        "bug_class",
        "method",
        "method_label",
        "prompt_type",
        "assertion_text",
        "normalized_assertion",
        "antecedent_text",
        "consequent_text",
        "compile_ok",
        "analysis_supported",
        "template_supported",
        "correct_pass",
        "fail_on_buggy",
        "heldout_correct_pass",
        "heldout_buggy_fail",
        "heldout_antecedent_hit",
        "seen_plausible",
        "seen_success_strict",
        "heldout_success_strict",
        "heldout_issue_label",
        "trace_overfit",
        "literal_hardcoding",
        "specific_address_value",
        "specific_counter_value",
        "specific_state_encoding",
        "specific_fifo_depth",
        "specific_onehot_encoding",
        "specific_cycle_number",
        "seen_only_constant",
        "constant_tokens",
        "explicit_literal_evidence",
        "overfit_class",
        "overfit_basis",
        "overfit_reason",
        "failure_type",
        "failure_reason",
    ]
    full_df = df[full_cols].copy().sort_values(["method", "bug_class", "case_id"]).reset_index(drop=True)

    summary_payload = {
        "source": str(SOURCE_CLEAN),
        "assertion_count": int(len(df)),
        "method_counts": {
            row["method"]: {
                "assertion_count": int(row["assertion_count"]),
                "seen_success_strict_count": int(row["seen_success_strict_count"]),
                "overfit_suspect_count": int(row["overfit_suspect_count"]),
                "literal_overfit_count": int(row["literal_overfit_count"]),
                "structural_overfit_count": int(row["structural_overfit_count"]),
                "vacuous_overfit_count": int(row["vacuous_overfit_count"]),
            }
            for row in method_summary_df.to_dict("records")
        },
        "pattern_totals_on_suspects": {
            "specific_address_value": int(df.loc[df["overfit_suspect"], "specific_address_value"].sum()),
            "specific_counter_value": int(df.loc[df["overfit_suspect"], "specific_counter_value"].sum()),
            "specific_state_encoding": int(df.loc[df["overfit_suspect"], "specific_state_encoding"].sum()),
            "specific_fifo_depth": int(df.loc[df["overfit_suspect"], "specific_fifo_depth"].sum()),
            "specific_onehot_encoding": int(df.loc[df["overfit_suspect"], "specific_onehot_encoding"].sum()),
            "specific_cycle_number": int(df.loc[df["overfit_suspect"], "specific_cycle_number"].sum()),
            "seen_only_constant": int(df.loc[df["overfit_suspect"], "seen_only_constant"].sum()),
        },
    }

    full_df.to_csv(OUTPUT_DIR / "trace_overfit_assertion_table.csv", index=False, encoding="utf-8")
    method_summary_df.to_csv(OUTPUT_DIR / "trace_overfit_method_summary.csv", index=False, encoding="utf-8")
    class_summary.to_csv(OUTPUT_DIR / "trace_overfit_class_summary.csv", index=False, encoding="utf-8")
    literal_pattern_summary.to_csv(OUTPUT_DIR / "trace_overfit_literal_pattern_summary.csv", index=False, encoding="utf-8")
    example_df.to_csv(OUTPUT_DIR / "trace_overfit_example_index.csv", index=False, encoding="utf-8")
    (OUTPUT_DIR / "trace_overfit_summary.json").write_text(
        json.dumps(summary_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(OUTPUT_DIR)


if __name__ == "__main__":
    main()
