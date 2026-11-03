#!/usr/bin/env bash
set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
root="$repo/rtl_cases_real_scale210_independent_next"
out="$repo/outputs/opentitan_hard_batch1_weak_monitor_validation"
args=(--root "$root" --output "$out")
[[ $# -eq 0 ]] || args+=("$@")
python3 "$repo/src/run_scale210_weak_monitors.py" "${args[@]}"
python3 "$repo/rtl_cases/check_independent_case_hardness.py" "$root" --monitor-results "$out/weak_monitor_results.csv"

