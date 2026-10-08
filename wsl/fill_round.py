"""Play one candidate's missing stage 2 round (same deals as everyone else) without touching the
finalists file. Run in WSL:  python fill_round.py CANDIDATE [ROUND] [--games 2]"""
import sys

sys.path.insert(0, "/mnt/c/Users/andre/Desktop/ygo-sim/wsl")
from stage2 import field_opponents, field_rate, play  # noqa: E402

cand = sys.argv[1]
rnd = int(sys.argv[2]) if len(sys.argv) > 2 else 0
opps = field_opponents(0.04)
for opp in opps:
    play(cand, opp, 2, 10_000 + rnd * 100, [])
    play(opp, cand, 2, 10_000 + rnd * 100, [])
r, se, n = field_rate(cand, opps)
print(f"{cand}: {r:5.1%} +- {se:4.1%} ({n} games)")
