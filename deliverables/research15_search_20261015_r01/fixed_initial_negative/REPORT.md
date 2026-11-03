# Coverage-feedback FIFO search: actual native execution

All inputs are development data. The shared model candidate is fixed for all methods. Faults are explicitly artificial output-boundary changes to real vendored axis_fifo RTL.

| Method | Queries | Native replays | Independent missed gap classes | Duplicate gap observations | Unknown queries |
|---|---:|---:|---:|---:|---:|
| ordinary | 12 | 60 | 0 | 0 | 0 |
| candidate_disagreement | 12 | 60 | 0 | 0 | 0 |
| raw_difference | 12 | 60 | 0 | 0 | 0 |
| contract_coverage | 12 | 60 | 0 | 0 | 0 |

Independent gap class = (artificial fault, violated obligation), not waveform/seed/cycle count. First violation per reset epoch is the attribution boundary; later violations are preserved as unknown. A native alarm for another named obligation is not counted as a silent false negative.

Contract selection uses accumulated observed obligation checks, native antecedent cover events and first-violation evidence. Deficits are recalculated after each own query, divided by prior target attempts. The exact input to each policy is stored in permitted_feedback_view; ordinary/disagreement/difference cannot read contract adjudication.

The single-property initial pool has no candidate disagreement pair, so that arm honestly falls back to uniform exploration. This does not replace the existing 11-pair comparison.

Native cover confirms finite sampled antecedent activation, not semantic entailment or global protection. The declared obligation mapping remains a proxy. RAM depth5 rounds to8; finite drain requires at least18 actual input-idle/ready samples within the explicitly bounded depth/pipeline configuration.

Treatment witness: not found; treatment_witness.json is null; no engineering substitution

No independent-test outcome is reported here. B/D may share the actual acquisition with shared cost; A/C must not read the acquisition artifact. No formal proof or historical original FIFO bug validation is claimed.
