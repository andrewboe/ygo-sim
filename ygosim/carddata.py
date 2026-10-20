"""Format-aware card index: YGOProDeck's Genesys dump plus the Ignis TCG list, in SQLite.

Separate from cards.py/banlist.py (which the simulator uses) so the format tools can carry
Genesys points, fetch metadata and points history without touching simulator code.

Tables:
  cards(passcode -> canonical_id, name, type, frame_type, ...)   alt arts are their own rows
  limits(format, canonical_id, lim, ygoprodeck, ignis)            only restricted cards
  points(format, canonical_id, points)                            only pointed cards
  points_history(fetch_id, format, canonical_id, old, new)        rows only when points change
  mentions(canonical_id, mention)                                 every "quoted" name in a card's text
  cards_fts(canonical_id, name, desc)                             FTS5 over canonical cards
  fetches(fetch_id, fetched_at, checked_at, db_version, ...)      one row per rebuild
"""
import json
import re
import sqlite3
import unicodedata
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .api import CARDINFO_URL, CARDSETS_URL, DATA_DIR, IGNIS_TCG_LFLIST_URL, cached, get_json, get_text
from .banlist import parse_lflist
from .links import extract_all

DB_PATH = DATA_DIR / "cards.sqlite"
DBVER_URL = "https://db.ygoprodeck.com/api/v7/checkDBVer.php"
BAN_LIMIT = {"Forbidden": 0, "Limited": 1, "Semi-Limited": 2}
QUOTED = re.compile(r'"([^"]+)"')  # Konami text quotes card and archetype names
SCHEMA_VERSION = 3 # bump when build() fills new tables; older indexes are rebuilt
CHECK_EVERY = timedelta(hours=24)  # ask YGOProDeck for its DB version at most this often
STALE_AFTER = timedelta(days=7)  # unverified for this long -> answers say stale

SCHEMA = """
CREATE TABLE IF NOT EXISTS cards (
  passcode INTEGER PRIMARY KEY, canonical_id INTEGER NOT NULL, name TEXT NOT NULL,
  name_norm TEXT NOT NULL, name_loose TEXT NOT NULL, type TEXT NOT NULL, frame_type TEXT NOT NULL,
  race TEXT, attribute TEXT, level INTEGER, atk INTEGER, def INTEGER, linkval INTEGER,
  desc TEXT, archetype TEXT, tcg_date TEXT, ocg_date TEXT, beta_name TEXT, konami_id INTEGER);
CREATE INDEX IF NOT EXISTS cards_norm ON cards(name_norm);
CREATE INDEX IF NOT EXISTS cards_loose ON cards(name_loose);
CREATE TABLE IF NOT EXISTS limits (
  format TEXT, canonical_id INTEGER, lim INTEGER, ygoprodeck INTEGER, ignis INTEGER,
  PRIMARY KEY (format, canonical_id));
CREATE TABLE IF NOT EXISTS points (
  format TEXT, canonical_id INTEGER, points INTEGER, PRIMARY KEY (format, canonical_id));
CREATE TABLE IF NOT EXISTS points_history (
  fetch_id INTEGER, format TEXT, canonical_id INTEGER, old INTEGER, new INTEGER);
CREATE TABLE IF NOT EXISTS mentions (canonical_id INTEGER, mention TEXT);
CREATE INDEX IF NOT EXISTS mentions_m ON mentions(mention);
CREATE VIRTUAL TABLE IF NOT EXISTS cards_fts USING fts5(canonical_id UNINDEXED, name, desc);
CREATE TABLE IF NOT EXISTS fetches (
  fetch_id INTEGER PRIMARY KEY AUTOINCREMENT, fetched_at TEXT, checked_at TEXT,
  db_version TEXT, db_last_update TEXT, remote_version TEXT, ignis_title TEXT, cards INTEGER);
"""


def norm_name(s: str) -> str:
    """Case, quote and punctuation-insensitive; ☆ and ★ stay (they tell different cards apart)."""
    s = unicodedata.normalize("NFKC", s).casefold()
    s = re.sub(r"[^\w☆★]+", " ", s)
    return " ".join(s.split())


