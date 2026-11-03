# case108_prim_arbiter_grant_without_ready

- `bug_class`: combination_same_cycle
- `bug_family`: ready_valid_handshake
- `bug_type`: grant can assert while sink is not ready

## Spec

A grant shall only assert when ready_i is high in the same cycle.

## Hardness Rationale

The arbiter still 'looks right' if you only check existence and one-hotness of grants. The exact no-ready suppression rule is what matters.

## Stimulus Notes

Alternate ready_i low/high while holding requests stable. Held-out should vary which requester is active under backpressure.

## Loose Negative Controls

- `valid_tracks_request`: valid_o can still track requests even if gnt_o ignores ready_i.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) (|req_i) |-> valid_o);`
- `grant_is_onehot`: One-hotness says nothing about whether granting under backpressure is legal.
  Assertion: `assert property (@(posedge clk_i) disable iff (!rst_ni) !((gnt_o[0] && gnt_o[1]) || (gnt_o[0] && gnt_o[2]) || (gnt_o[0] && gnt_o[3]) || (gnt_o[1] && gnt_o[2]) || (gnt_o[1] && gnt_o[3]) || (gnt_o[2] && gnt_o[3])));`

## Next Step

Create `tb.v`, `tb_holdout.v`, regenerate waveforms, then run golden self-check and hardness gates before admitting this case.

## Overfit Decoy

- Source: `self held-out trace with a decoy idle perturbation`
- Lure: Seen trace alternates ready_i around the same request literals; held-out changes requester identities while preserving the backpressure corner.
- Files: `tb_decoy.v`, `waveform_good_decoy.csv`, `waveform_bad_decoy.csv`

