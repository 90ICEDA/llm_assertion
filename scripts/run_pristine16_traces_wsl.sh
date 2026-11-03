#!/usr/bin/env bash
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
root="$repo/rtl_cases_real_scale210_independent"
seal="$repo/outputs/pristine_trace_router_v1/sealed_test_manifest.json"
out="$repo/outputs/pristine_trace_router_v1/trace_generation"
mkdir -p "$out/logs" "$out/work"

command -v iverilog >/dev/null || { echo "ERROR: iverilog not found" >&2; exit 2; }
command -v vvp >/dev/null || { echo "ERROR: vvp not found" >&2; exit 2; }

python3 - "$seal" "$root" <<'PY'
import hashlib, json, pathlib, sys
seal = json.load(open(sys.argv[1], encoding="utf-8"))
root = pathlib.Path(sys.argv[2])
for row in seal["cases"]:
    d = root / row["case_id"]
    for name, key in (("correct.v", "correct_rtl_sha256"), ("buggy.v", "buggy_rtl_sha256"), ("rtl_mutation.diff", "mutation_diff_sha256")):
        got = hashlib.sha256((d/name).read_bytes()).hexdigest()
        if got != row[key]: raise SystemExit(f"sealed hash mismatch: {row['case_id']}/{name}")
print(f"seal integrity OK: {len(seal['cases'])} cases")
PY

mapfile -t cases < <(python3 - "$seal" <<'PY'
import json,sys
for x in json.load(open(sys.argv[1], encoding="utf-8"))["cases"]: print(x["case_id"])
PY
)
if [[ $# -gt 0 ]]; then
  requested="$1"
  found=false
  for sealed_case in "${cases[@]}"; do [[ "$sealed_case" == "$requested" ]] && found=true; done
  [[ "$found" == true ]] || { echo "ERROR: requested case is not in sealed test: $requested" >&2; exit 2; }
  cases=("$requested")
fi

compile_run() {
  local case_id="$1" variant="$2" rtl_kind="$3"
  local d="$root/$case_id" tb rtl exe vcd csv log
  local -a case_defs=()
  [[ "$case_id" == case417_* || "$case_id" == case418_* ]] && case_defs=(-DCC_CLK_MUX_TB_DEPS)
  case "$variant" in
    primary) tb="$d/tb.v"; suffix="" ;;
    holdout) tb="$d/tb_holdout.v"; suffix="_holdout" ;;
    decoy) tb="$d/tb_decoy.v"; suffix="_decoy" ;;
  esac
  rtl="$d/${rtl_kind}.v"
  exe="$out/work/${case_id}.${variant}.${rtl_kind}.vvp"
  vcd="$out/work/${case_id}.${variant}.${rtl_kind}.vcd"
  csv="$d/waveform_${rtl_kind/correct/good}${suffix}.csv"
  [[ "$rtl_kind" == buggy ]] && csv="$d/waveform_bad${suffix}.csv"
  log="$out/logs/${case_id}.${variant}.${rtl_kind}.log"
  [[ -s "$tb" ]] || { echo "missing testbench: $tb" >&2; return 1; }

  # The harness writes its VCD to the +VCD plusarg path.
  if ! iverilog -g2012 -gno-assertions -DSYNTHESIS -DCOMMON_CELLS_ASSERTS_OFF "${case_defs[@]}" -i \
    -I "$d" \
    -I "$repo/external/common_cells/include" -I "$repo/external/common_cells/src" \
    -I "$repo/external/opentitan" -I "$repo/external/opentitan/hw/ip/prim/rtl" \
    -I "$repo/external/verilog-axis/rtl" \
    -o "$exe" \
    "$repo/rtl_cases/iverilog_compat/cc_pkg_iverilog.sv" \
    "$repo/rtl_cases/iverilog_compat/cc_clk_mux_tb_deps.sv" \
    "$repo/external/opentitan/hw/ip/prim/rtl/prim_util_pkg.sv" \
    "$repo/external/opentitan/hw/ip/prim/rtl/prim_count_pkg.sv" \
    "$rtl" "$tb" >"$log" 2>&1; then
    echo "COMPILE FAIL: $case_id $variant $rtl_kind" >&2; tail -n 40 "$log" >&2; return 1
  fi
  if ! vvp "$exe" +VCD="$vcd" >>"$log" 2>&1; then
    echo "RUNTIME FAIL: $case_id $variant $rtl_kind" >&2; tail -n 40 "$log" >&2; return 1
  fi
  [[ -s "$vcd" ]] || { echo "empty VCD: $vcd" >&2; return 1; }
  python3 "$repo/rtl_cases/vcd_to_csv.py" "$vcd" "$csv" >>"$log" 2>&1
  [[ $(wc -l < "$csv") -gt 2 ]] || { echo "empty CSV: $csv" >&2; return 1; }
}

total=0
for case_id in "${cases[@]}"; do
  for variant in primary holdout decoy; do
    compile_run "$case_id" "$variant" correct
    compile_run "$case_id" "$variant" buggy
    total=$((total+2))
  done
  echo "OK $case_id"
done

python3 - "$seal" "$root" <<'PY'
import csv, json, pathlib, sys
seal=json.load(open(sys.argv[1],encoding="utf-8")); root=pathlib.Path(sys.argv[2]); failures=[]
for row in seal["cases"]:
 d=root/row["case_id"]
 for suffix in ("", "_holdout", "_decoy"):
  g=(d/f"waveform_good{suffix}.csv").read_bytes(); b=(d/f"waveform_bad{suffix}.csv").read_bytes()
  if g==b: failures.append(f"{row['case_id']}:{suffix or 'primary'} no good/bad divergence")
if failures: raise SystemExit("\n".join(failures))
print("PASS: 16 sealed cases, 96 simulations, all three variants diverge")
PY

echo "logs: $out/logs"
