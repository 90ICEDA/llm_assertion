#!/usr/bin/env python3
import argparse
import csv
import shutil
import tempfile
from pathlib import Path
from typing import Dict, List

from evaluate_generated_sva import evaluate_one


PROBE_SPECS: List[Dict[str, object]] = [
    {
        "name": "template_mismatch_compile",
        "case_name": "case04_fsm_transition",
        "assertion_text": "probe_tm: assert property (@(posedge clk) disable iff (!rst_n) (finish) |=> (state == 2'd2));",
        "method": "",
        "candidate_index": "",
        "semantic_reasonable": None,
        "expect": {
            "syntax_pass": False,
            "analysis_supported": False,
            "compile_ok": True,
            "failure_type": "template_mismatch",
        },
    },
    {
        "name": "unsupported_compile",
        "case_name": "case08_pulse_width",
        "assertion_text": "assert property (@(posedge clk) disable iff (!rst_n) (trigger) |=> (pulse ##1 pulse));",
        "method": "",
        "candidate_index": "",
        "semantic_reasonable": None,
        "expect": {
            "syntax_pass": True,
            "analysis_supported": False,
            "compile_ok": True,
            "failure_type": "unsupported",
        },
    },
    {
        "name": "compile_fail",
        "case_name": "case02_grant_delay",
        "assertion_text": "assert property (@(posedge clk) disable iff (!rst_n) (req != 2'b00) |-> (false));",
        "method": "",
        "candidate_index": "",
        "semantic_reasonable": None,
        "expect": {
            "syntax_pass": True,
            "analysis_supported": True,
            "compile_ok": False,
            "failure_type": "compile_fail",
        },
    },
    {
        "name": "antecedent_not_triggered",
        "case_name": "case09_addr_increment",
        "assertion_text": "assert property (@(posedge clk) disable iff (!rst_n) ($past(step) && !$past(step)) |-> (addr == 8'hff));",
        "method": "",
        "candidate_index": "",
        "semantic_reasonable": None,
        "expect": {
            "compile_ok": True,
            "antecedent_triggered": False,
            "non_vacuous": False,
            "failure_type": "antecedent_not_triggered",
        },
    },
    {
        "name": "vacuous_pass",
        "case_name": "case07_fifo_full_boundary",
        "assertion_text": "assert property (@(posedge clk) disable iff (!rst_n) (full && (count != 3'd4)) |-> (count == 3'd4));",
        "method": "",
        "candidate_index": "",
        "semantic_reasonable": None,
        "expect": {
            "compile_ok": True,
            "pass_on_correct": True,
            "fail_on_buggy": True,
            "antecedent_triggered": True,
            "non_vacuous": False,
            "failure_type": "vacuous",
        },
    },
    {
        "name": "false_positive",
        "case_name": "case04_fsm_transition",
        "assertion_text": "assert property (@(posedge clk) disable iff (!rst_n) (start) |-> (state == 2'd2));",
        "method": "",
        "candidate_index": "",
        "semantic_reasonable": None,
        "expect": {
            "compile_ok": True,
            "pass_on_correct": False,
            "failure_type": "false_positive_on_correct",
        },
    },
    {
        "name": "bug_not_detected",
        "case_name": "case04_fsm_transition",
        "assertion_text": "assert property (@(posedge clk) disable iff (!rst_n) (start) |=> (state == 2'd1));",
        "method": "",
        "candidate_index": "",
        "semantic_reasonable": None,
        "expect": {
            "compile_ok": True,
            "pass_on_correct": True,
            "fail_on_buggy": False,
            "non_vacuous": True,
            "failure_type": "bug_not_detected_on_buggy",
        },
    },
    {
        "name": "static_filter_reject",
        "case_name": "case07_fifo_full_boundary",
        "assertion_text": "assert property (@(posedge clk) disable iff (!rst_n) (wr_en) |-> (1'b1));",
        "method": "",
        "candidate_index": "",
        "semantic_reasonable": None,
        "expect": {
            "syntax_pass": True,
            "analysis_supported": True,
            "compile_ok": True,
            "failure_type": "static_filter_reject",
        },
    },
    {
        "name": "trace_overfit",
        "case_name": "case09_addr_increment",
        "assertion_text": "assert property (@(posedge clk) disable iff (!rst_n) ($past(step) && ($past(addr) == 8'h04)) |-> (addr == 8'h08));",
        "method": "spec_rtl_trace_summary",
        "candidate_index": 99,
        "semantic_reasonable": True,
        "expect": {
            "compile_ok": True,
            "pass_on_correct": True,
            "fail_on_buggy": True,
            "non_vacuous": True,
            "trace_overfit": True,
            "failure_type": "trace_overfit",
        },
    },
    {
        "name": "semantic_unreviewed",
        "case_name": "case04_fsm_transition",
        "assertion_text": "assert property (@(posedge clk) disable iff (!rst_n) (finish) |=> (state == 2'd2));",
        "method": "",
        "candidate_index": "",
        "semantic_reasonable": None,
        "expect": {
            "compile_ok": True,
            "pass_on_correct": True,
            "fail_on_buggy": True,
            "non_vacuous": True,
            "failure_type": "semantic_unreviewed",
        },
    },
    {
        "name": "semantic_unreasonable",
        "case_name": "case03_valid_ready_or_bug",
        "assertion_text": "assert property (@(posedge clk) disable iff (!rst_n) (valid_i && !ready_i) |-> (!valid_o));",
        "method": "",
        "candidate_index": "",
        "semantic_reasonable": False,
        "expect": {
            "compile_ok": True,
            "pass_on_correct": True,
            "fail_on_buggy": True,
            "non_vacuous": True,
            "semantic_reasonable": False,
            "failure_type": "semantic_unreasonable",
        },
    },
]


