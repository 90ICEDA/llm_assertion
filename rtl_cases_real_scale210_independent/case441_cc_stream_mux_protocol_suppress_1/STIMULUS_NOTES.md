# case441_cc_stream_mux_protocol_suppress_1

- Parent bug: `case441_cc_stream_mux_protocol_suppress_1`
- Upstream RTL: `external/common_cells/src/cc_stream_mux.sv`
- Mutation: `  assign oup_data_o   = inp_data_i[inp_sel_i];` → `  assign oup_data_o = '0; // ASSERTIONFORGE_MUTATION: combinational/protocol output suppressed`
- Validation status: RTL mutation materialized; module-specific seen/held-out/decoy tests are pending.
