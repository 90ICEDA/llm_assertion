# case122_prim_count_incdec_not_cancelled

- `bug_class`: temporal_cross_cycle
- `bug_family`: action_priority
- `bug_type`: simultaneous increment and decrement no longer cancel

## Spec

When incr_en_i and decr_en_i are asserted together in the same cycle, the counter shall remain unchanged on the next cycle.

## Hardness Rationale

This is a classic corner that broad monotonicity checks miss because both individual actions still behave sensibly.

## Stimulus Notes

Prime the count away from saturation, then issue simultaneous incr/decr with commit_i high. Held-out should vary the pre-count value.

## Loose Negative Controls

- `increment_works`: Single-action behavior can remain correct while the simultaneous-action corner breaks.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) (commit_i && incr_en_i && !decr_en_i) |=> (cnt_o >= $past(cnt_o)));`
- `decrement_works`: It ignores the double-asserted corner.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) (commit_i && decr_en_i && !incr_en_i) |=> (cnt_o <= $past(cnt_o)));`

## Next Step

Create `tb.v`, `tb_holdout.v`, regenerate waveforms, then run golden self-check and hardness gates before admitting this case.
