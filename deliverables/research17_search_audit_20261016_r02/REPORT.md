# Archived development search requalification

No new RTL simulation or model call. No independent holdout read.

Witness qualified: True. Target: drain_no_loss, cycle 111.

| Method | Queries | Replays | Gap classes | Additional contract classes |
|---|---:|---:|---|---|
| ordinary | 12 | 60 | reset_residue/no_unsolicited_output, reset_residue/reset_cancellation | drop/drain_no_loss |
| candidate_disagreement | 12 | 60 | drop/drain_no_loss, reset_residue/no_unsolicited_output, reset_residue/reset_cancellation |  |
| raw_difference | 12 | 60 | reset_residue/no_unsolicited_output, reset_residue/reset_cancellation | drop/drain_no_loss |
| contract_coverage | 12 | 60 | drop/drain_no_loss, reset_residue/no_unsolicited_output, reset_residue/reset_cancellation |  |

Contract adds drop/drain_no_loss relative to ordinary and raw-difference, but adds none relative to the degenerate disagreement/exploration arm. No general superiority claim.

Target transaction alignment and native trigger details are in witness_qualification.json. The original a0 property checks payload on an output handshake: it triggers on the first three responses but cannot trigger when the fourth response disappears. This is an unprotected drain obligation, not an entirely vacuous candidate.

Single-property candidate-disagreement arm is uniform fallback. Results are small fixed-budget observations, not a demonstrated general search advantage. Reset-cancellation and no-unsolicited-output are distinct obligations for one reset-residue failure mechanism, not two independent parent bugs.

Costs are historical actual costs, reused once; audit adds zero model/native/formal calls. All evidence remains development data. Artificial output-boundary faults are not the original historical FIFO presented bug.

API: `validate_witness(candidate_path, witness_path)` refuses mismatched candidate replay and unknown checks. A revised candidate requires a new native replay; this API cannot evaluate new SVA from old logs.
