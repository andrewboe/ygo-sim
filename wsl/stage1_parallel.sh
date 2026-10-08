#!/usr/bin/env bash
# Run stage 1 with N parallel workers (they claim candidates via locks). Logs: data/screen/stage1_w<i>.log
# Usage: stage1_parallel.sh WORKERS [HANDS] [GAMES_PER_OPPONENT] [opponents...]
W=/mnt/c/Users/andre/Desktop/ygo-sim/wsl
DATA=/mnt/c/Users/andre/Desktop/ygo-sim/data
workers=${1:-3}; shift
python3 $W/setup_runtime.py > /dev/null
rm -rf "$DATA/screen/locks"  # no workers are running yet: any lock is stale
for i in $(seq 1 "$workers"); do
  STAGE1_NO_SETUP=1 bash $W/stage1.sh "$@" > "$DATA/screen/stage1_w$i.log" 2>&1 &
  sleep 5  # stagger start-up
done
wait
echo "ALL WORKERS DONE"
