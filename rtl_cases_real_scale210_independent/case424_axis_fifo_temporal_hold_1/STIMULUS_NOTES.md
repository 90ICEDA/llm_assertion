# case424_axis_fifo_temporal_hold_1

- Parent bug: `case424_axis_fifo_temporal_hold_1`
- Upstream RTL: `external/verilog-axis/rtl/axis_fifo.v`
- Mutation: `    overflow_reg <= 1'b0;` → `    overflow_reg <= overflow_reg; // ASSERTIONFORGE_MUTATION: state update suppressed`
- Validation status: RTL mutation materialized; module-specific seen/held-out/decoy tests are pending.
