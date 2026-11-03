# case421_axis_register_temporal_hold_1

- Parent bug: `case421_axis_register_temporal_hold_1`
- Upstream RTL: `external/verilog-axis/rtl/axis_register.v`
- Mutation: `        s_axis_tready_reg <= s_axis_tready_early;` → `        s_axis_tready_reg <= s_axis_tready_reg; // ASSERTIONFORGE_MUTATION: state update suppressed`
- Validation status: RTL mutation materialized; module-specific seen/held-out/decoy tests are pending.
