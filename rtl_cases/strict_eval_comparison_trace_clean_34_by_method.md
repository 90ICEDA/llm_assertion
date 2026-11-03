# Strict Eval By Prompt Method

| Method | Raw Rows | Distinct Assertions | Cases | Syntax Pass | Correct Pass | Buggy Fail | Non-vacuous | Antecedent Triggered | Strict Success Assertions | Success Cases |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| spec + RTL + raw trace | 49 | 23 | 10 | 22 | 13 | 8 | 14 | 14 | 1 | 1 |
| spec + RTL + trace summary | 49 | 19 | 10 | 19 | 15 | 3 | 7 | 7 | 0 | 0 |

## Failure Type Breakdown

### spec + RTL + raw trace

| Failure Type | Count |
|---|---:|
| bug_not_detected_on_buggy | 12 |
| false_positive_on_correct | 9 |
| strict_success | 1 |
| syntax_fail | 1 |

### spec + RTL + trace summary

| Failure Type | Count |
|---|---:|
| bug_not_detected_on_buggy | 14 |
| false_positive_on_correct | 4 |
| trace_overfit | 1 |

