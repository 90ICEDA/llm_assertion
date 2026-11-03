#!/usr/bin/env bash
set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
root="$repo/rtl_cases_real_scale210_independent_next"
out="$repo/outputs/opentitan_hard_batch1_semantic_validation"
mkdir -p "$out/logs" "$out/work"
mapfile -t cases < <(find "$root" -mindepth 1 -maxdepth 1 -type d -name 'case45*' -printf '%f\n' | sort)
[[ $# -eq 0 ]] || cases=("$1")
for c in "${cases[@]}"; do
 d="$root/$c"
 for variant in primary holdout decoy; do
  case "$variant" in primary) tb=tb.v;sfx=;;holdout)tb=tb_holdout.v;sfx=_holdout;;decoy)tb=tb_decoy.v;sfx=_decoy;;esac
  for kind in correct buggy; do
   exe="$out/work/$c.$variant.$kind.vvp";vcd="$out/work/$c.$variant.$kind.vcd"
   iverilog -g2012 -o "$exe" "$d/$kind.v" "$d/$tb" >"$out/logs/$c.$variant.$kind.log" 2>&1
   vvp "$exe" +VCD="$vcd" >>"$out/logs/$c.$variant.$kind.log" 2>&1
   csv="$d/waveform_good$sfx.csv";[[ "$kind" == buggy ]]&&csv="$d/waveform_bad$sfx.csv"
   python3 "$repo/rtl_cases/vcd_to_csv.py" "$vcd" "$csv" >>"$out/logs/$c.$variant.$kind.log" 2>&1
  done
  for sfx in '' _holdout _decoy;do cmp -s "$d/waveform_good$sfx.csv" "$d/waveform_bad$sfx.csv"&&{ echo "NO DIVERGENCE $c $sfx";exit 1;}||true;done
 echo "OK $c"
done
python3 - "$root" "$out/semantic_validation_summary.json" <<'PY'
import hashlib,json,pathlib,sys
r=pathlib.Path(sys.argv[1]);rows=[]
for d in sorted(r.glob('case45*')):
 v={}
 for n,s in [('primary',''),('heldout','_holdout'),('decoy','_decoy')]:
  g=d/f'waveform_good{s}.csv';b=d/f'waveform_bad{s}.csv';v[n]={'present':g.exists() and b.exists(),'diverges':g.exists() and b.exists() and g.read_bytes()!=b.read_bytes()}
 rows.append({'case_id':d.name,'variants':v,'all_three_diverge':all(x['diverges'] for x in v.values())})
p={'schema_version':1,'case_count':len(rows),'all_three_diverge_count':sum(x['all_three_diverge'] for x in rows),'all_pass':all(x['all_three_diverge'] for x in rows),'cases':rows}
pathlib.Path(sys.argv[2]).write_text(json.dumps(p,indent=2));print(json.dumps({k:p[k] for k in ('case_count','all_three_diverge_count','all_pass')},indent=2))
PY

