#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
case_root="$repo_root/rtl_cases_real_scale210_independent_next"
cases=()

case_traces_current() {
  local dir="$1" suffix tb good bad
  for suffix in "" "_holdout" "_decoy"; do
    case "$suffix" in
      "") tb="$dir/tb.v" ;;
      "_holdout") tb="$dir/tb_holdout.v" ;;
      "_decoy") tb="$dir/tb_decoy.v" ;;
    esac
    good="$dir/waveform_good${suffix}.csv"
    bad="$dir/waveform_bad${suffix}.csv"
    [[ -s "$good" && -s "$bad" ]] || return 1
    cmp -s "$good" "$bad" && return 1
    for input in "$dir/correct.v" "$dir/buggy.v" "$dir/tb.v" "$tb"; do
      [[ "$good" -nt "$input" && "$bad" -nt "$input" ]] || return 1
    done
  done
}

for number in $(seq 476 510); do
  matches=("$case_root/case${number}_"*)
  if [[ ${#matches[@]} -ne 1 || ! -d "${matches[0]}" ]]; then
    echo "ERROR: expected exactly one directory for case${number}" >&2
    exit 2
  fi
  if ! case_traces_current "${matches[0]}"; then
    cases+=("$(basename "${matches[0]}")")
  fi
done

echo "Validating ${#cases[@]} pending/stale cases (case476-case510)"
if [[ ${#cases[@]} -gt 0 ]]; then
  bash "$repo_root/scripts/run_scale210_next_traces_wsl.sh" "${cases[@]}"
else
  echo "All case476-case510 trace pairs are current and divergent"
fi
bash "$repo_root/scripts/run_scale210_next_weak_monitors_wsl.sh" --resume
