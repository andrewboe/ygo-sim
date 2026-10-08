#!/usr/bin/env bash
# Continue processes frozen by pause_sims.sh.
n=0
for pid in $(pgrep -f 'ygo-sim/wsl/|train_pilot.py'); do
  [ "$pid" = $$ ] && continue
  kill -CONT "$pid" 2>/dev/null && n=$((n + 1))
done
echo "resumed $n processes"
