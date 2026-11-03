# Real RTL Scale120

This root is generated from admitted real-RTL OpenTitan seeds, a reduced augmentation pool, and additional real OpenTitan mutation-backed seeds.

- total cases: 120
- unique seed coverage: 40
- augmentation/variant pool: 80
- combination/same-cycle cases: 101
- temporal/cross-cycle cases: 19
- source projects: opentitan only (120/120)
- unique seed modules: 8

Generation policy:
- keep only real OpenTitan-backed cases in this root
- preserve the seen + held-out + overfit-decoy three-track structure for every case
- count seed-backed variants separately from unique seed coverage
- prefer combination/same-cycle additions when filling new seed slots

Counting policy:
- Cases without `seed_case_name` are the only cases that count as unique seed coverage.
- Cases with `seed_case_name` are augmentation-only and do not count as new module, new seed, or new bug-family coverage.

Per-case trace structure:
- seen trace: `tb.v` + `waveform_good.csv` / `waveform_bad.csv`
- held-out trace: `tb_holdout.v` + `waveform_good_holdout.csv` / `waveform_bad_holdout.csv`
- overfit decoy: `tb_decoy.v` + `waveform_good_decoy.csv` / `waveform_bad_decoy.csv`

Local verification note:
- decoy structure and seen/held-out/decoy divergence were refreshed locally for all 120 cases
- the current recorded full-root reruns are simulator-backed WSL checks: [golden_recheck_scale120_wsl.csv](/D:/AssertionForge-main1/outputs/golden_recheck_scale120_wsl.csv) = `120/120` pass and [hardness_scale120_wsl.csv](/D:/AssertionForge-main1/outputs/hardness_scale120_wsl.csv) = `120/120` pass, last refreshed on July 9, 2026
- those reruns used `iverilog` + `vvp` under WSL; they were not JasperGold runs
- the golden/hardness recheck scripts can now ingest external Jasper antecedent-reachability CSV results, but no such Jasper outputs are checked into this root today
- this root does not include JasperGold cover/property-proof artifacts, so it does not claim proof-level reachability or proof-level unreachable results

Acceptance policy:
- See [DATASET_ACCEPTANCE.md](/D:/AssertionForge-main1/DATASET_ACCEPTANCE.md) for the seed-vs-augmentation counting rules.
