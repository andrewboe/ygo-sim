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
import json
import os
import sys
import time
from collections import Counter, defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from goldfish import (INFO_KEYS, KIND_PASS, RUN, P2Rule, load, make_pool, make_probe,  # noqa: E402
                      rollout_batch, search_opening, set_opening)

# Search results are kept as training data for the pilot's imitation stage (THEORY §5).
SEARCH_LOG = "/mnt/c/Users/andre/Desktop/ygo-sim/data/search"
from card_tags import all_tags  # noqa: E402

MAX_FOLLOWUPS = 4  # cap on first follow-up choices tried per response (e.g. Impermanence targets)
MAX_WINDOWS = 12   # per line, spread evenly (Impermanence is legal almost everywhere)


def distinct_windows(windows: list) -> list:
    """Windows with no P1 decision in between share a game state; keep the first of each run,
    then at most MAX_WINDOWS, spread evenly over the line."""
    kept, last = [], None
    for w in windows:
        if w.p1_decisions != last:
            kept.append(w)
            last = w.p1_decisions
    if len(kept) > MAX_WINDOWS:
        kept = [kept[round(i * (len(kept) - 1) / (MAX_WINDOWS - 1))] for i in range(MAX_WINDOWS)]
    return kept


def card_names(names: dict) -> dict[int, str]:
    """Code-list id (1-based line in code_list.txt) -> card name."""
    codes = [int(l) for l in open(f"{RUN}/code_list.txt") if l.strip()]
    return {i + 1: names.get(c, str(c)) for i, c in enumerate(codes)}


def state_after(envs, k: int, opening: int, actions: list[int]) -> dict:
    """Replay `actions` in every env and return env 0's info at the next decision."""
    set_opening(opening)
    _, info = envs.reset()
    for t, a in enumerate(actions):  # replay flag on all but the last move (goldfish.REPLAY)
        flag = 1000 if t < len(actions) - 1 else 0
        _, _, _, _, info = envs.step(np.full(k, a + flag, dtype=np.int32))
    return {key: info[key][0] for key in INFO_KEYS}


def followups(envs, k, opening, prefix, response) -> list[tuple[int, int]]:
    """If P2 must choose right after `response` (e.g. a target), the (option, card) choices."""
    info = state_after(envs, k, opening, prefix + [response])
    if int(info["to_play"]) != 1 or int(info["msg"]) == 16:  # P1's turn again, or a new chain window
        return []
    n = int(info["num_options"])
    return [(o, int(info["option_card_"][o])) for o in range(n) if info["option_kinds_"][o] != KIND_PASS]


def interruption_trials(envs, k, opening, line, cont_gens, alpha, tags, ids, probe=None) -> list[dict]:
    """For every window on `line` and every legal response (+ first follow-up): P1's best board after
    re-searching its continuation. P2's best timing is the minimum."""
    trials = []
    for w in distinct_windows(line.windows):
        prefix = line.actions[:w.step]
        for option, card, _kind in w.options:
            plans = [([option], card, 0)]
            follow = followups(envs, k, opening, prefix, option)
            if follow:
                plans = [([option, f], card, fcard) for f, fcard in follow[:MAX_FOLLOWUPS]]
            for plan, card_, target in plans:
                best, _ = search_opening(envs, k, opening, cont_gens, alpha, tags, None, prefix, plan,
                                         rng_salt=1 + w.step * 100 + option * 10 + len(plan), probe=probe)
                trials.append({"step": w.step, "after": ids.get(w.p1_card, "?"), "after_id": w.p1_card,
                               "card_id": card_, "card": ids.get(card_, "?"),
                               "target": ids.get(target, "") if target else "", "plan": plan,
                               "prefix_len": w.step, "score": best.score, "reply": best.actions,
                               "line": best})  # P1's continuation (with its own later windows); not logged
    return sorted(trials, key=lambda r: r["score"])


