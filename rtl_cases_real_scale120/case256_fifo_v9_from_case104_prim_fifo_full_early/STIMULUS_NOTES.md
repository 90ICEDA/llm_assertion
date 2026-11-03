# case104_prim_fifo_full_early

- `bug_class`: combination_same_cycle
- `bug_family`: fifo_boundary_flag
- `bug_type`: full asserted one slot early

## Spec

full_o shall assert if and only if the FIFO currently contains Depth entries; it must remain low at Depth-1.

## Hardness Rationale

This is a classic tight boundary bug. A hand-wavy FIFO assertion can pass while missing the exact Depth-1 cycle.

## Stimulus Notes

Fill the FIFO to 3 entries without reads, sample full_o at depth 3, then push once more. Held-out should use an interleaved read/write prelude before reaching depth 3 again.

## Loose Negative Controls

- `full_implies_max_depth`: It may stay vacuous if the bug avoids asserting full under the sampled corner or if the depth output is also misleading.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) full_o |-> (depth_o == 3'd4));`
- `eventual_full_after_writes`: It does not constrain the exact boundary cycle where full must remain low.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) incr_wptr_i |-> !empty_o);`

## Next Step

Create `tb.v`, `tb_holdout.v`, regenerate waveforms, then run golden self-check and hardness gates before admitting this case.

## Overfit Decoy

- Source: `donor primary trace from case104_prim_fifo_full_early`
- Lure: Seen and held-out reach the same FIFO boundary through different write/read preludes.
- Files: `tb_decoy.v`, `waveform_good_decoy.csv`, `waveform_bad_decoy.csv`

