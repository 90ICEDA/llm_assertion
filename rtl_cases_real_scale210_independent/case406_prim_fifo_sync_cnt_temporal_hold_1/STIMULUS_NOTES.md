# case406_prim_fifo_sync_cnt_temporal_hold_1

- Parent bug: `case406_prim_fifo_sync_cnt_temporal_hold_1`
- Upstream RTL: `external/opentitan/hw/ip/prim/rtl/prim_fifo_sync_cnt.sv`
- Mutation: `        wptr_wrap_cnt_q <= {WrapPtrW{1'b0}};` → `        wptr_wrap_cnt_q <= wptr_wrap_cnt_q; // ASSERTIONFORGE_MUTATION: state update suppressed`
- Validation status: RTL mutation materialized; module-specific seen/held-out/decoy tests are pending.