def pair_trials(envs, k, opening, line, first_trials, cont_gens, alpha, tags, ids, probe, top=3) -> list[dict]:
    """Two interruptions (e.g. Ash + Impermanence), nested (THEORY §2, multiple interruptions).

    The first is chosen from the `top` best single-interruption timings per hand trap; for each, the
    second is mapped exactly on the continuation P1 plays after the first. Each entry's score is P1's
    board after both, or after only the first if P1's continuation gives no window for the second."""
    by_trap = defaultdict(list)
    for t in first_trials:
        by_trap[t["card_id"]].append(t)
    out = []
    for trap, trials in by_trap.items():
        for first in trials[:top]:
            # first["line"] is P1's best continuation after the first interruption; its windows are
            # the second hand trap's chances (the first trap is spent, so it can't appear again).
            seconds = interruption_trials(envs, k, opening, first["line"], cont_gens, alpha, tags, ids, probe)
            second = seconds[0] if seconds and seconds[0]["score"] < first["score"] else None
            out.append({**first, "then": second, "score": second["score"] if second else first["score"]})
    return sorted(out, key=lambda r: r["score"])


def loggable(trial: dict) -> dict:
    """A trial without in-memory rollouts, for the JSONL training log."""
    t = {k: v for k, v in trial.items() if k not in ("line", "then")}
    if trial.get("then"):
        t["then"] = loggable(trial["then"])
    return t


def worst_case(line, trials) -> float:
    """P1's board after P2's best choice, which includes not interrupting at all."""
    return min([line.score] + [t["score"] for t in trials])


def robust_lines(envs, k, opening, gens, cont_gens, alpha, tags, ids, probe, rounds) -> list:
    """Max-min candidates by iterated best response (double oracle, THEORY §2.3-4).

    Round 0 is the goldfish line. Each round, P2's best timing against the newest line becomes a rule
    ("use the trap right after P1 uses card X"); P1 then re-searches with that rule live in its
    rollouts, which finds baits and workarounds. The strategy's own uninterrupted line (greedy replay
    of the learned policy) is the next candidate. Returns [(line, exact trials)] for every candidate.
    """
    line, _ = search_opening(envs, k, opening, gens, alpha, tags, None, probe=probe)
    out = [(line, interruption_trials(envs, k, opening, line, cont_gens, alpha, tags, ids, probe))]
    rules = []
    for r in range(rounds):
        trials = out[-1][1]
        if not trials:
            break  # no window on the newest line: nothing left for P2 to exploit
        rule = P2Rule(trap=trials[0]["card_id"], trigger=trials[0]["after_id"])
        if rule in rules:
            break
        rules.append(rule)
        weights = {}
        search_opening(envs, k, opening, gens, alpha, tags, None, rng_salt=1000 + r, probe=probe,
                       p2_rule=rule, weights_out=weights)
        set_opening(opening)
        greedy = max(rollout_batch(envs, k, defaultdict(float, weights), tags, np.random.default_rng(0),
                                   probe=probe, greedy=True), key=lambda x: x.score)
        out.append((greedy, interruption_trials(envs, k, opening, greedy, cont_gens, alpha, tags, ids, probe)))
    return out


def map_opening(envs, k, opening, gens, cont_gens, alpha, tags, ids, probe=None):
    base, _ = search_opening(envs, k, opening, gens, alpha, tags, None, probe=probe)
    return base, interruption_trials(envs, k, opening, base, cont_gens, alpha, tags, ids, probe)


ODDS_FILE = "/mnt/c/Users/andre/Desktop/ygo-sim/data/field/hand_trap_odds.json"


