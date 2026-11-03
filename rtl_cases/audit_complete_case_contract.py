#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


REQUIRED_FIELDS = [
    "parent_bug_id", "source_project", "source_module", "source_commit",
    "bug_class", "bug_family", "spec", "golden_sva", "first_divergence",
    "relevant_signals", "temporal_type",
]
REQUIRED_FILES = [
    "correct.v", "buggy.v", "rtl_mutation.diff",
    "waveform_good.csv", "waveform_bad.csv",
    "waveform_good_holdout.csv", "waveform_bad_holdout.csv",
    "waveform_good_decoy.csv", "waveform_bad_decoy.csv",
]


def nonempty(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, (list, dict)):
        return bool(value)
    return bool(str(value).strip())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", type=Path, default=Path("rtl_cases_real_scale210_independent"))
    parser.add_argument("--allow-incomplete", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    cases = json.loads((root / "independent_new_bug_manifest.json").read_text(encoding="utf-8"))["cases"]
    rows = []
    for case in cases:
        case_dir = root / case["name"]
        missing_fields = [field for field in REQUIRED_FIELDS if not nonempty(case.get(field))]
        missing_files = [name for name in REQUIRED_FILES if not (case_dir / name).is_file() or (case_dir / name).stat().st_size == 0]
        trace_files = [case_dir / name for name in REQUIRED_FILES if name.startswith("waveform_")]
        trace_hashes = {path.read_bytes() for path in trace_files if path.is_file()}
        traces_distinct = len(trace_hashes) == len(trace_files) if len(trace_files) == 6 else False
        rows.append({
            "case_name": case["name"],
            "missing_fields": ";".join(missing_fields),
            "missing_files": ";".join(missing_files),
            "six_trace_files_distinct": traces_distinct,
            "complete": not missing_fields and not missing_files and traces_distinct,
        })
    out = root / "complete_case_contract_audit.csv"
    with out.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "case_count": len(rows),
        "complete_case_count": sum(row["complete"] for row in rows),
        "incomplete_case_count": sum(not row["complete"] for row in rows),
        "all_complete": all(row["complete"] for row in rows),
        "required_fields": REQUIRED_FIELDS,
        "required_files": REQUIRED_FILES,
        "trace_distinctness_required": True,
    }
    (root / "complete_case_contract_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    if not summary["all_complete"] and not args.allow_incomplete:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
