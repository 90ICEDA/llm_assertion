# case435_prim_filter_ctr_protocol_suppress_1

- Parent bug: `case435_prim_filter_ctr_protocol_suppress_1`
- Upstream RTL: `external/opentitan/hw/ip/prim/rtl/prim_filter_ctr.sv`
- Mutation: `    assign filter_synced = filter_i;` → `    assign filter_synced = '0; // ASSERTIONFORGE_MUTATION: combinational/protocol output suppressed`
- Validation status: RTL mutation materialized; module-specific seen/held-out/decoy tests are pending.