def resolve_p_trap(value: str, opponent: str) -> float:
    """A number, or 'auto': P(opponent opens >= 1 of the set's traps) from field odds, assuming
    independence across different traps."""
    if value != "auto":
        return float(value)
    from setup_runtime import HAND_TRAP_SETS
    odds = json.load(open(ODDS_FILE))["odds"]
    p_none = 1.0
    for name in HAND_TRAP_SETS[opponent]:
        p_none *= 1 - odds.get(name, 0.5)
    return 1 - p_none


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
    ap.add_argument("--no-probe", action="store_true", help="tag-based board score instead of probing")
    ap.add_argument("--pair", action="store_true",
                    help="opponent holds two hand traps (e.g. --opponent ash-imperm): nest the second")
    ap.add_argument("--robust", type=int, default=0, metavar="ROUNDS",
                    help="robust line (THEORY §2.3): candidates from ROUNDS of iterated best response")
    ap.add_argument("--p-trap", default="auto",
                    help="chance P2 holds the trap; picks the line maximizing p*worst + (1-p)*goldfish "
                         "(1.0 = pure max-min; 'auto' = field odds from `ygosim hand-traps`)")
    args = ap.parse_args()

    names = load(args.deck)
    ids = card_names(names)
    tags = all_tags()
    args.p_trap = resolve_p_trap(args.p_trap, args.opponent)
    print(f"P(opponent holds the trap) = {args.p_trap:.2f}", flush=True)
    probe = None if args.no_probe else make_probe(names)
    envs = make_pool(args.deck, args.rollouts, args.seed, opponent=f"_p2__{args.opponent}")
    os.makedirs(SEARCH_LOG, exist_ok=True)
    log = open(f"{SEARCH_LOG}/{args.deck}__{args.opponent}{'__robust' if args.robust else ''}.jsonl", "a")
    t0 = time.time()
    rows, choke_cards = [], Counter()
    for h in range(args.first, args.first + args.hands):
        if args.robust:
            evaluated = robust_lines(envs, args.rollouts, h, args.generations, args.cont_generations,
                                     args.alpha, tags, ids, probe, args.robust)
            goldfish, g_trials = evaluated[0]
            # Expected board: P2 holds the trap with probability p (then times it best), else passes.
            line, trials = max(evaluated, key=lambda e: args.p_trap * worst_case(*e) + (1 - args.p_trap) * e[0].score)
        else:
            goldfish, g_trials = map_opening(envs, args.rollouts, h, args.generations, args.cont_generations,
                                             args.alpha, tags, ids, probe)
            line, trials = goldfish, g_trials
        if args.pair:  # both hand traps: nest the second inside P1's reply to the first
            trials = pair_trials(envs, args.rollouts, h, line, trials, args.cont_generations, args.alpha,
                                 tags, ids, probe)
            if not args.robust:
                g_trials = trials
        row = {"hand": h, "goldfish": goldfish.score, "goldfish_worst": worst_case(goldfish, g_trials),
               "line": line.score, "worst": worst_case(line, trials), "windows": len(line.windows)}
        rows.append(row)
        log.write(json.dumps({**row, "deck": args.deck, "opponent": args.opponent, "seed": args.seed,
                              "actions": line.actions[:line.turn1_len],
                              "trials": [loggable(t) for t in trials]}) + "\n")
        log.flush()
        if not trials:
            print(f"hand {h:3}: {line.score:5.2f}  no window for {args.opponent} on this line", flush=True)
            continue
        worst = trials[0]
        choke_cards[worst["after"]] += 1
        target = f", then picking {worst['target']}" if worst["target"] else ""  # target or forced choice
        how = f"{worst['card']} after {worst['after']} (step {worst['step']}){target}"
        if worst.get("then"):
            nxt = worst["then"]
            how += f", then {nxt['card']} after {nxt['after']} (step {nxt['step']})"
        robust = (f"  [max-min line: goldfish {line.score:.2f}, worst {row['worst']:.2f} vs best goldfish line "
                  f"{goldfish.score:.2f}, worst {row['goldfish_worst']:.2f}]") if args.robust else ""
        print(f"hand {h:3}: {line.score:5.2f} -> {worst['score']:5.2f} with {how}; "
              f"{len(trials)} options tried{robust}", flush=True)

    mean = lambda key: np.mean([r[key] for r in rows])
    dead = sum(1 for r in rows if r["windows"] == 0)
    print(f"\n{args.deck} vs {args.opponent}: {args.hands} openings in {time.time() - t0:.0f}s")
    print(f"  goldfish line: board {mean('goldfish'):.2f} -> through best-timed {args.opponent} "
          f"{mean('goldfish_worst'):.2f}")
    if args.robust:
        print(f"  max-min line:  board {mean('line'):.2f} -> through best-timed {args.opponent} "
              f"{mean('worst'):.2f}  (up to {args.robust} rounds of best response)")
    print(f"  chosen lines with no usable window: {dead}/{args.hands}")
    print(f"  most common chokepoints (P1 card the interruption answered): {choke_cards.most_common(5)}")


if __name__ == "__main__":
    main()
