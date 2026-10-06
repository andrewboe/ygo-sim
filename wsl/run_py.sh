#!/usr/bin/env bash
# Run a wsl/ script from ~/ygo/run in the venv. Usage: run_py.sh SCRIPT.py [args...]
source ~/ygo/.venv/bin/activate
cd ~/ygo/run
timeout ${TIMEOUT:-1800} python3 -u /mnt/c/Users/andre/Desktop/ygo-sim/wsl/"$@" 2>&1 \
  | grep -vE '^(Gym has|Please upgrade|Users of this|See the migration)|Unable to open script file'
