#!/usr/bin/env bash
# Goldfish every field deck: turn-1 strength per deck, and pilot training data
# (data/search/<deck>__goldfish.jsonl). Launch through wsl/awake.ps1.
# Usage: goldfish_field.sh HANDS [goldfish.py args...]
W=/mnt/c/Users/andre/Desktop/ygo-sim/wsl
hands=${1:-100}; shift
OUT=/mnt/c/Users/andre/Desktop/ygo-sim/data/goldfish
mkdir -p $OUT
python3 $W/setup_runtime.py > /dev/null
for p in ~/ygo/run/decks/[!_]*.ydk; do
  d=$(basename "$p" .ydk)
  TIMEOUT=${TIMEOUT:-14400} bash $W/run_goldfish.sh "$d" --hands "$hands" "$@" > "$OUT/$d.log" 2>&1
  echo "== $d: $(grep 'mean interruptions' "$OUT/$d.log")"
done
echo "FIELD DONE"
