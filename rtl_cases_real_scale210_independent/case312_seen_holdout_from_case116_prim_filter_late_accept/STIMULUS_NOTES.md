# case116_prim_filter_late_accept

- `bug_class`: temporal_cross_cycle
- `bug_family`: filter_threshold
- `bug_type`: filtered output switches one cycle late

## Spec

With filtering enabled, filter_o shall adopt a new stable input at the exact acceptance boundary, not one sampled cycle later.

## Hardness Rationale

This is precisely the kind of cross-cycle boundary condition that vague "eventually follows the input" assertions under-specify.

## Stimulus Notes

With `Cycles=2`, drive the new value from a `negedge` so the second agreeing enabled `posedge` is the exact acceptance boundary. The wrapper now exposes a one-shot `accept_boundary_dbg` pulse on that sampled cycle. Held-out should first establish the opposite stored polarity, then test the same two-sample boundary in the reverse direction.

## Loose Negative Controls

- `eventual_switch`: It allows the output to lag by an unspecified amount.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) (enable_i && filter_i) |-> (filter_o || $past(filter_o)));`
- `steady_input_implies_stable_output`: The bug occurs only while enabled and at the exact threshold boundary.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) (!enable_i) |-> (filter_o == filter_i));`

## Admission Status

Completed. `tb.v` and `tb_holdout.v` now drive the exact threshold boundary, the wrapper exposes the one-shot `accept_boundary_dbg` observer, and the case has passed both the golden self-check and the hard-case admission gate.

## Overfit Decoy

- Source: `self held-out trace with a decoy idle perturbation`
- Lure: Use Cycles=3 with trace runs like 000111 so trace methods see tempting literal streaks.
- Files: `tb_decoy.v`, `waveform_good_decoy.csv`, `waveform_bad_decoy.csv`

## Temporal Bootstrap Variant

- Variant case: `case312_seen_holdout_from_case116_prim_filter_late_accept`
- Seed case: `case116_prim_filter_late_accept`
- Track plan: `seen_from_holdout`
- Primary trace source: `holdout`
- Held-out trace source: `primary`
- Decoy trace source: `decoy`
- Validation basis: inherited from the seed case's track-level formal golden report and hardness/divergence gates.
