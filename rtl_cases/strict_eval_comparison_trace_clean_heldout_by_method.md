# Strict Eval By Prompt Method

| Method | Raw Rows | Distinct Assertions | Cases | Syntax Pass | Correct Pass | Buggy Fail | Non-vacuous | Antecedent Triggered | Strict Success Assertions | Success Cases |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| spec + RTL + raw trace | 50 | 20 | 10 | 20 | 13 | 7 | 10 | 10 | 1 | 1 |
| spec + RTL + trace summary | 49 | 22 | 10 | 22 | 18 | 4 | 8 | 8 | 0 | 0 |

## Failure Type Breakdown

### spec + RTL + raw trace

| Failure Type | Count |
|---|---:|
| bug_not_detected_on_buggy | 12 |
| false_positive_on_correct | 7 |
| strict_success | 1 |

### spec + RTL + trace summary

| Failure Type | Count |
|---|---:|
| bug_not_detected_on_buggy | 17 |
| false_positive_on_correct | 4 |
| trace_overfit | 1 |

