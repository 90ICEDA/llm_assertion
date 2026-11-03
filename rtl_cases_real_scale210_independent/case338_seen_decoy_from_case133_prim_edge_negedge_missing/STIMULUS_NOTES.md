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

## Overfit Decoy

- Source: `self held-out trace with a decoy idle perturbation`
- Lure: Decoy trace preserves the same temporal trigger for negedge pulse is dropped entirely through self held-out trace with a decoy idle perturbation, but shifts surrounding prelude timing so the assertion must generalize beyond the seen trace.
- Files: `tb_decoy.v`, `waveform_good_decoy.csv`, `waveform_bad_decoy.csv`

## Temporal Bootstrap Variant

- Variant case: `case338_seen_decoy_from_case133_prim_edge_negedge_missing`
- Seed case: `case133_prim_edge_negedge_missing`
- Track plan: `seen_from_decoy`
- Primary trace source: `decoy`
- Held-out trace source: `holdout`
- Decoy trace source: `primary`
- Validation basis: inherited from the seed case's track-level formal golden report and hardness/divergence gates.
