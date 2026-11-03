# case419_cc_clk_int_div_temporal_hold_1

- Parent bug: `case419_cc_clk_int_div_temporal_hold_1`
- Upstream RTL: `external/common_cells/src/cc_clk_int_div.sv`
- Mutation: `      gate_is_open_q <= 1'b0;` → `      gate_is_open_q <= gate_is_open_q; // ASSERTIONFORGE_MUTATION: state update suppressed`
- Validation status: RTL mutation materialized; module-specific seen/held-out/decoy tests are pending.
