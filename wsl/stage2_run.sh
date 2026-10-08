#!/usr/bin/env bash
# Launch funnel stage 2 on the stage 1 entrants (data/screen/stage2_entrants.txt, written from the report).
# Log: data/games/stage2.log. Launch through wsl/awake.ps1. Usage: stage2_run.sh [extra stage2.py args]
source ~/ygo/.venv/bin/activate
DATA=/mnt/c/Users/andre/Desktop/ygo-sim/data
mkdir -p $DATA/games
python3 -u /mnt/c/Users/andre/Desktop/ygo-sim/wsl/stage2.py $(cat $DATA/screen/stage2_entrants.txt) "$@" \
  >> $DATA/games/stage2.log 2>&1
echo "STAGE2 EXIT $?" >> $DATA/games/stage2.log
