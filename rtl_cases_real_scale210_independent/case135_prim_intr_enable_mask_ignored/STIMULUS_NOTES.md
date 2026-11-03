# case135_prim_intr_enable_mask_ignored

- `bug_class`: combination_same_cycle
- `bug_family`: interrupt_masking
- `bug_type`: interrupt output ignores the enable mask

## Spec

Even if interrupt state is set, intr_o shall be low in any sampled cycle where reg2hw_intr_enable_q_i is low.

## Hardness Rationale

Many loose interrupt assertions check only that enabled events become visible. The hard part is checking the exact masked corner after state has already gone high.

## Stimulus Notes

Raise interrupt state first, then drop reg2hw_intr_enable_q_i while holding state high. Held-out should do the same after a different event prelude.

## Loose Negative Controls

- `event_updates_state`: State-update correctness says nothing about whether the mask is applied at the outgoing interrupt pin.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) event_intr_i |-> hw2reg_intr_state_de_o);`
- `enabled_event_visible`: The buggy design still satisfies enabled visibility while failing masked suppression after enable drops.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) (reg2hw_intr_enable_q_i && $past(reg2hw_intr_enable_q_i) && reg2hw_intr_state_q_i && $past(reg2hw_intr_state_q_i)) |-> intr_o);`

## Next Step

Create `tb.v`, `tb_holdout.v`, regenerate waveforms, then run golden self-check and hardness gates before admitting this case.

## Overfit Decoy

- Source: `donor primary trace from case289_intr_mask_v1_from_case135_prim_intr_enable_mask_ignored`
- Lure: Decoy trace replays the same same-cycle bug family for interrupt output ignores the enable mask through donor primary trace from case289_intr_mask_v1_from_case135_prim_intr_enable_mask_ignored, but changes surrounding legal context or idle spacing so literal pinning to the seen trace should fail.
- Files: `tb_decoy.v`, `waveform_good_decoy.csv`, `waveform_bad_decoy.csv`

