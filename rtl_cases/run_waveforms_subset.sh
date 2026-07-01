#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <dataset-root> <case-name> [<case-name> ...]" >&2
  exit 1
fi

root=$1
shift
converter="$(cd "$(dirname "$0")" && pwd)/vcd_to_csv.py"

for case in "$@"; do
  case_dir="$root/$case"
  if [[ ! -d "$case_dir" ]]; then
    echo "[ERROR] Missing case dir: $case_dir" >&2
    exit 1
  fi

  cid="${case%%_*}"
  echo "[INFO] $case"
  cd "$case_dir"

  rm -f \
    waveform_good.vcd waveform_bad.vcd waveform_good.csv waveform_bad.csv \
    waveform_good_holdout.vcd waveform_bad_holdout.vcd \
    waveform_good_holdout.csv waveform_bad_holdout.csv \
    sim_good sim_bad sim_good_holdout sim_bad_holdout \
    "${cid}.vcd" "${cid}_holdout.vcd"

  iverilog -g2012 -o sim_good ./correct.v ./tb.v
  vvp ./sim_good
  mv "${cid}.vcd" waveform_good.vcd
  python3 "$converter" waveform_good.vcd waveform_good.csv

  iverilog -g2012 -o sim_bad ./buggy.v ./tb.v
  vvp ./sim_bad
  mv "${cid}.vcd" waveform_bad.vcd
  python3 "$converter" waveform_bad.vcd waveform_bad.csv

  iverilog -g2012 -o sim_good_holdout ./correct.v ./tb_holdout.v
  vvp ./sim_good_holdout
  mv "${cid}_holdout.vcd" waveform_good_holdout.vcd
  python3 "$converter" waveform_good_holdout.vcd waveform_good_holdout.csv

  iverilog -g2012 -o sim_bad_holdout ./buggy.v ./tb_holdout.v
  vvp ./sim_bad_holdout
  mv "${cid}_holdout.vcd" waveform_bad_holdout.vcd
  python3 "$converter" waveform_bad_holdout.vcd waveform_bad_holdout.csv

  rm -f sim_good sim_bad sim_good_holdout sim_bad_holdout
done

echo "[DONE] Waveforms regenerated for $# case(s)"
