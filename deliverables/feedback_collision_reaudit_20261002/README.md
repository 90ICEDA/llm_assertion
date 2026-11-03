# Feedback collision re-audit (2026-10-02)

## Final per-pair semantic and time-position review

The latest `adjudicated_pairs.jsonl` and `pair_index.csv` map **each of the 294 pairs** to a case-specific repair obligation in `repair_obligations.json`. Each side records the actual trigger, checked relation, cycle alignment, missing trigger/check signals, and any same-cycle self-comparison. Every row also retains the spec text, the original buggy/fixed RTL paths, an RTL line delta, the original candidate evidence, the frozen feedback signature, a quality relation, and confidence. `unconstrained_formula_counterexample` gives a two-sample Boolean distinguishing assignment for 254 pairs; it is **not** claimed reachable on either RTL.

Semantic-equivalence outcomes are: **12 proved equivalent by a same-cycle Boolean rewrite**, **162 distinguished by verified existing probe replay**, **1 distinguished by the existing legal fixed-RTL held-flush replay**, and **119 UNKNOWN**. In particular, a count difference on the same probe means the two assertion checkers cannot be semantically identical on that replay, even when their binary FP/TP signatures agree. Relative *repair quality* is a separate judgment: **1 evidence-supported A-better pair (case510 slots 06/07)**, **12 equivalent-assertion pairs**, and **281 UNKNOWN**. The 293 `both wrong` categories state that each side has a known defect; they do not rank two defective assertions.

For the **162 count-different pairs**, `count_timeline_162.jsonl` stores every failing sample time on fixed and buggy RTL, both antecedent time lists, shared and side-only failure times, and links to the replay record. `count_timeline_162.csv` is the compact index. The read-only VPI monitor `scripts/fail_time_vpi.c` observes the counters in the **original compiled** probe binaries, without modifying their checker or RTL. All **3,221 unique candidate-probe runs** matched their historical antecedent and fail totals; all **4,737 pair–probe comparisons** are covered. Times are in picoseconds. In **110 pairs**, at least one probe has failure clock positions unique to *both* assertions; in **52 pairs**, the observed positions consist of shared failure clocks plus extra clocks on one side. These facts separate timing behavior from mere aggregate count. They do **not** establish that adjacent hits belong to one transaction or one root violation: the original stimuli and checker have no transaction ID. `same_violation_identity` remains `UNKNOWN` for all 162, with the exact timestamps available for further RTL-specific review. No quality ordering is inferred from larger fail counts.

The first timestamp attempt recompiled and instrumented the checker. It failed to reproduce historical counts on **643/3,221** runs, including a one-hit end-of-simulation scheduling difference. All its raw checker, stdout, VCD and mismatch artifacts remain in `time_replays/` and `time_replay_*.json`. The later VPI run reproduced **3,221/3,221** and is the authoritative time-position evidence in `vpi_replays/`. This failed attempt is retained rather than silently discarded.

Reproduction from the repository root, in order:

```powershell
node scripts\reaudit_feedback_collisions.js
node scripts\adjudicate_feedback_collisions.js
wsl bash -lc 'cd /mnt/d/AssertionForge-main1 && python3 scripts/replay_collision_fail_times_vpi.py'
node scripts\analyze_collision_fail_times.js
node scripts\adjudicate_feedback_collisions.js
```

The final adjudication pass links the verified timeline back to the semantic-equivalence field. The VPI module build and every individual `vvp` command are recorded in the replay records. Original experiment files are read-only inputs. The four-auditor decision protocol below remains a proposed workflow; the scripts implement this scoped review, not a general formal-proof system.

## Earlier automated pass (retained for provenance)

The original `pairs.jsonl` is preserved as the first-pass inventory. The evidence-scoped review is `adjudicated_pairs.jsonl`; `pair_index.csv` is its compact 294-row index and `count_difference_162.csv` is the count-difference subset. The adjudication script reads each candidate's AST/SVA and original fixed/buggy run, all existing probe results, each case's obligation text, and a line-level delta derived from the two RTL files. `adjudication_incidents.json` is empty: no referenced probe result was unreadable.

The evidence-scoped categories are **293 `both wrong`** and **1 `quality difference`**. In 292 pairs, both assertions have direct defects recorded by the existing tests: a fixed-RTL false positive, a miss of the parent target on the original buggy testbench, or both. In the remaining `both wrong` pair (case505 slots 06/07), both omit the required later status pulse and captured length; the previously corrected reading of slot 07 samples `frame_done_i` in the consequent cycle. The one quality-difference pair is case510 slots 06/07, supported by the prior held-flush replay. These classifications describe *known defects relative to the repair obligation*. They do not imply the two wrong assertions are equivalent or equally bad. The initial automated pass left semantic equivalence UNKNOWN for all pairs; the final outcomes are stated above.

