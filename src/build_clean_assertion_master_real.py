from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SOURCE_REPORT = ROOT / "rtl_cases_real_admitted_20260619" / "strict_eval_report_iv12.csv"
INVENTORY_CSV = ROOT / "docs" / "real_rtl_scaleout" / "dataset_inventory_30cases.csv"
OUTPUT_DIR = ROOT / "docs" / "real_rtl_scaleout"
OUTPUT_MASTER = OUTPUT_DIR / "assertion_clean_master_iv12.csv"
OUTPUT_STATS = OUTPUT_DIR / "assertion_clean_stats_iv12.csv"
OUTPUT_NOTES = OUTPUT_DIR / "assertion_clean_notes_iv12.md"


METHOD_TO_PROMPT_TYPE = {
    "spec_only": "prompt_1_spec_only",
    "spec_plus_rtl": "prompt_2_spec_plus_rtl",
    "spec_rtl_raw_trace": "prompt_3_spec_rtl_raw_trace",
    "spec_rtl_trace_summary": "prompt_4_spec_rtl_trace_summary",
}


def parse_bool(value):
    if pd.isna(value):
        return pd.NA
    text = str(value).strip().lower()
    if text == "":
        return pd.NA
    if text == "true":
        return True
    if text == "false":
        return False
    return pd.NA


def parse_int(value):
    if pd.isna(value):
        return pd.NA
    text = str(value).strip()
    if text == "":
        return pd.NA
    try:
        return int(text)
    except ValueError:
        return pd.NA


def collapse_ws(text: str) -> str:
    text = re.sub(r"\s+", " ", text.strip())
    text = re.sub(r"\s+\)", ")", text)
    text = re.sub(r"\(\s+", "(", text)
    text = re.sub(r"\s+\]", "]", text)
    text = re.sub(r"\[\s+", "[", text)
    text = re.sub(r"\s+\}", "}", text)
    text = re.sub(r"\{\s+", "{", text)
    return text.strip()


def strip_wrapping_parens(text: str) -> str:
    text = text.strip()
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


def normalize_expr(text: str) -> str:
    text = collapse_ws(text)
    text = re.sub(r"\s*\&\&\s*", " && ", text)
    text = re.sub(r"\s*\|\|\s*", " || ", text)
    text = re.sub(r"\s+\&\s+", " && ", text)
    text = re.sub(r"\s+\|\s+", " || ", text)
    text = re.sub(r"\s*==\s*", " == ", text)
    text = re.sub(r"\s*!=\s*", " != ", text)
    text = re.sub(r"\s*<=\s*", " <= ", text)
    text = re.sub(r"\s*>=\s*", " >= ", text)
    text = re.sub(r"\s*<\s*", " < ", text)
    text = re.sub(r"\s*>\s*", " > ", text)
    text = re.sub(r"\s*\+\s*", " + ", text)
    text = re.sub(r"\s*-\s*", " - ", text)
    text = re.sub(r"\s*/\s*", " / ", text)
    text = re.sub(r"\s*\*\s*", " * ", text)
    text = re.sub(r"\s*\?\s*", " ? ", text)
    text = re.sub(r"\s*:\s*", " : ", text)
    text = collapse_ws(text)
    return strip_wrapping_parens(text)


def normalize_assertion(assertion_line: str) -> str:
    raw = str(assertion_line or "").strip()
    if not raw:
        return ""
    raw = raw.rstrip(";").strip()
    raw = collapse_ws(raw)
    match = re.match(
        r"^assert property\s*\(@\(posedge clk\)\s*disable iff\s*\(!rst_n\)\s*(.*)\)$",
        raw,
        flags=re.IGNORECASE,
    )
    if not match:
        return raw.lower()
    body = match.group(1).strip()
    implication = None
    for token in ("|->", "|=>"):
        if token in body:
            implication = token
            antecedent, consequent = body.split(token, 1)
            break
    if implication is None:
        return raw.lower()

    antecedent = normalize_expr(antecedent)
    consequent = normalize_expr(consequent)
    return f"assert property (@(posedge clk) disable iff (!rst_n) ({antecedent}) {implication} ({consequent}));"


def first_nonblank(series: pd.Series):
    for value in series:
        if pd.isna(value):
            continue
        if str(value).strip() != "":
            return value
    return ""


def any_true(series: pd.Series):
    vals = [bool(v) for v in series if pd.notna(v)]
    return any(vals) if vals else False


def tri_state_semantic(series: pd.Series):
    vals = [parse_bool(v) for v in series]
    present = [v for v in vals if pd.notna(v)]
    if not present:
        return ""
    if any(v is True for v in present):
        return True
    if any(v is False for v in present):
        return False
    return ""


def max_int(series: pd.Series):
    vals = [int(v) for v in series if pd.notna(v)]
    return max(vals) if vals else 0


