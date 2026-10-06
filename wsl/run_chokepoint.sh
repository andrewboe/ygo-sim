#!/usr/bin/env bash
# Usage: run_chokepoint.sh DECK [chokepoint.py args...]   e.g. run_chokepoint.sh elfnote__tcg --opponent ash --hands 5
source ~/ygo/.venv/bin/activate
W=/mnt/c/Users/andre/Desktop/ygo-sim/wsl
python3 $W/setup_runtime.py > /dev/null || exit 1
cd ~/ygo/run
timeout ${TIMEOUT:-3600} python3 -u $W/chokepoint.py "$@" 2>&1 \
  | grep -vE '^(Gym has|Please upgrade|Users of this|See the migration)|Unable to open script file'
