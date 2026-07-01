#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import shutil
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

from evaluate_generated_sva import evaluate_one


def load_manifest(root: Path) -> List[Dict[str, object]]:
    return json.loads((root / "case_manifest.json").read_text(encoding="utf-8"))["cases"]


def boolify(value: object) -> bool:
    return str(value).strip().lower() == "true"


def evaluate_assertion(
    root: Path,
    case_name: str,
    assertion_text: str,
    iverilog_bin: str,
    vvp_bin: str,
    tag: str,
) -> Dict[str, object]:
    with tempfile.TemporaryDirectory(prefix=f"hardness_{case_name}_{tag}_") as td:
        sva_path = Path(td) / f"{tag}.sv"
        sva_path.write_text(assertion_text.strip() + "\n", encoding="utf-8", newline="\n")
        row = evaluate_one(
            root=root,
            case_name=case_name,
            sva_file=sva_path,
            iverilog_bin=iverilog_bin,
            vvp_bin=vvp_bin,
            bug_type="hardness_check",
            method="hardness_check",
            candidate_index=None,
            semantic_reasonable=True,
            semantic_review_label="auto:hardness_check",
            reviewed_assertion="",
        )
    return row


def has_required_files(case_dir: Path) -> Dict[str, bool]:
    needed = [
        "correct.v",
        "buggy.v",
        "tb.v",
        "tb_holdout.v",
        "waveform_good.csv",
        "waveform_bad.csv",
        "waveform_good_holdout.csv",
        "waveform_bad_holdout.csv",
    ]
    return {name: (case_dir / name).exists() for name in needed}


def evaluate_case(
    root: Path,
    case_entry: Dict[str, object],
    iverilog_bin: str,
    vvp_bin: str,
) -> Dict[str, object]:
    case_name = str(case_entry["name"])
    case_dir = root / case_name
    required = has_required_files(case_dir)
    missing = [name for name, ok in required.items() if not ok]
    if missing:
        return {
            "case_name": case_name,
            "bug_class": str(case_entry.get("bug_class", "")),
            "hardness_ok": False,
            "golden_ok": False,
            "loose_control_misses_bug": False,
            "heldout_files_present": False,
            "missing_files": ", ".join(missing),
            "failure_reason": "missing_artifacts",
        }

    golden_text = str(case_entry.get("golden_sva", {}).get("sva", "")).strip()
    golden_row = evaluate_assertion(root, case_name, golden_text, iverilog_bin, vvp_bin, "golden")
    golden_ok = boolify(golden_row.get("compile_ok")) and boolify(golden_row.get("pass_on_correct")) and boolify(
        golden_row.get("fail_on_buggy")
    ) and boolify(golden_row.get("non_vacuous")) and int(golden_row.get("buggy_antecedent_hits", 0)) > 0

    loose_controls = case_entry.get("loose_negative_controls", []) or []
    misses: List[Dict[str, object]] = []
    for idx, control in enumerate(loose_controls, start=1):
        row = evaluate_assertion(
            root,
            case_name,
            str(control["sva"]),
            iverilog_bin,
            vvp_bin,
            f"loose_{idx:02d}",
        )
        misses.append(
            {
                "name": str(control["name"]),
                "misses_bug": boolify(row.get("compile_ok")) and boolify(row.get("pass_on_correct")) and not boolify(row.get("fail_on_buggy")),
                "failure_type": row.get("failure_type", ""),
            }
        )

    loose_control_misses_bug = any(item["misses_bug"] for item in misses)
    hardness_ok = golden_ok and loose_control_misses_bug
    failure_reason = ""
    if not golden_ok:
        failure_reason = "golden_failed_self_check"
    elif not loose_control_misses_bug:
        failure_reason = "no_loose_control_missed_bug"

    return {
        "case_name": case_name,
        "bug_class": str(case_entry.get("bug_class", "")),
        "hardness_ok": hardness_ok,
        "golden_ok": golden_ok,
        "loose_control_misses_bug": loose_control_misses_bug,
        "heldout_files_present": True,
        "missing_files": "",
        "failure_reason": failure_reason,
        "golden_buggy_hits": golden_row.get("buggy_antecedent_hits", 0),
        "golden_failure_type": golden_row.get("failure_type", ""),
        "loose_controls_summary": "; ".join(
            f"{item['name']}={'miss' if item['misses_bug'] else 'no'}"
            for item in misses
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Enforce the new hard-case admission gates for a real-RTL benchmark root."
    )
    parser.add_argument("--root", required=True, help="Dataset root to audit.")
    parser.add_argument("--output-csv", default="hardness_check_report.csv", help="Output CSV path.")
    parser.add_argument("--iverilog", default="iverilog", help="iverilog binary name/path.")
    parser.add_argument("--vvp", default="vvp", help="vvp binary name/path.")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    if shutil.which(args.iverilog) is None:
        raise RuntimeError(f"Cannot find iverilog binary: {args.iverilog}")
    if shutil.which(args.vvp) is None:
        raise RuntimeError(f"Cannot find vvp binary: {args.vvp}")

    rows = [evaluate_case(root, case_entry, args.iverilog, args.vvp) for case_entry in load_manifest(root)]
    fields = [
        "case_name",
        "bug_class",
        "hardness_ok",
        "golden_ok",
        "loose_control_misses_bug",
        "heldout_files_present",
        "missing_files",
        "failure_reason",
        "golden_buggy_hits",
        "golden_failure_type",
        "loose_controls_summary",
    ]
    out_csv = Path(args.output_csv).resolve()
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})

    passed = sum(1 for row in rows if row["hardness_ok"])
    total = len(rows)
    print(f"[DONE] Wrote hardness report: {out_csv}")
    print(f"SUMMARY: {passed}/{total} cases satisfy the hard-case admission gates.")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
