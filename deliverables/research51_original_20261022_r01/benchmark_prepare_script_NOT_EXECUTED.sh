#!/bin/bash
set -euo pipefail

cd /home/ibex
git fetch --all --tags --prune || true
git checkout -f c96ece04296c3c69df578d760aa8a66f9b886fef
git submodule update --init --recursive

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y verilator g++

cat > /etc/profile.d/ibex-local-path.sh <<'EOF'
export PATH="/usr/bin:$PATH"
EOF

export PATH="/usr/bin:$PATH"
