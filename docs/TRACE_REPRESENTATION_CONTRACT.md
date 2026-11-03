# Trace Representation Contract

Experiments use exactly four trace representations:

1. `raw_trace`
2. `naive_summary`
3. `event_abstraction`
4. `temporal_relation_abstraction`

The temporal-relation abstraction must explicitly retain trigger, polarity,
ordering, the exact delay observed in the supplied trace, duration, reset context,
and the first good/bad divergence. Exact delay is observational evidence, not an
automatically valid general property.

It must not contain golden SVA, expected-property text, mutation diff, buggy or
mutation source lines. Absolute trace cycle indices and one-off literal constants
must not be promoted into universal rules. Every abstraction therefore includes a
`Generalization boundary` field stating this limitation.

Run `src/audit_trace_representation_contract.py` before a trace-representation
experiment. The experiment runner also applies the same contract and refuses
noncompliant temporal summaries.
