#!/usr/bin/env bash
# Freeze every simulator/training process in place (frees CPU instantly; RAM/GPU memory stay
# allocated). Continue with resume_sims.sh. Doesn't survive a reboot (use the resumable runs for that).
n=0
for pid in $(pgrep -f 'ygo-sim/wsl/|train_pilot.py'); do
  [ "$pid" = $$ ] && continue
  kill -STOP "$pid" 2>/dev/null && n=$((n + 1))
done
echo "paused $n processes"
