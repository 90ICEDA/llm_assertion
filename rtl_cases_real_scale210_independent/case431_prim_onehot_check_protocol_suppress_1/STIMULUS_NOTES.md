# case431_prim_onehot_check_protocol_suppress_1

- Parent bug: `case431_prim_onehot_check_protocol_suppress_1`
- Upstream RTL: `external/opentitan/hw/ip/prim/rtl/prim_onehot_check.sv`
- Mutation: `          assign or_tree[Pa]  = oh_i[offset];` → `          assign or_tree[Pa] = '0; // ASSERTIONFORGE_MUTATION: combinational/protocol output suppressed`
- Validation status: RTL mutation materialized; module-specific seen/held-out/decoy tests are pending.
