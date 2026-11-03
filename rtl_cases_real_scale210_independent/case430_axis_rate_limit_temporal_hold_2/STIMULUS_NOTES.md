# case430_axis_rate_limit_temporal_hold_2

- Parent bug: `case430_axis_rate_limit_temporal_hold_2`
- Upstream RTL: `external/verilog-axis/rtl/axis_rate_limit.v`
- Mutation: `    frame_reg <= frame_next;` → `    frame_reg <= frame_reg; // ASSERTIONFORGE_MUTATION: state update suppressed`
- Validation status: RTL mutation materialized; module-specific seen/held-out/decoy tests are pending.
