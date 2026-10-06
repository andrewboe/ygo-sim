#!/usr/bin/env bash
# Show the tail of every failed xmake package install log.
for f in ~/.xmake/cache/packages/*/*/*/*/installdir.failed/logs/install.txt; do
  echo "==== $f"
  grep -inE 'error|not found|fatal|undefined|cannot' "$f" | grep -viE 'Werror|warning' | head -8
  tail -5 "$f"
done
