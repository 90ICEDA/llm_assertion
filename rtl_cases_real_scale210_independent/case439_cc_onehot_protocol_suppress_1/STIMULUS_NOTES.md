# case439_cc_onehot_protocol_suppress_1

- Parent bug: `case439_cc_onehot_protocol_suppress_1`
- Upstream RTL: `external/common_cells/src/cc_onehot.sv`
- Mutation: `    assign is_onehot_o = d_i;` → `    assign is_onehot_o = '0; // ASSERTIONFORGE_MUTATION: combinational/protocol output suppressed`
- Validation status: RTL mutation materialized; module-specific seen/held-out/decoy tests are pending.
