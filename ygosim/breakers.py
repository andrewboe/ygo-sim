"""Board-breaker packages for candidate variants (going second; THEORY §2).

For each variant list from `ygosim variants`, and each package in config/breakers.json, make a candidate:
top up the package's cards to their target counts (TCG limits respected), cutting the variant's least-played
flex cards: lowest play rate across the deck's tournament lists, never core cards (>= 90% play rate),
breakers, or hand traps. Conditional breakers (e.g. The Fallen & The Virtuous) are only added when the deck
has a card that mentions what they need. Every candidate passes the legality gate before it's written.
"""
import json
from collections import Counter
from pathlib import Path

from .api import DATA_DIR
from .banlist import tcg_banlist
from .cards import by_name, card_db
from .deck import Deck
from .field import FOLD_MIN  # noqa: F401  (same pooling rule as variants)
from .meta import build_meta, card_set, slugify
from .project import generic_cards
from .variants import _pool

CONFIG = Path(__file__).resolve().parent.parent / "config" / "breakers.json"
CORE = 0.90
CANDIDATES = DATA_DIR / "candidates"


def load_config() -> dict:
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def _hand_trap_ids() -> set[int]:
    """Hand traps by the same rules as wsl/card_tags.py (one source of truth for tags)."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "wsl"))
    from card_tags import tag  # noqa: E402  (pure text rules; no engine needed)

    def type_bits(t: str) -> int:
        bits = (1 if "Monster" in t else 0) | (2 if "Spell" in t else 0) | (4 if "Trap" in t else 0)
        bits |= 0x20000 if "Continuous" in t else 0
        bits |= 0x10000 if "Quick-Play" in t else 0
        bits |= 0x4000 if "Token" in t else 0
        return bits

    return {c.id for c in {c.id: c for c in card_db().values()}.values()
            if tag(type_bits(c.type), c.desc)["hand"] > 0}


def _meets(requirement: str, deck: Deck) -> bool:
    db = card_db()
    return any(requirement.lower() in db[c].desc.lower() or requirement.lower() == db[c].name.lower()
               for c in set(deck.main) | set(deck.extra) if c in db)


def apply_package(deck: Deck, package: dict, config: dict, play_rate: dict[int, float],
                  protected: set[int], core: float = CORE, engine: set[str] = frozenset()
                  ) -> tuple[Deck | None, list[str], list[str]]:
    """Return (new deck, added, cut), or (None, reason, []) when the package doesn't apply."""
    bl = tcg_banlist()
    new = Deck(deck.name, deck.main.copy(), deck.extra.copy(), deck.side.copy())
    adds = Counter()
    for card_name, target in package.items():
        spec = config["cards"].get(card_name, {})
        if spec.get("requires") and not _meets(spec["requires"], deck):
            return None, [f"{card_name} needs {spec['requires']}"], []
        cid = by_name(card_name).id
        have = new.total()[cid]
        want = min(target, bl.limit(cid), 3)
        if want > have:
            adds[cid] += want - have
    if not adds:
        return None, ["already runs the package"], []
    # Cut the least-played flex cards, one copy at a time.
    cuts = []
    db = card_db()
    for _ in range(sum(adds.values())):
        flex = [c for c in new.main if new.main[c] > 0 and c not in protected and c not in adds
                and play_rate.get(c, 0.0) < core]
        if not flex:
            return None, ["no flex slots left to cut"], []
        # Rarest first; among equals, generic cards before the deck's own engine, then fewer copies.
        victim = min(flex, key=lambda c: (play_rate.get(c, 0.0), db[c].archetype in engine, new.main[c]))
        new.main[victim] -= 1
        cuts.append(victim)
    new.main += Counter()
    new.main.update(adds)
    return new, [f"{n}x {db[c].name}" for c, n in adds.items()], [db[c].name for c in cuts]


def build_candidates(packages: list[str] | None = None) -> list[dict]:
    config = load_config()
    variants = json.loads((DATA_DIR / "variants" / "variants.json").read_text(encoding="utf-8"))
    field = json.loads((DATA_DIR / "field" / "field.json").read_text(encoding="utf-8"))
    tcg, _ = build_meta(60, 1)
    generic = generic_cards(tcg)
    field_decks = {e["deck"] for e in field["entries"] if e["source"] == "tcg"}
    breaker_ids = {by_name(n).id for n in config["cards"]}
    protected_base = breaker_ids | _hand_trap_ids()
    rows = []
    for deck_name, report in variants.items():
        for v in report["variants"]:
            # Flex vs core within this variant: its signature cards are core even if rare deck-wide.
            play_rate = {int(c): r for c, r in v.get("play_rate", {}).items()}
            base = Deck.from_ydk(DATA_DIR / v["ydk"]).canonical_ids()
            db = card_db()
            # Small variants: only cards in every list are core. Signature cards are always protected.
            core = CORE if v["lists"] >= 8 else 1.0
            protected = protected_base | {by_name(n).id for n in v["signature"]}
            engine = {a for a, _ in Counter(db[c].archetype for c in base.main.elements()
                                            if c in db and db[c].archetype).most_common(3)}
            base_name = f"{slugify(deck_name)}__{slugify(v['variant']) or 'core'}"
            base.to_ydk(CANDIDATES / f"{base_name}.ydk")
            rows.append({"candidate": base_name, "deck": deck_name, "variant": v["variant"], "package": None})
            for pkg in packages or list(config["packages"]):
                new, added, cut = apply_package(base, config["packages"][pkg], config, play_rate, protected,
                                                core, engine)
                if new is None:
                    rows.append({"candidate": f"{base_name}__{pkg}", "deck": deck_name, "variant": v["variant"],
                                 "package": pkg, "skipped": added[0]})
                    continue
                errors = new.legality_errors()
                if errors:
                    rows.append({"candidate": f"{base_name}__{pkg}", "deck": deck_name, "variant": v["variant"],
                                 "package": pkg, "skipped": "; ".join(errors)})
                    continue
                new.to_ydk(CANDIDATES / f"{base_name}__{pkg}.ydk")
                rows.append({"candidate": f"{base_name}__{pkg}", "deck": deck_name, "variant": v["variant"],
                             "package": pkg, "added": added, "cut": cut})
    (CANDIDATES / "candidates.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    return rows
