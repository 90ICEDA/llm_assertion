# case124_prim_fifo_clear_ignored

- `bug_class`: temporal_cross_cycle
- `bug_family`: clear_semantics
- `bug_type`: clear pulse does not reset FIFO pointers

## Spec

A clear pulse shall reset the FIFO occupancy and pointers on the next cycle.

## Hardness Rationale

The bug hides in an operational control path distinct from reset. Loose FIFO assertions rarely distinguish the two.

## Stimulus Notes

Fill the FIFO, pulse clr_i, and sample the next cycle. Held-out should clear from a different occupancy level.

## Loose Negative Controls

- `eventual_empty_after_reads`: Reads can still eventually drain the FIFO without proving clear works.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) incr_rptr_i |-> !full_o);`
- `reset_path_only`: It checks asynchronous reset rather than operational clear.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) !rst_ni |-> empty_o);`

## Next Step

Create `tb.v`, `tb_holdout.v`, regenerate waveforms, then run golden self-check and hardness gates before admitting this case.

## Overfit Decoy

- Source: `self held-out trace with a decoy idle perturbation`
- Lure: Decoy trace preserves the same temporal trigger for clear pulse does not reset FIFO pointers through self held-out trace with a decoy idle perturbation, but shifts surrounding prelude timing so the assertion must generalize beyond the seen trace.
- Files: `tb_decoy.v`, `waveform_good_decoy.csv`, `waveform_bad_decoy.csv`

