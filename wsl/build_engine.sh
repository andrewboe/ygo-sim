#!/usr/bin/env bash
# Build ygo-agent's EDOPro (Project Ignis) environment against the current edo9300 ygopro-core.
# Usage: build_engine.sh [release|releasedbg]   (runs build_core.sh first)
set -e
MODE=${1:-release}
W=/mnt/c/Users/andre/Desktop/ygo-sim/wsl
export PATH=~/.local/bin:$PATH
source ~/ygo/.venv/bin/activate
bash $W/build_core.sh
cd ~/ygo/ygo-agent
cp $W/edopro-core.xmake.lua repo/packages/e/edopro-core/xmake.lua
# Force xmake to re-install the freshly built core.
rm -rf ~/.xmake/cache/packages/*/e/edopro-core ~/.xmake/packages/e/edopro-core
xmake f -y -m "$MODE" 2>&1 | grep -E 'error|failed' || true
bash $W/rebuild.sh
