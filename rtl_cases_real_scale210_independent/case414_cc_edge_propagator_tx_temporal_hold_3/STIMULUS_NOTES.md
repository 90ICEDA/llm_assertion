# case414_cc_edge_propagator_tx_temporal_hold_3

- Parent bug: `case414_cc_edge_propagator_tx_temporal_hold_3`
- Upstream RTL: `external/common_cells/src/cc_edge_propagator_tx.sv`
- Mutation: `            r_input_reg <= s_input_reg_next;` → `            r_input_reg <= r_input_reg; // ASSERTIONFORGE_MUTATION: state update suppressed`
- Validation status: RTL mutation materialized; module-specific seen/held-out/decoy tests are pending.
