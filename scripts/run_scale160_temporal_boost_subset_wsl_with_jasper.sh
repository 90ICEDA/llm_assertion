#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: $0 /mnt/d/AssertionForge-main1/outputs/scale160_temporal_boost_subset_jasper/jasper_reachability_scale160_temporal_boost_subset.csv"
  exit 2
fi

JASPER_RESULTS_CSV="$1"
REPO_ROOT="/mnt/d/AssertionForge-main1"
DATA_ROOT="$REPO_ROOT/rtl_cases_real_scale160_temporal_boosted"
OUT_DIR="$REPO_ROOT/outputs/scale160_temporal_boost_subset_wsl_formal"
SUMMARY_JSON="$DATA_ROOT/temporal_variant_expansion_summary.json"

cd "$REPO_ROOT"
mkdir -p "$OUT_DIR"

mapfile -t CASES < <(python3 rtl_cases/print_temporal_boost_cases.py --summary-json "$SUMMARY_JSON" --format plain)

echo "=== SCALE160 TEMPORAL BOOST SUBSET (WSL + JASPER CACHE) ==="
echo "cases: ${#CASES[@]}"
echo "jasper cache: $JASPER_RESULTS_CSV"

CASE_ARGS=()
for case_name in "${CASES[@]}"; do
  CASE_ARGS+=(--case "$case_name")
done

python3 src/recheck_golden_wsl.py \
  --root "$DATA_ROOT" \
  --iverilog iverilog \
  --vvp vvp \
  --jasper-results-csv "$JASPER_RESULTS_CSV" \
  --jasper-mode require \
  --output-csv "$OUT_DIR/golden_recheck_scale160_temporal_boost_subset_formal.csv" \
  "${CASE_ARGS[@]}"

python3 rtl_cases/check_case_hardness.py \
  --root "$DATA_ROOT" \
  --iverilog iverilog \
  --vvp vvp \
  --jasper-results-csv "$JASPER_RESULTS_CSV" \
  --jasper-mode require \
  --output-csv "$OUT_DIR/hardness_scale160_temporal_boost_subset_formal.csv" \
  "${CASE_ARGS[@]}"

python3 rtl_cases/audit_trace_divergence_gate.py \
  --root "$DATA_ROOT" \
  --output-csv "$OUT_DIR/trace_divergence_scale160_temporal_boost_subset_formal.csv" \
  "${CASE_ARGS[@]}"

echo "=== DONE ==="
echo "golden_formal: $OUT_DIR/golden_recheck_scale160_temporal_boost_subset_formal.csv"
echo "hardness:      $OUT_DIR/hardness_scale160_temporal_boost_subset_formal.csv"
echo "traces:        $OUT_DIR/trace_divergence_scale160_temporal_boost_subset_formal.csv"
