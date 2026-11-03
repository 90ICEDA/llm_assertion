# SVA Prompt Experiment Workflow

This workflow does exactly what you asked for:

1. Convert waveform results to per-cycle text traces
2. Build 4 prompt variants
3. Generate one SVA per prompt
4. Check compile / pass-on-correct / fail-on-buggy / non-vacuous

## 0) Prerequisites (inside Ubuntu / WSL)

- `iverilog`, `vvp`
- `python3`
- Waveforms already regenerated (recommended):
  - `waveform_good.csv`
  - `waveform_bad.csv`

## 1) Prepare trace text + prompts

From `rtl_cases`:

```bash
cd /mnt/d/AssertionForge-main/rtl_cases
python3 ./prepare_prompt_assets.py --root .
```

For each case, it creates:

- `experiment/spec.txt`
- `experiment/trace_good.txt`
- `experiment/trace_bad.txt`
- `experiment/prompts/prompt_1_spec_only.txt`
- `experiment/prompts/prompt_2_spec_plus_rtl.txt`
- `experiment/prompts/prompt_3_spec_rtl_raw_trace.txt`
- `experiment/prompts/prompt_4_spec_rtl_trace_summary.txt`

The `trace_summary.txt/json` outputs are observation-only:

- first divergence cycle
- differing signal names
- observed good/bad values for those differing signals

They deliberately do not restate the expected behavior in natural language, so method 4 does not get to "peek" at the answer.

If you want direct VCD-to-text conversion for one file:

```bash
python3 ./vcd_to_trace_text.py \
  ./case03_valid_ready_or_bug/waveform_good.vcd \
  ./case03_valid_ready_or_bug/experiment/trace_good_from_vcd.txt \
  --signals clk,rst_n,valid_i,ready_i,valid_o,data_i[7:0],data_o[7:0]
```

## 2) Generate SVA from prompts

Use any LLM CLI command that accepts a prompt file and prints output to stdout.

Example:

```bash
python3 ./generate_sva_from_prompts.py \
  --root . \
  --llm-command "your_llm_cli --prompt-file {prompt_file}"
```

Recommended for Qwen online API (OpenAI-compatible):

```bash
export QWEN_API_KEY="your_api_key"
export QWEN_MODEL="your_qwen_model"
python3 ./generate_sva_from_prompts.py \
  --root . \
  --llm-command "python3 ./qwen_api_bridge.py --prompt-file {prompt_file}"
```

Optional overrides:

- `QWEN_BASE_URL`: custom OpenAI-compatible base URL
- `DASHSCOPE_API_KEY`: accepted as an alternative to `QWEN_API_KEY`
- `DASHSCOPE_MODEL`: accepted as an alternative to `QWEN_MODEL`

Or with local Ollama directly:

```bash
python3 ./generate_sva_from_prompts.py \
  --root . \
  --ollama-model qwen2.5-coder:7b-instruct \
  --max-attempts 4 \
  --num-candidates 5
```

If WSL cannot reach Windows-hosted Ollama at `127.0.0.1:11434`, pass the Windows host IP explicitly:

```bash
WIN_HOST=$(awk '/nameserver/ {print $2; exit}' /etc/resolv.conf)
python3 ./generate_sva_from_prompts.py \
  --root . \
  --ollama-model qwen2.5-coder:7b-instruct \
  --ollama-base-url "http://${WIN_HOST}:11434" \
  --max-attempts 4 \
  --num-candidates 5
```

If the Windows Ollama service is only exposed to the Windows CLI and not reachable from WSL over HTTP, use the included CLI bridge instead:

```bash
python3 ./generate_sva_from_prompts.py \
  --root . \
  --llm-command "python3 ./ollama_cli_bridge.py --model qwen2.5-coder:7b-instruct --prompt-file {prompt_file}" \
  --max-attempts 4 \
  --num-candidates 5
```

With the current candidate-preserving flow, `--num-candidates 5` writes five files per method, for example:

- `sva_1_spec_only__cand_01.sv`
- `sva_1_spec_only__cand_02.sv`
- ...
- `sva_4_spec_rtl_trace_summary__cand_05.sv`

The generator now has built-in reject-and-regenerate checks:

- stage 1: JSON structured generation (`op`, `antecedent`, `consequent`) then local assembly
- stage 2 fallback: legacy direct assertion-line generation if JSON stage fails
- static filter rejects low-level errors before acceptance
- generate multiple candidates per prompt and choose the best one with a trace-based gate
- exactly one `assert property (...) ;`
- only whitelist signals from `case_manifest.json`
- reject `next_state`, `count_next`, `count_prev`, `S_*`, `old(...)`, `$past`, `##`
- reject nested implication inside antecedent/consequent
- reject tautologies, same-cycle self-update compares, unknown signals, bad reset/clock conditions, scalar bit-selects, and multi-assertion outputs
- prefer candidates that do not fail on good trace and do fail on bad trace
- for trace-based methods, avoid one-off literal memorization from the trace summary or raw trace when a more general relation is possible

Outputs per case:

- `experiment/generated/sva_1_spec_only__cand_01.sv` ... `__cand_05.sv`
- `experiment/generated/sva_2_spec_plus_rtl__cand_01.sv` ... `__cand_05.sv`
- `experiment/generated/sva_3_spec_rtl_raw_trace__cand_01.sv` ... `__cand_05.sv`
- `experiment/generated/sva_4_spec_rtl_trace_summary__cand_01.sv` ... `__cand_05.sv`

## 3) Evaluate generated SVA

Evaluate all available generated files:

```bash
python3 ./evaluate_generated_sva.py --root . --output-csv ./sva_eval_report.csv
```

