# Behavioral specification

While reset is asserted, the filter's retained output state is cleared to zero. After reset release, disabled filtering passes filter_i directly; enabled filtering changes filter_o only after the sampled input has remained consistently opposite for the configured filter length.
