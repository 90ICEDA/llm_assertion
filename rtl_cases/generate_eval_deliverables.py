#!/usr/bin/env python3
import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple


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

BEST_FIELDS = [
    "case_name",
    "bug_type",
    "method",
    "method_label",
    "candidate_index",
    "failure_type",
    "template_ok",
    "compile_ok",
    "analysis_supported",
    "unsupported_reason",
    "pass_on_correct",
    "fail_on_buggy",
    "non_vacuous",
    "antecedent_triggered",
    "trace_overfit",
    "trace_overfit_reason",
    "heldout_pass_on_correct",
    "heldout_fail_on_buggy",
    "heldout_non_vacuous",
    "strict_success",
    "semantic_reasonable",
    "assertion_line",
    "sva_file",
]

MANUAL_GOLDEN_FIELDS = [
    "Case",
    "Bug Type",
    "Golden SVA",
    "Expected Behavior",
    "First Divergence Cycle",
    "Relevant Signals",
    "Temporal Type",
]


def to_bool(value: object) -> bool:
    return str(value).strip().lower() == "true"


def read_manifest(root: Path) -> List[Dict[str, object]]:
    return json.loads((root / "case_manifest.json").read_text(encoding="utf-8"))["cases"]


def read_report(path: Path) -> List[Dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
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
    unique_cases = sorted(
        {(row.get("case_name") or "").strip() for row in rows if row.get("case_name")}
    )
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


def write_by_method_csv(path: Path, rows: List[Dict[str, object]]) -> None:
    fields = [
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
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fields})


def write_by_method_md(path: Path, rows: List[Dict[str, object]]) -> None:
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
        lines.append("")
        if not counts:
            lines.append("- (no rows)")
            lines.append("")
            continue
        lines.append("| Failure Type | Count |")
        lines.append("|---|---:|")
        for failure_type, count in counts.items():
            lines.append(f"| {failure_type or '(empty)'} | {count} |")
        lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def semantic_is_true(value: str) -> bool:
    return str(value).strip().lower() == "true"


def method_rank(method: str) -> int:
    ranking = {
        "spec_rtl_trace_summary": 4,
        "spec_rtl_raw_trace": 3,
        "spec_plus_rtl": 2,
        "spec_only": 1,
    }
    return ranking.get(method, 0)


def parse_candidate_index(value: str) -> int:
    try:
        return int(str(value).strip())
    except Exception:
        return 9999


def case_row_score(row: Dict[str, str]) -> Tuple[int, int, int, int, int, int, int, int, int, int]:
    return (
        1 if to_bool(row.get("strict_success", "False")) else 0,
        1 if not to_bool(row.get("trace_overfit", "False")) else 0,
        1 if to_bool(row.get("compile_ok", "False")) else 0,
        1 if to_bool(row.get("syntax_pass", "False")) else 0,
        1 if to_bool(row.get("pass_on_correct", "False")) else 0,
        1 if to_bool(row.get("fail_on_buggy", "False")) else 0,
        1 if to_bool(row.get("non_vacuous", "False")) else 0,
        1 if to_bool(row.get("antecedent_triggered", "False")) else 0,
        1 if semantic_is_true(row.get("semantic_reasonable", "")) else 0,
        method_rank((row.get("method") or "").strip()),
    )


def pick_best_per_case(rows: List[Dict[str, str]]) -> Dict[str, Dict[str, str]]:
    grouped: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    for row in rows:
        case_name = (row.get("case_name") or "").strip()
        if case_name:
            grouped[case_name].append(row)

    best: Dict[str, Dict[str, str]] = {}
    for case_name, group_rows in grouped.items():
        sorted_rows = sorted(
            group_rows,
            key=lambda r: (
                case_row_score(r),
                -parse_candidate_index(r.get("candidate_index", "")),
            ),
            reverse=True,
        )
        best[case_name] = sorted_rows[0]
    return best


