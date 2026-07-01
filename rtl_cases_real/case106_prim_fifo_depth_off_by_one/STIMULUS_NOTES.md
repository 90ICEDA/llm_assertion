# case106_prim_fifo_depth_off_by_one

- `bug_class`: combination_same_cycle
- `bug_family`: fifo_boundary_flag
- `bug_type`: depth output biased high by one

## Spec

depth_o shall equal the exact FIFO occupancy in every cycle.

## Hardness Rationale

This bug is subtle because the control flags can look mostly plausible. Only a precise occupancy relation catches it.

## Stimulus Notes

Exercise empty, single-entry, and two-entry states. Held-out should revisit zero occupancy after a clear pulse.

## Loose Negative Controls

- `monotonic_growth_only`: A biased counter can still look monotonic.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) incr_wptr_i && !incr_rptr_i |=> (depth_o >= $past(depth_o)));`
- `full_empty_exclusive`: It ignores the numeric correctness of depth_o itself.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) !(full_o && empty_o));`

## Next Step

Create `tb.v`, `tb_holdout.v`, regenerate waveforms, then run golden self-check and hardness gates before admitting this case.
