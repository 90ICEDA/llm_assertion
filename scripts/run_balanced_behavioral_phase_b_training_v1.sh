#!/usr/bin/env bash
set -euo pipefail
cd /root/autodl-tmp/AssertionForge-main1
export HF_HOME=/root/autodl-tmp/cache/huggingface
export TOKENIZERS_PARALLELISM=false
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
python3 src/train_balanced_behavioral_phase_b_qwen3.py --variant anchor_20_all30 --resume
