#!/usr/bin/env bash
# The fixed audit set: the same deals, played and rendered after every pilot fix (docs/reviews/).
# Each matchup plays deals 90000-90001 (game.py logs them under the current CONFIG); review.py renders
# the latest logged copy of each. Usage: audit_set.sh
source ~/ygo/.venv/bin/activate
cd ~/ygo/run
W=/mnt/c/Users/andre/Desktop/ygo-sim/wsl
MATCHUPS="cand__chaos-ritual__dogmatika-stardust__backrow:elfnote__tcg
cand__blitzclique__swordsoul-dogmatika:dark-magician-chaos-ritual__tcg
cand__branded__springans-dogmatika__backrow:sky-striker__tcg"
for m in $MATCHUPS; do
  f=${m%%:*}; s=${m##*:}
  TIMEOUT=1800 bash $W/run_py.sh game.py "$f" "$s" --games 2 --first-game 90000 | grep -E '^game|Error|Traceback'
  for g in 90000 90001; do
    timeout 300 python3 $W/review.py --game "$f" "$s" $g 2>&1 | grep -E 'flags$|Error|Traceback'
  done
done
