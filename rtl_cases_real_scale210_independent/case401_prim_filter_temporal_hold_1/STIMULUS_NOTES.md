# case401_prim_filter_temporal_hold_1

- Parent bug: `case401_prim_filter_temporal_hold_1`
- Upstream RTL: `external/opentitan/hw/ip/prim/rtl/prim_filter.sv`
- Mutation: `      stored_value_q <= 1'b0;` → `      stored_value_q <= stored_value_q; // ASSERTIONFORGE_MUTATION: state update suppressed`
- Validation status: RTL mutation materialized; module-specific seen/held-out/decoy tests are pending.
