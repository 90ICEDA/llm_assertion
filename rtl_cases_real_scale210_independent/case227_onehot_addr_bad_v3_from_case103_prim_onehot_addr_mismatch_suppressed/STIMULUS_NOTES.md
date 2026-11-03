# case103_prim_onehot_addr_mismatch_suppressed

- `bug_class`: combination_same_cycle
- `bug_family`: decoded_index_consistency
- `bug_type`: address mismatch error suppressed

## Spec

If exactly one bit of oh_i is high, err_o shall assert when addr_i points to a different bit in the same cycle.

## Hardness Rationale

The bug is not about onehotness; it is about exact bit-to-index consistency. General 'onehot legal' assertions will miss it.

## Stimulus Notes

Hold oh_i onehot while sweeping addr_i across both matching and mismatching values. Held-out should use different active bits.

## Loose Negative Controls

- `enable_consistency_only`: en_i can still match |oh_i| even when addr_i points to the wrong position.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) (((|oh_i) ^ en_i)) |-> err_o);`
- `any_request_valid`: It treats any asserted onehot vector as valid and therefore misses the index mismatch.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) (|oh_i) |-> !err_o);`

## Next Step

Create `tb.v`, `tb_holdout.v`, regenerate waveforms, then run golden self-check and hardness gates before admitting this case.

## Overfit Decoy

- Source: `donor primary trace from case228_onehot_addr_bad_v4_from_case103_prim_onehot_addr_mismatch_suppressed`
- Lure: Seen mismatch pair is (4'b0010, 3); held-out swaps to (4'b0100, 1).
- Files: `tb_decoy.v`, `waveform_good_decoy.csv`, `waveform_bad_decoy.csv`

