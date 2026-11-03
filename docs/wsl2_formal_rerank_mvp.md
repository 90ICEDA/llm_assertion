# WSL2 Qwen Formal-Rerank MVP

This note describes the smallest useful experiment for AssertionForge on WSL2 Ubuntu:

1. Generate NL plans
2. Generate multiple SVA candidates per plan with local Qwen
3. Run JasperGold on every candidate
4. Rerank by formal outcome
5. Compare the selected result with the first-candidate baseline

## Why this MVP

This is the shortest path to answer the practical question:

> Does "generate several candidates, then use formal results to choose" beat the baseline first candidate?

No extra training is required. The only model work is inference from a locally deployed Qwen model.

## What already exists in this repo

The repo already contains the main rerank loop in [src/gen_plan.py](/C:/Users/USER/Desktop/AssertionForge-main/src/gen_plan.py):

- `generate_sva_candidates(...)`
- `run_jaspergold(...)`
- `rerank_sva_candidates(...)`
- `save_candidate_rerank_report(...)`

The run writes `candidate_rerank_report.csv` into the log directory.

## Recommended minimal settings

For the first pass, keep the experiment intentionally small:

- `enable_formal_rerank = True`
- `num_sva_candidates_per_plan = 3`
- `max_formal_candidates_per_plan = 3`
- `max_num_signals_process = 2`
- `max_prompts_per_signal = 2`
- `generate_SVAs = True`
- `use_KG = True`
- `prompt_builder = "dynamic"`

This keeps the compute budget low while still giving reranking a chance to help.

## WSL2 Ubuntu setup

### 1. Create the Python environment

```bash
cd ~/AssertionForge-main
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

### 2. Install and start Ollama

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama serve
```

Open another WSL2 terminal:

```bash
ollama pull qwen2.5-coder:7b-instruct
```

If the machine has enough VRAM, `qwen2.5-coder:14b-instruct` is the next model to try.

### 3. Confirm the local model endpoint

```bash
curl http://127.0.0.1:11434/api/tags
```

### 4. Confirm JasperGold is visible in WSL2

```bash
which jg
jg -version
```

If `jg` is not found, export the tool path before running AssertionForge.

## Minimal config flow

Use [src/config_mvp_qwen_wsl2_template.py](/C:/Users/USER/Desktop/AssertionForge-main/src/config_mvp_qwen_wsl2_template.py) as the starting point.

Update these fields first:

- `file_path`
- `design_dir`
- `KG_path`
- `valid_signals`
- `design_name`

Important design-dir requirements:

- `design_dir` must contain the RTL
- `design_dir` must contain `property_goldmine.sva`
- `design_dir` must contain an `FPV_*.tcl` file, because the current Jasper flow clones and edits that TCL

## Run command

```bash
cd ~/AssertionForge-main/src
source ../.venv/bin/activate
python main.py --config_file ./config_mvp_qwen_wsl2_template.py
```

## What to compare

The key comparison is already aligned with the MVP goal:

- baseline: first generated candidate for each NL plan
- reranked: best candidate chosen by formal result priority

Formal priority is:

- `proven`
- `inconclusive`
- `cex`
- `error`

Check the generated `candidate_rerank_report.csv` and compare:

- number of `proven`
- syntax-error count
- improvement over first-candidate selection

## Suggested evaluation protocol

For a fast sanity check:

1. Pick one design with an existing KG and working Jasper TCL
2. Restrict to 2 signals
3. Generate 3 candidates per plan
4. Run once with the local Qwen model
5. Inspect whether reranking increases proven assertions over baseline

If this helps, only then scale up:

1. Increase `max_num_signals_process`
2. Increase `max_prompts_per_signal`
3. Try a stronger Qwen model
4. Add more sophisticated reranking features

## Known practical blockers

- `property_goldmine.sva` missing in `design_dir`
- no `FPV_*.tcl` template in `design_dir`
- `jg` not available inside WSL2
- `KG_path` still points to a placeholder
- `valid_signals` includes names not present in the design

## Recommended next step

Run one existing design end to end first. Do not begin from a brand-new design and a brand-new KG in the same iteration.
