#!/usr/bin/env bash
# Run one env (no rebuild) and print the crash trace frames from ygoenv.
YGOSIM_TRACE_WIN=1 bash /mnt/c/Users/andre/Desktop/ygo-sim/wsl/run_smoke.sh ${1:-1} ${2:-3} 2>&1 \
  | grep -E 'ygosim|games|length|what|terminate|edopro::|ankerl|on_error|Error' | grep -v '_ZZN\|_ZSt' | head -${3:-25}