def loose_name(s: str) -> str:
    """norm_name without spaces or stars, for "Cupsy Yummy" -> Cupsy☆Yummy (used only when unique)."""
    return re.sub(r"[\s☆★]+", "", norm_name(s))


def _date(s: str | None) -> str | None:
    try:
        return date.fromisoformat(s).isoformat() if s else None
    except ValueError:
        return None


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def connect(path: Path = DB_PATH) -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def build(con: sqlite3.Connection, dump: dict, lflist_text: str, set_dates: dict[str, str | None],
          db_version: dict, fetched_at: datetime | None = None) -> int:
    """Replace the card, limit and points tables from raw data in one transaction; returns fetch_id."""
    fetched_at = (fetched_at or _now()).isoformat()
    ignis_title, ignis_raw = parse_lflist(lflist_text)
    old_points = {(r["format"], r["canonical_id"]): r["points"]
                  for r in con.execute("SELECT * FROM points")}

    cards, ygopd, points = [], {}, {}
    alt_to_canon: dict[int, int] = {}
    for c in dump["data"]:
        misc = (c.get("misc_info") or [{}])[0]
        cid = c["id"]
        tcg = _date(misc.get("tcg_date"))
        if tcg is None:  # fall back to the earliest dated TCG set, as cards.py does
            tcg = min(filter(None, (set_dates.get(s["set_name"]) for s in c.get("card_sets") or [])),
                      default=None)
        row = (c["name"], norm_name(c["name"]), loose_name(c["name"]), c["type"], c.get("frameType", ""),
               c.get("race"), c.get("attribute"), c.get("level"), c.get("atk"), c.get("def"),
               c.get("linkval"), c.get("desc", ""), c.get("archetype"), tcg, _date(misc.get("ocg_date")),
               misc.get("beta_name"), misc.get("konami_id"))
        for pid in {cid, *(img["id"] for img in c.get("card_images", []))}:
            alt_to_canon[pid] = cid
            cards.append((pid, cid, *row))
        if (ban := (c.get("banlist_info") or {}).get("ban_tcg")) in BAN_LIMIT:
            ygopd[cid] = BAN_LIMIT[ban]
        for fmt, key in (("genesys", "genesys_points"), ("genesys_ocg", "genesys_ocg_points")):
            if misc.get(key):
                points[(fmt, cid)] = int(misc[key])

    ignis: dict[int, int] = {}
    for pid, lim in ignis_raw.items():
        cid = alt_to_canon.get(pid, pid)
        ignis[cid] = min(lim, ignis.get(cid, 3))

    with con:
        cur = con.execute(
            "INSERT INTO fetches (fetched_at, checked_at, db_version, db_last_update, remote_version,"
            " ignis_title, cards) VALUES (?,?,?,?,?,?,?)",
            (fetched_at, fetched_at, db_version.get("database_version"), db_version.get("last_update"),
             db_version.get("database_version"), ignis_title, len(dump["data"])))
        fetch_id = cur.lastrowid
        for t in ("cards", "limits", "points", "mentions", "cards_fts"):
            con.execute(f"DELETE FROM {t}")
        con.executemany(f"INSERT INTO cards VALUES ({','.join('?' * 19)})", cards)
        con.executemany("INSERT INTO limits VALUES ('tcg',?,?,?,?)",
                        [(cid, min(ygopd.get(cid, 3), ignis.get(cid, 3)), ygopd.get(cid, 3), ignis.get(cid, 3))
                         for cid in ygopd.keys() | ignis.keys()])
        con.executemany("INSERT INTO points VALUES (?,?,?)", [(f, cid, p) for (f, cid), p in points.items()])
        con.executemany("INSERT INTO cards_fts VALUES (?,?,?)",
                        [(c["id"], c["name"], c.get("desc", "")) for c in dump["data"]])
        con.executemany("INSERT INTO mentions VALUES (?,?)",
                        [(c["id"], m) for c in dump["data"] for m in sorted(set(QUOTED.findall(c.get("desc", ""))))])
        if old_points:  # the first build is the baseline, not a change
            fmts = {f for f, _ in points} & {f for f, _ in old_points}  # a missing format is not a change
            changes = [(fetch_id, f, cid, old_points.get((f, cid), 0), points.get((f, cid), 0))
                       for f, cid in old_points.keys() | points.keys()
                       if f in fmts and old_points.get((f, cid), 0) != points.get((f, cid), 0)]
            con.executemany("INSERT INTO points_history VALUES (?,?,?,?,?)", changes)
        con.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    extract_all(con)  # the link-graph pass over every card's text
    return fetch_id


