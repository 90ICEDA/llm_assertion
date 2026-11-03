# case429_axis_rate_limit_temporal_hold_1

- Parent bug: `case429_axis_rate_limit_temporal_hold_1`
- Upstream RTL: `external/verilog-axis/rtl/axis_rate_limit.v`
- Mutation: `    acc_reg <= acc_next;` → `    acc_reg <= acc_reg; // ASSERTIONFORGE_MUTATION: state update suppressed`
- Validation status: RTL mutation materialized; module-specific seen/held-out/decoy tests are pending.
