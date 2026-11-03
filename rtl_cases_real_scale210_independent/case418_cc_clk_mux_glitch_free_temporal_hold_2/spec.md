# Behavioral specification

Reasserting asynchronous reset disables clock propagation promptly: clk_o is low during reset and does not retain a previously selected clock transition.

Temporal type: `cross-cycle sequential state transition`
