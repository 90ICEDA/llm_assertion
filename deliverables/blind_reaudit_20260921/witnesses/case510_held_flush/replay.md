# Held-flush witness

This is a post-freeze, targeted replay witness, not an active probe-selection experiment or training run. The freeze precedes this file. Both candidates receive the same input stimulus and same RTL variants.

Fixed compilation:

```bash
iverilog -g2012 -s tb -o correct.out rtl_cases_real_scale210_independent_next/case510_cc_spill_register_flush_push_priority/correct.v deliverables/blind_reaudit_20260921/witnesses/case510_held_flush/tb_held_flush.v
vvp correct.out
```

Buggy compilation replaces `correct.v` with `buggy.v` and `correct.out` with `buggy.out`.

The testbench reports the direct monitor semantics of `flush_i |=> !valid_o` (slot 06) and `flush_i |=> (data_o == flush_i)` (slot 07). On the fixed RTL, while flush remains high at the consequent sample, `valid_o=0` and `data_o=0`. Slot 06 passes; slot 07 wrongly demands `data_o=1`. On the buggy RTL, the simultaneous push creates `valid_o=1`, `data_o=0x55`, so both fail. Original stdout is saved separately. WSL emitted a launch/network warning before command output; both compiles and both simulations exited with code 0.

This establishes a legal fixed-design false positive for slot 07 outside the old one-cycle-flush feedback traces. It does not establish that slot 06 is a complete repair assertion: slot 06 omits the explicit collision trigger and the data-not-exposed condition.
