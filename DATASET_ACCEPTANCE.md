# Dataset Acceptance

This document defines how `rtl_cases_real_scale120` is counted and reviewed after the OpenTitan-only source-diversity repair.

## Current Baseline

- `rtl_cases_real_scale120` contains `120` total cases.
- These split into `40` seed slots and `80` augmentation-only variants.
- Current source-project coverage is `opentitan = 120`, `opencores = 0`.
- Current unique seed modules = `8`:
  - `prim_intr_hw` (`8`)
  - `prim_onehot_check` (`6`)
  - `prim_fifo_sync_cnt` (`6`)
  - `prim_edge_detector` (`6`)
  - `prim_filter_ctr` (`5`)
  - `prim_arbiter_fixed` (`3`)
  - `prim_filter` (`3`)
  - `prim_reg_we_check` (`3`)

## Counting Rules

- Only cases without `seed_case_name` count as seed coverage.
- Any case with `seed_case_name` is augmentation-only.
- Augmentation-only cases may support:
  - seen/held-out robustness testing
  - overfit pressure testing
  - same-bug literal or prelude perturbation
- Augmentation-only cases do not count toward:
  - new seed coverage
  - new module coverage
  - new bug-family coverage

## Source Rules

- `scale120` must contain only real OpenTitan-backed RTL cases.
- Synthetic cross-project scaffolds are not allowed in `scale120`.
- New seed slots should preferentially come from real OpenTitan mutation-backed cases or previously gated real-RTL case directories.

## Admission Rule

- A case counts as new seed coverage only if it has no `seed_case_name`, is backed by real OpenTitan RTL, and passes the required gate bundle.
- If a case has `seed_case_name`, it is always augmentation-only.

## Required Gate Bundle

- golden self-check passes on seen trace
- golden self-check passes on held-out trace
- explicit overfit decoy artifacts are present: `tb_decoy.v`, `waveform_good_decoy.csv`, `waveform_bad_decoy.csv`
- hardness gate passes
- trace-divergence gate passes on seen, held-out, and decoy tracks
- overfit structure is present and explicitly documented

## Proof Boundary

- The gate bundle above is currently simulator-backed evidence, using `iverilog` and `vvp` under WSL.
- In this root, `antecedent_triggered` means the antecedent fired in a simulation trace; it does not mean JasperGold proved a `cover property`.
- No case in `rtl_cases_real_scale120` should be reported as proof-level reachable or proof-level unreachable unless separate JasperGold artifacts are added and cited.
- The gate scripts now accept external Jasper antecedent-reachability CSV inputs, so proof-backed admission can be layered on later without changing the dataset schema.
- Until such Jasper CSV or report artifacts are actually attached to a run, the checked-in `scale120` outputs remain simulation-backed only.

## Current Augmentation Clusters

- `case201-208` from `case101_prim_onehot_multihot_suppressed`
- `case209-216` from `case102_prim_onehot_enable_mismatch_suppressed`
- `case217-224` from `case129_prim_onehot_zero_enabled_suppressed`
- `case225-232` from `case103_prim_onehot_addr_mismatch_suppressed`
- `case233-240` from `case137_prim_onehot_addr_false_positive`
- `case241-244` from `case126_prim_regwe_enable_gap`
- `case248-256` from `case104_prim_fifo_full_early`
- `case257-265` from `case105_prim_fifo_empty_late`
- `case266-274` from `case106_prim_fifo_depth_off_by_one`
- `case275-283` from `case130_prim_fifo_empty_early`

These `10` clusters account for the full `80` augmentation-only cases in `rtl_cases_real_scale120`.

## Local Verification Status

- `decoy_structure_scale120.csv` is refreshed and reports `120/120` decoy-complete cases.
- `trace_divergence_scale120.csv` is refreshed and reports `120/120` seen/held-out/decoy divergence.
- This desktop thread still cannot access a working WSL distro or any Windows-visible RTL simulator directly.
- On July 9, 2026, external full-root WSL golden reruns passed `120/120`; see [golden_recheck_scale120_wsl.csv](/D:/AssertionForge-main1/outputs/golden_recheck_scale120_wsl.csv).
- On July 9, 2026, external full-root WSL hardness reruns passed `120/120`; see [hardness_scale120_wsl.csv](/D:/AssertionForge-main1/outputs/hardness_scale120_wsl.csv).
- The current three-track divergence artifact is [trace_divergence_scale120.csv](/D:/AssertionForge-main1/outputs/trace_divergence_scale120.csv), and the full WSL rerun script now also emits [trace_divergence_scale120_wsl.csv](/D:/AssertionForge-main1/outputs/trace_divergence_scale120_wsl.csv).
- These acceptance records are based on WSL `iverilog`/`vvp` reruns, not JasperGold cover or proof output.
- The `40` seed slots are admitted under the simulation-backed gate bundle in this document; no proof-level reachability claim is recorded here.

## Reporting Template

- `seed slots`: report cases without `seed_case_name`
- `augmentation pool`: report cases with `seed_case_name`
- `source projects`: report per-project counts
- `seed modules`: report unique seed modules
- `verification status`: separate locally refreshed structure/divergence from externally rerun golden/hardness
