#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="/mnt/d/AssertionForge-main1"
DATA_ROOT="$REPO_ROOT/rtl_cases_real_scale160_temporal_boosted"
OUT_DIR="$REPO_ROOT/outputs/scale160_temporal_boost_subset_wsl"
SUMMARY_JSON="$DATA_ROOT/temporal_variant_expansion_summary.json"

cd "$REPO_ROOT"
mkdir -p "$OUT_DIR"

mapfile -t CASES < <(python3 rtl_cases/print_temporal_boost_cases.py --summary-json "$SUMMARY_JSON" --format plain)

echo "=== SCALE160 TEMPORAL BOOST SUBSET (WSL SIM) ==="
echo "cases: ${#CASES[@]}"

CASE_ARGS=()
for case_name in "${CASES[@]}"; do
  CASE_ARGS+=(--case "$case_name")
done

echo "=== PREPARE PROMPT ASSETS ==="
python3 rtl_cases/prepare_prompt_assets.py --root "$DATA_ROOT"

echo "=== REGENERATE WAVEFORMS (40 NEW CASES ONLY) ==="
python3 rtl_cases/regenerate_waveforms_for_root.py \
  --root "$DATA_ROOT" \
  --iverilog iverilog \
  --vvp vvp \
  --converter "$REPO_ROOT/rtl_cases/vcd_to_csv.py" \
  "${CASE_ARGS[@]}"

echo "=== GOLDEN RECHECK (SIM-ONLY CACHELESS) ==="
python3 src/recheck_golden_wsl.py \
  --root "$DATA_ROOT" \
  --iverilog iverilog \
  --vvp vvp \
  --jasper-mode off \
  --output-csv "$OUT_DIR/golden_recheck_scale160_temporal_boost_subset_sim.csv" \
  "${CASE_ARGS[@]}"

echo "=== HARDNESS RECHECK (SIM-ONLY CACHELESS) ==="
python3 rtl_cases/check_case_hardness.py \
  --root "$DATA_ROOT" \
  --iverilog iverilog \
  --vvp vvp \
  --jasper-mode off \
  --output-csv "$OUT_DIR/hardness_scale160_temporal_boost_subset_sim.csv" \
  "${CASE_ARGS[@]}"

echo "=== TRACE DIVERGENCE RECHECK ==="
python3 rtl_cases/audit_trace_divergence_gate.py \
  --root "$DATA_ROOT" \
  --output-csv "$OUT_DIR/trace_divergence_scale160_temporal_boost_subset.csv" \
  "${CASE_ARGS[@]}"

echo "=== DONE ==="
echo "golden_sim: $OUT_DIR/golden_recheck_scale160_temporal_boost_subset_sim.csv"
echo "hardness:   $OUT_DIR/hardness_scale160_temporal_boost_subset_sim.csv"
echo "traces:     $OUT_DIR/trace_divergence_scale160_temporal_boost_subset.csv"
