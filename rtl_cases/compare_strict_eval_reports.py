#!/usr/bin/env python3
import argparse
import csv
import re
from collections import Counter
from pathlib import Path
from typing import Dict, List, Tuple


SVA_BASENAME_TO_METHOD = {
    "sva_1_spec_only.sv": "spec_only",
    "sva_2_spec_plus_rtl.sv": "spec_plus_rtl",
    "sva_3_spec_rtl_raw_trace.sv": "spec_rtl_raw_trace",
    "sva_4_spec_rtl_trace_summary.sv": "spec_rtl_trace_summary",
}

CANDIDATE_SUFFIX_RE = re.compile(r"^(?P<base>.+)__cand_(?P<idx>\d+)\.sv$")


def to_bool(value: str) -> bool:
    return str(value).strip().lower() == "true"


def infer_method(row: Dict[str, str]) -> str:
    method = (row.get("method") or "").strip()
    if method:
        return method
    name = Path(row.get("sva_file", "")).name
    m = CANDIDATE_SUFFIX_RE.fullmatch(name)
    if m:
        name = m.group("base") + ".sv"
    return SVA_BASENAME_TO_METHOD.get(name, "")


def infer_candidate_index(row: Dict[str, str]) -> str:
    candidate_index = (row.get("candidate_index") or "").strip()
    if candidate_index:
        return candidate_index
    name = Path(row.get("sva_file", "")).name
    m = CANDIDATE_SUFFIX_RE.fullmatch(name)
    if m:
        return m.group("idx")
    return ""


def read_report(path: Path) -> Dict[Tuple[str, str, str], Dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    out: Dict[Tuple[str, str, str], Dict[str, str]] = {}
    for row in rows:
        key = (
            (row.get("case_name") or "").strip(),
            infer_method(row),
            infer_candidate_index(row),
        )
        out[key] = row
    return out


def read_grammar_versions(path: Path) -> List[str]:
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    versions = sorted({(row.get("grammar_version") or "").strip() for row in rows if row})
    return versions


def classify_change(before: Dict[str, str], after: Dict[str, str]) -> str:
    if not before and after:
        return "new_in_after"
    if before and not after:
        return "missing_in_after"
    before_strict = to_bool(before.get("strict_success", "False"))
    after_strict = to_bool(after.get("strict_success", "False"))
    if before_strict and after_strict:
        return "strict_success_unchanged"
    if (not before_strict) and after_strict:
        return "improved_to_strict_success"
    if before_strict and (not after_strict):
        return "regressed_from_strict_success"
    if before.get("failure_type", "") != after.get("failure_type", ""):
        return "failure_type_changed"
    if (before.get("assertion_line", "") or "").strip() != (after.get("assertion_line", "") or "").strip():
        return "assertion_changed"
    return "unchanged"


def summarize_counts(rows: List[Dict[str, str]], prefix: str) -> Dict[str, int]:
    counts: Counter[str] = Counter()
    counts[f"{prefix}_total"] = len(rows)
    counts[f"{prefix}_strict_success"] = sum(
        1 for row in rows if to_bool(row.get("strict_success", "False"))
    )
    for row in rows:
        counts[f"{prefix}_failure_type::{row.get('failure_type', '')}"] += 1
    return dict(counts)


def write_detailed_csv(path: Path, rows: List[Dict[str, str]]) -> None:
    fields = [
        "case_name",
        "bug_type",
        "method",
        "candidate_index",
        "change_type",
        "before_strict_success",
        "after_strict_success",
        "before_failure_type",
        "after_failure_type",
        "before_template_ok",
        "after_template_ok",
        "before_compile_ok",
        "after_compile_ok",
        "before_correct_pass",
        "after_correct_pass",
        "before_buggy_fail",
        "after_buggy_fail",
        "before_non_vacuous",
        "after_non_vacuous",
        "before_antecedent_triggered",
        "after_antecedent_triggered",
        "before_semantic_reasonable",
        "after_semantic_reasonable",
        "before_assertion_line",
        "after_assertion_line",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fields})


