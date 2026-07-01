# case111_prim_intr_output_or_mask

- `bug_class`: combination_same_cycle
- `bug_family`: interrupt_masking
- `bug_type`: interrupt enable mask turned into OR

## Spec

The outgoing interrupt shall assert only when both the interrupt status and enable are high.

## Hardness Rationale

The internal event machinery can still look healthy while the externally visible mask logic is wrong.

## Stimulus Notes

Keep reg2hw_intr_state_q_i high while toggling enable. Held-out should build status via event feedback first, then mask it.

## Loose Negative Controls

- `event_implies_event_detect`: It ignores the mask/output relation entirely.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) event_intr_i |-> hw2reg_intr_state_de_o);`
- `status_can_raise_interrupt`: It is too permissive and allows masked cycles to escape.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) reg2hw_intr_state_q_i |-> intr_o || !reg2hw_intr_enable_q_i);`

## Next Step

Create `tb.v`, `tb_holdout.v`, regenerate waveforms, then run golden self-check and hardness gates before admitting this case.
