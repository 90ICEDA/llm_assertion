# case436_prim_filter_ctr_protocol_suppress_2

- Parent bug: `case436_prim_filter_ctr_protocol_suppress_2`
- Upstream RTL: `external/opentitan/hw/ip/prim/rtl/prim_filter_ctr.sv`
- Mutation: `  assign update_stored_value = (diff_ctr_d == thresh_i);` → `  assign update_stored_value = '0; // ASSERTIONFORGE_MUTATION: combinational/protocol output suppressed`
- Validation status: RTL mutation materialized; module-specific seen/held-out/decoy tests are pending.
