#!/usr/bin/env bash
set -euo pipefail
cd /root/autodl-tmp/AssertionForge-main1
export HF_HOME=/root/autodl-tmp/cache/huggingface
export TOKENIZERS_PARALLELISM=false
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
for variant in anchor_10 anchor_20 anchor_25
do
  echo "START ${variant} $(date -Is)"
  python3 src/train_balanced_behavioral_dev_qwen3.py --variant "${variant}" --resume
  echo "COMPLETE ${variant} $(date -Is)"
done
echo "ALL_BALANCED_DEV_TRAINING_COMPLETE $(date -Is)"
