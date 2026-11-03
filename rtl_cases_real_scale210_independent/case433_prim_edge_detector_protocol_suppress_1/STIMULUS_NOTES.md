# case433_prim_edge_detector_protocol_suppress_1

- Parent bug: `case433_prim_edge_detector_protocol_suppress_1`
- Upstream RTL: `external/opentitan/hw/ip/prim/rtl/prim_edge_detector.sv`
- Mutation: `    assign q_sync_d = d_i;` → `    assign q_sync_d = '0; // ASSERTIONFORGE_MUTATION: combinational/protocol output suppressed`
- Validation status: RTL mutation materialized; module-specific seen/held-out/decoy tests are pending.
