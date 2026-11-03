# case413_cc_edge_propagator_tx_temporal_hold_2

- Parent bug: `case413_cc_edge_propagator_tx_temporal_hold_2`
- Upstream RTL: `external/common_cells/src/cc_edge_propagator_tx.sv`
- Mutation: `            sync_a      <= 2'b00;` → `            sync_a <= sync_a; // ASSERTIONFORGE_MUTATION: state update suppressed`
- Validation status: RTL mutation materialized; module-specific seen/held-out/decoy tests are pending.
