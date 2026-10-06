"""Best-of-3 match win probability from per-game win rates.

Game 1 is played with main decks and a coin flip decides who goes first. Games 2 and 3 are post-side,
and the loser of the previous game chooses turn order, picking whatever is best for them.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class GameRates:
    """Deck A's chance to win a single game against deck B."""
    pre_first: float    # game 1, A goes first
    pre_second: float   # game 1, A goes second
    post_first: float   # games 2-3 (after siding), A goes first
    post_second: float  # games 2-3 (after siding), A goes second


def match_win_rate(r: GameRates) -> float:
    g1 = (r.pre_first + r.pre_second) / 2
    a_picks = max(r.post_first, r.post_second)  # A lost the last game and picks its better order
    b_picks = min(r.post_first, r.post_second)  # B lost and picks the order worst for A
    # Won game 1: B picks game 2; if B takes it, A picks game 3.
    # Lost game 1: A picks game 2; if A takes it, B picks game 3.
    return g1 * (b_picks + (1 - b_picks) * a_picks) + (1 - g1) * a_picks * b_picks
