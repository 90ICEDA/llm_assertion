#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONVERTER="$ROOT_DIR/vcd_to_csv.py"

if ! command -v iverilog >/dev/null 2>&1; then
  echo "ERROR: iverilog not found in PATH."
  exit 1
fi

if ! command -v vvp >/dev/null 2>&1; then
  echo "ERROR: vvp not found in PATH."
  exit 1
fi

for d in "$ROOT_DIR"/case*; do
  [ -d "$d" ] || continue
  base="$(basename "$d")"
  echo "[INFO] Processing $base"

  pushd "$d" >/dev/null

  case_id="${base%%_*}" # case01

  iverilog -g2012 -o sim_good ./correct.v ./tb.v
  vvp ./sim_good
  mv "${case_id}.vcd" waveform_good.vcd
  python3 "$CONVERTER" waveform_good.vcd waveform_good.csv

  iverilog -g2012 -o sim_bad ./buggy.v ./tb.v
  vvp ./sim_bad
  mv "${case_id}.vcd" waveform_bad.vcd
  python3 "$CONVERTER" waveform_bad.vcd waveform_bad.csv

  if [ -f ./tb_holdout.v ]; then
    holdout_vcd="${case_id}_holdout.vcd"

    iverilog -g2012 -o sim_good_holdout ./correct.v ./tb_holdout.v
    vvp ./sim_good_holdout
    mv "$holdout_vcd" waveform_good_holdout.vcd
    python3 "$CONVERTER" waveform_good_holdout.vcd waveform_good_holdout.csv

    iverilog -g2012 -o sim_bad_holdout ./buggy.v ./tb_holdout.v
    vvp ./sim_bad_holdout
    mv "$holdout_vcd" waveform_bad_holdout.vcd
    python3 "$CONVERTER" waveform_bad_holdout.vcd waveform_bad_holdout.csv
  fi

  rm -f sim_good sim_bad sim_good_holdout sim_bad_holdout
  popd >/dev/null
done

echo "[DONE] Regenerated primary and held-out waveform CSV/VCD files for all cases."
