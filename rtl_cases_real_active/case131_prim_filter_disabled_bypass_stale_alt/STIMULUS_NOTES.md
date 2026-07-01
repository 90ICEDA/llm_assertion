# case131_prim_filter_disabled_bypass_stale_alt

- `bug_class`: combination_same_cycle
- `bug_family`: filter_bypass_control
- `bug_type`: disabled filter bypass stays on stored state

## Spec

When enable_i is low, filter_o shall reflect the live filter_i input immediately rather than the stored filtered value.

## Hardness Rationale

This mutation preserves the filtered behavior and only breaks the control-path bypass. Assertions that focus on threshold behavior miss it.

## Stimulus Notes

Build up the stored value under enable_i, then switch to bypass from a `negedge` so the next sampled cycle must reflect the live input. Held-out should establish the opposite stored polarity before disabling.

## Loose Negative Controls

- `enabled_only`: It constrains only enabled operation and ignores the disabled bypass path entirely.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) enable_i |-> (filter_o == filter_o));`
- `steady_input_eventual_match`: The filtered path can still converge correctly while the disabled bypass path remains stale.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) (enable_i && filter_i && $past(filter_i)) |-> filter_o);`

## Next Step

Create `tb.v`, `tb_holdout.v`, regenerate waveforms, then run golden self-check and hardness gates before admitting this case.
