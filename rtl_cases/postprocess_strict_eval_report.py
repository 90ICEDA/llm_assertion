#!/usr/bin/env python3
import argparse
import csv
import re
from pathlib import Path
from typing import Dict, List, Tuple



def normalize_assertion(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def to_bool(value: str) -> bool:
    return str(value).strip().lower() == "true"


def classify_failure_type(row: Dict[str, str]) -> str:
    if (row.get("unsupported_reason") or "").strip():
        return "unsupported"
    detail = row.get("compile_error", "")
    if detail.startswith("STATIC_FILTER:"):
        return "static_filter_reject"
    if not to_bool(row["syntax_pass"]):
        return "template_mismatch"
    if not to_bool(row.get("compile_ok", "False")):
        return "compile_fail"
    if not to_bool(row["pass_on_correct"]):
        return "false_positive_on_correct"
    if not to_bool(row["antecedent_triggered"]):
        return "antecedent_not_triggered"
    if not to_bool(row["non_vacuous"]):
        return "vacuous"
    if not to_bool(row["fail_on_buggy"]):
        return "bug_not_detected_on_buggy"
    if to_bool(row.get("trace_overfit", "False")):
        return "trace_overfit"
    semantic = row.get("semantic_reasonable", "").strip().lower()
    if not semantic:
        return "semantic_unreviewed"
    if semantic != "true":
        return "semantic_unreasonable"
    return "strict_success"


def load_rows(path: Path) -> List[Dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write_rows(path: Path, rows: List[Dict[str, str]], fields: List[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for row in rows:
            w.writerow({field: row.get(field, "") for field in fields})


def is_template_garbage(row: Dict[str, str]) -> bool:
    detail = row.get("compile_error") or ""
    return detail.startswith("TEMPLATE_MISMATCH:") or detail.startswith("PARSE_ERROR:")


def build_review_decisions() -> Dict[Tuple[str, str, str], Tuple[str, str]]:
    decisions: Dict[Tuple[str, str, str], Tuple[str, str]] = {}

    broad_case03 = normalize_assertion(
        "assert property (@(posedge clk) disable iff (!rst_n) "
        "((valid_i && !ready_i) || (!valid_i && ready_i)) |-> (!valid_o));"
    )
    commuted_case03 = normalize_assertion(
        "assert property (@(posedge clk) disable iff (!rst_n) "
        "((valid_i && !ready_i) || (ready_i && !valid_i)) |-> (!valid_o));"
    )
    narrow_case03 = normalize_assertion(
        "assert property (@(posedge clk) disable iff (!rst_n) "
        "((valid_i && !ready_i)) |-> (!valid_o));"
    )
    case05 = normalize_assertion(
        "assert property (@(posedge clk) disable iff (!rst_n) "
        "(en && cnt == limit - 1) |=> (cnt == limit));"
    )
    case09 = normalize_assertion(
        "assert property (@(posedge clk) disable iff (!rst_n) "
        "(step && addr == 8'h04) |=> (addr == 8'h08));"
    )

    for method in ["spec_only", "spec_plus_rtl", "spec_rtl_raw_trace"]:
        for idx in ["1", "2", "3", "4", "5"]:
            key = ("case03_valid_ready_or_bug", method, idx)
            decisions[key] = (
                "true",
                "Yes (semantically meaningful illegal valid_o gating check)",
            )

    decisions[("case03_valid_ready_or_bug", "spec_plus_rtl", "3")] = (
        "false",
        "No (only covers valid_i=1, ready_i=0 and misses the symmetric illegal case)",
    )

    for idx in ["1", "4", "5"]:
        decisions[("case05_counter_boundary", "spec_rtl_trace_summary", idx)] = (
            "true",
            "Yes (correct boundary next-state check for early wrap bug)",
        )

    decisions[("case09_addr_increment", "spec_rtl_trace_summary", "5")] = (
        "false",
        "No (overfits one concrete address transition instead of expressing the general +4 stride property)",
    )

    for method in ["spec_only", "spec_plus_rtl", "spec_rtl_raw_trace", "spec_rtl_trace_summary"]:
        decisions[("case01_reset_omission", method, "1")] = (
            "true",
            "Yes (checks the required reset-to-zero behavior at reset assertion and directly targets the omitted-reset bug)",
        )
        decisions[("case02_grant_delay", method, "1")] = (
            "true",
            "Yes (cycle-by-cycle registered req/grant relation that directly exposes the extra-cycle delay bug)",
        )
        decisions[("case07_fifo_full_boundary", method, "1")] = (
            "true",
            "Yes (correct full/count equivalence invariant that directly detects early full assertion)",
        )
        decisions[("case04_fsm_transition", method, "1")] = (
            "true",
            "Yes (finish-aligned DONE-state check that directly catches the buggy BUSY-to-IDLE skip)",
        )
        decisions[("case05_counter_boundary", method, "1")] = (
            "true",
            "Yes (checks the required increment-by-one behavior before the wrap boundary)",
        )
        decisions[("case06_priority_encoder", method, "1")] = (
            "true",
            "true (checks exercised req[3]-contention scenarios and directly targets the reversed-priority bug under the current sampled-testbench semantics)",
        )
        decisions[("case10_hold_valid_until_ready", method, "1")] = (
            "true",
            "Yes (captures hold-until-ready while allowing handshake completion on the next cycle)",
        )

    for method in ["spec_only", "spec_plus_rtl", "spec_rtl_raw_trace"]:
        decisions[("case09_addr_increment", method, "1")] = (
            "true",
            "Yes (general +4 stride plus alignment property, not tied to one observed literal trace value)",
        )

    decisions[("case03_valid_ready_or_bug", "spec_rtl_trace_summary", "1")] = (
        "true",
        "Yes (semantically meaningful illegal valid_o gating check)",
    )
    decisions[("case09_addr_increment", "spec_rtl_trace_summary", "1")] = (
        "true",
        "Yes (general +4 stride plus alignment property, not tied to one observed literal trace value)",
    )

    for method in ["spec_plus_rtl"]:
        for idx in ["1", "2", "3", "4", "5"]:
            decisions[("case08_pulse_width", method, idx)] = (
                "true",
                "Yes (checks the required post-trigger hold cycle, which is the semantic core of the width bug)",
            )

    decisions[("case08_pulse_width", "spec_only", "1")] = (
        "true",
        "Yes (checks the required one-cycle-later pulse hold under the evaluator's sampled-state semantics)",
    )
    decisions[("case08_pulse_width", "spec_rtl_raw_trace", "1")] = (
        "true",
        "Yes (checks the required one-cycle-later pulse hold under the evaluator's sampled-state semantics)",
    )
    for idx in ["2", "3", "5"]:
        decisions[("case08_pulse_width", "spec_rtl_raw_trace", idx)] = (
            "true",
            "Yes (checks pulse remains high in the cycle after trigger, which directly targets the 1-cycle pulse bug)",
        )

    decisions[("case08_pulse_width", "spec_rtl_trace_summary", "1")] = (
        "true",
        "Yes (minimal but semantically correct delayed hold check for the required second pulse cycle)",
    )
    for idx in ["4", "5"]:
        decisions[("case08_pulse_width", "spec_rtl_trace_summary", idx)] = (
            "true",
            "Yes (reasonable launch-from-idle variant of the required delayed pulse hold check)",
        )

    for idx in ["1", "2", "3", "4"]:
        decisions[("case09_addr_increment", "spec_rtl_trace_summary", idx)] = (
            "false",
            "No (hard-codes one observed trace value pair instead of expressing the general +4 stride property)",
        )

    decisions[("case09_addr_increment", "spec_rtl_trace_summary", "1")] = (
        "true",
        "Yes (general +4 stride plus alignment property, not tied to one observed literal trace value)",
    )

    return decisions


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply manual semantic review decisions and remove template garbage rows."
    )
    parser.add_argument("--report", required=True, help="Path to strict eval report CSV.")
    args = parser.parse_args()

    report_path = Path(args.report).resolve()
    rows = load_rows(report_path)
    fields = list(rows[0].keys()) if rows else []
    for extra_field in [
        "trace_overfit",
        "trace_overfit_reason",
        "trace_literal_warning",
        "trace_literal_warning_reason",
        "heldout_compile_ok",
        "heldout_pass_on_correct",
        "heldout_fail_on_buggy",
        "heldout_non_vacuous",
        "heldout_antecedent_triggered",
        "heldout_correct_antecedent_hits",
        "heldout_buggy_antecedent_hits",
        "heldout_correct_fail_count",
        "heldout_buggy_fail_count",
        "heldout_compile_error",
        "analysis_supported",
        "unsupported_reason",
        "grammar_version",
    ]:
        if extra_field not in fields:
            fields.append(extra_field)

    decisions = build_review_decisions()

    kept_rows: List[Dict[str, str]] = []
    removed = 0
    reviewed = 0

    for row in rows:
        if is_template_garbage(row):
            removed += 1
            continue

        key = (
            row.get("case_name", "").strip(),
            row.get("method", "").strip(),
            row.get("candidate_index", "").strip(),
        )
        if key in decisions:
            semantic_value, semantic_label = decisions[key]
            row["semantic_reasonable"] = semantic_value
            row["semantic_review_label"] = semantic_label
            reviewed += 1
        row.setdefault("trace_overfit", "False")
        row.setdefault("trace_overfit_reason", "")
        row.setdefault("trace_literal_warning", "False")
        row.setdefault("trace_literal_warning_reason", "")
        row.setdefault("heldout_compile_ok", "False")
        row.setdefault("heldout_pass_on_correct", "False")
        row.setdefault("heldout_fail_on_buggy", "False")
        row.setdefault("heldout_non_vacuous", "False")
        row.setdefault("heldout_antecedent_triggered", "False")
        row.setdefault("heldout_correct_antecedent_hits", "0")
        row.setdefault("heldout_buggy_antecedent_hits", "0")
        row.setdefault("heldout_correct_fail_count", "-1")
        row.setdefault("heldout_buggy_fail_count", "-1")
        row.setdefault("heldout_compile_error", "")
        row.setdefault("analysis_supported", "True")
        row.setdefault("unsupported_reason", "")
        row.setdefault("grammar_version", "")

        row["strict_success"] = str(
            to_bool(row.get("compile_ok", "False"))
            and to_bool(row.get("pass_on_correct", "False"))
            and to_bool(row.get("fail_on_buggy", "False"))
            and to_bool(row.get("non_vacuous", "False"))
            and to_bool(row.get("antecedent_triggered", "False"))
            and not to_bool(row.get("trace_overfit", "False"))
            and str(row.get("semantic_reasonable", "")).strip().lower() == "true"
        )
        row["failure_type"] = classify_failure_type(row)
        kept_rows.append(row)

    write_rows(report_path, kept_rows, fields)
    print(f"[DONE] Updated report: {report_path}")
    print(f"[INFO] Reviewed rows: {reviewed}")
    print(f"[INFO] Removed template garbage rows: {removed}")
    print(
        "[INFO] strict_success rows: "
        f"{sum(1 for row in kept_rows if to_bool(row.get('strict_success', 'False')))}"
    )


if __name__ == "__main__":
    main()
