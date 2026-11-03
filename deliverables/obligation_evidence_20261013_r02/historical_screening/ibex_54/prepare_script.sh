#!/bin/bash
set -e

# Stage 1: checkout base_sha in a clean workspace (+submodules)
cd /home/ibex
git reset --hard
git clean -fdx
git checkout cd15ce88beba8ed8496f414af361f664764f47e2
git submodule update --init --recursive || true

# Stage 2: install the simulator required by this reproducer
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends iverilog
rm -rf /var/lib/apt/lists/*

# Stage 3: persist PATH for future shells
cat > /etc/ibex_tools_path.sh <<'EOF'
export PATH="/usr/bin:$PATH"
EOF
touch /etc/ibex_bash_env
if ! grep -q "/etc/ibex_tools_path.sh" /etc/ibex_bash_env; then
  echo "source /etc/ibex_tools_path.sh" >> /etc/ibex_bash_env
fi

# Stage 4: apply PATH for current shell
source /etc/ibex_tools_path.sh

# Stage 5: record baseline commit
BASE_FILE="/home/ibex_base_commit.txt"
git rev-parse HEAD > "${BASE_FILE}"
echo "[INFO] Baseline HEAD recorded to ${BASE_FILE}: $(cat "${BASE_FILE}")"
