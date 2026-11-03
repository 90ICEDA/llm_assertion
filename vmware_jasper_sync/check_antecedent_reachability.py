#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Dict, List

from jasper_antecedent_reachability import run_jasper_on_case


def load_manifest(root: Path) -> List[Dict[str, object]]:
    return json.loads((root / "case_manifest.json").read_text(encoding="utf-8"))["cases"]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run JasperGold antecedent cover reachability checks for a dataset root."
    )
    parser.add_argument("--root", required=True, help="Dataset root to audit.")
    parser.add_argument("--jasper-binary", required=True, help="JasperGold binary name/path.")
    parser.add_argument("--output-csv", required=True, help="CSV report path.")
    parser.add_argument(
        "--report-dir",
        default="",
        help="Optional directory to save raw Jasper stdout reports. Defaults beside the CSV.",
    )
    parser.add_argument(
        "--case",
        action="append",
        default=[],
        help="Optional case name filter. Repeat to evaluate multiple cases.",
    )
    parser.add_argument("--prove-time-limit", default="1m", help="Jasper prove time limit.")
    parser.add_argument("--cover-time-limit", default="1m", help="Jasper cover time limit.")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    manifest_path = root / "case_manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Cannot find manifest: {manifest_path}")
    out_csv = Path(args.output_csv).resolve()
    report_dir = Path(args.report_dir).resolve() if args.report_dir else out_csv.with_suffix("")
    manifest = load_manifest(root)
    available_case_names = {str(entry.get("name", "")).strip() for entry in manifest}
    requested = {name.strip() for name in args.case if name.strip()}
    if requested:
        missing = sorted(name for name in requested if name not in available_case_names)
        if missing:
            raise ValueError(
                "Requested cases not found in manifest: " + ", ".join(missing)
            )
        manifest = [entry for entry in manifest if str(entry.get("name", "")) in requested]
    if not manifest:
        raise ValueError(f"No cases selected from manifest: {manifest_path}")

    print(f"[INFO] Selected {len(manifest)} case(s) from {manifest_path}")

    rows = []
    for case_entry in manifest:
        case_name = str(case_entry["name"])
        case_dir = root / case_name
        report_path = report_dir / f"{case_name}.txt"
        result = run_jasper_on_case(
            case_name=case_name,
            correct_v=case_dir / "correct.v",
            assertion_text=str(case_entry.get("golden_sva", {}).get("sva", "")).strip(),
            jasper_binary=args.jasper_binary,
            report_path=report_path,
            prove_time_limit=args.prove_time_limit,
            cover_time_limit=args.cover_time_limit,
        )
        row = {
            "case_name": case_name,
            "bug_class": str(case_entry.get("bug_class", "")),
            **result,
        }
        rows.append(row)
        print(
            f"{case_name}: proof_status={row['proof_status']} "
            f"antecedent_reachability={row['antecedent_reachability_label']} "
            f"effective={row['effective_proof_status']}"
        )

    fields = [
        "case_name",
        "bug_class",
        "jasper_available",
        "jasper_ran",
        "jasper_report_path",
        "jasper_exit_code",
        "proof_status",
        "antecedent_reachability",
        "antecedent_reachability_label",
        "effective_proof_status",
        "formal_failure_reason",
    ]
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})

    passed = sum(1 for row in rows if row["antecedent_reachability"] is True)
    print(f"[DONE] Wrote Jasper reachability report: {out_csv}")
    print(f"SUMMARY: {passed}/{len(rows)} cases are antecedent-reachable by Jasper cover.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