Strict evaluation with `strict_success` and `failure_type`:

```bash
python3 ./evaluate_generated_sva.py --root . --output-csv ./strict_eval_report.csv
```

The evaluator now reuses the same static filter before simulation. If a generated SVA has a low-level issue, the row is marked with:

- `syntax_pass=False`
- `failure_type=syntax_fail`
- `compile_error=STATIC_FILTER: ...`

Or evaluate one file:

```bash
python3 ./evaluate_generated_sva.py \
  --root . \
  --case case03_valid_ready_or_bug \
  --sva-file ./case03_valid_ready_or_bug/experiment/generated/sva_4_spec_rtl_trace_summary.sv \
  --output-csv ./case03_caseonly_report.csv
```

## Expected SVA format

The checker expects one assertion in this strict format:

```systemverilog
assert property (@(posedge clk) disable iff (!rst_n) (<ANTECEDENT>) |-> (<CONSEQUENT>));
```

`|=>` is also accepted.

To keep automatic checking robust, avoid:

- `##` delays
- `$past`
- complex sequence operators

## Optional standalone static filter

You can also run the static filter directly on one candidate:

```bash
python3 ./sva_static_filter.py \
  --root . \
  --case case03_valid_ready_or_bug \
  --sva-file ./case03_valid_ready_or_bug/experiment/generated/sva_4_spec_rtl_trace_summary.sv
```

It returns JSON with `pass`, `reasons`, and `warnings`, and exits nonzero when the assertion should be rejected.

## Output meaning

In the CSV report:

- `compile_ok`: SVA syntax accepted by `iverilog`
- `pass_on_correct`: no assertion failure on correct RTL under provided testbench
- `fail_on_buggy`: at least one assertion failure on buggy RTL under provided testbench
- `non_vacuous`: antecedent hit count > 0 (correct or buggy run)
- `trace_overfit`: candidate appears to hard-code observed trace literals rather than expressing a general rule
- `strict_success`: requires syntax pass, correct pass, buggy fail, non-vacuous, antecedent triggered, no trace overfit, and manual semantic approval
- `failure_type`: strict failure classification (`syntax_fail`, `false_positive_on_correct`, `bug_not_detected_on_buggy`, `trace_overfit`, etc.)

## 4) Rerun + Compare

To regenerate SVA with the new prompts and compare against an existing baseline strict report:

```bash
python3 ./rerun_sva_prompt_experiment.py \
  --root . \
  --baseline-report ./strict_eval_report.csv \
  --new-report ./strict_eval_report_rerun.csv \
  --comparison-prefix ./strict_eval_comparison_rerun \
  --ollama-model qwen2.5-coder:7b-instruct
```

If Ollama is running on Windows and WSL cannot use `127.0.0.1`, add:

```bash
  --ollama-base-url "http://${WIN_HOST}:11434"
```

Or bypass HTTP entirely and call the Windows Ollama CLI from WSL:

```bash
python3 ./rerun_sva_prompt_experiment.py \
  --root . \
  --baseline-report ./strict_eval_report.csv \
  --new-report ./strict_eval_report_rerun.csv \
  --comparison-prefix ./strict_eval_comparison_rerun \
  --methods 3,4 \
  --llm-command "python3 ./ollama_cli_bridge.py --model qwen2.5-coder:7b-instruct --prompt-file {prompt_file}"
```

If `ollama.exe` is installed in a nonstandard Windows location, probe first:

```bash
python3 ./ollama_cli_bridge.py --model qwen2.5-coder:7b-instruct --probe
```

Or pass the executable path explicitly:

```bash
python3 ./rerun_sva_prompt_experiment.py \
  --root . \
  --baseline-report ./strict_eval_report.csv \
  --new-report ./strict_eval_report_rerun.csv \
  --comparison-prefix ./strict_eval_comparison_rerun \
  --methods 3,4 \
  --llm-command "python3 ./ollama_cli_bridge.py --model qwen2.5-coder:7b-instruct --ollama-exe /mnt/c/Path/To/ollama.exe --prompt-file {prompt_file}"
```

The bridge also accepts `OLLAMA_EXE` or `OLLAMA_WINDOWS_EXE` from the environment.

If you want to avoid local Ollama entirely and keep using Qwen through an online API, rerun methods 3/4 like this:

```bash
export QWEN_API_KEY="your_api_key"
export QWEN_MODEL="your_qwen_model"
python3 ./rerun_sva_prompt_experiment.py \
  --root . \
  --baseline-report ./strict_eval_report_rerun.csv \
  --new-report ./strict_eval_report_trace_clean_34.csv \
  --comparison-prefix ./strict_eval_comparison_trace_clean_34 \
  --methods 3,4 \
  --llm-command "python3 ./qwen_api_bridge.py --prompt-file {prompt_file}"
```

If you only want the full candidate report and by-method summary (and want to skip baseline comparison), add:

```bash
  --skip-compare
```

This produces:

- `strict_eval_report_rerun.csv`
- `strict_eval_comparison_rerun_by_method.csv`
- `strict_eval_comparison_rerun_by_method.md`
- `strict_eval_comparison_rerun.csv`
- `strict_eval_comparison_rerun.md`

When `--num-candidates 5` is used across 10 cases and 4 methods, the strict report contains 200 candidate rows.

To rerun only the trace-informed methods after changing summary leakage behavior:

```bash
python3 ./rerun_sva_prompt_experiment.py \
  --root . \
  --baseline-report ./strict_eval_report.csv \
  --new-report ./strict_eval_report_trace_clean.csv \
  --comparison-prefix ./strict_eval_comparison_trace_clean \
  --methods 3,4 \
  --ollama-model qwen2.5-coder:7b-instruct
```

