from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RTL_CASES_DIR = ROOT / "rtl_cases"
if str(RTL_CASES_DIR) not in sys.path:
    sys.path.insert(0, str(RTL_CASES_DIR))

from jasper_antecedent_reachability import run_jasper_on_case  # type: ignore  # noqa: E402


def load_cases(root: Path) -> list[dict]:
    return json.loads((root / "case_manifest.json").read_text(encoding="utf-8"))["cases"]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run Jasper antecedent reachability on selected dataset cases and emit a cacheable CSV."
    )
    parser.add_argument("--root", required=True, help="Dataset root containing case_manifest.json.")
    parser.add_argument("--jasper-binary", required=True, help="JasperGold binary name/path.")
    parser.add_argument("--output-csv", required=True, help="Output CSV path.")
    parser.add_argument(
        "--report-dir",
        default="",
        help="Optional directory to store per-case raw Jasper stdout reports.",
    )
    parser.add_argument(
        "--case",
        action="append",
        default=[],
        help="Optional case name filter. Repeat to evaluate multiple cases.",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    report_dir = Path(args.report_dir).resolve() if args.report_dir else None
    manifest = load_cases(root)
    requested = {name.strip() for name in args.case if name.strip()}
    if requested:
        unknown = sorted(requested - {str(case["name"]) for case in manifest})
        if unknown:
            raise RuntimeError(f"Unknown case filters: {', '.join(unknown)}")
        selected_cases = [case for case in manifest if str(case["name"]) in requested]
    else:
        selected_cases = manifest

    rows: list[dict[str, object]] = []
    for case in selected_cases:
        case_name = str(case["name"])
        assertion_text = str(case.get("golden_sva", {}).get("sva", "")).strip()
        correct_v = root / case_name / "correct.v"
        per_case_report = report_dir / f"{case_name}.txt" if report_dir is not None else None
        print(f"[INFO] Jasper | {case_name}")
        result = run_jasper_on_case(
            case_name=case_name,
            correct_v=correct_v,
            assertion_text=assertion_text,
            jasper_binary=args.jasper_binary,
            report_path=per_case_report,
        )
        rows.append(
            {
                "case_name": case_name,
                "bug_class": str(case.get("bug_class", "")),
                "bug_type": str(case.get("bug_type", "")),
                "jasper_available": result["jasper_available"],
                "jasper_ran": result["jasper_ran"],
                "jasper_report_path": result["jasper_report_path"],
                "jasper_exit_code": result["jasper_exit_code"],
                "proof_status": result["proof_status"],
                "antecedent_reachability": result["antecedent_reachability"],
                "antecedent_reachability_label": result["antecedent_reachability_label"],
                "effective_proof_status": result["effective_proof_status"],
                "formal_failure_reason": result["formal_failure_reason"],
            }
        )

    out_csv = Path(args.output_csv).resolve()
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else [
        "case_name",
        "bug_class",
        "bug_type",
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
    with out_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    reachable = sum(1 for row in rows if row["antecedent_reachability_label"] == "reachable")
    print(f"WROTE {out_csv}")
    print(f"REACHABLE {reachable}/{len(rows)}")
    return 0 if reachable == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
