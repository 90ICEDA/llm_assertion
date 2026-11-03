# case420_cc_clk_int_div_temporal_hold_2

- Parent bug: `case420_cc_clk_int_div_temporal_hold_2`
- Upstream RTL: `external/common_cells/src/cc_clk_int_div.sv`
- Mutation: `      gate_is_open_q <= gate_en_q & en_i;` → `      gate_is_open_q <= gate_is_open_q; // ASSERTIONFORGE_MUTATION: state update suppressed`
- Validation status: RTL mutation materialized; module-specific seen/held-out/decoy tests are pending.
