# case449_axis_demux_protocol_suppress_1

- Parent bug: `case449_axis_demux_protocol_suppress_1`
- Upstream RTL: `external/verilog-axis/rtl/axis_demux.v`
- Mutation: `assign s_axis_tready = s_axis_tready_reg && enable;` → `assign s_axis_tready = '0; // ASSERTIONFORGE_MUTATION: combinational/protocol output suppressed`
- Validation status: RTL mutation materialized; module-specific seen/held-out/decoy tests are pending.
