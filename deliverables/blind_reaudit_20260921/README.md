# Corrected lineage preservation and blind re-audit — 2026-09-21

## Outcome

The old case505 “real selection impact” claim is **RETRACTED** in the prior delivery; its original raw evidence and `MISSING` ledger remain in place. The prior case misread `frame_done_i |=> (stat_valid_o == frame_done_i)`: the right-hand `frame_done_i` is sampled in the consequent cycle.

In a new four-parent draw that excluded all six previously inspected parents, 28 model-response natural assertions (slots 1–7) were judged against repair requirements before opening the new batch's old verification feedback. Slot 8 is explicitly a **synthetic rendered control**: its AST is model-originated, but source code injects a contradictory antecedent `x && !x`; all four slot-8 outputs were excluded from judgments and feedback comparisons. The pre-feedback seal is `PRE_FEEDBACK_FREEZE.json` (SHA-256 `cc409941757e80f309eb2c61b0a35c65b8a6b882514ebd2bada91d09ab7cd616`). The seal rechecked with zero mismatches after unblinding.

One actionable case survived replay: `case510_cc_spill_register_flush_push_priority` slots 06 and 07 have identical **full FP and TP ID sets**, not merely equal counts, under both old probe policies. Yet held-flush replay on fixed RTL shows slot 06 passes while slot 07 has a false positive. Both fail on buggy RTL. The actual Phase-B schedule used both as SFT anchors 136 times each. Thus old feedback failed to exclude an assertion that is unsound for a legal fixed-design behavior; it did affect admission to the training batch. This is narrower than claiming a measured effect on final model accuracy. Slot 06 itself is only `PARTIAL`, not a complete repair specification.

## Audit boundary

The new sample was random within 24 parents after excluding six already inspected; it was not an unconditional random draw of all 30. The reviewer had seen old feedback in the prior task, so human-memory blindness cannot be certified. The new selected parents' feedback files were not opened for this re-audit until after the new judgments and pairwise comparisons were sealed. Pre-feedback provenance checks used request/raw response/rendered assertion and RTL/patch/spec; runtime compile verdicts were checked only after unblinding. No active probe sweep, new preference construction, or training was performed. A single targeted, replayable witness was run after unblinding.

The prior Phase-B adapter, `training_result.json`, `train_log.jsonl`, and latest-checkpoint pointer remain `MISSING` in this checkout. The previous [lineage artifact inventory](../lineage_and_blind_review_20260918/lineage/artifact_inventory.csv) and raw copies are preserved. Therefore physical adapter bytes and original training logs remain unverifiable; the OOD generation scripts/manifests only establish the declared historical load path/hash.

## Evidence map

- `selected_parents.csv`, `sampling_and_provenance_manifest.json`: seeded sampling frame and exclusions.
- `candidate_provenance.csv`, `pre_feedback_file_inventory.csv`, `pre_feedback_raw/`: source paths, original file hashes, model responses, RTL, patch, specs and copied raw artifacts. Each slot-8 row is separate and marked synthetic control.
- `repair_requirements_frozen.md`, `independent_judgments_frozen.csv`, `pairwise_judgments_frozen.csv`, `PRE_FEEDBACK_FREEZE*.json`: pre-unblind judgment and seal.
- `legacy_feedback_snapshot.json`, `postfreeze_feedback_comparison.csv`, `case510_original_candidate_verification.json`: post-seal original feedback and full-signature comparisons.
- `case510_training_batch_rows.json`: exact schedule rows demonstrating both SFT anchor admissions.
- `witnesses/case510_held_flush/`: new testbench, original stdout, compiled simulation artifacts, and replay commands.
- `status_ledger.csv`: FOUND, MISSING, NOT FOUND, UNKNOWN and timeout accounting without conflating “not run” with “not found after search.”

The new witness establishes a fixed-RTL false positive for slot 07. No replayable witness was established for the other tied case (`case459` slots 02/06), which remains `UNKNOWN` as a selection-impact claim.
