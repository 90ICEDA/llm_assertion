# case434_prim_edge_detector_protocol_suppress_2

- Parent bug: `case434_prim_edge_detector_protocol_suppress_2`
- Upstream RTL: `external/opentitan/hw/ip/prim/rtl/prim_edge_detector.sv`
- Mutation: `  assign q_sync_o = q_sync_d;` → `  assign q_sync_o = '0; // ASSERTIONFORGE_MUTATION: combinational/protocol output suppressed`
- Validation status: RTL mutation materialized; module-specific seen/held-out/decoy tests are pending.
