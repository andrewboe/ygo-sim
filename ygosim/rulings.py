"""card_rulings: official FAQ and Q&A for a card, from YGOResources (db.ygoresources.com), cached.

YGOResources mirrors Konami's OCG database FAQ/Q&A with community translations. Their API page asks
for on-demand requests, local caching and no load on their servers (a full offline copy is
available on request instead of crawling). So:
  - only the cards and Q&As a question needs are fetched, at most MAX_FETCH per call;
  - everything is cached in cards.sqlite (rul_* tables, untouched by card rebuilds);
  - at most once per CHECK_EVERY, /manifest/<revision> lists what changed, and only those
    cached entries are dropped.
These are OCG rulings; TCG rulings can differ. The tool quotes them and does not reason past them.
"""
import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone

from .api import _get
from .formats import DeckInputError, resolve

BASE = "https://db.ygoresources.com"
CHECK_EVERY = timedelta(hours=24)
MAX_FETCH = 20  # Q&A requests per call, to stay polite
REF = re.compile(r"<<(-?\d+)>>")

SCHEMA = """
CREATE TABLE IF NOT EXISTS rul_card (konami_id INTEGER PRIMARY KEY, body TEXT, fetched_at TEXT);
CREATE TABLE IF NOT EXISTS rul_qa (qa_id INTEGER PRIMARY KEY, body TEXT, fetched_at TEXT);
CREATE TABLE IF NOT EXISTS rul_names (konami_id INTEGER PRIMARY KEY, name TEXT);
CREATE TABLE IF NOT EXISTS rul_state (key TEXT PRIMARY KEY, value TEXT);
"""


def http_get(path: str) -> tuple[dict, int | None]:
    """GET a YGOResources JSON path; returns (body, X-Cache-Revision). Tests replace this."""
    resp = _get(BASE + path)
    rev = resp.headers.get("X-Cache-Revision")
    return resp.json(), int(rev) if rev and rev.isdigit() else None


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


class Rulings:
    def __init__(self, con: sqlite3.Connection, fetch=None):
        self.con = con
        self.fetch = fetch or http_get
        self.fetched = 0
        con.executescript(SCHEMA)

    # -- state / cache
    def _state(self, key: str) -> str | None:
        r = self.con.execute("SELECT value FROM rul_state WHERE key = ?", (key,)).fetchone()
        return r[0] if r else None

    def _set_state(self, **kv) -> None:
        with self.con:
            self.con.executemany("INSERT OR REPLACE INTO rul_state VALUES (?, ?)", [(k, str(v)) for k, v in kv.items()])

    def _get(self, path: str) -> dict:
        body, rev = self.fetch(path)
        self.fetched += 1
        if rev is not None and self._state("revision") is None:
            self._set_state(revision=rev, checked_at=_now().isoformat())
        return body

    def sync(self) -> str:
        """Drop cached entries YGOResources changed since our revision (at most once per CHECK_EVERY)."""
        rev, checked = self._state("revision"), self._state("checked_at")
        if rev is None or (checked and _now() - datetime.fromisoformat(checked) < CHECK_EVERY):
            return "fresh"
        try:
            body, new_rev = self.fetch(f"/manifest/{rev}")
        except Exception as e:  # offline: serve the cache
            return f"change check failed ({type(e).__name__}); cached rulings may be out of date"
        changed = body.get("data", {})
        with self.con:
            self.con.executemany("DELETE FROM rul_card WHERE konami_id = ?", [(int(k),) for k in changed.get("card", {})])
            self.con.executemany("DELETE FROM rul_qa WHERE qa_id = ?", [(int(k),) for k in changed.get("qa", {})])
        self._set_state(revision=new_rev or rev, checked_at=_now().isoformat())
        return f"synced ({len(changed.get('card', {}))} cards, {len(changed.get('qa', {}))} Q&As changed)"

    def card(self, kid: int) -> dict:
        r = self.con.execute("SELECT body FROM rul_card WHERE konami_id = ?", (kid,)).fetchone()
        if r:
            return json.loads(r[0])
        body = self._get(f"/data/card/{kid}")
        with self.con:
            self.con.execute("INSERT OR REPLACE INTO rul_card VALUES (?, ?, ?)", (kid, json.dumps(body), _now().isoformat()))
        return body

    def qa(self, qid: int, budget: bool = True) -> dict | None:
        r = self.con.execute("SELECT body FROM rul_qa WHERE qa_id = ?", (qid,)).fetchone()
        if r:
            return json.loads(r[0])
        if budget and self.fetched >= MAX_FETCH:
            return None
        body = self._get(f"/data/qa/{qid}")
        with self.con:
            self.con.execute("INSERT OR REPLACE INTO rul_qa VALUES (?, ?, ?)", (qid, json.dumps(body), _now().isoformat()))
        return body

    # -- names
    def name(self, kid: int) -> str:
        r = self.con.execute("SELECT name FROM cards WHERE konami_id = ? LIMIT 1", (kid,)).fetchone()
        if r:
            return r[0]
        r = self.con.execute("SELECT name FROM rul_names WHERE konami_id = ?", (kid,)).fetchone()
        if r:
            return r[0]
        if self._state("names_loaded") is None and self.fetched < MAX_FETCH:
            # One request maps every English name to Konami ids; cached for good (refetched if the state is cleared).
            idx = self._get("/data/idx/card/name/en")
            rows = {}
            for nm, ids in idx.items():
                for i in ids:
                    rows.setdefault(i, nm)
            with self.con:
                self.con.executemany("INSERT OR REPLACE INTO rul_names VALUES (?, ?)", list(rows.items()))
            self._set_state(names_loaded=_now().isoformat())
            return self.name(kid)
        return f"[Konami card {kid}]"

    def text(self, s: str | None) -> str | None:
        return REF.sub(lambda m: f'"{self.name(int(m.group(1)))}"', s) if s else s


