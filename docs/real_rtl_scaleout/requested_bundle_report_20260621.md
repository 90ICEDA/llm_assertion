# Requested Bundle (2026-06-21)

## 1. Main Table

- Case-dedup main table: `/mnt/d/AssertionForge-main/rtl_cases_real_admitted_20260619/strict_eval_case_dedup_by_method_and_bug_class_iv12.csv`
- Gap table: `/mnt/d/AssertionForge-main/rtl_cases_real_admitted_20260619/strict_eval_case_dedup_gap_vs_spec_plus_rtl_iv12.csv`
- combination_same_cycle gap: correct_pass 2, fail_on_buggy -1, strict_success 0
- temporal_cross_cycle gap: correct_pass -1, fail_on_buggy 4, strict_success 0
- overall gap: correct_pass 1, fail_on_buggy 3, strict_success 0

## 2. Dataset

- Manifest and inventory: `/mnt/d/AssertionForge-main/docs/real_rtl_scaleout/dataset_inventory_30cases.csv`
- Source manifest: `/mnt/d/AssertionForge-main/rtl_cases_real_active/case_manifest.json`

## 3. Golden Self-Check

- Golden report: `/mnt/d/AssertionForge-main/docs/real_rtl_scaleout/golden_self_check_active_30cases.csv`
- Result: 30/30 pass.

## 4. Antecedent Coverage

- Antecedent report: `/mnt/d/AssertionForge-main/docs/real_rtl_scaleout/antecedent_coverage_30cases.csv`
- Result: 30/30 have buggy antecedent hits > 0.

## 5. Overfit / Generalization

- Summary: `/mnt/d/AssertionForge-main/docs/real_rtl_scaleout/overfit_generalization_summary_iv12.csv`
- Detail: `/mnt/d/AssertionForge-main/docs/real_rtl_scaleout/trace_overfit_detail_iv12.csv`
- Trace overfit cases: case124_prim_fifo_clear_ignored, case126_prim_regwe_enable_gap
- Trace overfit lure cases: none

## 6. Trace Summary Miss Attribution

- Full attribution table: `/mnt/d/AssertionForge-main/docs/real_rtl_scaleout/trace_summary_miss_attribution_full_iv12.csv`

## 7. Judgment

- The scaled-up case-dedup result does not show a robust breakout where trace summary clearly wins over spec+RTL on a bug class.
- Combination cases improve correct_pass a bit (+2) but lose fail_on_buggy (-1).
- Temporal cases improve fail_on_buggy (+4) but lose correct_pass (-1).
- strict_success stays 0, so there is still no evidence of a stable end-to-end advantage.
