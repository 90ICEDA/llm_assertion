# case110_prim_intr_event_overwrite

- `bug_class`: temporal_cross_cycle
- `bug_family`: event_state_accumulation
- `bug_type`: event state overwrite instead of hold-until-clear

## Spec

For Event interrupts, once a new event sets the interrupt state, the state shall remain set across subsequent cycles until software clears it.

## Hardness Rationale

This is exactly the kind of hold-state bug that vague 'event causes interrupt' assertions miss. The state is set once, then silently forgotten.

## Stimulus Notes

Model the CSR state feedback in tb, set an event, idle without clearing, and confirm state persistence. Held-out should insert a test pulse before the persistent hold check.

## Loose Negative Controls

- `event_sets_state_once`: The buggy design still latches the event state into the external feedback register; it only loses the enabled interrupt visibility afterward.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) (event_intr_i && reg2hw_intr_enable_q_i) |=> reg2hw_intr_state_q_i);`
- `masked_interrupt_low`: The bug is about losing a latched enabled interrupt, not masked behavior.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) (!reg2hw_intr_enable_q_i) |-> !intr_o);`

## Next Step

Create `tb.v`, `tb_holdout.v`, regenerate waveforms, then run golden self-check and hardness gates before admitting this case.

## Overfit Decoy

- Source: `self held-out trace with a decoy idle perturbation`
- Lure: Decoy trace preserves the same temporal trigger for event state overwrite instead of hold-until-clear through self held-out trace with a decoy idle perturbation, but shifts surrounding prelude timing so the assertion must generalize beyond the seen trace.
- Files: `tb_decoy.v`, `waveform_good_decoy.csv`, `waveform_bad_decoy.csv`

## Temporal Bootstrap Variant

- Variant case: `case303_rotate_tracks_from_case110_prim_intr_event_overwrite`
- Seed case: `case110_prim_intr_event_overwrite`
- Track plan: `rotate_all_tracks`
- Primary trace source: `holdout`
- Held-out trace source: `decoy`
- Decoy trace source: `primary`
- Validation basis: inherited from the seed case's track-level formal golden report and hardness/divergence gates.
