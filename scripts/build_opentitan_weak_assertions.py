#!/usr/bin/env python3
"""Materialize task-4 weak-assertion candidates for the 15 OpenTitan cases.

These are deliberately weak hypotheses, not verified results.  Semantic admission
must be decided by the separate correct/buggy, holdout, and non-vacuity run.
"""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "rtl_cases_real_scale210_independent"


def w(kind: str, body: str, antecedent: str | None, reason: str) -> dict:
    return {
        "weakness_class": kind,
        "property": body,
        "antecedent": antecedent,
        "antecedent_nonempty": bool(antecedent),
        "expected_weakness": reason,
        "validation_status": "pending",
        "catches_bug": None,
        "nonvacuity_verified": False,
    }


CASES = {
    401: [
        w("single_cycle_implication", "(!rst_ni) |-> (filter_o == 1'b0)", "!rst_ni", "Only checks the visible output in the reset sample and ignores retained-state timing."),
        w("final_output_only", "enable_i |-> !$isunknown(filter_o)", "enable_i", "Observes only whether the final output is known, not when it may change."),
        w("delay_removed", "(enable_i && filter_i) |-> filter_o", "enable_i && filter_i", "Requires only an immediate sample and discards the qualification interval."),
        w("antecedent_removed", "stored_value_q == 1'b0", None, "Drops the reset trigger and therefore describes only a coarse state value."),
        w("simple_invariant", "filter_o == stored_value_q || !enable_i", None, "A local consistency invariant cannot establish reset or history duration."),
    ],
    402: [
        w("single_cycle_implication", "(enable_i && filter_i) |-> (filter_o == stored_value_q)", "enable_i && filter_i", "Checks one sample without requiring a full stable-input history."),
        w("final_output_only", "(&stored_vector_q) |-> filter_o", "&stored_vector_q", "Checks only the output endpoint and omits the retained-state update."),
        w("delay_removed", "(enable_i && (&stored_vector_q)) |-> (stored_value_q && filter_o)", "enable_i && (&stored_vector_q)", "Removes the required next-cycle state transition."),
        w("antecedent_removed", "stored_value_q |-> filter_o", "stored_value_q", "Removes the qualifying history antecedent and keeps only local state/output consistency."),
        w("simple_invariant", "!enable_i || (filter_o == stored_value_q)", None, "Does not constrain when stored_value_q is allowed to update."),
    ],
    403: [
        w("single_cycle_implication", "filter_i |-> stored_vector_q[0]", "filter_i", "Looks at one history bit in one sample, not the complete shift operation."),
        w("final_output_only", "rst_ni |-> !$isunknown(stored_vector_q)", "rst_ni", "Only checks that the final vector is known."),
        w("delay_removed", "filter_i |-> (stored_vector_q != '0)", "filter_i", "Uses an immediate coarse nonzero check instead of next-cycle append and shift."),
        w("antecedent_removed", "stored_vector_q == '0", None, "Drops the reset trigger and cannot distinguish reset behavior from an incidental zero history."),
        w("simple_invariant", "!$isunknown(stored_vector_q)", None, "Knownness does not constrain reset clearing or sample order."),
    ],
    404: [
        w("single_cycle_implication", "(reg2hw_intr_state_q_i && reg2hw_intr_enable_q_i) |-> intr_o", "reg2hw_intr_state_q_i && reg2hw_intr_enable_q_i", "Checks the current sample and misses registered-output latency."),
        w("final_output_only", "rst_ni |-> !$isunknown(intr_o)", "rst_ni", "Only checks the output endpoint for knownness."),
        w("delay_removed", "(event_intr_i != '0) |-> (intr_o != '0)", "event_intr_i != '0", "Collapses the registered response into the event cycle."),
        w("antecedent_removed", "intr_o == '0", None, "Drops the reset antecedent and becomes a coarse constant-output claim."),
        w("simple_invariant", "(intr_o & ~reg2hw_intr_enable_q_i) == '0", None, "A mask invariant cannot prove reset or prior-cycle capture semantics."),
    ],
    405: [
        w("single_cycle_implication", "(reg2hw_intr_state_q_i && reg2hw_intr_enable_q_i) |-> intr_o", "reg2hw_intr_state_q_i && reg2hw_intr_enable_q_i", "Uses same-cycle implication and misses the register delay."),
        w("final_output_only", "intr_o |-> reg2hw_intr_enable_q_i", "intr_o", "Checks only a current output-to-enable relation, not capture timing."),
        w("delay_removed", "(reg2hw_intr_state_q_i && reg2hw_intr_enable_q_i) |-> intr_o", "reg2hw_intr_state_q_i && reg2hw_intr_enable_q_i", "Explicitly removes the next-cycle operator from the golden behavior."),
        w("antecedent_removed", "intr_o", None, "Drops the enabled-status trigger and reduces the property to an output level."),
        w("simple_invariant", "!intr_o || reg2hw_intr_enable_q_i", None, "Local implication does not constrain the registered transition."),
    ],
    406: [
        w("single_cycle_implication", "(!rst_ni) |-> empty_o", "!rst_ni", "Checks only one visible flag, omitting pointer, depth, and reset-state timing."),
        w("final_output_only", "empty_o |-> !full_o", "empty_o", "Only relates endpoint flags."),
        w("delay_removed", "clr_i |-> (depth_o == '0)", "clr_i", "Checks clear in the request sample rather than the cleared registered state."),
        w("antecedent_removed", "depth_o == '0", None, "Drops reset and observes only an occupancy value."),
        w("simple_invariant", "!(empty_o && full_o)", None, "Flag mutual exclusion does not establish pointer/depth reset correctness."),
    ],
    407: [
        w("single_cycle_implication", "clr_i |-> empty_o", "clr_i", "Checks only the current empty flag, not the following cleared state."),
        w("final_output_only", "clr_i |=> empty_o", "clr_i", "Checks only one final flag and omits pointer and occupancy."),
        w("delay_removed", "clr_i |-> ((wptr_o == '0) && (depth_o == '0))", "clr_i", "Removes the next-cycle clear effect."),
        w("antecedent_removed", "(wptr_o == '0) && (depth_o == '0)", None, "Drops the clear request and cannot tie zero state to the operation."),
        w("simple_invariant", "empty_o |-> (depth_o == '0)", "empty_o", "Only checks flag/depth consistency, not clearing behavior."),
    ],
    408: [
        w("single_cycle_implication", "incr_wptr_i |-> (wptr_o != 2'd3)", "incr_wptr_i", "A one-sample endpoint check does not establish modulo wrap."),
        w("final_output_only", "(wptr_o == 2'd3) |=> (wptr_o != 2'd3)", "wptr_o == 2'd3", "Observes only that the endpoint changes, not that it wraps to zero under an accepted write."),
        w("delay_removed", "(incr_wptr_i && (wptr_o == 2'd3)) |-> (wptr_o == 2'd0)", "incr_wptr_i && (wptr_o == 2'd3)", "Removes the required next-cycle wrap transition."),
        w("antecedent_removed", "wptr_o == 2'd0", None, "Drops both increment and terminal-pointer triggers."),
        w("simple_invariant", "wptr_o <= 2'd3", None, "Range checking cannot distinguish correct modulo update."),
    ],
    409: [
        w("single_cycle_implication", "incr_wptr_i |-> (wptr_o != $past(wptr_o))", "incr_wptr_i", "Only demands a change and does not constrain its value or clear interaction."),
        w("final_output_only", "incr_wptr_i |=> (wptr_o <= 2'd3)", "incr_wptr_i", "Checks only the final pointer range."),
        w("delay_removed", "(incr_wptr_i && !clr_i) |-> (wptr_o == ($past(wptr_o) + 1'b1))", "incr_wptr_i && !clr_i", "Uses the update equation in the request sample rather than the next sample."),
        w("antecedent_removed", "wptr_o == ($past(wptr_o) + 1'b1)", None, "Drops the accepted-increment condition."),
        w("simple_invariant", "wptr_o <= 2'd3", None, "A pointer-range invariant misses wrong increment timing and direction."),
    ],
    431: [
        w("single_cycle_implication", "oh_i[0] |-> !err_o", "oh_i[0]", "Samples only one bit and accepts multi-hot combinations containing it."),
        w("final_output_only", "$onehot(oh_i) |-> !$isunknown(err_o)", "$onehot(oh_i)", "Checks only that the error output is known, not deasserted."),
        w("delay_removed", "$onehot(oh_i) |=> !err_o", "$onehot(oh_i)", "Introduces a delayed endpoint and can miss a same-cycle protocol error."),
        w("antecedent_removed", "!err_o", None, "Drops the valid-code condition and reduces the assertion to an output level."),
        w("simple_invariant", "err_o == 1'b0 || err_o == 1'b1", None, "A Boolean range invariant carries no one-hot semantics."),
    ],
    432: [
        w("single_cycle_implication", "(en_i && oh_i[addr_i]) |-> !err_o", "en_i && oh_i[addr_i]", "Omits the one-hot requirement and therefore ignores other asserted bits."),
        w("final_output_only", "(en_i && $onehot(oh_i)) |-> !$isunknown(err_o)", "en_i && $onehot(oh_i)", "Checks only output knownness and omits address agreement."),
        w("delay_removed", "(en_i && $onehot(oh_i) && oh_i[addr_i]) |=> !err_o", "en_i && $onehot(oh_i) && oh_i[addr_i]", "Moves a same-cycle protocol relation to the next sample."),
        w("antecedent_removed", "!err_o", None, "Drops enable, one-hot, and matching-address conditions."),
        w("simple_invariant", "!en_i |-> !err_o", "!en_i", "Only constrains the disabled mode and says nothing about address checking."),
    ],
    433: [
        w("single_cycle_implication", "d_i |-> q_sync_o", "d_i", "Checks only the high polarity and not continuous equality or edge pulses."),
        w("final_output_only", "rst_ni |-> !$isunknown(q_sync_o)", "rst_ni", "Only checks output knownness."),
        w("delay_removed", "d_i |=> q_sync_o", "d_i", "Adds a cycle to a no-synchronizer path and loses same-cycle tracking."),
        w("antecedent_removed", "q_sync_o", None, "Drops the input condition and observes only a fixed output polarity."),
        w("simple_invariant", "!(q_posedge_pulse_o && q_negedge_pulse_o)", None, "Pulse mutual exclusion does not establish the data path."),
    ],
    434: [
        w("single_cycle_implication", "!d_i |-> !q_sync_o", "!d_i", "Checks only the low polarity and omits edge behavior."),
        w("final_output_only", "rst_ni |-> !$isunknown(q_sync_o)", "rst_ni", "Only checks that the endpoint is known."),
        w("delay_removed", "d_i |=> q_sync_o", "d_i", "Uses next-cycle response for a same-cycle bypass path."),
        w("antecedent_removed", "!q_sync_o", None, "Drops the input relation and becomes a constant-level claim."),
        w("simple_invariant", "!(q_posedge_pulse_o && q_negedge_pulse_o)", None, "Does not constrain q_sync_o tracking or pulse timing."),
    ],
    435: [
        w("single_cycle_implication", "(!enable_i && filter_i) |-> filter_o", "!enable_i && filter_i", "Checks only the high input polarity and misses equality for low input."),
        w("final_output_only", "!enable_i |-> !$isunknown(filter_o)", "!enable_i", "Only checks output knownness in bypass mode."),
        w("delay_removed", "(!enable_i) |=> (filter_o == filter_i)", "!enable_i", "Delays a same-cycle bypass relation and can miss the current mismatch."),
        w("antecedent_removed", "filter_o == filter_i", None, "Drops the disabled-mode guard and does not target the bypass protocol."),
        w("simple_invariant", "filter_o == 1'b0 || filter_o == 1'b1", None, "A Boolean range invariant contains no filter semantics."),
    ],
    436: [
        w("single_cycle_implication", "(enable_i && filter_i) |-> filter_o", "enable_i && filter_i", "Checks one sample and ignores the threshold qualification duration."),
        w("final_output_only", "enable_i |-> !$isunknown(filter_o)", "enable_i", "Only checks final output knownness."),
        w("delay_removed", "(enable_i && $stable(filter_i)) |-> (filter_o == filter_i)", "enable_i && $stable(filter_i)", "Reduces the four-sample persistence requirement to one stable observation."),
        w("antecedent_removed", "filter_o == filter_i", None, "Drops enable and persistence qualification."),
        w("simple_invariant", "filter_o == 1'b0 || filter_o == 1'b1", None, "A Boolean range check cannot establish counter-qualified commitment."),
    ],
}

