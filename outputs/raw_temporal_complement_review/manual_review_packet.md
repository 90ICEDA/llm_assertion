# Raw vs legacy temporal abstraction: manual review packet

Seed: `20260719`; unit: model x case; k: 2; success: case-level any-of-k on held-out; temporal contract: legacy/noncompliant.

Allowed attributions: concrete_value_important, exact_cycle_important, cross_cycle_relation_important, trigger_lost, polarity_lost, duration_lost, raw_noise, hardcoding, vacuity, too_strong

## 1. raw_success_temporal_fail | Claude | case104_prim_fifo_full_early

Parent: `case104_prim_fifo_full_early`; overlap: `False`; bug class: `combination_same_cycle`; family: `fifo_boundary_flag`

Spec: full_o shall assert if and only if the FIFO currently contains Depth entries; it must remain low at Depth-1.

Legacy temporal input:

Abstracted trace summary:
- Repeated writes fill the FIFO toward the full boundary without intervening reads.
- The bug is triggered on the last pre-full write: good behavior keeps full_o low while the FIFO still has exactly one slot remaining, but bad behavior asserts full_o one cycle too early and also reports maximum depth too soon.
- The first divergence is the first boundary approach cycle where good is still "not full" and bad already claims "full".

Raw candidates:

```text
c1 [literal-hardcoding] assert property (@(posedge clk) disable iff (!rst_n) (full_o) |-> (depth_o == 3'd4));
c2 [literal-hardcoding] assert property (@(posedge clk) disable iff (!rst_n) (depth_o == 3'd4) |-> (full_o));
```

Temporal candidates:

```text
c1 [literal-hardcoding] assert property (@(posedge clk) disable iff (!rst_n) (full_o) |-> (depth_o == 3'd4));
c2 [no-heldout-trigger|vacuous|literal-hardcoding] assert property (@(posedge clk) disable iff (!rst_n) (depth_o == 3'd3) |-> (!full_o));
```

Manual verdict: REVIEWED | primary=concrete_value_important | secondary=hardcoding

Evidence: Raw succeeds through the exact depth=4/full boundary; temporal's pre-full antecedent is vacuous on held-out.

## 2. raw_success_temporal_fail | GPT | case128_prim_intr_event_mask_stall

Parent: `case128_prim_intr_event_mask_stall`; overlap: `False`; bug class: `temporal_cross_cycle`; family: `event_output_state_alignment`

Spec: With FlopOutput enabled in Event mode, intr_o shall be derived from the committed interrupt state feedback, not from the speculative next-state in the same event cycle.

Legacy temporal input:

Abstracted trace summary:
- The bug is triggered after reset when an interrupt event arrives while reg2hw_intr_enable_q_i is asserted but the currently committed reg2hw_intr_state_q_i is still clear.
- Good behavior keeps intr_o determined by the committed interrupt state feedback, so intr_o stays low during that event cycle and only reflects the interrupt after the state has been committed; buggy behavior lets intr_o respond to the same-cycle event/speculative next-state and asserts intr_o immediately.
- The first divergence is the first enabled event pulse seen while reg2hw_intr_state_q_i has not yet been updated: both traces match beforehand, then bad raises intr_o on the event cycle whereas good waits until after state feedback indicates the pending interrupt.

Raw candidates:

```text
c1 [clean] assert property (@(posedge clk) disable iff (!rst_n) (event_intr_i && reg2hw_intr_enable_q_i && !reg2hw_intr_state_q_i) |-> (!intr_o));
c2 [clean] assert property (@(posedge clk) disable iff (!rst_n) (reg2hw_intr_enable_q_i && !reg2hw_intr_state_q_i) |=> (!intr_o));
```

Temporal candidates:

```text
c1 [clean] assert property (@(posedge clk) disable iff (!rst_n) (event_intr_i && reg2hw_intr_enable_q_i && !reg2hw_intr_state_q_i) |-> (!intr_o));
c2 [clean] assert property (@(posedge clk) disable iff (!rst_n) (!reg2hw_intr_state_q_i && intr_o) |-> (!event_intr_i));
```

Manual verdict: REVIEWED | primary=exact_cycle_important | secondary=polarity_lost

Evidence: The successful raw candidate checks the delayed committed-state cycle; temporal candidates stay on the immediate event polarity.

## 3. raw_success_temporal_fail | Claude | case125_prim_fifo_wrap_late

Parent: `case125_prim_fifo_wrap_late`; overlap: `False`; bug class: `temporal_cross_cycle`; family: `pointer_wrap`

Spec: When the write pointer is at Depth-1 and a write occurs, the internal write pointer shall wrap on the next cycle rather than stepping to an out-of-range state.

Legacy temporal input:

Abstracted trace summary:
- Consecutive writes advance the write pointer to the wrap boundary, and then one more write attempts to cross that boundary.
- Good behavior wraps the pointer immediately on the next state update after the boundary write. Buggy behavior delays that wrap by one cycle, temporarily exposing an out-of-range or otherwise inconsistent post-boundary state.
- The first divergence is the boundary-crossing write: good performs the wrap on time, bad preserves the pre-wrap progression for one cycle too long.

Raw candidates:

```text
c1 [literal-hardcoding] assert property (@(posedge clk) disable iff (!rst_n) (incr_wptr_i && (wptr_o == 2'd3)) |=> (wptr_o == 2'd0));
c2 [literal-hardcoding] assert property (@(posedge clk) disable iff (!rst_n) (incr_rptr_i && !incr_wptr_i && !full_o && !empty_o) |=> (depth_o <= 3'd4));
```

Temporal candidates:

```text
c1 [literal-hardcoding] assert property (@(posedge clk) disable iff (!rst_n) ((wptr_o == 2'd3) && incr_wptr_i && !clr_i) |=> (wptr_o == 2'd0));
c2 [no-heldout-trigger|vacuous|literal-hardcoding] assert property (@(posedge clk) disable iff (!rst_n) (incr_wptr_i && !clr_i && !incr_rptr_i) |=> (wptr_o == ($past(wptr_o) + 2'd1) % 3'd4));
```

Manual verdict: REVIEWED | primary=exact_cycle_important | secondary=concrete_value_important

Evidence: Detection requires the next-cycle 3-to-0 wrap relation; the alternate temporal progression trigger is vacuous.

## 4. raw_success_temporal_fail | GPT | case237_onehot_addr_legal_v5_from_case137_prim_onehot_addr_false_positive

Parent: `case137_prim_onehot_addr_false_positive`; overlap: `False`; bug class: `combination_same_cycle`; family: `decoded_index_consistency`

Spec: If exactly one bit of oh_i is high and addr_i points to that bit, err_o shall remain low in the same cycle.

Legacy temporal input:

Abstracted trace summary:
- The bug is triggered when en_i is active and oh_i is a legal one-hot value whose asserted bit is exactly the bit selected by addr_i.
- Good behavior keeps err_o low on that same cycle because the one-hot/address combination is valid, while buggy behavior falsely asserts err_o even though the selected one-hot bit matches addr_i.
- The first divergence is the first enabled legal one-hot match after reset release; later traces still agree that genuinely illegal cases should assert err_o.

Raw candidates:

```text
c1 [clean] assert property (@(posedge clk) disable iff (!rst_n) (en_i && $onehot(oh_i) && oh_i[addr_i]) |-> (!err_o));
c2 [too-strong-on-good|literal-hardcoding] assert property (@(posedge clk) disable iff (!rst_n) ((oh_i == 4'b0001 && addr_i == 2'b00) || (oh_i == 4'b0010 && addr_i == 2'b01) || (oh_i == 4'b0100 && addr_i == 2'b10) || (oh_i == 4'b1000 && addr_i == 2'b11)) |-> (!err_o));
```

Temporal candidates:

```text
c1 [no-heldout-trigger|vacuous|literal-hardcoding] assert property (@(posedge clk) disable iff (!rst_n) (en_i && (oh_i == 4'b0001) && (addr_i == 2'b00)) |-> (!err_o));
c2 [no-heldout-trigger|vacuous|literal-hardcoding] assert property (@(posedge clk) disable iff (!rst_n) (en_i && (oh_i == 4'b0100) && (addr_i == 2'b10)) |-> (!err_o));
```

Manual verdict: REVIEWED | primary=hardcoding | secondary=vacuity

Evidence: Temporal candidates pin two witnessed onehot/address literals and do not trigger on held-out positions; raw includes a relational onehot/index candidate.

## 5. raw_success_temporal_fail | GPT | case123_prim_edge_sync_output_lag

Parent: `case123_prim_edge_sync_output_lag`; overlap: `False`; bug class: `temporal_cross_cycle`; family: `pulse_persistence`

Spec: q_posedge_pulse_o shall assert only on the sampled 0->1 transition cycle and must return low on the following stable-high cycle.

Legacy temporal input:

Abstracted trace summary:
- The bug is triggered after reset when the synchronized input rises and then remains high on the next sampled cycle, i.e. after a single detected 0->1 transition followed by stable-high input.
- Good behavior makes q_posedge_pulse_o a one-cycle pulse: it is high only on the sampled rising-edge cycle and low on the following stable-high cycle. Buggy behavior lets q_posedge_pulse_o remain asserted beyond the transition instead of clearing immediately.
- The first divergence is the first cycle after a valid rising-edge pulse, when q_sync_o is still high without a new 0->1 transition; good has q_posedge_pulse_o deasserted, while bad still asserts it.

Raw candidates:

```text
c1 [no-heldout-trigger|vacuous] assert property (@(posedge clk) disable iff (!rst_n) ($rose(q_sync_o)) |-> (q_posedge_pulse_o && !q_negedge_pulse_o));
c2 [clean] assert property (@(posedge clk) disable iff (!rst_n) (q_sync_o && q_posedge_pulse_o) |=> (!q_posedge_pulse_o));
```

Temporal candidates:

