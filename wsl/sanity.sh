#!/usr/bin/env bash
# Sanity statistics for the current pilot (docs/AUDIT.md item 4): the Elfnote mirror (pure seat effect)
# and six field-deck pairings, both seats. Games 92000+, logged under game.CONFIG. Summarize with
# sanity_report.py. Usage: sanity.sh [MIRROR_GAMES] [PAIR_GAMES]
W=/mnt/c/Users/andre/Desktop/ygo-sim/wsl
m=${1:-30}; p=${2:-6}
TIMEOUT=14400 bash $W/run_py.sh game.py elfnote__tcg elfnote__tcg --games "$m" --first-game 92000 | grep -E '^game|wins|Error'
DECKS="elfnote__tcg dark-magician-chaos-ritual__tcg sky-striker__tcg blitzclique__tcg"
for a in $DECKS; do for b in $DECKS; do
  [ "$a" \< "$b" ] || continue
  TIMEOUT=7200 bash $W/run_py.sh game.py "$a" "$b" --games "$p" --first-game 92100 | grep -E 'wins|Error'
  TIMEOUT=7200 bash $W/run_py.sh game.py "$b" "$a" --games "$p" --first-game 92100 | grep -E 'wins|Error'
done; done
echo "SANITY DONE"
