# case136_prim_filter_ctr_disabled_bypass_stale_alt

- `bug_class`: combination_same_cycle
- `bug_family`: filter_bypass_control
- `bug_type`: counter-based disabled filter bypass stays on stored state

## Spec

When enable_i is low, the counter-based filter shall bypass to the current input in the same sampled cycle.

## Hardness Rationale

This keeps the counter machinery intact and only corrupts the disabled bypass path, which is exactly the kind of bug broad filter assertions tend to miss.

## Stimulus Notes

Accumulate the stored value while enabled, then switch into bypass from a `negedge` and flip `filter_i` so the next sampled cycle must match the live input. Held-out should establish the opposite stored polarity before disabling.

## Loose Negative Controls

- `enabled_threshold_only`: The threshold path can still look fine while the disabled bypass path is stale.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) (enable_i && filter_i) |-> (filter_o || $past(filter_o)));`
- `threshold_nonzero`: It never constrains the bypass output relation at all.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) enable_i |-> (thresh_i == thresh_i));`

## Next Step

Create `tb.v`, `tb_holdout.v`, regenerate waveforms, then run golden self-check and hardness gates before admitting this case.
