# case427_arbiter_temporal_hold_1

- Parent bug: `case427_arbiter_temporal_hold_1`
- Upstream RTL: `external/verilog-axis/rtl/arbiter.v`
- Mutation: `    grant_reg <= grant_next;` → `    grant_reg <= grant_reg; // ASSERTIONFORGE_MUTATION: state update suppressed`
- Validation status: RTL mutation materialized; module-specific seen/held-out/decoy tests are pending.
