#!/usr/bin/env python3
import argparse
import csv
import json
import shutil
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from evaluate_generated_sva import (
    checker_module_text,
    first_error_line,
    inject_checker_into_tb,
    parse_dut_ports,
    parse_module_name,
    rewrite_past_refs,
    run_case_sim,
)
from sva_eval_grammar import extract_single_assertion as shared_extract_single_assertion
from sva_static_filter import analyze_sva, collect_vector_signals


def extract_single_assertion(sva_text: str) -> Tuple[str, Optional[str], str, str, str]:
    return shared_extract_single_assertion(sva_text)


def evaluate_non_triviality(
    assertion_text: str,
    case_entry: Dict[str, object],
    case_dir: Path,
) -> Tuple[bool, str]:
    allowed_signals = [str(sig) for sig in case_entry.get("key_signals", [])]
    vector_signals = collect_vector_signals(case_dir)
    result = analyze_sva(assertion_text, allowed_signals, vector_signals)
    reasons = [str(item) for item in result.get("reasons", [])]
    warnings = [str(item) for item in result.get("warnings", [])]

    if reasons:
        return False, "static_filter_reject: " + "; ".join(reasons)

    disallowed_warnings = [
        warning for warning in warnings if warning not in {"tautology_in_antecedent"}
    ]
    if disallowed_warnings:
        return False, "triviality_warning: " + "; ".join(disallowed_warnings)

    return True, ""


def evaluate_golden_case(
    root: Path,
    case_entry: Dict[str, object],
    iverilog_bin: str,
    vvp_bin: str,
) -> Dict[str, object]:
    case_name = str(case_entry["name"])
    case_dir = root / case_name
    correct_v = case_dir / "correct.v"
    buggy_v = case_dir / "buggy.v"
    tb_v = case_dir / "tb.v"
    tb_holdout_v = case_dir / "tb_holdout.v"
    golden = case_entry.get("golden_sva", {})
    assertion_text = str(golden.get("sva", "")).strip()

    correct_text = correct_v.read_text(encoding="utf-8")
    tb_text = tb_v.read_text(encoding="utf-8")
    tb_module_name = parse_module_name(tb_text)
    tb_holdout_text = tb_holdout_v.read_text(encoding="utf-8") if tb_holdout_v.exists() else ""
    tb_holdout_module_name = parse_module_name(tb_holdout_text) if tb_holdout_text else ""
    ports = parse_dut_ports(correct_text)
    non_trivial, non_trivial_reason = evaluate_non_triviality(assertion_text, case_entry, case_dir)

    try:
        assertion_line, disable_expr, ante, op, cons = extract_single_assertion(assertion_text)
    except Exception as exc:
        return {
            "case_name": case_name,
            "bug_type": str(case_entry.get("bug_type", "")),
            "compile_ok": False,
            "pass_on_correct": False,
            "fail_on_buggy": False,
            "non_vacuous": False,
            "antecedent_triggered": False,
            "correct_antecedent_hits": 0,
            "buggy_antecedent_hits": 0,
            "correct_fail_count": -1,
            "buggy_fail_count": -1,
            "non_trivial": non_trivial,
            "non_trivial_reason": non_trivial_reason,
            "golden_ok": False,
            "status": "rejected",
            "failure_reason": f"extract_error: {exc}",
            "compile_error": "",
            "assertion_line": assertion_text,
        }

    # Icarus Verilog does not reliably accept concurrent SVA syntax, so we treat
    # successful extraction as the syntax gate for our supported golden subset and
    # rely on the generated checker for simulation-based semantic validation.
    with tempfile.TemporaryDirectory(prefix="golden_sva_check_") as td:
        temp_dir = Path(td)
        checker = temp_dir / "sva_checker.sv"
        eval_tb = temp_dir / "tb_eval.sv"
        checker.write_text(
            checker_module_text(ports, assertion_line, disable_expr, ante, op, cons),
            encoding="utf-8",
            newline="\n",
        )
        eval_tb.write_text(
            inject_checker_into_tb(tb_text, tb_module_name, ports),
            encoding="utf-8",
            newline="\n",
        )

        correct_res = run_case_sim(
            iverilog_bin, vvp_bin, temp_dir, correct_v, eval_tb, tb_module_name, checker
        )
        buggy_res = run_case_sim(
            iverilog_bin, vvp_bin, temp_dir, buggy_v, eval_tb, tb_module_name, checker
        )
        holdout_correct_res = None
        holdout_buggy_res = None
        if tb_holdout_text:
            eval_tb_holdout = temp_dir / "tb_eval_holdout.sv"
            eval_tb_holdout.write_text(
                inject_checker_into_tb(tb_holdout_text, tb_holdout_module_name, ports),
                encoding="utf-8",
                newline="\n",
            )
            holdout_correct_res = run_case_sim(
                iverilog_bin, vvp_bin, temp_dir, correct_v, eval_tb_holdout, tb_holdout_module_name, checker
            )
            holdout_buggy_res = run_case_sim(
                iverilog_bin, vvp_bin, temp_dir, buggy_v, eval_tb_holdout, tb_holdout_module_name, checker
            )

    compile_ok = bool(correct_res["compile_ok"] and buggy_res["compile_ok"])
    if holdout_correct_res is not None and holdout_buggy_res is not None:
        compile_ok = bool(
            compile_ok and holdout_correct_res["compile_ok"] and holdout_buggy_res["compile_ok"]
        )

    pass_on_correct = compile_ok and int(correct_res["fail_count"]) == 0
    if holdout_correct_res is not None:
        pass_on_correct = bool(pass_on_correct and int(holdout_correct_res["fail_count"]) == 0)

    fail_on_buggy = compile_ok and int(buggy_res["fail_count"]) > 0
    if holdout_buggy_res is not None:
        fail_on_buggy = bool(fail_on_buggy or int(holdout_buggy_res["fail_count"]) > 0)

    correct_total_hits = int(correct_res["antecedent_hits"])
    if holdout_correct_res is not None:
        correct_total_hits += int(holdout_correct_res["antecedent_hits"])
    buggy_total_hits = int(buggy_res["antecedent_hits"])
    if holdout_buggy_res is not None:
        buggy_total_hits += int(holdout_buggy_res["antecedent_hits"])

    antecedent_triggered = correct_total_hits > 0
    non_vacuous = compile_ok and antecedent_triggered
    golden_ok = compile_ok and pass_on_correct and fail_on_buggy and non_vacuous and non_trivial

    if not compile_ok:
        failure_reason = first_error_line(str(correct_res["log"])) or first_error_line(
            str(buggy_res["log"])
        )
        if not failure_reason and holdout_correct_res is not None and holdout_buggy_res is not None:
            failure_reason = first_error_line(str(holdout_correct_res["log"])) or first_error_line(
                str(holdout_buggy_res["log"])
            )
    elif not pass_on_correct:
        failure_reason = "fails on correct RTL"
    elif not fail_on_buggy:
        failure_reason = "does not fail on buggy RTL"
    elif not non_vacuous:
        failure_reason = "antecedent never triggered on correct trace"
    elif not non_trivial:
        failure_reason = non_trivial_reason or "assertion is trivial"
    else:
        failure_reason = ""

    return {
        "case_name": case_name,
        "bug_type": str(case_entry.get("bug_type", "")),
        "compile_ok": compile_ok,
        "pass_on_correct": pass_on_correct,
        "fail_on_buggy": fail_on_buggy,
        "non_vacuous": non_vacuous,
        "antecedent_triggered": antecedent_triggered,
        "correct_antecedent_hits": correct_total_hits,
        "buggy_antecedent_hits": buggy_total_hits,
        "correct_fail_count": int(correct_res["fail_count"]),
        "buggy_fail_count": int(buggy_res["fail_count"]),
        "non_trivial": non_trivial,
        "non_trivial_reason": non_trivial_reason,
        "golden_ok": golden_ok,
        "status": "pass" if golden_ok else "rejected",
        "failure_reason": failure_reason,
        "compile_error": "" if compile_ok else failure_reason,
        "assertion_line": assertion_line,
    }