def fetch_and_build(con: sqlite3.Connection) -> int:
    """Pull the Genesys dumps (TCG and OCG points) and the Ignis list, then rebuild."""
    version = get_json(DBVER_URL)[0]
    dump = get_json(CARDINFO_URL, {"misc": "yes", "format": "genesys"})
    ocg = get_json(CARDINFO_URL, {"misc": "yes", "format": "genesys ocg"})
    ocg_points = {c["id"]: (c.get("misc_info") or [{}])[0].get("genesys_ocg_points") for c in ocg["data"]}
    for c in dump["data"]:
        if (p := ocg_points.get(c["id"])) is not None:
            c["misc_info"] = c.get("misc_info") or [{}]
            c["misc_info"][0]["genesys_ocg_points"] = p
    (DATA_DIR / "cards_genesys.json").write_text(json.dumps(dump), encoding="utf-8")
    sets = {s["set_name"]: _date(s.get("tcg_date"))
            for s in cached("cardsets.json", 24, lambda: get_json(CARDSETS_URL))}
    return build(con, dump, get_text(IGNIS_TCG_LFLIST_URL), sets, version)


def latest_fetch(con: sqlite3.Connection) -> sqlite3.Row | None:
    return con.execute("SELECT * FROM fetches ORDER BY fetch_id DESC LIMIT 1").fetchone()


def ensure_fresh(con: sqlite3.Connection, force: bool = False) -> str:
    """Build if empty; otherwise, at most once per CHECK_EVERY, rebuild only if YGOProDeck's DB version moved.
    Never raises on network errors when a usable index exists; the freshness block reports it."""
    last = latest_fetch(con)
    old_schema = con.execute("PRAGMA user_version").fetchone()[0] < SCHEMA_VERSION
    if last is None or force or old_schema:
        fetch_and_build(con)
        return "built"
    if _now() - datetime.fromisoformat(last["checked_at"]) < CHECK_EVERY:
        return "fresh"
    try:
        remote = get_json(DBVER_URL)[0]["database_version"]
    except Exception as e:  # offline: keep serving the cache
        return f"check failed ({type(e).__name__}); using cached data"
    if remote != last["db_version"]:
        try:
            fetch_and_build(con)
            return f"rebuilt (YGOProDeck {last['db_version']} -> {remote})"
        except Exception as e:
            with con:
                con.execute("UPDATE fetches SET remote_version=? WHERE fetch_id=?", (remote, last["fetch_id"]))
            return f"rebuild failed ({type(e).__name__}); using cached data"
    with con:
        con.execute("UPDATE fetches SET checked_at=?, remote_version=? WHERE fetch_id=?",
                    (_now().isoformat(), remote, last["fetch_id"]))
    return "fresh"


def freshness(con: sqlite3.Connection, now: datetime | None = None) -> dict:
    """The "as of" block attached to every tool answer."""
    last = latest_fetch(con)
    if last is None:
        return {"stale": True, "note": "no card data has been fetched"}
    now = now or _now()
    verified = datetime.fromisoformat(last["checked_at"])
    behind = last["remote_version"] not in (None, last["db_version"])
    return {
        "fetched_at": last["fetched_at"],
        "verified_current_at": last["checked_at"],
        "ygoprodeck_db": f"{last['db_version']} ({last['db_last_update']})",
        "tcg_list": last["ignis_title"],
        "stale": behind or now - verified > STALE_AFTER,
        "note": ("YGOProDeck has a newer database than this index. " if behind else "")
                + "Genesys points as published on YGOProDeck at fetch time; Konami publishes no effective date.",
    }
