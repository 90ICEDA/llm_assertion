#!/usr/bin/env bash
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
root="$repo/rtl_cases_real_scale210_independent"
out="$repo/outputs/scale210_semantic_validation"
mkdir -p "$out/logs" "$out/work"

command -v iverilog >/dev/null || { echo "ERROR: iverilog not found" >&2; exit 2; }
command -v vvp >/dev/null || { echo "ERROR: vvp not found" >&2; exit 2; }

mapfile -t cases < <(find "$root" -mindepth 1 -maxdepth 1 -type d -name 'case4*' -printf '%f\n' | sort)
if [[ $# -gt 0 ]]; then
  requested="$1"
  [[ -d "$root/$requested" ]] || { echo "ERROR: unknown case $requested" >&2; exit 2; }
  cases=("$requested")
fi

compile_run() {
  local case_id="$1" variant="$2" rtl_kind="$3"
  local d="$root/$case_id" tb suffix rtl exe vcd csv log
  local -a case_defs=()
  [[ "$case_id" == case417_* || "$case_id" == case418_* || "$case_id" == case419_* || "$case_id" == case420_* ]] && case_defs=(-DCC_CLK_MUX_TB_DEPS)
  case "$variant" in
    primary) tb="$d/tb.v"; suffix="" ;;
    holdout) tb="$d/tb_holdout.v"; suffix="_holdout" ;;
    decoy) tb="$d/tb_decoy.v"; suffix="_decoy" ;;
  esac
  rtl="$d/${rtl_kind}.v"
  exe="$out/work/${case_id}.${variant}.${rtl_kind}.vvp"
  vcd="$out/work/${case_id}.${variant}.${rtl_kind}.vcd"
  csv="$d/waveform_good${suffix}.csv"
  [[ "$rtl_kind" == buggy ]] && csv="$d/waveform_bad${suffix}.csv"
  log="$out/logs/${case_id}.${variant}.${rtl_kind}.log"
  [[ -s "$tb" ]] || { echo "MISSING TB: $case_id $variant" >&2; return 1; }
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
    echo "COMPILE FAIL: $case_id $variant $rtl_kind" >&2; tail -n 30 "$log" >&2; return 1
  fi
  if ! vvp "$exe" +VCD="$vcd" >>"$log" 2>&1; then
    echo "RUNTIME FAIL: $case_id $variant $rtl_kind" >&2; tail -n 30 "$log" >&2; return 1
  fi
  [[ -s "$vcd" ]] || { echo "EMPTY VCD: $case_id $variant $rtl_kind" >&2; return 1; }
  python3 "$repo/rtl_cases/vcd_to_csv.py" "$vcd" "$csv" >>"$log" 2>&1
  [[ $(wc -l < "$csv") -gt 2 ]] || { echo "EMPTY CSV: $case_id $variant $rtl_kind" >&2; return 1; }
}

passed=0
for case_id in "${cases[@]}"; do
  for variant in primary holdout decoy; do
    compile_run "$case_id" "$variant" correct
    compile_run "$case_id" "$variant" buggy
  done
  python3 - "$root/$case_id" <<'PY'
import pathlib, sys
d=pathlib.Path(sys.argv[1])
for suffix in ("", "_holdout", "_decoy"):
    good=d/f"waveform_good{suffix}.csv"; bad=d/f"waveform_bad{suffix}.csv"
    if good.read_bytes()==bad.read_bytes():
        raise SystemExit(f"NO DIVERGENCE: {d.name} {suffix or 'primary'}")
PY
  passed=$((passed+1))
  echo "OK $case_id"
done

python3 - "$root" "$out/semantic_validation_summary.json" <<'PY'
import hashlib, json, pathlib, sys
root=pathlib.Path(sys.argv[1]); output=pathlib.Path(sys.argv[2]); rows=[]
for d in sorted(root.glob("case4*")):
    variants={}
    for label,suffix in (("primary",""),("heldout","_holdout"),("decoy","_decoy")):
        g=d/f"waveform_good{suffix}.csv"; b=d/f"waveform_bad{suffix}.csv"
        variants[label]={"present":g.is_file() and b.is_file(),"diverges":g.is_file() and b.is_file() and g.read_bytes()!=b.read_bytes(),
            "good_sha256":hashlib.sha256(g.read_bytes()).hexdigest() if g.is_file() else None,
            "bad_sha256":hashlib.sha256(b.read_bytes()).hexdigest() if b.is_file() else None}
    rows.append({"case_id":d.name,"variants":variants,"all_three_diverge":all(x["diverges"] for x in variants.values())})
payload={"schema_version":1,"case_count":len(rows),"all_three_diverge_count":sum(x["all_three_diverge"] for x in rows),"all_pass":all(x["all_three_diverge"] for x in rows),"cases":rows}
output.write_text(json.dumps(payload,indent=2),encoding="utf-8")
print(json.dumps({k:payload[k] for k in ("case_count","all_three_diverge_count","all_pass")},indent=2))
PY

echo "PASS: $passed requested cases; results: $out/semantic_validation_summary.json"
