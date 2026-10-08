#!/usr/bin/env bash
# Stage C (THEORY §6): play every ordered deck pair (each deck going first and second, mirrors
# included). With POST=1, also play games 2-3 lists: the first player's __s1 vs the second's __s2
# (ygosim side-plans). Results land in data/games/results.jsonl; `ygosim matrix` builds Bo3 rates.
# Launch through wsl/awake.ps1 for long runs.
# Usage: [POST=1] matchups.sh "deckA deckB ..." GAMES_PER_PAIR [game.py args...]
W=/mnt/c/Users/andre/Desktop/ygo-sim/wsl
decks=$1 games=${2:-20}; shift 2
python3 $W/setup_runtime.py > /dev/null
play() {
  # Resumable: skip pairs that already have enough games logged.
  have=$(grep -c "\"first\": \"$1\", \"second\": \"$2\"" /mnt/c/Users/andre/Desktop/ygo-sim/data/games/results.jsonl 2>/dev/null || echo 0)
  if [ "$have" -ge "$games" ]; then echo "== $1 vs $2: $have games already, skipped"; return; fi
  echo "== $1 (first) vs $2 (second)"
  TIMEOUT=${TIMEOUT:-21600} bash $W/run_py.sh game.py "$1" "$2" --games "$games" "$@" | grep --line-buffered -E "first wins|Traceback|Error"
}
for a in $decks; do
  for b in $decks; do
    play "$a" "$b" "$@"
    if [ "${POST:-0}" = 1 ] && [ -e ~/ygo/run/decks/"$a"__s1.ydk ] && [ -e ~/ygo/run/decks/"$b"__s2.ydk ]; then
      play "${a}__s1" "${b}__s2" "$@"
    fi
  done
done
echo "MATCHUPS DONE"
