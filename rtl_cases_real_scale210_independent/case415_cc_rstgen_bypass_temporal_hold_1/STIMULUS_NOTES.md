# case415_cc_rstgen_bypass_temporal_hold_1

- Parent bug: `case415_cc_rstgen_bypass_temporal_hold_1`
- Upstream RTL: `external/common_cells/src/cc_rstgen_bypass.sv`
- Mutation: `            synch_regs_q <= 0;` → `            synch_regs_q <= synch_regs_q; // ASSERTIONFORGE_MUTATION: state update suppressed`
- Validation status: RTL mutation materialized; module-specific seen/held-out/decoy tests are pending.
