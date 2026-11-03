# Strict Eval Comparison

## Overall

- Before strict_success: 8/88
- After strict_success: 5/98
- Improved to strict_success: 0
- Regressed from strict_success: 3
- Failure type changed: 18
- Assertion changed only: 40

## Failure Type Counts

| Failure Type | Before | After |
|---|---:|---:|
| bug_not_detected_on_buggy | 52 | 59 |
| false_positive_on_correct | 26 | 28 |
| semantic_unreasonable | 1 | 0 |
| strict_success | 8 | 5 |
| syntax_fail | 1 | 1 |
| trace_overfit | 0 | 5 |

## Changed Rows

| Case | Method | Candidate | Change | Before | After |
|---|---|---:|---|---|---|
| case01_reset_omission | spec_rtl_raw_trace | 1 | assertion_changed | bug_not_detected_on_buggy | bug_not_detected_on_buggy |
| case01_reset_omission | spec_rtl_raw_trace | 2 | assertion_changed | bug_not_detected_on_buggy | bug_not_detected_on_buggy |
| case01_reset_omission | spec_rtl_raw_trace | 3 | assertion_changed | bug_not_detected_on_buggy | bug_not_detected_on_buggy |
| case01_reset_omission | spec_rtl_raw_trace | 4 | failure_type_changed | bug_not_detected_on_buggy | false_positive_on_correct |
| case01_reset_omission | spec_rtl_raw_trace | 5 | assertion_changed | bug_not_detected_on_buggy | bug_not_detected_on_buggy |
| case01_reset_omission | spec_rtl_trace_summary | 1 | new_in_after |  | bug_not_detected_on_buggy |
| case01_reset_omission | spec_rtl_trace_summary | 2 | new_in_after |  | bug_not_detected_on_buggy |
| case01_reset_omission | spec_rtl_trace_summary | 3 | new_in_after |  | bug_not_detected_on_buggy |
| case01_reset_omission | spec_rtl_trace_summary | 4 | new_in_after |  | bug_not_detected_on_buggy |
| case01_reset_omission | spec_rtl_trace_summary | 5 | new_in_after |  | bug_not_detected_on_buggy |
| case02_grant_delay | spec_rtl_raw_trace | 3 | assertion_changed | bug_not_detected_on_buggy | bug_not_detected_on_buggy |
| case02_grant_delay | spec_rtl_raw_trace | 4 | failure_type_changed | bug_not_detected_on_buggy | syntax_fail |
| case02_grant_delay | spec_rtl_trace_summary | 1 | new_in_after |  | false_positive_on_correct |
| case02_grant_delay | spec_rtl_trace_summary | 2 | new_in_after |  | false_positive_on_correct |
| case02_grant_delay | spec_rtl_trace_summary | 3 | new_in_after |  | false_positive_on_correct |
| case02_grant_delay | spec_rtl_trace_summary | 4 | failure_type_changed | bug_not_detected_on_buggy | false_positive_on_correct |
| case02_grant_delay | spec_rtl_trace_summary | 5 | new_in_after |  | false_positive_on_correct |
| case03_valid_ready_or_bug | spec_rtl_raw_trace | 1 | strict_success_unchanged | strict_success | strict_success |
| case03_valid_ready_or_bug | spec_rtl_raw_trace | 2 | strict_success_unchanged | strict_success | strict_success |
| case03_valid_ready_or_bug | spec_rtl_raw_trace | 3 | strict_success_unchanged | strict_success | strict_success |
| case03_valid_ready_or_bug | spec_rtl_raw_trace | 4 | strict_success_unchanged | strict_success | strict_success |
| case03_valid_ready_or_bug | spec_rtl_raw_trace | 5 | strict_success_unchanged | strict_success | strict_success |
| case03_valid_ready_or_bug | spec_rtl_trace_summary | 2 | assertion_changed | bug_not_detected_on_buggy | bug_not_detected_on_buggy |
| case03_valid_ready_or_bug | spec_rtl_trace_summary | 3 | assertion_changed | bug_not_detected_on_buggy | bug_not_detected_on_buggy |
| case03_valid_ready_or_bug | spec_rtl_trace_summary | 4 | assertion_changed | bug_not_detected_on_buggy | bug_not_detected_on_buggy |
| case03_valid_ready_or_bug | spec_rtl_trace_summary | 5 | assertion_changed | bug_not_detected_on_buggy | bug_not_detected_on_buggy |
| case04_fsm_transition | spec_rtl_raw_trace | 2 | assertion_changed | bug_not_detected_on_buggy | bug_not_detected_on_buggy |
| case04_fsm_transition | spec_rtl_raw_trace | 3 | assertion_changed | bug_not_detected_on_buggy | bug_not_detected_on_buggy |
| case04_fsm_transition | spec_rtl_raw_trace | 5 | assertion_changed | bug_not_detected_on_buggy | bug_not_detected_on_buggy |
| case04_fsm_transition | spec_rtl_trace_summary | 1 | assertion_changed | bug_not_detected_on_buggy | bug_not_detected_on_buggy |
| case04_fsm_transition | spec_rtl_trace_summary | 2 | assertion_changed | bug_not_detected_on_buggy | bug_not_detected_on_buggy |
| case04_fsm_transition | spec_rtl_trace_summary | 3 | assertion_changed | bug_not_detected_on_buggy | bug_not_detected_on_buggy |
| case04_fsm_transition | spec_rtl_trace_summary | 4 | assertion_changed | bug_not_detected_on_buggy | bug_not_detected_on_buggy |
| case04_fsm_transition | spec_rtl_trace_summary | 5 | assertion_changed | bug_not_detected_on_buggy | bug_not_detected_on_buggy |
| case05_counter_boundary | spec_rtl_raw_trace | 3 | assertion_changed | false_positive_on_correct | false_positive_on_correct |
| case05_counter_boundary | spec_rtl_raw_trace | 4 | assertion_changed | false_positive_on_correct | false_positive_on_correct |
| case05_counter_boundary | spec_rtl_trace_summary | 1 | regressed_from_strict_success | strict_success | false_positive_on_correct |
| case05_counter_boundary | spec_rtl_trace_summary | 2 | assertion_changed | false_positive_on_correct | false_positive_on_correct |
| case05_counter_boundary | spec_rtl_trace_summary | 3 | assertion_changed | false_positive_on_correct | false_positive_on_correct |
| case05_counter_boundary | spec_rtl_trace_summary | 4 | regressed_from_strict_success | strict_success | false_positive_on_correct |
| case05_counter_boundary | spec_rtl_trace_summary | 5 | regressed_from_strict_success | strict_success | false_positive_on_correct |
| case06_priority_encoder | spec_rtl_raw_trace | 1 | failure_type_changed | syntax_fail | false_positive_on_correct |
| case06_priority_encoder | spec_rtl_raw_trace | 2 | assertion_changed | false_positive_on_correct | false_positive_on_correct |
| case06_priority_encoder | spec_rtl_raw_trace | 4 | assertion_changed | false_positive_on_correct | false_positive_on_correct |
| case06_priority_encoder | spec_rtl_raw_trace | 5 | assertion_changed | false_positive_on_correct | false_positive_on_correct |
| case06_priority_encoder | spec_rtl_trace_summary | 1 | failure_type_changed | false_positive_on_correct | bug_not_detected_on_buggy |
| case06_priority_encoder | spec_rtl_trace_summary | 2 | failure_type_changed | false_positive_on_correct | bug_not_detected_on_buggy |
| case06_priority_encoder | spec_rtl_trace_summary | 3 | failure_type_changed | false_positive_on_correct | bug_not_detected_on_buggy |
| case06_priority_encoder | spec_rtl_trace_summary | 4 | failure_type_changed | false_positive_on_correct | bug_not_detected_on_buggy |
| case06_priority_encoder | spec_rtl_trace_summary | 5 | failure_type_changed | false_positive_on_correct | bug_not_detected_on_buggy |
| case07_fifo_full_boundary | spec_rtl_raw_trace | 5 | assertion_changed | false_positive_on_correct | false_positive_on_correct |
| case07_fifo_full_boundary | spec_rtl_trace_summary | 1 | assertion_changed | bug_not_detected_on_buggy | bug_not_detected_on_buggy |
| case07_fifo_full_boundary | spec_rtl_trace_summary | 2 | assertion_changed | bug_not_detected_on_buggy | bug_not_detected_on_buggy |
| case07_fifo_full_boundary | spec_rtl_trace_summary | 3 | failure_type_changed | false_positive_on_correct | bug_not_detected_on_buggy |
| case07_fifo_full_boundary | spec_rtl_trace_summary | 4 | assertion_changed | bug_not_detected_on_buggy | bug_not_detected_on_buggy |
| case07_fifo_full_boundary | spec_rtl_trace_summary | 5 | failure_type_changed | false_positive_on_correct | bug_not_detected_on_buggy |
| case08_pulse_width | spec_rtl_raw_trace | 1 | assertion_changed | bug_not_detected_on_buggy | bug_not_detected_on_buggy |
| case08_pulse_width | spec_rtl_raw_trace | 2 | new_in_after |  | false_positive_on_correct |
| case08_pulse_width | spec_rtl_raw_trace | 3 | assertion_changed | bug_not_detected_on_buggy | bug_not_detected_on_buggy |
| case08_pulse_width | spec_rtl_raw_trace | 4 | assertion_changed | bug_not_detected_on_buggy | bug_not_detected_on_buggy |
| case08_pulse_width | spec_rtl_trace_summary | 1 | failure_type_changed | bug_not_detected_on_buggy | false_positive_on_correct |
| case08_pulse_width | spec_rtl_trace_summary | 2 | assertion_changed | bug_not_detected_on_buggy | bug_not_detected_on_buggy |
| case08_pulse_width | spec_rtl_trace_summary | 3 | assertion_changed | bug_not_detected_on_buggy | bug_not_detected_on_buggy |
| case08_pulse_width | spec_rtl_trace_summary | 4 | failure_type_changed | bug_not_detected_on_buggy | false_positive_on_correct |
| case09_addr_increment | spec_rtl_raw_trace | 2 | assertion_changed | bug_not_detected_on_buggy | bug_not_detected_on_buggy |
| case09_addr_increment | spec_rtl_raw_trace | 5 | assertion_changed | bug_not_detected_on_buggy | bug_not_detected_on_buggy |
| case09_addr_increment | spec_rtl_trace_summary | 1 | failure_type_changed | false_positive_on_correct | trace_overfit |
| case09_addr_increment | spec_rtl_trace_summary | 2 | failure_type_changed | false_positive_on_correct | trace_overfit |
| case09_addr_increment | spec_rtl_trace_summary | 3 | failure_type_changed | false_positive_on_correct | trace_overfit |
| case09_addr_increment | spec_rtl_trace_summary | 4 | failure_type_changed | false_positive_on_correct | trace_overfit |
| case09_addr_increment | spec_rtl_trace_summary | 5 | failure_type_changed | semantic_unreasonable | trace_overfit |
| case10_hold_valid_until_ready | spec_rtl_trace_summary | 1 | assertion_changed | bug_not_detected_on_buggy | bug_not_detected_on_buggy |
| case10_hold_valid_until_ready | spec_rtl_trace_summary | 2 | assertion_changed | bug_not_detected_on_buggy | bug_not_detected_on_buggy |
| case10_hold_valid_until_ready | spec_rtl_trace_summary | 3 | assertion_changed | bug_not_detected_on_buggy | bug_not_detected_on_buggy |
| case10_hold_valid_until_ready | spec_rtl_trace_summary | 4 | assertion_changed | bug_not_detected_on_buggy | bug_not_detected_on_buggy |
| case10_hold_valid_until_ready | spec_rtl_trace_summary | 5 | assertion_changed | bug_not_detected_on_buggy | bug_not_detected_on_buggy |