def write_best_csv(path: Path, case_order: List[str], best: Dict[str, Dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=BEST_FIELDS)
        w.writeheader()
        for case_name in case_order:
            row = best.get(case_name)
            if not row:
                continue
            method = (row.get("method") or "").strip()
            w.writerow(
                {
                    "case_name": case_name,
                    "bug_type": row.get("bug_type", ""),
                    "method": method,
                    "method_label": METHOD_LABELS.get(method, method),
                    "candidate_index": row.get("candidate_index", ""),
                    "failure_type": row.get("failure_type", ""),
                    "template_ok": row.get("syntax_pass", ""),
                    "compile_ok": row.get("compile_ok", ""),
                    "analysis_supported": row.get("analysis_supported", ""),
                    "unsupported_reason": row.get("unsupported_reason", ""),
                    "pass_on_correct": row.get("pass_on_correct", ""),
                    "fail_on_buggy": row.get("fail_on_buggy", ""),
                    "non_vacuous": row.get("non_vacuous", ""),
                    "antecedent_triggered": row.get("antecedent_triggered", ""),
                    "trace_overfit": row.get("trace_overfit", ""),
                    "trace_overfit_reason": row.get("trace_overfit_reason", ""),
                    "heldout_pass_on_correct": row.get("heldout_pass_on_correct", ""),
                    "heldout_fail_on_buggy": row.get("heldout_fail_on_buggy", ""),
                    "heldout_non_vacuous": row.get("heldout_non_vacuous", ""),
                    "strict_success": row.get("strict_success", ""),
                    "semantic_reasonable": row.get("semantic_reasonable", ""),
                    "assertion_line": row.get("assertion_line", ""),
                    "sva_file": row.get("sva_file", ""),
                }
            )


def build_best_rows(case_order: List[str], best: Dict[str, Dict[str, str]]) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    for case_name in case_order:
        row = best.get(case_name)
        if not row:
            continue
        method = (row.get("method") or "").strip()
        rows.append(
            {
                "case_name": case_name,
                "bug_type": row.get("bug_type", ""),
                "method": method,
                "method_label": METHOD_LABELS.get(method, method),
                "candidate_index": row.get("candidate_index", ""),
                "failure_type": row.get("failure_type", ""),
                "template_ok": row.get("syntax_pass", ""),
                "compile_ok": row.get("compile_ok", ""),
                "analysis_supported": row.get("analysis_supported", ""),
                "unsupported_reason": row.get("unsupported_reason", ""),
                "pass_on_correct": row.get("pass_on_correct", ""),
                "fail_on_buggy": row.get("fail_on_buggy", ""),
                "non_vacuous": row.get("non_vacuous", ""),
                "antecedent_triggered": row.get("antecedent_triggered", ""),
                "trace_overfit": row.get("trace_overfit", ""),
                "trace_overfit_reason": row.get("trace_overfit_reason", ""),
                "heldout_pass_on_correct": row.get("heldout_pass_on_correct", ""),
                "heldout_fail_on_buggy": row.get("heldout_fail_on_buggy", ""),
                "heldout_non_vacuous": row.get("heldout_non_vacuous", ""),
                "strict_success": row.get("strict_success", ""),
                "semantic_reasonable": row.get("semantic_reasonable", ""),
                "assertion_line": row.get("assertion_line", ""),
                "sva_file": row.get("sva_file", ""),
            }
        )
    return rows


def write_best_md(
    path: Path, case_order: List[str], bug_type_by_case: Dict[str, str], best: Dict[str, Dict[str, str]]
) -> None:
    lines = [
        "# Best Generated Assertion Per Case",
        "",
        "Selection rule: prefer `strict_success`, then non-`trace_overfit`, then template match, compile success, "
        "`correct_pass`, `buggy_fail`, `non_vacuous`, `antecedent_triggered`, and richer prompt methods as tie-breaker.",
        "",
    ]
    for case_name in case_order:
        row = best.get(case_name)
        if not row:
            continue
        method = (row.get("method") or "").strip()
        lines.append(f"## {case_name}")
        lines.append("")
        lines.append(f"- Bug type: {bug_type_by_case.get(case_name, '')}")
        lines.append(f"- Chosen method: {METHOD_LABELS.get(method, method)}")
        lines.append(f"- Candidate: {row.get('candidate_index', '')}")
        lines.append(f"- Failure type: {row.get('failure_type', '')}")
        lines.append(f"- template_ok: {row.get('syntax_pass', '')}")
        lines.append(f"- compile_ok: {row.get('compile_ok', '')}")
        lines.append(f"- analysis_supported: {row.get('analysis_supported', '')}")
        if row.get("unsupported_reason"):
            lines.append(f"- unsupported_reason: {row.get('unsupported_reason', '')}")
        lines.append(f"- correct_pass: {row.get('pass_on_correct', '')}")
        lines.append(f"- buggy_fail: {row.get('fail_on_buggy', '')}")
        lines.append(f"- non_vacuous: {row.get('non_vacuous', '')}")
        lines.append(f"- antecedent_triggered: {row.get('antecedent_triggered', '')}")
        lines.append(f"- trace_overfit: {row.get('trace_overfit', '')}")
        if row.get("trace_overfit_reason"):
            lines.append(f"- trace_overfit_reason: {row.get('trace_overfit_reason', '')}")
        lines.append(f"- heldout_pass_on_correct: {row.get('heldout_pass_on_correct', '')}")
        lines.append(f"- heldout_fail_on_buggy: {row.get('heldout_fail_on_buggy', '')}")
        lines.append(f"- heldout_non_vacuous: {row.get('heldout_non_vacuous', '')}")
        lines.append(f"- Assertion: `{row.get('assertion_line', '')}`")
        lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_manual_golden_table(path: Path, cases: List[Dict[str, object]]) -> None:
    lines = [
        "# Manual Golden SVA Table",
        "",
        "These golden assertions are human reference assertions chosen for semantic strength and bug-target relevance.",
        "They are not limited to the weaker patterns that happen to be easiest for the current automatic evaluator to score.",
        "",
        "| Case | Bug Type | Golden SVA | Expected Behavior | First Divergence Cycle | Relevant Signals | Temporal Type |",
        "|---|---|---|---|---:|---|---|",
    ]
    for case in cases:
        golden = case.get("golden_sva", {})
        relevant = ", ".join(golden.get("relevant_signals", []))
        lines.append(
            f"| {case.get('name', '')} | {case.get('bug_type', '')} | "
            f"`{golden.get('sva', '')}` | {golden.get('expected_behavior', '')} | "
            f"{golden.get('first_divergence_cycle', '')} | `{relevant}` | "
            f"{golden.get('temporal_type', '')} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_manual_golden_rows(cases: List[Dict[str, object]]) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    for case in cases:
        golden = case.get("golden_sva", {})
        rows.append(
            {
                "Case": case.get("name", ""),
                "Bug Type": case.get("bug_type", ""),
                "Golden SVA": golden.get("sva", ""),
                "Expected Behavior": golden.get("expected_behavior", ""),
                "First Divergence Cycle": golden.get("first_divergence_cycle", ""),
                "Relevant Signals": ", ".join(golden.get("relevant_signals", [])),
                "Temporal Type": golden.get("temporal_type", ""),
            }
        )
    return rows


def write_deliverables_index(path: Path) -> None:
    lines = [
        "# Deliverables Index",
        "",
        "1. Manual golden assertion table",
        "   - `MANUAL_GOLDEN_SVA_TABLE.md`",
        "2. New automatic evaluation script",
        "   - `evaluate_generated_sva_v2.py`",
        "3. Good/bad waveform divergence summary script",
        "   - `summarize_trace_divergence.py`",
        "4. SVA static filter script",
        "   - `sva_static_filter.py`",
        "5. Full rerun experiment result table",
        "   - `strict_eval_report_rerun.csv`",
        "6. Four-method summary comparison",
        "   - `strict_eval_comparison_rerun_by_method.csv`",
        "   - `strict_eval_comparison_rerun_by_method.md`",
        "7. Best assertion per case document",
        "   - `BEST_ASSERTION_PER_CASE.md`",
        "   - `best_assertion_per_case.csv`",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_by_method_outputs(report_rows: List[Dict[str, str]]) -> List[Dict[str, object]]:
    grouped: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    for row in report_rows:
        method = (row.get("method") or "").strip()
        grouped[method].append(row)

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
    return summary_rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate deliverable documents/tables from strict evaluation report."
    )
    parser.add_argument("--root", default=".", help="Path to rtl_cases root.")
    parser.add_argument(
        "--strict-report",
        default="strict_eval_report_rerun.csv",
        help="Strict evaluation CSV used for summaries and best assertion selection.",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    cases = read_manifest(root)
    case_order = [str(case.get("name", "")) for case in cases]
    bug_type_by_case = {
        str(case.get("name", "")): str(case.get("bug_type", "")) for case in cases
    }

    report_path = (root / args.strict_report).resolve()
    report_rows = read_report(report_path)

    by_method_rows = build_by_method_outputs(report_rows)
    write_by_method_csv(root / "strict_eval_comparison_rerun_by_method.csv", by_method_rows)
    write_by_method_md(root / "strict_eval_comparison_rerun_by_method.md", by_method_rows)
    best = pick_best_per_case(report_rows)
    write_best_md(root / "BEST_ASSERTION_PER_CASE.md", case_order, bug_type_by_case, best)
    write_best_csv(root / "best_assertion_per_case.csv", case_order, best)

    write_manual_golden_table(root / "MANUAL_GOLDEN_SVA_TABLE.md", cases)
    write_deliverables_index(root / "DELIVERABLES_INDEX.md")

    print(f"[DONE] Loaded strict report: {report_path}")
    print(f"[DONE] Wrote {root / 'strict_eval_comparison_rerun_by_method.csv'}")
    print(f"[DONE] Wrote {root / 'strict_eval_comparison_rerun_by_method.md'}")
    print(f"[DONE] Wrote {root / 'BEST_ASSERTION_PER_CASE.md'}")
    print(f"[DONE] Wrote {root / 'best_assertion_per_case.csv'}")
    print(f"[DONE] Wrote {root / 'MANUAL_GOLDEN_SVA_TABLE.md'}")
    print(f"[DONE] Wrote {root / 'DELIVERABLES_INDEX.md'}")


if __name__ == "__main__":
    main()
