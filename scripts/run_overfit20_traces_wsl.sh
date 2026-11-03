#!/usr/bin/env bash
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
root="$repo/rtl_cases_overfit_bait20"
out="$repo/outputs/overfit_bait20_semantic_validation"
work="$out/work"
mkdir -p "$work"

python3 - "$root" <<'PY'
import json, pathlib, sys
r=pathlib.Path(sys.argv[1]); m=json.loads((r/'overfit20_manifest.json').read_text())
assert len(m['cases']) == 20
assert all(x['heldout_count'] >= 3 for x in m['cases'])
assert all(len({x['primary_bait_value'], *x['heldout_bait_values']}) == 4 for x in m['cases'])
print('contract OK: 20 cases, three held-outs each, four distinct legal bait values')
PY

pass=0
total=0
while IFS= read -r case_dir; do
  case_id="$(basename "$case_dir")"
  for index in 0 1 2 3; do
    if [[ "$index" == 0 ]]; then tb="$case_dir/tb.v"; tag="primary"; else tb="$case_dir/tb_holdout_${index}.v"; tag="heldout_${index}"; fi
    variant_dir="$work/$case_id/$tag"
    mkdir -p "$variant_dir/good" "$variant_dir/bad"
    for kind in good bad; do
      rtl="$case_dir/correct.v"; [[ "$kind" == bad ]] && rtl="$case_dir/buggy.v"
      build="$variant_dir/$kind"
      iverilog -g2012 -I "$case_dir" -o "$build/simv" "$rtl" "$tb" >"$build/compile.log" 2>&1
      (cd "$build" && timeout 20s vvp ./simv >sim.log 2>&1)
      vcd="$(find "$build" -maxdepth 1 -type f -name '*.vcd' -print -quit)"
      [[ -n "$vcd" && -s "$vcd" ]] || { echo "EMPTY VCD: $case_id $tag $kind"; exit 1; }
    done
    good_vcd="$(find "$variant_dir/good" -maxdepth 1 -type f -name '*.vcd' -print -quit)"
    bad_vcd="$(find "$variant_dir/bad" -maxdepth 1 -type f -name '*.vcd' -print -quit)"
    if python3 - "$good_vcd" "$bad_vcd" <<'PY'
import re,sys
def changes(path):
    return [line.strip() for line in open(path,errors='replace') if re.match(r'^(?:#|[01xXzZ]|[bBrR])',line)]
raise SystemExit(0 if changes(sys.argv[1]) == changes(sys.argv[2]) else 1)
PY
    then echo "NO DIVERGENCE: $case_id $tag"; exit 1; fi
    total=$((total+2)); pass=$((pass+2))
  done
  echo "OK $case_id"
done < <(find "$root" -mindepth 1 -maxdepth 1 -type d -name 'overfit*' | sort)

python3 - "$out/semantic_validation_summary.json" "$pass" "$total" <<'PY'
import json,pathlib,sys
p=pathlib.Path(sys.argv[1]); passed=int(sys.argv[2]); total=int(sys.argv[3])
payload={'case_count':20,'heldouts_per_case':3,'expected_simulation_count':160,'simulation_pass_count':passed,'all_compile_and_diverge':passed==total==160}
p.write_text(json.dumps(payload,indent=2)); print(json.dumps(payload,indent=2))
PY
