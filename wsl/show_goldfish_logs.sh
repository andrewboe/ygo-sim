#!/usr/bin/env bash
# Summarize goldfish logs: last hands, errors, and ygoenv frames of any crash trace.
for f in /mnt/c/Users/andre/Desktop/ygo-sim/data/goldfish/*.log; do
  echo "== $(basename "$f")"
  grep -E '^hand' "$f" | tail -3 | cut -c1-160
  grep -E 'Aborted|SIG|what\(\)|Error|\[ygosim\]|TIMED|edopro::|Traceback' "$f" | grep -vE 'Py_|_ZZN|_ZSt' | head -15 | cut -c1-200
done
