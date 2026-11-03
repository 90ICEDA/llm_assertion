#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: $0 /path/to/jaspergold"
  exit 2
fi

JASPER_BIN="$1"
REPO_ROOT="${REPO_ROOT:-$(pwd)}"
DATA_ROOT="${DATA_ROOT:-$REPO_ROOT/rtl_cases_real_scale160_temporal_boosted}"
OUT_DIR="${OUT_DIR:-$REPO_ROOT/outputs/scale160_temporal_boost_subset_jasper}"
SUMMARY_JSON="$DATA_ROOT/temporal_variant_expansion_summary.json"

mkdir -p "$OUT_DIR" "$OUT_DIR/reports"

mapfile -t CASES < <(python3 rtl_cases/print_temporal_boost_cases.py --summary-json "$SUMMARY_JSON" --format plain)

echo "=== SCALE160 TEMPORAL BOOST SUBSET (JASPER) ==="
echo "cases: ${#CASES[@]}"

CASE_ARGS=()
for case_name in "${CASES[@]}"; do
  CASE_ARGS+=(--case "$case_name")
done

python3 src/run_jasper_reachability_batch.py \
  --root "$DATA_ROOT" \
  --jasper-binary "$JASPER_BIN" \
  --report-dir "$OUT_DIR/reports" \
  --output-csv "$OUT_DIR/jasper_reachability_scale160_temporal_boost_subset.csv" \
  "${CASE_ARGS[@]}"

echo "=== DONE ==="
echo "jasper_csv: $OUT_DIR/jasper_reachability_scale160_temporal_boost_subset.csv"
echo "reports:    $OUT_DIR/reports"
