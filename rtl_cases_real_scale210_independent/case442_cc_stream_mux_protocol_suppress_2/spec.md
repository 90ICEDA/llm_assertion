# Behavioral specification

The mux output valid equals the valid bit of the selected input lane in the same cycle. Backpressure is returned only to the selected lane.

Temporal type: `same-cycle combinational/protocol relation`
