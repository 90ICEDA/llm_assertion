# case137_prim_onehot_addr_false_positive

- `bug_class`: combination_same_cycle
- `bug_family`: decoded_index_consistency
- `bug_type`: legal onehot request spuriously flags address error

## Spec

If exactly one bit of oh_i is high and addr_i points to that bit, err_o shall remain low in the same cycle.

## Hardness Rationale

This is a good negative-correctness case: generic assertions about illegal inputs still pass, but only an exact legal-corner assertion exposes the spurious error.

## Stimulus Notes

Exercise both legal and illegal onehot/address pairs. Held-out should use a different legal bit/index match than the primary trace.

## Loose Negative Controls

- `illegal_must_error`: It constrains only obviously illegal address mismatches and says nothing about false positives on legal requests.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) ((((oh_i == 4'b0100) && (addr_i == 2'd0)) || ((oh_i == 4'b1000) && (addr_i == 2'd1))) && en_i) |-> err_o);`
- `multihot_implies_enable`: It only checks that an unrelated multihot stimulus was presented while enabled, so it says nothing about false positives on legal onehot requests.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) ((oh_i == 4'b1010) || (oh_i == 4'b1100)) |-> en_i);`

## Next Step

Create `tb.v`, `tb_holdout.v`, regenerate waveforms, then run golden self-check and hardness gates before admitting this case.
