#!/usr/bin/env bash
# Profile goldfish (py-spy as parent, so ptrace_scope=1 is fine) and show the hottest native stacks.
# Usage: profile_hang.sh DECK SEED HANDS SECONDS
source ~/ygo/.venv/bin/activate
cd ~/ygo/run
py-spy record --native --idle --threads -r 20 -d "$4" -f raw -o /tmp/prof.txt -- \
  python3 /mnt/c/Users/andre/Desktop/ygo-sim/wsl/goldfish.py "$1" --seed "$2" --hands "$3" --generations 15 \
  > /tmp/prof_run.log 2>&1
tail -1 /tmp/prof_run.log | cut -c1-80
# Collapsed stacks "a;b;c count": keep ygoenv/core frames, rank by samples.
python3 - <<'EOF'
import re, collections
c = collections.Counter()
for line in open("/tmp/prof.txt"):
    stack, _, n = line.rstrip().rpartition(" ")
    frames = [f for f in stack.split(";") if re.search(r"edopro|ocgcore|lua|interpreter|field::|processor|duel::|card::|handle_message|next|Step|Reset", f)]
    if frames:
        c[";".join(f.split(" (")[0][-60:] for f in frames[-6:])] += int(n)
for s, n in c.most_common(8):
    print(n, s)
EOF
