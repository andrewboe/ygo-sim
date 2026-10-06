"""Condense tournament lists into one entry per archetype.

Output per archetype:
  - a representative .ydk (the medoid: the real list closest to all others)
  - a card-inclusion table (how often each card appears, average copies).
    This is the edit space the deck optimizer will search later.
Archetype weight decays with list age, so last weekend's tops outweigh last month's.
"""
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date

from .api import DATA_DIR
from .cards import name
from .deck import Deck

HALF_LIFE_DAYS = 21


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def recency_weight(d: Deck, today: date) -> float:
    day = d.meta.get("date")
    return 1.0 if day is None else 0.5 ** (max(0, (today - day).days) / HALF_LIFE_DAYS)


def _distance(a: Deck, b: Deck) -> int:
    return sum(((a.main - b.main) + (b.main - a.main)).values()) + \
           sum(((a.extra - b.extra) + (b.extra - a.extra)).values())


@dataclass
class Archetype:
    name: str
    lists: list[Deck]
    events: set[str]
    variants: list[str] = field(default_factory=list)  # deck names merged into this one

    def weight(self, today: date) -> float:
        return sum(recency_weight(d, today) for d in self.lists)

    @property
    def representative(self) -> Deck:
        rep = min(self.lists, key=lambda d: sum(_distance(d, o) for o in self.lists))
        return Deck(self.name, rep.main.copy(), rep.extra.copy(), rep.side.copy())

    def inclusion(self) -> list[dict]:
        """Per card: share of lists that run it and average copies when run."""
        n = len(self.lists)
        seen, copies = Counter(), Counter()
        for d in self.lists:
            for z, c in d.zones().items():
                for cid, k in c.items():
                    seen[(z, cid)] += 1
                    copies[(z, cid)] += k
        rows = [{"zone": z, "id": cid, "name": name(cid),
                 "play_rate": round(seen[(z, cid)] / n, 3),
                 "avg_copies": round(copies[(z, cid)] / seen[(z, cid)], 2)}
                for (z, cid) in seen]
        return sorted(rows, key=lambda r: (r["zone"], -r["play_rate"], -r["avg_copies"]))


def group_archetypes(decks: list[Deck], min_lists: int) -> list[Archetype]:
    groups: dict[str, Archetype] = {}
    for deck in decks:
        arch = groups.setdefault(deck.name, Archetype(deck.name, [], set()))
        arch.lists.append(deck)
        if deck.meta.get("event"):
            arch.events.add(deck.meta["event"])
    archetypes = [a for a in groups.values() if len(a.lists) >= min_lists]
    return sorted(archetypes, key=lambda a: -len(a.lists))


def card_set(d: Deck) -> set[int]:
    return set(d.main) | set(d.extra)


def jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a | b else 0.0


MERGE_THRESHOLD = 0.45


def merge_archetypes(archs: list[Archetype], threshold: float = MERGE_THRESHOLD) -> list[Archetype]:
    """Merge differently-labelled deck names that are really the same deck ('Elfnote' / 'Synchron Elfnote',
    or YGOProDeck's 'Light and Darkness Ritual' / Yugioh Meta's 'Chaos Ritual').
    Average-linkage clustering on card overlap, so one shared package can't chain unrelated decks."""
    reps = {a.name: card_set(a.representative) for a in archs}
    clusters = [[a] for a in archs]

    def sim(c1, c2):
        return sum(jaccard(reps[a.name], reps[b.name]) for a in c1 for b in c2) / (len(c1) * len(c2))

    while len(clusters) > 1:
        score, i, j = max((sim(c1, c2), i, j) for i, c1 in enumerate(clusters)
                          for j, c2 in enumerate(clusters) if i < j)
        if score < threshold:
            break
        clusters[i] += clusters.pop(j)

    merged = []
    for c in clusters:
        c.sort(key=lambda a: -len(a.lists))
        merged.append(Archetype(c[0].name, [d for a in c for d in a.lists],
                                set().union(*(a.events for a in c)), [a.name for a in c]))
    return sorted(merged, key=lambda a: -len(a.lists))


def build_meta(max_days: int, min_lists: int, include_illegal: bool = False,
               as_of: date | None = None, merge: bool = True, ocg: bool = False) -> tuple[list[Archetype], int]:
    """Archetypes from the store. TCG lists that break the current TCG banlist are dropped by default:
    dates are too coarse to cut cleanly at a banlist's effective date.
    `min_lists` applies after merging, so small variants still count toward their deck."""
    from .sources import collect

    decks = collect(ocg, max_days)
    if not ocg and not include_illegal:
        decks = [d for d in decks if not d.legality_errors(as_of)]
    archs = group_archetypes(decks, 1)
    if merge:
        archs = merge_archetypes(archs)
    return [a for a in archs if len(a.lists) >= min_lists], len(decks)


def export_meta(archetypes: list[Archetype], total_lists: int, include_illegal: bool = False) -> None:
    out = DATA_DIR / "meta"
    out.mkdir(parents=True, exist_ok=True)
    today = date.today()
    total_weight = sum(a.weight(today) for a in archetypes) or 1
    summary = []
    for a in archetypes:
        slug = slugify(a.name)
        rep = a.representative
        errors = rep.legality_errors()
        if not errors:
            rep.to_ydk(out / f"{slug}.ydk")
        elif not include_illegal:
            raise AssertionError(f"filtered meta produced an illegal list: {errors}")
        (out / f"{slug}.inclusion.json").write_text(json.dumps(a.inclusion(), indent=1), encoding="utf-8")
        summary.append({"archetype": a.name, "variants": a.variants, "slug": slug, "lists": len(a.lists),
                        "list_share": round(len(a.lists) / total_lists, 3),
                        "weighted_share": round(a.weight(today) / total_weight, 3),
                        "events": sorted(a.events), "legality_errors": errors})
    (out / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
