# case404_prim_intr_hw_temporal_hold_1

- Parent bug: `case404_prim_intr_hw_temporal_hold_1`
- Upstream RTL: `external/opentitan/hw/ip/prim/rtl/prim_intr_hw.sv`
- Mutation: `        intr_o <= '0;` → `        intr_o <= intr_o; // ASSERTIONFORGE_MUTATION: state update suppressed`
- Validation status: RTL mutation materialized; module-specific seen/held-out/decoy tests are pending.
