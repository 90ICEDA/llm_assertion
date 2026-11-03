# Assertion clean version notes

- Source report: `rtl_cases_real_admitted_20260619\strict_eval_report_iv12.csv`
- Inventory join: `docs\real_rtl_scaleout\dataset_inventory_30cases.csv`
- Main table: `docs\real_rtl_scaleout\assertion_clean_master_iv12.csv`
- Stats table: `docs\real_rtl_scaleout\assertion_clean_stats_iv12.csv`

## Dedupe rule

- One clean-row per `(case_id, method, normalized_assertion)`.
- `normalized_assertion` is built from `assertion_text` after:
  - whitespace normalization
  - outer-parenthesis stripping
  - canonicalizing spaced binary `&`/`&&` to `&&`
  - canonicalizing spaced binary `|`/`||` to `||`
  - rebuilding the assertion into one canonical `assert property ...` line

## Counting rule

- `raw_candidate_count`: all raw rows in `strict_eval_report_iv12.csv`
- `dedup_candidate_count`: number of clean assertion rows after assertion-level dedupe
- `template_garbage_count`: raw rows with empty assertion text or `failure_type == template_mismatch`
- `unsupported_count`: raw rows with `analysis_supported == False` after excluding template garbage
- `compile_fail_count`: raw rows with non-empty assertion text and `compile_ok == False`
- `syntax_error_count`: raw rows whose `compile_error` contains `syntax error`

## Important separation

- `template_garbage_count`, `unsupported_count`, `compile_fail_count`, and `syntax_error_count` are emitted as separate stats.
- The clean master table only includes rows with non-empty `assertion_text`.
