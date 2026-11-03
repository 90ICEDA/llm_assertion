# case416_cc_rstgen_bypass_temporal_hold_2

- Parent bug: `case416_cc_rstgen_bypass_temporal_hold_2`
- Upstream RTL: `external/common_cells/src/cc_rstgen_bypass.sv`
- Mutation: `            synch_regs_q <= {synch_regs_q[NumRegs-2:0], 1'b1};` → `            synch_regs_q <= synch_regs_q; // ASSERTIONFORGE_MUTATION: state update suppressed`
- Validation status: RTL mutation materialized; module-specific seen/held-out/decoy tests are pending.
