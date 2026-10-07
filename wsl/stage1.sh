#!/usr/bin/env bash
# Funnel stage 1 for every candidate (data/candidates via `ygosim packages`):
#   going first:  goldfish board over HANDS openings (data/search/cand__*__goldfish.jsonl)
#   going second: break-the-board screen vs the top field decks (data/screen/second.jsonl)
# Launch through wsl/awake.ps1. Usage: stage1.sh [HANDS] [GAMES_PER_OPPONENT] [opponents...]
W=/mnt/c/Users/andre/Desktop/ygo-sim/wsl
hands=${1:-40} games=${2:-12}; shift 2
opponents=${*:-"elfnote__tcg dark-magician-chaos-ritual__tcg sky-striker__tcg"}
python3 $W/setup_runtime.py > /dev/null
for p in ~/ygo/run/decks/cand__*.ydk; do
  c=$(basename "$p" .ydk)
  g=$(TIMEOUT=7200 bash $W/run_goldfish.sh "$c" --hands "$hands" 2>&1 | grep 'mean interruptions')
  echo "== $c | first: $g"
  for o in $opponents; do
    TIMEOUT=7200 bash $W/run_py.sh second_screen.py "$c" "$o" --games "$games" 2>&1 | grep --line-buffered "score"
  done
done
echo "STAGE1 DONE"
