#!/usr/bin/env python3
import argparse
import csv
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List



METHOD_ORDER = [
    "spec_only",
    "spec_plus_rtl",
    "spec_rtl_raw_trace",
    "spec_rtl_trace_summary",
]

METHOD_LABELS = {
    "spec_only": "spec only",
    "spec_plus_rtl": "spec + RTL",
    "spec_rtl_raw_trace": "spec + RTL + raw trace",
    "spec_rtl_trace_summary": "spec + RTL + trace summary",
}

SUMMARY_FIELDS = [
    "method",
    "label",
    "raw_rows",
    "num_rows",
    "num_cases",
    "template_ok",
    "compile_ok",
    "correct_pass",
    "buggy_fail",
    "non_vacuous",
    "antecedent_triggered",
    "strict_success_assertions",
    "success_cases",
    "failure_type_counts",
]


def to_bool(value: str) -> bool:
    return str(value).strip().lower() == "true"


def read_rows(path: Path) -> List[Dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def normalize_assertion(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def dedupe_rows(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    seen = set()
    deduped: List[Dict[str, str]] = []
    for row in rows:
        key = (
            (row.get("case_name") or "").strip(),
            (row.get("method") or "").strip(),
            normalize_assertion(row.get("assertion_line", "")),
        )
        if not key[2]:
            continue
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def summarize_method(rows: List[Dict[str, str]]) -> Dict[str, object]:
    deduped_rows = dedupe_rows(rows)
    total = len(deduped_rows)
    failure_counts: Counter[str] = Counter(row.get("failure_type", "") for row in deduped_rows)
    unique_cases = sorted({(row.get("case_name") or "").strip() for row in rows if row.get("case_name")})
    success_cases = sorted(
        {
            (row.get("case_name") or "").strip()
            for row in deduped_rows
            if to_bool(row.get("strict_success", "False"))
        }
    )
    return {
        "raw_rows": len(rows),
        "num_rows": total,
        "num_cases": len(unique_cases),
        "template_ok": sum(1 for row in deduped_rows if to_bool(row.get("syntax_pass", "False"))),
        "compile_ok": sum(1 for row in deduped_rows if to_bool(row.get("compile_ok", "False"))),
        "correct_pass": sum(1 for row in deduped_rows if to_bool(row.get("pass_on_correct", "False"))),
        "buggy_fail": sum(1 for row in deduped_rows if to_bool(row.get("fail_on_buggy", "False"))),
        "non_vacuous": sum(1 for row in deduped_rows if to_bool(row.get("non_vacuous", "False"))),
        "antecedent_triggered": sum(
            1 for row in deduped_rows if to_bool(row.get("antecedent_triggered", "False"))
        ),
        "strict_success_assertions": sum(
            1 for row in deduped_rows if to_bool(row.get("strict_success", "False"))
        ),
        "success_cases": len(success_cases),
        "failure_counts": dict(sorted(failure_counts.items())),
    }


def write_csv(path: Path, rows: List[Dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=SUMMARY_FIELDS)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in SUMMARY_FIELDS})


def write_md(path: Path, rows: List[Dict[str, object]]) -> None:
    lines = [
        "# Strict Eval By Prompt Method",
        "",
        "| Method | Raw Rows | Distinct Assertions | Cases | Template Match | Compile OK | Correct Pass | Buggy Fail | Non-vacuous | Antecedent Triggered | Strict Success Assertions | Success Cases |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['label']} | {row['raw_rows']} | {row['num_rows']} | {row['num_cases']} | {row['template_ok']} | "
            f"{row['compile_ok']} | {row['correct_pass']} | {row['buggy_fail']} | {row['non_vacuous']} | "
            f"{row['antecedent_triggered']} | {row['strict_success_assertions']} | {row['success_cases']} |"
        )

    lines.extend(["", "## Failure Type Breakdown", ""])
    for row in rows:
        counts = row.get("failure_counts", {})
        lines.append(f"### {row['label']}")
        if not counts:
            lines.append("")
            lines.append("- (no rows)")
            lines.append("")
            continue
        lines.append("")
        lines.append("| Failure Type | Count |")
        lines.append("|---|---:|")
        for failure_type, count in counts.items():
            lines.append(f"| {failure_type or '(empty)'} | {count} |")
        lines.append("")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Summarize strict evaluation results by prompt method."
    )
    parser.add_argument("--report", required=True, help="Strict eval CSV report.")
    parser.add_argument(
        "--output-prefix",
        default="strict_eval_by_method",
        help="Output prefix for CSV/MD summaries.",
    )
    args = parser.parse_args()

    report_path = Path(args.report).resolve()
    output_prefix = Path(args.output_prefix).resolve()
    rows = read_rows(report_path)

    grouped: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[(row.get("method") or "").strip()].append(row)

    ordered_methods = [m for m in METHOD_ORDER if m in grouped] + [
        m for m in sorted(grouped.keys()) if m not in METHOD_ORDER
    ]

    summary_rows: List[Dict[str, object]] = []
    for method in ordered_methods:
        stats = summarize_method(grouped.get(method, []))
        summary_rows.append(
            {
                "method": method,
                "label": METHOD_LABELS.get(method, method),
                **stats,
                "failure_type_counts": "; ".join(
                    f"{k}={v}" for k, v in stats["failure_counts"].items()
                ),
            }
        )

    write_csv(output_prefix.with_suffix(".csv"), summary_rows)
    write_md(output_prefix.with_suffix(".md"), summary_rows)
    print(f"[DONE] Wrote {output_prefix.with_suffix('.csv')}")
    print(f"[DONE] Wrote {output_prefix.with_suffix('.md')}")


if __name__ == "__main__":
    main()
