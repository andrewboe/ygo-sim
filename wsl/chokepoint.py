"""Chokepoint map (THEORY §2, objective 2): where should the opponent interrupt, and what does it cost us?

For each opening:
  1. Goldfish: search P1's best turn-1 line while P2 (holding a stacked hand-trap hand) passes, and log
     every window where P2 could have responded.
  2. For each window and each legal response (plus its first follow-up choice, e.g. Impermanence's
     target), replay the line to that point, apply the interruption, and re-search P1's best
     continuation: P1 adapts to the interruption.
  3. P2's best timing is the window and response that minimize P1's resulting board.

Run from ~/ygo/run:  python chokepoint.py DECK --opponent ash [--hands N]
"""
import argparse
import os
import sys
import time
from collections import Counter

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from goldfish import (INFO_KEYS, KIND_PASS, RUN, load, make_pool, search_opening,  # noqa: E402
                      set_opening)
from card_tags import all_tags  # noqa: E402

MAX_FOLLOWUPS = 4  # cap on first follow-up choices tried per response (e.g. Impermanence targets)


def card_names(names: dict) -> dict[int, str]:
    """Code-list id (1-based line in code_list.txt) -> card name."""
    codes = [int(l) for l in open(f"{RUN}/code_list.txt") if l.strip()]
    return {i + 1: names.get(c, str(c)) for i, c in enumerate(codes)}


def state_after(envs, k: int, opening: int, actions: list[int]) -> dict:
    """Replay `actions` in every env and return env 0's info at the next decision."""
    set_opening(opening)
    _, info = envs.reset()
    for a in actions:
        _, _, _, _, info = envs.step(np.full(k, a, dtype=np.int32))
    return {key: info[key][0] for key in INFO_KEYS}


def followups(envs, k, opening, prefix, response) -> list[tuple[int, int]]:
    """If P2 must choose right after `response` (e.g. a target), the (option, card) choices."""
    info = state_after(envs, k, opening, prefix + [response])
    if int(info["to_play"]) != 1 or int(info["msg"]) == 16:  # P1's turn again, or a new chain window
        return []
    n = int(info["num_options"])
    return [(o, int(info["option_card_"][o])) for o in range(n) if info["option_kinds_"][o] != KIND_PASS]


def map_opening(envs, k, opening, gens, cont_gens, alpha, tags, ids):
    base, _ = search_opening(envs, k, opening, gens, alpha, tags, None)
    trials = []
    for w in base.windows:
        prefix = base.actions[:w.step]
        for option, card, _kind in w.options:
            plans = [([option], card, 0)]
            follow = followups(envs, k, opening, prefix, option)
            if follow:
                plans = [([option, f], card, fcard) for f, fcard in follow[:MAX_FOLLOWUPS]]
            for plan, card_, target in plans:
                best, _ = search_opening(envs, k, opening, cont_gens, alpha, tags, None, prefix, plan,
                                         rng_salt=1 + w.step * 100 + option * 10 + len(plan))
                trials.append({"step": w.step, "after": ids.get(w.p1_card, "?"), "card": ids.get(card_, "?"),
                               "target": ids.get(target, "") if target else "", "score": best.score})
    return base, trials


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("deck")
    ap.add_argument("--opponent", default="ash", help="hand-trap set: _p2__<set>.ydk in run/decks")
    ap.add_argument("--hands", type=int, default=10)
    ap.add_argument("--first", type=int, default=0)
    ap.add_argument("--rollouts", type=int, default=32)
    ap.add_argument("--generations", type=int, default=15, help="goldfish search per opening")
    ap.add_argument("--cont-generations", type=int, default=8, help="re-search after each interruption")
    ap.add_argument("--alpha", type=float, default=1.0)
    ap.add_argument("--seed", type=int, default=1000)
    args = ap.parse_args()

    names = load(args.deck)
    ids = card_names(names)
    tags = all_tags()
    envs = make_pool(args.deck, args.rollouts, args.seed, opponent=f"_p2__{args.opponent}")
    t0 = time.time()
    base_scores, through, choke_cards, dead = [], [], Counter(), 0
    for h in range(args.first, args.first + args.hands):
        base, trials = map_opening(envs, args.rollouts, h, args.generations, args.cont_generations,
                                   args.alpha, tags, ids)
        base_scores.append(base.score)
        if not trials:
            dead += 1
            through.append(base.score)
            print(f"hand {h:3}: {base.score:5.2f}  no window for {args.opponent} on this line", flush=True)
            continue
        trials.sort(key=lambda r: r["score"])
        best = trials[0]
        through.append(best["score"])
        choke_cards[best["after"]] += 1
        target = f", then picking {best['target']}" if best["target"] else ""  # target or forced choice
        print(f"hand {h:3}: {base.score:5.2f} -> {best['score']:5.2f} with {best['card']}{target} "
              f"after {best['after']} (step {best['step']}; {len(trials)} options tried, "
              f"worst for P2: {trials[-1]['score']:.2f})", flush=True)

    b, t = np.array(base_scores), np.array(through)
    print(f"\n{args.deck} vs {args.opponent}: {args.hands} openings in {time.time() - t0:.0f}s")
    print(f"  goldfish board {b.mean():.2f} -> through best-timed {args.opponent} {t.mean():.2f} "
          f"(drop {np.mean(b - t):.2f}); no usable window on {dead}/{args.hands} lines")
    print(f"  most common chokepoints (P1 card the interruption answered): {choke_cards.most_common(5)}")


if __name__ == "__main__":
    main()
