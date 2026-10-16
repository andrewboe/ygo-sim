"""Goldfish A/B for a deck executor: does its prior help the turn-1 search? The same openings and RNG streams are
searched with the executor's priors off and on, at a small budget, where priors matter most; prints both best
boards per opening (with the watched cards that ended on board) and the means.

Run from ~/ygo/run:  python executor_ab.py DECK OPENINGS ROLLOUTS GENERATIONS [WATCH]
  OPENINGS: N (openings 0..N-1) or a comma list; WATCH: comma list of passcodes to report on board."""
import os
import sys

os.environ["YGOSIM_CARD_HANDLERS"] = "1"
os.environ["YGOSIM_CONTEXT"] = "1"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402

import card_handlers as ch  # noqa: E402
import goldfish as gf  # noqa: E402
from card_tags import all_tags  # noqa: E402

deck = sys.argv[1]
openings = [int(x) for x in sys.argv[2].split(",")] if "," in sys.argv[2] else list(range(int(sys.argv[2])))
K, G = int(sys.argv[3]), int(sys.argv[4])
watch = [int(x) for x in sys.argv[5].split(",")] if len(sys.argv) > 5 else []
names = gf.load(deck)
tags = all_tags()
ids = [0] + [int(l) for l in open(f"{gf.RUN}/code_list.txt") if l.strip()]
envs = gf.make_pool(deck, K, 1000, opponent="_p2__none")
ch.set_decks(deck, "_p2__none")


class Hook:
    def reset(self, k):
        ch.reset(k)

    def offsets(self, info, i, n):
        return ch.windbot_offsets(info, i, n, ids)

    def chosen(self, i, o):
        ch.chosen(i, 0, o)


rows = []
for h in openings:
    res = []
    for arm in (None, Hook()):
        gf.PRIOR_HOOK = arm
        rng = np.random.default_rng(0)
        best, first = gf.search_opening(envs, K, h, G, 1.0, tags, rng)
        board = [abs(c) for c in best.board if c]
        res.append((best.score, first, [w for w in watch if w in board]))
    rows.append(res)
    (s0, f0, w0), (s1, f1, w1) = res
    print(f"opening {h:3}: off {s0:5.2f} (first {f0:5.2f}) {[names.get(w) for w in w0]} | "
          f"on {s1:5.2f} (first {f1:5.2f}) {[names.get(w) for w in w1]}", flush=True)
off = np.array([r[0][0] for r in rows])
on = np.array([r[1][0] for r in rows])
f_off = np.array([r[0][1] for r in rows])
f_on = np.array([r[1][1] for r in rows])
print(f"\n{deck}: {len(rows)} openings, {K}x{G}")
print(f"  best line   off {off.mean():.2f}  on {on.mean():.2f}  (on better {np.mean(on > off):.0%}, worse {np.mean(on < off):.0%})")
print(f"  first batch off {f_off.mean():.2f}  on {f_on.mean():.2f}")
for w in watch:
    print(f"  {names.get(w)} on board: off {np.mean([w in r[0][2] for r in rows]):.0%}  on {np.mean([w in r[1][2] for r in rows]):.0%}")
