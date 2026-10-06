#!/usr/bin/env bash
# Run goldfish and print the crash trace frames from ygoenv/core. Usage: crash_trace.sh DECK SEED HANDS
source ~/ygo/.venv/bin/activate
cd ~/ygo/run
timeout ${TIMEOUT:-300} python3 -u /mnt/c/Users/andre/Desktop/ygo-sim/wsl/goldfish.py "$1" --seed "$2" --hands "$3" --generations 15 > /tmp/crash.log 2>&1
echo "exit $?"
grep -E 'SIG|what\(\)|\[ygosim\]|Traceback|Error|^\s+@.*(edopro|Env|ocg|lua|card|field|duel|interpreter|processor)' /tmp/crash.log | head -25 | cut -c1-180
