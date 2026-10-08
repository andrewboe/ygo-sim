#!/usr/bin/env bash
# Assemble the runtime dir, then run the random self-play smoke test.
# Usage: run_smoke.sh [envs] [games] [verbose]   (TIMEOUT env var, default 600s)
source ~/ygo/.venv/bin/activate
W=/mnt/c/Users/andre/Desktop/ygo-sim/wsl
python3 $W/setup_runtime.py || exit 1
cd ~/ygo/run
nice -n 19 timeout ${TIMEOUT:-600} python3 -u $W/smoke_test.py "$@" 2>&1 | grep -vE '^(Gym has|Please upgrade|Users of this|See the migration)'
status=${PIPESTATUS[0]}
[ $status -eq 124 ] && echo "[smoke] TIMED OUT after ${TIMEOUT:-600}s"
exit $status
