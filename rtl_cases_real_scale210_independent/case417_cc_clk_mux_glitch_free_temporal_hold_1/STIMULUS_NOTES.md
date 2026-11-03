# case417_cc_clk_mux_glitch_free_temporal_hold_1

- Parent bug: `case417_cc_clk_mux_glitch_free_temporal_hold_1`
- Upstream RTL: `external/common_cells/src/cc_clk_mux_glitch_free.sv`
- Mutation: `          async_reset_bypass_active_q[i] <= 1'b1;` → `          async_reset_bypass_active_q[i] <= async_reset_bypass_active_q[i]; // ASSERTIONFORGE_MUTATION: state update suppressed`
- Validation status: RTL mutation materialized; module-specific seen/held-out/decoy tests are pending.
