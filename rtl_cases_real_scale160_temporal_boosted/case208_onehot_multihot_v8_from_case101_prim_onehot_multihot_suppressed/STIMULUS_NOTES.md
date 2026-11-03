# case101_prim_onehot_multihot_suppressed

- `bug_class`: combination_same_cycle
- `bug_family`: onehot_violation_masked
- `bug_type`: multihot error suppressed

## Spec

When more than one bit of oh_i is high in the same cycle, err_o must assert in that same cycle.

## Hardness Rationale

A vague assertion like 'onehot input should be legal' can pass without explicitly checking the multihot corner. The precise bug appears only when two request bits are simultaneously high.

## Stimulus Notes

Drive legal onehot patterns first, then inject 4'b1010 and 4'b0110 while en_i is high. Held-out should use different multihot literals.

## Loose Negative Controls

- `enable_only`: It constrains only the disabled case and says nothing about multihot inputs while enabled.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) (!en_i) |-> !err_o);`
- `eventual_error`: It is too weak and does not require exact multihot detection.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) (|oh_i) |-> (err_o || en_i));`

## Next Step

Create `tb.v`, `tb_holdout.v`, regenerate waveforms, then run golden self-check and hardness gates before admitting this case.

## Overfit Decoy

- Source: `donor primary trace from case101_prim_onehot_multihot_suppressed`
- Lure: Seen trace still uses bug-revealing literal 4'b1010, but the surrounding legal context changes; held-out keeps 4'b1100.
- Files: `tb_decoy.v`, `waveform_good_decoy.csv`, `waveform_bad_decoy.csv`

