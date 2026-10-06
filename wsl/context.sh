#!/usr/bin/env bash
# Run the smoke test and show output around the first line matching a pattern.
# Usage: context.sh PATTERN [envs] [games]
YGOSIM_TRACE_WIN=1 bash /mnt/c/Users/andre/Desktop/ygo-sim/wsl/run_smoke.sh ${2:-16} ${3:-500} > /tmp/smoke.log 2>&1
echo "exit: $? lines: $(wc -l < /tmp/smoke.log)"
grep -n -m1 -B12 -A3 -- "$1" /tmp/smoke.log | cut -c1-200
echo ...; tail -4 /tmp/smoke.log | cut -c1-200
