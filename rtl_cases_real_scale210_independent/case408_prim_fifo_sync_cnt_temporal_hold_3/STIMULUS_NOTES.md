# case408_prim_fifo_sync_cnt_temporal_hold_3

- Parent bug: `case408_prim_fifo_sync_cnt_temporal_hold_3`
- Upstream RTL: `external/opentitan/hw/ip/prim/rtl/prim_fifo_sync_cnt.sv`
- Mutation: `        wptr_wrap_cnt_q <= wptr_wrap_set_cnt;` → `        wptr_wrap_cnt_q <= wptr_wrap_cnt_q; // ASSERTIONFORGE_MUTATION: state update suppressed`
- Validation status: RTL mutation materialized; module-specific seen/held-out/decoy tests are pending.
