# case445_priority_encoder_protocol_suppress_1

- Parent bug: `case445_priority_encoder_protocol_suppress_1`
- Upstream RTL: `external/verilog-axis/rtl/priority_encoder.v`
- Mutation: `assign output_valid = stage_valid[LEVELS-1];` → `assign output_valid = '0; // ASSERTIONFORGE_MUTATION: combinational/protocol output suppressed`
- Validation status: RTL mutation materialized; module-specific seen/held-out/decoy tests are pending.
