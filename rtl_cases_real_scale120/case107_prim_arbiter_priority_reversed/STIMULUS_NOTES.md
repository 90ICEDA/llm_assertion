# case107_prim_arbiter_priority_reversed

- `bug_class`: combination_same_cycle
- `bug_family`: priority_resolution
- `bug_type`: left/right fixed priority reversed

## Spec

When multiple requests are high, the fixed arbiter shall grant the lowest index request in the same cycle when ready_i is high.

## Hardness Rationale

This is a classic 'some legal grant exists, but not the highest-priority one' bug. Generic handshake assertions miss it completely.

## Stimulus Notes

Use tied request vectors like 4'b0011 and 4'b1011. Held-out should use different tie patterns that still include requester 0.

## Loose Negative Controls

- `some_grant_when_ready`: The buggy arbiter still produces a grant; it is just the wrong requester.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) (ready_i && (|req_i)) |-> (|gnt_o));`
- `grant_implies_request`: It never checks exact priority order.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) (|gnt_o) |-> (|req_i));`

## Next Step

Create `tb.v`, `tb_holdout.v`, regenerate waveforms, then run golden self-check and hardness gates before admitting this case.

## Overfit Decoy

- Source: `self held-out trace with a decoy idle perturbation`
- Lure: Seen trace uses tied request vectors 0011 and 1010; held-out switches to 1100 and 0110 so literal requester memorization breaks.
- Files: `tb_decoy.v`, `waveform_good_decoy.csv`, `waveform_bad_decoy.csv`

