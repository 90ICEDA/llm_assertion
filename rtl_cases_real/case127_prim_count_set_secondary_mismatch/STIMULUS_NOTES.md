# case127_prim_count_set_secondary_mismatch

- `bug_class`: temporal_cross_cycle
- `bug_family`: set_semantics
- `bug_type`: secondary mirror set value no longer complementary

## Spec

After a committed set action, the architectural count shall match set_cnt_i and the protected mirror logic shall remain internally consistent with no err_o assertion.

## Hardness Rationale

This case is valuable because a superficially correct architectural output can hide broken internal protection logic.

## Stimulus Notes

Apply a committed set_i pulse with several different set_cnt_i values. Held-out should use a different literal than the prompt trace.

## Loose Negative Controls

- `cnt_matches_set_only`: cnt_o can still look correct even though the secondary mirror and err_o behavior are corrupted.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) (commit_i && set_i) |=> (cnt_o == $past(set_cnt_i)));`
- `error_never_high_during_idle`: It ignores the specific set transition that injects the inconsistency.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) (!set_i && !incr_en_i && !decr_en_i) |-> !err_o);`

## Next Step

Create `tb.v`, `tb_holdout.v`, regenerate waveforms, then run golden self-check and hardness gates before admitting this case.
