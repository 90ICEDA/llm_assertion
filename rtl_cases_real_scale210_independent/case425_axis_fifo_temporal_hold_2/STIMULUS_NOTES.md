# case425_axis_fifo_temporal_hold_2

- Parent bug: `case425_axis_fifo_temporal_hold_2`
- Upstream RTL: `external/verilog-axis/rtl/axis_fifo.v`
- Mutation: `    bad_frame_reg <= 1'b0;` → `    bad_frame_reg <= bad_frame_reg; // ASSERTIONFORGE_MUTATION: state update suppressed`
- Validation status: RTL mutation materialized; module-specific seen/held-out/decoy tests are pending.
