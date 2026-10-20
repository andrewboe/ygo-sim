"""Format rules as data, a strict deck parser, and validate_deck (the MCP tool's core).

Formats: tcg_advanced (Forbidden & Limited, stricter of YGOProDeck and Ignis) and genesys
(no F&L, no Link/Pendulum, Main+Extra+Side points under a cap). Rules are FormatSpec rows so a
rule change is a data edit. Rulings are out of scope: this checks construction legality only.
"""
import base64
import re
import sqlite3
import struct
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .carddata import freshness, loose_name, norm_name

ZONES = ("main", "extra", "side")
EXTRA_FRAMES = {"fusion", "synchro", "xyz", "link"}
BAN_LABEL = {0: "Forbidden", 1: "Limited", 2: "Semi-Limited", 3: "Unlimited"}


@dataclass(frozen=True)
class FormatSpec:
    key: str
    title: str
    region: str  # "tcg" | "ocg": which release date gates the card pool
    limits: str | None  # limits-table format, or None when no Forbidden & Limited list applies
    points: str | None = None  # points-table format
    default_cap: int | None = None
    banned_frames: frozenset[str] = frozenset()  # frameType parts, e.g. "link", "pendulum"
    main: tuple[int, int] = (40, 60)
    extra_max: int = 15
    side_max: int = 15
    max_copies: int = 3
    banned_types: frozenset[str] = frozenset({"Token", "Skill Card"})


FORMATS = {f.key: f for f in (
    FormatSpec("tcg_advanced", "TCG Advanced", "tcg", limits="tcg"),
    FormatSpec("genesys", "Genesys", "tcg", limits=None, points="genesys", default_cap=100,
               banned_frames=frozenset({"link", "pendulum"})),
)}


class DeckInputError(ValueError):
    pass


@dataclass
class ParsedDeck:
    zones: dict[str, list[int]] = field(default_factory=lambda: {z: [] for z in ZONES})
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    resolved: list[str] = field(default_factory=list)  # name inputs that needed normalizing


# ---------------------------------------------------------------- parsing

def parse_ydk(text: str) -> ParsedDeck:
    """Strict .ydk parser: every non-blank line must be a section marker, a comment or a passcode."""
    deck = ParsedDeck()
    if text.startswith("﻿"):
        text = text[1:]
    if "\r" in text:
        deck.warnings.append("file has CRLF line endings: EDOPro reads it, but ygoenv's parser drops "
                             "'\\r'-terminated card lines (the simulator would see no cards)")
    zone, seen = None, set()
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        marker = {"#main": "main", "#extra": "extra", "!side": "side"}.get(line.lower())
        if marker:
            if marker in seen:
                deck.errors.append(f"line {n}: duplicate section '{line}'")
            zone = marker
            seen.add(marker)
        elif not line:
            continue
        elif line.lower() == "#side":
            deck.errors.append(f"line {n}: '#side' is not a section marker (use '!side'); "
                               "EDOPro would put the cards below it in the Extra Deck")
        elif line.startswith("#"):
            continue  # comment, e.g. "#created by ..."
        elif line.isdigit():
            if zone is None:
                deck.errors.append(f"line {n}: card {line} before any #main/#extra/!side marker")
            else:
                deck.zones[zone].append(int(line))
        else:
            deck.errors.append(f"line {n}: unreadable line {raw!r} (a card line must be only a passcode)")
    if not seen:
        deck.errors.append("no #main/#extra/!side markers: not a .ydk file")
    return deck


def parse_ydke(url: str) -> ParsedDeck:
    """ydke://<main>!<extra>!<side>! with each part base64 little-endian uint32 passcodes."""
    deck = ParsedDeck()
    parts = url.strip()[len("ydke://"):].split("!")
    if len(parts) < 3:
        deck.errors.append("ydke URL needs three '!'-separated parts (main, extra, side)")
        return deck
    for zone, part in zip(ZONES, parts):
        try:
            raw = base64.b64decode(part, validate=True)
        except ValueError:
            deck.errors.append(f"ydke {zone} part is not valid base64")
            continue
        if len(raw) % 4:
            deck.errors.append(f"ydke {zone} part is {len(raw)} bytes, not a multiple of 4")
            continue
        deck.zones[zone] = [v for (v,) in struct.iter_unpack("<I", raw)]
    return deck


