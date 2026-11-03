# case139_prim_regwe_addr_check_false_positive

- `bug_class`: combination_same_cycle
- `bug_family`: write_enable_position_legality
- `bug_type`: legal nonzero write-enable spuriously fails an address-style check

## Spec

For prim_reg_we_check, a legal onehot write-enable vector with en_i high shall not raise err_o even when the hot bit is not bit 0.

## Hardness Rationale

This is another negative-correctness case: broad assertions about illegal write-enable shapes still pass, while a precise legal-bit-position check is needed to catch the false positive.

## Stimulus Notes

Drive a stable legal onehot on bit 1 and later on bit 2 while en_i stays high. Held-out should use a different legal onehot position than the primary trace.

## Loose Negative Controls

- `zero_when_enabled_ok`: The bug hits legal nonzero write enables, not the enabled zero-hot corner.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) ((oh_i == 4'b0000) && en_i) |-> !err_o);`
- `multihot_must_error`: The mutation preserves obviously illegal multihot rejection and only breaks legal nonzero onehot requests.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) (((oh_i == 4'b0011) || (oh_i == 4'b1010) || (oh_i == 4'b1100)) && en_i) |-> err_o);`

## Next Step

Create `tb.v`, `tb_holdout.v`, regenerate waveforms, then run golden self-check and hardness gates before admitting this case.

## Overfit Decoy

- Source: `self held-out trace with a decoy idle perturbation`
- Lure: Seen trace pins a legal bit-1 request; held-out switches to a different legal onehot so position literals alone stop working.
- Files: `tb_decoy.v`, `waveform_good_decoy.csv`, `waveform_bad_decoy.csv`

