"""Build the Bo3 matchup matrix from simulated games (THEORY §6).

For decks A and B: P(A wins | A first) comes from games with A first and B second; P(A wins | A second) is
1 - P(B wins | B first) from games with B first. With Laplace smoothing (one pseudo-win and one
pseudo-loss) so few games don't give 0% or 100%. Post-side rates equal pre-side rates until side plans
exist. match.match_win_rate turns the four rates into a Bo3 match win rate.
"""
import json
from collections import defaultdict

import numpy as np

from .api import DATA_DIR
from .match import GameRates, match_win_rate

RESULTS = DATA_DIR / "games" / "results.jsonl"
MATRIX = DATA_DIR / "games" / "matrix.json"


def first_win_rates(decks: list[str], eval_filter: str | None = None) -> dict:
    """(first, second) -> (first-player wins, games), draws counted as half."""
    tally = defaultdict(lambda: [0.0, 0])
    for line in RESULTS.read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        if r["first"] in decks and r["second"] in decks and (eval_filter is None or r["eval"] == eval_filter):
            t = tally[(r["first"], r["second"])]
            t[0] += 1.0 if r["winner"] == 0 else 0.5 if r["winner"] == -1 else 0.0
            t[1] += 1
    return tally


def build(decks: list[str], eval_filter: str | None = None) -> dict:
    """Game 1 uses the main lists; games 2-3 use side plans when those games exist: the deck going
    first plays <name>__s1, the deck going second <name>__s2 (ygosim side-plans). Otherwise post = pre."""
    names = decks + [f"{d}__{s}" for d in decks for s in ("s1", "s2")]
    tally = first_win_rates(names, eval_filter)
    rate = lambda a, b: (tally[(a, b)][0] + 1) / (tally[(a, b)][1] + 2)  # P(a wins going first vs b)
    has = lambda a, b: tally[(a, b)][1] > 0
    n = len(decks)
    match = np.zeros((n, n))
    game = {}
    sided = 0
    for i, a in enumerate(decks):
        for j, b in enumerate(decks):
            first, second = rate(a, b), 1 - rate(b, a)
            post_first = rate(f"{a}__s1", f"{b}__s2") if has(f"{a}__s1", f"{b}__s2") else first
            post_second = 1 - rate(f"{b}__s1", f"{a}__s2") if has(f"{b}__s1", f"{a}__s2") else second
            sided += has(f"{a}__s1", f"{b}__s2")
            game[f"{a} vs {b}"] = {"first": first, "second": second, "post_first": post_first,
                                   "post_second": post_second, "games": tally[(a, b)][1] + tally[(b, a)][1]}
            match[i, j] = match_win_rate(GameRates(first, second, post_first, post_second))
    # Mirror and complementarity: average with the transpose so M[a,b] + M[b,a] = 1 exactly.
    match = (match + (1 - match.T)) / 2
    out = {"decks": decks, "matrix": match.round(4).tolist(), "game_rates": game,
           "note": f"post-side games played for {sided} of {n * n} ordered pairs; others reuse pre-side rates"}
    MATRIX.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out
