#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple


def to_bool(value: object) -> bool:
    return str(value).strip().lower() == "true"


def read_rows(path: Path) -> List[Dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_bug_class_lookup(root: Path) -> Dict[str, str]:
    manifest = json.loads((root / "case_manifest.json").read_text(encoding="utf-8"))
    return {
        str(case["name"]): str(case.get("bug_class", ""))
        for case in manifest["cases"]
    }


def dedup_case_method(rows: List[Dict[str, str]]) -> Dict[str, object]:
    return {
        "row_count": len(rows),
        "compile_ok": any(to_bool(row.get("compile_ok")) for row in rows),
        "correct_pass": any(to_bool(row.get("pass_on_correct")) for row in rows),
        "buggy_fail": any(to_bool(row.get("fail_on_buggy")) for row in rows),
        "non_vacuous": any(to_bool(row.get("non_vacuous")) for row in rows),
        "strict_success": any(to_bool(row.get("strict_success")) for row in rows),
        "candidate_indices": ",".join(
            str(row.get("candidate_index", "")).strip()
            for row in rows
            if str(row.get("candidate_index", "")).strip()
        ),
        "failure_types_seen": ";".join(
            sorted({str(row.get("failure_type", "")).strip() for row in rows if str(row.get("failure_type", "")).strip()})
        ),
    }


def summarize_case_rows(rows: List[Dict[str, object]]) -> Dict[str, int]:
    return {
        "cases": len(rows),
        "compile_ok": sum(1 for row in rows if bool(row["compile_ok"])),
        "correct_pass": sum(1 for row in rows if bool(row["correct_pass"])),
        "buggy_fail": sum(1 for row in rows if bool(row["buggy_fail"])),
        "non_vacuous": sum(1 for row in rows if bool(row["non_vacuous"])),
        "strict_success": sum(1 for row in rows if bool(row["strict_success"])),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Summarize strict eval results at case-level (deduped across candidates) by method x bug_class."
    )
    parser.add_argument("--root", required=True, help="Dataset root containing case_manifest.json.")
    parser.add_argument("--report", required=True, help="Strict eval CSV report path.")
    parser.add_argument(
        "--output-csv",
        default="strict_eval_case_dedup_by_method_and_bug_class.csv",
        help="Output CSV path for method x bug_class summary.",
    )
    parser.add_argument(
        "--output-case-csv",
        default="strict_eval_case_dedup_rows.csv",
        help="Output CSV path for deduped case x method rows.",
    )
    parser.add_argument(
        "--output-gap-csv",
        default="strict_eval_case_dedup_gap_vs_baseline.csv",
        help="Output CSV path for compare-vs-baseline gap rows.",
    )
    parser.add_argument(
        "--baseline-method",
        default="spec_plus_rtl",
        help="Baseline method for gap columns (default: spec_plus_rtl).",
    )
    parser.add_argument(
        "--compare-method",
        default="spec_rtl_trace_summary",
        help="Compare method for gap columns (default: spec_rtl_trace_summary).",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    report_path = Path(args.report).resolve()
    bug_class_by_case = load_bug_class_lookup(root)
    rows = read_rows(report_path)

    grouped_case_method: Dict[Tuple[str, str], List[Dict[str, str]]] = defaultdict(list)
    for row in rows:
        case_name = str(row.get("case_name", "")).strip()
        method = str(row.get("method", "")).strip()
        if not case_name or not method:
            continue
        grouped_case_method[(case_name, method)].append(row)

    dedup_rows: List[Dict[str, object]] = []
    grouped_method_bug_class: Dict[Tuple[str, str], List[Dict[str, object]]] = defaultdict(list)
    for (case_name, method), items in sorted(grouped_case_method.items()):
        bug_class = bug_class_by_case.get(case_name, "")
        dedup = dedup_case_method(items)
        out_row: Dict[str, object] = {
            "case_name": case_name,
            "method": method,
            "bug_class": bug_class,
            **dedup,
        }
        dedup_rows.append(out_row)
        grouped_method_bug_class[(method, bug_class)].append(out_row)

    summary_rows: List[Dict[str, object]] = []
    for (method, bug_class), items in sorted(grouped_method_bug_class.items()):
        stats = summarize_case_rows(items)
        summary_rows.append(
            {
                "method": method,
                "bug_class": bug_class,
                **stats,
            }
        )

    summary_index = {(row["method"], row["bug_class"]): row for row in summary_rows}
    gap_rows: List[Dict[str, object]] = []
    for bug_class in sorted({row["bug_class"] for row in summary_rows}):
        base = summary_index.get((args.baseline_method, bug_class))
        comp = summary_index.get((args.compare_method, bug_class))
        if not base or not comp:
            continue
        gap_rows.append(
            {
                "method": args.compare_method,
                "bug_class": bug_class,
                "cases": comp["cases"],
                "compile_ok": comp["compile_ok"],
                "correct_pass": comp["correct_pass"],
                "buggy_fail": comp["buggy_fail"],
                "non_vacuous": comp["non_vacuous"],
                "strict_success": comp["strict_success"],
                "gap_vs_" + args.baseline_method + "_correct_pass": int(comp["correct_pass"]) - int(base["correct_pass"]),
                "gap_vs_" + args.baseline_method + "_buggy_fail": int(comp["buggy_fail"]) - int(base["buggy_fail"]),
                "gap_vs_" + args.baseline_method + "_strict_success": int(comp["strict_success"]) - int(base["strict_success"]),
            }
        )

    overall_by_method: Dict[str, List[Dict[str, object]]] = defaultdict(list)
    for row in dedup_rows:
        overall_by_method[str(row["method"])].append(row)
    overall_summary: Dict[str, Dict[str, int]] = {
        method: summarize_case_rows(items) for method, items in overall_by_method.items()
    }
    if args.baseline_method in overall_summary and args.compare_method in overall_summary:
        base = overall_summary[args.baseline_method]
        comp = overall_summary[args.compare_method]
        gap_rows.append(
            {
                "method": args.compare_method,
                "bug_class": "overall",
                "cases": comp["cases"],
                "compile_ok": comp["compile_ok"],
                "correct_pass": comp["correct_pass"],
                "buggy_fail": comp["buggy_fail"],
                "non_vacuous": comp["non_vacuous"],
                "strict_success": comp["strict_success"],
                "gap_vs_" + args.baseline_method + "_correct_pass": int(comp["correct_pass"]) - int(base["correct_pass"]),
                "gap_vs_" + args.baseline_method + "_buggy_fail": int(comp["buggy_fail"]) - int(base["buggy_fail"]),
                "gap_vs_" + args.baseline_method + "_strict_success": int(comp["strict_success"]) - int(base["strict_success"]),
            }
        )

    out_case_csv = Path(args.output_case_csv).resolve()
    out_case_csv.parent.mkdir(parents=True, exist_ok=True)
    case_fields = [
        "case_name",
        "method",
        "bug_class",
        "row_count",
        "compile_ok",
        "correct_pass",
        "buggy_fail",
        "non_vacuous",
        "strict_success",
        "candidate_indices",
        "failure_types_seen",
    ]
    with out_case_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=case_fields)
        writer.writeheader()
        for row in dedup_rows:
            writer.writerow({field: row.get(field, "") for field in case_fields})

    out_csv = Path(args.output_csv).resolve()
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    summary_fields = [
        "method",
        "bug_class",
        "cases",
        "compile_ok",
        "correct_pass",
        "buggy_fail",
        "non_vacuous",
        "strict_success",
        "gap_vs_" + args.baseline_method + "_correct_pass",
        "gap_vs_" + args.baseline_method + "_buggy_fail",
        "gap_vs_" + args.baseline_method + "_strict_success",
    ]
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=summary_fields)
        writer.writeheader()
        gap_index = {row["bug_class"]: row for row in gap_rows}
        for row in summary_rows:
            bug_class = str(row["bug_class"])
            enriched = dict(row)
            gap = gap_index.get(bug_class, {})
            enriched["gap_vs_" + args.baseline_method + "_correct_pass"] = gap.get(
                "gap_vs_" + args.baseline_method + "_correct_pass", ""
            )
            enriched["gap_vs_" + args.baseline_method + "_buggy_fail"] = gap.get(
                "gap_vs_" + args.baseline_method + "_buggy_fail", ""
            )
            enriched["gap_vs_" + args.baseline_method + "_strict_success"] = gap.get(
                "gap_vs_" + args.baseline_method + "_strict_success", ""
            )
            writer.writerow({field: enriched.get(field, "") for field in summary_fields})
        if "overall" in gap_index:
            overall_gap = {
                "method": args.compare_method,
                "bug_class": "overall",
                **gap_index["overall"],
            }
            writer.writerow({field: overall_gap.get(field, "") for field in summary_fields})

    out_gap_csv = Path(args.output_gap_csv).resolve()
    out_gap_csv.parent.mkdir(parents=True, exist_ok=True)
    gap_fields = [
        "method",
        "bug_class",
        "cases",
        "compile_ok",
        "correct_pass",
        "buggy_fail",
        "non_vacuous",
        "strict_success",
        "gap_vs_" + args.baseline_method + "_correct_pass",
        "gap_vs_" + args.baseline_method + "_buggy_fail",
        "gap_vs_" + args.baseline_method + "_strict_success",
    ]
    with out_gap_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=gap_fields)
        writer.writeheader()
        for row in gap_rows:
            writer.writerow({field: row.get(field, "") for field in gap_fields})

    print(f"[DONE] Wrote case-level dedup rows: {out_case_csv}")
    print(f"[DONE] Wrote case-level method x bug_class summary: {out_csv}")
    print(f"[DONE] Wrote compare-vs-baseline gap rows: {out_gap_csv}")


if __name__ == "__main__":
    main()
