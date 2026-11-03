# case446_priority_encoder_protocol_suppress_2

- Parent bug: `case446_priority_encoder_protocol_suppress_2`
- Upstream RTL: `external/verilog-axis/rtl/priority_encoder.v`
- Mutation: `assign output_encoded = stage_enc[LEVELS-1];` → `assign output_encoded = '0; // ASSERTIONFORGE_MUTATION: combinational/protocol output suppressed`
- Validation status: RTL mutation materialized; module-specific seen/held-out/decoy tests are pending.