```text
c1 [no-heldout-trigger|vacuous|too-strong-on-good] assert property (@(posedge clk) disable iff (!rst_n) ($rose(q_sync_o)) |-> (q_posedge_pulse_o && ##1 (q_sync_o && !$rose(q_sync_o) && !q_posedge_pulse_o)));
c2 [no-heldout-trigger|vacuous|too-strong-on-good] assert property (@(posedge clk) disable iff (!rst_n) ((q_posedge_pulse_o && q_sync_o) ##1 q_sync_o) |-> (!q_posedge_pulse_o));
```

Manual verdict: REVIEWED | primary=duration_lost | secondary=too_strong

Evidence: Raw checks pulse clearing on the following stable-high cycle; temporal sequences overconstrain the rise/persistence window and fail good held-out.

## 6. raw_success_temporal_fail | GPT | case245_regwe_enable_gap_v5_from_case126_prim_regwe_enable_gap

Parent: `case126_prim_regwe_enable_gap`; overlap: `False`; bug class: `combination_same_cycle`; family: `register_write_enable_consistency`

Spec: When en_i is low, any nonzero onehot write-enable vector shall trigger err_o in the same cycle.

Legacy temporal input:

Abstracted trace summary:
- The bug is triggered after reset when en_i is low while oh_i is a nonzero onehot write-enable vector in the same sampled cycle.
- Good behavior asserts err_o in that same cycle whenever a onehot write-enable appears with en_i deasserted, while buggy behavior leaves err_o low under that invalid disabled-write condition.
- The first divergence is the earliest post-reset disabled cycle carrying any valid onehot write request; prior cycles either are in reset or have no offending write-enable, so both traces match.

Raw candidates:

```text
c1 [too-strong-on-good|literal-hardcoding] assert property (@(posedge clk) disable iff (!rst_n) (!en_i && (oh_i != 4'b0000)) |-> (err_o));
c2 [literal-hardcoding] assert property (@(posedge clk) disable iff (!rst_n) ((oh_i != 4'b0000) && !en_i) |=> (err_o));
```

Temporal candidates:

```text
c1 [too-strong-on-good] assert property (@(posedge clk) disable iff (!rst_n) (!en_i && $onehot(oh_i)) |-> (err_o));
c2 [too-strong-on-good] assert property (@(posedge clk) disable iff (!rst_n) (!en_i && (|oh_i)) |-> (err_o));
```

Manual verdict: REVIEWED | primary=too_strong | secondary=polarity_lost

Evidence: Temporal broadens the disabled request condition and rejects legal good behavior; the successful raw candidate preserves the observed implication direction.

## 7. raw_success_temporal_fail | GPT | case110_prim_intr_event_overwrite

Parent: `case110_prim_intr_event_overwrite`; overlap: `False`; bug class: `temporal_cross_cycle`; family: `event_state_accumulation`

Spec: For Event interrupts, once a new event sets the interrupt state, the state shall remain set across subsequent cycles until software clears it.

Legacy temporal input:

Abstracted trace summary:
- The bug is triggered when an event interrupt request sets reg2hw_intr_state_q_i while interrupts are enabled, with no software clear occurring afterward.
- Good behavior keeps the event interrupt pending and causes intr_o to assert only after the latched interrupt state is observed as set; buggy behavior instead produces a transient/overwritten intr_o response that asserts too early and then drops even though reg2hw_intr_state_q_i remains set.
- The first divergence occurs immediately after the event has been latched into interrupt state: both traces show the state set, but bad raises intr_o in that first post-latch cycle while good does not, and the next cycle the polarity reverses while the pending state is still unchanged.

Raw candidates:

```text
c1 [clean] assert property (@(posedge clk) disable iff (!rst_n) ((reg2hw_intr_state_q_i && !event_intr_i && !reg2hw_intr_test_qe_i)) |-> (hw2reg_intr_state_d_o));
c2 [clean] assert property (@(posedge clk) disable iff (!rst_n) ((reg2hw_intr_state_q_i && reg2hw_intr_enable_q_i)) |=> (intr_o));
```

Temporal candidates:

```text
c1 [too-strong-on-good] assert property (@(posedge clk) disable iff (!rst_n) (reg2hw_intr_state_q_i && reg2hw_intr_enable_q_i) |-> (intr_o));
c2 [no-heldout-trigger|vacuous] assert property (@(posedge clk) disable iff (!rst_n) ($past(reg2hw_intr_state_q_i && reg2hw_intr_enable_q_i) && reg2hw_intr_state_q_i && reg2hw_intr_enable_q_i) |-> (intr_o));
```

Manual verdict: REVIEWED | primary=exact_cycle_important | secondary=too_strong

Evidence: Raw uses a next-cycle implication from committed state; temporal uses same-cycle or repeated-state antecedents and becomes too strong/vacuous.

## 8. raw_success_temporal_fail | GPT | case255_fifo_v8_from_case104_prim_fifo_full_early

Parent: `case104_prim_fifo_full_early`; overlap: `True`; bug class: `combination_same_cycle`; family: `fifo_boundary_flag`

Spec: full_o shall assert if and only if the FIFO currently contains Depth entries; it must remain low at Depth-1.

Legacy temporal input:

Abstracted trace summary:
- The bug is triggered when repeated write-side increments with no concurrent read advance the FIFO from a non-full occupancy to the last remaining slot before full.
- Good behavior keeps full_o deasserted while depth_o indicates one entry short of capacity, then asserts full_o only once the FIFO actually reaches capacity; buggy behavior reports the full condition one write early and then drops full_o after depth_o reaches the full count.
- The first divergence is the write that should leave the FIFO at the pre-full boundary: good still shows not-full with depth_o below capacity, while bad already jumps to a full indication and an over-advanced depth report.

Raw candidates:

```text
c1 [no-heldout-trigger|vacuous|literal-hardcoding] assert property (@(posedge clk) disable iff (!rst_n) (depth_o == 3'b011) |-> (!full_o));
c2 [literal-hardcoding] assert property (@(posedge clk) disable iff (!rst_n) (depth_o == 3'b100) |-> (full_o));
```

Temporal candidates:

```text
c1 [no-heldout-trigger|vacuous|literal-hardcoding] assert property (@(posedge clk) disable iff (!rst_n) (depth_o == 3'd3) |-> (!full_o));
c2 [no-heldout-trigger|vacuous|literal-hardcoding] assert property (@(posedge clk) disable iff (!rst_n) ((depth_o == 3'd3) && incr_wptr_i && !incr_rptr_i && !clr_i) |-> (!full_o));
```

Manual verdict: REVIEWED | primary=concrete_value_important | secondary=vacuity

Evidence: The usable raw assertion retains the true full count; temporal checks the unobserved pre-full count and never triggers held-out.

## 9. raw_success_temporal_fail | GPT | case104_prim_fifo_full_early

Parent: `case104_prim_fifo_full_early`; overlap: `True`; bug class: `combination_same_cycle`; family: `fifo_boundary_flag`

Spec: full_o shall assert if and only if the FIFO currently contains Depth entries; it must remain low at Depth-1.

Legacy temporal input:

Abstracted trace summary:
- Repeated writes fill the FIFO toward the full boundary without intervening reads.
- The bug is triggered on the last pre-full write: good behavior keeps full_o low while the FIFO still has exactly one slot remaining, but bad behavior asserts full_o one cycle too early and also reports maximum depth too soon.
- The first divergence is the first boundary approach cycle where good is still "not full" and bad already claims "full".

Raw candidates:

```text
c1 [no-heldout-trigger|vacuous|too-strong-on-good|literal-hardcoding] assert property (@(posedge clk) disable iff (!rst_n) (!clr_i && (depth_o == 3'b011) && incr_wptr_i && !incr_rptr_i) |=> (!full_o));
c2 [literal-hardcoding] assert property (@(posedge clk) disable iff (!rst_n) ((depth_o == 3'b100)) |-> (full_o));
```

Temporal candidates:

```text
c1 [no-heldout-trigger|vacuous|literal-hardcoding] assert property (@(posedge clk) disable iff (!rst_n) (depth_o == 3'd3) |-> (!full_o));
c2 [no-heldout-trigger|vacuous|literal-hardcoding] assert property (@(posedge clk) disable iff (!rst_n) (!clr_i && !incr_rptr_i && incr_wptr_i && (depth_o == 3'd3)) |-> (!full_o));
```

Manual verdict: REVIEWED | primary=concrete_value_important | secondary=vacuity

Evidence: Raw succeeds on full depth=4 while temporal pins depth=3 antecedents that are absent from held-out.

## 10. raw_success_temporal_fail | GPT | case252_fifo_v5_from_case104_prim_fifo_full_early

Parent: `case104_prim_fifo_full_early`; overlap: `True`; bug class: `combination_same_cycle`; family: `fifo_boundary_flag`

Spec: full_o shall assert if and only if the FIFO currently contains Depth entries; it must remain low at Depth-1.

Legacy temporal input:

Abstracted trace summary:
- The bug is triggered by successive write increments with no read increments after reset, bringing the FIFO from not-full up to the full boundary.
- Good behavior keeps full_o low while depth_o indicates one remaining slot and asserts full_o only once depth_o reaches the true full count; buggy behavior asserts full_o on the boundary-approach write and then deasserts it after the FIFO is actually full.
- The first divergence occurs on the write that should move occupancy from below-full to just one entry short of full: good still reports not full with intermediate depth_o, while bad jumps to a full indication and full depth_o too early.

Raw candidates:

```text
c1 [no-heldout-trigger|vacuous|literal-hardcoding] assert property (@(posedge clk) disable iff (!rst_n) (depth_o == 3'd3) |-> (!full_o));
c2 [literal-hardcoding] assert property (@(posedge clk) disable iff (!rst_n) (depth_o == 3'd4) |-> (full_o));
```

Temporal candidates:

