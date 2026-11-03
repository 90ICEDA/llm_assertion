# case105_prim_fifo_empty_late

- `bug_class`: combination_same_cycle
- `bug_family`: fifo_boundary_flag
- `bug_type`: empty asserted one cycle late

## Spec

empty_o shall assert in the same cycle the FIFO occupancy returns to zero.

## Hardness Rationale

The bug only appears at the exact zero-occupancy return point. Loose assertions about mutual exclusion of full/empty are not enough.

## Stimulus Notes

Write two entries, read them out, and sample the final read-to-empty transition. Held-out should empty after a write/read/write/read pattern.

## Loose Negative Controls

- `empty_after_clear_only`: It checks reset-like clearing but not the normal read-to-empty transition.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) clr_i |=> empty_o);`
- `no_full_when_empty`: The buggy design can satisfy this while still delaying empty_o.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) empty_o |-> !full_o);`

## Next Step

Create `tb.v`, `tb_holdout.v`, regenerate waveforms, then run golden self-check and hardness gates before admitting this case.

## Overfit Decoy

- Source: `donor primary trace from case258_fifo_v2_from_case105_prim_fifo_empty_late`
- Lure: Seen and held-out reach the same FIFO boundary through different write/read preludes.
- Files: `tb_decoy.v`, `waveform_good_decoy.csv`, `waveform_bad_decoy.csv`

