#!/usr/bin/env bash
# Paired full-game A/B of the deck executors (docs/windbot_plan.md, phase 5). Each executor deck X plays a fixed
# opponent Y in both seats on the same deals in both arms; arm 1 runs the card handlers / executor for X's seat
# only (YGOSIM_HANDLER_SEATS), arm 0 runs no handlers. Arms and seats alternate in chunks of the same deals, so a
# run stopped early is still balanced. Results: OUT/arm0/results.jsonl, OUT/arm1/results.jsonl (ab_report.py).
# Usage (WSL): ab_executors.sh OUT GAMES_PER_SEAT FIRST_GAME [CHUNK] [X:Y ...]
OUT=$1; GAMES=$2; BASE=$3; CHUNK=${4:-5}
shift 4 2>/dev/null || shift $#
PAIRS=${*:-"elfnote__tcg:invoked__tcg chaos-ritual__tcg:lunalight__tcg maliss__tcg:mitsurugi-yummy__tcg
branded__tcg:magistus-invoked-fairy-tail__tcg sky-striker__tcg:blitzclique__tcg
mitsurugi__tcg:dark-magician-chaos-ritual__tcg"}
HERE="$(cd "$(dirname "$0")" && pwd)"
export TIMEOUT=${TIMEOUT:-21600}
mkdir -p "$OUT"
{  # what the games ran with
  echo "date $(date -Is)"
  echo "commit $(git -C "$HERE" rev-parse --short HEAD)$(git -C "$HERE" diff --quiet HEAD -- . || echo ' (dirty)')"
  echo "card_tag_overrides $(sha1sum "$HERE/card_tag_overrides.json" | cut -c1-12)"
  echo "YGOSIM_LATE_BOOST ${YGOSIM_LATE_BOOST:-1} YGOSIM_CPU_RULES ${YGOSIM_CPU_RULES:-1} games/seat $GAMES first $BASE"
} >> "$OUT/settings.txt"
for pair in $PAIRS; do
  X=${pair%%:*}; Y=${pair##*:}
  for ((g = BASE; g < BASE + GAMES; g += CHUNK)); do
    n=$(( BASE + GAMES - g < CHUNK ? BASE + GAMES - g : CHUNK ))
    for seat in 0 1; do
      if [ $seat = 0 ]; then decks="$X $Y"; else decks="$Y $X"; fi
      for arm in 0 1; do
        echo "=== $(date +%T) $X vs $Y seat $seat arm $arm games $g..$((g + n - 1))"
        YGOSIM_LOG_DIR="$OUT/arm$arm" YGOSIM_CARD_HANDLERS=$arm YGOSIM_HANDLER_SEATS=$seat \
          bash "$HERE/run_py.sh" game.py $decks --games $n --first-game $g | grep -E "^game |Error|Traceback"
      done
    done
  done
done
echo "=== $(date +%T) done"