_COUNT = re.compile(r"^\s*(?:(\d+)\s*x?\s+(.+?)|(.+?)\s+x\s*(\d+))\s*$", re.I)


def parse_names(con: sqlite3.Connection, decklist: dict[str, list[str]]) -> ParsedDeck:
    """{"main": ["3 Ash Blossom & Joyous Spring", "Called by the Grave x2", "14558127"], ...}"""
    deck = ParsedDeck()
    for zone, entries in decklist.items():
        if zone not in ZONES:
            deck.errors.append(f"unknown zone {zone!r} (use main, extra, side)")
            continue
        for entry in entries or []:
            entry = str(entry).strip()
            # A bare number is a passcode; "3 Foo" / "3x Foo" / "Foo x3" carry a count unless the
            # whole entry is itself a card name (e.g. "7 Colored Fish").
            count, (pid, note) = 1, resolve(con, entry)
            if pid is None and not entry.isdigit() and (m := _COUNT.match(entry)):
                count = int(m.group(1) or m.group(4))
                pid, note = resolve(con, (m.group(2) or m.group(3)).strip())
            if pid is None:
                deck.errors.append(f"{zone}: {note}")
            else:
                if note:
                    deck.resolved.append(note)
                deck.zones[zone].extend([pid] * count)
    return deck


def resolve(con: sqlite3.Connection, query: str) -> tuple[int | None, str]:
    """Passcode or name -> passcode. Exact, then normalized, then star/space-insensitive if unique.
    Never guesses: anything fuzzier comes back as an error with candidates."""
    q = query.strip()
    if q.isdigit():
        return int(q), ""
    rows = con.execute("SELECT DISTINCT canonical_id, name FROM cards WHERE name = ?", (q,)).fetchall()
    if not rows:
        rows = con.execute("SELECT DISTINCT canonical_id, name FROM cards WHERE name_norm = ?",
                           (norm_name(q),)).fetchall()
    if not rows:
        rows = con.execute("SELECT DISTINCT canonical_id, name FROM cards WHERE name_loose = ?",
                           (loose_name(q),)).fetchall()
    if not rows:  # pre-release / unofficial name
        rows = con.execute("SELECT DISTINCT canonical_id, name FROM cards WHERE beta_name = ? COLLATE NOCASE",
                           (q,)).fetchall()
    if len(rows) == 1:
        name = rows[0]["name"]
        return rows[0]["canonical_id"], (f"'{q}' -> '{name}'" if name != q else "")
    if len(rows) > 1:
        return None, f"'{q}' is ambiguous: " + "; ".join(f"{r['name']} ({r['canonical_id']})" for r in rows)
    cands = candidates(con, q)
    return None, f"no card named '{q}'" + (f"; did you mean: {'; '.join(cands)}" if cands else "")


def candidates(con: sqlite3.Connection, q: str, limit: int = 5) -> list[str]:
    words = norm_name(q).split()
    if not words:
        return []
    where = " AND ".join("name_norm LIKE ?" for _ in words)
    rows = con.execute(f"SELECT DISTINCT canonical_id, name FROM cards WHERE {where} "
                       "AND type NOT IN ('Token','Skill Card') ORDER BY length(name) LIMIT ?",
                       [f"%{w}%" for w in words] + [limit]).fetchall()
    return [f"{r['name']} ({r['canonical_id']})" for r in rows]


def parse_input(con: sqlite3.Connection, ydk_path: str | None, ydk_text: str | None,
                decklist: dict | None) -> ParsedDeck:
    given = [x is not None for x in (ydk_path, ydk_text, decklist)]
    if sum(given) != 1:
        raise DeckInputError("pass exactly one of ydk_path, ydk_text, decklist")
    if decklist is not None:
        return parse_names(con, decklist)
    if ydk_path is not None:
        path = Path(ydk_path).expanduser()
        if not path.is_file():
            raise DeckInputError(f"no such file: {path}")
        ydk_text = path.read_text(encoding="utf-8-sig", errors="strict")
    if ydk_text.strip().lower().startswith("ydke://"):
        return parse_ydke(ydk_text)
    return parse_ydk(ydk_text)


