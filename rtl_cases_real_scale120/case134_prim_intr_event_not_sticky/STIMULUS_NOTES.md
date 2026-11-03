# case134_prim_intr_event_not_sticky

- `bug_class`: temporal_cross_cycle
- `bug_family`: event_latching
- `bug_type`: event interrupt state drops when the source pulse goes away

## Spec

In Event mode, a captured event shall remain latched in the interrupt state until software clears it.

## Hardness Rationale

A momentary event makes this easy to miss with generic 'event seen' wording. The contract is specifically about retention across cycles.

## Stimulus Notes

Pulse event_intr_i high for one cycle under enable, then keep it low without clearing state. Held-out should insert an extra idle cycle before the pulse.

## Loose Negative Controls

- `event_sets_state_next_cycle`: It checks only that the sampled hardware event arrived while enabled, not whether the interrupt stayed latched afterward.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) event_intr_i |-> reg2hw_intr_enable_q_i);`
- `masked_interrupt_low`: The bug is about event retention while enabled, not masked behavior.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) (!reg2hw_intr_enable_q_i) |-> !intr_o);`

## Next Step

Create `tb.v`, `tb_holdout.v`, regenerate waveforms, then run golden self-check and hardness gates before admitting this case.

## Overfit Decoy

- Source: `self held-out trace with a decoy idle perturbation`
- Lure: Decoy trace preserves the same temporal trigger for event interrupt state drops when the source pulse goes away through self held-out trace with a decoy idle perturbation, but shifts surrounding prelude timing so the assertion must generalize beyond the seen trace.
- Files: `tb_decoy.v`, `waveform_good_decoy.csv`, `waveform_bad_decoy.csv`

