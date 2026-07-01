# case116_prim_filter_late_accept

- `bug_class`: temporal_cross_cycle
- `bug_family`: filter_threshold
- `bug_type`: filtered output switches one cycle late

## Spec

With filtering enabled, filter_o shall adopt a new stable input after exactly Cycles consecutive opposite samples, not one cycle later.

## Hardness Rationale

This is precisely the kind of cross-cycle exact-length property that vague filtering assertions under-specify.

## Stimulus Notes

Hold filter_i low, then high for exactly 3 enabled cycles and sample the boundary. Held-out should use the opposite direction first.

## Loose Negative Controls

- `eventual_switch`: It allows the output to lag by an unspecified amount.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) (enable_i && filter_i) |-> (filter_o || $past(filter_o)));`
- `steady_input_implies_stable_output`: The bug occurs only while enabled and at the exact threshold boundary.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) (!enable_i) |-> (filter_o == filter_i));`

## Next Step

Create `tb.v`, `tb_holdout.v`, regenerate waveforms, then run golden self-check and hardness gates before admitting this case.
