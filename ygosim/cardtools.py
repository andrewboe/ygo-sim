"""Card search, lookup and archetype views over data/cards.sqlite, format-aware (MCP tools' core).

Archetype membership follows the game rule: a card is an "X" card if its name contains X
(case-sensitive; a few cards are exceptions). YGOProDeck's archetype tag also covers support cards
that are not members (e.g. "Dark City" is tagged Destiny HERO), so tag-only cards are listed as
support, alongside outside cards whose text names "X".
"""
import re
import sqlite3
from datetime import date

from .formats import FORMATS, DeckInputError, card_status, resolve

SPELL_TRAP_KINDS = {"normal spell": ("spell", "Normal"), "quick-play": ("spell", "Quick-Play"),
                    "continuous spell": ("spell", "Continuous"), "field": ("spell", "Field"),
                    "equip": ("spell", "Equip"), "ritual spell": ("spell", "Ritual"),
                    "normal trap": ("trap", "Normal"), "continuous trap": ("trap", "Continuous"),
                    "counter": ("trap", "Counter")}
MONSTER_KINDS = {"monster", "extra", "main", "tuner", "normal", "effect", "fusion", "synchro", "xyz",
                 "link", "ritual", "pendulum", "flip", "gemini", "spirit", "union", "toon"}
TEXT_CHARS = 400


def _spec(format: str):
    if format not in FORMATS:
        raise DeckInputError(f"unknown format {format!r}; known: {', '.join(FORMATS)}")
    return FORMATS[format]


def _is_monster(c) -> bool:
    return c["frame_type"] not in ("spell", "trap", "token", "skill")


def _kind_ok(c, kind: str) -> bool:
    k = kind.casefold().strip()
    if k in ("spell", "trap"):
        return c["frame_type"] == k
    if k in SPELL_TRAP_KINDS:
        frame, race = SPELL_TRAP_KINDS[k]
        return c["frame_type"] == frame and c["race"] == race
    if not _is_monster(c):
        return False
    parts = set(c["frame_type"].split("_"))
    is_extra = bool(parts & {"fusion", "synchro", "xyz", "link"})
    if k == "monster":
        return True
    if k == "extra":
        return is_extra
    if k == "main":
        return not is_extra
    if k in parts:
        return True
    return k in c["type"].casefold()  # tuner, flip, gemini, spirit, union, toon


def _row(con, c, spec, day, full_text: bool) -> dict:
    text = c["desc"] if full_text or len(c["desc"]) <= TEXT_CHARS else c["desc"][:TEXT_CHARS] + " …"
    out = {"passcode": c["canonical_id"], "name": c["name"], "type": c["type"]}
    if _is_monster(c):
        stat = "link" if c["frame_type"] == "link" else ("rank" if "xyz" in c["frame_type"] else "level")
        out.update({"attribute": c["attribute"], "race": c["race"],
                    stat: c["linkval"] if stat == "link" else c["level"], "atk": c["atk"], "def": c["def"]})
    else:
        out["property"] = c["race"]
    if c["archetype"]:
        out["archetype"] = c["archetype"]
    out[spec.key] = card_status(con, spec, c, day)
    out["text"] = text
    return out


def _canonical(con, where: str = "1", params=()) -> list[sqlite3.Row]:
    return con.execute(f"SELECT * FROM cards WHERE passcode = canonical_id AND {where}", params).fetchall()


def members(con, name: str) -> list[sqlite3.Row]:
    """Cards whose name contains `name` (case-sensitive), i.e. archetype members by the game rule."""
    return _canonical(con, "type NOT IN ('Token','Skill Card') AND instr(name, ?) > 0", (name,))


def _fts_query(text: str) -> str:
    """Accept FTS5 syntax; otherwise AND the words (quoted, so punctuation can't break the query)."""
    if re.search(r'\b(AND|OR|NOT|NEAR)\b|"', text):
        return text
    return " AND ".join(f'"{w}"' for w in re.findall(r"[\w'-]+", text))