```text
c1 [no-heldout-trigger|vacuous|literal-hardcoding] assert property (@(posedge clk) disable iff (!rst_n) (depth_o == 3'd3) |-> (!full_o));
c2 [literal-hardcoding] assert property (@(posedge clk) disable iff (!rst_n) (!clr_i && incr_wptr_i && !incr_rptr_i && depth_o == 3'd2) |-> (!full_o));
```

Manual verdict: REVIEWED | primary=concrete_value_important | secondary=vacuity

Evidence: The exact full occupancy constant distinguishes the bug; temporal's depth=3/depth=2 triggers miss held-out.

## 11. temporal_success_raw_fail | GPT | case111_prim_intr_output_or_mask

Parent: `case111_prim_intr_output_or_mask`; overlap: `False`; bug class: `combination_same_cycle`; family: `interrupt_masking`

Spec: The outgoing interrupt shall assert only when both the interrupt status and enable are high.

Legacy temporal input:

Abstracted trace summary:
- The bug is exposed whenever event_intr_i is asserted or the interrupt state changes while the intended output condition should still be governed by the conjunction of reg2hw_intr_state_q_i and reg2hw_intr_enable_q_i.
- Good behavior drives intr_o high only when both reg2hw_intr_state_q_i and reg2hw_intr_enable_q_i are high, and drives it low if either input is low. Buggy behavior lets intr_o assert when only one of those conditions is true, effectively behaving like an OR-masked interrupt output.
- The first divergence occurs immediately after reset release on a cycle where reg2hw_intr_enable_q_i is high but reg2hw_intr_state_q_i is still low: good keeps intr_o low, while bad raises intr_o early; later bad also stays high when enable drops or state clears but the other term remains high.

Raw candidates:

```text
c1 [too-strong-on-good] assert property (@(posedge clk) disable iff (!rst_n) (intr_o) |-> (reg2hw_intr_enable_q_i && reg2hw_intr_state_q_i));
c2 [too-strong-on-good] assert property (@(posedge clk) disable iff (!rst_n) ((!reg2hw_intr_enable_q_i || !reg2hw_intr_state_q_i)) |-> (!intr_o));
```

Temporal candidates:

```text
c1 [clean] assert property (@(posedge clk) disable iff (!rst_n) (reg2hw_intr_enable_q_i && !reg2hw_intr_state_q_i) |-> (!intr_o));
c2 [too-strong-on-good] assert property (@(posedge clk) disable iff (!rst_n) ((!reg2hw_intr_enable_q_i || !reg2hw_intr_state_q_i)) |-> (!intr_o));
```

Manual verdict: REVIEWED | primary=too_strong | secondary=raw_noise

Evidence: Raw candidates encode the complete biconditional and reject good behavior; temporal isolates one observed enable-high/state-low branch.

## 12. temporal_success_raw_fail | GPT | case231_onehot_addr_bad_v7_from_case103_prim_onehot_addr_mismatch_suppressed

Parent: `case103_prim_onehot_addr_mismatch_suppressed`; overlap: `False`; bug class: `combination_same_cycle`; family: `decoded_index_consistency`

Spec: If exactly one bit of oh_i is high, err_o shall assert when addr_i points to a different bit in the same cycle.

Legacy temporal input:

Abstracted trace summary:
- The bug is triggered when en_i is high, oh_i is exactly onehot, and addr_i selects a different bit position than the asserted bit of oh_i in the same cycle.
- Good behavior asserts err_o on each enabled onehot/address mismatch cycle and deasserts it again when addr_i matches the onehot bit; buggy behavior leaves err_o low even during the mismatch condition.
- The first divergence occurs at the first transition from a matching onehot/address pair to a mismatching pair while the same onehot request remains active; good raises err_o there, bad does not.

Raw candidates:

```text
c1 [no-heldout-trigger|vacuous|literal-hardcoding] assert property (@(posedge clk) disable iff (!rst_n) (en_i && oh_i == 4'b0001 && addr_i != 2'b00) |-> (err_o));
c2 [no-heldout-trigger|vacuous|literal-hardcoding] assert property (@(posedge clk) disable iff (!rst_n) (en_i && oh_i == 4'b0010 && addr_i != 2'b01) |-> (err_o));
```

Temporal candidates:

```text
c1 [clean] assert property (@(posedge clk) disable iff (!rst_n) (en_i && $onehot(oh_i) && !oh_i[addr_i]) |-> (err_o));
c2 [no-heldout-trigger|vacuous] assert property (@(posedge clk) disable iff (!rst_n) (en_i && $onehot(oh_i) && $past(en_i && $onehot(oh_i) && oh_i == $past(oh_i) && oh_i[$past(addr_i)] && !oh_i[addr_i])) |-> (err_o));
```

Manual verdict: REVIEWED | primary=hardcoding | secondary=vacuity

Evidence: Raw enumerates witnessed onehot literals and misses held-out; temporal uses the relational !oh_i[addr_i] trigger.

## 13. temporal_success_raw_fail | GPT | case115_prim_edge_both_edges_collapsed

Parent: `case115_prim_edge_both_edges_collapsed`; overlap: `False`; bug class: `temporal_cross_cycle`; family: `edge_direction`

Spec: q_posedge_pulse_o shall remain low on falling edges and assert only on rising edges.

Legacy temporal input:

Abstracted trace summary:
- The bug is triggered when the sampled input/synchronized value makes a falling transition after reset, i.e. a negedge event is detected rather than a posedge event.
- Good behavior keeps q_posedge_pulse_o low on that falling-edge detection and only q_negedge_pulse_o pulses; buggy behavior incorrectly also asserts q_posedge_pulse_o on the same falling-edge event.
- The first divergence is the first high-to-low transition of q_sync_o/d_i after an earlier low-to-high transition has behaved correctly; both traces agree on the rising-edge pulse, then differ when the opposite edge occurs.

Raw candidates:

```text
c1 [no-heldout-trigger|vacuous] assert property (@(posedge clk) disable iff (!rst_n) ($fell(q_sync_o)) |-> (!q_posedge_pulse_o));
c2 [no-heldout-trigger|vacuous] assert property (@(posedge clk) disable iff (!rst_n) (q_posedge_pulse_o) |-> ($rose(q_sync_o)));
```

Temporal candidates:

```text
c1 [no-heldout-trigger|vacuous] assert property (@(posedge clk) disable iff (!rst_n) ($past(q_sync_o) && !q_sync_o) |-> (!q_posedge_pulse_o));
c2 [clean] assert property (@(posedge clk) disable iff (!rst_n) (q_negedge_pulse_o) |-> (!q_posedge_pulse_o));
```

Manual verdict: REVIEWED | primary=trigger_lost | secondary=raw_noise

Evidence: Raw $fell-based triggers do not occur in held-out sampling; temporal anchors the check on the observed negedge pulse.

## 14. temporal_success_raw_fail | GPT | case137_prim_onehot_addr_false_positive

Parent: `case137_prim_onehot_addr_false_positive`; overlap: `False`; bug class: `combination_same_cycle`; family: `decoded_index_consistency`

Spec: If exactly one bit of oh_i is high and addr_i points to that bit, err_o shall remain low in the same cycle.

Legacy temporal input:

Abstracted trace summary:
- The bug is triggered when en_i is active, oh_i is exactly one-hot, and addr_i selects the asserted bit of oh_i in that same cycle.
- Good behavior keeps err_o low for this valid one-hot-address match, while buggy behavior falsely asserts err_o under the same legal condition.
- The first divergence is the first enabled legal one-hot match after reset release; later both traces still agree that mismatched one-hot selections or multi-hot patterns should assert err_o.

Raw candidates:

```text
c1 [no-heldout-trigger|vacuous|literal-hardcoding] assert property (@(posedge clk) disable iff (!rst_n) (en_i && oh_i == 4'b0001 && addr_i == 2'b00) |-> (!err_o));
c2 [no-heldout-trigger|vacuous|literal-hardcoding] assert property (@(posedge clk) disable iff (!rst_n) (en_i && oh_i == 4'b0100 && addr_i == 2'b10) |-> (!err_o));
```

Temporal candidates:

```text
c1 [no-heldout-trigger|vacuous|literal-hardcoding] assert property (@(posedge clk) disable iff (!rst_n) (en_i && (oh_i == 4'b0001) && (addr_i == 2'b00)) |-> (!err_o));
c2 [literal-hardcoding] assert property (@(posedge clk) disable iff (!rst_n) (en_i && ((addr_i == 2'b01 && oh_i == 4'b0010) || (addr_i == 2'b10 && oh_i == 4'b0100) || (addr_i == 2'b11 && oh_i == 4'b1000))) |-> (!err_o));
```

Manual verdict: REVIEWED | primary=hardcoding | secondary=vacuity

Evidence: Raw pins two specific legal positions; temporal covers additional onehot/address positions and obtains one non-vacuous success.

## 15. temporal_success_raw_fail | Claude | case110_prim_intr_event_overwrite

Parent: `case110_prim_intr_event_overwrite`; overlap: `False`; bug class: `temporal_cross_cycle`; family: `event_state_accumulation`

Spec: For Event interrupts, once a new event sets the interrupt state, the state shall remain set across subsequent cycles until software clears it.

Legacy temporal input:

Abstracted trace summary:
- The bug is triggered when an event interrupt request sets reg2hw_intr_state_q_i while interrupts are enabled, with no software clear occurring afterward.
- Good behavior keeps the event interrupt pending and causes intr_o to assert only after the latched interrupt state is observed as set; buggy behavior instead produces a transient/overwritten intr_o response that asserts too early and then drops even though reg2hw_intr_state_q_i remains set.
- The first divergence occurs immediately after the event has been latched into interrupt state: both traces show the state set, but bad raises intr_o in that first post-latch cycle while good does not, and the next cycle the polarity reverses while the pending state is still unchanged.

Raw candidates:

```text
c1 [too-strong-on-good] assert property (@(posedge clk) disable iff (!rst_n) (reg2hw_intr_state_q_i && reg2hw_intr_enable_q_i && !hw2reg_intr_state_de_o) |-> intr_o);
c2 [too-strong-on-good] assert property (@(posedge clk) disable iff (!rst_n) ((event_intr_i || (reg2hw_intr_test_qe_i && reg2hw_intr_test_q_i)) || reg2hw_intr_state_q_i) |-> hw2reg_intr_state_d_o);
```

Temporal candidates:

```text
c1 [too-strong-on-good] assert property (@(posedge clk) disable iff (!rst_n) (event_intr_i || (reg2hw_intr_test_qe_i && reg2hw_intr_test_q_i)) |-> (hw2reg_intr_state_de_o && hw2reg_intr_state_d_o));
c2 [clean] assert property (@(posedge clk) disable iff (!rst_n) (reg2hw_intr_state_q_i && reg2hw_intr_enable_q_i) |=> (intr_o));
```

Manual verdict: REVIEWED | primary=cross_cycle_relation_important | secondary=too_strong

Evidence: Temporal produces the successful committed-state |=> intr_o relation; raw same-cycle state/update assertions reject good behavior.

## 16. temporal_success_raw_fail | GPT | case134_prim_intr_event_not_sticky

Parent: `case134_prim_intr_event_not_sticky`; overlap: `False`; bug class: `temporal_cross_cycle`; family: `event_latching`

Spec: In Event mode, a captured event shall remain latched in the interrupt state until software clears it.

Legacy temporal input:

Abstracted trace summary:
- The bug is triggered after an event has been captured in Event mode, so reg2hw_intr_state_q_i becomes set and the interrupt remains enabled without a software clear.
- Good behavior keeps the interrupt indication aligned with the latched state while it remains uncleared and enabled; buggy behavior produces only a transient pulse and then drops intr_o even though the captured interrupt state is still set.
- The first divergence occurs on the first cycle after reg2hw_intr_state_q_i is observed set from a prior event: the bad trace asserts intr_o immediately, while the good trace delays it and then sustains it until disable or clear instead of letting it disappear spontaneously.

Raw candidates:

```text
c1 [too-strong-on-good] assert property (@(posedge clk) disable iff (!rst_n) (reg2hw_intr_state_q_i && reg2hw_intr_enable_q_i) |-> (intr_o));
c2 [too-strong-on-good] assert property (@(posedge clk) disable iff (!rst_n) (event_intr_i && reg2hw_intr_enable_q_i) |-> (intr_o || reg2hw_intr_state_q_i));
```

Temporal candidates:

```text
c1 [too-strong-on-good] assert property (@(posedge clk) disable iff (!rst_n) (reg2hw_intr_state_q_i && reg2hw_intr_enable_q_i) |-> (intr_o));
c2 [clean] assert property (@(posedge clk) disable iff (!rst_n) (intr_o && reg2hw_intr_enable_q_i && reg2hw_intr_state_q_i) |=> (intr_o || !reg2hw_intr_enable_q_i || !reg2hw_intr_state_q_i));
```

Manual verdict: REVIEWED | primary=duration_lost | secondary=cross_cycle_relation_important

Evidence: Temporal captures persistence into the following cycle; raw only checks immediate state/event conditions and is too strong.

## 17. temporal_success_raw_fail | Claude | case138_prim_regwe_zero_enabled_false_positive

Parent: `case138_prim_regwe_zero_enabled_false_positive`; overlap: `False`; bug class: `combination_same_cycle`; family: `masked_write_enable_legality`

Spec: For prim_reg_we_check, en_i high with oh_i equal to zero shall remain legal and must not raise err_o in the same cycle.

Legacy temporal input:

Abstracted trace summary:
- The bug is triggered when en_i is asserted while oh_i is the all-zero vector in a sampled cycle after reset is released.
- Good behavior treats this zero-oh_i enabled case as legal and keeps err_o low in the same cycle, while buggy behavior falsely asserts err_o on that enabled zero input.
- The first divergence occurs at the first enabled cycle with no selected bit in oh_i; surrounding enabled one-hot cycles agree and keep err_o deasserted.

Raw candidates:

```text
c1 [no-heldout-trigger|vacuous] assert property (@(posedge clk) disable iff (!rst_n) (en_i && (oh_i == '0)) |-> (!err_o));
c2 [no-heldout-trigger|vacuous] assert property (@(posedge clk) disable iff (!rst_n) (en_i && !(|oh_i)) |-> (err_o == 1'b0));
```

Temporal candidates:

```text
c1 [no-heldout-trigger|vacuous] assert property (@(posedge clk) disable iff (!rst_n) (en_i && (oh_i == '0)) |-> (!err_o));
c2 [clean] assert property (@(posedge clk) disable iff (!rst_n) (en_i && $onehot0(oh_i)) |-> (!err_o));
```

Manual verdict: REVIEWED | primary=hardcoding | secondary=vacuity

Evidence: Raw zero-vector literals do not trigger held-out; temporal generalizes the legal condition with $onehot0.

## 18. temporal_success_raw_fail | GPT | case254_fifo_v7_from_case104_prim_fifo_full_early

Parent: `case104_prim_fifo_full_early`; overlap: `False`; bug class: `combination_same_cycle`; family: `fifo_boundary_flag`

Spec: full_o shall assert if and only if the FIFO currently contains Depth entries; it must remain low at Depth-1.

Legacy temporal input:

Abstracted trace summary:
- The bug is triggered by consecutive write-side increments after reset, with no read-side increments or clear, as the FIFO advances toward the full boundary.
- Good behavior keeps full_o deasserted while the FIFO still has one remaining slot and only reports the full depth once that boundary is actually reached; buggy behavior asserts full_o early and advances depth_o to the full count on that last pre-full write.
- The first divergence is the write that should leave the FIFO at Depth-1: good shows a still-not-full state, while bad already reports a full state and corresponding full depth.

Raw candidates:

```text
c1 [no-heldout-trigger|vacuous|literal-hardcoding] assert property (@(posedge clk) disable iff (!rst_n) ((depth_o == 3'b011)) |-> (!full_o));
c2 [literal-hardcoding] assert property (@(posedge clk) disable iff (!rst_n) ((full_o)) |-> (depth_o == 3'b100));
```

Temporal candidates:

```text
c1 [no-heldout-trigger|vacuous|literal-hardcoding] assert property (@(posedge clk) disable iff (!rst_n) (!clr_i && !incr_rptr_i && (depth_o == 3'd3)) |-> (!full_o));
c2 [literal-hardcoding] assert property (@(posedge clk) disable iff (!rst_n) (!clr_i && !incr_rptr_i && incr_wptr_i && (depth_o == 3'd2)) |=> ((depth_o == 3'd3) && !full_o));
```

Manual verdict: REVIEWED | primary=cross_cycle_relation_important | secondary=vacuity

Evidence: Temporal includes the depth=2 to depth=3 next-cycle transition; raw boundary antecedents are vacuous.

## 19. temporal_success_raw_fail | GPT | case114_prim_edge_negedge_misdecoded

Parent: `case114_prim_edge_negedge_misdecoded`; overlap: `False`; bug class: `temporal_cross_cycle`; family: `edge_direction`

Spec: q_negedge_pulse_o shall pulse for exactly the sampled 1->0 transition and not for 0->1 transitions.

Legacy temporal input:

Abstracted trace summary:
- The bug is triggered after reset when the sampled signal transitions upward (an effective 0->1 change on the synchronized input/output state) rather than downward.
- Good behavior keeps q_negedge_pulse_o low on a rising transition and pulses it only on the later falling transition; buggy behavior incorrectly asserts q_negedge_pulse_o on the rising transition and then misses the real negedge pulse.
- The first divergence is the first upward transition event: q_sync_o updates high and q_posedge_pulse_o indicates a posedge, while only the bad trace also raises q_negedge_pulse_o.

Raw candidates:

```text
c1 [no-heldout-trigger|vacuous] assert property (@(posedge clk) disable iff (!rst_n) ($past(q_sync_o) && !q_sync_o) |-> (q_negedge_pulse_o));
c2 [no-heldout-trigger|vacuous] assert property (@(posedge clk) disable iff (!rst_n) (!$past(q_sync_o) && q_sync_o) |-> (!q_negedge_pulse_o));
```

Temporal candidates:

```text
c1 [no-heldout-trigger|vacuous] assert property (@(posedge clk) disable iff (!rst_n) ($rose(q_sync_o)) |-> (!q_negedge_pulse_o));
c2 [clean] assert property (@(posedge clk) disable iff (!rst_n) (q_posedge_pulse_o) |-> (!q_negedge_pulse_o));
```

Manual verdict: REVIEWED | primary=polarity_lost | secondary=trigger_lost

Evidence: Raw reconstructed edge triggers miss held-out; temporal relates posedge and negedge pulse polarity directly.

## 20. temporal_success_raw_fail | GPT | case122_prim_filter_ctr_streak_reset_ignored

Parent: `case122_prim_filter_ctr_streak_reset_ignored`; overlap: `False`; bug class: `temporal_cross_cycle`; family: `filter_counter_reset`

Spec: When the candidate polarity flips, the counter-based filter shall discard stale progress from the previous polarity; two samples of the new value are still not enough to switch the output at threshold two.

Legacy temporal input:

Abstracted trace summary:
- The bug is triggered when enable_i is active, the filter has accumulated progress toward one candidate value, and then filter_i flips to the opposite polarity before the threshold is reached; stale count from the old polarity must be discarded.
- Good behavior resets the streak on that polarity change, so two enabled samples of the new filter_i value are still insufficient to make filter_o switch. Buggy behavior carries over prior progress across the flip and lets filter_o switch too early on the new polarity.
- The first divergence occurs at the first attempt to complete the new-polarity streak after a recent opposite-polarity sample: good still holds filter_o at its old value, while bad already updates filter_o as if the earlier opposite-polarity progress still counted.

Raw candidates:

