#!/usr/bin/env bash
# Goldfish several decks on the same openings (same seeds) and keep the logs.
# Usage: compare.sh "deck1 deck2 ..." [goldfish.py args...]
W=/mnt/c/Users/andre/Desktop/ygo-sim/wsl
OUT=/mnt/c/Users/andre/Desktop/ygo-sim/data/goldfish
mkdir -p $OUT
decks=$1; shift
for d in $decks; do
  bash $W/run_goldfish.sh $d "$@" > $OUT/$d.log 2>&1
  echo "== $d"; tail -6 $OUT/$d.log
done
