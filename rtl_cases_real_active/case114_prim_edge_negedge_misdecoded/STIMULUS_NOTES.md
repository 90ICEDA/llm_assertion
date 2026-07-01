# case114_prim_edge_negedge_misdecoded

- `bug_class`: temporal_cross_cycle
- `bug_family`: edge_direction
- `bug_type`: negedge output decodes posedge

## Spec

q_negedge_pulse_o shall pulse for exactly the sampled 1->0 transition and not for 0->1 transitions.

## Hardness Rationale

Like the posedge case, this forces exact polarity rather than generic 'edge activity' checking.

## Stimulus Notes

Toggle d_i through both rising and falling transitions with clean holds in between. Held-out should use a different ordering of edges.

## Loose Negative Controls

- `event_exists`: It ignores which edge output is supposed to fire.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) (d_i != q_sync_o) |-> (q_posedge_pulse_o || q_negedge_pulse_o));`
- `stable_no_pulse`: The bug occurs only on transitions, not on stable cycles.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) (d_i == q_sync_o) |-> !(q_posedge_pulse_o || q_negedge_pulse_o));`

## Next Step

Create `tb.v`, `tb_holdout.v`, regenerate waveforms, then run golden self-check and hardness gates before admitting this case.
