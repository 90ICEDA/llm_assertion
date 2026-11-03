# Behavioral specification

Reset clears the complete input-history vector. On each active clock after reset, the history shifts by one sample and appends filter_i, providing the configured observation window used by the filter.
