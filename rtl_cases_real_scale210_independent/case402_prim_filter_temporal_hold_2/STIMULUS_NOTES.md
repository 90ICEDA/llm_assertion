# case402_prim_filter_temporal_hold_2

- Parent bug: `case402_prim_filter_temporal_hold_2`
- Upstream RTL: `external/opentitan/hw/ip/prim/rtl/prim_filter.sv`
- Mutation: `      stored_value_q <= filter_synced;` → `      stored_value_q <= stored_value_q; // ASSERTIONFORGE_MUTATION: state update suppressed`
- Validation status: RTL mutation materialized; module-specific seen/held-out/decoy tests are pending.
