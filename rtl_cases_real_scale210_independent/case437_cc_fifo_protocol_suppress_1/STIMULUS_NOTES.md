# case437_cc_fifo_protocol_suppress_1

- Parent bug: `case437_cc_fifo_protocol_suppress_1`
- Upstream RTL: `external/common_cells/src/cc_fifo.sv`
- Mutation: `    assign usage_o = status_cnt_q;` → `    assign usage_o = '0; // ASSERTIONFORGE_MUTATION: combinational/protocol output suppressed`
- Validation status: RTL mutation materialized; module-specific seen/held-out/decoy tests are pending.
