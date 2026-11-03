from __future__ import annotations

import argparse
import csv
import json
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RTL_CASES_DIR = ROOT / "rtl_cases"
if str(RTL_CASES_DIR) not in sys.path:
    sys.path.insert(0, str(RTL_CASES_DIR))

from check_golden_sva import (  # type: ignore  # noqa: E402
    evaluate_non_triviality,
    extract_single_assertion,
    run_trace_pair,
)
from jasper_antecedent_reachability import (  # type: ignore  # noqa: E402
    parse_cached_reachability_row,
    read_jasper_results_csv,
    run_jasper_on_case,
)
from evaluate_generated_sva import (  # type: ignore  # noqa: E402
    checker_module_text,
    first_error_line,
    parse_dut_ports,
    parse_module_name,
)


def load_cases(root: Path):
    return json.loads((root / "case_manifest.json").read_text(encoding="utf-8"))["cases"]


def evaluate_case(
    root: Path,
    case_entry: dict,
    iverilog_bin: str,
    vvp_bin: str,
    jasper_binary: str = "",
    jasper_mode: str = "prefer",
    jasper_results_lookup: dict | None = None,
    jasper_report_dir: Path | None = None,
) -> dict:
    case_name = str(case_entry["name"])
    case_dir = root / case_name
    correct_v = case_dir / "correct.v"
    buggy_v = case_dir / "buggy.v"
    tb_v = case_dir / "tb.v"
    tb_holdout_v = case_dir / "tb_holdout.v"
    tb_decoy_v = case_dir / "tb_decoy.v"
    golden = case_entry.get("golden_sva", {})
    assertion_text = str(golden.get("sva", "")).strip()
    cached_jasper_row = (jasper_results_lookup or {}).get(case_name)

    correct_text = correct_v.read_text(encoding="utf-8")
    tb_text = tb_v.read_text(encoding="utf-8")
    tb_module_name = parse_module_name(tb_text)
    tb_holdout_text = tb_holdout_v.read_text(encoding="utf-8") if tb_holdout_v.exists() else ""
    tb_holdout_module_name = parse_module_name(tb_holdout_text) if tb_holdout_text else ""
    tb_decoy_text = tb_decoy_v.read_text(encoding="utf-8") if tb_decoy_v.exists() else ""
    tb_decoy_module_name = parse_module_name(tb_decoy_text) if tb_decoy_text else ""
    ports = parse_dut_ports(correct_text)
    non_trivial, non_trivial_reason = evaluate_non_triviality(assertion_text, case_entry, case_dir)

    try:
        assertion_line, disable_expr, ante, op, cons = extract_single_assertion(assertion_text)
    except Exception as exc:
        return {
            "case_name": case_name,
            "bug_type": str(case_entry.get("bug_type", "")),
            "compile_ok": False,
            "correct_pass": False,
            "fail_on_buggy": False,
            "antecedent_hit_correct": False,
            "antecedent_hit_buggy": False,
            "non_vacuous_correct": False,
            "non_vacuous_buggy": False,
            "heldout_correct_pass": False,
            "heldout_buggy_fail": False,
            "heldout_antecedent_hit": False,
            "correct_antecedent_hits": 0,
            "buggy_antecedent_hits": 0,
            "heldout_correct_antecedent_hits": 0,
            "heldout_buggy_antecedent_hits": 0,
            "correct_fail_count": -1,
            "buggy_fail_count": -1,
            "heldout_correct_fail_count": -1,
            "heldout_buggy_fail_count": -1,
            "decoy_correct_pass": False,
            "decoy_buggy_fail": False,
            "decoy_antecedent_hit": False,
            "decoy_correct_antecedent_hits": 0,
            "decoy_buggy_antecedent_hits": 0,
            "decoy_correct_fail_count": -1,
            "decoy_buggy_fail_count": -1,
            "jasper_available": False,
            "jasper_ran": False,
            "jasper_report_path": "",
            "jasper_exit_code": "",
            "proof_status": "unknown",
            "antecedent_reachability": "",
            "antecedent_reachability_label": "unknown",
            "effective_proof_status": "unknown",
            "reachability_gate_source": "simulation",
            "reachability_gate_ok": False,
            "formal_failure_reason": "",
            "non_trivial": non_trivial,
            "non_trivial_reason": non_trivial_reason,
            "golden_ok_strict": False,
            "failure_reason": f"extract_error: {exc}",
            "compile_error": "",
            "assertion_line": assertion_text,
            "antecedent_text": "",
            "consequent_text": "",
            "implication_op": "",
        }

    with tempfile.TemporaryDirectory(prefix="golden_recheck_") as td:
        temp_dir = Path(td)
        checker = temp_dir / "sva_checker.sv"
        checker.write_text(
            checker_module_text(ports, assertion_line, disable_expr, ante, op, cons),
            encoding="utf-8",
            newline="\n",
        )
        correct_res, buggy_res = run_trace_pair(
            iverilog_bin,
            vvp_bin,
            temp_dir,
            correct_v,
            buggy_v,
            checker,
            ports,
            tb_text,
            tb_module_name,
            "primary",
        )
        heldout_correct_res, heldout_buggy_res = run_trace_pair(
            iverilog_bin,
            vvp_bin,
            temp_dir,
            correct_v,
            buggy_v,
            checker,
            ports,
            tb_holdout_text,
            tb_holdout_module_name,
            "holdout",
        )
        decoy_correct_res, decoy_buggy_res = run_trace_pair(
            iverilog_bin,
            vvp_bin,
            temp_dir,
            correct_v,
            buggy_v,
            checker,
            ports,
            tb_decoy_text,
            tb_decoy_module_name,
            "decoy",
        )

    compile_ok = bool(correct_res["compile_ok"] and buggy_res["compile_ok"])
    if tb_holdout_text:
        compile_ok = bool(compile_ok and heldout_correct_res["compile_ok"] and heldout_buggy_res["compile_ok"])
    if tb_decoy_text:
        compile_ok = bool(compile_ok and decoy_correct_res["compile_ok"] and decoy_buggy_res["compile_ok"])

    correct_pass = bool(correct_res["compile_ok"] and int(correct_res["fail_count"]) == 0)
    fail_on_buggy = bool(buggy_res["compile_ok"] and int(buggy_res["fail_count"]) > 0)
    antecedent_hit_correct = int(correct_res["antecedent_hits"]) > 0
    antecedent_hit_buggy = int(buggy_res["antecedent_hits"]) > 0
    non_vacuous_correct = bool(correct_res["compile_ok"] and antecedent_hit_correct)
    non_vacuous_buggy = bool(buggy_res["compile_ok"] and antecedent_hit_buggy)

    heldout_correct_pass = False
    heldout_buggy_fail = False
    heldout_antecedent_hit = False
    heldout_correct_hits = 0
    heldout_buggy_hits = 0
    heldout_correct_fail_count = -1
    heldout_buggy_fail_count = -1
    if tb_holdout_text:
        heldout_correct_hits = int(heldout_correct_res["antecedent_hits"])
        heldout_buggy_hits = int(heldout_buggy_res["antecedent_hits"])
        heldout_correct_fail_count = int(heldout_correct_res["fail_count"])
        heldout_buggy_fail_count = int(heldout_buggy_res["fail_count"])
        heldout_correct_pass = bool(heldout_correct_res["compile_ok"] and heldout_correct_fail_count == 0)
        heldout_buggy_fail = bool(heldout_buggy_res["compile_ok"] and heldout_buggy_fail_count > 0)
        heldout_antecedent_hit = bool(heldout_correct_res["compile_ok"] and heldout_correct_hits > 0)

    decoy_correct_pass = False
    decoy_buggy_fail = False
    decoy_antecedent_hit = False
    decoy_correct_hits = 0
    decoy_buggy_hits = 0
    decoy_correct_fail_count = -1
    decoy_buggy_fail_count = -1
    if tb_decoy_text:
        decoy_correct_hits = int(decoy_correct_res["antecedent_hits"])
        decoy_buggy_hits = int(decoy_buggy_res["antecedent_hits"])
        decoy_correct_fail_count = int(decoy_correct_res["fail_count"])
        decoy_buggy_fail_count = int(decoy_buggy_res["fail_count"])
        decoy_correct_pass = bool(decoy_correct_res["compile_ok"] and decoy_correct_fail_count == 0)
        decoy_buggy_fail = bool(decoy_buggy_res["compile_ok"] and decoy_buggy_fail_count > 0)
        decoy_antecedent_hit = bool(decoy_correct_res["compile_ok"] and decoy_correct_hits > 0)

    jasper_result = {
        "jasper_available": False,
        "jasper_ran": False,
        "jasper_report_path": "",
        "jasper_exit_code": "",
        "proof_status": "unknown",
        "antecedent_reachability": None,
        "antecedent_reachability_label": "unknown",
        "effective_proof_status": "unknown",
        "formal_failure_reason": "",
    }
    reachability_gate_source = "simulation"
    reachability_gate_ok = antecedent_hit_correct
    use_formal_reachability = jasper_mode != "off"

    if not compile_ok:
        failure_reason = (
            first_error_line(str(correct_res["log"]))
            or first_error_line(str(buggy_res["log"]))
            or first_error_line(str(heldout_correct_res.get("log", "")))
            or first_error_line(str(heldout_buggy_res.get("log", "")))
            or first_error_line(str(decoy_correct_res.get("log", "")))
            or first_error_line(str(decoy_buggy_res.get("log", "")))
            or "compile_fail"
        )
    else:
        if use_formal_reachability and cached_jasper_row:
            jasper_result = parse_cached_reachability_row(case_name, cached_jasper_row)
        elif use_formal_reachability and jasper_binary:
            report_path = None
            if jasper_report_dir is not None:
                report_path = jasper_report_dir / f"{case_name}.txt"
            jasper_result = run_jasper_on_case(
                case_name=case_name,
                correct_v=correct_v,
                assertion_text=assertion_text,
                jasper_binary=jasper_binary,
                report_path=report_path,
            )

        if use_formal_reachability and jasper_result["jasper_available"]:
            reachability_gate_source = "jasper"
            reachability_gate_ok = jasper_result["antecedent_reachability"] is True
        elif jasper_mode == "require":
            reachability_gate_source = "jasper_required_missing"
            reachability_gate_ok = False

        missing = []
        checks = [
            ("correct_pass", correct_pass),
            ("fail_on_buggy", fail_on_buggy),
            ("reachability_gate_ok", reachability_gate_ok),
            ("non_trivial", non_trivial),
        ]
        for name, ok in checks:
            if not ok:
                missing.append(name)
        failure_reason = "; ".join(missing)

    golden_ok_strict = bool(
        compile_ok
        and correct_pass
        and fail_on_buggy
        and reachability_gate_ok
        and non_trivial
    )

    return {
        "case_name": case_name,
        "bug_type": str(case_entry.get("bug_type", "")),
        "compile_ok": compile_ok,
        "correct_pass": correct_pass,
        "fail_on_buggy": fail_on_buggy,
        "antecedent_hit_correct": antecedent_hit_correct,
        "antecedent_hit_buggy": antecedent_hit_buggy,
        "non_vacuous_correct": non_vacuous_correct,
        "non_vacuous_buggy": non_vacuous_buggy,
        "heldout_correct_pass": heldout_correct_pass,
        "heldout_buggy_fail": heldout_buggy_fail,
        "heldout_antecedent_hit": heldout_antecedent_hit,
        "correct_antecedent_hits": int(correct_res["antecedent_hits"]),
        "buggy_antecedent_hits": int(buggy_res["antecedent_hits"]),
        "heldout_correct_antecedent_hits": heldout_correct_hits,
        "heldout_buggy_antecedent_hits": heldout_buggy_hits,
        "correct_fail_count": int(correct_res["fail_count"]),
        "buggy_fail_count": int(buggy_res["fail_count"]),
        "heldout_correct_fail_count": heldout_correct_fail_count,
        "heldout_buggy_fail_count": heldout_buggy_fail_count,
        "decoy_correct_pass": decoy_correct_pass,
        "decoy_buggy_fail": decoy_buggy_fail,
        "decoy_antecedent_hit": decoy_antecedent_hit,
        "decoy_correct_antecedent_hits": decoy_correct_hits,
        "decoy_buggy_antecedent_hits": decoy_buggy_hits,
        "decoy_correct_fail_count": decoy_correct_fail_count,
        "decoy_buggy_fail_count": decoy_buggy_fail_count,
        "jasper_available": jasper_result["jasper_available"],
        "jasper_ran": jasper_result["jasper_ran"],
        "jasper_report_path": jasper_result["jasper_report_path"],
        "jasper_exit_code": jasper_result["jasper_exit_code"],
        "proof_status": jasper_result["proof_status"],
        "antecedent_reachability": jasper_result["antecedent_reachability"],
        "antecedent_reachability_label": jasper_result["antecedent_reachability_label"],
        "effective_proof_status": jasper_result["effective_proof_status"],
        "reachability_gate_source": reachability_gate_source,
        "reachability_gate_ok": reachability_gate_ok,
        "formal_failure_reason": jasper_result["formal_failure_reason"],
        "non_trivial": non_trivial,
        "non_trivial_reason": non_trivial_reason,
        "golden_ok_strict": golden_ok_strict,
        "failure_reason": failure_reason,
        "compile_error": "" if compile_ok else failure_reason,
        "assertion_line": assertion_line,
        "antecedent_text": ante,
        "consequent_text": cons,
        "implication_op": op,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Recheck golden assertions with per-trace heldout metrics.")
    parser.add_argument("--root", required=True, help="Path to rtl_cases_real_active root")
    parser.add_argument("--output-csv", required=True, help="CSV path for raw recheck output")
    parser.add_argument("--iverilog", default="iverilog")
    parser.add_argument("--vvp", default="vvp")
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
    args = parser.parse_args()

    root = Path(args.root).resolve()
    jasper_results_path = Path(args.jasper_results_csv).resolve() if args.jasper_results_csv else None
    jasper_results_lookup = read_jasper_results_csv(jasper_results_path)
    jasper_report_dir = Path(args.jasper_report_dir).resolve() if args.jasper_report_dir else None
    rows = [
        evaluate_case(
            root,
            case,
            args.iverilog,
            args.vvp,
            jasper_binary=args.jasper_binary,
            jasper_mode=args.jasper_mode,
            jasper_results_lookup=jasper_results_lookup,
            jasper_report_dir=jasper_report_dir,
        )
        for case in load_cases(root)
    ]

    out_csv = Path(args.output_csv).resolve()
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else []
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    passed = sum(1 for row in rows if row["golden_ok_strict"])
    print(f"WROTE {out_csv}")
    print(f"STRICT_PASS {passed}/{len(rows)}")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
