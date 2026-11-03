# Frozen repair requirements (before opening legacy feedback)

Sampling used a direct seeded shuffle (`System.Random(20260918)`) of all 30 parent IDs in `selected_train_parents.csv`; the first six were retained. No pair list, probe result, failure count, chosen/rejected field, or prior manual-review output was used. Slots 1–7 are the natural candidate pool. Slot 8 is excluded and recorded only as a **synthetic control**.

- `case115_prim_edge_both_edges_collapsed`: `q_posedge_pulse_o` may assert for a low-to-high transition only; it must remain low for a high-to-low transition, while `q_negedge_pulse_o` represents the falling edge.
- `case505_axis_stat_counter_frame_pulse_early`: after a sampled frame completion, `stat_valid_o` must remain low on the immediately following cycle and assert one cycle later, carrying the captured original length.
- `case463_axis_frame_join_port_skip`: after an accepted last beat, the selected input port advances exactly one position, including under ready/valid backpressure.
- `case506_axis_crosspoint_simultaneous_source_priority`: if both sources are valid for a ready output, source zero wins; exactly one valid beat is presented with source-zero data and matching ready behavior.
- `case457_cc_delta_counter_load_enable_priority`: a load overrides enable when simultaneous; on the following cycle `q_o` equals the sampled `d_i` (subject to reset/clear precedence).
- `case478_axis_srl_register_ready_recovery`: an accepted downstream transfer (`m_valid && m_ready`) frees capacity so `s_ready` is asserted on the next cycle.

Judgment vocabulary: `MATCH`, `PARTIAL`, `MISMATCH`, `UNKNOWN`. Pairwise comparisons derived from these judgments must be `A_BETTER`, `B_BETTER`, `EQUIVALENT_AT_THIS_RESOLUTION`, `INCOMPARABLE`, or `UNKNOWN`; no forced ordering is allowed.