```text
c1 [too-strong-on-good] assert property (@(posedge clk) disable iff (!rst_n) (second_new_sample_dbg) |-> (!filter_o));
c2 [too-strong-on-good|literal-hardcoding] assert property (@(posedge clk) disable iff (!rst_n) (enable_i && (thresh_i == 2'd2) && second_new_sample_dbg && (filter_i != filter_o)) |=> (!filter_o));
```

Temporal candidates:

```text
c1 [clean] assert property (@(posedge clk) disable iff (!rst_n) (second_new_sample_dbg) |-> (filter_o != filter_i));
c2 [no-heldout-trigger|vacuous|literal-hardcoding] assert property (@(posedge clk) disable iff (!rst_n) (enable_i && (thresh_i == 2'd2) && $rose(filter_i) && $past(enable_i && (thresh_i == 2'd2) && (filter_i != filter_o),1) && $past(enable_i && (thresh_i == 2'd2) && (filter_i == filter_o),2)) |-> (filter_o == $past(filter_o)));
```

Manual verdict: REVIEWED | primary=cross_cycle_relation_important | secondary=too_strong

Evidence: Temporal relates the second candidate sample to retained output; raw consequent polarity is fixed and rejects good behavior.

## 21. both_success | Claude | case120_prim_filter_ctr_bypass_stale

Parent: `case120_prim_filter_ctr_bypass_stale`; overlap: `False`; bug class: `temporal_cross_cycle`; family: `filter_bypass_control`

Spec: When enable_i is low, filter_o shall bypass to the current input rather than stay at the previously stored filtered value.

Legacy temporal input:

Abstracted trace summary:
- The bug is triggered after reset once filtering has previously driven filter_o to a stored value, and then enable_i is deasserted while filter_i changes.
- Good behavior makes filter_o bypass directly to the current filter_i whenever enable_i is low. Buggy behavior instead holds the previously filtered/stored filter_o value during the disabled interval.
- The first divergence is the first disable phase immediately following an active filtering period: good output follows the new input at once, while bad output remains stale from the prior enabled result.

Raw candidates:

```text
c1 [clean] assert property (@(posedge clk) disable iff (!rst_n) (!enable_i) |-> (filter_o == filter_i));
c2 [clean] assert property (@(posedge clk) disable iff (!rst_n) (!enable_i && filter_i == 1'b0) |-> (filter_o == 1'b0));
```

Temporal candidates:

```text
c1 [clean] assert property (@(posedge clk) disable iff (!rst_n) (!enable_i) |-> (filter_o == filter_i));
c2 [clean] assert property (@(posedge clk) disable iff (!rst_n) (!enable_i && (filter_i != filter_o)) |=> (filter_o == filter_i));
```

Manual verdict: REVIEWED | primary=polarity_lost | secondary=cross_cycle_relation_important

Evidence: Both preserve the disabled-bypass equality across either input polarity; temporal also supplies a next-cycle variant.

## 22. both_success | GPT | case280_fifo_v6_from_case130_prim_fifo_empty_early

Parent: `case130_prim_fifo_empty_early`; overlap: `False`; bug class: `combination_same_cycle`; family: `fifo_boundary_flag`

Spec: empty_o shall remain low while the FIFO still contains exactly one entry.

Legacy temporal input:

Abstracted trace summary:
- The bug is triggered whenever normal operation leaves the FIFO with exactly one stored entry after reset is released, whether by a write into an empty FIFO or by a read from a deeper occupancy down to one remaining entry.
- Good behavior keeps empty_o deasserted while that last entry is still present; buggy behavior asserts empty_o as soon as occupancy becomes one and continues to treat the FIFO as empty too early.
- The first divergence is the first transition into the one-entry state: both traces agree on reset-empty behavior and on non-empty behavior at higher occupancy, then bad raises empty_o at the one-entry boundary while good does not.

Raw candidates:

```text
c1 [literal-hardcoding] assert property (@(posedge clk) disable iff (!rst_n) ((depth_o == 3'b001)) |-> (!empty_o));
c2 [literal-hardcoding] assert property (@(posedge clk) disable iff (!rst_n) ((!clr_i && !incr_wptr_i && !incr_rptr_i && (depth_o == 3'b001))) |-> (!empty_o));
```

Temporal candidates:

```text
c1 [literal-hardcoding] assert property (@(posedge clk) disable iff (!rst_n) (depth_o == 3'd1) |-> (!empty_o));
c2 [literal-hardcoding] assert property (@(posedge clk) disable iff (!rst_n) (!clr_i && ((empty_o && incr_wptr_i && !incr_rptr_i) || (depth_o == 3'd2 && incr_rptr_i && !incr_wptr_i))) |=> (!empty_o));
```

Manual verdict: REVIEWED | primary=concrete_value_important | secondary=exact_cycle_important

Evidence: Both retain the one-entry boundary; temporal additionally expresses the transition into that boundary.

## 23. both_success | Claude | case216_onehot_zerohot_v8_from_case102_prim_onehot_enable_mismatch_suppressed

Parent: `case102_prim_onehot_enable_mismatch_suppressed`; overlap: `False`; bug class: `combination_same_cycle`; family: `enable_consistency`

Spec: With strict enable checking enabled, err_o shall assert whenever en_i disagrees with whether any onehot bit is set.

Legacy temporal input:

Abstracted trace summary:
- The bug is triggered after reset when strict enable checking is active and en_i indicates an enabled request while oh_i has no bit set, creating an enable-versus-onehot-presence mismatch.
- Good behavior asserts err_o on mismatch cycles where en_i disagrees with whether any oh_i bit is high; buggy behavior leaves err_o deasserted for the zero-hot while en_i-high case.
- The first divergence is the first post-reset cycle in which a previously valid enabled onehot condition changes into an enabled zero-hot condition; signals match before that because en_i and onehot presence agree.

Raw candidates:

```text
c1 [clean] assert property (@(posedge clk) disable iff (!rst_n) ((|oh_i) != en_i) |-> (err_o));
c2 [no-heldout-trigger|vacuous] assert property (@(posedge clk) disable iff (!rst_n) (!en_i && (|oh_i)) |-> (err_o));
```

Temporal candidates:

```text
c1 [clean] assert property (@(posedge clk) disable iff (!rst_n) ((|oh_i) != en_i) |-> (err_o));
c2 [literal-hardcoding] assert property (@(posedge clk) disable iff (!rst_n) (en_i && (oh_i == 4'b0)) |-> (err_o));
```

Manual verdict: REVIEWED | primary=trigger_lost | secondary=polarity_lost

Evidence: Both successful candidates preserve the relational mismatch trigger and positive err_o polarity.

## 24. both_success | Claude | case220_onehot_zerohot_v4_from_case129_prim_onehot_zero_enabled_suppressed

Parent: `case129_prim_onehot_zero_enabled_suppressed`; overlap: `False`; bug class: `combination_same_cycle`; family: `enable_consistency`

Spec: With strict checking enabled, en_i high with oh_i equal to zero shall assert err_o in the same sampled cycle.

Legacy temporal input:

Abstracted trace summary:
- The bug is triggered after reset when strict checking is active via en_i and the one-hot input oh_i is all-zero in a sampled cycle.
- Good behavior asserts err_o in the same cycle whenever en_i is high and oh_i has no bits set; buggy behavior incorrectly leaves err_o deasserted under that enabled zero-hot condition.
- The first divergence is the first enabled zero-hot occurrence following an earlier enabled legal one-hot case where both traces still agree that err_o should remain low.

Raw candidates:

```text
c1 [literal-hardcoding] assert property (@(posedge clk) disable iff (!rst_n) (en_i && (oh_i == 4'b0000)) |-> (err_o));
c2 [clean] assert property (@(posedge clk) disable iff (!rst_n) ((|oh_i) != en_i) |-> (err_o));
```

Temporal candidates:

```text
c1 [literal-hardcoding] assert property (@(posedge clk) disable iff (!rst_n) (en_i && (oh_i == 4'b0)) |-> (err_o));
c2 [clean] assert property (@(posedge clk) disable iff (!rst_n) ((|oh_i) != en_i) |-> (err_o));
```

Manual verdict: REVIEWED | primary=concrete_value_important | secondary=hardcoding

Evidence: Both retain the zero-hot boundary, while their alternate relational candidate avoids dependence on a single trace position.

## 25. both_success | GPT | case203_onehot_multihot_v3_from_case101_prim_onehot_multihot_suppressed

Parent: `case101_prim_onehot_multihot_suppressed`; overlap: `False`; bug class: `combination_same_cycle`; family: `onehot_violation_masked`

Spec: When more than one bit of oh_i is high in the same cycle, err_o must assert in that same cycle.

Legacy temporal input:

Abstracted trace summary:
- The bug is triggered when, after reset is released, more than one bit of oh_i is high in the same sampled cycle.
- Good behavior asserts err_o in that same multihot cycle (and while the multihot condition persists), whereas buggy behavior leaves err_o deasserted despite the illegal oh_i pattern.
- The first divergence is the first post-reset cycle where oh_i changes from a legal onehot value to a multihot value; before that, both traces agree with err_o low.

Raw candidates:

```text
c1 [literal-hardcoding] assert property (@(posedge clk) disable iff (!rst_n) ((oh_i[3] && oh_i[2]) || (oh_i[3] && oh_i[1]) || (oh_i[3] && oh_i[0]) || (oh_i[2] && oh_i[1]) || (oh_i[2] && oh_i[0]) || (oh_i[1] && oh_i[0])) |-> (err_o));
c2 [literal-hardcoding] assert property (@(posedge clk) disable iff (!rst_n) ((en_i && !((oh_i == 4'b0000) || (oh_i == 4'b0001) || (oh_i == 4'b0010) || (oh_i == 4'b0100) || (oh_i == 4'b1000)))) |-> (err_o));
```

Temporal candidates:

