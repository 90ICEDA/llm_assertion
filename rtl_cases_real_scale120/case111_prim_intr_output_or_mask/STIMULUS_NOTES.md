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
- `status_can_raise_interrupt`: It checks only the enabled visibility case and ignores the masked-state corner where the OR bug leaks through.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) (reg2hw_intr_enable_q_i && $past(reg2hw_intr_enable_q_i) && reg2hw_intr_state_q_i && $past(reg2hw_intr_state_q_i)) |-> intr_o);`

## Next Step

Create `tb.v`, `tb_holdout.v`, regenerate waveforms, then run golden self-check and hardness gates before admitting this case.

## Overfit Decoy

- Source: `donor primary trace from case284_intr_mask_v1_from_case111_prim_intr_output_or_mask`
- Lure: Decoy trace replays the same same-cycle bug family for interrupt enable mask turned into OR through donor primary trace from case284_intr_mask_v1_from_case111_prim_intr_output_or_mask, but changes surrounding legal context or idle spacing so literal pinning to the seen trace should fail.
- Files: `tb_decoy.v`, `waveform_good_decoy.csv`, `waveform_bad_decoy.csv`