def _konami_id(con: sqlite3.Connection, query: str) -> tuple[int, str]:
    pid, note = resolve(con, query)
    if pid is None:
        raise DeckInputError(note)
    r = con.execute("SELECT c2.name, c2.konami_id FROM cards c JOIN cards c2 ON c2.passcode = c.canonical_id "
                    "WHERE c.passcode = ?", (pid,)).fetchone()
    if r is None:
        raise DeckInputError(f"unknown passcode {pid}")
    if not r["konami_id"]:
        raise DeckInputError(f"{r['name']} has no Konami database id yet (too new, or not in Konami's database)")
    return r["konami_id"], r["name"]


def card_rulings(con: sqlite3.Connection, card: str, with_card: str | None = None, query: str | None = None,
                 limit: int = 8, fetch=None) -> dict:
    """FAQ entries and Q&As for `card`; with_card keeps only Q&As involving both cards; query keeps Q&As
    containing all its words (searching at most MAX_FETCH uncached Q&As per call)."""
    try:
        return _card_rulings(con, card, with_card, query, limit, fetch)
    except DeckInputError:
        raise
    except Exception as e:  # network or unexpected response: say so instead of failing the call
        raise DeckInputError(f"YGOResources request failed ({type(e).__name__}: {e}); "
                             "cached rulings are still used when available") from None


def _card_rulings(con, card, with_card, query, limit, fetch) -> dict:
    rul = Rulings(con, fetch)
    sync = rul.sync()
    kid, name = _konami_id(con, card)
    body = rul.card(kid)
    faq = []
    for _, lines in sorted((body.get("faqData") or {}).get("entries", {}).items(), key=lambda kv: int(kv[0])):
        en = [rul.text(x.get("en")) for x in lines if x.get("en")]
        if en:
            faq.append(" ".join(en))
    qids = sorted(set(body.get("qaIndex") or []), reverse=True)  # newest first
    out = {"card": name, "konami_id": kid}
    if with_card:
        kid2, name2 = _konami_id(con, with_card)
        qids = [q for q in qids if q in set(rul.card(kid2).get("qaIndex") or [])]
        out["with_card"] = name2
    words = [w.casefold() for w in re.findall(r"\w+", query or "")]
    shown, searched, skipped = [], 0, 0
    for q in qids:
        if len(shown) >= limit:
            break
        data = rul.qa(q)
        if data is None:
            skipped += 1
            continue
        searched += 1
        en = (data.get("qaData") or {}).get("en") or {}
        if not en.get("answer"):
            continue
        item = {"id": q, "title": rul.text(en.get("title")), "question": rul.text(en.get("question")),
                "answer": rul.text(en.get("answer")), "date": (en.get("thisSrc") or {}).get("date"),
                "translation": en.get("translationStatus"), "cards": [rul.name(c) for c in data.get("cards", [])],
                "url": f"{BASE}/qa#{q}"}
        hay = " ".join(str(item[k]) for k in ("title", "question", "answer")).casefold()
        if all(w in hay for w in words):
            shown.append(item)
    out.update({
        "faq": faq, "qa_total": len(qids), "qa_shown": len(shown), "qa": shown,
        "card_url": f"{BASE}/card#{kid}",
        "source": "YGOResources: Konami's official OCG FAQ/Q&A with community translations "
                  "('translation' says how settled each one is). OCG rulings; TCG rulings can differ. "
                  "Quote these; don't extend them to cases they don't cover.",
        "cache": {"revision": rul._state("revision"), "checked_at": rul._state("checked_at"), "sync": sync,
                  "fetched_now": rul.fetched},
    })
    if words and len(shown) < limit and (skipped or searched < len(qids)):
        out["note"] = (f"searched {searched} of {len(qids)} Q&As (fetch cap {MAX_FETCH} per call); "
                       "ask again to search more, or open card_url")
    elif skipped:
        out["note"] = f"{skipped} Q&As not fetched this call (fetch cap {MAX_FETCH}); ask again for more"
    return out
