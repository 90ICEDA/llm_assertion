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

- `nonempty_has_depth`: A depth output biased high by one can still satisfy a coarse nonzero-when-nonempty check.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) (!empty_o) |-> (depth_o != 3'd0));`
- `full_empty_exclusive`: It ignores the numeric correctness of depth_o itself.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) !(full_o && empty_o));`

## Next Step

Create `tb.v`, `tb_holdout.v`, regenerate waveforms, then run golden self-check and hardness gates before admitting this case.

## Overfit Decoy

- Source: `donor primary trace from case273_fifo_v8_from_case106_prim_fifo_depth_off_by_one`
- Lure: Seen and held-out reach the same FIFO boundary through different write/read preludes.
- Files: `tb_decoy.v`, `waveform_good_decoy.csv`, `waveform_bad_decoy.csv`