def load_cases(root: Path) -> List[Dict[str, object]]:
    return json.loads((root / "case_manifest.json").read_text(encoding="utf-8"))["cases"]


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Self-check manual golden SVA entries. Each golden must compile, pass on correct RTL, "
            "fail on buggy RTL, trigger on a correct trace at least once, and be non-trivial."
        )
    )
    parser.add_argument("--root", default=".", help="Path to rtl_cases root.")
    parser.add_argument("--case", help="Optional single case name to check.")
    parser.add_argument(
        "--output-csv",
        default="golden_sva_check_report.csv",
        help="CSV report path.",
    )
    parser.add_argument("--iverilog", default="iverilog", help="iverilog binary name/path.")
    parser.add_argument("--vvp", default="vvp", help="vvp binary name/path.")
    args = parser.parse_args()

    root = Path(args.root).resolve()

    if shutil.which(args.iverilog) is None:
        raise RuntimeError(f"Cannot find iverilog binary: {args.iverilog}")
    if shutil.which(args.vvp) is None:
        raise RuntimeError(f"Cannot find vvp binary: {args.vvp}")

    cases = load_cases(root)
    if args.case:
        cases = [case for case in cases if str(case.get("name", "")) == args.case]
        if not cases:
            raise ValueError(f"Unknown case: {args.case}")

    rows = [evaluate_golden_case(root, case, args.iverilog, args.vvp) for case in cases]
    passing_rows = [row for row in rows if row.get("golden_ok")]

    out_csv = Path(args.output_csv).resolve()
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "case_name",
        "bug_type",
        "compile_ok",
        "pass_on_correct",
        "fail_on_buggy",
        "non_vacuous",
        "antecedent_triggered",
        "correct_antecedent_hits",
        "buggy_antecedent_hits",
        "correct_fail_count",
        "buggy_fail_count",
        "non_trivial",
        "non_trivial_reason",
        "golden_ok",
        "status",
        "failure_reason",
        "compile_error",
        "assertion_line",
    ]
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in passing_rows:
            writer.writerow({field: row.get(field, "") for field in fields})
    passed = len(passing_rows)
    total = len(rows)
    print(f"[DONE] Wrote report: {out_csv}")
    for row in rows:
        verdict = "PASS" if row["golden_ok"] else "FAIL"
        print(
            f"{row['case_name']}: {verdict} | compile={row['compile_ok']} "
            f"correct_pass={row['pass_on_correct']} buggy_fail={row['fail_on_buggy']} "
            f"non_vacuous={row['non_vacuous']} non_trivial={row['non_trivial']} status={row['status']}"
        )
        if not row["golden_ok"]:
            print(
                "  reason: "
                f"{row['failure_reason']} | "
                f"correct_hits={row['correct_antecedent_hits']} "
                f"buggy_hits={row['buggy_antecedent_hits']} "
                f"correct_fail={row['correct_fail_count']} "
                f"buggy_fail={row['buggy_fail_count']} "
                f"non_trivial_reason={row['non_trivial_reason']}"
            )
    print(f"[INFO] Passing rows written to result table: {passed}")
    print(f"[INFO] Rejected rows excluded from result table: {total - passed}")
    print(f"SUMMARY: {passed}/{total} golden assertions meet the bar.")
    if passed != total:
        print("[ERROR] Golden self-check failed. At least one golden assertion does not meet the bar.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
