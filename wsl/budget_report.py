"""Budget elasticity: same deals at 1x (gens 10, untagged) vs 3x (gens 30) search, current pilot only."""
import json
import sys
from collections import defaultdict

sys.path.insert(0, "/mnt/c/Users/andre/Desktop/ygo-sim/wsl")
from game import CONFIG  # noqa: E402

rows = [json.loads(l) for l in open("/mnt/c/Users/andre/Desktop/ygo-sim/data/games/results.jsonl")]
rows = [r for r in rows if r.get("config") == CONFIG and 92100 <= r["game"] < 92104 and r["first"] != r["second"]]
res = {}
for r in rows:
    res[(r.get("gens", 10), r["first"], r["second"], r["game"])] = r["winner"]
pairs = {(f, s, g) for (b, f, s, g) in res if b == 30}
stats = defaultdict(lambda: {10: [0, 0], 30: [0, 0]})
first = {10: [0, 0], 30: [0, 0]}
changed = 0
for f, s, g in sorted(pairs):
    if (10, f, s, g) not in res:
        continue
    for b in (10, 30):
        w = res[(b, f, s, g)]
        first[b][0] += w == 0
        first[b][1] += 1
        for seat, d in ((0, f), (1, s)):
            stats[d][b][0] += w == seat
            stats[d][b][1] += 1
    changed += res[(10, f, s, g)] != res[(30, f, s, g)]
n = first[10][1]
print(f"{n} paired games; outcome changed in {changed}")
print(f"going first wins: 1x {first[10][0]}/{n}, 3x {first[30][0]}/{n}")
for d, v in sorted(stats.items()):
    a, b = v[10], v[30]
    print(f"{d.replace('__tcg', ''):28} 1x {a[0]}/{a[1]}  3x {b[0]}/{b[1]}")