# ---------------------------------------------------------------- validation

def _frame_parts(frame: str) -> set[str]:
    return set(frame.split("_"))


def validate_deck(con: sqlite3.Connection, format: str, ydk_path: str | None = None,
                  ydk_text: str | None = None, decklist: dict | None = None,
                  point_cap: int | None = None, as_of: str | None = None) -> dict:
    spec = FORMATS.get(format)
    if spec is None:
        raise DeckInputError(f"unknown format {format!r}; known: {', '.join(FORMATS)}")
    day = date.fromisoformat(as_of) if as_of else date.today()
    cap = point_cap if point_cap is not None else spec.default_cap
    data = freshness(con)
    deck = parse_input(con, ydk_path, ydk_text, decklist)

    # Every passcode must resolve before anything is validated: no partial answers.
    cards: dict[int, sqlite3.Row] = {}
    for pid in {p for z in deck.zones.values() for p in z}:
        row = con.execute("SELECT * FROM cards WHERE passcode = ?", (pid,)).fetchone()
        if row is None:
            deck.errors.append(f"unknown passcode {pid}: not in YGOProDeck's database as of "
                               f"{data.get('fetched_at')} (typo, or a card newer than the data)")
        else:
            cards[pid] = row
    if deck.errors:
        return {"legal": None, "format": spec.title,
                "summary": f"NOT VALIDATED: {len(deck.errors)} input problem(s); fix them and retry. "
                           "No card was dropped or guessed.",
                "parse_errors": deck.errors, "warnings": deck.warnings, "data": data}

    problems, rows = [], []
    by_canon: Counter = Counter()
    totals = {z: {"cards": 0, "points": 0} for z in ZONES}
    for zone in ZONES:
        counts: Counter = Counter()
        alts: dict[int, set[int]] = {}
        for pid in deck.zones[zone]:
            cid = cards[pid]["canonical_id"]
            counts[cid] += 1
            if pid != cid:
                alts.setdefault(cid, set()).add(pid)
        for cid, n in sorted(counts.items(), key=lambda kv: cards_name(con, kv[0])):
            c = con.execute("SELECT * FROM cards WHERE passcode = ?", (cid,)).fetchone()
            by_canon[cid] += n
            frames = _frame_parts(c["frame_type"])
            flags = []
            limit = _limit(con, spec, cid)
            pts = _points(con, spec, cid)
            released = c["tcg_date"] if spec.region == "tcg" else c["ocg_date"]
            if released is None or date.fromisoformat(released) > day:
                flags.append(f"not {spec.region.upper()}-released by {day} "
                             f"({released or 'no ' + spec.region.upper() + ' release'})")
            if bad := frames & spec.banned_frames:
                flags.append(f"{'/'.join(sorted(bad)).title()} Monster: not allowed in {spec.title}")
            if c["type"] in spec.banned_types:
                flags.append(f"{c['type']}: not a deck card")
            is_extra = bool(frames & EXTRA_FRAMES)
            if zone == "main" and is_extra:
                flags.append("Extra Deck monster in the Main Deck")
            if zone == "extra" and not is_extra:
                flags.append("Main Deck card in the Extra Deck")
            for f in flags:
                problems.append(f"{c['name']} ({cid}, {zone}): {f}")
            row = {"zone": zone, "count": n, "passcode": cid, "name": c["name"], "type": c["type"],
                   "limit": limit}
            if spec.limits:
                row["status"] = BAN_LABEL[limit]
            if spec.points:
                row["points"], row["points_total"] = pts, pts * n
            if cid in alts:
                row["alt_passcodes"] = sorted(alts[cid])
            if flags:
                row["flags"] = flags
            rows.append(row)
            totals[zone]["cards"] += n
            totals[zone]["points"] += pts * n

    for cid, n in by_canon.items():
        limit = _limit(con, spec, cid)
        if n > limit:
            why = BAN_LABEL[limit] if spec.limits and limit < spec.max_copies else "copy limit"
            problems.append(f"{cards_name(con, cid)} ({cid}): {n} {'copy' if n == 1 else 'copies'} across Main/Extra/Side, "
                            f"{why} allows {limit}")

    lo, hi = spec.main
    if not lo <= totals["main"]["cards"] <= hi:
        problems.append(f"Main Deck has {totals['main']['cards']} cards (needs {lo}-{hi})")
    if totals["extra"]["cards"] > spec.extra_max:
        problems.append(f"Extra Deck has {totals['extra']['cards']} cards (max {spec.extra_max})")
    if totals["side"]["cards"] > spec.side_max:
        problems.append(f"Side Deck has {totals['side']['cards']} cards (max {spec.side_max})")
    deck_points = sum(t["points"] for t in totals.values())
    if spec.points and deck_points > cap:
        problems.append(f"Points {deck_points} > cap {cap} (Main+Extra+Side)")

    size = f"Main {totals['main']['cards']}, Extra {totals['extra']['cards']}, Side {totals['side']['cards']}"
    pts_line = (f" Points {deck_points}/{cap} (Main {totals['main']['points']}, Extra "
                f"{totals['extra']['points']}, Side {totals['side']['points']})." if spec.points else "")
    where = f"{spec.title}" + (f" (cap {cap})" if spec.points else f" ({data.get('tcg_list')})")
    verdict = "LEGAL" if not problems else f"ILLEGAL: {len(problems)} problem(s)"
    out = {
        "legal": not problems, "format": spec.title,
        "summary": f"{verdict} in {where}.{pts_line} {size}. Data as of {data.get('fetched_at')}"
                   + (" (STALE)" if data.get("stale") else "") + ".",
        "problems": problems, "warnings": deck.warnings, "cards": rows,
        "totals": {**totals, **({"deck_points": deck_points, "point_cap": cap} if spec.points else {})},
        "data": data,
    }
    if deck.resolved:
        out["resolved_names"] = deck.resolved
    return out


