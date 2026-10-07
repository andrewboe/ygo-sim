"""Side plans for games 2-3 of a Bo3 (THEORY §6): one post-side list per seat.

Each candidate's side deck comes from its tournament list. For games 2-3:
  going first  (<cand>__s1): side IN hand traps and negating traps; side OUT breakers (dead going first),
                             then the least-played flex cards
  going second (<cand>__s2): side IN breakers and hand traps; side OUT set-only traps (slow going
                             second), then the least-played flex cards
At most MAX_SWAPS cards move; swapped-out cards go to the side deck, so totals stay legal.
"""
import json
from collections import Counter

from .api import DATA_DIR
from .breakers import CANDIDATES, _hand_trap_ids, load_config
from .cards import by_name, card_db
from .deck import Deck

MAX_SWAPS = 6


def _is_set_only_trap(card) -> bool:
    d = card.desc.lower()
    return "Trap" in card.type and "activate this card from your hand" not in d


def _negating_trap(card) -> bool:
    return "Trap" in card.type and "negate" in card.desc.lower()


def plan(deck: Deck, play_rate: dict[int, float], going_first: bool, breakers: set[int],
         hand_traps: set[int]) -> tuple[Deck, list[str], list[str]]:
    db = card_db()
    new = Deck(deck.name, deck.main.copy(), deck.extra.copy(), deck.side.copy())
    # The deck's own engine: its most common archetypes. Engine cards are never "dead" for a seat.
    engine = {a for a, _ in Counter(db[c].archetype for c in new.main.elements()
                                    if c in db and db[c].archetype).most_common(3)}
    if going_first:
        wanted = [c for c in new.side.elements() if c in hand_traps or _negating_trap(db[c])]
        dead = lambda c: c in breakers
        keep = hand_traps
    else:
        wanted = [c for c in new.side.elements() if c in breakers or c in hand_traps]
        dead = lambda c: _is_set_only_trap(db[c]) and c not in hand_traps and db[c].archetype not in engine
        keep = hand_traps | breakers
    wanted = wanted[:MAX_SWAPS]
    ins, outs = [], []
    for c in wanted:
        # Never swap like for like (a hand trap out for a hand trap in) or cut what this seat wants.
        candidates = [m for m in new.main if new.main[m] > 0 and m not in wanted and m not in keep]
        if not candidates:
            break
        # Dead cards for this seat first, then the least played; never cut a copy of what comes in.
        out = min(candidates, key=lambda m: (not dead(m), play_rate.get(m, 0.0), -new.main[m]))
        new.main[out] -= 1
        new.side[out] += 1
        new.side[c] -= 1
        new.main[c] += 1
        ins.append(db[c].name)
        outs.append(db[out].name)
    new.main += Counter()
    new.side += Counter()
    return new, ins, outs


def build_side_plans() -> list[dict]:
    rows = json.loads((CANDIDATES / "candidates.json").read_text(encoding="utf-8"))
    variants = json.loads((DATA_DIR / "variants" / "variants.json").read_text(encoding="utf-8"))
    rates = {}
    for deck, report in variants.items():
        for v in report["variants"]:
            rates[(deck, v["variant"])] = {int(c): r for c, r in v.get("play_rate", {}).items()}
    breakers = {by_name(n).id for n in load_config()["cards"]}
    hand_traps = _hand_trap_ids()
    out = []
    for r in rows:
        if "skipped" in r:
            continue
        path = CANDIDATES / f"{r['candidate']}.ydk"
        deck = Deck.from_ydk(path).canonical_ids()
        play_rate = rates.get((r["deck"], r["variant"]), {})
        for seat, first in (("s1", True), ("s2", False)):
            new, ins, outs = plan(deck, play_rate, first, breakers, hand_traps)
            errors = new.legality_errors()
            if errors:
                out.append({"candidate": r["candidate"], "seat": seat, "skipped": "; ".join(errors)})
                continue
            new.to_ydk(CANDIDATES / f"{r['candidate']}__{seat}.ydk")
            out.append({"candidate": r["candidate"], "seat": seat, "in": ins, "out": outs})
    (CANDIDATES / "side_plans.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out
