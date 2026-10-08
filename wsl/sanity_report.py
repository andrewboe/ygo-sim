"""Summarize sanity.sh: going-first win rate in the mirror and across field pairings (game.CONFIG only)."""
import json
import math
import sys

sys.path.insert(0, "/mnt/c/Users/andre/Desktop/ygo-sim/wsl")
from game import CONFIG  # noqa: E402

rows = [json.loads(l) for l in open("/mnt/c/Users/andre/Desktop/ygo-sim/data/games/results.jsonl")]
rows = [r for r in rows if r.get("config") == CONFIG and 92000 <= r["game"] < 93000]


def rate(rs):
    n = len(rs)
    w = sum(1.0 if r["winner"] == 0 else 0.5 if r["winner"] == -1 else 0.0 for r in rs)
    p = w / n if n else float("nan")
    return p, math.sqrt(p * (1 - p) / n) if n else float("nan"), n


mirror = [r for r in rows if r["first"] == r["second"]]
pairs = [r for r in rows if r["first"] != r["second"]]
for label, rs in (("mirror (Elfnote)", mirror), ("field pairings", pairs)):
    p, se, n = rate(rs)
    caps = sum(r["by"] == "turn cap" for r in rs)
    print(f"{label}: going first wins {p:.0%} +- {se:.0%} over {n} games ({caps} turn caps)")
