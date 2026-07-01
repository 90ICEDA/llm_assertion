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
