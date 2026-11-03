# Best Generated Assertion Per Case

Selection rule: prefer `strict_success`, then non-`trace_overfit`, then template match, compile success, `correct_pass`, `buggy_fail`, `non_vacuous`, `antecedent_triggered`, and richer prompt methods as tie-breaker.

## case01_reset_omission

- Bug type: reset omitted
- Chosen method: spec + RTL + trace summary
- Candidate: 1
- Failure type: strict_success
- template_ok: True
- compile_ok: True
- analysis_supported: True
- correct_pass: True
- buggy_fail: True
- non_vacuous: True
- antecedent_triggered: True
- trace_overfit: False
- heldout_pass_on_correct: True
- heldout_fail_on_buggy: True
- heldout_non_vacuous: True
- Assertion: `assert property (@(posedge clk) (!rst_n) |-> (q == 1'b0));`

## case02_grant_delay

- Bug type: grant delayed by one cycle
- Chosen method: spec + RTL + trace summary
- Candidate: 1
- Failure type: strict_success
- template_ok: True
- compile_ok: True
- analysis_supported: True
- correct_pass: True
- buggy_fail: True
- non_vacuous: True
- antecedent_triggered: True
- trace_overfit: False
- heldout_pass_on_correct: True
- heldout_fail_on_buggy: True
- heldout_non_vacuous: True
- Assertion: `assert property (@(posedge clk) disable iff (!rst_n) (1'b1) |-> (grant == $past(req)));`

## case03_valid_ready_or_bug

- Bug type: valid/ready logic uses OR
- Chosen method: spec + RTL + trace summary
- Candidate: 1
- Failure type: strict_success
- template_ok: True
- compile_ok: True
- analysis_supported: True
- correct_pass: True
- buggy_fail: True
- non_vacuous: True
- antecedent_triggered: True
- trace_overfit: False
- heldout_pass_on_correct: True
- heldout_fail_on_buggy: True
- heldout_non_vacuous: True
- Assertion: `assert property (@(posedge clk) disable iff (!rst_n) ((valid_i && !ready_i) || (!valid_i && ready_i)) |-> (!valid_o));`

## case04_fsm_transition

- Bug type: FSM transition wrong
- Chosen method: spec + RTL + trace summary
- Candidate: 1
- Failure type: strict_success
- template_ok: True
- compile_ok: True
- analysis_supported: True
- correct_pass: True
- buggy_fail: True
- non_vacuous: True
- antecedent_triggered: True
- trace_overfit: False
- heldout_pass_on_correct: True
- heldout_fail_on_buggy: True
- heldout_non_vacuous: True
- Assertion: `assert property (@(posedge clk) disable iff (!rst_n) (finish) |=> (state == 2'd2));`

## case05_counter_boundary

- Bug type: counter wrap boundary wrong
- Chosen method: spec + RTL + trace summary
- Candidate: 1
- Failure type: strict_success
- template_ok: True
- compile_ok: True
- analysis_supported: True
- correct_pass: True
- buggy_fail: True
- non_vacuous: True
- antecedent_triggered: True
- trace_overfit: False
- heldout_pass_on_correct: True
- heldout_fail_on_buggy: True
- heldout_non_vacuous: True
- Assertion: `assert property (@(posedge clk) disable iff (!rst_n) (en && (cnt != limit)) |=> (cnt == ($past(cnt) + 3'd1)));`

## case06_priority_encoder

- Bug type: priority reversed
- Chosen method: spec + RTL + trace summary
- Candidate: 1
- Failure type: strict_success
- template_ok: True
- compile_ok: True
- analysis_supported: True
- correct_pass: True
- buggy_fail: True
- non_vacuous: True
- antecedent_triggered: True
- trace_overfit: False
- heldout_pass_on_correct: True
- heldout_fail_on_buggy: True
- heldout_non_vacuous: True
- Assertion: `assert property (@(posedge clk) disable iff (!rst_n) (($past(req) == 4'b1010) || ($past(req) == 4'b1100) || ($past(req) == 4'b1001)) |-> (((($past(req) == 4'b1010) && ((grant == 4'b1000) || (grant == 4'b0100))) || ((($past(req) == 4'b1100) || ($past(req) == 4'b1001)) && (grant == 4'b1000)))));`

## case07_fifo_full_boundary

- Bug type: full asserted early
- Chosen method: spec + RTL + trace summary
- Candidate: 1
- Failure type: strict_success
- template_ok: True
- compile_ok: True
- analysis_supported: True
- correct_pass: True
- buggy_fail: True
- non_vacuous: True
- antecedent_triggered: True
- trace_overfit: False
- heldout_pass_on_correct: True
- heldout_fail_on_buggy: True
- heldout_non_vacuous: True
- Assertion: `assert property (@(posedge clk) disable iff (!rst_n) (1'b1) |-> (full == (count == 3'd4)));`

## case08_pulse_width

- Bug type: pulse width too short
- Chosen method: spec + RTL + trace summary
- Candidate: 1
- Failure type: strict_success
- template_ok: True
- compile_ok: True
- analysis_supported: True
- correct_pass: True
- buggy_fail: True
- non_vacuous: True
- antecedent_triggered: True
- trace_overfit: False
- heldout_pass_on_correct: True
- heldout_fail_on_buggy: True
- heldout_non_vacuous: True
- Assertion: `assert property (@(posedge clk) disable iff (!rst_n) (trigger) |=> ##1 (pulse));`

## case09_addr_increment

- Bug type: address stride wrong
- Chosen method: spec + RTL + trace summary
- Candidate: 1
- Failure type: strict_success
- template_ok: True
- compile_ok: True
- analysis_supported: True
- correct_pass: True
- buggy_fail: True
- non_vacuous: True
- antecedent_triggered: True
- trace_overfit: False
- heldout_pass_on_correct: True
- heldout_fail_on_buggy: True
- heldout_non_vacuous: True
- Assertion: `assert property (@(posedge clk) disable iff (!rst_n) ($past(step)) |-> ((addr == ($past(addr) + 8'd4)) && (addr[1:0] == 2'b00)));`

## case10_hold_valid_until_ready

- Bug type: valid drops too early
- Chosen method: spec + RTL + trace summary
- Candidate: 1
- Failure type: strict_success
- template_ok: True
- compile_ok: True
- analysis_supported: True
- correct_pass: True
- buggy_fail: True
- non_vacuous: True
- antecedent_triggered: True
- trace_overfit: False
- heldout_pass_on_correct: True
- heldout_fail_on_buggy: True
- heldout_non_vacuous: True
- Assertion: `assert property (@(posedge clk) disable iff (!rst_n) (valid_o && !ready_i) |=> (valid_o || ready_i));`

