# case138_prim_regwe_zero_enabled_false_positive

- `bug_class`: combination_same_cycle
- `bug_family`: masked_write_enable_legality
- `bug_type`: enabled zero-write vector spuriously flags an error

## Spec

For prim_reg_we_check, en_i high with oh_i equal to zero shall remain legal and must not raise err_o in the same cycle.

## Hardness Rationale

This is a negative-correctness case: broad assertions about obviously illegal write-enable patterns still pass, but only an exact enabled-zero legality check exposes the false positive.

## Stimulus Notes

Hold en_i high while driving oh_i at zero for multiple sampled cycles. Held-out should surround the zero-hot window with legal onehot activity so the false-positive corner is isolated.

## Loose Negative Controls

- `multihot_only`: It constrains only clearly illegal multihot cases and says nothing about a false positive on the enabled zero-hot corner.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) (((oh_i == 4'b0011) || (oh_i == 4'b0101) || (oh_i == 4'b0110) || (oh_i == 4'b0111) || (oh_i == 4'b1001) || (oh_i == 4'b1010) || (oh_i == 4'b1011) || (oh_i == 4'b1100) || (oh_i == 4'b1101) || (oh_i == 4'b1110) || (oh_i == 4'b1111)) |-> err_o);`
- `disabled_vector_only`: The mutation breaks the enabled zero-hot legality corner, not the disabled nonzero vector check.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) (!en_i && (oh_i == 4'b0100) && ($past(oh_i) == 4'b0100) && !$past(en_i)) |-> err_o);`

## Next Step

Create `tb.v`, `tb_holdout.v`, regenerate waveforms, then run golden self-check and hardness gates before admitting this case.

## Overfit Decoy

- Source: `self held-out trace with a decoy idle perturbation`
- Lure: Seen trace holds en_i=1 across a zero-hot window; held-out surrounds the same legality corner with different legal onehot preludes.
- Files: `tb_decoy.v`, `waveform_good_decoy.csv`, `waveform_bad_decoy.csv`

