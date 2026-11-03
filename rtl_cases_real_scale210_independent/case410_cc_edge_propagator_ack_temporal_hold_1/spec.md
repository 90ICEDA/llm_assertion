# Behavioral specification

A request launched by edge_i is retained across the transmit/receive clock boundary until acknowledgement. Reset in either domain clears the corresponding observable handshake state; no receive pulse or transmit acknowledgement is emitted solely because reset was asserted.

Temporal type: `cross-cycle sequential state transition`
