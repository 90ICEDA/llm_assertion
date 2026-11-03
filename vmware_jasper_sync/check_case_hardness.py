#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import shutil
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

from audit_trace_divergence_gate import check_pair
from check_golden_sva import evaluate_golden_case
from evaluate_generated_sva import evaluate_one
from jasper_antecedent_reachability import read_jasper_results_csv


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
        "tb_decoy.v",
        "waveform_good.csv",
        "waveform_bad.csv",
        "waveform_good_holdout.csv",
        "waveform_bad_holdout.csv",
        "waveform_good_decoy.csv",
        "waveform_bad_decoy.csv",
    ]
    return {name: (case_dir / name).exists() for name in needed}


def evaluate_case(
    root: Path,
    case_entry: Dict[str, object],
    iverilog_bin: str,
    vvp_bin: str,
    jasper_binary: str = "",
    jasper_mode: str = "prefer",
    jasper_results_lookup: Optional[Dict[str, Dict[str, str]]] = None,
    jasper_report_dir: Optional[Path] = None,
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
            "decoy_files_present": False,
            "overfit_lure_present": False,
            "decoy_semantic_ok": False,
            "decoy_correct_pass": False,
            "decoy_buggy_fail": False,
            "decoy_antecedent_hit": False,
            "divergence_gate_ok": False,
            "missing_files": ", ".join(missing),
            "failure_reason": "missing_artifacts",
            "golden_reachability_source": "",
            "golden_antecedent_reachability": "",
            "golden_effective_proof_status": "",
            "golden_formal_failure_reason": "",
        }

    golden_row = evaluate_golden_case(
        root,
        case_entry,
        iverilog_bin,
        vvp_bin,
        jasper_binary=jasper_binary,
        jasper_mode=jasper_mode,
        jasper_results_lookup=jasper_results_lookup,
        jasper_report_dir=jasper_report_dir,
    )
    golden_ok = bool(golden_row.get("golden_ok"))
    overfit_lure_present = bool(str(case_entry.get("overfit_lure", "") or "").strip())
    key_signals = [str(sig) for sig in case_entry.get("key_signals", [])]
    primary_div = check_pair(case_dir, key_signals, "waveform_good.csv", "waveform_bad.csv")
    heldout_div = check_pair(case_dir, key_signals, "waveform_good_holdout.csv", "waveform_bad_holdout.csv")
    decoy_div = check_pair(case_dir, key_signals, "waveform_good_decoy.csv", "waveform_bad_decoy.csv")
    decoy_semantic_ok = bool(decoy_div["diverges"])
    divergence_gate_ok = bool(primary_div["diverges"] and heldout_div["diverges"] and decoy_div["diverges"])

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
    decoy_files_present = bool(required["tb_decoy.v"] and required["waveform_good_decoy.csv"] and required["waveform_bad_decoy.csv"])
    hardness_ok = bool(
        golden_ok
        and loose_control_misses_bug
        and overfit_lure_present
        and decoy_files_present
        and decoy_semantic_ok
        and divergence_gate_ok
    )
    failure_reason = ""
    if not golden_ok:
        failure_reason = "golden_failed_self_check"
    elif not loose_control_misses_bug:
        failure_reason = "no_loose_control_missed_bug"
    elif not overfit_lure_present:
        failure_reason = "missing_overfit_lure"
    elif not decoy_files_present:
        failure_reason = "missing_decoy_artifacts"
    elif not decoy_semantic_ok:
        failure_reason = "decoy_semantic_gate_failed"
    elif not divergence_gate_ok:
        failure_reason = "trace_divergence_gate_failed"

    return {
        "case_name": case_name,
        "bug_class": str(case_entry.get("bug_class", "")),
        "hardness_ok": hardness_ok,
        "golden_ok": golden_ok,
        "loose_control_misses_bug": loose_control_misses_bug,
        "heldout_files_present": True,
        "decoy_files_present": decoy_files_present,
        "overfit_lure_present": overfit_lure_present,
        "decoy_semantic_ok": decoy_semantic_ok,
        "decoy_correct_pass": "",
        "decoy_buggy_fail": "",
        "decoy_antecedent_hit": "",
        "divergence_gate_ok": divergence_gate_ok,
        "missing_files": "",
        "failure_reason": failure_reason,
        "golden_buggy_hits": golden_row.get("buggy_antecedent_hits", 0),
        "golden_failure_type": golden_row.get("failure_reason", ""),
        "golden_reachability_source": golden_row.get("reachability_gate_source", ""),
        "golden_antecedent_reachability": golden_row.get("antecedent_reachability_label", ""),
        "golden_effective_proof_status": golden_row.get("effective_proof_status", ""),
        "golden_formal_failure_reason": golden_row.get("formal_failure_reason", ""),
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
    parser.add_argument(
        "--jasper-binary",
        default="",
        help="Optional JasperGold binary name/path for antecedent cover reachability checks.",
    )
    parser.add_argument(
        "--jasper-results-csv",
        default="",
        help="Optional CSV of precomputed Jasper antecedent reachability results.",
    )
    parser.add_argument(
        "--jasper-report-dir",
        default="",
        help="Optional directory to save raw Jasper stdout reports when running Jasper locally.",
    )
    parser.add_argument(
        "--jasper-mode",
        choices=["off", "prefer", "require"],
        default="prefer",
        help=(
            "Reachability gate mode: off=simulation-only fallback, prefer=use Jasper when available "
            "else simulation fallback, require=reject cases without Jasper reachability."
        ),
    )
    parser.add_argument(
        "--case",
        action="append",
        default=[],
        help="Optional case name filter. Repeat to evaluate multiple cases.",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    if shutil.which(args.iverilog) is None:
        raise RuntimeError(f"Cannot find iverilog binary: {args.iverilog}")
    if shutil.which(args.vvp) is None:
        raise RuntimeError(f"Cannot find vvp binary: {args.vvp}")

    manifest = load_manifest(root)
    requested = {name.strip() for name in args.case if name.strip()}
    if requested:
        manifest = [case_entry for case_entry in manifest if str(case_entry.get("name", "")) in requested]
    jasper_results_path = Path(args.jasper_results_csv).resolve() if args.jasper_results_csv else None
    jasper_results_lookup = read_jasper_results_csv(jasper_results_path) if jasper_results_path else {}
    jasper_report_dir = Path(args.jasper_report_dir).resolve() if args.jasper_report_dir else None

    rows = [
        evaluate_case(
            root,
            case_entry,
            args.iverilog,
            args.vvp,
            jasper_binary=args.jasper_binary,
            jasper_mode=args.jasper_mode,
            jasper_results_lookup=jasper_results_lookup,
            jasper_report_dir=jasper_report_dir,
        )
        for case_entry in manifest
    ]
    fields = [
        "case_name",
        "bug_class",
        "hardness_ok",
        "golden_ok",
        "loose_control_misses_bug",
        "heldout_files_present",
        "decoy_files_present",
        "overfit_lure_present",
        "decoy_semantic_ok",
        "decoy_correct_pass",
        "decoy_buggy_fail",
        "decoy_antecedent_hit",
        "divergence_gate_ok",
        "missing_files",
        "failure_reason",
        "golden_buggy_hits",
        "golden_failure_type",
        "golden_reachability_source",
        "golden_antecedent_reachability",
        "golden_effective_proof_status",
        "golden_formal_failure_reason",
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
