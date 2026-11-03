# case448_axis_mux_protocol_suppress_2

- Parent bug: `case448_axis_mux_protocol_suppress_2`
- Upstream RTL: `external/verilog-axis/rtl/axis_mux.v`
- Mutation: `assign m_axis_tdata  = m_axis_tdata_reg;` → `assign m_axis_tdata = '0; // ASSERTIONFORGE_MUTATION: combinational/protocol output suppressed`
- Validation status: RTL mutation materialized; module-specific seen/held-out/decoy tests are pending.