def join_unique(values: Iterable) -> str:
    seen = []
    for value in values:
        if pd.isna(value):
            continue
        text = str(value).strip()
        if not text:
            continue
        if text not in seen:
            seen.append(text)
    return "; ".join(seen)


def failure_reason_row(row: pd.Series) -> str:
    parts = []
    for field in (
        "compile_error",
        "unsupported_reason",
        "trace_overfit_reason",
        "trace_literal_warning_reason",
    ):
        value = row.get(field, "")
        if pd.notna(value) and str(value).strip():
            parts.append(str(value).strip())
    semantic_label = str(row.get("semantic_review_label", "") or "").strip()
    if semantic_label and semantic_label.lower() not in {"nan", "none"}:
        parts.append(f"semantic_review_label={semantic_label}")
    return join_unique(parts)


def build_stats(raw_df: pd.DataFrame, clean_df: pd.DataFrame) -> pd.DataFrame:
    def summarize(scope: str, scope_value: str, raw_part: pd.DataFrame, clean_part: pd.DataFrame):
        return {
            "scope": scope,
            "scope_value": scope_value,
            "raw_candidate_count": len(raw_part),
            "raw_assertion_text_count": int(raw_part["assertion_has_text"].sum()),
            "dedup_candidate_count": len(clean_part),
            "template_garbage_count": int(raw_part["is_template_garbage"].sum()),
            "unsupported_count": int(raw_part["is_unsupported"].sum()),
            "compile_fail_count": int(raw_part["is_compile_fail"].sum()),
            "syntax_error_count": int(raw_part["is_syntax_error"].sum()),
        }

    rows = [summarize("overall", "all", raw_df, clean_df)]
    for method in sorted(raw_df["method"].dropna().unique()):
        raw_part = raw_df[raw_df["method"] == method].copy()
        clean_part = clean_df[clean_df["method"] == method].copy()
        rows.append(summarize("method", method, raw_part, clean_part))
    return pd.DataFrame(rows)