def search_cards(con: sqlite3.Connection, format: str, text: str | None = None, pattern: str | None = None,
                 name: str | None = None, archetype: str | None = None, mentions: str | None = None,
                 kind: str | None = None, attribute: str | None = None, race: str | None = None,
                 level_min: int | None = None, level_max: int | None = None, atk_max: int | None = None,
                 def_max: int | None = None, max_points: int | None = None, include_illegal: bool = False,
                 as_of: str | None = None, limit: int = 20, full_text: bool = False) -> dict:
    spec = _spec(format)
    day = date.fromisoformat(as_of) if as_of else date.today()
    where, params = ["passcode = canonical_id", "type NOT IN ('Token','Skill Card')"], []
    order = "name"
    if text:
        where.append("canonical_id IN (SELECT canonical_id FROM cards_fts WHERE cards_fts MATCH ?)")
        params.append(_fts_query(text))
    if name:
        where.append("instr(lower(name), lower(?)) > 0")
        params.append(name)
    if archetype:
        where.append("instr(name, ?) > 0")  # membership by name, as in archetype()
        params.append(archetype)
    if mentions:
        where.append("canonical_id IN (SELECT canonical_id FROM mentions WHERE mention = ? COLLATE NOCASE)")
        params.append(mentions)
    if attribute:
        where.append("attribute = ? COLLATE NOCASE")
        params.append(attribute)
    if race:
        where.append("race = ? COLLATE NOCASE")
        params.append(race)
    for col, op, v in (("coalesce(level, linkval)", ">=", level_min), ("coalesce(level, linkval)", "<=", level_max),
                       ("atk", "<=", atk_max), ("def", "<=", def_max)):
        if v is not None:
            where.append(f"{col} {op} ?")
            params.append(v)
    try:
        rows = con.execute(f"SELECT * FROM cards WHERE {' AND '.join(where)} ORDER BY {order}", params).fetchall()
    except sqlite3.OperationalError as e:
        raise DeckInputError(f"bad text query {text!r}: {e}") from None
    rx = re.compile(pattern, re.I) if pattern else None
    out, skipped = [], 0
    for c in rows:
        if kind and not _kind_ok(c, kind):
            continue
        if rx and not rx.search(c["desc"]):
            continue
        st = card_status(con, spec, c, day)
        if not include_illegal and not st["legal"]:
            skipped += 1
            continue
        if max_points is not None and st.get("points", 0) > max_points:
            continue
        out.append(c)
    shown = [_row(con, c, spec, day, full_text) for c in out[:limit]]
    res = {"format": spec.title, "matches": len(out), "shown": len(shown), "cards": shown}
    if len(out) > limit:
        res["note"] = f"{len(out) - limit} more; narrow the filters or raise limit"
    if skipped:
        res["hidden_illegal"] = skipped
    return res


def card_lookup(con: sqlite3.Connection, query: str | int) -> dict:
    """Everything about one card, in every registered format."""
    pid, note = resolve(con, str(query))
    if pid is None:
        return {"match": "none", "error": note}
    c = con.execute("SELECT * FROM cards WHERE passcode = ?", (pid,)).fetchone()
    if c is None:
        return {"match": "none", "error": f"unknown passcode {pid}", "candidates": []}
    c = con.execute("SELECT * FROM cards WHERE passcode = ?", (c["canonical_id"],)).fetchone()
    row = _row(con, c, FORMATS["tcg_advanced"], date.today(), full_text=True)
    row.pop("tcg_advanced")
    row["formats"] = {k: card_status(con, spec, c, date.today()) for k, spec in FORMATS.items()}
    alts = [r[0] for r in con.execute("SELECT passcode FROM cards WHERE canonical_id = ? AND passcode != ?",
                                      (c["canonical_id"], c["canonical_id"]))]
    if alts:
        row["alt_passcodes"] = alts
    row["tcg_date"], row["ocg_date"] = c["tcg_date"], c["ocg_date"]
    row["mentions"] = [r[0] for r in con.execute("SELECT mention FROM mentions WHERE canonical_id = ?",
                                                  (c["canonical_id"],))]
    if c["konami_id"]:
        row["rulings_links"] = [
            f"https://www.db.yugioh-card.com/yugiohdb/card_search.action?ope=2&cid={c['konami_id']}&request_locale=en",
            f"https://db.ygoresources.com/card#{c['konami_id']}"]
    return {"match": "exact" if not note else "normalized", **({"resolved": note} if note else {}), "card": row}


def archetype(con: sqlite3.Connection, name: str, format: str, as_of: str | None = None,
              include_text: bool | None = None) -> dict:
    """Members of an archetype plus outside cards whose text names it ("support").
    Card text is included when the answer is small (<= 60 cards) unless include_text says otherwise."""
    spec = _spec(format)
    day = date.fromisoformat(as_of) if as_of else date.today()
    mem = members(con, name)
    if not mem:  # e.g. wrong capitalization: suggest names and tags that do exist
        tags = [r[0] for r in con.execute("SELECT DISTINCT archetype FROM cards WHERE archetype LIKE ? LIMIT 10",
                                          (f"%{name}%",))]
        return {"archetype": name, "members": [], "error": f"no card name contains '{name}' (case-sensitive)",
                "similar_archetypes": tags}
    ids = {c["canonical_id"] for c in mem}
    support = [c for c in _canonical(con, "type NOT IN ('Token','Skill Card') AND (archetype = ? COLLATE NOCASE OR "
                                          "canonical_id IN (SELECT canonical_id FROM mentions WHERE mention = ?))",
                                     (name, name))
               if c["canonical_id"] not in ids]

    with_text = include_text if include_text is not None else len(mem) + len(support) <= 60

    def rows(cards):
        out = [_row(con, c, spec, day, full_text=True) for c in cards]
        if not with_text:
            for r in out:
                r.pop("text")
        return out

    mem_rows = rows(mem)
    legal = [r for r in mem_rows if r[spec.key]["legal"]]
    res = {"archetype": name, "format": spec.title, "members": len(mem_rows), "legal_members": len(legal),
           "cards": mem_rows, "support": rows(support)}
    if spec.points:
        res["points_if_one_of_each_legal"] = sum(r[spec.key].get("points", 0) for r in legal)
    return res
