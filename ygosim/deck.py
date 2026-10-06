"""Deck model, TCG legality, and .ydk (YGOPro/EDOPro) I/O."""
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .banlist import tcg_banlist
from .cards import card_db


class IllegalDeckError(RuntimeError):
    pass


@dataclass
class Deck:
    name: str
    main: Counter = field(default_factory=Counter)
    extra: Counter = field(default_factory=Counter)
    side: Counter = field(default_factory=Counter)
    meta: dict = field(default_factory=dict, compare=False)  # date, source, event

    def zones(self) -> dict[str, Counter]:
        return {"main": self.main, "extra": self.extra, "side": self.side}

    def total(self) -> Counter:
        return self.main + self.extra + self.side

    def canonical_ids(self) -> "Deck":
        """Map alt-art passcodes to the base card id so lists compare cleanly."""
        db = card_db()
        return Deck(self.name, _remap(self.main, db), _remap(self.extra, db), _remap(self.side, db), self.meta)

    def legality_errors(self, as_of: date | None = None) -> list[str]:
        """Every reason this deck is not TCG-legal on `as_of` (default: today).
        Fails closed: unknown cards and cards without a TCG release date are illegal."""
        as_of = as_of or date.today()
        db, banlist = card_db(), tcg_banlist()
        errors = []
        if not 40 <= sum(self.main.values()) <= 60:
            errors.append(f"main deck has {sum(self.main.values())} cards")
        if sum(self.extra.values()) > 15:
            errors.append(f"extra deck has {sum(self.extra.values())} cards")
        if sum(self.side.values()) > 15:
            errors.append(f"side deck has {sum(self.side.values())} cards")

        # Count by canonical id so alt arts can't dodge the limit.
        totals = _remap(self.total(), db)
        for cid, n in totals.items():
            card = db.get(cid)
            if card is None:
                errors.append(f"unknown card id {cid}")
                continue
            if not card.released_by(as_of):
                when = card.tcg_date.isoformat() if card.tcg_date else "no TCG release"
                errors.append(f"{card.name}: not TCG-released by {as_of} ({when})")
            if n > banlist.limit(cid):
                errors.append(f"{card.name}: {n} copies, TCG limit {banlist.limit(cid)}")
            if n > 3:
                errors.append(f"{card.name}: {n} copies")

        for cid in self.main:
            if (card := db.get(cid)) and card.is_extra:
                errors.append(f"{card.name}: extra deck card in main deck")
        for cid in self.extra:
            if (card := db.get(cid)) and not card.is_extra:
                errors.append(f"{card.name}: main deck card in extra deck")
        return errors

    def assert_legal(self, as_of: date | None = None) -> None:
        if errors := self.legality_errors(as_of):
            raise IllegalDeckError(f"{self.name} is not TCG-legal: " + "; ".join(errors))

    def to_ydk(self, path: Path, as_of: date | None = None) -> None:
        """Write a .ydk. Refuses to write an illegal deck."""
        self.assert_legal(as_of)

        def ids(c: Counter):
            return [str(cid) for cid, n in sorted(c.items()) for _ in range(n)]

        lines = ["#created by ygosim", "#main", *ids(self.main),
                 "#extra", *ids(self.extra), "!side", *ids(self.side)]
        path.parent.mkdir(parents=True, exist_ok=True)
        # LF only: ygoenv's .ydk parser skips card lines ending in '\r'.
        path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")

    @classmethod
    def from_ydk(cls, path: Path) -> "Deck":
        deck = cls(path.stem)
        section = deck.main
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line == "#main":
                section = deck.main
            elif line == "#extra":
                section = deck.extra
            elif line == "!side":
                section = deck.side
            elif line.isdigit():
                section[int(line)] += 1
        return deck


def _remap(c: Counter, db) -> Counter:
    out = Counter()
    for cid, n in c.items():
        out[db[cid].id if cid in db else cid] += n
    return out
