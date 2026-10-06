import itertools
import random

import pytest

from ygosim.match import GameRates, match_win_rate


def simulate(r: GameRates, n: int, seed: int = 0) -> float:
    """Play out Bo3 matches directly, as a cross-check of the closed form."""
    rng = random.Random(seed)
    wins = 0
    for _ in range(n):
        a, b = 0, 0
        first = rng.random() < 0.5  # game 1 coin flip: does A go first?
        p = r.pre_first if first else r.pre_second
        a_won = rng.random() < p
        while True:
            a, b = a + a_won, b + (not a_won)
            if a == 2 or b == 2:
                break
            # Loser chooses: A maximizes its rate, B minimizes A's.
            p = max(r.post_first, r.post_second) if not a_won else min(r.post_first, r.post_second)
            a_won = rng.random() < p
        wins += a == 2
    return wins / n


@pytest.mark.parametrize("rates", [
    GameRates(0.5, 0.5, 0.5, 0.5),
    GameRates(0.7, 0.4, 0.65, 0.45),
    GameRates(0.9, 0.2, 0.6, 0.6),
    GameRates(0.3, 0.6, 0.35, 0.55),
])
def test_closed_form_matches_simulation(rates):
    assert match_win_rate(rates) == pytest.approx(simulate(rates, 200_000), abs=0.005)


def test_even_matchup_is_even():
    assert match_win_rate(GameRates(0.5, 0.5, 0.5, 0.5)) == pytest.approx(0.5)


def test_symmetry():
    # A's match rate plus B's (built from A's complements, turn order swapped) is 1.
    for pf, ps, qf, qs in itertools.product([0.2, 0.55, 0.8], repeat=4):
        a = GameRates(pf, ps, qf, qs)
        b = GameRates(1 - ps, 1 - pf, 1 - qs, 1 - qf)
        assert match_win_rate(a) + match_win_rate(b) == pytest.approx(1)
