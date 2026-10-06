"""Goldfish: how strong a turn-1 board does a deck make, against a passive opponent?

For each opening hand, every env replays the same duel (deterministic seed). Turn 1 is searched with
NRPA (Nested Rollout Policy Adaptation): batches of rollouts sample choices from a softmax policy over
option identities (card + action, from the env's option hashes); after each batch the policy shifts
toward the best line found so far. The opponent declines everything.

A board is scored in "interruptions" (card_tags.py): tagged cards on the field (face-up/set) plus
hand traps kept in hand, with small tiebreaks for cards in hand and on the field.

Run from ~/ygo/run:  python goldfish.py DECK [--hands N] [--rollouts K] [--generations G]
                     python goldfish.py DECK --check     (determinism check)
"""
import argparse
import glob
import os
import sqlite3
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np

sys.path.insert(0, os.path.expanduser("~/ygo/ygo-agent/ygoenv"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ygoenv  # noqa: E402
from ygoenv.edopro import init_module  # noqa: E402
from ygoenv.edopro.edopro_ygoenv import set_opening  # noqa: E402
from card_tags import all_tags  # noqa: E402

RUN = os.path.expanduser("~/ygo/run")
MAX_OPTIONS = 24
KIND_ACTION, KIND_PASS, KIND_END, KIND_PHASE = 0, 1, 2, 3
PRIOR = {KIND_ACTION: 0.0, KIND_PASS: -1.0, KIND_END: -3.0, KIND_PHASE: -3.0}  # logit offsets
MAX_STEPS = 300  # per rollout; turn-1 combos are far shorter
INFO_KEYS = ("num_options", "option_kinds_", "option_hash_", "option_card_", "to_play", "turn", "msg",
             "board_", "field_codes_", "hand_codes_")


@dataclass
class Window:
    """A point where P2 could interrupt (THEORY §2): a P2 decision with a non-pass option."""
    step: int        # index into Rollout.actions
    msg: int         # decision type (16 = chain)
    options: list    # (option index, card id, kind) for each non-pass option
    p1_card: int     # card id of P1's most recent choice, i.e. what P2 would be responding to


@dataclass
class Rollout:
    trace: list = field(default_factory=list)    # (option hashes, priors, chosen) per searched P1 decision
    actions: list = field(default_factory=list)  # every action taken, both players, for exact replay
    windows: list = field(default_factory=list)  # Window, for P2 decisions where it passed
    score: float = float("-inf")
    board: list = field(default_factory=list)  # field codes, negative = face-down
    hand: list = field(default_factory=list)


def score_board(field_codes, hand_codes, tags) -> float:
    """Interruptions on board + hand traps in hand, with tiebreaks for resources."""
    total, n_field = 0.0, 0
    for c in field_codes:
        if c:
            n_field += 1
            t = tags.get(abs(int(c)))
            if t:
                total += t["set"] if c < 0 else t["field"]
    hand = [int(c) for c in hand_codes if c]
    total += sum(tags.get(c, {}).get("hand", 0.0) for c in hand)
    return total + 0.1 * len(hand) + 0.02 * n_field


def sample(hashes, priors, weights, rng) -> tuple[int, np.ndarray]:
    logits = np.array([weights[h] for h in hashes]) + priors
    p = np.exp(logits - logits.max())
    p /= p.sum()
    return int(rng.choice(len(p), p=p)), p


def rollout_batch(envs, k, weights, tags, rng, prefix=(), p2_plan=()) -> list[Rollout]:
    """K rollouts of turn 1 of the current opening.

    The first len(prefix) actions are forced (both players), for exact replay to a window. After
    that, P2's next decisions follow p2_plan in order (e.g. [activate Ash] or [activate Imperm,
    target]), then P2 passes. P1 samples from the softmax policy throughout, after the prefix.
    """
    _, info = envs.reset()
    info = {key: info[key].copy() for key in INFO_KEYS}
    out = [Rollout() for _ in range(k)]
    active = np.ones(k, dtype=bool)
    plan_pos = np.zeros(k, dtype=int)
    last_p1_card = np.zeros(k, dtype=int)
    for _ in range(MAX_STEPS):
        if not active.any():
            break
        # Step every env: envpool's sync mode can deadlock waiting for a full batch when only a
        # subset is stepped. Finished envs get a filler action and their results are ignored.
        acts = np.zeros(k, dtype=np.int32)
        for i in np.flatnonzero(active):
            n = int(info["num_options"][i])
            kinds = info["option_kinds_"][i][:n]
            t = len(out[i].actions)
            if t < len(prefix):
                acts[i] = prefix[t]
            elif int(info["to_play"][i]) == 1:
                if plan_pos[i] < len(p2_plan):
                    acts[i] = p2_plan[plan_pos[i]]
                    plan_pos[i] += 1
                else:  # passive opponent: decline when possible, and log the window if it could act
                    passes = np.flatnonzero(kinds == KIND_PASS)
                    acts[i] = passes[0] if len(passes) else 0
                    acting = [(o, int(info["option_card_"][i][o]), int(kinds[o]))
                              for o in range(n) if kinds[o] != KIND_PASS]
                    if acting and len(passes):
                        out[i].windows.append(Window(t, int(info["msg"][i]), acting, int(last_p1_card[i])))
            else:
                hashes = info["option_hash_"][i][:n].tolist()
                priors = np.array([PRIOR[int(x)] for x in kinds])
                acts[i], _ = sample(hashes, priors, weights, rng)
                out[i].trace.append((hashes, priors, int(acts[i])))
            if int(info["to_play"][i]) == 0 and info["option_card_"][i][acts[i]]:
                last_p1_card[i] = int(info["option_card_"][i][acts[i]])
            out[i].actions.append(int(acts[i]))
        _, _, term, trunc, step = envs.step(acts)
        for j, i in enumerate(step["env_id"]):
            if not active[i]:
                continue
            for key in INFO_KEYS:
                info[key][i] = step[key][j]
            if term[j] or trunc[j] or step["turn"][j] >= 2:
                active[i] = False
                out[i].board = step["field_codes_"][j][0].tolist()
                out[i].hand = step["hand_codes_"][j][0].tolist()
                out[i].score = score_board(out[i].board, out[i].hand, tags)
    return out


def adapt(weights, best: Rollout, alpha: float) -> None:
    """NRPA: move the policy toward the best line's choices."""
    old = dict(weights)
    for hashes, priors, chosen in best.trace:
        logits = np.array([old.get(h, 0.0) for h in hashes]) + priors
        p = np.exp(logits - logits.max())
        p /= p.sum()
        for h, ph in zip(hashes, p):
            weights[h] -= alpha * ph
        weights[hashes[chosen]] += alpha


def search_opening(envs, k, opening, generations, alpha, tags, rng, prefix=(), p2_plan=(),
                   rng_salt=0) -> tuple[Rollout, float]:
    """Best turn-1 line for one opening (optionally continuing after a forced prefix and P2 plan);
    also returns the first (untrained) batch's best score."""
    set_opening(opening)
    rng = np.random.default_rng([opening, rng_salt])  # per-opening stream: any hand reproduces alone
    weights = defaultdict(float)
    best, first = Rollout(), None
    for _ in range(generations):
        batch = rollout_batch(envs, k, weights, tags, rng, prefix, p2_plan)
        top = max(batch, key=lambda r: r.score)
        first = top.score if first is None else first
        if top.score > best.score:
            best = top
        adapt(weights, best, alpha)
    return best, first


def make_pool(deck: str, k: int, base_seed: int, opponent: str | None = None):
    """K lockstep envs. `opponent` is a stacked P2 deck (e.g. '_p2__ash'), dealt in file order."""
    return ygoenv.make(task_id="EDOPro-v0", env_type="gymnasium", num_envs=k, num_threads=k,
                       seed=0, deck1=deck, deck2=opponent or deck, player=-1, max_options=MAX_OPTIONS,
                       n_history_actions=16, play_mode="self", lite=True, duel_seed=base_seed,
                       shuffle2=opponent is None)


def load(deck=None):
    os.chdir(RUN)
    decks = {os.path.basename(p)[:-4]: p for p in glob.glob(f"{RUN}/decks/*.ydk")}
    if deck is not None and deck not in decks:
        sys.exit(f"unknown deck {deck}; have: {sorted(d for d in decks if not d.startswith('_'))}")
    init_module(f"{RUN}/cards.cdb", f"{RUN}/code_list.txt", decks)
    return dict(sqlite3.connect(f"{RUN}/cards.cdb").execute("select id, name from texts"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("deck")
    ap.add_argument("--hands", type=int, default=20)
    ap.add_argument("--rollouts", type=int, default=32)
    ap.add_argument("--generations", type=int, default=15)
    ap.add_argument("--alpha", type=float, default=1.0)
    ap.add_argument("--seed", type=int, default=1000, help="duel seed base; opening n uses seed + n")
    ap.add_argument("--first", type=int, default=0, help="index of the first opening")
    args = ap.parse_args()

    names = load(args.deck)
    tags = all_tags()
    rng = np.random.default_rng(0)
    envs = make_pool(args.deck, args.rollouts, args.seed)
    t0, scores, firsts = time.time(), [], []
    for h in range(args.first, args.first + args.hands):
        best, first = search_opening(envs, args.rollouts, h, args.generations, args.alpha, tags, rng)
        scores.append(best.score)
        firsts.append(first)
        board = [("(set) " if c < 0 else "") + names.get(abs(c), str(c)) for c in best.board if c]
        held = [names.get(c, str(c)) for c in best.hand if c and tags.get(c, {}).get("hand")]
        print(f"hand {h:3}: {best.score:5.2f} (random: {first:5.2f}) in {len(best.trace):3} decisions | "
              f"board: {board} | hand traps held: {held}", flush=True)
    dt = time.time() - t0
    s = np.array(scores)
    print(f"\n{args.deck}: {args.hands} openings, {args.rollouts}x{args.generations} rollouts each, {dt:.0f}s")
    print(f"  mean interruptions {s.mean():.2f} (random-policy best: {np.mean(firsts):.2f})")
    for t in (1, 2, 3, 4):
        print(f"  P(>= {t}) = {(s >= t).mean():.0%}")


def check_determinism(deck: str, k: int = 4):
    """Same opening + same actions must give the same board."""
    load(deck)
    set_opening(7)
    rng = np.random.default_rng(1)
    envs = make_pool(deck, k, 0)
    _, info = envs.reset()
    for _ in range(60):
        a = int(rng.integers(int(info["num_options"][0])))
        _, _, term, _, info = envs.step(np.full(k, a, dtype=np.int32))
        if term[0]:
            break
    same = all((info["field_codes_"][i] == info["field_codes_"][0]).all() and
               (info["hand_codes_"][i] == info["hand_codes_"][0]).all() for i in range(k))
    print(f"determinism ({k} envs, same opening and actions): {'OK' if same else 'MISMATCH'}")


if __name__ == "__main__":
    if "--check" in sys.argv:
        check_determinism(sys.argv[1])
    else:
        main()
