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
    tally = first_win_rates(decks, eval_filter)
    rate = lambda a, b: (tally[(a, b)][0] + 1) / (tally[(a, b)][1] + 2)  # P(a wins going first vs b)
    n = len(decks)
    match = np.zeros((n, n))
    game = {}
    for i, a in enumerate(decks):
        for j, b in enumerate(decks):
            first, second = rate(a, b), 1 - rate(b, a)
            game[f"{a} vs {b}"] = {"first": first, "second": second,
                                   "games": tally[(a, b)][1] + tally[(b, a)][1]}
            match[i, j] = match_win_rate(GameRates(first, second, first, second))
    # Mirror and complementarity: average with the transpose so M[a,b] + M[b,a] = 1 exactly.
    match = (match + (1 - match.T)) / 2
    out = {"decks": decks, "matrix": match.round(4).tolist(), "game_rates": game,
           "note": "post-side = pre-side until side plans exist"}
    MATRIX.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out
