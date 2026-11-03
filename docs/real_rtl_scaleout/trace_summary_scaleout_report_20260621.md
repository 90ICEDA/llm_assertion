# Trace Summary Scale-Out Report (2026-06-21)

## 1. Main Table

- Source: cloud full-admitted iv12 rerun for `rtl_cases_real_admitted_20260619`.
- Limitation: the deduped case-level `strict_eval_report_iv12.csv` is not present locally, so this package reports candidate-row summaries for the main method x bug_class table.
- Evaluation subset size: 23 cases, 115 candidate rows. bug_class split: 12 combination_same_cycle, 11 temporal_cross_cycle.
- Key gap (`spec_rtl_trace_summary - spec_plus_rtl`):
  - combination_same_cycle: correct_pass +14, buggy_fail -2, strict_success +0
  - temporal_cross_cycle: correct_pass -17, buggy_fail +4, strict_success +0
  - overall: correct_pass -3, buggy_fail +2, strict_success +0
- Readout: there is no stable class-specific breakout in favor of trace summary. Combination cases improve only on correct_pass but get worse on fail_on_buggy; temporal cases regress strongly on correct_pass. strict_success remains 0 everywhere.

## 2. Dataset Body

- The most complete local 30-case dataset body is `rtl_cases_real_active`: 14 combination_same_cycle and 16 temporal_cross_cycle.
- Machine-readable inventory: `dataset_inventory_30cases.csv`.
- Non-empty overfit_lure cases: 9.

## 3. Golden Self-Check

- Locally confirmed golden passes from golden_sva_check_report.csv: 30 / 30.
- The latest local active-root golden stamp is fully consistent at 30/30.
- Per-case status: `golden_status_30cases.csv`.

## 4. Antecedent Coverage

- Locally confirmed cases with `buggy_antecedent_hits > 0`: 30 / 30.
- The locally recorded golden rows do show that bad traces actually hit the antecedent.
- Per-case coverage: `antecedent_coverage_30cases.csv`.

## 5. Overfit / Generalization

- Cloud full-admitted aggregate reports `trace_overfit = 13`.
- The full per-candidate cloud `strict_eval_report_iv12.csv` is not stored locally, so the complete 13-case list cannot be reconstructed from the workspace alone.
- Observable real-RTL overfit cases retained in local resume logs: case124_prim_fifo_clear_ignored, case126_prim_regwe_enable_gap.
- Observed rows: `trace_overfit_observed_from_resume_attachment.csv`.

## 6. Trace Summary Failure Attribution

- I extracted the retained resume-stage per-candidate log rows for method `spec_rtl_trace_summary` and aggregated them by case.
- This is an observed subset, not the final full-admitted complete table. Even so, the dominant modes are `antecedent_not_triggered`, `bug_not_detected_on_buggy`, and `false_positive_on_correct`, not strict_success.
- Attribution table: `trace_summary_failure_attribution_resume_observed.csv`.

## 7. My Judgment

- The scaled-up evidence currently supports "no robust advantage over spec+RTL" more than "real breakout on some bug class".
- Temporal/cross-cycle cases do not split in favor of trace summary; they regress on correct_pass.
- Combination/same-cycle cases gain correct_pass but lose fail_on_buggy, which looks more like drift/loosening than better bug capture.
- With strict_success still at 0, there is no evidence yet that trace summary is simultaneously precise, bug-catching, non-vacuous, and held-out-stable.

## Artifact Index

- `dataset_inventory_30cases.csv`
- `golden_status_30cases.csv`
- `antecedent_coverage_30cases.csv`
- `full_admitted_cloud_method_bugclass_candidate_level.csv`
- `full_admitted_cloud_overall_candidate_level.csv`
- `trace_summary_vs_spec_plus_rtl_gap_candidate_level.csv`
- `resume_observed_trace_summary_candidate_rows.csv`
- `trace_summary_failure_attribution_resume_observed.csv`
- `trace_overfit_observed_from_resume_attachment.csv`
