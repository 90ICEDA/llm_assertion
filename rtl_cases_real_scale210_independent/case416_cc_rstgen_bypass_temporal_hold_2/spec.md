# Behavioral specification

After the selected reset input is released, the reset synchronizer advances on successive clk_i edges and eventually releases rst_no and init_no; they must not remain low indefinitely.

Temporal type: `cross-cycle sequential state transition`
