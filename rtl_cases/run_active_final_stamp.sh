#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

ROOT_REL="${ROOT_REL:-rtl_cases_real_active}"
DATA_ROOT="${DATA_ROOT:-$REPO_ROOT/$ROOT_REL}"

IVERILOG_BIN="${IVERILOG_BIN:-iverilog}"
VVP_BIN="${VVP_BIN:-vvp}"
STAMP_TAG="${STAMP_TAG:-final_$(date +%Y%m%d_%H%M%S)}"

GOLDEN_CSV="$DATA_ROOT/golden_sva_check_report_${STAMP_TAG}.csv"
HARDNESS_CSV="$DATA_ROOT/hardness_check_report_${STAMP_TAG}.csv"
DIVERGENCE_CSV="$DATA_ROOT/trace_divergence_gate_report_${STAMP_TAG}.csv"
ANTECEDENT_CSV="$DATA_ROOT/antecedent_coverage_${STAMP_TAG}.csv"

echo "[INFO] Repo root: $REPO_ROOT"
echo "[INFO] Data root: $DATA_ROOT"
echo "[INFO] IVerilog: $IVERILOG_BIN"
echo "[INFO] VVP: $VVP_BIN"
echo "[INFO] Stamp tag: $STAMP_TAG"

if [[ ! -d "$DATA_ROOT" ]]; then
  echo "[FATAL] Dataset root does not exist: $DATA_ROOT" >&2
  exit 1
fi

python3 "$REPO_ROOT/rtl_cases/check_golden_sva.py" \
  --root "$DATA_ROOT" \
  --output-csv "$GOLDEN_CSV" \
  --iverilog "$IVERILOG_BIN" \
  --vvp "$VVP_BIN"

if python3 "$REPO_ROOT/rtl_cases/audit_trace_divergence_gate.py" \
  --root "$DATA_ROOT" \
  --output-csv "$DIVERGENCE_CSV"; then
  DIVERGENCE_RC=0
else
  DIVERGENCE_RC=$?
  echo "[WARN] Divergence gate reported non-green status; continuing to write full stamp artifacts."
fi

python3 "$REPO_ROOT/rtl_cases/check_case_hardness.py" \
  --root "$DATA_ROOT" \
  --output-csv "$HARDNESS_CSV" \
  --iverilog "$IVERILOG_BIN" \
  --vvp "$VVP_BIN"

python3 - "$GOLDEN_CSV" "$ANTECEDENT_CSV" <<'PY'
import csv
import sys
from pathlib import Path

golden_csv = Path(sys.argv[1])
ante_csv = Path(sys.argv[2])

with golden_csv.open("r", encoding="utf-8", newline="") as f:
    rows = list(csv.DictReader(f))

fields = [
    "case_name",
    "antecedent_triggered",
    "buggy_antecedent_hits",
    "antecedent_coverage_ok",
    "golden_ok",
    "failure_reason",
]

with ante_csv.open("w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fields)
    writer.writeheader()
    for row in rows:
        hits = int(row.get("buggy_antecedent_hits", "0") or "0")
        writer.writerow(
            {
                "case_name": row.get("case_name", ""),
                "antecedent_triggered": row.get("antecedent_triggered", ""),
                "buggy_antecedent_hits": hits,
                "antecedent_coverage_ok": str(hits > 0),
                "golden_ok": row.get("golden_ok", ""),
                "failure_reason": row.get("failure_reason", ""),
            }
        )
PY

cp "$GOLDEN_CSV" "$DATA_ROOT/golden_sva_check_report.csv"
cp "$HARDNESS_CSV" "$DATA_ROOT/hardness_check_report_latest.csv"
cp "$DIVERGENCE_CSV" "$DATA_ROOT/trace_divergence_gate_report_latest.csv"

echo "[DONE] Golden report: $GOLDEN_CSV"
echo "[DONE] Divergence report: $DIVERGENCE_CSV"
echo "[DONE] Hardness report: $HARDNESS_CSV"
echo "[DONE] Antecedent report: $ANTECEDENT_CSV"
echo "[DONE] Refreshed canonical files under $DATA_ROOT"
exit $DIVERGENCE_RC
