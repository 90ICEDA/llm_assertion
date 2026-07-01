# case133_prim_edge_negedge_missing

- `bug_class`: temporal_cross_cycle
- `bug_family`: edge_presence
- `bug_type`: negedge pulse is dropped entirely

## Spec

A sampled 1->0 transition shall generate a one-cycle pulse on q_negedge_pulse_o.

## Hardness Rationale

Like the posedge variant, this needs the exact boundary relation rather than a vague pulse-exists check.

## Stimulus Notes

Drive a clean high interval first, then force a falling edge between sampled clocks. Held-out should interleave extra rises between the fall checks.

## Loose Negative Controls

- `pulse_onehot_only`: A missing negedge pulse still satisfies exclusivity.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) !(q_posedge_pulse_o && q_negedge_pulse_o));`
- `posedge_path_only`: The rising-edge path can stay correct while the falling-edge pulse disappears.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) (!$past(q_sync_o) && q_sync_o) |-> q_posedge_pulse_o);`

## Next Step

Create `tb.v`, `tb_holdout.v`, regenerate waveforms, then run golden self-check and hardness gates before admitting this case.
