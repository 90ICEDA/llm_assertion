# case438_cc_fifo_protocol_suppress_2

- Parent bug: `case438_cc_fifo_protocol_suppress_2`
- Upstream RTL: `external/common_cells/src/cc_fifo.sv`
- Mutation: `        assign empty_o     = ~push_i;` → `        assign empty_o = '0; // ASSERTIONFORGE_MUTATION: combinational/protocol output suppressed`
- Validation status: RTL mutation materialized; module-specific seen/held-out/decoy tests are pending.
