"""Turn-1 lines a deck can make: finds openings holding each starter, searches turn 1 hard (goldfish NRPA) and
prints the best line step by step (decision type, choice, card). Used to source and check combo lines for a
deck executor (docs/windbot_porting.md).

Run from ~/ygo/run:  python goldfish_lines.py DECK STARTERS [SCAN] [ROLLOUTS] [GENERATIONS] [PER_STARTER]
  STARTERS: comma list of passcodes; SCAN: openings scanned for them."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402

import goldfish as gf  # noqa: E402
from card_tags import all_tags  # noqa: E402

deck = sys.argv[1]
starters = [int(x) for x in sys.argv[2].split(",")]
scan = int(sys.argv[3]) if len(sys.argv) > 3 else 120
K = int(sys.argv[4]) if len(sys.argv) > 4 else 32
G = int(sys.argv[5]) if len(sys.argv) > 5 else 20
per = int(sys.argv[6]) if len(sys.argv) > 6 else 2
names = gf.load(deck)
tags = all_tags()
codes = [int(l) for l in open(f"{gf.RUN}/code_list.txt") if l.strip()]
id_to_code = [0] + codes
envs = gf.make_pool(deck, K, 1000, opponent="_p2__none")
STARTERS = {names.get(c, str(c)): c for c in starters}
hands = {}
for h in range(scan):
    gf.set_opening(h)
    _, info = envs.reset()
    hands[h] = [int(c) for c in info["hand_codes_"][0][0] if c]
picked = []
for label, code in STARTERS.items():
    hits = [h for h, hand in hands.items() if code in hand and h not in picked][:per]
    picked += hits
    print(f"{label}: openings {hits}")
rng = np.random.default_rng(0)
LET = {"s": "summon", "c": "sp.summon", "r": "repos", "m": "set mon", "t": "set", "v": "activate",
       "b": "battle", "e": "end"}
for h in picked:
    best, first = gf.search_opening(envs, K, h, G, 1.0, tags, rng)
    print(f"\n=== opening {h}: hand {[names.get(c) for c in hands[h]]}")
    print(f"    score {best.score:.2f} (first batch {first:.2f}); board "
          f"{[('(set) ' if c < 0 else '') + names.get(abs(c), str(c)) for c in best.board if c]}")
    # replay the line in env 0 and describe P1's choices
    gf.set_opening(h)
    _, info = envs.reset()
    info = {k: info[k].copy() for k in gf.INFO_KEYS}
    for step, a in enumerate(best.actions[:best.turn1_len]):
        acts = np.zeros(K, np.int32)
        acts[0] = a
        if int(info["to_play"][0]) == 0 and int(info["num_options"][0]) > 1:
            cid = int(info["option_card_"][0][a])
            card = names.get(id_to_code[cid], "") if 0 < cid < len(id_to_code) else ""
            act = chr(int(info["option_act_"][0][a]))
            print(f"    msg {int(info['msg'][0]):2} {LET.get(act, act) if int(info['msg'][0]) == 11 else act:9} {card}")
        _, _, _, _, step_info = envs.step(acts)
        for j, e in enumerate(step_info["env_id"]):
            for k in gf.INFO_KEYS:
                info[k][e] = step_info[k][j]
