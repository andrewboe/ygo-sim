"""Report a paired executor A/B (ab_executors.sh): per executor deck (the decks in windbot_decks.DECKS), its win
rate with no handlers (arm 0) and with its executor (arm 1) on the same deals, the deals whose result changed
(better / worse) with a two-sided sign test, its going-first win rate per arm, and the overall going-first rate.

Usage: python ab_report.py OUT_DIR"""
import json
import os
import sys
from collections import defaultdict
from math import comb

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from windbot_decks import DECKS  # noqa: E402


def load(path):
    games = {}
    if os.path.exists(path):
        for line in open(path):
            r = json.loads(line)
            games[(r["first"], r["second"], r["game"])] = r["winner"]  # -1: no winner
    return games


def score(winner, seat):
    return 0.5 if winner == -1 else float(winner == seat)


def sign_test(better, worse):
    n = better + worse
    if n == 0:
        return 1.0
    return min(1.0, 2 * sum(comb(n, i) for i in range(min(better, worse) + 1)) / 2 ** n)


def main(out):
    arms = [load(os.path.join(out, f"arm{a}", "results.jsonl")) for a in (0, 1)]
    paired = sorted(set(arms[0]) & set(arms[1]))
    rows = defaultdict(lambda: defaultdict(list))  # (deck, opponent) -> {"off", "on", "first_off", "first_on"}
    for first, second, g in paired:
        for seat, deck, other in ((0, first, second), (1, second, first)):
            if deck not in DECKS:
                continue
            a, b = score(arms[0][(first, second, g)], seat), score(arms[1][(first, second, g)], seat)
            r = rows[(deck, other)]
            r["off"].append(a)
            r["on"].append(b)
            r["first_off" if seat == 0 else "second_off"].append(a)
            r["first_on" if seat == 0 else "second_on"].append(b)
    mean = lambda xs: sum(xs) / len(xs) if xs else float("nan")
    print(f"{len(paired)} paired games in {out}\n")
    print(f"{'executor deck':22} {'opponent':34} {'n':>4} {'off':>5} {'on':>5} {'better':>6} {'worse':>5} {'p':>5}"
          f"  {'1st off':>7} {'1st on':>6}  {'2nd off':>7} {'2nd on':>6}")
    for (deck, other), r in sorted(rows.items()):
        better = sum(b > a for a, b in zip(r["off"], r["on"]))
        worse = sum(b < a for a, b in zip(r["off"], r["on"]))
        print(f"{deck:22} {other:34} {len(r['off']):4} {mean(r['off']):5.0%} {mean(r['on']):5.0%} {better:6} {worse:5} "
              f"{sign_test(better, worse):5.2f}  {mean(r['first_off']):7.0%} {mean(r['first_on']):6.0%}  "
              f"{mean(r['second_off']):7.0%} {mean(r['second_on']):6.0%}")
    allo = [x for r in rows.values() for x in r["off"]]
    alln = [x for r in rows.values() for x in r["on"]]
    if allo:
        better = sum(b > a for a, b in zip(allo, alln))
        worse = sum(b < a for a, b in zip(allo, alln))
        print(f"\nall executor decks: off {mean(allo):.0%}  on {mean(alln):.0%}  better {better}  worse {worse}  "
              f"p {sign_test(better, worse):.3f}")
    for a in (0, 1):
        res = [score(w, 0) for k, w in arms[a].items() if k in paired]
        if res:
            print(f"arm {a}: going first wins {mean(res):.0%} of {len(res)} paired games")


if __name__ == "__main__":
    main(sys.argv[1])
