# case126_prim_regwe_enable_gap

- `bug_class`: combination_same_cycle
- `bug_family`: register_write_enable_consistency
- `bug_type`: write-enable checker ignores enable mismatch

## Spec

When en_i is low, any nonzero onehot write-enable vector shall trigger err_o in the same cycle.

## Hardness Rationale

This module is a good same-cycle 'context matters' case: onehot legality alone is not enough; enable gating is part of correctness.

## Stimulus Notes

Drive legal onehot oh_i values while toggling en_i low. Held-out should use different bit positions and include an all-zero disabled control sample.

## Loose Negative Controls

- `multihot_only`: A legal onehot vector with en_i low is still illegal for this module but passes this looser check.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) (((oh_i == 4'b0011) || (oh_i == 4'b0101) || (oh_i == 4'b0110) || (oh_i == 4'b0111) || (oh_i == 4'b1001) || (oh_i == 4'b1010) || (oh_i == 4'b1011) || (oh_i == 4'b1100) || (oh_i == 4'b1101) || (oh_i == 4'b1110) || (oh_i == 4'b1111)) |-> err_o);`
- `zero_ok_when_disabled`: It only checks the easy disabled-zero corner.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) (!en_i && !(|oh_i)) |-> !err_o);`

## Next Step

Create `tb.v`, `tb_holdout.v`, regenerate waveforms, then run golden self-check and hardness gates before admitting this case.
