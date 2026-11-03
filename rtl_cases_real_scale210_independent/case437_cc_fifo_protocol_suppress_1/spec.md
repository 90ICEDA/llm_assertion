# Behavioral specification

usage_o reports the current FIFO occupancy. A successful push into an empty FIFO without a simultaneous pop increases the reported usage on the next clock edge.

Temporal type: `same-cycle combinational/protocol relation`