```text
c1 [literal-hardcoding] assert property (@(posedge clk) disable iff (!rst_n) ((en_i && ((oh_i[0] && oh_i[1]) || (oh_i[0] && oh_i[2]) || (oh_i[0] && oh_i[3]) || (oh_i[1] && oh_i[2]) || (oh_i[1] && oh_i[3]) || (oh_i[2] && oh_i[3])))) |-> (err_o));
c2 [no-heldout-trigger|vacuous|too-strong-on-good|literal-hardcoding] assert property (@(posedge clk) disable iff (!rst_n) ((((oh_i[0] && oh_i[1]) || (oh_i[0] && oh_i[2]) || (oh_i[0] && oh_i[3]) || (oh_i[1] && oh_i[2]) || (oh_i[1] && oh_i[3]) || (oh_i[2] && oh_i[3])) && (addr_i == 2'd0 || addr_i == 2'd1 || addr_i == 2'd2 || addr_i == 2'd3)) |-> (err_o));
```

Manual verdict: REVIEWED | primary=concrete_value_important | secondary=hardcoding

Evidence: Both encode the multi-hot cardinality relation, though literal bit-pair expansion remains a hardcoding risk.

## 26. both_success | GPT | case250_fifo_v3_from_case104_prim_fifo_full_early

Parent: `case104_prim_fifo_full_early`; overlap: `False`; bug class: `combination_same_cycle`; family: `fifo_boundary_flag`

Spec: full_o shall assert if and only if the FIFO currently contains Depth entries; it must remain low at Depth-1.

Legacy temporal input:

Abstracted trace summary:
- The bug is triggered by consecutive write-side increments with no read-side increment or clear, as the FIFO occupancy advances to the full boundary.
- Good behavior keeps full_o deasserted while the FIFO is still one entry short of full and asserts it only when depth_o reaches the true full count; buggy behavior asserts full_o and advances depth_o to the full count one write too early, then later drops full_o even while depth_o remains at the full count.
- The first divergence is the boundary-approach write where occupancy should still be pre-full: the good trace shows a not-full state with depth_o below capacity, while the bad trace already reports full_o and a full depth_o.

Raw candidates:

```text
c1 [literal-hardcoding] assert property (@(posedge clk) disable iff (!rst_n) (depth_o == 3'b100) |-> (full_o));
c2 [no-heldout-trigger|vacuous|literal-hardcoding] assert property (@(posedge clk) disable iff (!rst_n) ((depth_o == 3'b011) && !clr_i) |-> (!full_o));
```

Temporal candidates:

```text
c1 [no-heldout-trigger|vacuous|literal-hardcoding] assert property (@(posedge clk) disable iff (!rst_n) (depth_o == 3'd3) |-> (!full_o));
c2 [literal-hardcoding] assert property (@(posedge clk) disable iff (!rst_n) (depth_o == 3'd4) |-> (full_o));
```

Manual verdict: REVIEWED | primary=concrete_value_important | secondary=vacuity

Evidence: Each arm has one successful exact full-count assertion and one vacuous pre-full assertion.

## 27. both_success | GPT | case257_fifo_v1_from_case105_prim_fifo_empty_late

Parent: `case105_prim_fifo_empty_late`; overlap: `False`; bug class: `combination_same_cycle`; family: `fifo_boundary_flag`

Spec: empty_o shall assert in the same cycle the FIFO occupancy returns to zero.

Legacy temporal input:

Abstracted trace summary:
- The bug is triggered whenever the FIFO occupancy is zero, including reset/initial empty state and after a sequence of reads drains previously written entries back to zero.
- Good behavior asserts empty_o in the same cycle that depth_o indicates zero occupancy. Buggy behavior leaves empty_o deasserted even though the FIFO is empty.
- The first divergence is at the earliest zero-occupancy observation: both traces agree on non-empty operation while depth_o is above zero, then differ exactly when occupancy reaches or starts at zero and empty_o should reflect that immediately.

Raw candidates:

```text
c1 [literal-hardcoding] assert property (@(posedge clk) disable iff (!rst_n) ((depth_o == 3'b000)) |-> (empty_o));
c2 [literal-hardcoding] assert property (@(posedge clk) disable iff (!rst_n) ((!clr_i && (depth_o == 3'b001) && !incr_wptr_i && incr_rptr_i)) |=> (empty_o));
```

Temporal candidates:

```text
c1 [literal-hardcoding] assert property (@(posedge clk) disable iff (!rst_n) (depth_o == 3'd0) |-> (empty_o));
c2 [literal-hardcoding] assert property (@(posedge clk) disable iff (!rst_n) (!clr_i && depth_o == 3'd1 && incr_rptr_i && !incr_wptr_i) |=> (depth_o == 3'd0 && empty_o));
```

Manual verdict: REVIEWED | primary=exact_cycle_important | secondary=concrete_value_important

Evidence: Both preserve zero occupancy and same/next-cycle empty timing.

## 28. both_success | GPT | case273_fifo_v8_from_case106_prim_fifo_depth_off_by_one

Parent: `case106_prim_fifo_depth_off_by_one`; overlap: `False`; bug class: `combination_same_cycle`; family: `fifo_boundary_flag`

Spec: depth_o shall equal the exact FIFO occupancy in every cycle.

Legacy temporal input:

Abstracted trace summary:
- The bug is exposed from reset/empty initialization onward and throughout subsequent write-only, read-only, and idle cycles: depth_o should always represent the current FIFO occupancy implied by incr_wptr_i and incr_rptr_i.
- Good behavior reports zero occupancy when the FIFO is empty and then increments/decrements depth_o in step with net writes and reads. Buggy behavior reports depth_o consistently one higher than the true occupancy across the whole sequence.
- The first divergence occurs immediately in the empty reset state: empty_o indicates an empty FIFO in both traces, but only the bad trace shows a nonempty depth_o, after which every occupancy change remains offset by the same extra count.

Raw candidates:

```text
c1 [literal-hardcoding] assert property (@(posedge clk) disable iff (!rst_n) (empty_o) |-> (depth_o == 3'b000));
c2 [no-heldout-trigger|vacuous|literal-hardcoding] assert property (@(posedge clk) disable iff (!rst_n) (clr_i) |-> ((depth_o == 3'b000) && empty_o));
```

Temporal candidates:

```text
c1 [literal-hardcoding] assert property (@(posedge clk) disable iff (!rst_n) (empty_o) |-> (depth_o == 3'd0));
c2 [no-heldout-trigger|vacuous|literal-hardcoding] assert property (@(posedge clk) disable iff (!rst_n) (!clr_i && !full_o && !incr_rptr_i && incr_wptr_i) |-> (depth_o == $past(depth_o) + 3'd1));
```

Manual verdict: REVIEWED | primary=concrete_value_important | secondary=hardcoding

Evidence: Both catch the offset through the empty=>depth zero invariant; transition alternatives are more trace-sensitive.

## 29. both_success | Claude | case131_prim_filter_disabled_bypass_stale_alt

Parent: `case131_prim_filter_disabled_bypass_stale_alt`; overlap: `False`; bug class: `combination_same_cycle`; family: `filter_bypass_control`

Spec: When enable_i is low, filter_o shall reflect the live filter_i input immediately rather than the stored filtered value.

Legacy temporal input:

Abstracted trace summary:
- The bug is triggered when enable_i is deasserted after the filter had previously been active and the current filter_i differs from the previously stored filtered value.
- Good behavior bypasses the stored state and drives filter_o directly from the live filter_i immediately while disabled; buggy behavior instead lets filter_o momentarily reflect the stale prior filtered value.
- The first divergence occurs on the disable transition where the remembered filtered result and current filter_i no longer agree: good follows the new input at once, while bad still shows the old value.

Raw candidates:

```text
c1 [clean] assert property (@(posedge clk) disable iff (!rst_n) (!enable_i) |-> (filter_o == filter_i));
c2 [clean] assert property (@(posedge clk) disable iff (!rst_n) (!enable_i && filter_i) |-> (filter_o));
```

Temporal candidates:

```text
c1 [clean] assert property (@(posedge clk) disable iff (!rst_n) (!enable_i) |-> (filter_o == filter_i));
c2 [clean] assert property (@(posedge clk) disable iff (!rst_n) (!enable_i && filter_i) |-> (filter_o));
```

Manual verdict: REVIEWED | primary=polarity_lost | secondary=trigger_lost

Evidence: Both retain the disabled trigger and live-input/output polarity equality without cycle literals.

## 30. both_success | Claude | case225_onehot_addr_bad_v1_from_case103_prim_onehot_addr_mismatch_suppressed

Parent: `case103_prim_onehot_addr_mismatch_suppressed`; overlap: `False`; bug class: `combination_same_cycle`; family: `decoded_index_consistency`

Spec: If exactly one bit of oh_i is high, err_o shall assert when addr_i points to a different bit in the same cycle.

Legacy temporal input:

Abstracted trace summary:
- The bug is triggered when en_i is active, oh_i is exactly onehot, and addr_i selects a different bit than the asserted one in that same cycle.
- Good behavior asserts err_o on each enabled onehot/address mismatch cycle and keeps err_o low when addr_i matches the asserted onehot bit; buggy behavior incorrectly leaves err_o low even during the mismatch condition.
- The first divergence occurs at the first transition from an enabled matching onehot/address relation to an enabled mismatching relation while the same onehot input remains present; good raises err_o there, bad does not.

Raw candidates:

```text
c1 [clean] assert property (@(posedge clk) disable iff (!rst_n) ($onehot(oh_i) && !oh_i[addr_i]) |-> (err_o));
c2 [clean] assert property (@(posedge clk) disable iff (!rst_n) (oh_i[addr_i] != (|oh_i)) |-> (err_o));
```

Temporal candidates:

```text
c1 [clean] assert property (@(posedge clk) disable iff (!rst_n) ($onehot(oh_i) && !oh_i[addr_i]) |-> (err_o));
c2 [clean] assert property (@(posedge clk) disable iff (!rst_n) ($onehot(oh_i) && oh_i[addr_i]) |-> (!err_o));
```