For the **162 count-different pairs**, `count_difference_162.csv` lists the number of selected probes with different fixed and buggy fail-hit totals. All 162 are among the `both wrong` pairs. The count mechanism is `UNKNOWN` in every row: the original checker reports only aggregate antecedent and fail-hit totals, without cycle or transaction IDs. Thus we can establish different *multiplicity* but cannot identify from existing raw data whether a single violation repeated or distinct violations occurred. The quality category in those rows comes from independent fixed-RTL false-positive or target-miss evidence, never from which candidate has the larger count. `behavior difference only` is therefore not asserted for any pair. The absence of that label is an evidence limit, not evidence that repeated failures never occur.

Run the second pass after the reconstruction:

```powershell
node scripts\adjudicate_feedback_collisions.js
```

The second pass is reproducible and does not modify either RTL or source probe artifacts. Its judgments are limited to the stored traces and explicit repair obligation. A complete semantic equivalence or same-root-cause decision would require a mutual-implication proof or time-indexed violation replay, respectively. Preserve `UNKNOWN` until that evidence exists.

## Scope and result

This reuses the frozen `disagreement_guided` 32-probe feedback, eight existing candidates per parent, and existing 64-probe run artifacts. It generates no candidates or probes. The runner reconstructs **294** pairs with identical selected FP/TP ID sets; **162** have different fail-hit counts on at least one selected probe. There were **zero unreadable or missing artifacts** in this run. All 294 rows, including 293 `UNKNOWN` decisions, are retained in `pairs.jsonl`. `failures.json` is an empty array, not an omitted file.

One existing natural pair establishes the sought pattern: `case510_cc_spill_register_flush_push_priority` slots **06/07** share the frozen full FP/TP sets, but slot 07 falsely fires on a legal held-flush fixed-RTL trace while slot 06 passes that trace. Both detect the buggy RTL. Slot 06 is only **PARTIAL** against the full repair obligation: it does not check that the pushed data remains hidden on a simultaneous flush/push. See the already preserved [replay](../blind_reaudit_20260921/witnesses/case510_held_flush/replay.md), its raw command capture, and the local spec, patch and RTL paths in the pair row. This is a quality difference within the current evidence, not proof that slot 06 is a complete specification. No synthetic weakening, over-constraint, or vacuity case was needed to find a natural example.

The 162 count differences are evidence of *different event frequencies*, not 162 quality differences. A single violated condition can fire repeatedly across clock cycles. A count difference becomes a quality difference only when tied to an obligation-relevant reachable scenario, such as a fixed-design false positive, target miss, or vacuous antecedent. Until then its category stays `unknown`. The existing 60-pair manual separability review found 34 different fail-hit behaviors, but explicitly did not establish that each difference changed assertion quality.

## Fields and decision limits

Each JSONL row contains `pair_id`, candidate identifiers and full SVA, the source ASTs in `semantic_difference`, the identical selected feedback signature, `quality_relation`, `category`, `evidence`, and `confidence`. `count_difference_probes` links both original result JSON files and their exact fixed/buggy fail-hit counts. Case context links the spec (repair obligation), mutation patch, buggy RTL, fixed RTL, and golden SVA. These references point to existing raw artifacts, which are preserved in place.

`UNKNOWN` is deliberate: textual SVA differences and finite binary feedback alone do not prove semantic equivalence, weakening, over-constraint, or obligation coverage. `behavior difference only`, `both acceptable`, and `both wrong` require an actual semantic argument and sufficient evidence, so no row was assigned those labels merely from counts. The one `quality difference` label relies on the existing replay. This inventory is a first review pass; it does **not** claim human semantic adjudication of the remaining 293 pairs.

## Proposed feedback auditor workflow

1. **Semantic auditor:** translate each assertion into its trigger, cycle alignment, checked signal/value, and reset scope; compare these to the spec, patch and both RTLs. Record the concrete semantic difference, not just syntax.
2. **Quality auditor:** test whether either assertion misses a required trigger or consequence (weakening), rejects a legal fixed behavior (over-constraint), or has an unreachable antecedent (vacuity). Preserve partial and incomparable outcomes.
3. **Evidence auditor:** inspect legal reachability and original fixed/buggy run artifacts; group fail hits by underlying event to distinguish repeated triggers from distinct violations. Request a targeted replay only for a specific unresolved hypothesis. Preserve compile errors, timeouts and failed witnesses.
4. **Decision auditor:** accept a quality ordering only when the evidence supports it. Otherwise keep `UNKNOWN`, state the missing witness or proof, and record confidence. A preference selector should abstain on unresolved ties.

For the 162 count-different pairs, review fixed-RTL count differences first, then buggy-only count differences; use the linked original probe result and stimulus. A fixed-RTL excess is a *lead* for over-constraint, never a verdict by itself. Record whether the same violation repeated in multiple cycles. The remaining 132 count-equal pairs still need semantic review because equal counts can hide different trigger and consequent behavior.

## Reproduction and logs

From the repository root on Windows:

```powershell
node scripts\reaudit_feedback_collisions.js
```

The portable Python source is `scripts/reaudit_feedback_collisions.py`; this environment lacked a native Python command and WSL did not launch reliably, so the checked run used Node. The exact command and observed output are preserved in `run.log`. The script overwrites only this audit's `pairs.jsonl`, `summary.json`, and `failures.json`; original experiment artifacts are read only. The full evidence path for each pair is present in its row.
