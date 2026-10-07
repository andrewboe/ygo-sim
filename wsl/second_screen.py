"""Funnel stage 1, going second: can the candidate break a real turn-1 board?

A field deck goes first and searches its turn 1; the candidate searches its turn 2 against that board
(co-evolved responder on both turns, game.py). Score per game: 1 if the candidate wins during turn 2 (OTK
or the board player is out), otherwise its win probability after turn 2 from the fitted evaluation.
Logged to data/screen/second.jsonl.

Run from ~/ygo/run:  python second_screen.py CANDIDATE OPPONENT [--games N]
"""
import argparse
import json
import math
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.expanduser("~/ygo/ygo-agent/ygoenv"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ygoenv  # noqa: E402
from game import EVAL_WEIGHTS, MAX_OPTIONS, play_game  # noqa: E402
from goldfish import load  # noqa: E402
from card_tags import all_tags  # noqa: E402

OUT = "/mnt/c/Users/andre/Desktop/ygo-sim/data/screen"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("candidate", help="deck going second")
    ap.add_argument("opponent", help="field deck going first")
    ap.add_argument("--games", type=int, default=20)
    ap.add_argument("--rollouts", type=int, default=32)
    ap.add_argument("--generations", type=int, default=10)
    ap.add_argument("--seed", type=int, default=7000)
    args = ap.parse_args()

    load(args.candidate)
    load(args.opponent)
    tags = all_tags()
    id_to_code = [0] + [int(l) for l in open(os.path.expanduser("~/ygo/run/code_list.txt")) if l.strip()]
    envs = ygoenv.make(task_id="EDOPro-v0", env_type="gymnasium", num_envs=args.rollouts,
                       num_threads=args.rollouts, seed=0, deck1=args.opponent, deck2=args.candidate, player=-1,
                       max_options=MAX_OPTIONS, n_history_actions=16, play_mode="self", lite=True,
                       duel_seed=args.seed)
    os.makedirs(OUT, exist_ok=True)
    log = open(f"{OUT}/second.jsonl", "a")
    scores, otk, t0 = [], 0, time.time()
    for g in range(args.games):
        r = play_game(envs, args.rollouts, g, 2, args.generations, 1.0, tags, id_to_code)
        if r["by"] == "game":
            s = 1.0 if r["winner"] == 1 else 0.0
            otk += r["winner"] == 1
        else:
            f = next(f for p, f in reversed(r["positions"]) if p == 1)  # candidate's end of turn 2
            s = 1 / (1 + math.exp(-sum(EVAL_WEIGHTS.get(k, 0.0) * v for k, v in f.items())))
        scores.append(s)
        log.write(json.dumps({"candidate": args.candidate, "opponent": args.opponent, "game": g,
                              "seed": args.seed, "score": s, "by": r["by"], "winner": r["winner"]}) + "\n")
        log.flush()
    s = np.array(scores)
    print(f"{args.candidate} (2nd) vs {args.opponent} (1st): score {s.mean():.2f} +- {s.std() / len(s) ** .5:.2f}, "
          f"wins in turn 2 {otk}/{args.games} [{time.time() - t0:.0f}s]")


if __name__ == "__main__":
    main()
