# Cross-model reproducibility

## One command

Formal reproducible benchmark (five sealed parents, four models, four candidates per cell):

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_all_cross_model_repro.ps1
```

All-case expansion:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_all_cross_model_repro.ps1 -AllCases -CandidatesPerCell 4
```

The command first materializes a sealed benchmark copy, then creates identical prompts, calls GPT, Claude, Qwen-72B and local Qwen2.5-Coder-7B, extracts candidates, compiles them, runs visible and held-out simulations, runs the Qwen property-to-SVA baseline, and generates tables plus prompt/model/test seals.

API keys are read from `.secrets/openai_api_key.txt`, `.secrets/anthropic_api_key.txt`, and `.secrets/qwen_api_key.txt`; they are never written to outputs. Local Ollama must expose `qwen2.5-coder:7b-instruct` at `http://127.0.0.1:11434/api/chat`.

All models use the same case set, method, prompt construction, temperature, and candidate count. Qwen direct and property-to-SVA also produce the same number of final candidates per cell; the two-stage path reports its additional calls, tokens, and latency separately. USD cost is emitted only for models with a sealed public price source; token and wall-time costs are always reported.

`run_all_stage_audit.json` is the terminal artifact. It verifies row counts and hashes across data selection, prompts, generation, extraction, compilation, visible/held-out validation, tables, and seals. A run is complete only when its top-level `pass` is true.