def write_summary_md(path: Path, before_rows: List[Dict[str, str]], after_rows: List[Dict[str, str]], detailed_rows: List[Dict[str, str]]) -> None:
    before_counts = summarize_counts(before_rows, "before")
    after_counts = summarize_counts(after_rows, "after")
    change_counts = Counter(row["change_type"] for row in detailed_rows)

    lines = [
        "# Strict Eval Comparison",
        "",
        "## Overall",
        "",
        f"- Grammar version: {(after_rows[0].get('grammar_version', '') if after_rows else '') or '(missing)'}",
        f"- Before strict_success: {before_counts.get('before_strict_success', 0)}/{before_counts.get('before_total', 0)}",
        f"- After strict_success: {after_counts.get('after_strict_success', 0)}/{after_counts.get('after_total', 0)}",
        f"- Improved to strict_success: {change_counts.get('improved_to_strict_success', 0)}",
        f"- Regressed from strict_success: {change_counts.get('regressed_from_strict_success', 0)}",
        f"- Failure type changed: {change_counts.get('failure_type_changed', 0)}",
        f"- Assertion changed only: {change_counts.get('assertion_changed', 0)}",
        "",
        "## Failure Type Counts",
        "",
        "| Failure Type | Before | After |",
        "|---|---:|---:|",
    ]

    failure_types = sorted(
        {
            key.split("::", 1)[1]
            for key in list(before_counts.keys()) + list(after_counts.keys())
            if "::" in key
        }
    )
    for failure_type in failure_types:
        lines.append(
            f"| {failure_type} | "
            f"{before_counts.get(f'before_failure_type::{failure_type}', 0)} | "
            f"{after_counts.get(f'after_failure_type::{failure_type}', 0)} |"
        )

    interesting = [
        row
        for row in detailed_rows
        if row["change_type"] != "unchanged"
    ]
    if interesting:
        lines.extend(
            [
                "",
                "## Changed Rows",
                "",
                "| Case | Method | Candidate | Change | Before | After |",
                "|---|---|---:|---|---|---|",
            ]
        )
        for row in interesting:
            lines.append(
                f"| {row['case_name']} | {row['method']} | {row['candidate_index'] or '-'} | {row['change_type']} | "
                f"{row['before_failure_type']} | {row['after_failure_type']} |"
            )

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare two strict evaluation CSV reports.")
    parser.add_argument("--before", required=True, help="Baseline strict eval CSV.")
    parser.add_argument("--after", required=True, help="New strict eval CSV.")
    parser.add_argument(
        "--output-prefix",
        default="strict_eval_comparison",
        help="Prefix for detailed CSV and markdown summary outputs.",
    )
    parser.add_argument(
        "--scope",
        choices=["after_only", "union"],
        default="after_only",
        help="Comparison scope: 'after_only' compares only rows present in the new report; 'union' includes missing rows from either side.",
    )
    args = parser.parse_args()

    before_path = Path(args.before).resolve()
    after_path = Path(args.after).resolve()
    output_prefix = Path(args.output_prefix).resolve()

    before_versions = read_grammar_versions(before_path)
    after_versions = read_grammar_versions(after_path)
    if before_versions != after_versions:
        raise SystemExit(
            "Refusing to compare reports built with different grammar versions: "
            f"before={before_versions or ['<missing>']} after={after_versions or ['<missing>']}"
        )

    before = read_report(before_path)
    after = read_report(after_path)
    if args.scope == "after_only":
        all_keys = sorted(after.keys())
    else:
        all_keys = sorted(set(before.keys()) | set(after.keys()))

    detailed_rows: List[Dict[str, str]] = []
    before_rows: List[Dict[str, str]] = []
    after_rows: List[Dict[str, str]] = []

    for key in all_keys:
        before_row = before.get(key, {})
        after_row = after.get(key, {})
        if before_row:
            before_rows.append(before_row)
        if after_row:
            after_rows.append(after_row)
        detailed_rows.append(
            {
                "case_name": key[0],
                "bug_type": after_row.get("bug_type", before_row.get("bug_type", "")),
                "method": key[1],
                "candidate_index": key[2],
                "change_type": classify_change(before_row, after_row),
                "before_strict_success": before_row.get("strict_success", ""),
                "after_strict_success": after_row.get("strict_success", ""),
                "before_failure_type": before_row.get("failure_type", ""),
                "after_failure_type": after_row.get("failure_type", ""),
                "before_template_ok": before_row.get("syntax_pass", ""),
                "after_template_ok": after_row.get("syntax_pass", ""),
                "before_compile_ok": before_row.get("compile_ok", ""),
                "after_compile_ok": after_row.get("compile_ok", ""),
                "before_correct_pass": before_row.get("pass_on_correct", ""),
                "after_correct_pass": after_row.get("pass_on_correct", ""),
                "before_buggy_fail": before_row.get("fail_on_buggy", ""),
                "after_buggy_fail": after_row.get("fail_on_buggy", ""),
                "before_non_vacuous": before_row.get("non_vacuous", ""),
                "after_non_vacuous": after_row.get("non_vacuous", ""),
                "before_antecedent_triggered": before_row.get("antecedent_triggered", ""),
                "after_antecedent_triggered": after_row.get("antecedent_triggered", ""),
                "before_semantic_reasonable": before_row.get("semantic_reasonable", ""),
                "after_semantic_reasonable": after_row.get("semantic_reasonable", ""),
                "before_assertion_line": before_row.get("assertion_line", ""),
                "after_assertion_line": after_row.get("assertion_line", ""),
            }
        )

    write_detailed_csv(output_prefix.with_suffix(".csv"), detailed_rows)
    write_summary_md(output_prefix.with_suffix(".md"), before_rows, after_rows, detailed_rows)
    print(f"[DONE] Wrote {output_prefix.with_suffix('.csv')}")
    print(f"[DONE] Wrote {output_prefix.with_suffix('.md')}")


if __name__ == "__main__":
    main()
