# case405_prim_intr_hw_temporal_hold_2

- Parent bug: `case405_prim_intr_hw_temporal_hold_2`
- Upstream RTL: `external/opentitan/hw/ip/prim/rtl/prim_intr_hw.sv`
- Mutation: `        intr_o <= status & reg2hw_intr_enable_q_i;` → `        intr_o <= intr_o; // ASSERTIONFORGE_MUTATION: state update suppressed`
- Validation status: RTL mutation materialized; module-specific seen/held-out/decoy tests are pending.
