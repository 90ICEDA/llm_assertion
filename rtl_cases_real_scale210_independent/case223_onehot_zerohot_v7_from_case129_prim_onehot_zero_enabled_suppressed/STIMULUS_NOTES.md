# case129_prim_onehot_zero_enabled_suppressed

- `bug_class`: combination_same_cycle
- `bug_family`: enable_consistency
- `bug_type`: zero-hot while enabled is no longer rejected

## Spec

With strict checking enabled, en_i high with oh_i equal to zero shall assert err_o in the same sampled cycle.

## Hardness Rationale

A broad 'onehot or enabled' check can still pass here. The useful assertion has to name the strict zero-hot-while-enabled corner explicitly.

## Stimulus Notes

Drive a legal onehot first, then hold en_i high while forcing oh_i to 4'b0000. Held-out should reuse a different surrounding onehot pattern before the same strict zero-hot corner.

## Loose Negative Controls

- `request_implies_enable`: It constrains only active-request cases and says nothing about enabled-zero.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) ((oh_i == 4'b0001) || (oh_i == 4'b0010) || (oh_i == 4'b0100) || (oh_i == 4'b1000)) |-> en_i);`
- `multihot_only`: The mutation leaves multihot detection intact and only breaks the strict zero-hot corner.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) (((oh_i == 4'b0011) || (oh_i == 4'b0101) || (oh_i == 4'b0110) || (oh_i == 4'b0111) || (oh_i == 4'b1001) || (oh_i == 4'b1010) || (oh_i == 4'b1011) || (oh_i == 4'b1100) || (oh_i == 4'b1101) || (oh_i == 4'b1110) || (oh_i == 4'b1111)) |-> err_o);`

## Next Step

Create `tb.v`, `tb_holdout.v`, regenerate waveforms, then run golden self-check and hardness gates before admitting this case.

## Overfit Decoy

- Source: `donor primary trace from case224_onehot_zerohot_v8_from_case129_prim_onehot_zero_enabled_suppressed`
- Lure: Seen legal wrappers use 0100/1000; held-out uses 0001/0010 around the same zero-hot mismatch.
- Files: `tb_decoy.v`, `waveform_good_decoy.csv`, `waveform_bad_decoy.csv`

