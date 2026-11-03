#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="/mnt/d/AssertionForge-main1"
DATA_ROOT="$REPO_ROOT/rtl_cases_real_scale160_temporal_boosted"
OUT_DIR="$REPO_ROOT/outputs/scale160_temporal_boost_wsl"

cd "$REPO_ROOT"
mkdir -p "$OUT_DIR"

echo "=== SCALE160 TEMPORAL BOOST: REGENERATE PROMPT ASSETS ==="
python3 rtl_cases/prepare_prompt_assets.py --root "$DATA_ROOT"

echo "=== SCALE160 TEMPORAL BOOST: REGENERATE WAVEFORMS ==="
python3 rtl_cases/regenerate_waveforms_for_root.py \
  --root "$DATA_ROOT" \
  --iverilog iverilog \
  --vvp vvp \
  --converter "$REPO_ROOT/rtl_cases/vcd_to_csv.py"

echo "=== SCALE160 TEMPORAL BOOST: GOLDEN RECHECK (FORMAL-AWARE) ==="
python3 src/recheck_golden_wsl.py \
  --root "$DATA_ROOT" \
  --iverilog iverilog \
  --vvp vvp \
  --output-csv "$OUT_DIR/golden_recheck_scale160_temporal_boost.csv"

echo "=== SCALE160 TEMPORAL BOOST: HARDNESS RECHECK ==="
python3 rtl_cases/check_case_hardness.py \
  --root "$DATA_ROOT" \
  --iverilog iverilog \
  --vvp vvp \
  --output-csv "$OUT_DIR/hardness_scale160_temporal_boost.csv"

echo "=== SCALE160 TEMPORAL BOOST: TRACE DIVERGENCE RECHECK ==="
python3 rtl_cases/audit_trace_divergence_gate.py \
  --root "$DATA_ROOT" \
  --output-csv "$OUT_DIR/trace_divergence_scale160_temporal_boost.csv"

echo "=== DONE ==="
echo "golden:   $OUT_DIR/golden_recheck_scale160_temporal_boost.csv"
echo "hardness: $OUT_DIR/hardness_scale160_temporal_boost.csv"
echo "traces:   $OUT_DIR/trace_divergence_scale160_temporal_boost.csv"
