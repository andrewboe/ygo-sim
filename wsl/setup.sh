#!/usr/bin/env bash
# One-time WSL setup for the simulator. Needs (sudo, once):
#   sudo apt install -y build-essential git cmake python3-venv python3-dev libncurses6 unzip pkg-config
# Everything lands in ~/ygo:
#   ygo-agent/   ygoenv (envpool-based gym env), patched by patch_ygoenv.py
#   edopro-core/ current edo9300 ygopro-core (Project Ignis engine)
#   CardScripts/, BabelCDB/  Ignis card scripts and databases
#   run/         runtime dir assembled by setup_runtime.py
set -e
W=$(cd "$(dirname "$0")" && pwd)
mkdir -p ~/ygo && cd ~/ygo
[ -d ygo-agent ] || git clone -q https://github.com/sbl1996/ygo-agent.git
[ -d edopro-core ] || git clone -q https://github.com/edo9300/ygopro-core.git edopro-core
command -v ~/.local/bin/xmake >/dev/null || bash "$W/install_xmake.sh"
bash "$W/setup_venv.sh"
bash "$W/fetch_ignis.sh"
bash "$W/build_engine.sh" "${1:-releasedbg}"
~/ygo/.venv/bin/python "$W/setup_runtime.py"
