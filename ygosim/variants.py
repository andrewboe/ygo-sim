"""Stage 0 of the candidate funnel: discover the real variants inside each field deck.

For every TCG field deck, pool its tournament lists (including sub-cutoff clusters folded into it, the
same rule as field.py), then sub-cluster the lists by staple-free card overlap. Each variant gets:
  - its list count and share of the deck (recency-weighted),
  - a representative list (medoid) written as .ydk,
  - the cards that set it apart: much more played in this variant than in the rest of the deck,
  - a name from those cards' archetypes (e.g. "Branded / Dracotail"), else the lists' own labels.
"""
import json
from collections import Counter
from datetime import date

from .api import DATA_DIR
from .cards import card_db, name
from .field import FOLD_MIN
from .meta import Archetype, build_meta, card_set, jaccard, slugify
from .project import generic_cards

SPLIT = 0.50        # average-linkage overlap needed to stay in the same variant
SIGNATURE_IN = 0.6  # a variant's distinguishing card: played in >= 60% of its lists...
SIGNATURE_OUT = 0.25  # ...and <= 25% of the deck's other lists


def _pool(tcg: list[Archetype], deck: str, field_decks: set[str], generic) -> list:
    """Lists of `deck` plus every sub-cutoff cluster that folds into it."""
    by_name = {a.name: a for a in tcg}
    lists = list(by_name[deck].lists)
    majors = [by_name[d] for d in field_decks if d in by_name]
    for a in tcg:
        if a.name in field_decks:
            continue
        cards = [card_set(d) - generic for d in a.lists]
        best = max(majors, key=lambda m: max(jaccard(c, card_set(d) - generic) for c in cards for d in m.lists))
        score = max(jaccard(c, card_set(d) - generic) for c in cards for d in best.lists)
        if best.name == deck and score >= FOLD_MIN:
            lists += a.lists
    return lists


def _cluster(lists: list, generic) -> list[list]:
    sets = [card_set(d) - generic for d in lists]
    clusters = [[i] for i in range(len(lists))]

    def sim(a, b):
        return sum(jaccard(sets[i], sets[j]) for i in a for j in b) / (len(a) * len(b))

    while len(clusters) > 1:
        score, x, y = max((sim(a, b), x, y) for x, a in enumerate(clusters)
                          for y, b in enumerate(clusters) if x < y)
        if score < SPLIT:
            break
        clusters[x] += clusters.pop(y)
    return sorted(([lists[i] for i in c] for c in clusters), key=len, reverse=True)


def _play_rate(lists: list) -> Counter:
    c = Counter()
    for d in lists:
        c.update(set(d.main) | set(d.extra))
    return Counter({k: v / len(lists) for k, v in c.items()}) if lists else Counter()


def discover(max_days: int = 60, min_lists: int = 2) -> dict:
    """Variants of every TCG field deck in data/field/field.json."""
    field = json.loads((DATA_DIR / "field" / "field.json").read_text(encoding="utf-8"))
    tcg, _ = build_meta(max_days, 1)
    generic = generic_cards(tcg)
    db = card_db()
    today = date.today()
    field_decks = {e["deck"] for e in field["entries"] if e["source"] == "tcg"}
    out_dir = DATA_DIR / "variants"
    report = {}
    for deck in sorted(field_decks):
        pooled = _pool(tcg, deck, field_decks, generic)
        groups = _cluster(pooled, generic)
        weight = lambda ls: sum(Archetype("", ls, set()).weight(today) for _ in [0])
        total = weight(pooled) or 1
        variants, singles = [], 0
        for g in groups:
            if len(g) < min_lists:
                singles += len(g)
                continue
            rest = [d for d in pooled if d not in g]
            inside, outside = _play_rate(g), _play_rate(rest)
            signature = sorted((c for c in inside if inside[c] >= SIGNATURE_IN and outside[c] <= SIGNATURE_OUT
                                and c not in generic), key=lambda c: outside[c] - inside[c])[:6]
            archetypes = [a for a, _ in Counter(db[c].archetype for c in signature
                                                if c in db and db[c].archetype).most_common(2)]
            labels = Counter(d.name for d in g).most_common(1)[0][0]
            vname = " / ".join(archetypes) if archetypes else labels
            rep = Archetype(f"{deck}: {vname}", g, set()).representative
            slug = slugify(vname) or "core"
            path = out_dir / slugify(deck) / f"{slug}.ydk"
            rep.to_ydk(path)
            main_rate = Counter()
            for d in g:
                main_rate.update(set(d.main))
            variants.append({"variant": vname, "lists": len(g), "share_of_deck": round(weight(g) / total, 3),
                             "labels": dict(Counter(d.name for d in g).most_common(4)),
                             "signature": [name(c) for c in signature], "ydk": str(path.relative_to(DATA_DIR)),
                             # main-deck play rate within this variant (flex vs core for package cuts)
                             "play_rate": {str(c): round(n / len(g), 3) for c, n in main_rate.items()}})
        report[deck] = {"lists": len(pooled), "variants": variants, "one_offs": singles}
    (out_dir / "variants.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    return report
