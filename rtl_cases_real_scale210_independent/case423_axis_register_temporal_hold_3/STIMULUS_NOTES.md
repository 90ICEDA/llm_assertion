# case423_axis_register_temporal_hold_3

- Parent bug: `case423_axis_register_temporal_hold_3`
- Upstream RTL: `external/verilog-axis/rtl/axis_register.v`
- Mutation: `        temp_m_axis_tvalid_reg <= temp_m_axis_tvalid_next;` → `        temp_m_axis_tvalid_reg <= temp_m_axis_tvalid_reg; // ASSERTIONFORGE_MUTATION: state update suppressed`
- Validation status: RTL mutation materialized; module-specific seen/held-out/decoy tests are pending.
