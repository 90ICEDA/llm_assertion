# Behavioral specification

After reset is released, an idle output with downstream ready must cause the registered source-ready output to assert on the next clock. Accepted source beats must subsequently obey ready/valid backpressure.
