#!/usr/bin/env bash
# Funnel stage 1 for every candidate (data/candidates via `ygosim packages`; side-plan lists excluded):
#   going first:  goldfish board over HANDS openings (data/search/cand__*__goldfish.jsonl)
#   going second: break-the-board screen vs the top field decks (data/screen/second.jsonl)
# Resumable (skips candidates with complete results) and parallel-safe: run several copies; each
# claims a candidate atomically (mkdir lock) before working on it.
# Launch through wsl/awake.ps1. Usage: stage1.sh [HANDS] [GAMES_PER_OPPONENT] [opponents...]
W=/mnt/c/Users/andre/Desktop/ygo-sim/wsl
DATA=/mnt/c/Users/andre/Desktop/ygo-sim/data
LOCKS=$DATA/screen/locks
hands=${1:-40} games=${2:-12}; shift 2
opponents=${*:-"elfnote__tcg dark-magician-chaos-ritual__tcg sky-striker__tcg"}
mkdir -p "$LOCKS"
[ -z "$STAGE1_NO_SETUP" ] && python3 $W/setup_runtime.py > /dev/null
current=""
trap 'rmdir "$LOCKS/$current" 2>/dev/null' EXIT
for p in ~/ygo/run/decks/cand__*.ydk; do
  c=$(basename "$p" .ydk)
  case "$c" in *__s1|*__s2) continue ;; esac
  done_first=$(cat "$DATA/search/${c}__goldfish.jsonl" 2>/dev/null | wc -l)
  need_second=0
  for o in $opponents; do
    n=$(grep -c "\"candidate\": \"$c\", \"opponent\": \"$o\"" "$DATA/screen/second.jsonl" 2>/dev/null); n=${n:-0}
    [ "$n" -lt "$games" ] && need_second=1
  done
  [ "$done_first" -ge "$hands" ] && [ "$need_second" = 0 ] && continue
  mkdir "$LOCKS/$c" 2>/dev/null || continue  # another worker has it
  current=$c
  if [ "$done_first" -lt "$hands" ]; then
    rm -f "$DATA/search/${c}__goldfish.jsonl"  # partial run: redo cleanly
    g=$(TIMEOUT=7200 bash $W/run_goldfish.sh "$c" --hands "$hands" 2>&1 | grep 'mean interruptions')
    echo "== $c | first: $g"
  fi
  for o in $opponents; do
    n=$(grep -c "\"candidate\": \"$c\", \"opponent\": \"$o\"" "$DATA/screen/second.jsonl" 2>/dev/null); n=${n:-0}
    if [ "$n" -lt "$games" ]; then
      TIMEOUT=7200 bash $W/run_py.sh second_screen.py "$c" "$o" --games "$games" 2>&1 | grep --line-buffered "score"
    fi
  done
  rmdir "$LOCKS/$c"
  current=""
done
echo "STAGE1 DONE"
