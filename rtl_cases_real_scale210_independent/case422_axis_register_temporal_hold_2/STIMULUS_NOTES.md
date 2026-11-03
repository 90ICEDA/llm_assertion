# case422_axis_register_temporal_hold_2

- Parent bug: `case422_axis_register_temporal_hold_2`
- Upstream RTL: `external/verilog-axis/rtl/axis_register.v`
- Mutation: `        m_axis_tvalid_reg <= m_axis_tvalid_next;` → `        m_axis_tvalid_reg <= m_axis_tvalid_reg; // ASSERTIONFORGE_MUTATION: state update suppressed`
- Validation status: RTL mutation materialized; module-specific seen/held-out/decoy tests are pending.
