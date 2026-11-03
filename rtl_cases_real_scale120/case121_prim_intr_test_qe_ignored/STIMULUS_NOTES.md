# case121_prim_intr_test_qe_ignored

- `bug_class`: combination_same_cycle
- `bug_family`: event_test_gate
- `bug_type`: event-mode test data is consumed even when the qe gate is low

## Spec

In Event mode, reg2hw_intr_test_q_i shall have no effect unless reg2hw_intr_test_qe_i is asserted in the same cycle.

## Hardness Rationale

This is a classic control-gating hard case: broad assertions about event visibility or test functionality can all pass while qe-low leakage quietly violates the contract.

## Stimulus Notes

Hold reg2hw_intr_test_q_i high while keeping reg2hw_intr_test_qe_i low and event_intr_i low, then sample hw2reg_intr_state_de_o/hw2reg_intr_state_d_o. Held-out should inject the same qe-low leak after an earlier legitimate event cycle.

## Loose Negative Controls

- `real_event_updates_state`: Real events still propagate correctly; the bug hides only in the qe-low synthetic-event corner.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) event_intr_i |-> hw2reg_intr_state_de_o);`
- `qe_high_allows_test_event`: It constrains only the legitimate qe-high path and says nothing about stale test data leaking through qe-low.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) (reg2hw_intr_test_qe_i && reg2hw_intr_test_q_i) |-> hw2reg_intr_state_de_o);`

## Next Step

Create `tb.v`, `tb_holdout.v`, regenerate waveforms, then run golden self-check and hardness gates before admitting this case.

## Overfit Decoy

- Source: `self held-out trace with a decoy idle perturbation`
- Lure: Primary traces should pin the tempting literal corner test_q=1, qe=0, event=0 so trace-heavy methods can overfit the obvious constant pattern.
- Files: `tb_decoy.v`, `waveform_good_decoy.csv`, `waveform_bad_decoy.csv`

