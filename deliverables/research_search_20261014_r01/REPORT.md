# Four-policy search pilot (2026-10-14)

All 864 queries are new physical runs. Same frozen pool, three seeds and 12-query budgets. Diagnostic Icarus procedural checks, not native SVA or formal proof. All evidence is development data.

| Parent | Method | Distinct FP / FN gaps | Repair witness obligations | Unknown spec queries |
|---|---|---|---|---|
| onehot | ordinary | 7 / 5 | multihot_detect | 0/36 |
| onehot | disagreement | 7 / 5 | multihot_detect | 0/36 |
| onehot | differential | 7 / 5 | multihot_detect | 0/36 |
| onehot | contract | 7 / 5 | multihot_detect | 0/36 |
| filter | ordinary | 1 / 0 | qualified_value | 0/36 |
| filter | disagreement | 1 / 1 | qualified_value | 0/36 |
| filter | differential | 1 / 1 | qualified_value | 0/36 |
| filter | contract | 1 / 0 | qualified_value | 0/36 |
| fifo | ordinary | 5 / 7 | empty_when_idle | 0/36 |
| fifo | disagreement | 5 / 7 | empty_when_idle | 0/36 |
| fifo | differential | 5 / 7 | empty_when_idle | 0/36 |
| fifo | contract | 5 / 7 | empty_when_idle | 0/36 |
| spill | ordinary | 6 / 5 | collision_empty | 0/36 |
| spill | disagreement | 6 / 5 | collision_empty | 0/36 |
| spill | differential | 6 / 5 | collision_empty | 0/36 |
| spill | contract | 6 / 6 | collision_empty | 0/36 |
| stat | ordinary | 0 / 0 | none | 36/36 |
| stat | disagreement | 0 / 0 | none | 36/36 |
| stat | differential | 3 / 3 | valid_latency | 35/36 |
| stat | contract | 3 / 3 | valid_latency | 24/36 |
| intr | ordinary | 0 / 0 | none | 36/36 |
| intr | disagreement | 0 / 0 | none | 36/36 |
| intr | differential | 0 / 0 | none | 36/36 |
| intr | contract | 0 / 0 | none | 36/36 |

## Focused 11 pairs

| Pair | Parent | ordinary / disagreement / differential / contract gap counts |
|---|---|---|
| 481caaa206d62a874e6212a0 | case135_prim_intr_enable_mask_ignored | 0 / 0 / 0 / 0 |
| d1cfb1097a5ce1c8514cda45 | case135_prim_intr_enable_mask_ignored | 0 / 0 / 0 / 0 |
| 3c7237fc0b630f1ab6d3947f | case438_cc_fifo_protocol_suppress_2 | 2 / 2 / 2 / 2 |
| c0c735fabb19f0f95295b928 | case438_cc_fifo_protocol_suppress_2 | 2 / 2 / 1 / 1 |
| 3e927f724aab0f75444ca4ed | case438_cc_fifo_protocol_suppress_2 | 2 / 2 / 2 / 2 |
| f463157a169a59d26038858a | case438_cc_fifo_protocol_suppress_2 | 2 / 2 / 1 / 1 |
| 299bedd4f9e969b4d2b2640b | case438_cc_fifo_protocol_suppress_2 | 2 / 2 / 2 / 2 |
| 62626ddb3bfd821cb0b7efa7 | case505_axis_stat_counter_frame_pulse_early | 0 / 0 / 2 / 2 |
| ad1bbcc36db7454db4993243 | case505_axis_stat_counter_frame_pulse_early | 0 / 0 / 2 / 2 |
| c847a262290a70a4f1fc0524 | case505_axis_stat_counter_frame_pulse_early | 0 / 0 / 0 / 0 |
| c83fbf0d527e60fb2850b01b | case510_cc_spill_register_flush_push_priority | 1 / 1 / 1 / 2 |

`pair_results.json` contains each method's exact gap IDs, added gaps versus ordinary and raw witness locations. `paired_gain.json` preserves both positive and negative differences for each seed. A distinct candidate gap is not an independent bug.

Stat timing: frozen spec_sources.json cites the local spec (two-entry pipeline, original captured length). Overlap permission is not explicit; all overlap-bearing query evidence is unknown and excluded. No upstream historical stat fix is established. Spill invalid data and intr mask timing remain unresolved. FIFO Depth=0 is a regression case and absent original-target witness remains absent.

Contract search is a finite three-category policy pilot. Gap template scheduling uses exposure counts, not a general constraint solver; no completeness claim or mechanism-superiority claim. The native-SVA/model refinement chain is outside this runner.

Commands: `python3 scripts/research_search_compare.py prepare`; `python3 scripts/research_search_compare.py run`; `python3 scripts/research_search_compare.py report`. Use WSL with Icarus. Existing output is append-protected; a second run needs a new directory constant and freeze.

Historical Ibex #54 remains separate: prior actual original-RTL reproduction is in `deliverables/obligation_evidence_20261013_r02/historical_screening/ibex_54`. Upstream PR https://github.com/lowRISC/ibex/pull/54 and issue https://github.com/lowRISC/ibex/issues/51. This runner neither reexecutes nor claims new model validation on Ibex.

## Audit and configurable reproduction

The complete audit verified 864 queries / 72 cells / 1728 physical RTL runs, frozen source hashes and original raw input hashes. See audit/audit_result.json and physical_runs.json. Existing Ibex original-source/test hashes also match; this is a read-only prior-result audit, not a fresh reproduction.

Use `python3 scripts/research_search_cli.py --run NEW_NAME prepare`, then `run`, then `report`; `python3 scripts/research_search_audit.py --run NEW_NAME` audits the complete result. The CLI wrapper supports new directories without editing frozen code. `--case` permits independent case execution.

Raw handshake annotations omitted reset gating; their name was too strong. The authoritative FIFO transaction ledger is audit/fifo_transactions.json, which records presentation, accepted transfers, reset cancellation and bounded pending status. Gap/pair results do not depend on the erroneous annotation. Full limitations are in audit/limitations_and_errata.json.
