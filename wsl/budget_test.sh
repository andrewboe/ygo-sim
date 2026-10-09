#!/usr/bin/env bash
# Budget elasticity (docs/AUDIT.md item 4a): replay sanity.sh deals 92100-92103 at 3x search budget,
# Elfnote vs three field decks plus a control pairing, both seats. Compare with budget_report.py.
W=/mnt/c/Users/andre/Desktop/ygo-sim/wsl
PAIRS="elfnote__tcg:blitzclique__tcg elfnote__tcg:dark-magician-chaos-ritual__tcg elfnote__tcg:sky-striker__tcg blitzclique__tcg:sky-striker__tcg"
for p in $PAIRS; do
  a=${p%%:*}; b=${p##*:}
  TIMEOUT=14400 bash $W/run_py.sh game.py "$a" "$b" --games 4 --first-game 92100 --generations 30 | grep -E 'wins|Error'
  TIMEOUT=14400 bash $W/run_py.sh game.py "$b" "$a" --games 4 --first-game 92100 --generations 30 | grep -E 'wins|Error'
done
echo "BUDGET DONE"
