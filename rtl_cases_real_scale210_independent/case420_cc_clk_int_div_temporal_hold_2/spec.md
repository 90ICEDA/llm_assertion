# Behavioral specification

Outside reset and test bypass, the divider gate-open state follows the prior cycle's gate enable qualified by en_i. This state controls whether divided clock activity is allowed.

Temporal type: `cross-cycle sequential state transition`
