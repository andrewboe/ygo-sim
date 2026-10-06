#!/usr/bin/env bash
# Run goldfish until it hangs, then dump native stacks of every thread with py-spy.
# Usage: dump_hang.sh DECK SEED HANDS SECONDS
source ~/ygo/.venv/bin/activate
pip install -q py-spy
echo "ptrace_scope: $(cat /proc/sys/kernel/yama/ptrace_scope)"
cd ~/ygo/run
python3 -u /mnt/c/Users/andre/Desktop/ygo-sim/wsl/goldfish.py "$1" --seed "$2" --hands "$3" --generations 15 > /tmp/hang.log 2>&1 &
pid=$!
sleep "$4"
tail -2 /tmp/hang.log | cut -c1-100
py-spy dump --native --pid $pid 2>&1 | grep -vE '^\s*$' | grep -E 'Thread|edopro|ocgcore|lua|interpreter|duel|field::|processor|card::|\(python|goldfish' | head -80
kill -9 $pid 2>/dev/null
