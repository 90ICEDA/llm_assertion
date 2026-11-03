#!/usr/bin/env bash
set -uo pipefail

# Usage (inside WSL):
#   cd /mnt/d/AssertionForge-main1
#   bash scripts/validate_scale210_independent_wsl.sh
# Optional:
#   bash scripts/validate_scale210_independent_wsl.sh \
#     rtl_cases_real_scale210_independent outputs/scale210_wsl_validation

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
dataset_arg="${1:-rtl_cases_real_scale210_independent}"
output_arg="${2:-outputs/scale210_wsl_validation}"

if [[ "$dataset_arg" = /* ]]; then
  dataset_root="$dataset_arg"
else
  dataset_root="$repo_root/$dataset_arg"
fi
if [[ "$output_arg" = /* ]]; then
  output_root="$output_arg"
else
  output_root="$repo_root/$output_arg"
fi

manifest="$dataset_root/independent_new_bug_manifest.json"
audit_script="$repo_root/rtl_cases/audit_scale210_independent.py"
mkdir -p "$output_root/logs"

if ! command -v iverilog >/dev/null 2>&1; then
  echo "ERROR: iverilog not found in WSL PATH" >&2
  exit 2
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 not found in WSL PATH" >&2
  exit 2
fi
if [[ ! -f "$manifest" ]]; then
  echo "ERROR: missing manifest: $manifest" >&2
  exit 2
fi

echo "iverilog: $(iverilog -V 2>&1 | head -n 1)"
echo "dataset:  $dataset_root"
echo "output:   $output_root"

# Re-run the mutation-integrity audit before compilation.
python3 "$audit_script" "$dataset_root" \
  >"$output_root/structural_audit.stdout.txt" \
  2>"$output_root/structural_audit.stderr.txt"

case_list="$output_root/cases.tsv"
python3 - "$manifest" >"$case_list" <<'PY'
import json, sys
payload = json.load(open(sys.argv[1], encoding="utf-8"))["cases"]
for c in payload:
    print("\t".join([
        c["name"], c["source_project"], c["source_module"],
        c["bug_class"], c["source_files"][0], c["parent_bug_id"],
    ]))
PY

results="$output_root/iverilog_compile_results.csv"
printf '%s\n' \
  'case_name,parent_bug_id,source_project,source_module,bug_class,correct_compile_ok,buggy_compile_ok,both_compile_ok,correct_log,buggy_log' \
  >"$results"

compile_one() {
  local project="$1"
  local module="$2"
  local rtl_file="$3"
  local log_file="$4"
  local -a cmd

  cmd=(iverilog -g2012 -gno-assertions -DSYNTHESIS -DCOMMON_CELLS_ASSERTS_OFF -tnull -i -Wall -s "$module")
  case "$project" in
    opentitan)
      cmd+=(
        -I "$repo_root/external/opentitan"
        -I "$repo_root/external/opentitan/hw/ip/prim/rtl"
      )
      # The selected FIFO counter imports prim_util_pkg. Other selected prim
      # modules tolerate this package being supplied as an extra compilation unit.
      cmd+=(
        "$repo_root/external/opentitan/hw/ip/prim/rtl/prim_util_pkg.sv"
        "$repo_root/external/opentitan/hw/ip/prim/rtl/prim_count_pkg.sv"
      )
      ;;
    common_cells)
      cmd+=(
        -I "$repo_root/external/common_cells/include"
        -I "$repo_root/external/common_cells/src"
      )
      # Several common_cells modules use `FF/`FFARN macros.
      cmd+=("$repo_root/rtl_cases/iverilog_compat/cc_pkg_iverilog.sv")
      ;;
    verilog_axis)
      cmd+=(-I "$repo_root/external/verilog-axis/rtl")
      ;;
    *)
      echo "unknown source_project=$project" >"$log_file"
      return 2
      ;;
  esac
  cmd+=("$rtl_file")
  printf 'COMMAND:' >"$log_file"
  printf ' %q' "${cmd[@]}" >>"$log_file"
  printf '\n\n' >>"$log_file"
  "${cmd[@]}" >>"$log_file" 2>&1
}

total=0
passed=0
while IFS=$'\t' read -r case_name project module bug_class source_file parent_bug_id; do
  total=$((total + 1))
  case_dir="$dataset_root/$case_name"
  correct_log="$output_root/logs/${case_name}.correct.log"
  buggy_log="$output_root/logs/${case_name}.buggy.log"

  correct_ok=false
  buggy_ok=false
  if compile_one "$project" "$module" "$case_dir/correct.v" "$correct_log"; then
    correct_ok=true
  fi
  if compile_one "$project" "$module" "$case_dir/buggy.v" "$buggy_log"; then
    buggy_ok=true
  fi
  both_ok=false
  if [[ "$correct_ok" == true && "$buggy_ok" == true ]]; then
    both_ok=true
    passed=$((passed + 1))
  fi
  printf '%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n' \
    "$case_name" "$parent_bug_id" "$project" "$module" "$bug_class" \
    "$correct_ok" "$buggy_ok" "$both_ok" \
    "logs/${case_name}.correct.log" "logs/${case_name}.buggy.log" \
    >>"$results"
  printf '[%02d/%02d] %-5s %s\n' "$total" 50 "$both_ok" "$case_name"
done <"$case_list"

python3 - "$results" "$output_root/validation_summary.json" <<'PY'
import csv, json, sys
rows = list(csv.DictReader(open(sys.argv[1], encoding="utf-8-sig")))
summary = {
    "case_count": len(rows),
    "correct_compile_pass_count": sum(r["correct_compile_ok"] == "true" for r in rows),
    "buggy_compile_pass_count": sum(r["buggy_compile_ok"] == "true" for r in rows),
    "both_compile_pass_count": sum(r["both_compile_ok"] == "true" for r in rows),
    "both_compile_fail_count": sum(r["both_compile_ok"] != "true" for r in rows),
    "all_both_compile_ok": all(r["both_compile_ok"] == "true" for r in rows),
    "note": "This is an Icarus compile/elaboration gate, not seen/held-out/decoy semantic validation.",
}
json.dump(summary, open(sys.argv[2], "w", encoding="utf-8"), indent=2)
print(json.dumps(summary, indent=2))
PY

echo "CSV:     $results"
echo "Summary: $output_root/validation_summary.json"
echo "Logs:    $output_root/logs"

if [[ "$passed" -ne "$total" ]]; then
  exit 1
fi
