# case410_cc_edge_propagator_ack_temporal_hold_1

- Parent bug: `case410_cc_edge_propagator_ack_temporal_hold_1`
- Upstream RTL: `external/common_cells/src/cc_edge_propagator_ack.sv`
- Mutation: `      r_input_reg <= 1'b0;` → `      r_input_reg <= r_input_reg; // ASSERTIONFORGE_MUTATION: state update suppressed`
- Validation status: RTL mutation materialized; module-specific seen/held-out/decoy tests are pending.
