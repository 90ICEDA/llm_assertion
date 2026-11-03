# Repair requirements — frozen before legacy feedback access

Sampling frame: 30 training parents in `selected_train_parents.csv`, excluding the six inspected in the superseded review. `System.Random(20260921)` Fisher–Yates selected four of the remaining 24. This exclusion prevents reuse of previously viewed case-level feedback; it means the draw is random within the 24-parent eligible frame, not an unconditional draw from all 30.

Only `buggy.v`, `correct.v`, `mutation.diff`, specification/bug context, testbench interface, model request/raw response, and rendered assertions were considered. Runtime verdict fields and the old probe manifest were not used for the judgments below. The source script `behavioral_preference_v3_gate.py` shows that all eight AST responses are model-originated, but slot 8 is rendered with a deliberately contradictory antecedent (`x && !x`). It is therefore a **synthetic rendered control** and is excluded from natural comparisons. Slots 1–7 have no such injected antecedent.

- `case508_cc_stream_fork_partial_ready_accept`: acceptance requires *both* branch-ready bits (`ready_o = &ready_i`). With only one branch ready, input ready must remain low; valid propagation alone is not the repair.
- `case461_axis_adapter_segment_boundary_early`: in 8-to-32 upsize mode, a non-last segment must not emit a wide output or reset the segment index at `SEG_COUNT-2`; completion occurs at `SEG_COUNT-1` or `tlast`, under backpressure.
- `case510_cc_spill_register_flush_push_priority`: flush dominates simultaneous push. After a sampled flush/push collision, `valid_o=0` and the pushed data are not exposed.
- `case459_cc_trip_counter_trip_one_cycle_late`: at the bound with enable high, `trip_o` is asserted in that same sampled cycle and the counter clears on the following edge. A registered, one-cycle-late trip is the bug.

Judgments below concern **repair relevance and soundness**, not legacy simulation outcomes. `PARTIAL` means a sound necessary subproperty but not the full repair. `MISMATCH` means the assertion is unrelated, overconstrains a legal behavior, or asserts the wrong behavior. `UNKNOWN` is used where the available context cannot establish either. Pairwise `INCOMPARABLE` is not a tie: it means no warranted superiority claim; `UNKNOWN` means evidence is insufficient.
