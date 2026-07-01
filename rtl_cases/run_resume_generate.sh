#!/usr/bin/env bash
set -euo pipefail

pkill -f "ollama serve" || true
nohup env \
  CUDA_VISIBLE_DEVICES= \
  HIP_VISIBLE_DEVICES= \
  ROCR_VISIBLE_DEVICES= \
  OLLAMA_LLM_LIBRARY=cpu \
  ollama serve >/tmp/ollama_cpu_serve.log 2>&1 </dev/null &

sleep 5

export OLLAMA_HOST=http://127.0.0.1:11434
export PYTHONUNBUFFERED=1

python3 /mnt/d/AssertionForge-main/rtl_cases/prepare_prompt_assets.py \
  --root /mnt/d/AssertionForge-main/rtl_cases_real_admitted_resume_20260619

python3 /mnt/d/AssertionForge-main/rtl_cases/generate_sva_from_prompts.py \
  --root /mnt/d/AssertionForge-main/rtl_cases_real_admitted_resume_20260619 \
  --ollama-model qwen2.5-coder:7b-instruct \
  --max-attempts 4 \
  --num-candidates 5
