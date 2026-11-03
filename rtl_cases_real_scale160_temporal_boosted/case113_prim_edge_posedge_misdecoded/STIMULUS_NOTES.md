# case113_prim_edge_posedge_misdecoded

- `bug_class`: temporal_cross_cycle
- `bug_family`: edge_direction
- `bug_type`: posedge output decodes negedge

## Spec

q_posedge_pulse_o shall pulse for exactly the sampled 0->1 transition and not for 1->0 transitions.

## Hardness Rationale

A broad 'signal changes cause a pulse' assertion is too loose; only exact edge polarity catches this mutation.

## Stimulus Notes

Use EnSync=0 in wrapper and toggle d_i 0->1 and 1->0 on separate cycles. Held-out should repeat with longer high/low runs between edges.

## Loose Negative Controls

- `some_event_on_change`: The buggy design still produces an event pulse, just on the wrong output.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) (d_i != q_sync_o) |-> (q_posedge_pulse_o || q_negedge_pulse_o));`
- `pulse_is_onehot`: Wrong polarity can still satisfy one-hot pulse exclusivity.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) !(q_posedge_pulse_o && q_negedge_pulse_o));`

## Next Step

Create `tb.v`, `tb_holdout.v`, regenerate waveforms, then run golden self-check and hardness gates before admitting this case.

## Overfit Decoy

- Source: `self held-out trace with a decoy idle perturbation`
- Lure: Decoy trace preserves the same temporal trigger for posedge output decodes negedge through self held-out trace with a decoy idle perturbation, but shifts surrounding prelude timing so the assertion must generalize beyond the seen trace.
- Files: `tb_decoy.v`, `waveform_good_decoy.csv`, `waveform_bad_decoy.csv`

