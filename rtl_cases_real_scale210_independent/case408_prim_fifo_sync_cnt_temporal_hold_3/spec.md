# Behavioral specification

An accepted write advances wptr_o modulo the configured depth. A write accepted at the final pointer position wraps wptr_o to zero on the following sampled cycle while occupancy accounting continues across the wrap.
