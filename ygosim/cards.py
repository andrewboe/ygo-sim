"""Card database: passcode -> card info, including TCG release date."""
from dataclasses import dataclass
from datetime import date
from functools import cache

from .api import CARDINFO_URL, CARDSETS_URL, cached, get_json

EXTRA_TYPES = ("Fusion", "Synchro", "XYZ", "Link")
BANLIST_LIMIT = {"Forbidden": 0, "Limited": 1, "Semi-Limited": 2}


@dataclass(frozen=True)
class Card:
    id: int  # canonical passcode; alt arts map here
    name: str
    type: str
    desc: str
    archetype: str | None
    tcg_date: date | None  # None = no known TCG release
    ygoprodeck_limit: int  # one of two banlist sources; use banlist.tcg_banlist() for legality

    @property
    def is_extra(self) -> bool:
        return any(t in self.type for t in EXTRA_TYPES)

    def released_by(self, day: date) -> bool:
        return self.tcg_date is not None and self.tcg_date <= day


def _parse_date(s: str | None) -> date | None:
    try:
        return date.fromisoformat(s) if s else None
    except ValueError:
        return None


@cache
def card_db() -> dict[int, Card]:
    raw = cached("cards.json", 24, lambda: get_json(CARDINFO_URL, {"misc": "yes"}))
    set_dates = {s["set_name"]: _parse_date(s.get("tcg_date"))
                 for s in cached("cardsets.json", 24, lambda: get_json(CARDSETS_URL))}
    db: dict[int, Card] = {}
    for c in raw["data"]:
        misc = (c.get("misc_info") or [{}])[0]
        # Prefer the card's own TCG date; fall back to its earliest dated TCG set.
        tcg_date = _parse_date(misc.get("tcg_date"))
        if tcg_date is None:
            dates = [d for s in c.get("card_sets") or [] if (d := set_dates.get(s["set_name"]))]
            tcg_date = min(dates, default=None)
        ban = (c.get("banlist_info") or {}).get("ban_tcg")
        card = Card(
            id=c["id"],
            name=c["name"],
            type=c["type"],
            desc=c.get("desc", ""),
            archetype=c.get("archetype"),
            tcg_date=tcg_date,
            ygoprodeck_limit=BANLIST_LIMIT.get(ban, 3),
        )
        # Alt-art printings share a card but have their own passcode.
        for img in c.get("card_images", []):
            db[img["id"]] = card
        db[card.id] = card
    return db


def name(card_id: int) -> str:
    card = card_db().get(card_id)
    return card.name if card else f"<unknown {card_id}>"


def by_name(card_name: str) -> Card:
    for card in card_db().values():
        if card.name == card_name:
            return card
    raise KeyError(card_name)
