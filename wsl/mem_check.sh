#!/usr/bin/env bash
# Run goldfish in the background and sample its memory every 10s. Usage: mem_check.sh DECK HANDS SECONDS
source ~/ygo/.venv/bin/activate
cd ~/ygo/run
python3 -u /mnt/c/Users/andre/Desktop/ygo-sim/wsl/goldfish.py "$1" --hands "$2" --generations 15 > /tmp/mem.log 2>&1 &
pid=$!
for _ in $(seq 1 $(( $3 / 10 ))); do
  sleep 10
  kill -0 $pid 2>/dev/null || break
  echo "$(grep -c '^hand' /tmp/mem.log) hands, RSS $(( $(awk '/VmRSS/{print $2}' /proc/$pid/status) / 1024 )) MB"
done
kill $pid 2>/dev/null
tail -6 /tmp/mem.log | cut -c1-100