Manual verdict: REVIEWED | primary=polarity_lost | secondary=trigger_lost

Evidence: Both retain onehot/address mismatch as trigger and positive err_o polarity.

## 31. both_fail | Claude | case139_prim_regwe_addr_check_false_positive

Parent: `case139_prim_regwe_addr_check_false_positive`; overlap: `False`; bug class: `combination_same_cycle`; family: `write_enable_position_legality`

Spec: For prim_reg_we_check, a legal onehot write-enable vector with en_i high shall not raise err_o even when the hot bit is not bit 0.

Legacy temporal input:

Abstracted trace summary:
- The bug is triggered when en_i is high and oh_i is a legal onehot write-enable whose single asserted bit is at a nonzero position.
- Good behavior keeps err_o low for that enabled legal onehot access regardless of which single bit is selected, while buggy behavior falsely asserts err_o for a valid non-bit-0 selection.
- The first divergence occurs when the trace moves from an enabled onehot on bit 0, which both implementations accept, to an enabled onehot on a different single bit; only the bad trace then raises err_o.

Raw candidates:

```text
c1 [clean] assert property (@(posedge clk) disable iff (!rst_n) ($onehot(oh_i) && en_i) |-> (!err_o));
c2 [literal-hardcoding] assert property (@(posedge clk) disable iff (!rst_n) (en_i && (oh_i != 4'b0000) && $onehot0(oh_i)) |-> (!err_o));
```

Temporal candidates:

```text
c1 [clean] assert property (@(posedge clk) disable iff (!rst_n) (en_i && $onehot(oh_i)) |-> (!err_o));
c2 [clean] assert property (@(posedge clk) disable iff (!rst_n) ($onehot0(oh_i) && ((|oh_i) == en_i)) |-> (!err_o));
```

Manual verdict: REVIEWED | primary=concrete_value_important | secondary=trigger_lost

Evidence: Generic legal-onehot assertions do not isolate the non-bit-0 condition that distinguishes this trace.

## 32. both_fail | GPT | case133_prim_edge_negedge_missing

Parent: `case133_prim_edge_negedge_missing`; overlap: `False`; bug class: `temporal_cross_cycle`; family: `edge_presence`

Spec: A sampled 1->0 transition shall generate a one-cycle pulse on q_negedge_pulse_o.

Legacy temporal input:

Abstracted trace summary:
- The bug is triggered when, after reset is released, the sampled input/output state transitions from high to low across consecutive clock samples.
- Good behavior generates a one-cycle pulse on q_negedge_pulse_o on that sampled falling-edge event, while buggy behavior leaves q_negedge_pulse_o low and misses the pulse.
- The first divergence is the first observed 1->0 transition of the sampled signal path: both traces agree on the earlier low level, steady high level, and rising-edge indication, then differ only when the falling-edge pulse should appear.

Raw candidates:

```text
c1 [no-heldout-trigger|vacuous] assert property (@(posedge clk) disable iff (!rst_n) ($past(q_sync_o) && !q_sync_o) |-> (q_negedge_pulse_o));
c2 [no-heldout-trigger|vacuous] assert property (@(posedge clk) disable iff (!rst_n) ($past(d_i) && !d_i) |-> (q_negedge_pulse_o));
```

Temporal candidates:

```text
c1 [no-heldout-trigger|vacuous] assert property (@(posedge clk) disable iff (!rst_n) ($past(q_sync_o) && !q_sync_o) |-> (q_negedge_pulse_o));
c2 [no-heldout-trigger|vacuous] assert property (@(posedge clk) disable iff (!rst_n) ($past(d_i) && !d_i) |-> (q_negedge_pulse_o));
```

Manual verdict: REVIEWED | primary=trigger_lost | secondary=vacuity

Evidence: Both reconstruct a falling edge on signals whose sampled antecedents never hit held-out.

## 33. both_fail | Claude | case253_fifo_v6_from_case104_prim_fifo_full_early

Parent: `case104_prim_fifo_full_early`; overlap: `False`; bug class: `combination_same_cycle`; family: `fifo_boundary_flag`

Spec: full_o shall assert if and only if the FIFO currently contains Depth entries; it must remain low at Depth-1.

Legacy temporal input:

Abstracted trace summary:
- The bug is triggered by write-only progression after reset, with successive incr_wptr_i assertions and no incr_rptr_i, as the FIFO advances from partially filled to the last remaining slot before full.
- Good behavior keeps full_o low while the FIFO is still at Depth-1 and only asserts full_o once the FIFO actually contains Depth entries; buggy behavior asserts full_o one write too early at the pre-full state and then deasserts full_o after the FIFO reaches the actually full state.
- The first divergence is the boundary-approach write that should leave exactly one slot remaining: good shows the FIFO as not full with depth_o indicating pre-full occupancy, while bad already reports full_o and a full depth_o.

Raw candidates:

```text
c1 [literal-hardcoding] assert property (@(posedge clk) disable iff (!rst_n) (full_o) |-> (depth_o == 3'd4));
c2 [no-heldout-trigger|vacuous|literal-hardcoding] assert property (@(posedge clk) disable iff (!rst_n) (depth_o == 3'd3) |-> (!full_o));
```

Temporal candidates:

```text
c1 [literal-hardcoding] assert property (@(posedge clk) disable iff (!rst_n) (full_o) |-> (depth_o == 3'd4));
c2 [no-heldout-trigger|vacuous|literal-hardcoding] assert property (@(posedge clk) disable iff (!rst_n) (depth_o == 3'd3) |-> (!full_o));
```

Manual verdict: REVIEWED | primary=vacuity | secondary=concrete_value_important

Evidence: Both arms duplicate the same boundary assertions; the pre-full trigger is absent and full=>depth does not expose the buggy run.

## 34. both_fail | GPT | case135_prim_intr_enable_mask_ignored

Parent: `case135_prim_intr_enable_mask_ignored`; overlap: `False`; bug class: `combination_same_cycle`; family: `interrupt_masking`

Spec: Even if interrupt state is set, intr_o shall be low in any sampled cycle where reg2hw_intr_enable_q_i is low.

Legacy temporal input:

Abstracted trace summary:
- Interrupt state has already been raised, and then the enable mask is dropped while the state remains high.
- Good behavior suppresses intr_o whenever the enable mask is low, even though the stored interrupt state is still set. Buggy behavior ignores the mask and leaves intr_o high.
- The first divergence is the first masked cycle after the interrupt state is already active: good drives intr_o low, bad keeps it asserted.

Raw candidates:

```text
c1 [too-strong-on-good] assert property (@(posedge clk) disable iff (!rst_n) (!reg2hw_intr_enable_q_i) |-> (!intr_o));
c2 [too-strong-on-good] assert property (@(posedge clk) disable iff (!rst_n) (reg2hw_intr_state_q_i && !reg2hw_intr_enable_q_i) |-> (!intr_o));
```

Temporal candidates:

```text
c1 [too-strong-on-good] assert property (@(posedge clk) disable iff (!rst_n) (!reg2hw_intr_enable_q_i && reg2hw_intr_state_q_i) |-> (!intr_o));
c2 [no-heldout-trigger|vacuous] assert property (@(posedge clk) disable iff (!rst_n) ($past(reg2hw_intr_state_q_i) && !reg2hw_intr_enable_q_i) |-> (!intr_o));
```

Manual verdict: REVIEWED | primary=too_strong | secondary=trigger_lost

Evidence: Both low-enable assertions reject good held-out behavior; the past-state alternative is vacuous.

## 35. both_fail | GPT | case138_prim_regwe_zero_enabled_false_positive

Parent: `case138_prim_regwe_zero_enabled_false_positive`; overlap: `False`; bug class: `combination_same_cycle`; family: `masked_write_enable_legality`

Spec: For prim_reg_we_check, en_i high with oh_i equal to zero shall remain legal and must not raise err_o in the same cycle.

Legacy temporal input:

Abstracted trace summary:
- The bug is triggered when en_i is asserted while oh_i is the all-zero vector in a sampled cycle after reset is released.
- Good behavior treats this zero-oh_i enabled case as legal and keeps err_o low in the same cycle, while buggy behavior falsely asserts err_o on that enabled zero input.
- The first divergence occurs at the first enabled cycle with no selected bit in oh_i; surrounding enabled one-hot cycles agree and keep err_o deasserted.

Raw candidates:

```text
c1 [no-heldout-trigger|vacuous|literal-hardcoding] assert property (@(posedge clk) disable iff (!rst_n) (en_i && (oh_i == 4'b0000)) |-> (!err_o));
c2 [no-heldout-trigger|vacuous|literal-hardcoding] assert property (@(posedge clk) disable iff (!rst_n) ((oh_i == 4'b0000) && err_o) |-> (!en_i));
```

Temporal candidates:

```text
c1 [no-heldout-trigger|vacuous|literal-hardcoding] assert property (@(posedge clk) disable iff (!rst_n) (en_i && (oh_i == 4'b0000)) |-> (!err_o));
c2 [literal-hardcoding] assert property (@(posedge clk) disable iff (!rst_n) ((oh_i == 4'b0000) && !err_o) |-> (!en_i || !err_o));
```

Manual verdict: REVIEWED | primary=hardcoding | secondary=vacuity

Evidence: Both pin the all-zero witnessed literal and fail to trigger on held-out.

## 36. both_fail | GPT | case247_regwe_enable_gap_v7_from_case126_prim_regwe_enable_gap

Parent: `case126_prim_regwe_enable_gap`; overlap: `False`; bug class: `combination_same_cycle`; family: `register_write_enable_consistency`

Spec: When en_i is low, any nonzero onehot write-enable vector shall trigger err_o in the same cycle.

Legacy temporal input:

