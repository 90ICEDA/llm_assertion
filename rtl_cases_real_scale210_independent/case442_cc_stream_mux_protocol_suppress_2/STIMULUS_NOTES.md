# case442_cc_stream_mux_protocol_suppress_2

- Parent bug: `case442_cc_stream_mux_protocol_suppress_2`
- Upstream RTL: `external/common_cells/src/cc_stream_mux.sv`
- Mutation: `  assign oup_valid_o  = inp_valid_i[inp_sel_i];` → `  assign oup_valid_o = '0; // ASSERTIONFORGE_MUTATION: combinational/protocol output suppressed`
- Validation status: RTL mutation materialized; module-specific seen/held-out/decoy tests are pending.
