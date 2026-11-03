# case440_cc_onehot_protocol_suppress_2

- Parent bug: `case440_cc_onehot_protocol_suppress_2`
- Upstream RTL: `external/common_cells/src/cc_onehot.sv`
- Mutation: `    assign sum[0] = d_i;` → `    assign sum[0] = '0; // ASSERTIONFORGE_MUTATION: combinational/protocol output suppressed`
- Validation status: RTL mutation materialized; module-specific seen/held-out/decoy tests are pending.
