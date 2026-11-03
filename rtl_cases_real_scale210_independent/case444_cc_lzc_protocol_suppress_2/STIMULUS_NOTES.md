# case444_cc_lzc_protocol_suppress_2

- Parent bug: `case444_cc_lzc_protocol_suppress_2`
- Upstream RTL: `external/common_cells/src/cc_lzc.sv`
- Mutation: `    assign empty_o = !in_i[0];` → `    assign empty_o = '0; // ASSERTIONFORGE_MUTATION: combinational/protocol output suppressed`
- Validation status: RTL mutation materialized; module-specific seen/held-out/decoy tests are pending.
