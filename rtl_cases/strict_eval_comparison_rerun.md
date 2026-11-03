# Strict Eval Comparison

## Overall

- Before strict_success: 0/2
- After strict_success: 0/4
- Improved to strict_success: 0
- Regressed from strict_success: 0
- Failure type changed: 0
- Assertion changed only: 1

## Failure Type Counts

| Failure Type | Before | After |
|---|---:|---:|
| bug_not_detected_on_buggy | 2 | 3 |
| semantic_unreviewed | 0 | 1 |

## Changed Rows

| Case | Method | Change | Before | After |
|---|---|---|---|---|
| case09_addr_increment | spec_only | assertion_changed | bug_not_detected_on_buggy | bug_not_detected_on_buggy |
| case09_addr_increment | spec_rtl_raw_trace | new_in_after |  | bug_not_detected_on_buggy |
| case09_addr_increment | spec_rtl_trace_summary | new_in_after |  | semantic_unreviewed |
