# Research20 prospective FIFO development evidence audit

Executed 2026-10-18. No model calls; existing real-model initial candidate from research19 r03 used unchanged. This is development evidence, not independent evaluation or a new generation success.

## Observed native results

Two compile operations, 18 case executions and two compile smoke executions completed. Nine cases cover a common corrupt regression and tail-loss, reset-pending, backpressure and overlap at depth=2/pipeline=0 and depth=5/pipeline=1 (RAM capacity rounds to 8).

All legal control and sampling-health checks passed. The ledger has 6,578 obligation/sample rows: seven detected targets, six missed targets, zero false positives and zero unknown admission rows. Another 110 later violation rows remain attribution-unknown and are not credited as independent target events.

| Obligation | First-violation targets | Independent checks on correct control |
| --- | ---: | ---: |
| order_payload | 7 | 401 |
| drain_no_loss | 2 | 8 |
| no_unsolicited_output | 2 | 401 |
| reset_cancellation | 2 | 119 |
| stall_stability | 0 | 171 |

Tail-loss targets occur at cycle 111 in both configurations. Reset-residue first violations occur at cycle 26 and 32; each physical event violates both no-unsolicited-output and reset-cancellation. They are not four independently different fault mechanisms. Existing duplicate/corrupt defects are detected by the initial order property.

Backpressure legal checks are real native-port observations: the two directed backpressure controls each have 47 stable-stall checks. Existing boundary fault modes do not deliberately break valid/data while stalled, and this run found no independent stall-stability violation. Consequently these cases can establish legal triggering and false-positive checks, but not detection coverage for that obligation.

## Scope and reproducibility

Run `wsl -- python3 scripts/research20_cases.py --out deliverables/research20_cases_20261018_r02` from repository root (always choose a fresh output directory). `cases()` exposes the fixed nine-case development list to the main loop. Seeds and complete scheduled inputs are in cases.json and plan.json. All actual native source, commands, tool versions, VCDs, trace, sampled reference state, independent oracle and evidence ledgers are under native/.

This is actual upstream axis_fifo with existing artificial output-boundary faults, not an upstream historical defect reproduction. No formal queries were performed. Exact internal full-state coverage remains unknown; accepted handshakes and externally observed backpressure are recorded. Finite simulation is not a proof.

Source snapshot was added after execution; see execution.command.json for the precise reporting-only post-execution edit. Actual compiled tb.sv and execution inputs are preserved unchanged.
