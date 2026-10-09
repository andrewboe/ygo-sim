"""Weak-point suite S1 (docs/gap_analysis.md): combo depth. A deck's turn 1 against a passive opponent
(stage 1's stacked deck: no interruptions), with the full game search, then the end board probe-scored
(live interruptions). With TRAP (ash, imperm, nibiru, droll, fuwalos, ...) it's suite S2: the opponent
opens that hand trap (stacked _p2__<trap> deck) and the searcher plays with its belief model (it isn't told).
Run in WSL from ~/ygo/run: python suite_s1.py DECK [N_DEALS] [FIRST_DEAL] [TRAP]"""
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
# Each deck gets its own deals: with a shared seed, decks whose lists group hand traps alike brick together.
import zlib
first = int(sys.argv[3]) if len(sys.argv) > 3 else 94000 + zlib.crc32(deck.encode()) % 50000 * 10
trap = sys.argv[4] if len(sys.argv) > 4 else "none"
mode, opp = ("passive" if trap == "none" else trap), f"_p2__{trap}"
names = load(deck); load(opp); tags = all_tags()
id_to_code = [0] + [int(l) for l in open(os.path.expanduser("~/ygo/run/code_list.txt")) if l.strip()]
envs = ygoenv.make(task_id="EDOPro-v0", env_type="gymnasium", num_envs=32, num_threads=32, seed=0, deck1=deck, deck2=opp,
                   player=-1, max_options=G.MAX_OPTIONS, n_history_actions=16, play_mode="self", lite=True,
                   duel_seed=5000, shuffle2=False)  # _p2__ decks are stacked: deal in file order
G.BELIEF = None if trap == "none" else Belief()
seen, offered_seen = [], []
orig = G.live_value
def lv(board, hand, offered, t, idc):
    v = orig(board, hand, offered, t, idc); seen.append(v)
    offered_seen.append(sorted({names.get(idc[c], str(c)) for c in offered if 0 < c < len(idc)}))
    return v
G.live_value = lv
nm = lambda c: names.get(abs(int(c)), str(c))
vals = []
for g in range(first, first + n_deals):
    set_opening(g); rng = np.random.default_rng(g)
    _, info0 = envs.reset()
    hand0 = [nm(c) for c in info0["hand_codes_"][0][0] if c]
    r = G.play_turn(envs, 32, [], 0, 1, 30, 1.0, tags, id_to_code, rng)
    seen.clear(); offered_seen.clear()
    G.BELIEF = None  # measure the real board only
    from collections import defaultdict
    G.turn_batch(envs, 32, r.actions, 0, 1, defaultdict(float), tags, id_to_code, rng, defaultdict(float), probe_now=True)
    G.BELIEF = None if trap == "none" else Belief()
    live = float(np.median(seen)) if seen else float("nan")
    _, _, info = G.current_state(envs, 32, r.actions)
    opp_hand = [nm(c) for c in info["hand_codes_"][0][1] if c]
    trap_used = trap != "none" and not any(n not in ("Card Trooper", "Upstart Goblin") for n in opp_hand)
    board = [("(set) " if c < 0 else "") + nm(c) for c in info["field_codes_"][0][0] if c]
    vals.append(live)
    used = f" | {trap} used: {trap_used}" if trap != "none" else ""
    print(f"{deck} deal {g}: live {live:.2f}{used} | hand {hand0} | board {board} | responded {offered_seen[0] if offered_seen else []}", flush=True)
print(f"{'S1' if trap == 'none' else 'S2 ' + trap} {deck}: mean live interruptions {np.nanmean(vals):.2f} over {len(vals)} deals")
