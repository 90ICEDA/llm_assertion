# case140_prim_onehot_legal_request_false_positive

- `bug_class`: combination_same_cycle
- `bug_family`: enable_consistency_false_positive
- `bug_type`: legal enabled onehot request spuriously raises enable mismatch error

## Spec

With exactly one bit of oh_i high, matching addr_i, and en_i high, err_o shall remain low in the same cycle.

## Hardness Rationale

This is a clean false-positive case: broad assertions about illegal inputs or zero-hot behavior still pass, while only an exact legal-request check catches the regression.

## Stimulus Notes

Drive stable legal onehot/address matches while en_i stays high. Held-out should use a different legal requester/address pair than the primary trace.

## Loose Negative Controls

- `illegal_must_error`: The mutation still flags obviously illegal address mismatches; it only creates a false positive on a legal request.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) ((((oh_i == 4'b0100) && (addr_i == 2'd0)) || ((oh_i == 4'b1000) && (addr_i == 2'd1))) && en_i) |-> err_o);`
- `zero_enabled_only`: It says nothing about whether a legal active onehot request incorrectly raises err_o.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) ((oh_i == 4'b0000) && en_i) |-> err_o || !err_o);`

## Next Step

Create `tb.v`, `tb_holdout.v`, regenerate waveforms, then run golden self-check and hardness gates before admitting this case.

## Overfit Decoy

- Source: `self held-out trace with a decoy idle perturbation`
- Lure: Seen trace uses the legal 0010/addr=1 corner; held-out changes to 0100/addr=2 so literal request memorization breaks.
- Files: `tb_decoy.v`, `waveform_good_decoy.csv`, `waveform_bad_decoy.csv`

