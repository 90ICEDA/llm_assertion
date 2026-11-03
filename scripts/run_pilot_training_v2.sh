#!/usr/bin/env bash
set -euo pipefail

PROJECT=${PROJECT:-/root/autodl-tmp/AssertionForge-main1}
cd "$PROJECT"
export HF_HOME=${HF_HOME:-/root/autodl-tmp/cache/huggingface}
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export TOKENIZERS_PARALLELISM=false

python3 src/materialize_pilot_training_data.py --check-only
methods=(ordinary_sft pass_count_dpo scalar_score_dpo random_probe_dominance_dpo full_disagreement_dominance_dpo)

for method in "${methods[@]}"; do
  python3 src/train_pilot_qwen3.py --method "$method" --dry-run
done

for method in "${methods[@]}"; do
  result="outputs/behavioral_preference_pilot_v1/formal_training_v2/${method}/training_result.json"
  if [[ -f "$result" ]] && grep -q '"status": "pass"' "$result"; then
    echo "SKIP_COMPLETE method=${method}"
    continue
  fi
  out="outputs/behavioral_preference_pilot_v1/formal_training_v2/${method}"
  mkdir -p "$out"
  echo "START method=${method} time=$(date -Is)"
  python3 src/train_pilot_qwen3.py --method "$method" --resume --save-steps 500 2>&1 | tee -a "$out/launcher.log"
  echo "COMPLETE method=${method} time=$(date -Is)"
done

echo "ALL_TRAINING_V2_COMPLETE time=$(date -Is)"
