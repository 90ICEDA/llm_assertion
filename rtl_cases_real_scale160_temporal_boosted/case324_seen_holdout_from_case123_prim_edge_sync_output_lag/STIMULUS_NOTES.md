# case123_prim_edge_sync_output_lag

- `bug_class`: temporal_cross_cycle
- `bug_family`: pulse_persistence
- `bug_type`: posedge pulse stays high beyond the single transition cycle

## Spec

q_posedge_pulse_o shall assert only on the sampled 0->1 transition cycle and must return low on the following stable-high cycle.

## Hardness Rationale

This is an exact pulse-width bug. Assertions that only check that a rise causes some pulse miss the illegal persistence on the next stable cycle.

## Stimulus Notes

Use EnSync=0 and drive a clean 0->1 rise from a negedge, then hold d_i high for at least one more sampled cycle. Held-out should use a longer high plateau and a later falling edge.

## Loose Negative Controls

- `pulse_occurs_on_rise`: The buggy design still produces a pulse on a rising edge; the bug is that the pulse incorrectly persists into later stable-high cycles.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) (!$past(d_i) && d_i) |-> q_posedge_pulse_o);`
- `falling_edge_detected`: The falling-edge output can remain perfectly correct while the posedge pulse width is wrong.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) ($past(d_i) && !d_i) |-> q_negedge_pulse_o);`

## Next Step

Create `tb.v`, `tb_holdout.v`, regenerate waveforms, then run golden self-check and hardness gates before admitting this case.

## Overfit Decoy

- Source: `self held-out trace with a decoy idle perturbation`
- Lure: Decoy trace preserves the same temporal trigger for posedge pulse stays high beyond the single transition cycle through self held-out trace with a decoy idle perturbation, but shifts surrounding prelude timing so the assertion must generalize beyond the seen trace.
- Files: `tb_decoy.v`, `waveform_good_decoy.csv`, `waveform_bad_decoy.csv`

## Temporal Bootstrap Variant

- Variant case: `case324_seen_holdout_from_case123_prim_edge_sync_output_lag`
- Seed case: `case123_prim_edge_sync_output_lag`
- Track plan: `seen_from_holdout`
- Primary trace source: `holdout`
- Held-out trace source: `primary`
- Decoy trace source: `decoy`
- Validation basis: inherited from the seed case's track-level formal golden report and hardness/divergence gates.
