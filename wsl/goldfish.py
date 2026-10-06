"""Goldfish v0: turn-1 rollouts of one deck against a passive opponent.

For each opening (a duel seed), K environments replay the same duel; each plays turn 1 with a random
policy that rarely ends the turn early, while the opponent declines everything. The board is recorded
when turn 2 starts. This version checks the plumbing (determinism, speed, board readout); a real
search/learned policy replaces the random one next.

Run from ~/ygo/run:  python goldfish.py DECK [--hands N] [--rollouts K]
"""
import argparse
import glob
import os
import sqlite3
import sys
import time

import numpy as np

sys.path.insert(0, os.path.expanduser("~/ygo/ygo-agent/ygoenv"))
import ygoenv  # noqa: E402
from ygoenv.edopro import init_module  # noqa: E402

RUN = os.path.expanduser("~/ygo/run")
MAX_OPTIONS = 24
KIND_ACTION, KIND_PASS, KIND_END, KIND_PHASE = 0, 1, 2, 3
END_TURN_P = 0.03  # chance per idle decision of taking "end turn"/"next phase" when other actions exist
MAX_STEPS = 400    # per rollout; turn-1 combos are far shorter
INFO_KEYS = ("num_options", "option_kinds_", "to_play", "turn", "board_", "field_codes_")


def policy(info, i, rng):
    """Action index for env i."""
    n = int(info["num_options"][i])
    kinds = info["option_kinds_"][i][:n]
    if int(info["to_play"][i]) == 1:  # passive opponent: decline when possible
        passes = np.flatnonzero(kinds == KIND_PASS)
        return int(passes[0]) if len(passes) else 0
    actions = np.flatnonzero(kinds == KIND_ACTION)
    others = np.flatnonzero(kinds != KIND_ACTION)
    if len(actions) and (not len(others) or rng.random() > END_TURN_P):
        return int(rng.choice(actions))
    return int(rng.choice(others)) if len(others) else int(rng.integers(n))


def make_pool(deck: str, k: int, base_seed: int):
    """K envs in lockstep: their n-th reset deals opening (base_seed + n) in every env."""
    return ygoenv.make(task_id="EDOPro-v0", env_type="gymnasium", num_envs=k, num_threads=min(k, 8),
                       seed=0, deck1=deck, deck2=deck, player=-1, max_options=MAX_OPTIONS,
                       n_history_actions=16, play_mode="self", lite=True, duel_seed=base_seed)


def run_hand(envs, k: int, rng):
    """Roll out turn 1 of the next opening in every env (resets all envs together)."""
    _, info = envs.reset()
    active = np.ones(k, dtype=bool)
    boards = [None] * k
    actions_taken = [[] for _ in range(k)]
    steps = 0
    for _ in range(MAX_STEPS):
        ids = np.flatnonzero(active)
        if not len(ids):
            break
        acts = np.array([policy(info, i, rng) for i in ids], dtype=np.int32)
        for i, a in zip(ids, acts):
            actions_taken[i].append(int(a))
        _, _, term, trunc, step_info = envs.step(acts, env_id=ids)
        steps += len(ids)
        for j, i in enumerate(step_info["env_id"]):  # results come back keyed by env_id
            for key in INFO_KEYS:
                info[key][i] = step_info[key][j]
            if term[j] or trunc[j] or step_info["turn"][j] >= 2:
                active[i] = False
                boards[i] = (step_info["board_"][j][0].copy(), step_info["field_codes_"][j][0].copy())
    return boards, actions_taken, steps


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("deck")
    ap.add_argument("--hands", type=int, default=20)
    ap.add_argument("--rollouts", type=int, default=32)
    args = ap.parse_args()

    os.chdir(RUN)
    decks = {os.path.basename(p)[:-4]: p for p in glob.glob(f"{RUN}/decks/*.ydk")}
    if args.deck not in decks:
        sys.exit(f"unknown deck {args.deck}; have: {sorted(d for d in decks if not d.startswith('_'))}")
    init_module(f"{RUN}/cards.cdb", f"{RUN}/code_list.txt", decks)
    names = dict(sqlite3.connect(f"{RUN}/cards.cdb").execute("select id, name from texts"))

    rng = np.random.default_rng(0)
    t0, total_steps, best = time.time(), 0, []
    envs = make_pool(args.deck, args.rollouts, base_seed=1000)
    for h in range(args.hands):
        boards, actions, steps = run_hand(envs, args.rollouts, rng)
        total_steps += steps
        sizes = [int(b[0][0] + b[0][1]) if b is not None else -1 for b in boards]  # monsters + spells/traps
        i = int(np.argmax(sizes))
        best.append(sizes[i])
        codes = [names.get(int(c), str(c)) for c in boards[i][1] if c] if boards[i] is not None else []
        print(f"hand {h}: best field size {sizes[i]} (median {int(np.median(sizes))}) "
              f"in {len(actions[i])} decisions: {codes}", flush=True)
    dt = time.time() - t0
    print(f"\n{args.deck}: mean best field size {np.mean(best):.2f} over {args.hands} hands; "
          f"{total_steps:,} steps in {dt:.0f}s ({total_steps / dt:,.0f} steps/s)")


def check_determinism(deck: str, seed: int = 7, k: int = 4):
    """Same seed + same actions must give the same board."""
    rng_actions = np.random.default_rng(1)
    envs = ygoenv.make(task_id="EDOPro-v0", env_type="gymnasium", num_envs=k, num_threads=k, seed=0,
                       deck1=deck, deck2=deck, player=-1, max_options=MAX_OPTIONS, n_history_actions=16,
                       play_mode="self", lite=True, duel_seed=seed)
    _, info = envs.reset()
    for _ in range(60):
        n = int(info["num_options"][0])
        a = int(rng_actions.integers(n))
        _, _, term, trunc, info = envs.step(np.full(k, a, dtype=np.int32))
        if term[0]:
            break
    same = all((info["board_"][i] == info["board_"][0]).all() and
               (info["field_codes_"][i] == info["field_codes_"][0]).all() for i in range(k))
    print(f"determinism ({k} envs, same seed and actions): {'OK' if same else 'MISMATCH'}")
    envs.close()


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[2] == "--check":
        os.chdir(RUN)
        decks = {os.path.basename(p)[:-4]: p for p in glob.glob(f"{RUN}/decks/*.ydk")}
        init_module(f"{RUN}/cards.cdb", f"{RUN}/code_list.txt", decks)
        check_determinism(sys.argv[1])
    else:
        main()
