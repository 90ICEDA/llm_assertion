# case443_cc_lzc_protocol_suppress_1

- Parent bug: `case443_cc_lzc_protocol_suppress_1`
- Upstream RTL: `external/common_cells/src/cc_lzc.sv`
- Mutation: `    assign cnt_o[0] = !in_i[0];` → `    assign cnt_o[0] = '0; // ASSERTIONFORGE_MUTATION: combinational/protocol output suppressed`
- Validation status: RTL mutation materialized; module-specific seen/held-out/decoy tests are pending.
