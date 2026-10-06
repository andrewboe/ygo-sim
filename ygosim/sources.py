"""Tournament lists from every source, normalized into one persistent store.

Sources:
  - YGOProDeck "Tournament Meta Decks" (TCG) and "Tournament Meta Decks OCG"
  - Yugioh Meta top decks (TCG and OCG; Genesys-format events excluded)
  - data/inbox/*.ydk: community lists you drop in by hand. These are candidates, not meta share.

The store (data/store.json) keeps every list ever seen with its date, so history accumulates
across refreshes. Lists appearing on several sites are deduplicated by contents.
"""
import json
import re
from collections import Counter
from datetime import date, timedelta
from functools import cache

from .api import DATA_DIR, DECKS_URL, cached, get_json
from .cards import card_db
from .deck import Deck

TCG_FORMAT = "Tournament Meta Decks"
OCG_FORMAT = "Tournament Meta Decks OCG"
YGOPRODECK_PAGE = 20  # server-side cap
YGOM_URL = "https://www.yugiohmeta.com/api/v1/top-decks"
YGOM_PAGE = 50
EXCLUDED_YGOM_EVENTS = ("genesys",)  # different format; not Advanced
STORE = DATA_DIR / "store.json"
INBOX = DATA_DIR / "inbox"


# ---- store -------------------------------------------------------------------------------

def load_store() -> dict[str, dict]:
    return json.loads(STORE.read_text(encoding="utf-8")) if STORE.exists() else {}


def save_store(store: dict[str, dict]) -> None:
    STORE.parent.mkdir(parents=True, exist_ok=True)
    STORE.write_text(json.dumps(store), encoding="utf-8")


def _record(key: str, source: str, deck: Deck, day: date, ocg: bool, event: str | None) -> dict:
    zone = lambda c: {str(k): v for k, v in c.items()}
    return {"key": key, "source": source, "name": deck.name, "date": day.isoformat(), "ocg": ocg,
            "event": event, "main": zone(deck.main), "extra": zone(deck.extra), "side": zone(deck.side)}


def record_deck(r: dict) -> Deck:
    zone = lambda z: Counter({int(k): v for k, v in r[z].items()})
    return Deck(r["name"], zone("main"), zone("extra"), zone("side"),
                meta={"date": date.fromisoformat(r["date"]), "source": r["source"], "event": r["event"]})


# ---- YGOProDeck --------------------------------------------------------------------------

_UNIT_DAYS = {"second": 0, "minute": 0, "hour": 0, "day": 1, "week": 7, "month": 30, "year": 365}


def _age_days(submit_date: str) -> int:
    """YGOProDeck reports dates as '3 days ago', '1 week ago', etc."""
    m = re.match(r"(\d+|an?)\s+(\w+?)s?\s+ago", submit_date.strip().lower())
    if not m:
        return 0  # 'today', 'just now'
    n = 1 if m[1] in ("a", "an") else int(m[1])
    return n * _UNIT_DAYS.get(m[2], 0)


def fetch_decks(fmt: str, max_days: int, max_age_hours: float = 12) -> list[dict]:
    def fetch():
        decks, offset = [], 0
        while True:
            page = get_json(DECKS_URL, {"format": fmt, "limit": YGOPRODECK_PAGE, "offset": offset})
            if not page:
                break
            decks += [d for d in page if _age_days(d["submit_date"]) <= max_days]
            if _age_days(page[-1]["submit_date"]) > max_days:
                break
            offset += YGOPRODECK_PAGE
        return decks

    slug = re.sub(r"[^a-z0-9]+", "_", fmt.lower())
    return cached(f"{slug}_{max_days}d.json", max_age_hours, fetch)


def to_deck(raw: dict) -> Deck:
    def parse(s):
        return Counter(int(x) for x in json.loads(s or "[]"))

    return Deck(raw["deck_name"].strip(), parse(raw.get("main_deck")),
                parse(raw.get("extra_deck")), parse(raw.get("side_deck"))).canonical_ids()


def pull_ygoprodeck(max_days: int, max_age_hours: float, today: date) -> list[dict]:
    out = []
    for fmt, ocg in ((TCG_FORMAT, False), (OCG_FORMAT, True)):
        for raw in fetch_decks(fmt, max_days, max_age_hours):
            # Only relative dates ('2 weeks ago') are given; the store keeps the earliest estimate.
            day = today - timedelta(days=_age_days(raw["submit_date"]))
            out.append(_record(f"ygoprodeck:{raw['deckNum']}", "ygoprodeck", to_deck(raw), day, ocg,
                               raw.get("tournamentName")))
    return out


