#!/usr/bin/env bash
# Review a sample of stage 2 games, one process per game (env pools can't be torn down in-process).
# Usage: review_sample.sh [N] [CONFIG]   (CONFIG: game.CONFIG of the games to sample; default v1)
source ~/ygo/.venv/bin/activate
cd ~/ygo/run
W=/mnt/c/Users/andre/Desktop/ygo-sim/wsl
rm -f /mnt/c/Users/andre/Desktop/ygo-sim/data/review/summary.jsonl
python3 $W/review.py --list --sample "${1:-12}" ${2:+--config $2} 2>/dev/null | grep -E '^\S+ \S+ [0-9]+$' | while read f s g; do
  timeout 300 python3 $W/review.py --game "$f" "$s" "$g" 2>&1 | grep -E 'flags$|Error|SIGSEGV'
done
