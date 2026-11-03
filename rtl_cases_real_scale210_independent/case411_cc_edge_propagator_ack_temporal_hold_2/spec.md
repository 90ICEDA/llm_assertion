# Behavioral specification

The receive-domain synchronizer is cleared by receive reset. After reset, edge_o remains low until a new request has propagated from edge_i through the clock-domain crossing.

Temporal type: `cross-cycle sequential state transition`
