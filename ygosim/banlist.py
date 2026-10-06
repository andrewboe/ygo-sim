"""TCG banlist built from two independent sources. When they disagree, the stricter limit wins.

Sources:
  - YGOProDeck card data (banlist_info.ban_tcg)
  - Project Ignis 0TCG.lflist.conf (what EDOPro, and later our simulator, enforce)
"""
from dataclasses import dataclass
from functools import cache

from .api import IGNIS_TCG_LFLIST_URL, cached, get_text
from .cards import card_db, name


@dataclass(frozen=True)
class Banlist:
    title: str
    limits: dict[int, int]  # canonical id -> 0..2; cards not listed are at 3
    conflicts: tuple[str, ...]

    def limit(self, card_id: int) -> int:
        return self.limits.get(card_id, 3)


def parse_lflist(text: str) -> tuple[str, dict[int, int]]:
    """Parse the first list in an lflist.conf file."""
    title, limits = "", {}
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("!"):
            if title:
                break  # only the first (current) list
            title = line[1:]
        elif line and line[0].isdigit():
            passcode, limit = line.split()[:2]
            limits[int(passcode)] = int(limit)
    if not title or not limits:
        raise ValueError("lflist.conf parsed to an empty banlist")
    return title, limits


@cache
def tcg_banlist() -> Banlist:
    db = card_db()
    title, ignis_raw = parse_lflist(cached("ignis_tcg_lflist.json", 24, lambda: get_text(IGNIS_TCG_LFLIST_URL)))

    ignis: dict[int, int] = {}
    for passcode, limit in ignis_raw.items():
        cid = db[passcode].id if passcode in db else passcode
        ignis[cid] = min(limit, ignis.get(cid, 3))
    ygopd = {c.id: c.ygoprodeck_limit for c in db.values() if c.ygoprodeck_limit < 3}

    limits, conflicts = {}, []
    for cid in ignis.keys() | ygopd.keys():
        a, b = ignis.get(cid, 3), ygopd.get(cid, 3)
        limits[cid] = min(a, b)
        if a != b:
            conflicts.append(f"{name(cid)}: Ignis {a}, YGOProDeck {b} -> using {min(a, b)}")
    return Banlist(title, limits, tuple(sorted(conflicts)))
