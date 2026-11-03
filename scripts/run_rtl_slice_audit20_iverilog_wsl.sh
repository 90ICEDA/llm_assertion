#!/usr/bin/env bash
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo"

command -v python3 >/dev/null || { echo "ERROR: python3 not found" >&2; exit 2; }
command -v iverilog >/dev/null || { echo "ERROR: iverilog not found" >&2; exit 2; }

python3 src/run_rtl_slice_iverilog_gate.py "$@"
