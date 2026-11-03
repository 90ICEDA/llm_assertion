#!/usr/bin/env bash
set -euo pipefail
cd /root/autodl-tmp/AssertionForge-main1
export HF_HOME=/root/autodl-tmp/cache/huggingface
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export TOKENIZERS_PARALLELISM=false
methods=(ordinary_sft pass_count_dpo scalar_score_dpo random_probe_dominance_dpo full_disagreement_dominance_dpo)
for method in "${methods[@]}"; do
  python3 src/train_pilot_v2_corrected_qwen3.py --method "$method" --dry-run
done
for method in "${methods[@]}"; do
  echo "START $method $(date -Is)"
  python3 src/train_pilot_v2_corrected_qwen3.py --method "$method" --resume
  echo "COMPLETE $method $(date -Is)"
done
