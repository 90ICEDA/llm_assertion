# Behavioral Preference Pilot v1 — Final Report

Status: **NO-GO**. Do not expand to 3,000–10,000 pairs.

## Data
- 30 parents, 3 projects, 240 executable candidates.
- Observed failure modes: `{"fixed_false_positive": 134, "target_miss": 100, "vacuous": 36}`.

## Probe ablation

| Policy | Distinguishing cells | Unique distinguishing probes | Pairs/query | Unique FP/TP signatures | Timeouts | Selected execution seconds | Frozen SCS@1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| random_legal | 30.17% | 64.06% | 0.5031 | 100 | 0 | 691.27 (6400/7680 cells) | 0.00% |
| disagreement_guided | 30.38% | 64.38% | 0.5042 | 101 | 0 | 687.09 (6400/7680 cells) | 0.00% |

Joint end-to-end probe wall-clock (both policies, inseparable in v1): 3243.90s.

## Dominance
- random legal: 483 strict pairs.
- disagreement guided: 484 strict pairs.
- No cross-parent/policy comparisons; incomparable relations omitted.

## Frozen Top-1
- All five adapters used the same 48 queries, greedy one-shot generation, no repair/reranking/selector.
- Project-OOD: structural N/A because Pilot training covers all three frozen projects.
- Full method SCS@1 is 0% on unseen-parent and unseen-bug-family.

## Decision
The +5pp SCS@1 gate failed and Fixed-Safe decreased. Pilot v1 is NO-GO.
