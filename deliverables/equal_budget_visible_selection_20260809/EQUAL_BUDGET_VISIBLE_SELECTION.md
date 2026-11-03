# Equal-budget candidate pools and visible-only selection

## Protocol

All four pools contain exactly four distinct candidates for every model×case. The primary analysis uses 40 canonical parents; the 120-case table is retained only as a variant-level sensitivity view. Selection may read only compile, seen-good/bad behavior, antecedent hit, non-vacuity, signal legality, reset usage, hardcoding, and representation agreement. Held-out fields are joined after selection.

## Main parent-deduplicated results

| Model | Best visible-only pool/policy | Coverage | Overall strict success | Oracle ceiling |
|---|---|---:|---:|---:|
| Claude | raw_k4 / fallback | 100.0% | 72.5% | 80.0% |
| GPT | raw_k4 / fallback | 100.0% | 57.5% | 77.5% |

For Claude, raw_k4 + score_ranking reaches 77.5% (31/40), versus an 80.0% raw-k4 oracle ceiling. For GPT, raw_k4 + score_ranking reaches 62.5% (25/40), versus a 77.5% ceiling. Mixed raw2+temporal2 and four-representation pools do not beat raw_k4 under the same budget in this run.

All visible policies except the explicitly named fallback arm abstain when a pool has zero hard-pass candidates. Fallback is labeled explicit_fallback_first; no repair was run. First/random remain baseline choice rules only when at least one hard-pass candidate exists in the pool.

## Held-out isolation audit

Original visible selection hash: `8efabdd8858c39e595896a472ee51f287ed4485001839b8147ed6bd9b9365929`
Held-out deleted hash: `8efabdd8858c39e595896a472ee51f287ed4485001839b8147ed6bd9b9365929`
Held-out shuffled hash: `8efabdd8858c39e595896a472ee51f287ed4485001839b8147ed6bd9b9365929`

All three hashes are identical. Oracle is deliberately excluded because it is an evaluation-only upper bound. Hard-filter and abstain return `abstain_no_hard_pass`; fallback uses the explicit label `explicit_fallback_first`; no repair was run.

## Interpretation limits

The random policy is deterministic for reproducibility, not an average over random seeds. Representation agreement is exact canonical-assertion agreement across representations, not semantic equivalence. McNemar and bootstrap intervals are model-specific and parent-paired; the comparison table is exploratory and uncorrected for multiple comparisons.
