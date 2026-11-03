# case450_axis_demux_protocol_suppress_2

- Parent bug: `case450_axis_demux_protocol_suppress_2`
- Upstream RTL: `external/verilog-axis/rtl/axis_demux.v`
- Mutation: `assign m_axis_tdata  = {M_COUNT{m_axis_tdata_reg}};` → `assign m_axis_tdata = '0; // ASSERTIONFORGE_MUTATION: combinational/protocol output suppressed`
- Validation status: RTL mutation materialized; module-specific seen/held-out/decoy tests are pending.
