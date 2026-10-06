#!/usr/bin/env bash
source ~/ygo/.venv/bin/activate
W=/mnt/c/Users/andre/Desktop/ygo-sim/wsl
python3 $W/setup_runtime.py && cd ~/ygo/run && timeout 600 python3 $W/smoke_test.py "$@" 2>&1 | tail -40
