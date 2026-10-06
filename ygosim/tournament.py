"""Monte Carlo YCS-style events: Swiss rounds, then a single-elimination top cut.

Each player brings a deck drawn from the field's shares. Every match is a best-of-3 whose outcome is
sampled from a deck-vs-deck match win rate (build those with match.match_win_rate). Run many events
to see how each deck converts: top-cut rate vs field share, win rate, average finish.

Swiss: 3 points per win, 1 per draw. Each round pairs players within score groups (top down,
avoiding rematches where possible); an odd player out gets a bye (a win). Standings break ties on
opponents' match-win percentage (floored at 33%, as in Konami tournament policy), then randomly.
"""
import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field

import numpy as np


@dataclass
class EventFormat:
    players: int
    rounds: int | None = None   # default: ceil(log2(players))
    top_cut: int | None = None  # default: largest power of two <= players / 8, between 8 and 64
    draw_rate: float = 0.0      # unfinished matches; YCS rounds are timed

    def resolved(self) -> "EventFormat":
        rounds = self.rounds or math.ceil(math.log2(self.players))
        cut = self.top_cut or max(8, min(64, 2 ** int(math.log2(max(1, self.players // 8)))))
        return EventFormat(self.players, rounds, min(cut, self.players), self.draw_rate)


@dataclass
class DeckResult:
    entrants: int = 0
    top_cut: int = 0
    wins: int = 0
    finish_sum: float = 0.0  # sum of final standings positions (1 = winner)


@dataclass
class EventStats:
    events: int = 0
    decks: dict[str, DeckResult] = field(default_factory=lambda: defaultdict(DeckResult))

    def table(self) -> list[dict]:
        total = sum(r.entrants for r in self.decks.values())
        cut_total = sum(r.top_cut for r in self.decks.values())
        rows = []
        for name, r in self.decks.items():
            share = r.entrants / total
            cut_share = r.top_cut / cut_total if cut_total else 0.0
            rows.append({"deck": name, "field_share": share, "top_cut_share": cut_share,
                         "conversion": cut_share / share if share else 0.0,
                         "top_cut_rate": r.top_cut / r.entrants, "win_rate": r.wins / self.events,
                         "avg_finish": r.finish_sum / r.entrants})
        return sorted(rows, key=lambda x: -x["conversion"])


def _play(a: int, b: int, decks: list[int], matrix: np.ndarray, draw_rate: float, rng) -> float:
    """Result for player a: 1 win, 0.5 draw, 0 loss."""
    if draw_rate and rng.random() < draw_rate:
        return 0.5
    return 1.0 if rng.random() < matrix[decks[a], decks[b]] else 0.0


def _pair(order: list[int], points: np.ndarray, played: list[set], rng) -> tuple[list[tuple[int, int]], int | None]:
    """Pair down the standings, avoiding rematches greedily. Returns pairs and the bye player."""
    pool = list(order)
    bye = None
    if len(pool) % 2:
        # Bye to the lowest-ranked player who hasn't had one (marked by -1 in played).
        for i in range(len(pool) - 1, -1, -1):
            if -1 not in played[pool[i]]:
                bye = pool.pop(i)
                break
        else:
            bye = pool.pop()
    pairs = []
    while pool:
        a = pool.pop(0)
        j = next((k for k, b in enumerate(pool) if b not in played[a]), 0)
        pairs.append((a, pool.pop(j)))
    return pairs, bye


def run_event(decks: list[int], matrix: np.ndarray, fmt: EventFormat, rng) -> tuple[list[int], int]:
    """One event. Returns final standings (player indices, best first) and the winner."""
    n = len(decks)
    points = np.zeros(n)
    match_wins = np.zeros(n)
    played: list[set] = [set() for _ in range(n)]
    opponents: list[list[int]] = [[] for _ in range(n)]
    for _ in range(fmt.rounds):
        # Within a score group, shuffle so pairings aren't fixed by seat.
        jitter = rng.random(n)
        order = sorted(range(n), key=lambda p: (-points[p], jitter[p]))
        pairs, bye = _pair(order, points, played, rng)
        if bye is not None:
            points[bye] += 3
            match_wins[bye] += 1
            played[bye].add(-1)
        for a, b in pairs:
            r = _play(a, b, decks, matrix, fmt.draw_rate, rng)
            points[a] += 3 * r if r != 0.5 else 1
            points[b] += 3 * (1 - r) if r != 0.5 else 1
            match_wins[a] += r
            match_wins[b] += 1 - r
            played[a].add(b)
            played[b].add(a)
            opponents[a].append(b)
            opponents[b].append(a)

    mwp = np.maximum(match_wins / fmt.rounds, 1 / 3)
    omw = np.array([np.mean([mwp[o] for o in opps]) if opps else 0.0 for opps in opponents])
    jitter = rng.random(n)
    standings = sorted(range(n), key=lambda p: (-points[p], -omw[p], jitter[p]))

    # Top cut: single elimination, seeded 1 v N, 2 v N-1, ...
    bracket = standings[:fmt.top_cut]
    while len(bracket) > 1:
        half = len(bracket) // 2
        nxt = []
        for i in range(half):
            a, b = bracket[i], bracket[-1 - i]
            win = rng.random() < matrix[decks[a], decks[b]]  # no draws in elimination
            nxt.append(a if win else b)
        bracket = nxt
    return standings, bracket[0]


def simulate(deck_names: list[str], shares: list[float], matrix: np.ndarray, fmt: EventFormat,
             events: int, seed: int = 0) -> EventStats:
    """Monte Carlo over `events` tournaments with players drawn from the field shares."""
    fmt = fmt.resolved()
    rng = np.random.default_rng(seed)
    p = np.asarray(shares, dtype=float)
    p /= p.sum()
    stats = EventStats(events)
    for _ in range(events):
        decks = list(rng.choice(len(deck_names), size=fmt.players, p=p))
        standings, winner = run_event(decks, matrix, fmt, rng)
        for pos, player in enumerate(standings, start=1):
            r = stats.decks[deck_names[decks[player]]]
            r.entrants += 1
            r.finish_sum += pos
            if pos <= fmt.top_cut:
                r.top_cut += 1
        stats.decks[deck_names[decks[winner]]].wins += 1
    return stats


def check_matrix(matrix: np.ndarray) -> None:
    """Match win rates must be complementary: M[a, b] + M[b, a] = 1."""
    if not np.allclose(matrix + matrix.T, 1.0, atol=1e-6):
        raise ValueError("matchup matrix is not complementary (M[a,b] + M[b,a] != 1)")
