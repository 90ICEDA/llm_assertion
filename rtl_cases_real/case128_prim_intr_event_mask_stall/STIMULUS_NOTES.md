# case128_prim_intr_event_mask_stall

- `bug_class`: temporal_cross_cycle
- `bug_family`: event_visibility_latency
- `bug_type`: new event is not visible until external state feedback catches up

## Spec

With FlopOutput enabled, a fresh event shall appear at intr_o on the next cycle even before software state feedback loops around.

## Hardness Rationale

This is a good example where 'event eventually becomes visible' is too weak; the one-cycle latency contract matters.

## Stimulus Notes

Keep state feedback low, pulse event_intr_i high for one cycle, and sample intr_o on the next cycle. Held-out should use a pre-existing state clear before the event pulse.

## Loose Negative Controls

- `event_updates_state`: The state-update side can still behave correctly while output visibility lags.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) event_intr_i |-> hw2reg_intr_state_de_o);`
- `masked_interrupt_low`: The bug occurs on enabled event visibility, not masked suppression.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) (!reg2hw_intr_enable_q_i) |-> !intr_o);`

## Next Step

Create `tb.v`, `tb_holdout.v`, regenerate waveforms, then run golden self-check and hardness gates before admitting this case.