Abstracted trace summary:
- The bug is triggered when en_i is low while oh_i is a nonzero onehot write-enable vector in the same sampled cycle.
- Good behavior asserts err_o immediately on each disabled-yet-active onehot request, while buggy behavior leaves err_o deasserted despite that invalid condition.
- The first divergence occurs at the first post-reset cycle where a onehot oh_i appears under en_i low; before that, reset/idle behavior matches and later enabled onehot activity is accepted by both traces.

Raw candidates:

```text
c1 [too-strong-on-good] assert property (@(posedge clk) disable iff (!rst_n) (!en_i && (|oh_i)) |-> (err_o));
c2 [too-strong-on-good|literal-hardcoding] assert property (@(posedge clk) disable iff (!rst_n) (!en_i && (oh_i != 4'b0000)) |-> (err_o));
```

Temporal candidates:

```text
c1 [too-strong-on-good] assert property (@(posedge clk) disable iff (!rst_n) (!en_i && $onehot(oh_i)) |-> (err_o));
c2 [too-strong-on-good|literal-hardcoding] assert property (@(posedge clk) disable iff (!rst_n) (!en_i && (oh_i != 4'b0000)) |-> (err_o));
```

Manual verdict: REVIEWED | primary=too_strong | secondary=polarity_lost

Evidence: Both broaden the invalid disabled request condition and reject legal good cycles.

## 37. both_fail | GPT | case118_prim_filter_ctr_early_accept

Parent: `case118_prim_filter_ctr_early_accept`; overlap: `False`; bug class: `temporal_cross_cycle`; family: `filter_threshold`

Spec: With filtering enabled, filter_o shall not switch until thresh_i consecutive agreeing samples have been observed.

Legacy temporal input:

Abstracted trace summary:
- The bug is triggered after reset when filtering is enabled and a new input value begins a run of agreeing samples that has not yet reached the programmed threshold.
- Good behavior keeps filter_o unchanged until the required number of consecutive agreeing enabled samples is accumulated, then updates; buggy behavior accepts on the first agreeing sample and switches filter_o too early.
- The first divergence is the first enabled sample of a new candidate value: good still holds the previous filtered output, while bad already changes filter_o before the threshold count is satisfied.

Raw candidates:

```text
c1 [no-heldout-trigger|vacuous] assert property (@(posedge clk) disable iff (!rst_n) (enable_i && pre_accept_hold_dbg) |-> (filter_o == $past(filter_o)));
c2 [no-heldout-trigger|vacuous|too-strong-on-good|literal-hardcoding] assert property (@(posedge clk) disable iff (!rst_n) (enable_i && (thresh_i > 2'd1) && (filter_i != filter_o)) |-> (!filter_o[=1] ##1 (enable_i && (filter_i == $past(filter_i)))));
```

Temporal candidates:

```text
c1 [no-heldout-trigger|vacuous] assert property (@(posedge clk) disable iff (!rst_n) (enable_i && pre_accept_hold_dbg) |-> (filter_o == $past(filter_o)));
c2 [no-heldout-trigger|vacuous|literal-hardcoding] assert property (@(posedge clk) disable iff (!rst_n) (enable_i && (thresh_i > 2'd1) && (filter_i != $past(filter_o)) && ($past(filter_i) != $past(filter_o))) |-> (filter_o == $past(filter_o)));
```

Manual verdict: REVIEWED | primary=duration_lost | secondary=trigger_lost

Evidence: Both miss the threshold-length run: debug/sequence antecedents are absent held-out and do not robustly encode consecutive duration.

## 38. both_fail | GPT | case127_prim_intr_status_test_qe_ignored

Parent: `case127_prim_intr_status_test_qe_ignored`; overlap: `False`; bug class: `temporal_cross_cycle`; family: `status_test_gate`

Spec: In Status mode, reg2hw_intr_test_q_i shall affect the latched test state only on cycles where reg2hw_intr_test_qe_i is asserted.

Legacy temporal input:

Abstracted trace summary:
- The bug is triggered in Status mode after a test-induced interrupt state has been set, when reg2hw_intr_test_q_i is later changed while reg2hw_intr_test_qe_i controls whether that change is allowed to update the latched test state.
- Good behavior updates the latched test state only on cycles with reg2hw_intr_test_qe_i asserted, so intr_o follows the earlier qualified set and later qualified clear. Buggy behavior effectively ignores the qualification rule and lets an unqualified test value keep intr_o asserted.
- The first divergence occurs when the previously qualified clear should have removed the test contribution to intr_o; good deasserts intr_o, while bad still shows the old asserted state and then continues to do so across the later qe-low test change.

Raw candidates:

```text
c1 [no-heldout-trigger|vacuous] assert property (@(posedge clk) disable iff (!rst_n) (reg2hw_intr_enable_q_i && !event_intr_i && !reg2hw_intr_test_qe_i) |-> (intr_o == $past(intr_o)));
c2 [no-heldout-trigger|vacuous] assert property (@(posedge clk) disable iff (!rst_n) (reg2hw_intr_enable_q_i && !event_intr_i && !reg2hw_intr_test_qe_i && $past(reg2hw_intr_enable_q_i) && !$past(event_intr_i) && !$past(reg2hw_intr_test_qe_i) && !$past(intr_o)) |-> (!intr_o));
```

Temporal candidates:

```text
c1 [too-strong-on-good] assert property (@(posedge clk) disable iff (!rst_n) (reg2hw_intr_enable_q_i && !event_intr_i && reg2hw_intr_test_qe_i && !reg2hw_intr_test_q_i) |-> (!intr_o));
c2 [no-heldout-trigger|vacuous] assert property (@(posedge clk) disable iff (!rst_n) (reg2hw_intr_enable_q_i && !event_intr_i && !reg2hw_intr_test_qe_i && !reg2hw_intr_test_q_i) |-> ($stable(intr_o)));
```

Manual verdict: REVIEWED | primary=trigger_lost | secondary=vacuity

Evidence: Most qe/history antecedents never occur held-out; the one firing temporal candidate is too strong on good.

## 39. both_fail | GPT | case132_prim_edge_posedge_missing

Parent: `case132_prim_edge_posedge_missing`; overlap: `False`; bug class: `temporal_cross_cycle`; family: `edge_presence`

Spec: A sampled 0->1 transition shall generate a one-cycle pulse on q_posedge_pulse_o.

Legacy temporal input:

Abstracted trace summary:
- The bug is triggered when rst_n is deasserted and the sampled input transitions from low to high, equivalently when q_sync_o reflects a 0->1 change.
- Good behavior generates a one-cycle pulse on q_posedge_pulse_o on that rising-transition sample, while buggy behavior leaves q_posedge_pulse_o low even though the positive edge occurred.
- The first divergence is the first post-reset rising edge of the tracked signal: both traces agree while the signal stays low, then good reports the edge and bad misses it.

Raw candidates:

```text
c1 [no-heldout-trigger|vacuous] assert property (@(posedge clk) disable iff (!rst_n) (!$past(q_sync_o) && q_sync_o) |-> (q_posedge_pulse_o));
c2 [no-heldout-trigger|vacuous] assert property (@(posedge clk) disable iff (!rst_n) (!$past(d_i) && d_i) |-> (q_posedge_pulse_o));
```

Temporal candidates:

```text
c1 [no-heldout-trigger|vacuous] assert property (@(posedge clk) disable iff (!rst_n) ($rose(q_sync_o)) |-> (q_posedge_pulse_o));
c2 [no-heldout-trigger|vacuous] assert property (@(posedge clk) disable iff (!rst_n) ($past(q_sync_o)==1'b0 && q_sync_o==1'b1) |-> (q_posedge_pulse_o && !q_negedge_pulse_o));
```

Manual verdict: REVIEWED | primary=trigger_lost | secondary=vacuity

Evidence: Both $rose/$past reconstructions have zero held-out antecedent hits.

## 40. both_fail | Claude | case111_prim_intr_output_or_mask

Parent: `case111_prim_intr_output_or_mask`; overlap: `False`; bug class: `combination_same_cycle`; family: `interrupt_masking`

Spec: The outgoing interrupt shall assert only when both the interrupt status and enable are high.

Legacy temporal input:

Abstracted trace summary:
- The bug is exposed whenever event_intr_i is asserted or the interrupt state changes while the intended output condition should still be governed by the conjunction of reg2hw_intr_state_q_i and reg2hw_intr_enable_q_i.
- Good behavior drives intr_o high only when both reg2hw_intr_state_q_i and reg2hw_intr_enable_q_i are high, and drives it low if either input is low. Buggy behavior lets intr_o assert when only one of those conditions is true, effectively behaving like an OR-masked interrupt output.
- The first divergence occurs immediately after reset release on a cycle where reg2hw_intr_enable_q_i is high but reg2hw_intr_state_q_i is still low: good keeps intr_o low, while bad raises intr_o early; later bad also stays high when enable drops or state clears but the other term remains high.

Raw candidates:

```text
c1 [too-strong-on-good] assert property (@(posedge clk) disable iff (!rst_n) (reg2hw_intr_state_q_i && reg2hw_intr_enable_q_i) |=> (intr_o));
c2 [too-strong-on-good] assert property (@(posedge clk) disable iff (!rst_n) (!(reg2hw_intr_state_q_i && reg2hw_intr_enable_q_i)) |=> (!intr_o));
```

Temporal candidates:

```text
c1 [too-strong-on-good] assert property (@(posedge clk) disable iff (!rst_n) (reg2hw_intr_state_q_i && reg2hw_intr_enable_q_i) |=> (intr_o));
c2 [too-strong-on-good] assert property (@(posedge clk) disable iff (!rst_n) (!(reg2hw_intr_state_q_i && reg2hw_intr_enable_q_i)) |=> (!intr_o));
```

Manual verdict: REVIEWED | primary=exact_cycle_important | secondary=too_strong

Evidence: Both use |=> for a same-cycle mask relation and therefore reject good held-out behavior.
