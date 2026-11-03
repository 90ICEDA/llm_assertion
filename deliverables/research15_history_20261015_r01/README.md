# Original historical Ibex #166 reproduction

The original downloaded decoder and package are compiled unchanged. A handwritten native SVA checks against frozen independent ISA classifications; a separate Python oracle adjudicates actual port traces. No LLM-generated assertion or full-core trap reproduction is claimed.

| Revision | Compile | Execution | Checks | Violations | Transactions with violation |
|---|---|---|---:|---:|---:|
| before | passed | completed | 1374 | 423 | 42 |
| after | passed | completed | 1374 | 0 | 0 |

Repair witnesses: 423 sample/config observations; these are not independent bugs. Both obligations: ['illegal_branch_persists', 'op_bit28_illegal'].

The native assertions are deliberately simple ISA-output checks. Simulation within these inputs is not formal proof. Original HWE-Bench full-core script is archived, not run. Zero model calls. Protocol, exact commands, tool version, raw logs, VCD, source hashes, transaction IDs and independent judgments are retained.

Sources: [PR #166](https://github.com/lowRISC/ibex/pull/166), [issue #163](https://github.com/lowRISC/ibex/issues/163). Before c96ece04296c3c69df578d760aa8a66f9b886fef; fixed 3bcbb50630a7cb0278623a8a1f5d262e0220dd86. Original patch application exactly reproduces fixed decoder bytes.

Reproduction: `python3 scripts/research15_history.py prepare`, then `run`, then `report` in WSL after saving the pinned source downloads. Existing runs are exclusive. See protocol.json for all parameters and source constraints.

## Source/specification audit and new-run commands

`stat_spec/audit.json` verifies the exact cited verilog-axis source. It has an AXI monitor/statistics interface and none of the four local frame_done/stat_valid signals. Historical two-cycle/overlap semantics therefore remain unconfirmed; no original stat parent success is credited. Byte differences between downloaded and vendored source are separately reported from newline-normalized text equality.

To reproduce without altering existing artifacts: `python3 scripts/research15_history_cli.py --run NEW_NAME prepare`; then the same command with `run` and `report`. Preparation reuses verified immutable source downloads, copies no old execution results, and freezes new inputs before execution. Original raw download URLs and commits are in protocol.json and archived official PR metadata.

`representative_witnesses.json` contains an actual original-RTL transaction for each of the two repair obligations. `audit.json` keeps the parent/obligation/sample denominators distinct.

## Combined history index (2026-10-15)

`combined_summary.json` keeps the two historical parent bugs separate. New parent #166 is admitted only at original decoder-module scope. Prior #54 receives a new boundary cohort: 119 new low16 encodings, before 32 violations and after 0; 87 controls pass both revisions. Five old development anchors are separately reproduced (5 failures before, 0 after). All 32 new failures are C.SLLI rd=x0 HINTs, absent from the specific prior 223-boundary/5-anchor corpus. This is engineering validation, not learned-assertion holdout success. No parameters exist on the #54 original module.

- #166: `summary.json`, `representative_witnesses.json`, `execution/`, `audit.json`.
- #54: `ibex54_new_boundaries/README.md`, `summary.json`, `protocol.json`, `execution/`.
- Stat provenance: `stat_spec/audit.json` remains unknown for historical overlap/two-cycle semantics.
- All 35 screened records: `screening_status.json`; 33 are not locally reproduced in this phase, including original shortlisted #222 and #1735.
- Independent code review for the main task: `acceptance_adapter_review.json`; synthetic adapter checks are not hardware experiment results.

Scripts added: `scripts/research15_history.py`, `research15_history_cli.py`, `research15_history_audit.py`, `research15_history_ibex54.py`. All use existing simulation infrastructure without modifying it. Native SVA here is handwritten; model calls and formal solver calls are zero.
