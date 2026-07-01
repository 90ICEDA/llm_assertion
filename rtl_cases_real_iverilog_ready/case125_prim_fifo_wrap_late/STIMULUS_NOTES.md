# case125_prim_fifo_wrap_late

- `bug_class`: temporal_cross_cycle
- `bug_family`: pointer_wrap
- `bug_type`: write pointer wraps one cycle late

## Spec

When the write pointer is at Depth-1 and a write occurs, the internal write pointer shall wrap on the next cycle rather than stepping to an out-of-range state.

## Hardness Rationale

Boundary pointer semantics are much tighter than generic occupancy checks.

## Stimulus Notes

Drive four writes from reset and sample wptr_o at the wrap. Held-out should include a read before the final wrap sequence.

## Loose Negative Controls

- `depth_changes_on_write`: Occupancy can still move in the right direction while the pointer encoding is wrong at the boundary.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) incr_wptr_i |=> (depth_o >= $past(depth_o)));`
- `full_eventually_asserts`: It does not require the exact pointer wrap relation.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) (depth_o == 3'd3 && incr_wptr_i) |-> full_o || $past(full_o));`

## Next Step

Create `tb.v`, `tb_holdout.v`, regenerate waveforms, then run golden self-check and hardness gates before admitting this case.
