# AssertionForge Mini RTL Cases (10)

This folder contains 10 small RTL bug cases for quick assertion and waveform experiments.

Each case directory includes:
- `correct.v`
- `buggy.v`
- `tb.v`
- `tb_holdout.v`
- `tb_decoy.v`
- `waveform_good.csv`
- `waveform_bad.csv`
- `waveform_good_holdout.csv`
- `waveform_bad_holdout.csv`
- `waveform_good_decoy.csv`
- `waveform_bad_decoy.csv`

## Suggested simulation flow

Use the same testbench with either `correct.v` or `buggy.v`:

```powershell
# Good
iverilog -g2012 -o sim_good .\correct.v .\tb.v
vvp .\sim_good

# Bad
iverilog -g2012 -o sim_bad .\buggy.v .\tb.v
vvp .\sim_bad
```

Each testbench already has `$dumpfile/$dumpvars` so you can regenerate VCD waveforms locally.

## Trace divergence summary

Besides raw per-cycle traces, you can now generate a compact good/bad divergence summary for each case:

```bash
cd /mnt/d/AssertionForge-main/rtl_cases
python3 ./summarize_trace_divergence.py --root .
```

For each case this writes:
- `experiment/trace_summary.txt`
- `experiment/trace_summary.json`
- `experiment/trace_good_holdout.txt`
- `experiment/trace_bad_holdout.txt`

The summary includes:
- first divergence cycle between good and bad traces
- differing signal names at that cycle
- observed good/bad values for those differing signals only

The summary is intentionally observation-only. It should not restate the golden expected behavior or embed a natural-language bug explanation, so method 4 does not leak the answer.

## Held-out trace policy

Each case now has three correct/buggy stimulus tracks:

- `tb.v` + `waveform_good.csv` / `waveform_bad.csv`
  - used for prompt construction and the in-distribution evaluation path
- `tb_holdout.v` + `waveform_good_holdout.csv` / `waveform_bad_holdout.csv`
  - never shown to the model
  - used only for held-out generalization checks
- `tb_decoy.v` + `waveform_good_decoy.csv` / `waveform_bad_decoy.csv`
  - used as an explicit overfit lure
  - must preserve the bug family while changing surrounding trace detail

Trace-overfit is now defined by held-out behavior, not just by literal pinning:

- the assertion must still trigger non-vacuously on the unseen correct held-out trace
- it must still pass on held-out correct RTL
- it must still fail on held-out buggy RTL

If a trace-informed candidate only works on the seen trace but fails one of the held-out checks, it is marked as `trace_overfit` and does not count as `strict_success`.

## Regenerate all waveform CSVs from simulation

Now that `iverilog/vvp` is available, you can replace all hand-written cycle CSV files with
VCD-derived CSV files:

```bash
cd /mnt/d/AssertionForge-main/rtl_cases
chmod +x ./regenerate_waveforms.sh
./regenerate_waveforms.sh
```

This will overwrite:
- `waveform_good.csv`
- `waveform_bad.csv`
- `waveform_good_holdout.csv`
- `waveform_bad_holdout.csv`
- `waveform_good_decoy.csv`
- `waveform_bad_decoy.csv`

for every case directory, and also keep:
- `waveform_good.vcd`
- `waveform_bad.vcd`
- `waveform_good_holdout.vcd`
- `waveform_bad_holdout.vcd`
- `waveform_good_decoy.vcd`
- `waveform_bad_decoy.vcd`

## Prompt + SVA experiment

See:

- `SVA_PROMPT_EXPERIMENT.md`

It includes scripts for:

- exporting per-cycle text traces
- exporting divergence summaries (`trace_summary.txt/json`)
- building 4 prompt variants:
  - spec only
  - spec + RTL
  - spec + RTL + raw trace
  - spec + RTL + trace summary
- filtering low-quality SVA candidates with a shared static filter (`sva_static_filter.py`)
- evaluating generated SVAs (`compile`, `correct pass`, `buggy fail`, `non-vacuous`)

