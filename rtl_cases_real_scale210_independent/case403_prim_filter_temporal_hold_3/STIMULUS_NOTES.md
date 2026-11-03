# case403_prim_filter_temporal_hold_3

- Parent bug: `case403_prim_filter_temporal_hold_3`
- Upstream RTL: `external/opentitan/hw/ip/prim/rtl/prim_filter.sv`
- Mutation: `      stored_vector_q <= '0;` → `      stored_vector_q <= stored_vector_q; // ASSERTIONFORGE_MUTATION: state update suppressed`
- Validation status: RTL mutation materialized; module-specific seen/held-out/decoy tests are pending.
