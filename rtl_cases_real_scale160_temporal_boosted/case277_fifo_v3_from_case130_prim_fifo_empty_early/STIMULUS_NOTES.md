# case130_prim_fifo_empty_early

- `bug_class`: combination_same_cycle
- `bug_family`: fifo_boundary_flag
- `bug_type`: empty asserts one slot early

## Spec

empty_o shall remain low while the FIFO still contains exactly one entry.

## Hardness Rationale

This is the mirror image of the classic empty-late bug: only the exact occupancy-1 boundary distinguishes correct from buggy.

## Stimulus Notes

Write entries, drain down to one remaining item, and sample empty_o before the final read. Held-out should revisit the one-entry boundary after a clear pulse and refill.

## Loose Negative Controls

- `no_full_when_empty`: The buggy FIFO can still avoid asserting full while empty_o rises too early.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) empty_o |-> !full_o);`
- `reads_reduce_depth`: It never checks the exact one-entry boundary where empty_o must stay low.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) incr_rptr_i |-> !full_o);`

## Next Step

Create `tb.v`, `tb_holdout.v`, regenerate waveforms, then run golden self-check and hardness gates before admitting this case.

## Overfit Decoy

- Source: `donor primary trace from case278_fifo_v4_from_case130_prim_fifo_empty_early`
- Lure: Seen and held-out reach the same FIFO boundary through different write/read preludes.
- Files: `tb_decoy.v`, `waveform_good_decoy.csv`, `waveform_bad_decoy.csv`

