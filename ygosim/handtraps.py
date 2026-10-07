"""How likely the opponent is to hold a given hand trap (THEORY §2: the p in expected-board selection).

P(at least one copy in the opening hand) = 1 - C(deck - copies, hand) / C(deck, hand), averaged over
the field: weighted by each deck's share, using that deck's representative list. Going first you face
the opponent's 6-card hand (5 + their draw); going second, their 5.
"""
import json
from math import comb

from .api import DATA_DIR
from .cards import by_name
from .deck import Deck


def p_in_hand(copies: int, deck_size: int, hand: int) -> float:
    if copies <= 0:
        return 0.0
    return 1 - comb(deck_size - copies, hand) / comb(deck_size, hand)


def field_hand_trap_odds(names: list[str], hand: int = 6) -> dict[str, float]:
    """P(the opponent opens each hand trap), averaged over the current field (data/field/field.json)."""
    field = json.loads((DATA_DIR / "field" / "field.json").read_text(encoding="utf-8"))
    ids = {n: by_name(n).id for n in names}
    out = {n: 0.0 for n in names}
    total = 0.0
    for entry in field["entries"]:
        path = DATA_DIR / "field" / entry["lists"][next(iter(entry["lists"]))]
        deck = Deck.from_ydk(path).canonical_ids()
        size = sum(deck.main.values())
        for n in names:
            out[n] += entry["weight"] * p_in_hand(deck.main.get(ids[n], 0), size, hand)
        total += entry["weight"]
    return {n: v / total for n, v in out.items()}
