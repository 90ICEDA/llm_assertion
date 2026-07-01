# Real RTL Mutation Scaffold

This directory contains mutation-backed case scaffolds extracted from real OpenTitan RTL.
The old evaluator scripts can be pointed at this root once each case has:

- `tb.v`
- `tb_holdout.v`
- waveform CSV/VCD files
- prompt assets regenerated
- golden + hardness self-checks passing

- total scaffolds: 30
- combo/same-cycle scaffolds: 14
- temporal/cross-cycle scaffolds: 16

Important: these are source-materialized mutation plans, not yet admitted benchmark cases.
Use the per-case `STIMULUS_NOTES.md` files to finish the held-out stimuli and waveform generation.
