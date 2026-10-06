#!/usr/bin/env bash
# Usage: run_goldfish.sh DECK [goldfish.py args...]   e.g. run_goldfish.sh elfnote__tcg --hands 10
source ~/ygo/.venv/bin/activate
cd ~/ygo/run
timeout ${TIMEOUT:-1800} python3 -u /mnt/c/Users/andre/Desktop/ygo-sim/wsl/goldfish.py "$@" 2>&1 \
  | grep -vE '^(Gym has|Please upgrade|Users of this|See the migration)|Unable to open script file'
