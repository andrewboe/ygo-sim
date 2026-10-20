"""Recent tournament lists per format (Yugioh Meta top-decks), for meta_snapshot and meta_inclusion.

Genesys lists are Yugioh Meta's `genesys` events; Advanced is TCG lists that are neither Genesys
nor OCG. Card names map to passcodes through cards.sqlite (exact, normalized, then star/space-
insensitive if unique); unmatched names are kept by name and reported, never guessed.
Points and ban status are today's, not the ones in force when the list was played.
"""
import json
import sqlite3
import time
from collections import Counter, defaultdict
from datetime import date, timedelta

from .api import DATA_DIR, get_json
from .carddata import loose_name, norm_name
from .formats import FORMATS, DeckInputError, _limit, _points, resolve

YGOM_URL = "https://www.yugiohmeta.com/api/v1/top-decks"
YGOM_PAGE = 50
WINDOW_DAYS = 120  # what we pull; queries pick their own window inside it
MAX_AGE_HOURS = 12
RAW = DATA_DIR / "format_meta_ygom.json"

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta_lists (
  id TEXT PRIMARY KEY, format TEXT, day TEXT, deck_type TEXT, event TEXT, event_type TEXT,
  placement REAL, unmatched INTEGER);
CREATE TABLE IF NOT EXISTS meta_cards (
  list_id TEXT, zone TEXT, canonical_id INTEGER, name TEXT, count INTEGER);
