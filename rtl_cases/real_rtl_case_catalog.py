#!/usr/bin/env python3
from __future__ import annotations

from typing import Dict, List


def _controls(*items: Dict[str, str]) -> List[Dict[str, str]]:
    return list(items)


def load_case_blueprints() -> List[Dict[str, object]]:
    # These are intentionally planning-grade blueprints backed by real RTL mutation points.
    # They define the mutation, metadata, and hardness rationale up front so we can build
    # the next benchmark phase around real source code rather than the old hand-written toys.
    #
    # The per-case simulation artifacts (tb / tb_holdout / waveforms) are expected to be added
    # on top of this catalog before the cases are admitted into the scored benchmark.
    return [
        {
            "name": "case101_prim_onehot_multihot_suppressed",
            "source_project": "opentitan",
            "source_module": "prim_onehot_check",
            "source_files": [
                "hw/ip/prim/rtl/prim_onehot_check.sv",
            ],
            "top_file": "hw/ip/prim/rtl/prim_onehot_check.sv",
            "mutation_edits": [
                {
                    "search": "  assign oh0_err = err_tree[0];\n",
                    "replace": "  assign oh0_err = 1'b0;\n",
                }
            ],
            "bug_class": "combination_same_cycle",
            "bug_family": "onehot_violation_masked",
            "bug_type": "multihot error suppressed",
            "spec": "When more than one bit of oh_i is high in the same cycle, err_o must assert in that same cycle.",
            "key_signals": ["clk_i", "rst_ni", "oh_i", "addr_i", "en_i", "err_o"],
            "golden_sva": {
                "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) (((((oh_i == 4'b1010) && ($past(oh_i) == 4'b1010)) || ((oh_i == 4'b1100) && ($past(oh_i) == 4'b1100))) && en_i && $past(en_i))) |-> err_o);",
                "expected_behavior": "A multihot onehot vector must trigger err_o in the sampled cycle.",
                "temporal_type": "same-cycle combinational check",
            },
            "loose_negative_controls": _controls(
                {
                    "name": "enable_only",
                    "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) (!en_i) |-> !err_o);",
                    "why_it_should_miss": "It constrains only the disabled case and says nothing about multihot inputs while enabled.",
                },
                {
                    "name": "eventual_error",
                    "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) (|oh_i) |-> (err_o || en_i));",
                    "why_it_should_miss": "It is too weak and does not require exact multihot detection.",
                },
            ),
            "hard_case_rationale": "A vague assertion like 'onehot input should be legal' can pass without explicitly checking the multihot corner. The precise bug appears only when two request bits are simultaneously high.",
            "overfit_lure": "",
            "stimulus_notes": "Drive legal onehot patterns first, then inject 4'b1010 and 4'b0110 while en_i is high. Held-out should use different multihot literals.",
        },
        {
            "name": "case102_prim_onehot_enable_mismatch_suppressed",
            "source_project": "opentitan",
            "source_module": "prim_onehot_check",
            "source_files": [
                "hw/ip/prim/rtl/prim_onehot_check.sv",
            ],
            "top_file": "hw/ip/prim/rtl/prim_onehot_check.sv",
            "mutation_edits": [
                {
                    "search": "      assign enable_err = or_tree[0] ^ en_i;\n",
                    "replace": "      assign enable_err = 1'b0;\n",
                }
            ],
            "bug_class": "combination_same_cycle",
            "bug_family": "enable_consistency",
            "bug_type": "enable mismatch error suppressed",
            "spec": "With strict enable checking enabled, err_o shall assert whenever en_i disagrees with whether any onehot bit is set.",
            "key_signals": ["clk_i", "rst_ni", "oh_i", "addr_i", "en_i", "err_o"],
            "golden_sva": {
                "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) (((oh_i == 4'b0000) && ($past(oh_i) == 4'b0000) && en_i && $past(en_i))) |-> err_o);",
                "expected_behavior": "The checker must flag disagreement between en_i and the OR-reduced oh_i input.",
                "temporal_type": "same-cycle combinational check",
            },
            "loose_negative_controls": _controls(
                {
                    "name": "multihot_only",
                    "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) (((oh_i == 4'b0011) || (oh_i == 4'b0101) || (oh_i == 4'b0110) || (oh_i == 4'b0111) || (oh_i == 4'b1001) || (oh_i == 4'b1010) || (oh_i == 4'b1011) || (oh_i == 4'b1100) || (oh_i == 4'b1101) || (oh_i == 4'b1110) || (oh_i == 4'b1111)) |-> err_o);",
                    "why_it_should_miss": "It ignores the legal onehot-but-disabled and zero-hot-but-enabled mismatches.",
                },
                {
                    "name": "request_implies_enable",
                    "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) (|oh_i) |-> en_i);",
                    "why_it_should_miss": "It checks only one direction and misses the all-zero while enabled corner.",
                },
            ),
            "hard_case_rationale": "The mutation does not break basic onehot structure. Only an assertion that ties en_i exactly to the presence of a selected bit can expose it.",
            "overfit_lure": "",
            "stimulus_notes": "Use both mismatch directions: oh_i=0 with en_i=1, and oh_i=4'b0100 with en_i=0. Held-out should use different onehot positions.",
        },
        {
            "name": "case103_prim_onehot_addr_mismatch_suppressed",
            "source_project": "opentitan",
            "source_module": "prim_onehot_check",
            "source_files": [
                "hw/ip/prim/rtl/prim_onehot_check.sv",
            ],
            "top_file": "hw/ip/prim/rtl/prim_onehot_check.sv",
            "mutation_edits": [
                {
                    "search": "    assign addr_err = or_tree[0] ^ and_tree[0];\n",
                    "replace": "    assign addr_err = 1'b0;\n",
                }
            ],
            "bug_class": "combination_same_cycle",
            "bug_family": "decoded_index_consistency",
            "bug_type": "address mismatch error suppressed",
            "spec": "If exactly one bit of oh_i is high, err_o shall assert when addr_i points to a different bit in the same cycle.",
            "key_signals": ["clk_i", "rst_ni", "oh_i", "addr_i", "en_i", "err_o"],
            "golden_sva": {
                "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) (((((oh_i == 4'b0100) && ($past(oh_i) == 4'b0100) && (addr_i == 2'd0) && ($past(addr_i) == 2'd0)) || ((oh_i == 4'b0010) && ($past(oh_i) == 4'b0010) && (addr_i == 2'd0) && ($past(addr_i) == 2'd0))) && en_i && $past(en_i))) |-> err_o);",
                "expected_behavior": "A onehot vector whose active bit disagrees with addr_i must be rejected immediately.",
                "temporal_type": "same-cycle combinational check",
            },
            "loose_negative_controls": _controls(
                {
                    "name": "enable_consistency_only",
                    "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) (((|oh_i) ^ en_i)) |-> err_o);",
                    "why_it_should_miss": "en_i can still match |oh_i| even when addr_i points to the wrong position.",
                },
                {
                    "name": "any_request_valid",
                    "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) (|oh_i) |-> !err_o);",
                    "why_it_should_miss": "It treats any asserted onehot vector as valid and therefore misses the index mismatch.",
                },
            ),
            "hard_case_rationale": "The bug is not about onehotness; it is about exact bit-to-index consistency. General 'onehot legal' assertions will miss it.",
            "overfit_lure": "",
            "stimulus_notes": "Hold oh_i onehot while sweeping addr_i across both matching and mismatching values. Held-out should use different active bits.",
        },
        {
            "name": "case104_prim_fifo_full_early",
            "source_project": "opentitan",
            "source_module": "prim_fifo_sync_cnt",
            "source_files": [
                "hw/ip/prim/rtl/prim_util_pkg.sv",
                "hw/ip/prim/rtl/prim_fifo_sync_cnt.sv",
            ],
            "top_file": "hw/ip/prim/rtl/prim_fifo_sync_cnt.sv",
            "mutation_edits": [
                {
                    "search": "  assign full_o = wptr_wrap_cnt_q == (rptr_wrap_cnt_q ^ {1'b1, {(WrapPtrW-1){1'b0}}});\n",
                    "replace": "  assign full_o = (wptr_wrap_cnt_q + {{(WrapPtrW-1){1'b0}}, 1'b1}) == (rptr_wrap_cnt_q ^ {1'b1, {(WrapPtrW-1){1'b0}}});\n",
                }
            ],
            "bug_class": "combination_same_cycle",
            "bug_family": "fifo_boundary_flag",
            "bug_type": "full asserted one slot early",
            "spec": "full_o shall assert if and only if the FIFO currently contains Depth entries; it must remain low at Depth-1.",
            "key_signals": ["clk_i", "rst_ni", "clr_i", "incr_wptr_i", "incr_rptr_i", "full_o", "empty_o", "depth_o", "wptr_o"],
            "golden_sva": {
                "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) ((wptr_o == 2'd3) && !incr_rptr_i && !empty_o && !clr_i) |-> !full_o);",
                "expected_behavior": "At the last legal pre-wrap write pointer position, the FIFO is not yet full and full_o must remain low.",
                "temporal_type": "same-cycle boundary flag check",
            },
            "loose_negative_controls": _controls(
                {
                    "name": "full_implies_max_depth",
                    "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) full_o |-> (depth_o == 3'd4));",
                    "why_it_should_miss": "It may stay vacuous if the bug avoids asserting full under the sampled corner or if the depth output is also misleading.",
                },
                {
                    "name": "eventual_full_after_writes",
                    "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) incr_wptr_i |-> !empty_o);",
                    "why_it_should_miss": "It does not constrain the exact boundary cycle where full must remain low.",
                },
            ),
            "hard_case_rationale": "This is a classic tight boundary bug. A hand-wavy FIFO assertion can pass while missing the exact Depth-1 cycle.",
            "overfit_lure": "Use Depth=4 and primary trace values 0,1,2,3,4 so trace-informed methods are tempted to memorize the literal boundary.",
            "stimulus_notes": "Fill the FIFO to 3 entries without reads, sample full_o at depth 3, then push once more. Held-out should use an interleaved read/write prelude before reaching depth 3 again.",
        },
        {
            "name": "case105_prim_fifo_empty_late",
            "source_project": "opentitan",
            "source_module": "prim_fifo_sync_cnt",
            "source_files": [
                "hw/ip/prim/rtl/prim_util_pkg.sv",
                "hw/ip/prim/rtl/prim_fifo_sync_cnt.sv",
            ],
            "top_file": "hw/ip/prim/rtl/prim_fifo_sync_cnt.sv",
            "mutation_edits": [
                {
                    "search": "  assign empty_o = wptr_wrap_cnt_q == rptr_wrap_cnt_q;\n",
                    "replace": "  assign empty_o = (wptr_wrap_cnt_q + {{(WrapPtrW-1){1'b0}}, 1'b1}) == rptr_wrap_cnt_q;\n",
                }
            ],
            "bug_class": "combination_same_cycle",
            "bug_family": "fifo_boundary_flag",
            "bug_type": "empty asserted one cycle late",
            "spec": "empty_o shall assert in the same cycle the FIFO occupancy returns to zero.",
            "key_signals": ["clk_i", "rst_ni", "clr_i", "incr_wptr_i", "incr_rptr_i", "full_o", "empty_o", "depth_o"],
            "golden_sva": {
                "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) (depth_o == 3'd0) |-> empty_o);",
                "expected_behavior": "Whenever occupancy is zero, empty_o must be high immediately.",
                "temporal_type": "same-cycle combinational boundary check",
            },
            "loose_negative_controls": _controls(
                {
                    "name": "empty_after_clear_only",
                    "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) clr_i |=> empty_o);",
                    "why_it_should_miss": "It checks reset-like clearing but not the normal read-to-empty transition.",
                },
                {
                    "name": "no_full_when_empty",
                    "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) empty_o |-> !full_o);",
                    "why_it_should_miss": "The buggy design can satisfy this while still delaying empty_o.",
                },
            ),
            "hard_case_rationale": "The bug only appears at the exact zero-occupancy return point. Loose assertions about mutual exclusion of full/empty are not enough.",
            "overfit_lure": "Use explicit depth values 2,1,0 in the primary trace so a trace-guided model can be baited into literal matching.",
            "stimulus_notes": "Write two entries, read them out, and sample the final read-to-empty transition. Held-out should empty after a write/read/write/read pattern.",
        },
        {
            "name": "case106_prim_fifo_depth_off_by_one",
            "source_project": "opentitan",
            "source_module": "prim_fifo_sync_cnt",
            "source_files": [
                "hw/ip/prim/rtl/prim_util_pkg.sv",
                "hw/ip/prim/rtl/prim_fifo_sync_cnt.sv",
            ],
            "top_file": "hw/ip/prim/rtl/prim_fifo_sync_cnt.sv",
            "mutation_edits": [
                {
                    "search": "                   wptr_wrap_msb == rptr_wrap_msb ? DepthW'(wptr_o) - DepthW'(rptr_o) :\n",
                    "replace": "                   wptr_wrap_msb == rptr_wrap_msb ? DepthW'(wptr_o) - DepthW'(rptr_o) + DepthW'(1'b1) :\n",
                }
            ],
            "bug_class": "combination_same_cycle",
            "bug_family": "fifo_boundary_flag",
            "bug_type": "depth output biased high by one",
            "spec": "depth_o shall equal the exact FIFO occupancy in every cycle.",
            "key_signals": ["clk_i", "rst_ni", "clr_i", "incr_wptr_i", "incr_rptr_i", "full_o", "empty_o", "depth_o"],
            "golden_sva": {
                "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) (empty_o) |-> (depth_o == 3'd0));",
                "expected_behavior": "When the FIFO is empty, the occupancy output must report zero rather than a biased nonzero value.",
                "temporal_type": "same-cycle combinational boundary check",
            },
            "loose_negative_controls": _controls(
                {
                    "name": "nonempty_has_depth",
                    "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) (!empty_o) |-> (depth_o != 3'd0));",
                    "why_it_should_miss": "A depth output biased high by one can still satisfy a coarse nonzero-when-nonempty check.",
                },
                {
                    "name": "full_empty_exclusive",
                    "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) !(full_o && empty_o));",
                    "why_it_should_miss": "It ignores the numeric correctness of depth_o itself.",
                },
            ),
            "hard_case_rationale": "This bug is subtle because the control flags can look mostly plausible. Only a precise occupancy relation catches it.",
            "overfit_lure": "",
            "stimulus_notes": "Exercise empty, single-entry, and two-entry states. Held-out should revisit zero occupancy after a clear pulse.",
        },
        {
            "name": "case107_prim_regwe_zero_enabled_false_positive",
            "source_project": "opentitan",
            "source_module": "prim_reg_we_check",
            "source_files": [
                "hw/ip/prim/rtl/prim_util_pkg.sv",
                "hw/ip/prim_generic/rtl/prim_buf.sv",
                "hw/ip/prim/rtl/prim_onehot_check.sv",
                "hw/ip/prim/rtl/prim_reg_we_check.sv",
            ],
            "top_file": "hw/ip/prim/rtl/prim_reg_we_check.sv",
            "mutation_edits": [
                {
                    "search": "    .StrictCheck(0)\n",
                    "replace": "    .StrictCheck(1)\n",
                }
            ],
            "bug_class": "combination_same_cycle",
            "bug_family": "masked_write_enable_legality",
            "bug_type": "enabled zero-write vector spuriously flags an error",
            "spec": "For prim_reg_we_check, en_i high with oh_i equal to zero shall remain legal and must not raise err_o in the same cycle.",
            "key_signals": ["clk_i", "rst_ni", "oh_i", "en_i", "err_o"],
            "golden_sva": {
                "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) ((oh_i == 4'b0000) && ($past(oh_i) == 4'b0000) && en_i && $past(en_i)) |-> !err_o);",
                "expected_behavior": "A masked write-enable checker must allow the enabled all-zero vector without raising a false error.",
                "temporal_type": "same-cycle combinational legality check",
            },
            "loose_negative_controls": _controls(
                {
                    "name": "multihot_only",
                    "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) (((oh_i == 4'b0011) || (oh_i == 4'b0101) || (oh_i == 4'b0110) || (oh_i == 4'b0111) || (oh_i == 4'b1001) || (oh_i == 4'b1010) || (oh_i == 4'b1011) || (oh_i == 4'b1100) || (oh_i == 4'b1101) || (oh_i == 4'b1110) || (oh_i == 4'b1111)) |-> err_o);",
                    "why_it_should_miss": "It constrains only clearly illegal multihot cases and says nothing about a false positive on the enabled zero-hot corner.",
                },
                {
                    "name": "disabled_vector_only",
                    "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) (!en_i && (oh_i == 4'b0100) && ($past(oh_i) == 4'b0100) && !$past(en_i)) |-> err_o);",
                    "why_it_should_miss": "The mutation breaks the enabled zero-hot legality corner, not the disabled nonzero vector check.",
                },
            ),
            "hard_case_rationale": "This is a negative-correctness case: broad assertions about obviously illegal write-enable patterns still pass, but only an exact enabled-zero legality check exposes the false positive.",
            "overfit_lure": "",
            "stimulus_notes": "Hold en_i high while driving oh_i at zero for multiple sampled cycles. Held-out should surround the zero-hot window with legal onehot activity so the false-positive corner is isolated.",
        },
        {
            "name": "case108_prim_regwe_addr_check_false_positive",
            "source_project": "opentitan",
            "source_module": "prim_reg_we_check",
            "source_files": [
                "hw/ip/prim/rtl/prim_util_pkg.sv",
                "hw/ip/prim_generic/rtl/prim_buf.sv",
                "hw/ip/prim/rtl/prim_onehot_check.sv",
                "hw/ip/prim/rtl/prim_reg_we_check.sv",
            ],
            "top_file": "hw/ip/prim/rtl/prim_reg_we_check.sv",
            "mutation_edits": [
                {
                    "search": "    .AddrCheck(0),\n",
                    "replace": "    .AddrCheck(1),\n",
                }
            ],
            "bug_class": "combination_same_cycle",
            "bug_family": "write_enable_position_legality",
            "bug_type": "legal nonzero write-enable spuriously fails an address-style check",
            "spec": "For prim_reg_we_check, a legal onehot write-enable vector with en_i high shall not raise err_o even when the hot bit is not bit 0.",
            "key_signals": ["clk_i", "rst_ni", "oh_i", "en_i", "err_o"],
            "golden_sva": {
                "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) ((oh_i == 4'b0010) && ($past(oh_i) == 4'b0010) && en_i && $past(en_i)) |-> !err_o);",
                "expected_behavior": "A valid onehot write-enable on bit 1 must remain legal and must not trigger a spurious checker error.",
                "temporal_type": "same-cycle combinational legality check",
            },
            "loose_negative_controls": _controls(
                {
                    "name": "zero_when_enabled_ok",
                    "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) ((oh_i == 4'b0000) && en_i) |-> !err_o);",
                    "why_it_should_miss": "The bug hits legal nonzero write enables, not the enabled zero-hot corner.",
                },
                {
                    "name": "multihot_must_error",
                    "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) (((oh_i == 4'b0011) || (oh_i == 4'b1010) || (oh_i == 4'b1100)) && en_i) |-> err_o);",
                    "why_it_should_miss": "The mutation preserves obviously illegal multihot rejection and only breaks legal nonzero onehot requests.",
                },
            ),
            "hard_case_rationale": "This is another negative-correctness case: broad assertions about illegal write-enable shapes still pass, while a precise legal-bit-position check is needed to catch the false positive.",
            "overfit_lure": "",
            "stimulus_notes": "Drive a stable legal onehot on bit 1 and later on bit 2 while en_i stays high. Held-out should use a different legal onehot position than the primary trace.",
        },
        {
            "name": "case109_prim_onehot_legal_request_false_positive",
            "source_project": "opentitan",
            "source_module": "prim_onehot_check",
            "source_files": [
                "hw/ip/prim/rtl/prim_onehot_check.sv",
            ],
            "top_file": "hw/ip/prim/rtl/prim_onehot_check.sv",
            "mutation_edits": [
                {
                    "search": "      assign enable_err = or_tree[0] ^ en_i;\n",
                    "replace": "      assign enable_err = en_i && or_tree[0];\n",
                }
            ],
            "bug_class": "combination_same_cycle",
            "bug_family": "enable_consistency_false_positive",
            "bug_type": "legal enabled onehot request spuriously raises enable mismatch error",
            "spec": "With exactly one bit of oh_i high, matching addr_i, and en_i high, err_o shall remain low in the same cycle.",
            "key_signals": ["clk_i", "rst_ni", "oh_i", "addr_i", "en_i", "err_o"],
            "golden_sva": {
                "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) ((oh_i == 4'b0010) && ($past(oh_i) == 4'b0010) && (addr_i == 2'd1) && ($past(addr_i) == 2'd1) && en_i && $past(en_i)) |-> !err_o);",
                "expected_behavior": "A legal onehot/address match under enable must not trip the enable-consistency checker.",
                "temporal_type": "same-cycle combinational legality check",
            },
            "loose_negative_controls": _controls(
                {
                    "name": "illegal_must_error",
                    "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) ((((oh_i == 4'b0100) && (addr_i == 2'd0)) || ((oh_i == 4'b1000) && (addr_i == 2'd1))) && en_i) |-> err_o);",
                    "why_it_should_miss": "The mutation still flags obviously illegal address mismatches; it only creates a false positive on a legal request.",
                },
                {
                    "name": "zero_enabled_only",
                    "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) ((oh_i == 4'b0000) && en_i) |-> err_o || !err_o);",
                    "why_it_should_miss": "It says nothing about whether a legal active onehot request incorrectly raises err_o.",
                },
            ),
            "hard_case_rationale": "This is a clean false-positive case: broad assertions about illegal inputs or zero-hot behavior still pass, while only an exact legal-request check catches the regression.",
            "overfit_lure": "",
            "stimulus_notes": "Drive stable legal onehot/address matches while en_i stays high. Held-out should use a different legal requester/address pair than the primary trace.",
        },
        {
            "name": "case110_prim_intr_event_overwrite",
            "source_project": "opentitan",
            "source_module": "prim_intr_hw",
            "source_files": [
                "hw/ip/prim/rtl/prim_intr_hw.sv",
            ],
            "top_file": "hw/ip/prim/rtl/prim_intr_hw.sv",
            "mutation_edits": [
                {
                    "search": "    assign status = reg2hw_intr_state_q_i ;\n",
                    "replace": "    assign status = new_event;\n",
                }
            ],
            "bug_class": "temporal_cross_cycle",
            "bug_family": "event_state_accumulation",
            "bug_type": "event state overwrite instead of hold-until-clear",
            "spec": "For Event interrupts, once a new event sets the interrupt state, the state shall remain set across subsequent cycles until software clears it.",
            "key_signals": ["clk_i", "rst_ni", "event_intr_i", "reg2hw_intr_enable_q_i", "reg2hw_intr_test_q_i", "reg2hw_intr_test_qe_i", "reg2hw_intr_state_q_i", "hw2reg_intr_state_de_o", "hw2reg_intr_state_d_o", "intr_o"],
            "golden_sva": {
                "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) ($past(reg2hw_intr_state_q_i) && reg2hw_intr_state_q_i && reg2hw_intr_enable_q_i) |-> intr_o);",
                "expected_behavior": "Once event state is latched and remains high, the enabled interrupt output must stay asserted on the next sampled cycle.",
                "temporal_type": "cross-cycle latched-visibility check",
            },
            "loose_negative_controls": _controls(
                {
                    "name": "state_update_flag_matches_data",
                    "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) hw2reg_intr_state_de_o |-> hw2reg_intr_state_d_o);",
                    "why_it_should_miss": "It only checks that the CSR update path drives a high state when the update flag is asserted, not that the enabled interrupt remains visible afterward.",
                },
                {
                    "name": "masked_interrupt_low",
                    "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) (!reg2hw_intr_enable_q_i) |-> !intr_o);",
                    "why_it_should_miss": "The bug is about losing a latched enabled interrupt, not masked behavior.",
                },
            ),
            "hard_case_rationale": "This is exactly the kind of hold-state bug that vague 'event causes interrupt' assertions miss. The state is set once, then silently forgotten.",
            "overfit_lure": "",
            "stimulus_notes": "Model the CSR state feedback in tb, set an event, idle without clearing, and confirm state persistence. Held-out should insert a test pulse before the persistent hold check.",
        },
        {
            "name": "case111_prim_intr_output_or_mask",
            "source_project": "opentitan",
            "source_module": "prim_intr_hw",
            "source_files": [
                "hw/ip/prim/rtl/prim_intr_hw.sv",
            ],
            "top_file": "hw/ip/prim/rtl/prim_intr_hw.sv",
            "mutation_edits": [
                {
                    "search": "        intr_o <= status & reg2hw_intr_enable_q_i;\n",
                    "replace": "        intr_o <= status | reg2hw_intr_enable_q_i;\n",
                }
            ],
            "bug_class": "combination_same_cycle",
            "bug_family": "interrupt_masking",
            "bug_type": "interrupt enable mask turned into OR",
            "spec": "The outgoing interrupt shall assert only when both the interrupt status and enable are high.",
            "key_signals": ["clk_i", "rst_ni", "event_intr_i", "reg2hw_intr_enable_q_i", "reg2hw_intr_state_q_i", "intr_o"],
            "golden_sva": {
                "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) (!reg2hw_intr_enable_q_i && !$past(reg2hw_intr_enable_q_i) && reg2hw_intr_state_q_i && $past(reg2hw_intr_state_q_i)) |-> !intr_o);",
                "expected_behavior": "Masking the interrupt must suppress intr_o regardless of stored status.",
                "temporal_type": "same-cycle masked-output check",
            },
            "loose_negative_controls": _controls(
                {
                    "name": "event_implies_event_detect",
                    "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) event_intr_i |-> hw2reg_intr_state_de_o);",
                    "why_it_should_miss": "It ignores the mask/output relation entirely.",
                },
                {
                    "name": "status_can_raise_interrupt",
                    "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) (reg2hw_intr_enable_q_i && $past(reg2hw_intr_enable_q_i) && reg2hw_intr_state_q_i && $past(reg2hw_intr_state_q_i)) |-> intr_o);",
                    "why_it_should_miss": "It checks only the enabled visibility case and ignores the masked-state corner where the OR bug leaks through.",
                },
            ),
            "hard_case_rationale": "The internal event machinery can still look healthy while the externally visible mask logic is wrong.",
            "overfit_lure": "",
            "stimulus_notes": "Keep reg2hw_intr_state_q_i high while toggling enable. Held-out should build status via event feedback first, then mask it.",
        },
        {
            "name": "case112_prim_intr_test_pulse_dropped",
            "source_project": "opentitan",
            "source_module": "prim_intr_hw",
            "source_files": [
                "hw/ip/prim/rtl/prim_intr_hw.sv",
            ],
            "top_file": "hw/ip/prim/rtl/prim_intr_hw.sv",
            "mutation_edits": [
                {
                    "search": "      else if (reg2hw_intr_test_qe_i) test_q <= reg2hw_intr_test_q_i;\n",
                    "replace": "      else if (reg2hw_intr_test_qe_i) test_q <= '0;\n",
                }
            ],
            "bug_class": "temporal_cross_cycle",
            "bug_family": "test_pulse_capture",
            "bug_type": "interrupt test write pulse is lost",
            "spec": "In Status mode, a software test pulse written through reg2hw_intr_test_qe_i shall be captured and reflected in the stored test_q state on the next cycle.",
            "key_signals": ["clk_i", "rst_ni", "event_intr_i", "reg2hw_intr_test_q_i", "reg2hw_intr_test_qe_i", "reg2hw_intr_enable_q_i", "hw2reg_intr_state_d_o", "intr_o"],
            "golden_sva": {
                "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) (reg2hw_intr_test_qe_i && $past(reg2hw_intr_test_qe_i) && reg2hw_intr_test_q_i && $past(reg2hw_intr_test_q_i) && reg2hw_intr_enable_q_i && $past(reg2hw_intr_enable_q_i)) |-> hw2reg_intr_state_d_o);",
                "expected_behavior": "A test write must drive the next-state interrupt bit high immediately so the pulse is captured on the following cycle.",
                "temporal_type": "next-state capture check",
            },
            "loose_negative_controls": _controls(
                {
                    "name": "event_path_only",
                    "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) event_intr_i |-> intr_o || !intr_o);",
                    "why_it_should_miss": "It ignores the software-injected test path completely.",
                },
                {
                    "name": "qe_seen",
                    "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) reg2hw_intr_test_qe_i |-> reg2hw_intr_test_qe_i);",
                    "why_it_should_miss": "It is vacuous and does not check the captured effect.",
                },
            ),
            "hard_case_rationale": "The test path is easy to overlook if assertions focus only on hardware events.",
            "overfit_lure": "",
            "stimulus_notes": "Instantiate Status mode, enable the interrupt, pulse reg2hw_intr_test_qe_i for one cycle, and watch the next-cycle output. Held-out should combine a test pulse with inactive event_intr_i.",
        },
        {
            "name": "case113_prim_edge_posedge_misdecoded",
            "source_project": "opentitan",
            "source_module": "prim_edge_detector",
            "source_files": [
                "hw/ip/prim_generic/rtl/prim_flop.sv",
                "hw/ip/prim_generic/rtl/prim_flop_2sync.sv",
                "hw/ip/prim/rtl/prim_edge_detector.sv",
            ],
            "top_file": "hw/ip/prim/rtl/prim_edge_detector.sv",
            "mutation_edits": [
                {
                    "search": "  assign q_posedge_pulse_o = q_sync_d & ~q_sync_q;\n",
                    "replace": "  assign q_posedge_pulse_o = ~q_sync_d & q_sync_q;\n",
                }
            ],
            "bug_class": "temporal_cross_cycle",
            "bug_family": "edge_direction",
            "bug_type": "posedge output decodes negedge",
            "spec": "q_posedge_pulse_o shall pulse for exactly the sampled 0->1 transition and not for 1->0 transitions.",
            "key_signals": ["clk_i", "rst_ni", "d_i", "q_sync_o", "q_posedge_pulse_o", "q_negedge_pulse_o"],
            "golden_sva": {
                "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) (!$past(q_sync_o) && q_sync_o) |-> q_posedge_pulse_o);",
                "expected_behavior": "A sampled rising input edge must create a posedge pulse rather than a negedge pulse.",
                "temporal_type": "cross-cycle edge relation",
            },
            "loose_negative_controls": _controls(
                {
                    "name": "some_event_on_change",
                    "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) (d_i != q_sync_o) |-> (q_posedge_pulse_o || q_negedge_pulse_o));",
                    "why_it_should_miss": "The buggy design still produces an event pulse, just on the wrong output.",
                },
                {
                    "name": "pulse_is_onehot",
                    "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) !(q_posedge_pulse_o && q_negedge_pulse_o));",
                    "why_it_should_miss": "Wrong polarity can still satisfy one-hot pulse exclusivity.",
                },
            ),
            "hard_case_rationale": "A broad 'signal changes cause a pulse' assertion is too loose; only exact edge polarity catches this mutation.",
            "overfit_lure": "",
            "stimulus_notes": "Use EnSync=0 in wrapper and toggle d_i 0->1 and 1->0 on separate cycles. Held-out should repeat with longer high/low runs between edges.",
        },
        {
            "name": "case114_prim_edge_negedge_misdecoded",
            "source_project": "opentitan",
            "source_module": "prim_edge_detector",
            "source_files": [
                "hw/ip/prim_generic/rtl/prim_flop.sv",
                "hw/ip/prim_generic/rtl/prim_flop_2sync.sv",
                "hw/ip/prim/rtl/prim_edge_detector.sv",
            ],
            "top_file": "hw/ip/prim/rtl/prim_edge_detector.sv",
            "mutation_edits": [
                {
                    "search": "  assign q_negedge_pulse_o = ~q_sync_d & q_sync_q;\n",
                    "replace": "  assign q_negedge_pulse_o = q_sync_d & ~q_sync_q;\n",
                }
            ],
            "bug_class": "temporal_cross_cycle",
            "bug_family": "edge_direction",
            "bug_type": "negedge output decodes posedge",
            "spec": "q_negedge_pulse_o shall pulse for exactly the sampled 1->0 transition and not for 0->1 transitions.",
            "key_signals": ["clk_i", "rst_ni", "d_i", "q_sync_o", "q_posedge_pulse_o", "q_negedge_pulse_o"],
            "golden_sva": {
                "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) ($past(q_sync_o) && !q_sync_o) |-> q_negedge_pulse_o);",
                "expected_behavior": "A sampled falling input edge must create a negedge pulse rather than a posedge pulse.",
                "temporal_type": "cross-cycle edge relation",
            },
            "loose_negative_controls": _controls(
                {
                    "name": "event_exists",
                    "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) (d_i != q_sync_o) |-> (q_posedge_pulse_o || q_negedge_pulse_o));",
                    "why_it_should_miss": "It ignores which edge output is supposed to fire.",
                },
                {
                    "name": "stable_no_pulse",
                    "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) (d_i == q_sync_o) |-> !(q_posedge_pulse_o || q_negedge_pulse_o));",
                    "why_it_should_miss": "The bug occurs only on transitions, not on stable cycles.",
                },
            ),
            "hard_case_rationale": "Like the posedge case, this forces exact polarity rather than generic 'edge activity' checking.",
            "overfit_lure": "",
            "stimulus_notes": "Toggle d_i through both rising and falling transitions with clean holds in between. Held-out should use a different ordering of edges.",
        },
        {
            "name": "case115_prim_edge_both_edges_collapsed",
            "source_project": "opentitan",
            "source_module": "prim_edge_detector",
            "source_files": [
                "hw/ip/prim_generic/rtl/prim_flop.sv",
                "hw/ip/prim_generic/rtl/prim_flop_2sync.sv",
                "hw/ip/prim/rtl/prim_edge_detector.sv",
            ],
            "top_file": "hw/ip/prim/rtl/prim_edge_detector.sv",
            "mutation_edits": [
                {
                    "search": "  assign q_posedge_pulse_o = q_sync_d & ~q_sync_q;\n",
                    "replace": "  assign q_posedge_pulse_o = q_sync_d ^ q_sync_q;\n",
                }
            ],
            "bug_class": "temporal_cross_cycle",
            "bug_family": "edge_direction",
            "bug_type": "posedge output fires on both edges",
            "spec": "q_posedge_pulse_o shall remain low on falling edges and assert only on rising edges.",
            "key_signals": ["clk_i", "rst_ni", "d_i", "q_sync_o", "q_posedge_pulse_o", "q_negedge_pulse_o"],
            "golden_sva": {
                "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) ($past(q_sync_o) && !q_sync_o) |-> !q_posedge_pulse_o);",
                "expected_behavior": "A falling edge must not leak into the posedge pulse output.",
                "temporal_type": "cross-cycle edge suppression check",
            },
            "loose_negative_controls": _controls(
                {
                    "name": "pulse_occurs_on_rise",
                    "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) (!q_sync_o && d_i) |-> q_posedge_pulse_o);",
                    "why_it_should_miss": "The buggy implementation still pulses on rises; the problem is the extra pulses on falls.",
                },
                {
                    "name": "negedge_output_correct",
                    "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) (q_sync_o && !d_i) |-> q_negedge_pulse_o);",
                    "why_it_should_miss": "The negedge output can stay correct while the posedge output spuriously fires too.",
                },
            ),
            "hard_case_rationale": "This is a good 'conservative assertion misses the false positives' case: one can verify positive behavior and still miss illegal extra pulses.",
            "overfit_lure": "",
            "stimulus_notes": "Include at least one clean falling edge where only q_negedge_pulse_o should assert. Held-out should vary the time spent high before falling.",
        },
        {
            "name": "case116_prim_filter_late_accept",
            "source_project": "opentitan",
            "source_module": "prim_filter",
            "source_files": [
                "hw/ip/prim_generic/rtl/prim_flop.sv",
                "hw/ip/prim_generic/rtl/prim_flop_2sync.sv",
                "hw/ip/prim/rtl/prim_filter.sv",
            ],
            "top_file": "hw/ip/prim/rtl/prim_filter.sv",
              "mutation_edits": [
                  {
                      "search": "      stored_value_q <= filter_synced;\n",
                      "replace": "      stored_value_q <= stored_vector_q[Cycles-1];\n",
                  }
              ],
              "bug_class": "temporal_cross_cycle",
              "bug_family": "filter_threshold",
              "bug_type": "filtered output switches one cycle late",
              "spec": "With filtering enabled, filter_o shall adopt a new stable input at the exact acceptance boundary, not one sampled cycle later.",
              "key_signals": ["clk_i", "rst_ni", "enable_i", "filter_i", "filter_o", "accept_boundary_dbg"],
                  "golden_sva": {
                      "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) accept_boundary_dbg |-> (filter_o == filter_i));",
                      "expected_behavior": "Whenever the filter reaches its acceptance boundary while enabled, the sampled output must already equal the new stable input on that same cycle.",
                      "temporal_type": "multi-cycle exact-length threshold check",
                  },
            "loose_negative_controls": _controls(
                {
                    "name": "eventual_switch",
                    "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) (enable_i && filter_i) |-> (filter_o || $past(filter_o)));",
                    "why_it_should_miss": "It allows the output to lag by an unspecified amount.",
                },
                {
                    "name": "steady_input_implies_stable_output",
                    "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) (!enable_i) |-> (filter_o == filter_i));",
                    "why_it_should_miss": "The bug occurs only while enabled and at the exact threshold boundary.",
                },
            ),
            "hard_case_rationale": "This is precisely the kind of cross-cycle boundary condition that vague filtering assertions under-specify.",
            "overfit_lure": "Use Cycles=3 with trace runs like 000111 so trace methods see tempting literal streaks.",
            "stimulus_notes": "With Cycles=2, drive the new value from a negedge so the second agreeing enabled posedge is the exact acceptance boundary. Held-out should first establish the opposite stored polarity, then test the same two-sample boundary in reverse.",
        },
        {
            "name": "case117_prim_filter_bypass_stale",
            "source_project": "opentitan",
            "source_module": "prim_filter",
            "source_files": [
                "hw/ip/prim_generic/rtl/prim_flop.sv",
                "hw/ip/prim_generic/rtl/prim_flop_2sync.sv",
                "hw/ip/prim/rtl/prim_filter.sv",
            ],
            "top_file": "hw/ip/prim/rtl/prim_filter.sv",
            "mutation_edits": [
                {
                    "search": "  assign filter_o = enable_i ? stored_value_q : filter_synced;\n",
                    "replace": "  assign filter_o = stored_value_q;\n",
                }
            ],
            "bug_class": "temporal_cross_cycle",
            "bug_family": "filter_bypass_control",
            "bug_type": "disabled bypass returns stale filtered state",
            "spec": "When enable_i is low, filter_o shall immediately bypass to the current input rather than the stored filtered state.",
            "key_signals": ["clk_i", "rst_ni", "enable_i", "filter_i", "filter_o"],
                "golden_sva": {
                    "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) (!enable_i && $past(enable_i) && (filter_i != $past(filter_i)) && ($past(filter_o) == $past(filter_i))) |-> (filter_o == filter_i));",
                    "expected_behavior": "On the first disabled sampled cycle after a previously tracked value is established, the bypassed output must match the live input immediately.",
                    "temporal_type": "enable-to-bypass transition check",
                },
            "loose_negative_controls": _controls(
                  {
                      "name": "enabled_threshold_only",
                      "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) (enable_i && filter_o) |-> filter_i);",
                      "why_it_should_miss": "It only constrains cycles where the enabled path is already outputting high, so it ignores the disabled bypass edge where this bug lives.",
                  },
                {
                    "name": "stored_value_eventual_match",
                    "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) filter_o |-> filter_i || $past(filter_i));",
                    "why_it_should_miss": "It allows stale filtered output to look acceptable.",
                },
            ),
            "hard_case_rationale": "This is not a basic functionality failure; the filter still behaves plausibly while enabled. The bug hides in the exact bypass semantics.",
            "overfit_lure": "",
            "stimulus_notes": "Prime the stored value while enabled, then disable from a negedge and flip filter_i so the first disabled sampled cycle reveals stale-vs-live bypass behavior. Held-out should use the opposite stored polarity.",
        },
        {
            "name": "case118_prim_filter_ctr_early_accept",
            "source_project": "opentitan",
            "source_module": "prim_filter_ctr",
            "source_files": [
                "hw/ip/prim_generic/rtl/prim_flop.sv",
                "hw/ip/prim_generic/rtl/prim_flop_2sync.sv",
                "hw/ip/prim/rtl/prim_filter_ctr.sv",
            ],
            "top_file": "hw/ip/prim/rtl/prim_filter_ctr.sv",
            "mutation_edits": [
                {
                    "search": "  assign update_stored_value = (diff_ctr_d == thresh_i);\n",
                    "replace": "  assign update_stored_value = (diff_ctr_d == (thresh_i - 1'b1));\n",
                }
            ],
            "bug_class": "temporal_cross_cycle",
            "bug_family": "filter_threshold",
            "bug_type": "counter-based filter accepts one cycle early",
            "spec": "With filtering enabled, filter_o shall not switch until thresh_i consecutive agreeing samples have been observed.",
            "key_signals": ["clk_i", "rst_ni", "enable_i", "filter_i", "thresh_i", "filter_o", "pre_accept_hold_dbg"],
            "golden_sva": {
                "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) pre_accept_hold_dbg |-> !filter_o);",
                "expected_behavior": "Whenever the counter-based filter is still in its pre-accept hold window, the filtered output must remain at the old value rather than switching early.",
                "temporal_type": "cross-cycle minimum-hold threshold check",
            },
            "loose_negative_controls": _controls(
                {
                    "name": "eventual_accept",
                    "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) (enable_i && filter_i) |-> (filter_o || !$past(filter_o)));",
                    "why_it_should_miss": "It allows the switch to happen too soon.",
                },
                {
                    "name": "disabled_bypass_only",
                    "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) (!enable_i) |-> (filter_o == filter_i));",
                    "why_it_should_miss": "It says nothing about the threshold timing while enabled.",
                },
            ),
            "hard_case_rationale": "An 'eventually filters the input' assertion is exactly the wrong abstraction here; the boundary cycle matters.",
            "overfit_lure": "Use thresh_i values like 2 and 3 in primary traces to tempt constant pinning.",
            "stimulus_notes": "Start from low, drive high for one cycle less than threshold and confirm no switch, then hit threshold. Held-out should exercise a different threshold literal.",
        },
        {
            "name": "case119_prim_filter_ctr_late_accept",
            "source_project": "opentitan",
            "source_module": "prim_filter_ctr",
            "source_files": [
                "hw/ip/prim_generic/rtl/prim_flop.sv",
                "hw/ip/prim_generic/rtl/prim_flop_2sync.sv",
                "hw/ip/prim/rtl/prim_filter_ctr.sv",
            ],
            "top_file": "hw/ip/prim/rtl/prim_filter_ctr.sv",
            "mutation_edits": [
                {
                    "search": "  assign update_stored_value = (diff_ctr_d == thresh_i);\n",
                    "replace": "  assign update_stored_value = (diff_ctr_q == thresh_i);\n",
                }
            ],
            "bug_class": "temporal_cross_cycle",
            "bug_family": "filter_threshold",
            "bug_type": "counter-based filter accepts one cycle late",
            "spec": "With filtering enabled, filter_o shall switch by the exact threshold cycle rather than lagging by one extra sample.",
            "key_signals": ["clk_i", "rst_ni", "enable_i", "filter_i", "thresh_i", "filter_o", "accept_boundary_dbg"],
            "golden_sva": {
                "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) accept_boundary_dbg |-> (filter_o == filter_i));",
                "expected_behavior": "At the exact threshold boundary, the filtered output must already have switched to the newly accepted input value.",
                "temporal_type": "multi-cycle exact-length threshold check",
            },
            "loose_negative_controls": _controls(
                {
                    "name": "two_or_more_highs_eventually_high",
                    "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) (enable_i && filter_i) |-> (filter_o || $past(filter_o)));",
                    "why_it_should_miss": "It permits an unspecified extra cycle of latency.",
                },
                {
                    "name": "no_glitch_when_disabled",
                    "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) (!enable_i) |-> (filter_o == filter_i));",
                    "why_it_should_miss": "The bug is in enabled threshold timing, not in bypass mode.",
                },
            ),
            "hard_case_rationale": "This is a clean exact-threshold bug with a natural trace-summary overfit lure around the threshold literal.",
            "overfit_lure": "Use primary trace threshold 2 and held-out threshold 3 so literal hard-coding can be detected.",
            "stimulus_notes": "Run one case with thresh_i=2 in the prompt trace and another hidden held-out check with thresh_i=3.",
        },
        {
            "name": "case120_prim_filter_ctr_bypass_stale",
            "source_project": "opentitan",
            "source_module": "prim_filter_ctr",
            "source_files": [
                "hw/ip/prim_generic/rtl/prim_flop.sv",
                "hw/ip/prim_generic/rtl/prim_flop_2sync.sv",
                "hw/ip/prim/rtl/prim_filter_ctr.sv",
            ],
            "top_file": "hw/ip/prim/rtl/prim_filter_ctr.sv",
            "mutation_edits": [
                {
                    "search": "  assign filter_o = enable_i ? stored_value_q : filter_synced;\n",
                    "replace": "  assign filter_o = stored_value_q;\n",
                }
            ],
            "bug_class": "temporal_cross_cycle",
            "bug_family": "filter_bypass_control",
            "bug_type": "counter-based filter bypass returns stale state",
            "spec": "When enable_i is low, filter_o shall bypass to the current input rather than stay at the previously stored filtered value.",
            "key_signals": ["clk_i", "rst_ni", "enable_i", "filter_i", "thresh_i", "filter_o"],
                "golden_sva": {
                    "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) (!enable_i && $past(enable_i) && (filter_i != $past(filter_i)) && ($past(filter_o) == $past(filter_i))) |-> (filter_o == filter_i));",
                    "expected_behavior": "On the first disabled sampled cycle after a previously tracked value is established, the counter-based bypass must match the live input immediately.",
                    "temporal_type": "enable-to-bypass transition check",
                },
            "loose_negative_controls": _controls(
                  {
                      "name": "enabled_eventual_accept",
                      "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) (enable_i && filter_o) |-> filter_i);",
                      "why_it_should_miss": "It checks only cycles where the enabled counter-based path is already driving high and says nothing about the disabled bypass edge.",
                  },
                {
                    "name": "threshold_nonzero",
                    "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) enable_i |-> (thresh_i != '0 || thresh_i == '0));",
                    "why_it_should_miss": "It is effectively unconstrained and misses the bypass bug entirely.",
                },
            ),
            "hard_case_rationale": "Like the shift-register filter bypass case, this bug hides in control gating rather than headline functionality.",
            "overfit_lure": "",
            "stimulus_notes": "Prime the counter-based stored state while enabled, then disable from a negedge and flip filter_i so the first disabled sampled cycle reveals stale-vs-live bypass behavior. Held-out should reverse the stored polarity.",
        },
        {
            "name": "case121_prim_intr_test_qe_ignored",
            "source_project": "opentitan",
            "source_module": "prim_intr_hw",
            "source_files": [
                "hw/ip/prim/rtl/prim_intr_hw.sv",
            ],
            "top_file": "hw/ip/prim/rtl/prim_intr_hw.sv",
            "mutation_edits": [
                {
                    "search": "               (({Width{reg2hw_intr_test_qe_i}} & reg2hw_intr_test_q_i) | event_intr_i);\n",
                    "replace": "               (reg2hw_intr_test_q_i | event_intr_i);\n",
                }
            ],
            "bug_class": "combination_same_cycle",
            "bug_family": "event_test_gate",
            "bug_type": "event-mode test data is consumed even when the qe gate is low",
            "spec": "In Event mode, reg2hw_intr_test_q_i shall have no effect unless reg2hw_intr_test_qe_i is asserted in the same cycle.",
            "key_signals": ["clk_i", "rst_ni", "event_intr_i", "reg2hw_intr_test_q_i", "reg2hw_intr_test_qe_i", "reg2hw_intr_state_q_i", "hw2reg_intr_state_de_o", "hw2reg_intr_state_d_o"],
            "golden_sva": {
                "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) (!event_intr_i && reg2hw_intr_test_q_i && !reg2hw_intr_test_qe_i && !reg2hw_intr_state_q_i) |-> (!hw2reg_intr_state_de_o && !hw2reg_intr_state_d_o));",
                "expected_behavior": "A stale test-data bit with qe low must not request a state update or inject a synthetic event.",
                "temporal_type": "same-cycle control-gating check",
            },
            "loose_negative_controls": _controls(
                {
                    "name": "real_event_updates_state",
                    "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) event_intr_i |-> hw2reg_intr_state_de_o);",
                    "why_it_should_miss": "Real events still propagate correctly; the bug hides only in the qe-low synthetic-event corner.",
                },
                {
                    "name": "qe_high_allows_test_event",
                    "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) (reg2hw_intr_test_qe_i && reg2hw_intr_test_q_i) |-> hw2reg_intr_state_de_o);",
                    "why_it_should_miss": "It constrains only the legitimate qe-high path and says nothing about stale test data leaking through qe-low.",
                },
            ),
            "hard_case_rationale": "This is a classic control-gating hard case: broad assertions about event visibility or test functionality can all pass while qe-low leakage quietly violates the contract.",
            "overfit_lure": "Primary traces should pin the tempting literal corner test_q=1, qe=0, event=0 so trace-heavy methods can overfit the obvious constant pattern.",
            "stimulus_notes": "Hold reg2hw_intr_test_q_i high while keeping reg2hw_intr_test_qe_i low and event_intr_i low, then sample hw2reg_intr_state_de_o/hw2reg_intr_state_d_o. Held-out should inject the same qe-low leak after an earlier legitimate event cycle.",
        },
        {
            "name": "case122_prim_filter_ctr_streak_reset_ignored",
            "source_project": "opentitan",
            "source_module": "prim_filter_ctr",
            "source_files": [
                "hw/ip/prim_generic/rtl/prim_flop.sv",
                "hw/ip/prim_generic/rtl/prim_flop_2sync.sv",
                "hw/ip/prim/rtl/prim_filter_ctr.sv",
            ],
            "top_file": "hw/ip/prim/rtl/prim_filter_ctr.sv",
            "mutation_edits": [
                {
                    "search": "  assign diff_ctr_d = (filter_synced != filter_q) ? '0       :           // restart\n                      (diff_ctr_q >= thresh_i)    ? thresh_i :           // saturate\n                                                    (diff_ctr_q + 1'b1); // count up\n",
                    "replace": "  assign diff_ctr_d = (filter_synced != filter_q) ? diff_ctr_q :       // stale progress retained\n                      (diff_ctr_q >= thresh_i)    ? thresh_i :           // saturate\n                                                    (diff_ctr_q + 1'b1); // count up\n",
                }
            ],
            "bug_class": "temporal_cross_cycle",
            "bug_family": "filter_counter_reset",
            "bug_type": "counter-based filter keeps stale progress after the candidate polarity flips",
            "spec": "When the candidate polarity flips, the counter-based filter shall discard stale progress from the previous polarity; two samples of the new value are still not enough to switch the output at threshold two.",
            "key_signals": ["clk_i", "rst_ni", "enable_i", "filter_i", "thresh_i", "filter_o", "second_new_sample_dbg"],
            "golden_sva": {
                "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) second_new_sample_dbg |-> (filter_o != filter_i));",
                "expected_behavior": "On the wrapper-observed second sample of a new opposing polarity at threshold two, the output must still hold the old value rather than switching early from stale counter progress.",
                "temporal_type": "observer-guided exact second-sample hold check",
            },
            "loose_negative_controls": _controls(
                {
                    "name": "eventual_accept_after_stability",
                    "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) (enable_i && filter_i && $past(filter_i)) |-> (filter_o || $past(filter_o)));",
                    "why_it_should_miss": "Two consecutive agreeing samples can still work; the bug is specifically that interrupted streaks are not reset.",
                },
                {
                    "name": "disabled_bypass_only",
                    "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) (!enable_i) |-> (filter_o == filter_i));",
                    "why_it_should_miss": "The disabled bypass can stay perfectly correct while the enabled acceptance counter silently carries stale progress across a chatter interruption.",
                },
            ),
            "hard_case_rationale": "This bug hides in exact temporal bookkeeping: the counter state looks plausible, but the module wrongly reuses progress from the previous polarity. Broad 'eventually follows after stability' assertions are too weak to pin down that reset rule.",
            "overfit_lure": "Primary traces should include a tempting 0,1,1 boundary and held-out should mirror it with 1,0,0 so trace-heavy methods can overfit concrete bit runs instead of the polarity-flip rule.",
            "stimulus_notes": "With thresh_i=2, first build stale progress for one polarity, then flip filter_i and provide exactly two samples of the new value. The wrapper exports second_new_sample_dbg on that second sample so the golden can check that filter_o still opposes filter_i. Held-out should mirror the same check in the opposite direction.",
        },
        {
            "name": "case123_prim_edge_sync_output_lag",
            "source_project": "opentitan",
            "source_module": "prim_edge_detector",
            "source_files": [
                "hw/ip/prim_generic/rtl/prim_flop.sv",
                "hw/ip/prim_generic/rtl/prim_flop_2sync.sv",
                "hw/ip/prim/rtl/prim_edge_detector.sv",
            ],
            "top_file": "hw/ip/prim/rtl/prim_edge_detector.sv",
            "mutation_edits": [
                {
                    "search": "  assign q_posedge_pulse_o = q_sync_d & ~q_sync_q;\n",
                    "replace": "  assign q_posedge_pulse_o = q_sync_d;\n",
                }
            ],
            "bug_class": "temporal_cross_cycle",
            "bug_family": "pulse_persistence",
            "bug_type": "posedge pulse stays high beyond the single transition cycle",
            "spec": "q_posedge_pulse_o shall assert only on the sampled 0->1 transition cycle and must return low on the following stable-high cycle.",
            "key_signals": ["clk_i", "rst_ni", "d_i", "q_sync_o", "q_posedge_pulse_o", "q_negedge_pulse_o"],
            "golden_sva": {
                "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) ($past(q_sync_o) && q_sync_o) |-> !q_posedge_pulse_o);",
                "expected_behavior": "Once the input is already stably high across consecutive sampled cycles, the posedge pulse must have disappeared.",
                "temporal_type": "cross-cycle single-cycle pulse width check",
            },
            "loose_negative_controls": _controls(
                {
                    "name": "pulse_occurs_on_rise",
                    "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) (!$past(d_i) && d_i) |-> q_posedge_pulse_o);",
                    "why_it_should_miss": "The buggy design still produces a pulse on a rising edge; the bug is that the pulse incorrectly persists into later stable-high cycles.",
                },
                {
                    "name": "falling_edge_detected",
                    "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) ($past(d_i) && !d_i) |-> q_negedge_pulse_o);",
                    "why_it_should_miss": "The falling-edge output can remain perfectly correct while the posedge pulse width is wrong.",
                },
            ),
            "hard_case_rationale": "This is an exact pulse-width bug. Assertions that only check that a rise causes some pulse miss the illegal persistence on the next stable cycle.",
            "overfit_lure": "",
            "stimulus_notes": "Use EnSync=0 and drive a clean 0->1 rise from a negedge, then hold d_i high for at least one more sampled cycle. Held-out should use a longer high plateau and a later falling edge.",
        },
        {
            "name": "case124_prim_fifo_clear_ignored",
            "source_project": "opentitan",
            "source_module": "prim_fifo_sync_cnt",
            "source_files": [
                "hw/ip/prim/rtl/prim_util_pkg.sv",
                "hw/ip/prim/rtl/prim_fifo_sync_cnt.sv",
            ],
            "top_file": "hw/ip/prim/rtl/prim_fifo_sync_cnt.sv",
            "mutation_edits": [
                {
                    "search": "      end else if (clr_i) begin\n        wptr_wrap_cnt_q <= {WrapPtrW{1'b0}};\n",
                    "replace": "      end else if (1'b0 && clr_i) begin\n        wptr_wrap_cnt_q <= {WrapPtrW{1'b0}};\n",
                },
                {
                    "search": "      end else if (clr_i) begin\n        rptr_wrap_cnt_q <= {WrapPtrW{1'b0}};\n",
                    "replace": "      end else if (1'b0 && clr_i) begin\n        rptr_wrap_cnt_q <= {WrapPtrW{1'b0}};\n",
                },
            ],
            "bug_class": "temporal_cross_cycle",
            "bug_family": "clear_semantics",
            "bug_type": "clear pulse does not reset FIFO pointers",
            "spec": "A clear pulse shall reset the FIFO occupancy and pointers on the next cycle.",
            "key_signals": ["clk_i", "rst_ni", "clr_i", "incr_wptr_i", "incr_rptr_i", "wptr_o", "rptr_o", "full_o", "empty_o", "depth_o"],
            "golden_sva": {
                "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) $past(clr_i) |-> (empty_o && (depth_o == 3'd0) && (wptr_o == 2'd0) && (rptr_o == 2'd0)));",
                "expected_behavior": "On the cycle after a sampled clear pulse, the FIFO-visible occupancy and both pointers must be at the reset state.",
                "temporal_type": "next-cycle clear effect check",
            },
            "loose_negative_controls": _controls(
                {
                    "name": "eventual_empty_after_reads",
                    "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) incr_rptr_i |-> !full_o);",
                    "why_it_should_miss": "Reads can still eventually drain the FIFO without proving clear works.",
                },
                {
                    "name": "reset_path_only",
                    "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) !rst_ni |-> empty_o);",
                    "why_it_should_miss": "It checks asynchronous reset rather than operational clear.",
                },
            ),
            "hard_case_rationale": "The bug hides in an operational control path distinct from reset. Loose FIFO assertions rarely distinguish the two.",
            "overfit_lure": "",
            "stimulus_notes": "Fill the FIFO, pulse clr_i, and sample the next cycle. Held-out should clear from a different occupancy level.",
        },
        {
            "name": "case125_prim_fifo_wrap_late",
            "source_project": "opentitan",
            "source_module": "prim_fifo_sync_cnt",
            "source_files": [
                "hw/ip/prim/rtl/prim_util_pkg.sv",
                "hw/ip/prim/rtl/prim_fifo_sync_cnt.sv",
            ],
            "top_file": "hw/ip/prim/rtl/prim_fifo_sync_cnt.sv",
            "mutation_edits": [
                {
                    "search": "  assign wptr_wrap_set = incr_wptr_i & (wptr_o == PtrW'(Depth-1));\n",
                    "replace": "  assign wptr_wrap_set = incr_wptr_i & (wptr_o == PtrW'(Depth));\n",
                }
            ],
            "bug_class": "temporal_cross_cycle",
            "bug_family": "pointer_wrap",
            "bug_type": "write pointer wraps one cycle late",
            "spec": "When the write pointer is at Depth-1 and a write occurs, the internal write pointer shall wrap on the next cycle rather than stepping to an out-of-range state.",
            "key_signals": ["clk_i", "rst_ni", "clr_i", "incr_wptr_i", "incr_rptr_i", "full_o", "empty_o", "depth_o", "wptr_o"],
            "golden_sva": {
                "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) ($past(full_o) && incr_rptr_i && !$past(clr_i)) |-> (depth_o == 3'd3));",
                "expected_behavior": "Reading one item from a full FIFO must reduce occupancy from 4 to 3 on the next sampled cycle.",
                "temporal_type": "next-cycle post-full read check",
            },
            "loose_negative_controls": _controls(
                {
                    "name": "full_implies_not_empty",
                    "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) full_o |-> !empty_o);",
                    "why_it_should_miss": "The FIFO can still avoid the contradictory full-and-empty state while the post-wrap read depth is corrupted.",
                },
                {
                    "name": "full_eventually_asserts",
                    "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) (depth_o == 3'd3 && incr_wptr_i) |-> full_o || $past(full_o));",
                    "why_it_should_miss": "It does not require the exact pointer wrap relation.",
                },
            ),
            "hard_case_rationale": "Boundary pointer semantics are much tighter than generic occupancy checks.",
            "overfit_lure": "Use visible pointer sequence 0,1,2,3,0 in the primary trace and a different prelude in held-out.",
            "stimulus_notes": "Drive four writes from reset and sample wptr_o at the wrap. Held-out should include a read before the final wrap sequence.",
        },
        {
            "name": "case126_prim_regwe_enable_gap",
            "source_project": "opentitan",
            "source_module": "prim_reg_we_check",
            "source_files": [
                "hw/ip/prim/rtl/prim_util_pkg.sv",
                "hw/ip/prim_generic/rtl/prim_buf.sv",
                "hw/ip/prim/rtl/prim_onehot_check.sv",
                "hw/ip/prim/rtl/prim_reg_we_check.sv",
            ],
            "top_file": "hw/ip/prim/rtl/prim_reg_we_check.sv",
            "mutation_edits": [
                {
                    "search": "    .EnableCheck(1),\n",
                    "replace": "    .EnableCheck(0),\n",
                }
            ],
            "bug_class": "combination_same_cycle",
            "bug_family": "register_write_enable_consistency",
            "bug_type": "write-enable checker ignores enable mismatch",
            "spec": "When en_i is low, any nonzero onehot write-enable vector shall trigger err_o in the same cycle.",
            "key_signals": ["clk_i", "rst_ni", "oh_i", "en_i", "err_o"],
            "golden_sva": {
                "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) (!en_i && !$past(en_i) && (oh_i != 4'b0000) && (oh_i == $past(oh_i))) |-> err_o);",
                "expected_behavior": "A sustained nonzero write-enable vector must be rejected whenever the enable gate is low, regardless of which onehot bit is active.",
                "temporal_type": "same-cycle combinational check",
            },
            "loose_negative_controls": _controls(
                {
                    "name": "multihot_only",
                    "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) (((oh_i == 4'b0011) || (oh_i == 4'b0101) || (oh_i == 4'b0110) || (oh_i == 4'b0111) || (oh_i == 4'b1001) || (oh_i == 4'b1010) || (oh_i == 4'b1011) || (oh_i == 4'b1100) || (oh_i == 4'b1101) || (oh_i == 4'b1110) || (oh_i == 4'b1111)) |-> err_o);",
                    "why_it_should_miss": "A legal onehot vector with en_i low is still illegal for this module but passes this looser check.",
                },
                {
                    "name": "zero_ok_when_disabled",
                    "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) (!en_i && !(|oh_i)) |-> !err_o);",
                    "why_it_should_miss": "It only checks the easy disabled-zero corner.",
                },
            ),
            "hard_case_rationale": "This module is a good same-cycle 'context matters' case: onehot legality alone is not enough; enable gating is part of correctness.",
            "overfit_lure": "",
            "stimulus_notes": "Drive legal onehot oh_i values while toggling en_i low. Held-out should use different bit positions and include an all-zero disabled control sample.",
        },
        {
            "name": "case127_prim_intr_status_test_qe_ignored",
            "source_project": "opentitan",
            "source_module": "prim_intr_hw",
            "source_files": [
                "hw/ip/prim/rtl/prim_intr_hw.sv",
            ],
            "top_file": "hw/ip/prim/rtl/prim_intr_hw.sv",
            "mutation_edits": [
                {
                    "search": "      else if (reg2hw_intr_test_qe_i) test_q <= reg2hw_intr_test_q_i;\n",
                    "replace": "      else if (reg2hw_intr_test_q_i) test_q <= reg2hw_intr_test_q_i;\n",
                }
            ],
            "bug_class": "temporal_cross_cycle",
            "bug_family": "status_test_gate",
            "bug_type": "status-mode test data is latched even when the qe gate is low",
            "spec": "In Status mode, reg2hw_intr_test_q_i shall affect the latched test state only on cycles where reg2hw_intr_test_qe_i is asserted.",
            "key_signals": ["clk_i", "rst_ni", "event_intr_i", "reg2hw_intr_enable_q_i", "reg2hw_intr_test_q_i", "reg2hw_intr_test_qe_i", "intr_o"],
            "golden_sva": {
                "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) (reg2hw_intr_enable_q_i && !event_intr_i && !$past(reg2hw_intr_test_q_i) && reg2hw_intr_test_q_i && !reg2hw_intr_test_qe_i) |=> !intr_o);",
                "expected_behavior": "On the first qe-low rise of test data, the following sampled cycle must still keep intr_o low because that write was not gated in.",
                "temporal_type": "next-cycle first-illegal-test visibility check",
            },
            "loose_negative_controls": _controls(
                {
                    "name": "real_status_event_visible",
                    "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) (event_intr_i && reg2hw_intr_enable_q_i) |=> intr_o);",
                    "why_it_should_miss": "The real event path can remain correct while qe-low test data leaks into the latched status state.",
                },
                {
                    "name": "qe_high_test_visible",
                    "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) (reg2hw_intr_test_qe_i && reg2hw_intr_test_q_i && reg2hw_intr_enable_q_i) |=> intr_o);",
                    "why_it_should_miss": "It only checks the legitimate qe-high software-test path and does not constrain the qe-low leak at all.",
                },
            ),
            "hard_case_rationale": "This is a pure control-lifetime bug. Assertions that only verify normal event behavior or legitimate test writes will miss that qe-low data can still arm the flopped output one cycle later.",
            "overfit_lure": "Primary traces should keep event_intr_i at 0 while holding test_q_i at 1 with qe low so trace-driven methods are tempted to memorize the obvious literal corner.",
            "stimulus_notes": "Keep event_intr_i low, reg2hw_intr_enable_q_i high, and drive reg2hw_intr_test_q_i=1 with reg2hw_intr_test_qe_i=0; the following sampled cycle must still keep intr_o low. Held-out should first exercise a legitimate qe-high test write, clear it, and then re-run the qe-low leak check.",
        },
        {
            "name": "case128_prim_intr_event_mask_stall",
            "source_project": "opentitan",
            "source_module": "prim_intr_hw",
            "source_files": [
                "hw/ip/prim/rtl/prim_intr_hw.sv",
            ],
            "top_file": "hw/ip/prim/rtl/prim_intr_hw.sv",
              "mutation_edits": [
                  {
                      "search": "        intr_o <= status & reg2hw_intr_enable_q_i;\n",
                      "replace": "        intr_o <= hw2reg_intr_state_d_o & reg2hw_intr_enable_q_i;\n",
                  }
              ],
              "bug_class": "temporal_cross_cycle",
              "bug_family": "event_output_state_alignment",
              "bug_type": "flopped interrupt output exposes pending next-state before committed state feedback",
              "spec": "With FlopOutput enabled in Event mode, intr_o shall be derived from the committed interrupt state feedback, not from the speculative next-state in the same event cycle.",
              "key_signals": ["clk_i", "rst_ni", "event_intr_i", "reg2hw_intr_enable_q_i", "reg2hw_intr_state_q_i", "intr_o"],
              "golden_sva": {
                  "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) (event_intr_i && reg2hw_intr_enable_q_i && !reg2hw_intr_state_q_i) |=> !intr_o);",
                  "expected_behavior": "Immediately after a fresh event, the flopped output must still remain low until the committed state feedback has caught up.",
                  "temporal_type": "next-cycle committed-state alignment check",
              },
            "loose_negative_controls": _controls(
                  {
                      "name": "event_updates_state",
                      "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) event_intr_i |-> hw2reg_intr_state_de_o);",
                      "why_it_should_miss": "The state-update side can still behave correctly even if the flopped output reads the wrong source too early.",
                  },
                  {
                      "name": "masked_interrupt_low",
                      "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) (!reg2hw_intr_enable_q_i) |-> !intr_o);",
                      "why_it_should_miss": "The bug occurs while enabled, as an early visible pulse, not as masked suppression.",
                  },
              ),
              "hard_case_rationale": "This is a source-alignment timing bug: broad assertions about eventual interrupt visibility or state update still pass, but an exact committed-state contract catches it.",
              "overfit_lure": "",
              "stimulus_notes": "Keep committed state feedback low, pulse event_intr_i from a negedge, and check that intr_o stays low on the following sampled cycle. Held-out should clear committed state first, then repeat the same check on a later event pulse.",
        },
        {
            "name": "case129_prim_onehot_zero_enabled_suppressed",
            "source_project": "opentitan",
            "source_module": "prim_onehot_check",
            "source_files": [
                "hw/ip/prim/rtl/prim_onehot_check.sv",
            ],
            "top_file": "hw/ip/prim/rtl/prim_onehot_check.sv",
            "mutation_edits": [
                {
                    "search": "      assign enable_err = or_tree[0] ^ en_i;\n",
                    "replace": "      assign enable_err = !en_i && or_tree[0];\n",
                }
            ],
            "bug_class": "combination_same_cycle",
            "bug_family": "enable_consistency",
            "bug_type": "zero-hot while enabled is no longer rejected",
            "spec": "With strict checking enabled, en_i high with oh_i equal to zero shall assert err_o in the same sampled cycle.",
            "key_signals": ["clk_i", "rst_ni", "oh_i", "addr_i", "en_i", "err_o"],
            "golden_sva": {
                "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) (((oh_i == 4'b0000) && ($past(oh_i) == 4'b0000) && en_i && $past(en_i))) |-> err_o);",
                "expected_behavior": "Strict onehot checking must reject the all-zero request vector while enabled.",
                "temporal_type": "same-cycle combinational check",
            },
            "loose_negative_controls": _controls(
                {
                    "name": "request_implies_enable",
                    "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) ((oh_i == 4'b0001) || (oh_i == 4'b0010) || (oh_i == 4'b0100) || (oh_i == 4'b1000)) |-> en_i);",
                    "why_it_should_miss": "It constrains only active-request cases and says nothing about enabled-zero.",
                },
                {
                    "name": "multihot_only",
                    "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) (((oh_i == 4'b0011) || (oh_i == 4'b0101) || (oh_i == 4'b0110) || (oh_i == 4'b0111) || (oh_i == 4'b1001) || (oh_i == 4'b1010) || (oh_i == 4'b1011) || (oh_i == 4'b1100) || (oh_i == 4'b1101) || (oh_i == 4'b1110) || (oh_i == 4'b1111)) |-> err_o);",
                    "why_it_should_miss": "The mutation leaves multihot detection intact and only breaks the strict zero-hot corner.",
                },
            ),
            "hard_case_rationale": "A broad 'onehot or enabled' check can still pass here. The useful assertion has to name the strict zero-hot-while-enabled corner explicitly.",
            "overfit_lure": "Primary trace should include a tempting enabled-zero literal like 4'b0000 between valid onehot patterns.",
            "stimulus_notes": "Drive a legal onehot first, then hold en_i high while forcing oh_i to 4'b0000. Held-out should reuse a different surrounding onehot pattern before the same strict zero-hot corner.",
        },
        {
            "name": "case130_prim_fifo_empty_early",
            "source_project": "opentitan",
            "source_module": "prim_fifo_sync_cnt",
            "source_files": [
                "hw/ip/prim/rtl/prim_util_pkg.sv",
                "hw/ip/prim/rtl/prim_fifo_sync_cnt.sv",
            ],
            "top_file": "hw/ip/prim/rtl/prim_fifo_sync_cnt.sv",
            "mutation_edits": [
                {
                    "search": "  assign empty_o = wptr_wrap_cnt_q == rptr_wrap_cnt_q;\n",
                    "replace": "  assign empty_o = (wptr_wrap_cnt_q == rptr_wrap_cnt_q) || (depth_o == 3'd1);\n",
                }
            ],
            "bug_class": "combination_same_cycle",
            "bug_family": "fifo_boundary_flag",
            "bug_type": "empty asserts one slot early",
            "spec": "empty_o shall remain low while the FIFO still contains exactly one entry.",
            "key_signals": ["clk_i", "rst_ni", "clr_i", "incr_wptr_i", "incr_rptr_i", "full_o", "empty_o", "depth_o"],
            "golden_sva": {
                "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) (depth_o == 3'd1) |-> !empty_o);",
                "expected_behavior": "Single-entry occupancy must not be mistaken for empty.",
                "temporal_type": "same-cycle combinational boundary check",
            },
            "loose_negative_controls": _controls(
                {
                    "name": "no_full_when_empty",
                    "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) empty_o |-> !full_o);",
                    "why_it_should_miss": "The buggy FIFO can still avoid asserting full while empty_o rises too early.",
                },
                {
                    "name": "reads_reduce_depth",
                    "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) incr_rptr_i |-> !full_o);",
                    "why_it_should_miss": "It never checks the exact one-entry boundary where empty_o must stay low.",
                },
            ),
            "hard_case_rationale": "This is the mirror image of the classic empty-late bug: only the exact occupancy-1 boundary distinguishes correct from buggy.",
            "overfit_lure": "The primary trace should visibly walk through depth 2,1,0 so literal-matching methods have a tempting shortcut.",
            "stimulus_notes": "Write entries, drain down to one remaining item, and sample empty_o before the final read. Held-out should revisit the one-entry boundary after a clear pulse and refill.",
        },
        {
            "name": "case131_prim_filter_disabled_bypass_stale_alt",
            "source_project": "opentitan",
            "source_module": "prim_filter",
            "source_files": [
                "hw/ip/prim_generic/rtl/prim_flop.sv",
                "hw/ip/prim_generic/rtl/prim_flop_2sync.sv",
                "hw/ip/prim/rtl/prim_filter.sv",
            ],
            "top_file": "hw/ip/prim/rtl/prim_filter.sv",
            "mutation_edits": [
                {
                    "search": "  assign filter_o = enable_i ? stored_value_q : filter_synced;\n",
                    "replace": "  assign filter_o = stored_value_q;\n",
                }
            ],
            "bug_class": "combination_same_cycle",
            "bug_family": "filter_bypass_control",
            "bug_type": "disabled filter bypass stays on stored state",
            "spec": "When enable_i is low, filter_o shall reflect the live filter_i input immediately rather than the stored filtered value.",
            "key_signals": ["clk_i", "rst_ni", "enable_i", "filter_i", "filter_o"],
                "golden_sva": {
                    "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) (!enable_i && $past(enable_i) && (filter_i != $past(filter_i)) && ($past(filter_o) == $past(filter_i))) |-> (filter_o == filter_i));",
                    "expected_behavior": "On the first disabled sampled cycle after a previously tracked value is established, the bypassed output must follow the live input immediately.",
                    "temporal_type": "enable-to-bypass transition check",
                },
            "loose_negative_controls": _controls(
                  {
                      "name": "enabled_only",
                      "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) (enable_i && filter_o) |-> filter_i);",
                      "why_it_should_miss": "It only checks cycles where the enabled path is already driving high, so it ignores the disabled bypass path entirely.",
                  },
                {
                    "name": "steady_input_eventual_match",
                    "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) (enable_i && filter_i && $past(filter_i)) |-> filter_o);",
                    "why_it_should_miss": "The filtered path can still converge correctly while the disabled bypass path remains stale.",
                },
            ),
            "hard_case_rationale": "This mutation preserves the filtered behavior and only breaks the control-path bypass. Assertions that focus on threshold behavior miss it.",
            "overfit_lure": "",
            "stimulus_notes": "Build up the stored value while enabled, then disable from a negedge and flip filter_i so the first disabled sampled cycle must reflect the live input. Held-out should establish the opposite stored polarity before disabling.",
        },
        {
            "name": "case132_prim_edge_posedge_missing",
            "source_project": "opentitan",
            "source_module": "prim_edge_detector",
            "source_files": [
                "hw/ip/prim_generic/rtl/prim_flop.sv",
                "hw/ip/prim_generic/rtl/prim_flop_2sync.sv",
                "hw/ip/prim/rtl/prim_edge_detector.sv",
            ],
            "top_file": "hw/ip/prim/rtl/prim_edge_detector.sv",
            "mutation_edits": [
                {
                    "search": "  assign q_posedge_pulse_o = q_sync_d & ~q_sync_q;\n",
                    "replace": "  assign q_posedge_pulse_o = 1'b0;\n",
                }
            ],
            "bug_class": "temporal_cross_cycle",
            "bug_family": "edge_presence",
            "bug_type": "posedge pulse is dropped entirely",
            "spec": "A sampled 0->1 transition shall generate a one-cycle pulse on q_posedge_pulse_o.",
            "key_signals": ["clk_i", "rst_ni", "d_i", "q_sync_o", "q_posedge_pulse_o", "q_negedge_pulse_o"],
            "golden_sva": {
                "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) (!$past(q_sync_o) && q_sync_o) |-> q_posedge_pulse_o);",
                "expected_behavior": "Every sampled rising edge must create a visible posedge pulse.",
                "temporal_type": "cross-cycle edge presence check",
            },
            "loose_negative_controls": _controls(
                {
                    "name": "pulse_onehot_only",
                    "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) !(q_posedge_pulse_o && q_negedge_pulse_o));",
                    "why_it_should_miss": "A completely missing posedge pulse still satisfies exclusivity.",
                },
                {
                    "name": "negedge_path_only",
                    "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) ($past(q_sync_o) && !q_sync_o) |-> q_negedge_pulse_o);",
                    "why_it_should_miss": "The falling-edge path can remain correct while the rising-edge pulse disappears.",
                },
            ),
            "hard_case_rationale": "A generic 'there is some pulse activity' statement is too weak; the exact rise-to-pulse contract matters.",
            "overfit_lure": "",
            "stimulus_notes": "Toggle d_i low-to-high between clock edges and sample the next posedge. Held-out should include a longer low dwell before the rise.",
        },
        {
            "name": "case133_prim_edge_negedge_missing",
            "source_project": "opentitan",
            "source_module": "prim_edge_detector",
            "source_files": [
                "hw/ip/prim_generic/rtl/prim_flop.sv",
                "hw/ip/prim_generic/rtl/prim_flop_2sync.sv",
                "hw/ip/prim/rtl/prim_edge_detector.sv",
            ],
            "top_file": "hw/ip/prim/rtl/prim_edge_detector.sv",
            "mutation_edits": [
                {
                    "search": "  assign q_negedge_pulse_o = ~q_sync_d & q_sync_q;\n",
                    "replace": "  assign q_negedge_pulse_o = 1'b0;\n",
                }
            ],
            "bug_class": "temporal_cross_cycle",
            "bug_family": "edge_presence",
            "bug_type": "negedge pulse is dropped entirely",
            "spec": "A sampled 1->0 transition shall generate a one-cycle pulse on q_negedge_pulse_o.",
            "key_signals": ["clk_i", "rst_ni", "d_i", "q_sync_o", "q_posedge_pulse_o", "q_negedge_pulse_o"],
            "golden_sva": {
                "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) ($past(q_sync_o) && !q_sync_o) |-> q_negedge_pulse_o);",
                "expected_behavior": "Every sampled falling edge must create a visible negedge pulse.",
                "temporal_type": "cross-cycle edge presence check",
            },
            "loose_negative_controls": _controls(
                {
                    "name": "pulse_onehot_only",
                    "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) !(q_posedge_pulse_o && q_negedge_pulse_o));",
                    "why_it_should_miss": "A missing negedge pulse still satisfies exclusivity.",
                },
                {
                    "name": "posedge_path_only",
                    "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) (!$past(q_sync_o) && q_sync_o) |-> q_posedge_pulse_o);",
                    "why_it_should_miss": "The rising-edge path can stay correct while the falling-edge pulse disappears.",
                },
            ),
            "hard_case_rationale": "Like the posedge variant, this needs the exact boundary relation rather than a vague pulse-exists check.",
            "overfit_lure": "",
            "stimulus_notes": "Drive a clean high interval first, then force a falling edge between sampled clocks. Held-out should interleave extra rises between the fall checks.",
        },
        {
            "name": "case134_prim_intr_event_not_sticky",
            "source_project": "opentitan",
            "source_module": "prim_intr_hw",
            "source_files": [
                "hw/ip/prim/rtl/prim_intr_hw.sv",
            ],
            "top_file": "hw/ip/prim/rtl/prim_intr_hw.sv",
            "mutation_edits": [
                {
                    "search": "    assign status = reg2hw_intr_state_q_i ;\n",
                    "replace": "    assign status = new_event;\n",
                }
            ],
            "bug_class": "temporal_cross_cycle",
            "bug_family": "event_latching",
            "bug_type": "event interrupt state drops when the source pulse goes away",
            "spec": "In Event mode, a captured event shall remain latched in the interrupt state until software clears it.",
            "key_signals": ["clk_i", "rst_ni", "event_intr_i", "reg2hw_intr_enable_q_i", "reg2hw_intr_state_q_i", "intr_o"],
            "golden_sva": {
                "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) ($past(reg2hw_intr_state_q_i) && reg2hw_intr_state_q_i && reg2hw_intr_enable_q_i) |-> intr_o);",
                "expected_behavior": "Once event state is latched and remains high, the enabled interrupt output must stay asserted on the next sampled cycle.",
                "temporal_type": "cross-cycle latched-visibility check",
            },
            "loose_negative_controls": _controls(
                {
                    "name": "event_sets_state_next_cycle",
                    "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) event_intr_i |-> reg2hw_intr_enable_q_i);",
                    "why_it_should_miss": "It checks only that the sampled hardware event arrived while enabled, not whether the interrupt stayed latched afterward.",
                },
                {
                    "name": "masked_interrupt_low",
                    "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) (!reg2hw_intr_enable_q_i) |-> !intr_o);",
                    "why_it_should_miss": "The bug is about event retention while enabled, not masked behavior.",
                },
            ),
            "hard_case_rationale": "A momentary event makes this easy to miss with generic 'event seen' wording. The contract is specifically about retention across cycles.",
            "overfit_lure": "",
            "stimulus_notes": "Pulse event_intr_i high for one cycle under enable, then keep it low without clearing state. Held-out should insert an extra idle cycle before the pulse.",
        },
        {
            "name": "case135_prim_intr_enable_mask_ignored",
            "source_project": "opentitan",
            "source_module": "prim_intr_hw",
            "source_files": [
                "hw/ip/prim/rtl/prim_intr_hw.sv",
            ],
            "top_file": "hw/ip/prim/rtl/prim_intr_hw.sv",
            "mutation_edits": [
                {
                    "search": "        intr_o <= status & reg2hw_intr_enable_q_i;\n",
                    "replace": "        intr_o <= status;\n",
                }
            ],
            "bug_class": "combination_same_cycle",
            "bug_family": "interrupt_masking",
            "bug_type": "interrupt output ignores the enable mask",
            "spec": "Even if interrupt state is set, intr_o shall be low in any sampled cycle where reg2hw_intr_enable_q_i is low.",
            "key_signals": ["clk_i", "rst_ni", "event_intr_i", "reg2hw_intr_enable_q_i", "reg2hw_intr_state_q_i", "intr_o"],
            "golden_sva": {
                "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) (!reg2hw_intr_enable_q_i && !$past(reg2hw_intr_enable_q_i) && reg2hw_intr_state_q_i && $past(reg2hw_intr_state_q_i)) |-> !intr_o);",
                "expected_behavior": "The output mask must suppress interrupt visibility immediately when enable is low.",
                "temporal_type": "same-cycle mask gating check",
            },
            "loose_negative_controls": _controls(
                {
                    "name": "event_updates_state",
                    "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) event_intr_i |-> hw2reg_intr_state_de_o);",
                    "why_it_should_miss": "State-update correctness says nothing about whether the mask is applied at the outgoing interrupt pin.",
                },
                {
                    "name": "enabled_event_visible",
                    "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) (reg2hw_intr_enable_q_i && $past(reg2hw_intr_enable_q_i) && reg2hw_intr_state_q_i && $past(reg2hw_intr_state_q_i)) |-> intr_o);",
                    "why_it_should_miss": "The buggy design still satisfies enabled visibility while failing masked suppression after enable drops.",
                },
            ),
            "hard_case_rationale": "Many loose interrupt assertions check only that enabled events become visible. The hard part is checking the exact masked corner after state has already gone high.",
            "overfit_lure": "",
            "stimulus_notes": "Raise interrupt state first, then drop reg2hw_intr_enable_q_i while holding state high. Held-out should do the same after a different event prelude.",
        },
        {
            "name": "case136_prim_filter_ctr_disabled_bypass_stale_alt",
            "source_project": "opentitan",
            "source_module": "prim_filter_ctr",
            "source_files": [
                "hw/ip/prim_generic/rtl/prim_flop.sv",
                "hw/ip/prim_generic/rtl/prim_flop_2sync.sv",
                "hw/ip/prim/rtl/prim_filter_ctr.sv",
            ],
            "top_file": "hw/ip/prim/rtl/prim_filter_ctr.sv",
            "mutation_edits": [
                {
                    "search": "  assign filter_o = enable_i ? stored_value_q : filter_synced;\n",
                    "replace": "  assign filter_o = stored_value_q;\n",
                }
            ],
            "bug_class": "combination_same_cycle",
            "bug_family": "filter_bypass_control",
            "bug_type": "counter-based disabled filter bypass stays on stored state",
            "spec": "When enable_i is low, the counter-based filter shall bypass to the current input in the same sampled cycle.",
            "key_signals": ["clk_i", "rst_ni", "enable_i", "filter_i", "thresh_i", "filter_o"],
                "golden_sva": {
                    "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) (!enable_i && $past(enable_i) && (filter_i != $past(filter_i)) && ($past(filter_o) == $past(filter_i))) |-> (filter_o == filter_i));",
                    "expected_behavior": "On the first disabled sampled cycle after a previously tracked value is established, the counter-based bypass must follow the live input immediately.",
                    "temporal_type": "enable-to-bypass transition check",
                },
            "loose_negative_controls": _controls(
                  {
                      "name": "enabled_threshold_only",
                      "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) (enable_i && filter_o) |-> filter_i);",
                      "why_it_should_miss": "The enabled threshold path can still look fine on cycles where it is already driving high while the disabled bypass path remains stale.",
                  },
                {
                    "name": "threshold_nonzero",
                    "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) enable_i |-> (thresh_i == thresh_i));",
                    "why_it_should_miss": "It never constrains the bypass output relation at all.",
                },
            ),
            "hard_case_rationale": "This keeps the counter machinery intact and only corrupts the disabled bypass path, which is exactly the kind of bug broad filter assertions tend to miss.",
            "overfit_lure": "",
            "stimulus_notes": "Accumulate the stored value while enabled, then disable from a negedge and flip filter_i so the next sampled cycle must reflect the live input. Held-out should force the opposite stored polarity before disabling.",
        },
        {
            "name": "case137_prim_onehot_addr_false_positive",
            "source_project": "opentitan",
            "source_module": "prim_onehot_check",
            "source_files": [
                "hw/ip/prim/rtl/prim_onehot_check.sv",
            ],
            "top_file": "hw/ip/prim/rtl/prim_onehot_check.sv",
            "mutation_edits": [
                {
                    "search": "    assign addr_err = or_tree[0] ^ and_tree[0];\n",
                    "replace": "    assign addr_err = or_tree[0];\n",
                }
            ],
            "bug_class": "combination_same_cycle",
            "bug_family": "decoded_index_consistency",
            "bug_type": "legal onehot request spuriously flags address error",
            "spec": "If exactly one bit of oh_i is high and addr_i points to that bit, err_o shall remain low in the same cycle.",
            "key_signals": ["clk_i", "rst_ni", "oh_i", "addr_i", "en_i", "err_o"],
            "golden_sva": {
                "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) (((((oh_i == 4'b0001) && ($past(oh_i) == 4'b0001) && (addr_i == 2'd0) && ($past(addr_i) == 2'd0)) || ((oh_i == 4'b0010) && ($past(oh_i) == 4'b0010) && (addr_i == 2'd1) && ($past(addr_i) == 2'd1))) && en_i && $past(en_i))) |-> !err_o);",
                "expected_behavior": "A legal onehot/address match must not raise a spurious checker error.",
                "temporal_type": "same-cycle combinational legality check",
            },
            "loose_negative_controls": _controls(
                {
                    "name": "illegal_must_error",
                    "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) ((((oh_i == 4'b0100) && (addr_i == 2'd0)) || ((oh_i == 4'b1000) && (addr_i == 2'd1))) && en_i) |-> err_o);",
                    "why_it_should_miss": "It constrains only obviously illegal address mismatches and says nothing about false positives on legal requests.",
                },
                {
                    "name": "multihot_implies_enable",
                    "sva": "assert property (@(posedge clk_i) disable iff (!rst_ni) ((oh_i == 4'b1010) || (oh_i == 4'b1100)) |-> en_i);",
                    "why_it_should_miss": "It only checks that an unrelated multihot stimulus was presented while enabled, so it says nothing about false positives on legal onehot requests.",
                },
            ),
            "hard_case_rationale": "This is a good negative-correctness case: generic assertions about illegal inputs still pass, but only an exact legal-corner assertion exposes the spurious error.",
            "overfit_lure": "Use exact legal pairs like (4'b0001, 2'd0) and (4'b0010, 2'd1) so trace-conditioned methods are tempted to memorize the seen constants.",
            "stimulus_notes": "Exercise both legal and illegal onehot/address pairs. Held-out should use a different legal bit/index match than the primary trace.",
        },
    ]
