# case447_axis_mux_protocol_suppress_1

- Parent bug: `case447_axis_mux_protocol_suppress_1`
- Upstream RTL: `external/verilog-axis/rtl/axis_mux.v`
- Mutation: `assign s_axis_tready = s_axis_tready_reg;` → `assign s_axis_tready = '0; // ASSERTIONFORGE_MUTATION: combinational/protocol output suppressed`
- Validation status: RTL mutation materialized; module-specific seen/held-out/decoy tests are pending.
