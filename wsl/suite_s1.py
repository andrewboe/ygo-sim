"""Weak-point suite S1 (docs/gap_analysis.md): combo depth. A deck's turn 1 against a passive opponent
(stage 1's stacked deck: no interruptions), with the full game search, then the end board probe-scored
(live interruptions). Run in WSL from ~/ygo/run: python suite_s1.py DECK [N_DEALS]"""
import os, sys
sys.path.insert(0, os.path.expanduser("~/ygo/ygo-agent/ygoenv"))
sys.path.insert(0, "/mnt/c/Users/andre/Desktop/ygo-sim/wsl")
import numpy as np, ygoenv
import game as G
from goldfish import load, set_opening
from card_tags import all_tags
from belief import Belief
deck = sys.argv[1]
n_deals = int(sys.argv[2]) if len(sys.argv) > 2 else 3
mode, opp = "passive", "_p2__none"
names = load(deck); load(opp); tags = all_tags()
id_to_code = [0] + [int(l) for l in open(os.path.expanduser("~/ygo/run/code_list.txt")) if l.strip()]
envs = ygoenv.make(task_id="EDOPro-v0", env_type="gymnasium", num_envs=32, num_threads=32, seed=0, deck1=deck, deck2=opp,
                   player=-1, max_options=G.MAX_OPTIONS, n_history_actions=16, play_mode="self", lite=True,
                   duel_seed=5000, shuffle2=mode != "passive")
G.BELIEF = None if mode == "passive" else Belief()
seen = []
orig = G.live_value
def lv(board, hand, offered, t, idc):
    v = orig(board, hand, offered, t, idc); seen.append(v); return v
G.live_value = lv
nm = lambda c: names.get(abs(int(c)), str(c))
vals = []
for g in range(94000, 94000 + n_deals):
    set_opening(g); rng = np.random.default_rng(g)
    r = G.play_turn(envs, 32, [], 0, 1, 30, 1.0, tags, id_to_code, rng)
    seen.clear()
    G.BELIEF = None  # measure the real board only
    from collections import defaultdict
    G.turn_batch(envs, 32, r.actions, 0, 1, defaultdict(float), tags, id_to_code, rng, defaultdict(float), probe_now=True)
    G.BELIEF = None if mode == "passive" else Belief()
    live = float(np.median(seen)) if seen else float("nan")
    _, _, info = G.current_state(envs, 32, r.actions)
    board = [("(set) " if c < 0 else "") + nm(c) for c in info["field_codes_"][0][0] if c]
    vals.append(live)
    print(f"{deck} deal {g}: live {live:.2f} | board {board}", flush=True)
print(f"S1 {deck}: mean live interruptions {np.nanmean(vals):.2f} over {len(vals)} deals")
