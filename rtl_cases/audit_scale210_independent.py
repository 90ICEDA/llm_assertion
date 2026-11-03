#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", type=Path, default=Path("rtl_cases_real_scale210_independent"))
    args = parser.parse_args()
    root = args.root.resolve()
    manifest = json.loads((root / "independent_new_bug_manifest.json").read_text(encoding="utf-8"))["cases"]
    rows = []
    signatures = set()
    for case in manifest:
        case_dir = root / case["name"]
        correct = case_dir / "correct.v"
        buggy = case_dir / "buggy.v"
        diff = case_dir / "rtl_mutation.diff"
        signature = (
            case["source_files"][0],
            case["mutation_edits"][0]["line"],
            case["mutation_edits"][0]["replace"],
        )
        signatures.add(signature)
        row = {
            "case_name": case["name"],
            "parent_bug_id": case["parent_bug_id"],
            "source_project": case["source_project"],
            "source_module": case["source_module"],
            "bug_class": case["bug_class"],
            "source_file": case["source_files"][0],
            "mutation_line": case["mutation_edits"][0]["line"],
            "correct_buggy_differ": correct.read_bytes() != buggy.read_bytes(),
            "correct_hash_matches": digest(correct) == case["correct_sha256"],
            "buggy_hash_matches": digest(buggy) == case["buggy_sha256"],
            "rtl_diff_present": diff.exists() and diff.stat().st_size > 0,
            "mutation_marker_present": "ASSERTIONFORGE_MUTATION" in buggy.read_text(encoding="utf-8"),
            "independent_parent": case["parent_bug_id"] == case["name"],
            "validation_status": case["status"],
        }
        row["structural_gate_ok"] = all(
            row[key]
            for key in [
                "correct_buggy_differ", "correct_hash_matches", "buggy_hash_matches",
                "rtl_diff_present", "mutation_marker_present", "independent_parent",
            ]
        )
        rows.append(row)

    out = root / "independent_new_bug_audit.csv"
    with out.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    summary = {
        "case_count": len(rows),
        "unique_parent_bug_count": len({row["parent_bug_id"] for row in rows}),
        "unique_mutation_signature_count": len(signatures),
        "temporal_bug_count": sum(row["bug_class"] == "temporal_cross_cycle" for row in rows),
        "combination_protocol_bug_count": sum(row["bug_class"] == "combination_protocol" for row in rows),
        "source_project_count": len({row["source_project"] for row in rows}),
        "unique_module_count": len({(row["source_project"], row["source_module"]) for row in rows}),
        "structural_gate_pass_count": sum(row["structural_gate_ok"] for row in rows),
        "all_structural_gates_ok": all(row["structural_gate_ok"] for row in rows),
        "simulation_formal_status": "pending_module_specific_testbench_and_trace_generation",
    }
    (root / "independent_new_bug_audit_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    if not summary["all_structural_gates_ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
