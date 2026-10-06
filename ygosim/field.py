"""The field to simulate against: what TCG players will actually bring, weighted by share.

- TCG decks (merged by card overlap) are weighted by their recency-decayed share of topping lists.
- An OCG projection or community list that updates a TCG deck becomes a candidate list for that
  deck: same weight, the simulator decides which list is strongest.
- One with no TCG counterpart enters as a new deck at a small prior share.
- A projection whose TCG counterpart sits below the cutoff (e.g. Sacred Beasts) stays out:
  the TCG already shows few people play it.
- Decks below `min_share` fold into 'other' and aren't simulated.
"""
import json
from dataclasses import dataclass, field
from datetime import date

from .api import DATA_DIR
from .deck import Deck
from .meta import Archetype, slugify
from .project import Projection, closest_tcg, generic_cards


@dataclass
class FieldEntry:
    name: str
    tcg_share: float          # recency-weighted share of TCG topping lists (0 for new decks)
    weight: float = 0.0       # normalized share within the simulated field
    source: str = "tcg"       # "tcg" or "new"
    variants: list[str] = field(default_factory=list)
    lists: dict[str, Deck] = field(default_factory=dict)  # label -> decklist to test


@dataclass
class Field:
    entries: list[FieldEntry]
    other_share: float
    notes: list[str]


def build_field(tcg: list[Archetype], projections: list[Projection], community: list[Deck],
                min_share: float, new_share: float, as_of: date, today: date | None = None,
                min_ocg_share: float = 0.04) -> Field:
    """`min_ocg_share` gates OCG decks with no TCG counterpart: most OCG data is small community
    events, and a one-off deck shouldn't take a full new-deck slot in the field."""
    today = today or date.today()
    total = sum(a.weight(today) for a in tcg) or 1
    share = {a.name: a.weight(today) / total for a in tcg}
    entries = {a.name: FieldEntry(a.name, share[a.name], variants=a.variants,
                                  lists={"tcg": a.representative})
               for a in tcg if share[a.name] >= min_share}
    notes = []
    generic = generic_cards(tcg)

    def place(label: str, deck: Deck, origin: str, ocg_share: float | None = None):
        match = closest_tcg(deck, tcg, generic)
        if match is None and ocg_share is not None and ocg_share < min_ocg_share:
            notes.append(f"{label}: no TCG counterpart and only {ocg_share:.1%} of the OCG, "
                         f"below the {min_ocg_share:.0%} bar for new decks ({origin})")
        elif match is None:
            entries[label] = FieldEntry(label, 0.0, source="new", lists={origin: deck})
            notes.append(f"{label}: new deck ({origin}), prior share {new_share:.0%}")
        elif match.name in entries:
            entries[match.name].lists[f"{origin}: {label}"] = deck
            notes.append(f"{label}: candidate update for {match.name} ({origin})")
        else:
            notes.append(f"{label}: matches {match.name} at {share[match.name]:.1%} TCG share, "
                         f"below the {min_share:.0%} cutoff ({origin})")

    for p in projections:
        if p.error:
            notes.append(f"{p.archetype}: rejected ({p.error})")
        else:
            place(p.archetype, p.deck, "projected", p.ocg_share)
    for deck in community:
        if errors := deck.legality_errors(as_of):
            notes.append(f"{deck.name}: community list rejected ({'; '.join(errors)})")
        else:
            place(deck.name, deck, "community")

    raw = {e.name: (new_share if e.source == "new" else e.tcg_share) for e in entries.values()}
    in_field = sum(raw.values())
    for e in entries.values():
        e.weight = raw[e.name] / in_field
    other = 1 - sum(e.tcg_share for e in entries.values())
    return Field(sorted(entries.values(), key=lambda e: -e.weight), other, notes)


def field_json(f: Field, as_of: date, out=DATA_DIR / "field") -> dict:
    """Write each list's .ydk under `out` (legality-gated) and return the field description."""
    rows = []
    for e in f.entries:
        files = {}
        for label, deck in e.lists.items():
            path = out / slugify(e.name) / f"{slugify(label)}.ydk"
            deck.to_ydk(path, as_of)  # legality gate
            files[label] = str(path.relative_to(out))
        rows.append({"deck": e.name, "weight": round(e.weight, 4), "tcg_share": round(e.tcg_share, 4),
                     "source": e.source, "variants": e.variants, "lists": files})
    return {"as_of": as_of.isoformat(), "other_share": round(f.other_share, 4),
            "entries": rows, "notes": f.notes}


def export_field(f: Field, as_of: date, out=DATA_DIR / "field") -> dict:
    out.mkdir(parents=True, exist_ok=True)
    data = field_json(f, as_of, out)
    (out / "field.json").write_text(json.dumps(data, indent=1), encoding="utf-8")
    return data
