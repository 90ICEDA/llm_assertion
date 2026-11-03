#!/usr/bin/env bash
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
root="$repo/rtl_cases_real_scale210_independent"
out="$repo/outputs/scale210_weak_monitor_validation"

command -v python3 >/dev/null || { echo "ERROR: python3 not found" >&2; exit 2; }
command -v iverilog >/dev/null || { echo "ERROR: iverilog not found" >&2; exit 2; }
command -v vvp >/dev/null || { echo "ERROR: vvp not found" >&2; exit 2; }

args=(--root "$root" --output "$out")
if [[ $# -gt 0 ]]; then
  if [[ "$1" == "--resume" ]]; then
    args+=(--resume)
  else
    args+=(--case "$1")
  fi
fi

python3 "$repo/src/audit_scale210_weak_assertions.py"
python3 "$repo/src/run_scale210_weak_monitors.py" "${args[@]}"

# The admission checker is deliberately last: no case can be admitted from
# unevaluated candidate metadata alone.
python3 "$repo/rtl_cases/check_independent_case_hardness.py" "$root"

echo "hardness summary: $root/hardness_admission_summary.json"
echo "monitor logs:     $out/logs"
