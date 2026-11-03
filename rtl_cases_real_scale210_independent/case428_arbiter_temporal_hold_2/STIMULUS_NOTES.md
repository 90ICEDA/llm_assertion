# case428_arbiter_temporal_hold_2

- Parent bug: `case428_arbiter_temporal_hold_2`
- Upstream RTL: `external/verilog-axis/rtl/arbiter.v`
- Mutation: `    grant_valid_reg <= grant_valid_next;` → `    grant_valid_reg <= grant_valid_reg; // ASSERTIONFORGE_MUTATION: state update suppressed`
- Validation status: RTL mutation materialized; module-specific seen/held-out/decoy tests are pending.
