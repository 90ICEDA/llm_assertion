# Behavioral specification

The overflow status is a pulse: after it is asserted for an oversized or dropped frame, it must return low on the next clock unless a new overflow event is reported.
