# Unified Result Reporting Contract

Every reported result must identify both **selection scope** and **aggregation unit**.
Rates with different values in either dimension are not directly comparable.

## Required selection scopes

1. `candidate_level`: evaluate every generated candidate among the first `k` candidates.
2. `first_candidate`: evaluate candidate index 0 (or the lowest available index) only; `k=1`.
3. `case_any_of_k`: a case succeeds when any of its first `k` candidates succeeds.

## Required aggregation units

Each selection scope must be reported at all three units:

1. `candidate`: micro average over selected candidate/derived observations.
2. `case`: macro average after grouping observations by case.
3. `parent_bug`: macro average after grouping case scores by independent `parent_bug_id`.

The default parent aggregation is `macro_mean_cases`: trace variants do not become extra
independent bugs, and parents with more variants do not receive more weight.

## Required columns on every result table

- `model`
- `method`
- `selection_scope`
- `aggregation_unit`
- `k`
- `metric`
- `value`
- `candidate_observation_count`
- `case_count`
- `parent_bug_count`
- `deduplicated`
- `dedup_key`
- `parent_aggregation`
- `overlap_status`
- `sample_definition`
- `ci_level`
- `ci_lower`
- `ci_upper`
- `ci_method`
- `bootstrap_unit`
- `bootstrap_repetitions`
- `random_seed`

`overlap_status` must be one of `overlap`, `non_overlap`, `mixed`, or `unknown`.
Unknown is permitted for intermediate files but must not be used in a final comparison table.

## Comparison rule

Two rates may be placed in the same direct comparison only when all of these match:

- metric
- selection scope
- aggregation unit
- k
- sample definition
- overlap status
- case population and parent population

Otherwise they must be shown in separate panels or explicitly labelled as non-comparable.

## Statistical confidence

- Main-method rates require a 95% cluster-bootstrap confidence interval.
- The bootstrap sampling unit is always `parent_bug_id`; all cases, trace variants,
  and candidates belonging to a sampled parent travel together as one cluster.
- Pairwise main-method comparisons require an exact paired McNemar test on the
  intersection of parent bugs covered by both methods.
- Pairwise tables must report `n01`, `n10`, the exact two-sided p-value, paired
  risk difference, and matched odds ratio. The parent-level binary outcome rule
  (`all_observations`, `any_observation`, or `majority`) must be explicit.
- Trace variants never increase `paired_parent_count` or bootstrap sample size.
