# case102_prim_onehot_enable_mismatch_suppressed

- `bug_class`: combination_same_cycle
- `bug_family`: enable_consistency
- `bug_type`: enable mismatch error suppressed

## Spec

With strict enable checking enabled, err_o shall assert whenever en_i disagrees with whether any onehot bit is set.

## Hardness Rationale

The mutation does not break basic onehot structure. Only an assertion that ties en_i exactly to the presence of a selected bit can expose it.

## Stimulus Notes

Use both mismatch directions: oh_i=0 with en_i=1, and oh_i=4'b0100 with en_i=0. Held-out should use different onehot positions.

## Loose Negative Controls

- `multihot_only`: It ignores the legal onehot-but-disabled and zero-hot-but-enabled mismatches.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) (((oh_i == 4'b0011) || (oh_i == 4'b0101) || (oh_i == 4'b0110) || (oh_i == 4'b0111) || (oh_i == 4'b1001) || (oh_i == 4'b1010) || (oh_i == 4'b1011) || (oh_i == 4'b1100) || (oh_i == 4'b1101) || (oh_i == 4'b1110) || (oh_i == 4'b1111)) |-> err_o);`
- `request_implies_enable`: It checks only one direction and misses the all-zero while enabled corner.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) (|oh_i) |-> en_i);`

## Next Step

Create `tb.v`, `tb_holdout.v`, regenerate waveforms, then run golden self-check and hardness gates before admitting this case.

## Overfit Decoy

- Source: `donor primary trace from case215_onehot_zerohot_v7_from_case102_prim_onehot_enable_mismatch_suppressed`
- Lure: Seen legal wrappers use 0010/0100; held-out uses 1000/0001 around the same zero-hot mismatch.
- Files: `tb_decoy.v`, `waveform_good_decoy.csv`, `waveform_bad_decoy.csv`

