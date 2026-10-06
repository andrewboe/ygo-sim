#!/usr/bin/env bash
# Chokepoint maps for several decks x hand-trap sets; logs to data/chokepoint/.
# Usage: chokepoint_batch.sh "deck1 deck2" "ash imperm" [chokepoint.py args...]
W=/mnt/c/Users/andre/Desktop/ygo-sim/wsl
OUT=/mnt/c/Users/andre/Desktop/ygo-sim/data/chokepoint
mkdir -p $OUT
decks=$1 sets=$2; shift 2
for d in $decks; do
  for s in $sets; do
    bash $W/run_chokepoint.sh $d --opponent $s "$@" > $OUT/${d}__${s}.log 2>&1
    echo "== $d vs $s"; tail -3 $OUT/${d}__${s}.log
  done
done
echo BATCH DONE
