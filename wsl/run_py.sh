#!/usr/bin/env bash
# Run a wsl/ script from ~/ygo/run in the venv. Usage: run_py.sh SCRIPT.py [args...]
HERE="$(cd "$(dirname "$0")" && pwd)"  # the checkout this script is in (a worktree runs its own code)
source ~/ygo/.venv/bin/activate
cd ~/ygo/run
nice -n 19 timeout ${TIMEOUT:-1800} python3 -u "$HERE/$1" "${@:2}" 2>&1 \
  | grep --line-buffered -vE '^(Gym has|Please upgrade|Users of this|See the migration)|Unable to open script file'
