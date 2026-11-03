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
