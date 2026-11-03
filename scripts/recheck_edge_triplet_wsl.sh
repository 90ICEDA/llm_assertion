#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="/mnt/d/AssertionForge-main1"
ROOT="$REPO_ROOT/rtl_cases_real_scale120"
OUT="$REPO_ROOT/outputs/wsl_scale120_edge_triplet"
MANIFEST="$ROOT/case_manifest.json"

mkdir -p "$OUT"
cd "$REPO_ROOT"

echo "=== CURRENT MANIFEST ASSERTIONS ==="
python3 - <<'PY'
import json
from pathlib import Path

manifest = Path("/mnt/d/AssertionForge-main1/rtl_cases_real_scale120/case_manifest.json")
cases = {
    "case114_prim_edge_negedge_misdecoded",
    "case115_prim_edge_both_edges_collapsed",
    "case133_prim_edge_negedge_missing",
}
data = json.loads(manifest.read_text(encoding="utf-8"))["cases"]
for case in data:
    if case["name"] in cases:
        print(case["name"])
        print("  " + case["golden_sva"]["sva"])
PY

CASES=(
  case114_prim_edge_negedge_misdecoded
  case115_prim_edge_both_edges_collapsed
  case133_prim_edge_negedge_missing
)

for c in "${CASES[@]}"; do
  echo "=== GOLDEN: $c ==="
  python3 rtl_cases/check_golden_sva.py \
    --root "$ROOT" \
    --case "$c" \
    --iverilog iverilog \
    --vvp vvp \
    --output-csv "$OUT/${c}_golden.csv"
done

echo "=== DONE ==="
echo "outputs in: $OUT"
