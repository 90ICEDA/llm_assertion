# case119_prim_filter_ctr_late_accept

- `bug_class`: temporal_cross_cycle
- `bug_family`: filter_threshold
- `bug_type`: counter-based filter accepts one cycle late

## Spec

With filtering enabled, filter_o shall switch by the exact threshold cycle rather than lagging by one extra sample.

## Hardness Rationale

This is a clean exact-threshold bug with a natural trace-summary overfit lure around the threshold literal.

## Stimulus Notes

Run one case with thresh_i=2 in the prompt trace and another hidden held-out check with thresh_i=3.

## Loose Negative Controls

- `two_or_more_highs_eventually_high`: It permits an unspecified extra cycle of latency.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) (enable_i && filter_i) |-> (filter_o || $past(filter_o)));`
- `no_glitch_when_disabled`: The bug is in enabled threshold timing, not in bypass mode.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) (!enable_i) |-> (filter_o == filter_i));`

## Next Step

Create `tb.v`, `tb_holdout.v`, regenerate waveforms, then run golden self-check and hardness gates before admitting this case.

## Overfit Decoy

- Source: `self held-out trace with a decoy idle perturbation`
- Lure: Use primary trace threshold 2 and held-out threshold 3 so literal hard-coding can be detected.
- Files: `tb_decoy.v`, `waveform_good_decoy.csv`, `waveform_bad_decoy.csv`

## Temporal Bootstrap Variant

- Variant case: `case318_seen_holdout_from_case119_prim_filter_ctr_late_accept`
- Seed case: `case119_prim_filter_ctr_late_accept`
- Track plan: `seen_from_holdout_decoy_from_holdout`
- Primary trace source: `holdout`
- Held-out trace source: `primary`
- Decoy trace source: `holdout`
- Validation basis: inherited from the seed case's track-level formal golden report and hardness/divergence gates.
