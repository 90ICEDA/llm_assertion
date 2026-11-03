#!/usr/bin/env python3
"""Materialize deliberately weak SVA candidates for the 16 verilog-axis cases.

These are admission-test inputs, not validation results.  In particular this
script never marks a candidate as catching or missing a mutation.
"""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "rtl_cases_real_scale210_independent"


# case suffix: (clocking, reduced antecedent, full antecedent, consequent)
CASES = {
    421: ("@(posedge clk) disable iff (rst)", "m_axis_tready", "m_axis_tready && !m_axis_tvalid", "s_axis_tready"),
    422: ("@(posedge clk) disable iff (rst)", "s_axis_tvalid", "s_axis_tvalid && s_axis_tready && m_axis_tready", "m_axis_tvalid"),
    423: ("@(posedge clk) disable iff (rst)", "m_axis_tvalid && !m_axis_tready", "m_axis_tvalid && !m_axis_tready && s_axis_tvalid && s_axis_tready", "!s_axis_tready"),
    424: ("@(posedge clk) disable iff (rst)", "status_overflow", "status_overflow", "!status_overflow"),
    425: ("@(posedge clk) disable iff (rst)", "status_bad_frame", "status_bad_frame", "!status_bad_frame"),
    426: ("@(posedge clk) disable iff (rst)", "status_good_frame", "status_good_frame", "!status_good_frame"),
    427: ("@(posedge clk) disable iff (rst)", "|request", "(|request) && !(|grant)", "|grant"),
    428: ("@(posedge clk) disable iff (rst)", "|request", "(|request) && !grant_valid", "grant_valid"),
    429: ("@(posedge clk) disable iff (rst)", "s_axis_tvalid", "!by_frame && s_axis_tvalid && s_axis_tready", "!s_axis_tready"),
    430: ("@(posedge clk) disable iff (rst)", "by_frame && !s_axis_tvalid", "by_frame && !s_axis_tvalid", "s_axis_tready"),
    445: ("@(input_unencoded)", "input_unencoded[0]", "|input_unencoded", "output_valid"),
    446: ("@(input_unencoded)", "output_valid", "output_valid", "input_unencoded[output_encoded]"),
    447: ("@(posedge clk) disable iff (rst)", "enable", "enable && m_axis_tready", "s_axis_tready[select]"),
    448: ("@(posedge clk) disable iff (rst)", "m_axis_tvalid", "m_axis_tvalid && m_axis_tready", "m_axis_tdata == s_axis_tdata[select*DATA_WIDTH +: DATA_WIDTH]"),
    449: ("@(posedge clk) disable iff (rst)", "enable && !drop", "enable && !drop && m_axis_tready[select] && !(|m_axis_tvalid)", "s_axis_tready"),
    450: ("@(posedge clk) disable iff (rst)", "m_axis_tvalid[select]", "m_axis_tvalid[select]", "m_axis_tdata[select*DATA_WIDTH +: DATA_WIDTH] == s_axis_tdata"),
}


def candidate(kind, expression, nonempty, rationale):
    return {
        "id": f"weak_{kind}",
        "weakening_type": kind,
        "expression": expression,
        "nonempty_antecedent": nonempty,
        "rationale": rationale,
        "verification_status": "pending",
        "catches_bug": None,
    }


def main():
    case_dirs = {int(p.name[4:7]): p for p in ROOT.glob("case*_*") if p.is_dir()}
    for number, (clocking, reduced, antecedent, consequent) in CASES.items():
        case_dir = case_dirs[number]
        candidates = [
            candidate(
                "single_cycle_implication",
                f"assert property ({clocking} ({reduced}) |-> ({consequent}));",
                True,
                "Checks only the current sample after a reduced trigger and cannot enforce the required cross-cycle history.",
            ),
            candidate(
                "final_output_only",
                f"assert property ({clocking} ({consequent}) |-> !$isunknown({consequent}));",
                True,
                "Observes only that the final output is known when already asserted; it ignores how and when that output was reached.",
            ),
            candidate(
                "delay_removed",
                f"assert property ({clocking} ({antecedent}) |-> ({consequent}));",
                True,
                "Removes the next-cycle or multi-cycle delay from the intended temporal relationship.",
            ),
            candidate(
                "antecedent_removed",
                f"assert property ({clocking} 1'b1 |-> !$isunknown({consequent}));",
                False,
                "Drops the behavioral trigger and reduces the check to output definedness.",
            ),
            candidate(
                "simple_invariant",
                f"assert property ({clocking} 1'b1 |-> !$isunknown({reduced}));",
                False,
                "A generic signal-integrity invariant contains no ordering, exact delay, duration, or protocol condition.",
            ),
        ]
        document = {
            "schema_version": "weak-assertions-v1",
            "case_id": case_dir.name,
            "source_project": "verilog_axis",
            "purpose": "difficulty_admission_pending_validation",
            "admission_rule": "At least two non-vacuous weak assertions must miss the buggy RTL before admission.",
            "overall_verification_status": "pending",
            "candidates": candidates,
        }
        (case_dir / "weak_assertions.json").write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        lines = [
            f"// Deliberately weak admission candidates for {case_dir.name}.",
            "// PENDING VALIDATION: presence in this file is not evidence that a candidate misses the bug.",
            "",
        ]
        for item in candidates:
            lines.extend([
                f"// {item['id']}: {item['rationale']}",
                item["expression"],
                "",
            ])
        (case_dir / "weak_assertions.sva").write_text("\n".join(lines), encoding="utf-8")

    print(f"wrote weak assertion assets for {len(CASES)} verilog-axis cases")


if __name__ == "__main__":
    main()
