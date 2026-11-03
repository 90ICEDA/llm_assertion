# Frozen repair requirements

Sampling: SHA-256 of UTF-8 `blind-review-20260922-v1|{parent_bug_id}`, sort hexadecimal digests ascending, take first two from all 30 IDs in `PARENTS.csv`. Full order is `sampling_order.csv`. This file is frozen before reading candidate judgments.

## case455_prim_crc32_set_enable_coupling

A `set_crc_i` pulse must load `~crc_in_i` into `crc_q` at that edge regardless of `data_valid_i`; consequently `crc_out_o` at the next sampled cycle must equal the seed value sampled at the set edge. The fix restores `crc_en = set_crc_i | data_valid_i`, while retaining set priority over data update. A useful assertion should expose a violation when set is high and data_valid is low, without forbidding that legal input combination. Evidence: `parents/case455_prim_crc32_set_enable_coupling/bug/spec.txt`, `bug/mutation.diff`, `bug/correct.v`, `bug/buggy.v`, `bug/trace_summary.txt`.

## case115_prim_edge_both_edges_collapsed

The positive-edge output must indicate a transition of synchronized input from 0 to 1 and remain low for the 1-to-0 transition; negative-edge output reports the latter transition. The fix restores `q_sync_d & ~q_sync_q` instead of XOR for `q_posedge_pulse_o`. A useful assertion should reject the false positive-edge pulse at a falling transition without treating a sustained high input as an edge. Evidence: `parents/case115_prim_edge_both_edges_collapsed/bug/spec.txt`, `bug/derived_mutation.diff`, `bug/correct.v`, `bug/buggy.v`, `bug/trace_summary.txt`.
