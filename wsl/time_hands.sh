#!/usr/bin/env bash
# Time individual openings. Usage: time_hands.sh DECK FIRST HANDS [timeout] [extra goldfish args...]
source ~/ygo/.venv/bin/activate
cd ~/ygo/run
deck=$1 first=$2 hands=$3 limit=${4:-120}; shift 4 2>/dev/null || shift $#
start=$(date +%s)
timeout "$limit" python3 -u /mnt/c/Users/andre/Desktop/ygo-sim/wsl/goldfish.py "$deck" --first "$first" --hands "$hands" \
  --generations 15 "$@" 2>&1 \
  | while IFS= read -r line; do
      case "$line" in hand*|*ygosim*|*what*|*Traceback*|*Error*|*mean*|*"P(>="*) echo "[$(( $(date +%s) - start ))s] ${line:0:120}";; esac
    done
echo "exit ${PIPESTATUS[0]} after $(( $(date +%s) - start ))s"
