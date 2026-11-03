# case117_prim_filter_bypass_stale

- `bug_class`: temporal_cross_cycle
- `bug_family`: filter_bypass_control
- `bug_type`: disabled bypass returns stale filtered state

## Spec

When enable_i is low, filter_o shall immediately bypass to the current input rather than the stored filtered state.

## Hardness Rationale

This is not a basic functionality failure; the filter still behaves plausibly while enabled. The bug hides in the exact bypass semantics.

## Stimulus Notes

Prime the stored value while enabled, then drive the bypass transition from a `negedge` so the first disabled `posedge` cleanly exposes stale-vs-live behavior. Held-out should repeat the same pattern with the opposite stored polarity.

## Loose Negative Controls

- `enabled_threshold_only`: It ignores the disabled bypass path where this bug lives.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) (enable_i && filter_i) |-> (filter_o || $past(filter_o)));`
- `stored_value_eventual_match`: It allows stale filtered output to look acceptable.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) filter_o |-> filter_i || $past(filter_i));`

## Next Step

Create `tb.v`, `tb_holdout.v`, regenerate waveforms, then run golden self-check and hardness gates before admitting this case.

## Overfit Decoy

- Source: `self held-out trace with a decoy idle perturbation`
- Lure: Decoy trace preserves the same temporal trigger for disabled bypass returns stale filtered state through self held-out trace with a decoy idle perturbation, but shifts surrounding prelude timing so the assertion must generalize beyond the seen trace.
- Files: `tb_decoy.v`, `waveform_good_decoy.csv`, `waveform_bad_decoy.csv`

## Temporal Bootstrap Variant

- Variant case: `case314_seen_holdout_from_case117_prim_filter_bypass_stale`
- Seed case: `case117_prim_filter_bypass_stale`
- Track plan: `seen_from_holdout`
- Primary trace source: `holdout`
- Held-out trace source: `primary`
- Decoy trace source: `decoy`
- Validation basis: inherited from the seed case's track-level formal golden report and hardness/divergence gates.
