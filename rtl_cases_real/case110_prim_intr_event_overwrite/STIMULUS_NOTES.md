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

- `event_sets_state_once`: The bug still raises de_o when the event first arrives.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) event_intr_i |-> hw2reg_intr_state_de_o);`
- `interrupt_requires_enable`: The enable path can remain correct while the stored event is lost a cycle later.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) intr_o |-> reg2hw_intr_enable_q_i);`

## Next Step

Create `tb.v`, `tb_holdout.v`, regenerate waveforms, then run golden self-check and hardness gates before admitting this case.
