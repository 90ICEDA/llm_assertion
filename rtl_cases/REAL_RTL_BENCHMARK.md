# Real RTL Mutation Benchmark

This is the phase change away from the original 10 toy cases.

The purpose of this benchmark is not to make trace summary win. It is to measure, cleanly, whether:

- `trace summary - (spec + RTL)` shrinks toward `0`
- or opens up on a specific bug class where trace summary is genuinely useful

## What Is In Scope

- real OpenTitan RTL as the correct implementation
- source-level mutations as buggy implementations
- explicit `bug_class` labels from the start:
  - `combination_same_cycle`
  - `temporal_cross_cycle`
- hard-case metadata:
  - `golden_sva`
  - `loose_negative_controls`
  - `hard_case_rationale`
  - `overfit_lure`
  - held-out requirement

## New Scripts

- `real_rtl_case_catalog.py`
  - planning catalog of mutation-backed case blueprints
- `build_real_rtl_benchmark.py`
  - materializes `correct.v` / `buggy.v` scaffolds from real RTL
- `check_case_hardness.py`
  - admission gate:
    - golden passes
    - golden fails buggy
    - antecedent hits the buggy trace
    - at least one loose control misses the bug
- `summarize_strict_eval_by_method_and_bug_class.py`
  - produces the method × bug_class split requested for the scaled rerun

## Current State

The catalog and source-mutation scaffolds are ready, but the cases are not benchmark-ready until each case also has:

- `tb.v`
- `tb_holdout.v`
- waveform CSV/VCD files
- prompt assets regenerated
- golden self-check passing
- hardness gate passing

This separation is intentional: the repository now has a real-RTL case plan and source materialization path, without pretending that unverified testbenches are already valid benchmark data.

## Build The Scaffold Dataset

From `rtl_cases`:

```bash
python3 ./build_real_rtl_benchmark.py --output-root ../rtl_cases_real
```

This creates:

- `../rtl_cases_real/case_manifest.json`
- one directory per case
- `correct.v`
- `buggy.v`
- `STIMULUS_NOTES.md`

## Admit Cases Into The Benchmark

After adding `tb.v`, `tb_holdout.v`, and regenerating waveforms:

```bash
python3 ./check_golden_sva.py --root ../rtl_cases_real --output-csv ../rtl_cases_real/golden_sva_check_report.csv
python3 ./check_case_hardness.py --root ../rtl_cases_real --output-csv ../rtl_cases_real/hardness_check_report.csv
```

Only cases that satisfy both checks should be scored.

## Rerun Existing Pipeline

Once the dataset root is complete, the existing pipeline can be reused without changing core evaluation logic:

```bash
python3 ./prepare_prompt_assets.py --root ../rtl_cases_real
python3 ./generate_sva_from_prompts.py --root ../rtl_cases_real ...
python3 ./evaluate_generated_sva.py --root ../rtl_cases_real --output-csv ../rtl_cases_real/strict_eval_report.csv
python3 ./summarize_strict_eval_by_method_and_bug_class.py --root ../rtl_cases_real --report ../rtl_cases_real/strict_eval_report.csv --output-csv ../rtl_cases_real/strict_eval_by_method_and_bug_class.csv
```

## Why The Hardness Gate Matters

Every admitted case should answer “yes” to both:

- does the golden assertion really hit and separate good vs buggy behavior?
- does at least one conservative-looking assertion miss the bug?

If the answer to the second question is “no”, the case is too loose and will not help distinguish methods.
