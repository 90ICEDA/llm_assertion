#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, List


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


def summarize(rows: List[Dict[str, str]]) -> Dict[str, object]:
    return {
        "rows": len(rows),
        "compile_ok": sum(1 for row in rows if to_bool(row.get("compile_ok"))),
        "correct_pass": sum(1 for row in rows if to_bool(row.get("pass_on_correct"))),
        "buggy_fail": sum(1 for row in rows if to_bool(row.get("fail_on_buggy"))),
        "non_vacuous": sum(1 for row in rows if to_bool(row.get("non_vacuous"))),
        "strict_success": sum(1 for row in rows if to_bool(row.get("strict_success"))),
        "cases": len({row.get("case_name", "") for row in rows if row.get("case_name")}),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Summarize strict eval results by method x bug_class."
    )
    parser.add_argument("--root", required=True, help="Dataset root containing case_manifest.json.")
    parser.add_argument("--report", required=True, help="Strict eval CSV report path.")
    parser.add_argument(
        "--output-csv",
        default="strict_eval_by_method_and_bug_class.csv",
        help="Output CSV path.",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    report_path = Path(args.report).resolve()
    bug_class_by_case = load_bug_class_lookup(root)
    rows = read_rows(report_path)

    grouped: Dict[tuple[str, str], List[Dict[str, str]]] = defaultdict(list)
    for row in rows:
        case_name = str(row.get("case_name", ""))
        bug_class = bug_class_by_case.get(case_name, "")
        method = str(row.get("method", "")).strip()
        grouped[(method, bug_class)].append(row)

    out_rows: List[Dict[str, object]] = []
    for (method, bug_class), items in sorted(grouped.items()):
        stats = summarize(items)
        out_rows.append(
            {
                "method": method,
                "bug_class": bug_class,
                **stats,
            }
        )

    out_csv = Path(args.output_csv).resolve()
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "method",
        "bug_class",
        "rows",
        "cases",
        "compile_ok",
        "correct_pass",
        "buggy_fail",
        "non_vacuous",
        "strict_success",
    ]
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in out_rows:
            writer.writerow({field: row.get(field, "") for field in fields})

    print(f"[DONE] Wrote method x bug_class summary: {out_csv}")


if __name__ == "__main__":
    main()
