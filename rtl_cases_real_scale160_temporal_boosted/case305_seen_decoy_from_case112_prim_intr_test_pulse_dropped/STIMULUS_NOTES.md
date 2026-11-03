# case112_prim_intr_test_pulse_dropped

- `bug_class`: temporal_cross_cycle
- `bug_family`: test_pulse_capture
- `bug_type`: interrupt test write pulse is lost

## Spec

In Status mode, a software test pulse written through reg2hw_intr_test_qe_i shall be captured and reflected in the stored test_q state on the next cycle.

## Hardness Rationale

The test path is easy to overlook if assertions focus only on hardware events.

## Stimulus Notes

Instantiate Status mode, enable the interrupt, pulse reg2hw_intr_test_qe_i for one cycle, and watch the next-cycle output. Held-out should combine a test pulse with inactive event_intr_i.

## Loose Negative Controls

- `event_path_only`: It ignores the software-injected test path completely.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) event_intr_i |-> intr_o || !intr_o);`
- `qe_seen`: It is vacuous and does not check the captured effect.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) reg2hw_intr_test_qe_i |-> reg2hw_intr_test_qe_i);`

## Next Step

Create `tb.v`, `tb_holdout.v`, regenerate waveforms, then run golden self-check and hardness gates before admitting this case.

## Overfit Decoy

- Source: `self held-out trace with a decoy idle perturbation`
- Lure: Decoy trace preserves the same temporal trigger for interrupt test write pulse is lost through self held-out trace with a decoy idle perturbation, but shifts surrounding prelude timing so the assertion must generalize beyond the seen trace.
- Files: `tb_decoy.v`, `waveform_good_decoy.csv`, `waveform_bad_decoy.csv`

## Temporal Bootstrap Variant

- Variant case: `case305_seen_decoy_from_case112_prim_intr_test_pulse_dropped`
- Seed case: `case112_prim_intr_test_pulse_dropped`
- Track plan: `seen_from_decoy`
- Primary trace source: `decoy`
- Held-out trace source: `holdout`
- Decoy trace source: `primary`
- Validation basis: inherited from the seed case's track-level formal golden report and hardness/divergence gates.
