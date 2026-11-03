# case127_prim_intr_status_test_qe_ignored

- `bug_class`: temporal_cross_cycle
- `bug_family`: status_test_gate
- `bug_type`: status-mode test data is latched even when the qe gate is low

## Spec

In Status mode, reg2hw_intr_test_q_i shall affect the latched test state only on cycles where reg2hw_intr_test_qe_i is asserted.

## Hardness Rationale

This is a pure control-lifetime bug. Assertions that only verify normal event behavior or legitimate test writes will miss that qe-low data can still arm the flopped output one cycle later.

## Stimulus Notes

Keep event_intr_i low, reg2hw_intr_enable_q_i high, and drive reg2hw_intr_test_q_i=1 with reg2hw_intr_test_qe_i=0; the following sampled cycle must still keep intr_o low. Held-out should first exercise a legitimate qe-high test write, clear it, and then re-run the qe-low leak check.

## Loose Negative Controls

- `real_status_event_visible`: The real event path can remain correct while qe-low test data leaks into the latched status state.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) (event_intr_i && reg2hw_intr_enable_q_i) |=> intr_o);`
- `qe_high_test_visible`: It only checks the legitimate qe-high software-test path and does not constrain the qe-low leak at all.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) (reg2hw_intr_test_qe_i && reg2hw_intr_test_q_i && reg2hw_intr_enable_q_i) |=> intr_o);`

## Next Step

Create `tb.v`, `tb_holdout.v`, regenerate waveforms, then run golden self-check and hardness gates before admitting this case.

## Overfit Decoy

- Source: `self held-out trace with a decoy idle perturbation`
- Lure: Primary traces should keep event_intr_i at 0 while holding test_q_i at 1 with qe low so trace-driven methods are tempted to memorize the obvious literal corner.
- Files: `tb_decoy.v`, `waveform_good_decoy.csv`, `waveform_bad_decoy.csv`