def cards_name(con: sqlite3.Connection, cid: int) -> str:
    return con.execute("SELECT name FROM cards WHERE passcode = ?", (cid,)).fetchone()["name"]


def _limit(con: sqlite3.Connection, spec: FormatSpec, cid: int) -> int:
    if spec.limits is None:
        return spec.max_copies
    r = con.execute("SELECT lim FROM limits WHERE format = ? AND canonical_id = ?", (spec.limits, cid)).fetchone()
    return min(r["lim"], spec.max_copies) if r else spec.max_copies


def _points(con: sqlite3.Connection, spec: FormatSpec, cid: int) -> int:
    if spec.points is None:
        return 0
    r = con.execute("SELECT points FROM points WHERE format = ? AND canonical_id = ?", (spec.points, cid)).fetchone()
    return r["points"] if r else 0


def card_status(con: sqlite3.Connection, spec: FormatSpec, c: sqlite3.Row, day: date | None = None) -> dict:
    """One canonical card's standing in a format: playable copies, points, and why not if not."""
    day = day or date.today()
    cid = c["canonical_id"]
    out: dict = {"limit": _limit(con, spec, cid)}
    if spec.limits:
        out["status"] = BAN_LABEL[out["limit"]]
    if spec.points:
        out["points"] = _points(con, spec, cid)
    why = []
    released = c["tcg_date"] if spec.region == "tcg" else c["ocg_date"]
    if released is None or date.fromisoformat(released) > day:
        why.append(f"not {spec.region.upper()}-released ({released or 'no ' + spec.region.upper() + ' release'})")
    if bad := _frame_parts(c["frame_type"]) & spec.banned_frames:
        why.append(f"{'/'.join(sorted(bad)).title()} Monster")
    if c["type"] in spec.banned_types:
        why.append(c["type"])
    if out["limit"] == 0:
        why.append("Forbidden")
    out["legal"] = not why
    if why:
        out["why_not"] = why
    return out
