# Strict Eval By Prompt Method

| Method | Raw Rows | Distinct Assertions | Cases | Template Match | Compile OK | Correct Pass | Buggy Fail | Non-vacuous | Antecedent Triggered | Strict Success Assertions | Success Cases |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| spec only | 47 | 30 | 10 | 30 | 30 | 21 | 19 | 23 | 23 | 10 | 10 |
| spec + RTL | 50 | 32 | 10 | 32 | 32 | 17 | 25 | 30 | 30 | 11 | 10 |
| spec + RTL + raw trace | 48 | 26 | 10 | 26 | 26 | 17 | 18 | 23 | 23 | 10 | 10 |
| spec + RTL + trace summary | 49 | 29 | 10 | 29 | 29 | 23 | 17 | 21 | 21 | 10 | 10 |

## Failure Type Breakdown

### spec only

| Failure Type | Count |
|---|---:|
| bug_not_detected_on_buggy | 9 |
| false_positive_on_correct | 9 |
| semantic_unreviewed | 2 |
| strict_success | 10 |

### spec + RTL

| Failure Type | Count |
|---|---:|
| bug_not_detected_on_buggy | 5 |
| false_positive_on_correct | 15 |
| semantic_unreviewed | 1 |
| strict_success | 11 |

### spec + RTL + raw trace

| Failure Type | Count |
|---|---:|
| bug_not_detected_on_buggy | 6 |
| false_positive_on_correct | 9 |
| semantic_unreviewed | 1 |
| strict_success | 10 |

### spec + RTL + trace summary

| Failure Type | Count |
|---|---:|
| bug_not_detected_on_buggy | 11 |
| false_positive_on_correct | 6 |
| strict_success | 10 |
| trace_overfit | 2 |

