#!/usr/bin/env bash
# Train the pilot on the GPU (WSL venv). Usage: run_train.sh [train_pilot.py args...]
source ~/ygo/.venv/bin/activate
cd /mnt/c/Users/andre/Desktop/ygo-sim/wsl
python3 -u train_pilot.py "$@"