# ---- Yugioh Meta -------------------------------------------------------------------------

def _norm(card_name: str) -> str:
    # Yugioh Meta drops some punctuation ('Maliss P Chessy Cat' vs 'Maliss <P> Chessy Cat').
    return re.sub(r"[^0-9a-z]", "", card_name.casefold())


@cache
def _names() -> dict[str, int | None]:
    """Normalized name -> card id. Names that normalize to more than one card map to None,
    so they're refused rather than guessed."""
    idx: dict[str, int | None] = {}
    for card in {c.id: c for c in card_db().values()}.values():
        key = _norm(card.name)
        idx[key] = card.id if key not in idx else None
    return idx


def _ygom_zone(entries: list[dict], unknown: Counter) -> Counter | None:
    out = Counter()
    for e in entries or []:
        cid = _names().get(_norm(e["card"]["name"]))
        if cid is None:
            unknown[e["card"]["name"]] += 1
            return None  # fail closed: never guess a card
        out[cid] += e["amount"]
    return out


def pull_ygom(max_days: int, max_age_hours: float, today: date) -> tuple[list[dict], Counter]:
    since = (today - timedelta(days=max_days)).isoformat()

    def fetch():
        rows, page = [], 1
        while True:
            batch = get_json(YGOM_URL, {"created[$gte]": since, "limit": YGOM_PAGE, "page": page})
            if not batch:
                return rows
            rows += batch
            page += 1

    out, unknown = [], Counter()
    for raw in cached(f"ygom_top_decks_{max_days}d.json", max_age_hours, fetch):
        event = (raw.get("tournamentType") or {}).get("shortName") or ""
        if raw.get("incomplete") or any(x in event.casefold() for x in EXCLUDED_YGOM_EVENTS):
            continue
        zones = [_ygom_zone(raw.get(z), unknown) for z in ("main", "extra", "side")]
        if any(z is None for z in zones):
            continue
        deck = Deck((raw.get("deckType") or {}).get("name", "Unknown"), *zones).canonical_ids()
        where = raw.get("tournamentLocation") or raw.get("customTournamentName") or ""
        out.append(_record(f"ygom:{raw['_id']}", "ygom", deck, date.fromisoformat(raw["created"][:10]),
                           bool(raw.get("ocg")), f"{event} {where}".strip() or None))
    return out, unknown


# ---- pull + query ------------------------------------------------------------------------

def pull_all(max_days: int, max_age_hours: float = 12, today: date | None = None) -> dict:
    """Fetch every source into the store. Returns counts and unmatched card names."""
    today = today or date.today()
    store = load_store()
    ygom, unknown = pull_ygom(max_days, max_age_hours, today)
    new = Counter()
    for r in pull_ygoprodeck(max_days, max_age_hours, today) + ygom:
        old = store.get(r["key"])
        if old is None:
            new[r["source"]] += 1
            store[r["key"]] = r
        elif r["date"] < old["date"]:
            old["date"] = r["date"]
    save_store(store)
    return {"new": dict(new), "stored": len(store), "unknown_names": dict(unknown)}


def _content_key(r: dict) -> tuple:
    return (r["ocg"], tuple(sorted(r["main"].items())), tuple(sorted(r["extra"].items())))


def collect(ocg: bool, max_days: int, today: date | None = None) -> list[Deck]:
    """Deduplicated lists from the store within the window. On duplicates, Yugioh Meta's exact
    date wins over YGOProDeck's estimate."""
    today = today or date.today()
    since = (today - timedelta(days=max_days)).isoformat()
    best: dict[tuple, dict] = {}
    for r in load_store().values():
        if r["ocg"] != ocg or not since <= r["date"] <= today.isoformat():
            continue
        k = _content_key(r)
        if k not in best or (r["source"] == "ygom" and best[k]["source"] != "ygom"):
            best[k] = r
    return [record_deck(r) for r in best.values()]


def inbox_decks() -> list[Deck]:
    """Community lists dropped into data/inbox/ as .ydk files."""
    return [Deck.from_ydk(p).canonical_ids() for p in sorted(INBOX.glob("*.ydk"))]
