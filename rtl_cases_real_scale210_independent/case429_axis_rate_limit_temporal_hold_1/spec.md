# Behavioral specification

In rate-limited operation outside an active frame, sustained valid traffic must consume the configured allowance and apply source backpressure when the allowance is exhausted; forwarding resumes as the accumulator recovers.
