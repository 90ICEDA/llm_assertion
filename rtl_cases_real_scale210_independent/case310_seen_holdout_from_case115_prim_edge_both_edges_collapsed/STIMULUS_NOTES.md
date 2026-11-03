# case115_prim_edge_both_edges_collapsed

- `bug_class`: temporal_cross_cycle
- `bug_family`: edge_direction
- `bug_type`: posedge output fires on both edges

## Spec

q_posedge_pulse_o shall remain low on falling edges and assert only on rising edges.

## Hardness Rationale

This is a good 'conservative assertion misses the false positives' case: one can verify positive behavior and still miss illegal extra pulses.

## Stimulus Notes

Include at least one clean falling edge where only q_negedge_pulse_o should assert. Held-out should vary the time spent high before falling.

## Loose Negative Controls

- `pulse_occurs_on_rise`: The buggy implementation still pulses on rises; the problem is the extra pulses on falls.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) (!q_sync_o && d_i) |-> q_posedge_pulse_o);`
- `negedge_output_correct`: The negedge output can stay correct while the posedge output spuriously fires too.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) (q_sync_o && !d_i) |-> q_negedge_pulse_o);`

## Next Step

Create `tb.v`, `tb_holdout.v`, regenerate waveforms, then run golden self-check and hardness gates before admitting this case.

## Overfit Decoy

- Source: `self held-out trace with a decoy idle perturbation`
- Lure: Decoy trace preserves the same temporal trigger for posedge output fires on both edges through self held-out trace with a decoy idle perturbation, but shifts surrounding prelude timing so the assertion must generalize beyond the seen trace.
- Files: `tb_decoy.v`, `waveform_good_decoy.csv`, `waveform_bad_decoy.csv`

## Temporal Bootstrap Variant

- Variant case: `case310_seen_holdout_from_case115_prim_edge_both_edges_collapsed`
- Seed case: `case115_prim_edge_both_edges_collapsed`
- Track plan: `seen_from_holdout`
- Primary trace source: `holdout`
- Held-out trace source: `primary`
- Decoy trace source: `decoy`
- Validation basis: inherited from the seed case's track-level formal golden report and hardness/divergence gates.