def main():
    raw_df = pd.read_csv(SOURCE_REPORT)
    inventory_df = pd.read_csv(INVENTORY_CSV)

    inventory_cols = inventory_df[["case_name", "source_module", "bug_class", "bug_type"]].rename(
        columns={
            "source_module": "module",
            "bug_type": "bug_name_inventory",
            "bug_class": "bug_class_inventory",
        }
    )
    df = raw_df.merge(inventory_cols, on="case_name", how="left")

    bool_cols = [
        "syntax_pass",
        "analysis_supported",
        "compile_ok",
        "pass_on_correct",
        "fail_on_buggy",
        "non_vacuous",
        "antecedent_triggered",
        "trace_overfit",
        "trace_literal_warning",
        "heldout_compile_ok",
        "heldout_pass_on_correct",
        "heldout_fail_on_buggy",
        "heldout_non_vacuous",
        "heldout_antecedent_triggered",
        "strict_success",
        "semantic_reasonable",
    ]
    int_cols = [
        "candidate_index",
        "correct_antecedent_hits",
        "buggy_antecedent_hits",
        "heldout_correct_antecedent_hits",
        "heldout_buggy_antecedent_hits",
        "correct_fail_count",
        "buggy_fail_count",
        "heldout_correct_fail_count",
        "heldout_buggy_fail_count",
    ]

    for col in bool_cols:
        df[col] = df[col].apply(parse_bool)
    for col in int_cols:
        df[col] = df[col].apply(parse_int)

    df["case_id"] = df["case_name"]
    df["module"] = df["module"].fillna("")
    df["bug_name"] = df["bug_type"].fillna(df["bug_name_inventory"]).fillna("")
    df["bug_class"] = df["bug_class_inventory"].fillna("")
    df["prompt_type"] = df["method"].map(METHOD_TO_PROMPT_TYPE).fillna(df["method"])
    df["assertion_text"] = df["assertion_line"].fillna("").astype(str).str.strip()
    df["assertion_has_text"] = df["assertion_text"] != ""
    df["normalized_assertion"] = df["assertion_text"].apply(normalize_assertion)
    df["template_supported"] = df["failure_type"].fillna("") != "template_mismatch"
    df["is_template_garbage"] = (~df["assertion_has_text"]) | (df["failure_type"].fillna("") == "template_mismatch")
    df["is_unsupported"] = (df["analysis_supported"] == False) & (~df["is_template_garbage"])
    df["is_compile_fail"] = (df["compile_ok"] == False) & df["assertion_has_text"]
    df["is_syntax_error"] = df["compile_error"].fillna("").str.contains("syntax error", case=False, regex=False)
    df["failure_reason_row"] = df.apply(failure_reason_row, axis=1)

    clean_source = df[df["assertion_has_text"]].copy()
    clean_source = clean_source.sort_values(["case_id", "method", "normalized_assertion", "candidate_index"])

    grouped_rows = []
    group_cols = ["case_id", "module", "bug_name", "bug_class", "method", "prompt_type", "normalized_assertion"]

    for keys, group in clean_source.groupby(group_cols, dropna=False, sort=True):
        group = group.sort_values(["candidate_index", "assertion_text"])
        correct_hits_max = max_int(group["correct_antecedent_hits"])
        buggy_hits_max = max_int(group["buggy_antecedent_hits"])
        heldout_correct_hits_max = max_int(group["heldout_correct_antecedent_hits"])
        heldout_buggy_hits_max = max_int(group["heldout_buggy_antecedent_hits"])

        grouped_rows.append(
            {
                "case_id": keys[0],
                "module": keys[1],
                "bug_name": keys[2],
                "bug_class": keys[3],
                "method": keys[4],
                "prompt_type": keys[5],
                "assertion_text": first_nonblank(group["assertion_text"]),
                "normalized_assertion": keys[6],
                "compile_ok": any_true(group["compile_ok"]),
                "analysis_supported": any_true(group["analysis_supported"]),
                "template_supported": any_true(group["template_supported"]),
                "correct_pass": any_true(group["pass_on_correct"]),
                "fail_on_buggy": any_true(group["fail_on_buggy"]),
                "antecedent_hit_correct": correct_hits_max > 0,
                "antecedent_hit_buggy": buggy_hits_max > 0,
                "non_vacuous_correct": correct_hits_max > 0,
                "non_vacuous_buggy": buggy_hits_max > 0,
                "heldout_correct_pass": any_true(group["heldout_pass_on_correct"]),
                "heldout_buggy_fail": any_true(group["heldout_fail_on_buggy"]),
                "heldout_antecedent_hit": heldout_buggy_hits_max > 0,
                "heldout_non_vacuous": any_true(group["heldout_non_vacuous"]),
                "trace_overfit": any_true(group["trace_overfit"]),
                "literal_hardcoding": any_true(group["trace_literal_warning"]),
                "semantic_reasonable": tri_state_semantic(group["semantic_reasonable"]),
                "failure_type": join_unique(group["failure_type"]),
                "failure_reason": join_unique(group["failure_reason_row"]),
                "raw_candidate_count": len(group),
                "candidate_indices": ",".join(str(int(v)) for v in group["candidate_index"].dropna().astype(int).tolist()),
                "correct_antecedent_hits_max": correct_hits_max,
                "buggy_antecedent_hits_max": buggy_hits_max,
                "heldout_correct_antecedent_hits_max": heldout_correct_hits_max,
                "heldout_buggy_antecedent_hits_max": heldout_buggy_hits_max,
            }
        )

    clean_df = pd.DataFrame(grouped_rows)
    clean_df = clean_df.sort_values(["case_id", "method", "normalized_assertion"]).reset_index(drop=True)

    stats_df = build_stats(df, clean_df)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    clean_df.to_csv(OUTPUT_MASTER, index=False)
    stats_df.to_csv(OUTPUT_STATS, index=False)

    notes = f"""# Assertion clean version notes

- Source report: `{SOURCE_REPORT.relative_to(ROOT)}`
- Inventory join: `{INVENTORY_CSV.relative_to(ROOT)}`
- Main table: `{OUTPUT_MASTER.relative_to(ROOT)}`
- Stats table: `{OUTPUT_STATS.relative_to(ROOT)}`

## Dedupe rule

- One clean-row per `(case_id, method, normalized_assertion)`.
- `normalized_assertion` is built from `assertion_text` after:
  - whitespace normalization
  - outer-parenthesis stripping
  - canonicalizing spaced binary `&`/`&&` to `&&`
  - canonicalizing spaced binary `|`/`||` to `||`
  - rebuilding the assertion into one canonical `assert property ...` line

## Counting rule

- `raw_candidate_count`: all raw rows in `strict_eval_report_iv12.csv`
- `dedup_candidate_count`: number of clean assertion rows after assertion-level dedupe
- `template_garbage_count`: raw rows with empty assertion text or `failure_type == template_mismatch`
- `unsupported_count`: raw rows with `analysis_supported == False` after excluding template garbage
- `compile_fail_count`: raw rows with non-empty assertion text and `compile_ok == False`
- `syntax_error_count`: raw rows whose `compile_error` contains `syntax error`

## Important separation

- `template_garbage_count`, `unsupported_count`, `compile_fail_count`, and `syntax_error_count` are emitted as separate stats.
- The clean master table only includes rows with non-empty `assertion_text`.
- `heldout_antecedent_hit` means buggy held-out trace antecedent reachability (`heldout_buggy_antecedent_hits > 0`), not "either held-out trace".
"""
    OUTPUT_NOTES.write_text(notes, encoding="utf-8")

    print(f"Wrote {OUTPUT_MASTER}")
    print(f"Wrote {OUTPUT_STATS}")
    print(f"Wrote {OUTPUT_NOTES}")
    print(f"raw_candidate_count={len(df)}")
    print(f"dedup_candidate_count={len(clean_df)}")


if __name__ == "__main__":
    main()
