#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-/mnt/d/AssertionForge-main/rtl_cases_real_admitted_resume_20260619}"
CPU_LOG="/tmp/ollama_cpu_serve.log"
OLLAMA_MODEL="${OLLAMA_MODEL:-qwen2.5-coder:7b-instruct}"

start_cpu_ollama() {
  pkill -f "ollama serve" || true
  pkill -f "/usr/lib/ollama/llama-server" || true

  nohup env \
    CUDA_VISIBLE_DEVICES= \
    HIP_VISIBLE_DEVICES= \
    ROCR_VISIBLE_DEVICES= \
    OLLAMA_LLM_LIBRARY=cpu \
    ollama serve >"$CPU_LOG" 2>&1 </dev/null &

  for _ in $(seq 1 20); do
    if OLLAMA_HOST=http://127.0.0.1:11434 ollama list >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done

  echo "[FATAL] CPU Ollama did not become ready." >&2
  tail -n 120 "$CPU_LOG" >&2 || true
  exit 1
}

count_candidates() {
  local gen_dir="$1"
  local stem="$2"
  find "$gen_dir" -maxdepth 1 -type f -name "${stem}__cand_*.sv" | wc -l
}

rerun_method_for_case() {
  local case_name="$1"
  local method="$2"
  local stem="$3"
  local gen_dir="$ROOT/$case_name/experiment/generated"

  mkdir -p "$gen_dir"
  find "$gen_dir" -maxdepth 1 -type f -name "${stem}__cand_*.sv" -delete

  echo "[RUN] $case_name method=$method stem=$stem"
  OLLAMA_HOST=http://127.0.0.1:11434 \
  PYTHONUNBUFFERED=1 \
  python3 /mnt/d/AssertionForge-main/rtl_cases/generate_sva_from_prompts.py \
    --root "$ROOT" \
    --case "$case_name" \
    --methods "$method" \
    --ollama-model "$OLLAMA_MODEL" \
    --max-attempts 4 \
    --num-candidates 5
}

main() {
  export OLLAMA_HOST=http://127.0.0.1:11434
  export PYTHONUNBUFFERED=1

  echo "[INFO] ROOT=$ROOT"
  echo "[INFO] OLLAMA_MODEL=$OLLAMA_MODEL"

  start_cpu_ollama

  python3 /mnt/d/AssertionForge-main/rtl_cases/prepare_prompt_assets.py --root "$ROOT"

  local method_ids=("1" "2" "3" "4")
  local stems=(
    "sva_1_spec_only"
    "sva_2_spec_plus_rtl"
    "sva_3_spec_rtl_raw_trace"
    "sva_4_spec_rtl_trace_summary"
  )

  while IFS= read -r case_path; do
    local case_name
    case_name="$(basename "$case_path")"
    local gen_dir="$case_path/experiment/generated"
    mkdir -p "$gen_dir"

    for i in "${!method_ids[@]}"; do
      local count
      count="$(count_candidates "$gen_dir" "${stems[$i]}")"
      if [[ "$count" -eq 5 ]]; then
        continue
      fi
      rerun_method_for_case "$case_name" "${method_ids[$i]}" "${stems[$i]}"
    done
  done < <(find "$ROOT" -mindepth 1 -maxdepth 1 -type d -name 'case*' | sort)
}

main "$@"
