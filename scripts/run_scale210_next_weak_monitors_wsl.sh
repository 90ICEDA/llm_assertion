#!/usr/bin/env bash
set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
root="$repo/rtl_cases_real_scale210_independent_next"
out="$repo/outputs/scale210_next_weak_monitor_validation"
semantic="$repo/outputs/scale210_next_semantic_validation/semantic_validation_summary.json"
args=(--root "$root" --output "$out" --semantic-summary "$semantic")
if [[ $# -gt 0 ]]; then
  if [[ "$1" == "--resume" ]]; then args+=(--resume); else args+=(--case "$1"); fi
fi
python3 "$repo/src/sync_next_candidate_manifest.py" --root "$root"
python3 "$repo/src/audit_scale210_weak_assertions.py" --root "$root"
python3 "$repo/src/run_scale210_weak_monitors.py" "${args[@]}"
python3 "$repo/rtl_cases/check_independent_case_hardness.py" "$root"
echo "hardness summary: $root/hardness_admission_summary.json"
echo "monitor logs:     $out/logs"
