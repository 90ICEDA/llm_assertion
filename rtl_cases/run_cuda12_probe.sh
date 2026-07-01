#!/usr/bin/env bash
set -euo pipefail

pkill -f "ollama serve" || true
pkill -f "/usr/lib/ollama/llama-server" || true

export OLLAMA_HOST=127.0.0.1:11436
export OLLAMA_LLM_LIBRARY=cuda_v12
export OLLAMA_FLASH_ATTENTION=false

nohup ollama serve >/tmp/ollama_cuda12_probe.log 2>&1 </dev/null &

for _ in $(seq 1 15); do
  if OLLAMA_HOST=http://127.0.0.1:11436 ollama list >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

echo "---LOG---"
tail -n 120 /tmp/ollama_cuda12_probe.log || true
echo "---RUN---"
OLLAMA_HOST=http://127.0.0.1:11436 ollama run qwen2.5-coder:7b-instruct "Return exactly OK."
