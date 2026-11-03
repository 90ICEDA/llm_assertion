#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

ROOT_REL="${ROOT_REL:-rtl_cases_real_admitted_20260619}"
DATA_ROOT="${DATA_ROOT:-$REPO_ROOT/$ROOT_REL}"

OLLAMA_HOST="${OLLAMA_HOST:-http://127.0.0.1:11434}"
OLLAMA_MODEL="${OLLAMA_MODEL:-qwen2.5-coder:7b-instruct}"

IVERILOG_BIN="${IVERILOG_BIN:-/root/iverilog12-install/bin/iverilog}"
VVP_BIN="${VVP_BIN:-/root/iverilog12-install/bin/vvp}"

MAX_ATTEMPTS="${MAX_ATTEMPTS:-4}"
NUM_CANDIDATES="${NUM_CANDIDATES:-5}"

STRICT_REPORT_BASENAME="${STRICT_REPORT_BASENAME:-strict_eval_report_iv12.csv}"
SUMMARY_BASENAME="${SUMMARY_BASENAME:-strict_eval_by_method_and_bug_class_iv12.csv}"

echo "[INFO] Repo root: $REPO_ROOT"
echo "[INFO] Data root: $DATA_ROOT"
echo "[INFO] Ollama host: $OLLAMA_HOST"
echo "[INFO] Ollama model: $OLLAMA_MODEL"
echo "[INFO] IVerilog: $IVERILOG_BIN"
echo "[INFO] VVP: $VVP_BIN"

if [[ ! -d "$DATA_ROOT" ]]; then
  echo "[FATAL] Dataset root does not exist: $DATA_ROOT" >&2
  exit 1
fi

if [[ ! -x "$IVERILOG_BIN" ]]; then
  echo "[FATAL] IVerilog binary is not executable: $IVERILOG_BIN" >&2
  exit 1
fi

if [[ ! -x "$VVP_BIN" ]]; then
  echo "[FATAL] VVP binary is not executable: $VVP_BIN" >&2
  exit 1
fi

export OLLAMA_HOST
export PYTHONUNBUFFERED=1

python3 "$REPO_ROOT/rtl_cases/prepare_prompt_assets.py" \
  --root "$DATA_ROOT"

python3 "$REPO_ROOT/rtl_cases/generate_sva_from_prompts.py" \
  --root "$DATA_ROOT" \
  --ollama-model "$OLLAMA_MODEL" \
  --max-attempts "$MAX_ATTEMPTS" \
  --num-candidates "$NUM_CANDIDATES"

python3 "$REPO_ROOT/rtl_cases/evaluate_generated_sva.py" \
  --root "$DATA_ROOT" \
  --output-csv "$DATA_ROOT/$STRICT_REPORT_BASENAME" \
  --iverilog "$IVERILOG_BIN" \
  --vvp "$VVP_BIN"

python3 "$REPO_ROOT/rtl_cases/summarize_strict_eval_by_method_and_bug_class.py" \
  --root "$DATA_ROOT" \
  --report "$DATA_ROOT/$STRICT_REPORT_BASENAME" \
  --output-csv "$DATA_ROOT/$SUMMARY_BASENAME"

echo "[DONE] Full admitted rerun complete."
echo "[DONE] Strict report: $DATA_ROOT/$STRICT_REPORT_BASENAME"
echo "[DONE] Summary: $DATA_ROOT/$SUMMARY_BASENAME"
