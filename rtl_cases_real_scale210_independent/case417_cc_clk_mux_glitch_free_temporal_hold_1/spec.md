# Behavioral specification

While asynchronous reset is asserted, clk_o is held inactive. Following reset release, the selected functional clock may propagate only after the bypass-control state has been safely established.

Temporal type: `cross-cycle sequential state transition`