EVENTS = {
    431: "@(oh_i or rst_ni)",
    432: "@(oh_i or addr_i or en_i or rst_ni)",
}


def main() -> None:
    for number, assertions in CASES.items():
        matches = sorted(ROOT.glob(f"case{number}_*"))
        if len(matches) != 1:
            raise RuntimeError(f"case{number}: expected one directory, found {len(matches)}")
        case_dir = matches[0]
        metadata = json.loads((case_dir / "case_metadata.json").read_text(encoding="utf-8"))
        project = str(metadata.get("source_project", "")).lower()
        if "opentitan" not in project:
            raise RuntimeError(f"{case_dir.name}: source_project is not OpenTitan: {project}")
        for index, assertion in enumerate(assertions, 1):
            assertion["id"] = f"W{index}_{assertion['weakness_class']}"
        document = {
            "schema_version": "weak-assertions-v1",
            "case_id": case_dir.name,
            "parent_bug_id": metadata.get("parent_bug_id"),
            "source_project": metadata.get("source_project"),
            "admission_rule": "At least two non-vacuous weak assertions must miss the RTL bug.",
            "overall_validation_status": "pending",
            "assertions": assertions,
        }
        (case_dir / "weak_assertions.json").write_text(
            json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        lines = [
            "// Task-4 weak candidates; NOT semantic-validation results.",
            "// Every property must be checked on correct/buggy primary and held-out traces.",
            "",
        ]
        event = EVENTS.get(number, "@(posedge clk_i)")
        for assertion in assertions:
            lines.extend(
                [
                    f"// {assertion['id']}",
                    f"// antecedent_nonempty: {str(assertion['antecedent_nonempty']).lower()}",
                    f"// expected weakness: {assertion['expected_weakness']}",
                    f"{assertion['id']}: assert property ({event} disable iff (!rst_ni) {assertion['property']});",
                    "",
                ]
            )
        (case_dir / "weak_assertions.sva").write_text("\n".join(lines), encoding="utf-8")
        print(case_dir.name)


if __name__ == "__main__":
    main()
