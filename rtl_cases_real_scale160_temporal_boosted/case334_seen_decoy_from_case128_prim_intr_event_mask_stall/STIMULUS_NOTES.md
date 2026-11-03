# case128_prim_intr_event_mask_stall

- `bug_class`: temporal_cross_cycle
- `bug_family`: event_output_state_alignment
- `bug_type`: flopped interrupt output exposes pending next-state before committed state feedback

## Spec

With FlopOutput enabled in Event mode, intr_o shall be derived from the committed interrupt state feedback, not from the speculative next-state in the same event cycle.

## Hardness Rationale

This is a source-alignment timing bug: broad assertions about eventual interrupt visibility or state update still pass, but an exact committed-state contract catches it.

## Stimulus Notes

Keep committed state feedback low, pulse `event_intr_i` from a `negedge`, and check that `intr_o` stays low on the following sampled cycle. Held-out should clear committed state first, then repeat the same check on a later event pulse.

## Loose Negative Controls

- `event_updates_state`: The state-update side can still behave correctly even if the flopped output reads the wrong source too early.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) event_intr_i |-> hw2reg_intr_state_de_o);`
- `masked_interrupt_low`: The bug occurs while enabled, as an early visible pulse, not as masked suppression.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) (!reg2hw_intr_enable_q_i) |-> !intr_o);`

## Next Step

Create `tb.v`, `tb_holdout.v`, regenerate waveforms, then run golden self-check and hardness gates before admitting this case.

## Overfit Decoy

- Source: `self held-out trace with a decoy idle perturbation`
- Lure: Decoy trace preserves the same temporal trigger for flopped interrupt output exposes pending next-state before committed state feedback through self held-out trace with a decoy idle perturbation, but shifts surrounding prelude timing so the assertion must generalize beyond the seen trace.
- Files: `tb_decoy.v`, `waveform_good_decoy.csv`, `waveform_bad_decoy.csv`

## Temporal Bootstrap Variant

- Variant case: `case334_seen_decoy_from_case128_prim_intr_event_mask_stall`
- Seed case: `case128_prim_intr_event_mask_stall`
- Track plan: `seen_from_decoy`
- Primary trace source: `decoy`
- Held-out trace source: `holdout`
- Decoy trace source: `primary`
- Validation basis: inherited from the seed case's track-level formal golden report and hardness/divergence gates.
