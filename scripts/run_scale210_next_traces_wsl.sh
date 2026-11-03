#!/usr/bin/env bash
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
root="$repo/rtl_cases_real_scale210_independent_next"
out="$repo/outputs/scale210_next_semantic_validation"
compile_timeout="${AF_COMPILE_TIMEOUT_SEC:-45}"
sim_timeout="${AF_SIM_TIMEOUT_SEC:-20}"
mkdir -p "$out/logs" "$out/work"

command -v iverilog >/dev/null || { echo "ERROR: iverilog not found" >&2; exit 2; }
command -v vvp >/dev/null || { echo "ERROR: vvp not found" >&2; exit 2; }
python3 "$repo/src/sync_next_candidate_manifest.py" --root "$root"
mapfile -t cases < <(find "$root" -mindepth 1 -maxdepth 1 -type d -regextype posix-extended -regex '.*/case[0-9]+_.*' -printf '%f\n' | sort)
if [[ $# -gt 0 ]]; then
  cases=("$@")
  for requested_case in "${cases[@]}"; do
    [[ -d "$root/$requested_case" ]] || { echo "ERROR: unknown case $requested_case" >&2; exit 2; }
  done
fi

compile_run() {
  local case_id="$1" variant="$2" rtl_kind="$3" d tb suffix rtl exe vcd csv log
  local -a dump_source=()
  d="$root/$case_id"
  case "$variant" in
    primary) tb="$d/tb.v"; suffix="" ;;
    holdout) tb="$d/tb_holdout.v"; suffix="_holdout" ;;
    decoy) tb="$d/tb_decoy.v"; suffix="_decoy" ;;
  esac
  rtl="$d/${rtl_kind}.v"; exe="$out/work/${case_id}.${variant}.${rtl_kind}.vvp"
  vcd="$out/work/${case_id}.${variant}.${rtl_kind}.vcd"
  csv="$d/waveform_good${suffix}.csv"; [[ "$rtl_kind" == buggy ]] && csv="$d/waveform_bad${suffix}.csv"
  log="$out/logs/${case_id}.${variant}.${rtl_kind}.log"
  if ! grep -q '\$dumpfile' "$tb"; then
    local dumper="$out/work/${case_id}.${variant}.vcd_dumper.sv"
    cat >"$dumper" <<'SV'
module assertionforge_vcd_dumper;
  string vcd;
  initial begin
    if (!$value$plusargs("VCD=%s", vcd)) vcd = "trace.vcd";
    $dumpfile(vcd);
    $dumpvars(0, tb);
  end
endmodule
SV
    dump_source=("$dumper")
  fi
  if ! timeout "${compile_timeout}s" iverilog -g2012 -gno-assertions -DSYNTHESIS -I "$d" -o "$exe" "$rtl" "$tb" "${dump_source[@]}" >"$log" 2>&1; then
    echo "COMPILE FAIL: $case_id $variant $rtl_kind" >&2; tail -n 30 "$log" >&2; return 1
  fi
  # Some legacy harnesses gate dumping with $test$plusargs("VCD") but still
  # write a fixed wave.vcd.  Remove only these exact generated files so a
  # failed run can never reuse a stale waveform.
  rm -f -- "$vcd" "$repo/wave.vcd"
  if ! timeout "${sim_timeout}s" vvp "$exe" +VCD="$vcd" >>"$log" 2>&1; then
    echo "RUNTIME FAIL: $case_id $variant $rtl_kind" >&2; tail -n 30 "$log" >&2; return 1
  fi
  if [[ ! -s "$vcd" && -s "$repo/wave.vcd" ]]; then
    mv -- "$repo/wave.vcd" "$vcd"
  fi
  if [[ ! -s "$vcd" ]]; then
    echo "EMPTY VCD: $case_id $variant $rtl_kind" >&2; tail -n 30 "$log" >&2; return 1
  fi
  if ! python3 "$repo/rtl_cases/vcd_to_csv.py" "$vcd" "$csv" >>"$log" 2>&1; then
    echo "CSV CONVERSION FAIL: $case_id $variant $rtl_kind" >&2; tail -n 30 "$log" >&2; return 1
  fi
  if [[ $(wc -l < "$csv") -le 2 ]]; then
    echo "EMPTY CSV: $case_id $variant $rtl_kind" >&2; return 1
  fi
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
    g=d/f"waveform_good{suffix}.csv"; b=d/f"waveform_bad{suffix}.csv"
    if not g.is_file() or not b.is_file() or g.read_bytes()==b.read_bytes():
        raise SystemExit(f"NO DIVERGENCE: {d.name} {suffix or 'primary'}")
PY
  passed=$((passed+1)); echo "OK $case_id"
done

python3 - "$root" "$out/semantic_validation_summary.json" <<'PY'
import hashlib,json,pathlib,sys
root=pathlib.Path(sys.argv[1]); out=pathlib.Path(sys.argv[2]); rows=[]
for d in sorted(p for p in root.iterdir() if p.is_dir() and __import__("re").match(r"^case\d+_", p.name)):
  variants={}
  for label,suffix in (("primary",""),("heldout","_holdout"),("decoy","_decoy")):
    g=d/f"waveform_good{suffix}.csv"; b=d/f"waveform_bad{suffix}.csv"
    variants[label]={"present":g.is_file() and b.is_file(),"diverges":g.is_file() and b.is_file() and g.read_bytes()!=b.read_bytes(),"good_sha256":hashlib.sha256(g.read_bytes()).hexdigest() if g.is_file() else None,"bad_sha256":hashlib.sha256(b.read_bytes()).hexdigest() if b.is_file() else None}
  rows.append({"case_id":d.name,"variants":variants,"all_three_diverge":all(v["diverges"] for v in variants.values())})
p={"schema_version":1,"case_count":len(rows),"all_three_diverge_count":sum(r["all_three_diverge"] for r in rows),"all_pass":all(r["all_three_diverge"] for r in rows),"cases":rows}
out.write_text(json.dumps(p,indent=2)+"\n",encoding="utf-8"); print(json.dumps({k:p[k] for k in ("case_count","all_three_diverge_count","all_pass")},indent=2))
PY
echo "PASS: $passed requested cases; results: $out/semantic_validation_summary.json"
