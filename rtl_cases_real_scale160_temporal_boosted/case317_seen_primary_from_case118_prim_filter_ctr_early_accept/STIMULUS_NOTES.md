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

## Overfit Decoy

- Source: `self held-out trace with a decoy idle perturbation`
- Lure: Use thresh_i values like 2 and 3 in primary traces to tempt constant pinning.
- Files: `tb_decoy.v`, `waveform_good_decoy.csv`, `waveform_bad_decoy.csv`

## Temporal Bootstrap Variant

- Variant case: `case317_seen_primary_from_case118_prim_filter_ctr_early_accept`
- Seed case: `case118_prim_filter_ctr_early_accept`
- Track plan: `seen_from_primary_decoy_from_holdout`
- Primary trace source: `primary`
- Held-out trace source: `holdout`
- Decoy trace source: `holdout`
- Validation basis: inherited from the seed case's track-level formal golden report and hardness/divergence gates.
