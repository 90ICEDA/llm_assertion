# Behavioral Preference Closed-Loop — Final Report

Status: **NO-GO**. Expansion to 3,000–10,000 executable pairs is not authorized.

## Frozen scope

- Existing 46-parent main diagnostic asset and 40-parent selector asset are hash-bound and unchanged.
- Any-of-k, selector, and repair remain diagnostic upper bounds only.
- Project-OOD is structural N/A because all three frozen projects occur in Pilot training.

## Executable data

- 30 train parents across common_cells, OpenTitan, and verilog-axis.
- 240 executable candidates (8 per parent).
- Failure observations: fixed false positive 134, target miss 100, vacuous 36.
- Candidate evidence retains prompts, AST/SVA, RTL hashes, stimulus, seeds, commands, versions, logs, antecedent hits, FP, and TP.

## Probe ablation

| Policy | Distinguishing cells | Unique distinguishing probes | Pairs/query | Unique FP/TP signatures | Timeout | Selected wall-clock | Frozen SCS@1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| random legal | 30.17% | 64.06% | 0.5031 | 100 | 0 | 691.27s | 0% |
| disagreement guided | 30.38% | 64.38% | 0.5042 | 101 | 0 | 687.09s | 0% |

Joint end-to-end probe wall-clock: 3243.90s.

## Strict dominance

- random legal: 483 pairs.
- disagreement guided: 484 pairs.
- FP subset, TP superset, at least one strict; no cross-parent/policy comparisons; incomparable relations omitted.

## Training and protocol

- Base model: Qwen3-8B; seed 20260815; exact response-loss budget 245,760 per method.
- Five methods: ordinary SFT, pass-count DPO, scalar-score DPO, random-probe dominance DPO, full disagreement dominance DPO.
- Corrected protocol: strict five-key JSON AST, supervised EOS, strict-trie decoding, deterministic SVA rendering.
- Pilot v1 failed through instruction echo/free-text output degeneration. Pilot v2 fixed executability but did not pass the behavioral gate.
- Frozen train-dev selection chose anchor_20; Phase B refit used all 30 parents and the same 245,760-token budget.
- Phase B smoke passed 24/24 schema/render/signal/pyslang/compile/execution.

## Final frozen first Top-1

| Split | SCS@1 | Fixed-Safe | Target Detect | Family Recall | Non-vacuity | TOR | Compile |
|---|---:|---:|---:|---:|---:|---:|---:|
| unseen parent | 0.00% | 2.86% | 60.00% | 0.00% | 74.29% | N/A | 100.00% |
| unseen bug family | 0.00% | 40.00% | 52.00% | 0.00% | 100.00% | 100.00% | 100.00% |

## Go/no-go

- unseen-parent: SCS delta −2.86pp versus scalar-score DPO; Fixed-Safe decreased from 31.43% to 2.86%.
- unseen-bug-family: SCS delta −4.00pp versus ordinary SFT.
- Required +5pp SCS@1 with no Fixed-Safe decrease was not met.

**Formal decision: NO-GO. Do not expand.**
