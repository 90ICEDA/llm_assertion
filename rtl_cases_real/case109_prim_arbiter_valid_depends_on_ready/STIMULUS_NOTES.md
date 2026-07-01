# case109_prim_arbiter_valid_depends_on_ready

- `bug_class`: combination_same_cycle
- `bug_family`: ready_valid_handshake
- `bug_type`: valid incorrectly drops under backpressure

## Spec

valid_o shall reflect pending requests even when ready_i is low; backpressure may block grant_o but not pending-valid indication.

## Hardness Rationale

A conservative handshake assertion often ignores the waiting state. This bug lives exactly there.

## Stimulus Notes

Hold requests high across several ready_i=0 cycles before releasing ready_i. Held-out should use different request vectors.

## Loose Negative Controls

- `grant_requires_ready`: The buggy design can still avoid issuing grants when ready_i is low.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) (|gnt_o) |-> ready_i);`
- `ready_and_request_imply_grant`: It does not constrain the stalled cycles where valid_o should remain asserted.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) (ready_i && (|req_i)) |-> (|gnt_o));`

## Next Step

Create `tb.v`, `tb_holdout.v`, regenerate waveforms, then run golden self-check and hardness gates before admitting this case.