CREATE INDEX IF NOT EXISTS meta_cards_cid ON meta_cards(canonical_id);
CREATE TABLE IF NOT EXISTS meta_fetch (fetched_at REAL, since TEXT, lists INTEGER);
"""


def _fetch(since: str) -> list[dict]:
    rows, page = [], 1
    while True:
        batch = get_json(YGOM_URL, {"created[$gte]": since, "limit": YGOM_PAGE, "page": page})
        if not batch:
            return rows
        rows += batch
        page += 1


def _format_of(raw: dict) -> str | None:
    event_type = ((raw.get("tournamentType") or {}).get("shortName") or "").casefold()
    if raw.get("genesys") or "genesys" in event_type:
        return "genesys"
    if raw.get("ocg"):
        return None
    return "tcg_advanced"


def _name_index(con: sqlite3.Connection) -> dict[str, int | None]:
    """name / normalized / loose key -> canonical id; ambiguous keys map to None (refused)."""
    idx: dict[str, int | None] = {}
    for cid, name, beta in con.execute("SELECT DISTINCT canonical_id, name, beta_name FROM cards "
                                       "WHERE type NOT IN ('Token','Skill Card')"):
        keys = [name, "n:" + norm_name(name), "l:" + loose_name(name)]
        if beta:  # pre-release / unofficial name, which some list sites keep using
            keys.append("b:" + loose_name(beta))
        for key in keys:
            idx[key] = cid if idx.get(key, cid) == cid else None
    return idx


def _lookup(idx, name: str) -> int | None:
    for key in (name, "n:" + norm_name(name), "l:" + loose_name(name), "b:" + loose_name(name)):
        if key in idx:
            return idx[key]
    return None


def load(con: sqlite3.Connection, raw: list[dict], fetched_at: float, since: str) -> int:
    """Replace the meta tables from raw Yugioh Meta records."""
    idx = _name_index(con)
    lists, cards = [], []
    for r in raw:
        fmt = _format_of(r)
        if fmt is None or r.get("incomplete"):
            continue
        unmatched = 0
        for zone in ("main", "extra", "side"):
            for e in r.get(zone) or []:
                name = e["card"]["name"]
                cid = _lookup(idx, name)
                unmatched += cid is None
                cards.append((r["_id"], zone, cid, name, e["amount"]))
        event = (r.get("event") or {}).get("name") or r.get("customTournamentName") or r.get("tournamentLocation")
        try:
            placement = float(r.get("tournamentPlacement"))
        except (TypeError, ValueError):
            placement = None
        lists.append((r["_id"], fmt, r["created"][:10], (r.get("deckType") or {}).get("name", "Unknown"),
                      event, (r.get("tournamentType") or {}).get("shortName"), placement, unmatched))
    with con:
        con.executescript("DELETE FROM meta_lists; DELETE FROM meta_cards; DELETE FROM meta_fetch;")
        con.executemany("INSERT INTO meta_lists VALUES (?,?,?,?,?,?,?,?)", lists)
        con.executemany("INSERT INTO meta_cards VALUES (?,?,?,?,?)", cards)
        con.execute("INSERT INTO meta_fetch VALUES (?,?,?)", (fetched_at, since, len(lists)))
    return len(lists)


def ensure_meta(con: sqlite3.Connection, force: bool = False) -> dict:
    con.executescript(SCHEMA)
    last = con.execute("SELECT * FROM meta_fetch").fetchone()
    if last and not force and time.time() - last["fetched_at"] < MAX_AGE_HOURS * 3600:
        return {"fetched_at": _iso(last["fetched_at"]), "since": last["since"]}
    since = (date.today() - timedelta(days=WINDOW_DAYS)).isoformat()
    try:
        raw = _fetch(since)
        RAW.write_text(json.dumps(raw), encoding="utf-8")
        now = time.time()
    except Exception as e:  # offline: reuse the last raw pull if there is one
        if not RAW.exists():
            raise
        raw, now = json.loads(RAW.read_text(encoding="utf-8")), RAW.stat().st_mtime
        load(con, raw, now, since)
        return {"fetched_at": _iso(now), "since": since, "note": f"refresh failed ({type(e).__name__}); cached lists"}
    load(con, raw, now, since)
    return {"fetched_at": _iso(now), "since": since}


def _iso(t: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


def _window(con, format: str, days: int, deck_type: str | None = None) -> list[sqlite3.Row]:
    if format not in FORMATS:
        raise DeckInputError(f"unknown format {format!r}; known: {', '.join(FORMATS)}")
    since = (date.today() - timedelta(days=days)).isoformat()
    q, params = "SELECT * FROM meta_lists WHERE format = ? AND day >= ?", [format, since]
    if deck_type:
        q += " AND deck_type = ? COLLATE NOCASE"
        params.append(deck_type)
    return con.execute(q, params).fetchall()


def _list_cards(con, ids: list[str]) -> dict[str, list[sqlite3.Row]]:
    out = defaultdict(list)
    for r in con.execute(f"SELECT * FROM meta_cards WHERE list_id IN ({','.join('?' * len(ids))})", ids):
        out[r["list_id"]].append(r)
    return out


def _legal_now(con, spec, rows: list[sqlite3.Row]) -> tuple[bool | None, int]:
    """Is this list legal under today's list/points? None if a card name didn't match. Returns (legal, points)."""
    totals: Counter = Counter()
    for r in rows:
        if r["canonical_id"] is None:
            return None, 0
        totals[r["canonical_id"]] += r["count"]
    if not totals:
        return None, 0
    pts = sum(_points(con, spec, cid) * n for cid, n in totals.items())
    ok = all(n <= _limit(con, spec, cid) for cid, n in totals.items())
    if spec.banned_frames:
        frames = {cid: f for cid, f in con.execute(
            f"SELECT passcode, frame_type FROM cards WHERE passcode IN ({','.join('?' * len(totals))})", list(totals))}
        ok = ok and not any(set(frames.get(cid, "").split("_")) & spec.banned_frames for cid in totals)
    if spec.points:
        ok = ok and pts <= spec.default_cap
    return ok, pts


def meta_snapshot(con: sqlite3.Connection, format: str, days: int = 60, top: int = 15) -> dict:
    spec = FORMATS.get(format)
    lists = _window(con, format, days)
    if not lists:
        return {"format": format, "lists": 0, "note": f"no {format} lists in the last {days} days"}
    cards = _list_cards(con, [l["id"] for l in lists])
    by_type = defaultdict(list)
    legal, points = {}, {}
    for l in lists:
        by_type[l["deck_type"]].append(l)
        legal[l["id"]], points[l["id"]] = _legal_now(con, spec, cards[l["id"]])
    types = []
    for t, ls in sorted(by_type.items(), key=lambda kv: -len(kv[1])):
        row = {"deck_type": t, "lists": len(ls), "share": round(len(ls) / len(lists), 3),
               "top8": sum(1 for l in ls if l["placement"] is not None and l["placement"] <= 8),
               "wins": sum(1 for l in ls if l["placement"] == 1),
               "legal_now": sum(1 for l in ls if legal[l["id"]])}
        if spec.points:
            row["avg_points"] = round(sum(points[l["id"]] for l in ls) / len(ls), 1)
        types.append(row)
    out = {
        "format": spec.title, "window": f"{min(l['day'] for l in lists)} .. {max(l['day'] for l in lists)}",
        "lists": len(lists), "events": len({l["event"] for l in lists}),
        "event_types": dict(Counter(l["event_type"] for l in lists).most_common()),
        "legal_now": sum(1 for v in legal.values() if v), "unmatched_lists": sum(1 for v in legal.values() if v is None),
        "deck_types": types[:top], "other_deck_types": max(0, len(types) - top),
        "staples": _inclusion_table(con, spec, lists, cards, top),
        "note": "Legality and points are today's; lists played under an older list or points may be illegal now.",
    }
    return out


def _inclusion_table(con, spec, lists, cards, top: int) -> list[dict]:
    played: Counter = Counter()
    copies: Counter = Counter()
    zones: dict[tuple, Counter] = defaultdict(Counter)
    names = {}
    for l in lists:
        per: Counter = Counter()
        for r in cards[l["id"]]:
            key = r["canonical_id"] or r["name"]
            names[key] = r["name"]
            per[key] += r["count"]
            zones[key][r["zone"]] += r["count"]
        for key, n in per.items():
            played[key] += 1
            copies[key] += n
    out = []
    for key, n in played.most_common(top):
        row = {"name": names[key], "share": round(n / len(lists), 3), "avg_copies": round(copies[key] / n, 2),
               "zone": zones[key].most_common(1)[0][0]}
        if isinstance(key, int):
            row["passcode"] = key
            if spec.points:
                row["points"] = _points(con, spec, key)
            if spec.limits:
                lim = _limit(con, spec, key)
                if lim < 3:
                    row["limit_now"] = lim
        else:
            row["unmatched_name"] = True
        out.append(row)
    return out


def meta_inclusion(con: sqlite3.Connection, format: str, card: str | None = None, deck_type: str | None = None,
                   days: int = 60, limit: int = 40) -> dict:
    spec = FORMATS.get(format)
    if (card is None) == (deck_type is None):
        raise DeckInputError("pass exactly one of card, deck_type")
    if deck_type:
        lists = _window(con, format, days, deck_type)
        if not lists:
            names = sorted({l["deck_type"] for l in _window(con, format, days)
                            if deck_type.casefold() in l["deck_type"].casefold()})
            return {"deck_type": deck_type, "lists": 0,
                    "note": f"no lists with that exact deck type in {days} days",
                    "similar_deck_types": names}
        cards = _list_cards(con, [l["id"] for l in lists])
        return {"format": spec.title, "deck_type": lists[0]["deck_type"], "lists": len(lists),
                "window": f"{min(l['day'] for l in lists)} .. {max(l['day'] for l in lists)}",
                "cards": _inclusion_table(con, spec, lists, cards, limit)}
    pid, note = resolve(con, card)
    if pid is None:
        return {"card": card, "error": note}
    cid = con.execute("SELECT canonical_id, name FROM cards WHERE passcode = ?", (pid,)).fetchone()
    if cid is None:
        return {"card": card, "error": f"unknown passcode {pid}"}
    lists = _window(con, format, days)
    by_id = {l["id"]: l for l in lists}
    hits: dict[str, int] = Counter()
    zones: Counter = Counter()
    for r in con.execute("SELECT * FROM meta_cards WHERE canonical_id = ?", (cid["canonical_id"],)):
        if r["list_id"] in by_id:
            hits[r["list_id"]] += r["count"]
            zones[r["zone"]] += r["count"]
    per_type = Counter(l["deck_type"] for l in lists)
    hit_type = Counter(by_id[i]["deck_type"] for i in hits)
    return {
        "format": spec.title, "card": cid["name"], "passcode": cid["canonical_id"], "lists": len(lists),
        "playing": len(hits), "share": round(len(hits) / len(lists), 3) if lists else 0,
        "avg_copies": round(sum(hits.values()) / len(hits), 2) if hits else 0, "zones": dict(zones),
        "by_deck_type": [{"deck_type": t, "playing": n, "of": per_type[t], "share": round(n / per_type[t], 3)}
                         for t, n in hit_type.most_common(limit)],
        **({"resolved": note} if note else {}),
    }
