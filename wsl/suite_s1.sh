#!/usr/bin/env bash
# Weak-point suite S1 for every TCG field deck (3 deals each). Usage: suite_s1.sh [N_DEALS]
source ~/ygo/.venv/bin/activate; cd ~/ygo/run
for d in $(ls decks | grep '__tcg.ydk$' | sed 's/.ydk$//'); do
  timeout 1200 python3 /mnt/c/Users/andre/Desktop/ygo-sim/wsl/suite_s1.py $d ${1:-3} 2>&1 | grep -a -E '^S1|deal [0-9]+:|Traceback' | grep -v '^\s'
done
