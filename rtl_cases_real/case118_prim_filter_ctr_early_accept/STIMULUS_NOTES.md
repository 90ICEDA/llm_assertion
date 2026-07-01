# case118_prim_filter_ctr_early_accept

- `bug_class`: temporal_cross_cycle
- `bug_family`: filter_threshold
- `bug_type`: counter-based filter accepts one cycle early

## Spec

With filtering enabled, filter_o shall not switch until thresh_i consecutive agreeing samples have been observed.

## Hardness Rationale

An 'eventually filters the input' assertion is exactly the wrong abstraction here; the boundary cycle matters.

## Stimulus Notes

Start from low, drive high for one cycle less than threshold and confirm no switch, then hit threshold. Held-out should exercise a different threshold literal.

## Loose Negative Controls

- `eventual_accept`: It allows the switch to happen too soon.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) (enable_i && filter_i) |-> (filter_o || !$past(filter_o)));`
- `disabled_bypass_only`: It says nothing about the threshold timing while enabled.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) (!enable_i) |-> (filter_o == filter_i));`

## Next Step

Create `tb.v`, `tb_holdout.v`, regenerate waveforms, then run golden self-check and hardness gates before admitting this case.