REPORT_FIELDS = [
    "probe_name",
    "case_name",
    "method",
    "syntax_pass",
    "analysis_supported",
    "compile_ok",
    "pass_on_correct",
    "fail_on_buggy",
    "non_vacuous",
    "antecedent_triggered",
    "trace_overfit",
    "semantic_reasonable",
    "failure_type",
    "unsupported_reason",
    "compile_error",
    "assertion_line",
]


def normalize_bool(value: object) -> object:
    if isinstance(value, bool):
        return value
    return value


def probe_filename(spec: Dict[str, object]) -> str:
    method = str(spec.get("method", "") or "").strip()
    candidate_index = spec.get("candidate_index", "")
    if method == "spec_rtl_trace_summary" and candidate_index != "":
        return f"sva_4_spec_rtl_trace_summary__cand_{int(candidate_index):02d}.sv"
    if method == "spec_rtl_raw_trace" and candidate_index != "":
        return f"sva_3_spec_rtl_raw_trace__cand_{int(candidate_index):02d}.sv"
    return f"{spec['name']}.sv"


def write_probe_file(temp_dir: Path, spec: Dict[str, object]) -> Path:
    sva_path = temp_dir / probe_filename(spec)
    sva_path.write_text(str(spec["assertion_text"]).strip() + "\n", encoding="utf-8", newline="\n")
    return sva_path


def row_matches_expectation(row: Dict[str, object], expected: Dict[str, object]) -> List[str]:
    mismatches: List[str] = []
    for key, expected_value in expected.items():
        actual_value = row.get(key)
        if normalize_bool(actual_value) != normalize_bool(expected_value):
            mismatches.append(f"{key}: expected {expected_value!r}, got {actual_value!r}")
    return mismatches


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run metric probe regression assertions for evaluator labels/columns."
    )
    parser.add_argument("--root", default=".", help="Path to rtl_cases root.")
    parser.add_argument("--output-csv", default="metric_probe_regression_report.csv", help="Report CSV path.")
    parser.add_argument("--iverilog", default="iverilog", help="iverilog binary name/path.")
    parser.add_argument("--vvp", default="vvp", help="vvp binary name/path.")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    if shutil.which(args.iverilog) is None:
        raise RuntimeError(f"Cannot find iverilog binary: {args.iverilog}")
    if shutil.which(args.vvp) is None:
        raise RuntimeError(f"Cannot find vvp binary: {args.vvp}")

    rows: List[Dict[str, object]] = []
    failures: List[str] = []

    with tempfile.TemporaryDirectory(prefix="metric_probe_") as td:
        temp_dir = Path(td)
        for spec in PROBE_SPECS:
            sva_path = write_probe_file(temp_dir, spec)
            row = evaluate_one(
                root,
                str(spec["case_name"]),
                sva_path,
                args.iverilog,
                args.vvp,
                bug_type="probe",
                method=str(spec.get("method", "") or ""),
                candidate_index=(int(spec["candidate_index"]) if str(spec.get("candidate_index", "")) else None),
                semantic_reasonable=spec.get("semantic_reasonable"),
                semantic_review_label=("override:false" if spec.get("semantic_reasonable") is False else ""),
                reviewed_assertion="",
            )
            row["probe_name"] = spec["name"]
            rows.append(row)
            mismatches = row_matches_expectation(row, dict(spec["expect"]))
            status = "PASS" if not mismatches else "FAIL"
            print(
                f"{spec['name']}: {status} | case={spec['case_name']} "
                f"template={row['syntax_pass']} analysis_supported={row['analysis_supported']} "
                f"compile={row['compile_ok']} failure_type={row['failure_type']}"
            )
            if mismatches:
                failures.append(f"{spec['name']}: " + "; ".join(mismatches))
                for item in mismatches:
                    print(f"  mismatch: {item}")

    out_csv = Path(args.output_csv).resolve()
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=REPORT_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in REPORT_FIELDS})

    print(f"[DONE] Wrote probe report: {out_csv}")
    if failures:
        print("[ERROR] Metric probe regression failed.")
        for failure in failures:
            print("  " + failure)
        return 1

    print(f"SUMMARY: {len(rows)}/{len(PROBE_SPECS)} probes matched expected columns/labels.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
