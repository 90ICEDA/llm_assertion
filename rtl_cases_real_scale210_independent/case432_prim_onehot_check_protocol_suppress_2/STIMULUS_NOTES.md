# case432_prim_onehot_check_protocol_suppress_2

- Parent bug: `case432_prim_onehot_check_protocol_suppress_2`
- Upstream RTL: `external/opentitan/hw/ip/prim/rtl/prim_onehot_check.sv`
- Mutation: `          assign and_tree[Pa] = oh_i[offset];` → `          assign and_tree[Pa] = '0; // ASSERTIONFORGE_MUTATION: combinational/protocol output suppressed`
- Validation status: RTL mutation materialized; module-specific seen/held-out/decoy tests are pending.
