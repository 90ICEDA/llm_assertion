# case426_axis_fifo_temporal_hold_3

- Parent bug: `case426_axis_fifo_temporal_hold_3`
- Upstream RTL: `external/verilog-axis/rtl/axis_fifo.v`
- Mutation: `    good_frame_reg <= 1'b0;` → `    good_frame_reg <= good_frame_reg; // ASSERTIONFORGE_MUTATION: state update suppressed`
- Validation status: RTL mutation materialized; module-specific seen/held-out/decoy tests are pending.
