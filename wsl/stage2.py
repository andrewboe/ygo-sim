"""Funnel stage 2: candidates vs the field, with racing (successive halving).

Each round, every surviving candidate plays GAMES games against each field opponent in each seat (a
separate game.py process per batch: env pools can't be safely torn down within one process). A
candidate's field win rate is the field-weighted mean over opponents of its average win rate across
seats. After each round, candidates whose upper confidence bound falls below the leader's lower bound
are dropped, then the bottom fraction is cut, until FINALISTS remain (they go to stage 3).

Results accumulate in data/games/results.jsonl, like every other game, so `ygosim matrix` can reuse them.

Run in WSL:  python stage2.py CAND1 CAND2 ... [--rounds 3] [--games 4] [--finalists 5]
"""
import argparse
import json
import math
import os
import subprocess
from collections import defaultdict

DATA = "/mnt/c/Users/andre/Desktop/ygo-sim/data"
W = os.path.dirname(os.path.abspath(__file__))


def field_opponents(min_weight: float) -> dict[str, float]:
    """Runtime deck name -> field weight, for TCG field decks with weight >= min_weight."""
    import re
    field = json.load(open(f"{DATA}/field/field.json"))
    slug = lambda s: re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    opps = {f"{slug(e['deck'])}__tcg": e["weight"] for e in field["entries"]
            if e["source"] == "tcg" and e["weight"] >= min_weight}
    total = sum(opps.values())
    return {k: v / total for k, v in opps.items()}


def play(first: str, second: str, games: int, seed_offset: int, extra: list[str]) -> None:
    # Resumable: skip a batch whose games (same pairing, same game indices) are already logged.
    done = {r["game"] for r in results() if r["first"] == first and r["second"] == second}
    if all(g in done for g in range(seed_offset, seed_offset + games)):
        return
    cmd = ["bash", f"{W}/run_py.sh", "game.py", first, second, "--games", str(games),
           "--first-game", str(seed_offset), *extra]
    subprocess.run(cmd, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   env={**os.environ, "TIMEOUT": "7200"})


def results() -> list[dict]:
    path = f"{DATA}/games/results.jsonl"
    return [json.loads(l) for l in open(path)] if os.path.exists(path) else []


def field_rate(cand: str, opps: dict[str, float]) -> tuple[float, float, int]:
    """(field-weighted win rate, standard error, games) for `cand` across seats."""
    tally = defaultdict(lambda: [0.0, 0])
    for r in results():
        for seat, me, opp in ((0, r["first"], r["second"]), (1, r["second"], r["first"])):
            if me == cand and opp in opps:
                win = 0.5 if r["winner"] == -1 else float(r["winner"] == seat)
                tally[(opp, seat)][0] += win
                tally[(opp, seat)][1] += 1
    rate, var, n = 0.0, 0.0, 0
    for opp, w in opps.items():
        seats = []
        for seat in (0, 1):
            wins, games = tally[(opp, seat)]
            p = (wins + 1) / (games + 2)  # Laplace
            seats.append((p, games))
            n += games
        p = sum(s[0] for s in seats) / 2
        rate += w * p
        var += (w / 2) ** 2 * sum(s[0] * (1 - s[0]) / max(s[1], 1) for s in seats)
    return rate, math.sqrt(var), n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("candidates", nargs="+", help="runtime names, e.g. cand__branded__dracotail")
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--games", type=int, default=4, help="per opponent per seat per round")
    ap.add_argument("--finalists", type=int, default=5)
    ap.add_argument("--keep", type=float, default=0.5, help="fraction kept after each round's CI cut")
    ap.add_argument("--min-weight", type=float, default=0.04, help="field decks at least this heavy")
    ap.add_argument("--z", type=float, default=1.64, help="CI width for dropping (1.64 = 90%% two-sided)")
    args, extra = ap.parse_known_args()

    opps = field_opponents(args.min_weight)
    print(f"field opponents: {', '.join(f'{o} ({w:.0%})' for o, w in opps.items())}", flush=True)
    alive = list(args.candidates)
    for rnd in range(args.rounds):
        for cand in alive:
            for opp in opps:
                offset = 10_000 + rnd * 100  # fresh games each round, same deals for every candidate
                play(cand, opp, args.games, offset, extra)
                play(opp, cand, args.games, offset, extra)
        stats = {c: field_rate(c, opps) for c in alive}
        ranked = sorted(alive, key=lambda c: -stats[c][0])
        leader_lo = stats[ranked[0]][0] - args.z * stats[ranked[0]][1]
        print(f"\nround {rnd}:", flush=True)
        for c in ranked:
            r, se, n = stats[c]
            print(f"  {r:5.1%} +- {se:4.1%}  ({n:4} games)  {c}", flush=True)
        survivors = [c for c in ranked if stats[c][0] + args.z * stats[c][1] >= leader_lo]
        survivors = survivors[:max(args.finalists, math.ceil(len(survivors) * args.keep))]
        dropped = [c for c in alive if c not in survivors]
        if dropped:
            print(f"  dropped: {', '.join(dropped)}", flush=True)
        alive = survivors
        if len(alive) <= args.finalists:
            break
    print(f"\nfinalists: {', '.join(alive)}", flush=True)
    json.dump({"finalists": alive, "opponents": opps}, open(f"{DATA}/screen/stage2_finalists.json", "w"), indent=1)


if __name__ == "__main__":
    main()
