# case132_prim_edge_posedge_missing

- `bug_class`: temporal_cross_cycle
- `bug_family`: edge_presence
- `bug_type`: posedge pulse is dropped entirely

## Spec

A sampled 0->1 transition shall generate a one-cycle pulse on q_posedge_pulse_o.

## Hardness Rationale

A generic 'there is some pulse activity' statement is too weak; the exact rise-to-pulse contract matters.

## Stimulus Notes

Toggle d_i low-to-high between clock edges and sample the next posedge. Held-out should include a longer low dwell before the rise.

## Loose Negative Controls

- `pulse_onehot_only`: A completely missing posedge pulse still satisfies exclusivity.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) !(q_posedge_pulse_o && q_negedge_pulse_o));`
- `negedge_path_only`: The falling-edge path can remain correct while the rising-edge pulse disappears.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) ($past(q_sync_o) && !q_sync_o) |-> q_negedge_pulse_o);`

## Next Step

Create `tb.v`, `tb_holdout.v`, regenerate waveforms, then run golden self-check and hardness gates before admitting this case.

## Overfit Decoy

- Source: `self held-out trace with a decoy idle perturbation`
- Lure: Decoy trace preserves the same temporal trigger for posedge pulse is dropped entirely through self held-out trace with a decoy idle perturbation, but shifts surrounding prelude timing so the assertion must generalize beyond the seen trace.
- Files: `tb_decoy.v`, `waveform_good_decoy.csv`, `waveform_bad_decoy.csv`

## Temporal Bootstrap Variant

- Variant case: `case336_seen_decoy_from_case132_prim_edge_posedge_missing`
- Seed case: `case132_prim_edge_posedge_missing`
- Track plan: `seen_from_decoy`
- Primary trace source: `decoy`
- Held-out trace source: `holdout`
- Decoy trace source: `primary`
- Validation basis: inherited from the seed case's track-level formal golden report and hardness/divergence gates.
