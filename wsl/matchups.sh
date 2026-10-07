#!/usr/bin/env bash
# Stage C (THEORY §6): play every ordered deck pair (each deck going first and second, mirrors
# included). Results land in data/games/results.jsonl; `ygosim matrix` turns them into Bo3 match rates.
# Launch through wsl/awake.ps1 for long runs.
# Usage: matchups.sh "deckA deckB ..." GAMES_PER_PAIR [game.py args...]
W=/mnt/c/Users/andre/Desktop/ygo-sim/wsl
decks=$1 games=${2:-20}; shift 2
for a in $decks; do
  for b in $decks; do
    echo "== $a (first) vs $b (second)"
    TIMEOUT=${TIMEOUT:-21600} bash $W/run_py.sh game.py "$a" "$b" --games "$games" "$@" | grep --line-buffered -E "first wins|Traceback|Error"
  done
done
echo "MATCHUPS DONE"
