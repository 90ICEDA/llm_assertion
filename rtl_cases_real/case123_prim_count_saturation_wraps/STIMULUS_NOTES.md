# case123_prim_count_saturation_wraps

- `bug_class`: temporal_cross_cycle
- `bug_family`: saturation_boundary
- `bug_type`: overflow wraps instead of saturating

## Spec

When the counter is at its maximum value and receives a further increment, it shall remain saturated at max rather than wrap.

## Hardness Rationale

Boundary hold semantics are the key here. A generic increment rule is not enough.

## Stimulus Notes

Drive the count to max, issue one more increment, and sample the next cycle. Held-out should use a larger step_i that also overflows at the boundary.

## Loose Negative Controls

- `counter_changes_under_increment`: A wrap from max to 0 violates the precise boundary but broad increment behavior elsewhere still looks fine.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) (commit_i && incr_en_i && !decr_en_i) |=> (cnt_o >= $past(cnt_o)));`
- `no_error_flag`: Internal consistency can remain intact even while saturation semantics are broken.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) !err_o);`

## Next Step

Create `tb.v`, `tb_holdout.v`, regenerate waveforms, then run golden self-check and hardness gates before admitting this case.
