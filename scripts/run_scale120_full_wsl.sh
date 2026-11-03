#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="/mnt/d/AssertionForge-main1"
DATA_ROOT="$REPO_ROOT/rtl_cases_real_scale120"
OUT_DIR="$REPO_ROOT/outputs"

cd "$REPO_ROOT"
mkdir -p "$OUT_DIR"

echo "=== REFRESH DECOY STRUCTURE ==="
python3 rtl_cases/ensure_decoy_structure.py \
  --root "$DATA_ROOT" \
  --output-csv "$OUT_DIR/decoy_structure_scale120_wsl.csv"

echo "=== REGENERATE WAVEFORMS ==="
python3 rtl_cases/regenerate_waveforms_for_root.py \
  --root "$DATA_ROOT" \
  --iverilog iverilog \
  --vvp vvp \
  --converter "$REPO_ROOT/rtl_cases/vcd_to_csv.py"

echo "=== FULL GOLDEN RECHECK ==="
python3 rtl_cases/check_golden_sva.py \
  --root "$DATA_ROOT" \
  --iverilog iverilog \
  --vvp vvp \
  --output-csv "$OUT_DIR/golden_recheck_scale120_wsl.csv"

echo "=== FULL HARDNESS RECHECK ==="
python3 rtl_cases/check_case_hardness.py \
  --root "$DATA_ROOT" \
  --iverilog iverilog \
  --vvp vvp \
  --output-csv "$OUT_DIR/hardness_scale120_wsl.csv"

echo "=== FULL TRACE DIVERGENCE RECHECK ==="
python3 rtl_cases/audit_trace_divergence_gate.py \
  --root "$DATA_ROOT" \
  --output-csv "$OUT_DIR/trace_divergence_scale120_wsl.csv"

echo "=== DONE ==="
echo "golden:   $OUT_DIR/golden_recheck_scale120_wsl.csv"
echo "hardness: $OUT_DIR/hardness_scale120_wsl.csv"
echo "traces:   $OUT_DIR/trace_divergence_scale120_wsl.csv"
echo "decoy:    $OUT_DIR/decoy_structure_scale120_wsl.csv"
