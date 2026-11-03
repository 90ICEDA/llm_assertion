# Native FIFO sampled feedback qualification

Instrumentation qualification passed on 2026-10-16. This is a development qualification, not a new LLM refinement experiment or independent holdout.

- Input assertion: unchanged real-model `shared_initial.json` from `research16_ablation_20261016_r03`; original source is recorded in `provenance.json`.
- Three native Verilator compilations: requested Depth=2 / RAM_PIPELINE=0, Depth=5 / RAM_PIPELINE=1 (actual RAM capacity 8), Depth=4 / RAM_PIPELINE=2.
- Twenty-four native replays: fixed plus engineering mutant for each of tail loss, backpressure, reset cancellation, and continuous/overlapping requests, at all three configurations.
- All 2,688 `$sampled` reference records match independent Python replay of pre-NBA queue state and the ordinary port trace. Reference data comparison is intentionally undefined when the reference queue is empty.
- All 12 fixed replays have legal stimuli, zero independent oracle violations/unknowns, and zero native assertion failures.
- Tail-loss mutant has a first `drain_no_loss` violation at each configuration; the historical initial candidate has no mapped drain property. The evidence includes the outstanding accepted transaction and the fixed/mutant sampled drain checkpoint.
- Backpressure scenarios observe 47–49 stalled output samples and simultaneous enqueue/dequeue. Reset scenarios observe one reset with accepted transactions pending in each configuration. Multicycle responses are observed in all families.
- Maximum outstanding accepted requests in backpressure: 3, 10, and 7 for the respective configurations. These counts include read pipeline storage and MUST NOT be reported as RAM full counts. Exact internal RAM-full-state coverage remains unknown without an internal state probe.
- Engineering corrupt payload and reset-residue output faults are artificial boundary faults applied to actual upstream FIFO RTL, not historical upstream fixes.

The module returns original native replay and independent oracle records, plus `reference_trace`, `sampling_qualification`, and `coverage_audit`. `feedback(fixed, mutant, ledger)` reports native trigger/failure counts and sampled signal windows, first oracle violations, associated accepted transactions, and evidence classification. It does not provide generated predicates or repair the candidate.

Run from repository root with a new output directory:

```powershell
wsl -- python3 scripts/research17_fifo_feedback.py --qualify --out deliverables/research17_feedback_qualification_20261016_r02
wsl -- python3 scripts/test_research17_fifo_feedback.py
```

The three focused Python regression checks passed (pre-NBA simultaneous push/pop and reset, rejection of post-update count, and missing/empty reference traces). Native qualification, not these logic checks alone, establishes the recorded sampling behavior.

Costs: 0 model calls, 0 model tokens, 3 native compilations (each also starts the default smoke replay), 24 explicit scenario replays, 0 formal queries. Native finite replay is not a formal proof.
