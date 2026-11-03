# case122_prim_filter_ctr_streak_reset_ignored

- `bug_class`: temporal_cross_cycle
- `bug_family`: filter_counter_reset
- `bug_type`: counter-based filter keeps stale progress after the candidate polarity flips

## Spec

When the candidate polarity flips, the counter-based filter shall discard stale progress from the previous polarity; two samples of the new value are still not enough to switch the output at threshold two.

## Hardness Rationale

This bug hides in exact temporal bookkeeping: the counter state looks plausible, but the module wrongly reuses progress from the previous polarity. Broad 'eventually follows after stability' assertions are too weak to pin down that reset rule.

## Stimulus Notes

With thresh_i=2, first build stale progress for one polarity, then flip filter_i and provide exactly two samples of the new value. The wrapper exports second_new_sample_dbg on that second sample so the golden can check that filter_o still opposes filter_i. Held-out should mirror the same check in the opposite direction.

## Loose Negative Controls

- `eventual_accept_after_stability`: Two consecutive agreeing samples can still work; the bug is specifically that interrupted streaks are not reset.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) (enable_i && filter_i && $past(filter_i)) |-> (filter_o || $past(filter_o)));`
- `disabled_bypass_only`: The disabled bypass can stay perfectly correct while the enabled acceptance counter silently carries stale progress across a chatter interruption.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) (!enable_i) |-> (filter_o == filter_i));`

## Next Step

Create `tb.v`, `tb_holdout.v`, regenerate waveforms, then run golden self-check and hardness gates before admitting this case.

## Overfit Decoy

- Source: `self held-out trace with a decoy idle perturbation`
- Lure: Primary traces should include a tempting 0,1,1 boundary and held-out should mirror it with 1,0,0 so trace-heavy methods can overfit concrete bit runs instead of the polarity-flip rule.
- Files: `tb_decoy.v`, `waveform_good_decoy.csv`, `waveform_bad_decoy.csv`

## Temporal Bootstrap Variant

- Variant case: `case322_seen_holdout_from_case122_prim_filter_ctr_streak_reset_ignored`
- Seed case: `case122_prim_filter_ctr_streak_reset_ignored`
- Track plan: `seen_from_holdout`
- Primary trace source: `holdout`
- Held-out trace source: `primary`
- Decoy trace source: `decoy`
- Validation basis: inherited from the seed case's track-level formal golden report and hardness/divergence gates.
