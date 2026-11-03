# One-step failure-guided repair

## Protocol

54 unique candidate identities were stratified as 9 failure types × 3 prompt arms × 2 models. Each candidate received exactly one repair call. Unified feedback gives a visible-check checklist; failure-specific feedback names the diagnosed visible failure; wrong-diagnosis supplies a deterministic incorrect category. No golden artifact, buggy RTL, held-out trace, or held-out result field is included in any prompt.

## Prompt-arm results

| Arm | n | Primary fixed | Seen strict success | Held-out strict success |
|---|---:|---:|---:|---:|
| failure_specific | 18 | 66.7% | 55.6% | 61.1% |
| unified | 18 | 55.6% | 50.0% | 55.6% |
| wrong_diagnosis | 18 | 66.7% | 72.2% | 83.3% |

The sample is deliberately small (2 candidates per failure×arm). Wrong diagnosis performing well on some cells is therefore a control result, not evidence that incorrect feedback is beneficial.

## Repair rate by primary failure

| Failure | n | Fixed | Rate |
|---|---:|---:|---:|
| antecedent_not_triggered | 6 | 2 | 33.3% |
| compile_fail | 6 | 2 | 33.3% |
| hardcoding | 6 | 2 | 33.3% |
| reset_misuse | 6 | 6 | 100.0% |
| signal_missing | 6 | 6 | 100.0% |
| too_strong | 6 | 2 | 33.3% |
| too_weak | 6 | 3 | 50.0% |
| unsupported | 6 | 6 | 100.0% |
| vacuity | 6 | 5 | 83.3% |

## Pre/post risk

| Metric | Before | After | Change | Introduced | Resolved |
|---|---:|---:|---:|---:|---:|
| false_positive | 3.7% | 5.6% | +1.9% | 2 | 1 |
| vacuity | 20.4% | 11.1% | -9.3% | 3 | 8 |
| overfit | 0.0% | 0.0% | +0.0% | 0 | 0 |

False positive means a compiled assertion rejects held-out correct behavior. Vacuity means a compiled assertion has no held-out non-vacuous trigger. Overfit is the evaluator trace-overfit flag.

## Complete cases

`complete_cases_by_failure.csv` contains six full cases per failure type, including the complete prompt, original assertion, raw response, repaired assertion, visible/held-out outcomes, and pre/post risk flags. Four sparse static categories use explicitly marked constructed invalid candidates; semantic categories use naturally occurring candidates.
