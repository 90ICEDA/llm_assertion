# case121_prim_count_commit_ignored

- `bug_class`: temporal_cross_cycle
- `bug_family`: commit_gating
- `bug_type`: counter updates even when commit_i is low

## Spec

Counter state shall only change on a cycle where a requested action is also committed with commit_i high.

## Hardness Rationale

The bug is architectural, not structural: the counter can remain self-consistent while violating the exact commit semantics.

## Stimulus Notes

Request increments with commit_i low, then confirm cnt_o does not move until a committed action. Held-out should use different step_i literals.

## Loose Negative Controls

- `committed_increments_only`: It ignores the uncommitted update case entirely.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) (commit_i && incr_en_i && !decr_en_i) |=> (cnt_o >= $past(cnt_o)));`
- `error_stays_low`: The cross-counter consistency can remain intact even though commit gating is broken.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) !err_o);`

## Next Step

Create `tb.v`, `tb_holdout.v`, regenerate waveforms, then run golden self-check and hardness gates before admitting this case.
