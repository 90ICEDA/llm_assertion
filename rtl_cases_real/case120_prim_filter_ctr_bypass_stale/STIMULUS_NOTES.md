# case120_prim_filter_ctr_bypass_stale

- `bug_class`: temporal_cross_cycle
- `bug_family`: filter_bypass_control
- `bug_type`: counter-based filter bypass returns stale state

## Spec

When enable_i is low, filter_o shall bypass to the current input rather than stay at the previously stored filtered value.

## Hardness Rationale

Like the shift-register filter bypass case, this bug hides in control gating rather than headline functionality.

## Stimulus Notes

Prime stored state, disable filtering, and toggle filter_i immediately. Held-out should reverse the polarity of the stale stored value.

## Loose Negative Controls

- `enabled_eventual_accept`: It only constrains the enabled filtering path.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) enable_i && filter_i |-> (filter_o || $past(filter_o)));`
- `threshold_nonzero`: It is effectively unconstrained and misses the bypass bug entirely.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) enable_i |-> (thresh_i != '0 || thresh_i == '0));`

## Next Step

Create `tb.v`, `tb_holdout.v`, regenerate waveforms, then run golden self-check and hardness gates before admitting this case.
