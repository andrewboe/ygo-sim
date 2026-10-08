#!/usr/bin/env bash
# Lower the priority of simulator processes that are already running (new runs start at nice 19).
n=0
for pid in $(pgrep -f 'ygo-sim/wsl/|train_pilot.py'); do
  [ "$pid" = $$ ] && continue
  renice -n 19 -p "$pid" > /dev/null 2>&1 && n=$((n + 1))  # processes may exit mid-loop
done
echo "reniced $n processes to 19"
