#!/usr/bin/env bash
# Stop running simulator batches and their Python workers (this script's own name doesn't match).
pkill -f 'chokepoint_batch.sh|run_chokepoint.sh|run_goldfish.sh|compare.sh|stage1.sh|matchups.sh|run_py.sh' 2>/dev/null
pkill -f 'python3 -u /mnt/c/Users/andre/Desktop/ygo-sim/wsl/' 2>/dev/null
sleep 2
pkill -9 -f 'python3 -u /mnt/c/Users/andre/Desktop/ygo-sim/wsl/' 2>/dev/null  # envpool may ignore SIGTERM
sleep 1
pgrep -fa 'ygo-sim/wsl/' | grep -v stop_sims || echo "no simulator processes running"
