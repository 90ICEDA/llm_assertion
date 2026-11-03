# Fixed candidate/seed stability replication

One original Ibex decoder; correlated development candidates, not independent bugs. No claim of search added value or R over H. Native simulation is not formal proof.

| Measure | Numerator | Denominator | Value |
|---|---:|---:|---:|
| planned_coverage | 12 | 12 | 1.0 |
| ordinary_acceptance | 7 | 12 | 0.5833333333333334 |
| generation_full_acceptance | 7 | 12 | 0.5833333333333334 |
| conditional_recovery | 0 | 0 | None |
| independent_pass | 7 | 7 | 1.0 |
| unique_version_independent_pass | 7 | 7 | 1.0 |
| whole_schedule_success | 7 | 12 | 0.5833333333333334 |

Physical model calls: 12; native compiles/executions: 86/86; formal calls: 0.

Zero recovery opportunities yields null, not a recovery success/failure rate. Missing independent results stay in the eligible denominator. Per-candidate, seed, mechanism, cluster, unknown and token details: results.json.
