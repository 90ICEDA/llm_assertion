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
