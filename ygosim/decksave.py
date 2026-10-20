"""finalize_deck: save a deck only once validate_deck says it is legal; saved_decks lists them.

Files in data/decks/: <slug>.<format>.ydk (EDOPro/YGOPro, LF line endings) and <slug>.<format>.json
(name, format, saved_at, ydke URL, text list, points/limits breakdown, data freshness). Saving the
same name again replaces those two and keeps the old .ydk under data/decks/history/.
"""
import base64
import json
import re
import shutil
import sqlite3
import struct
from datetime import datetime, timezone

from .api import DATA_DIR
from .formats import FORMATS, ZONES, DeckInputError, parse_input, validate_deck

DECKS_DIR = DATA_DIR / "decks"


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")[:60] or "deck"


def ydke(zones: dict[str, list[int]]) -> str:
    parts = [base64.b64encode(b"".join(struct.pack("<I", p) for p in zones[z])).decode() for z in ZONES]
    return "ydke://" + "!".join(parts) + "!"


def ydk_text(zones: dict[str, list[int]], name: str) -> str:
    lines = [f"#created by ygosim finalize_deck: {name}", "#main", *map(str, zones["main"]),
             "#extra", *map(str, zones["extra"]), "!side", *map(str, zones["side"])]
    return "\n".join(lines) + "\n"


def finalize_deck(con: sqlite3.Connection, format: str, name: str, decklist: dict | None = None,
                  ydk_path: str | None = None, ydk_text_in: str | None = None, point_cap: int | None = None,
                  notes: str | None = None, as_of: str | None = None) -> dict:
    spec = FORMATS.get(format)
    if spec is None:
        raise DeckInputError(f"unknown format {format!r}; known: {', '.join(FORMATS)}")
    if not name.strip():
        raise DeckInputError("name the deck")
    check = validate_deck(con, format, ydk_path=ydk_path, ydk_text=ydk_text_in, decklist=decklist,
                          point_cap=point_cap, as_of=as_of)
    if check["legal"] is not True:
        return {"saved": False, "reason": "the deck does not validate; nothing was written",
                **{k: check[k] for k in ("summary", "problems", "parse_errors", "data") if k in check}}

    zones = parse_input(con, ydk_path, ydk_text_in, decklist).zones
    text = []
    for zone in ZONES:
        rows = [c for c in check["cards"] if c["zone"] == zone]
        text.append(f"{zone.title()} ({check['totals'][zone]['cards']})")
        for c in rows:
            tail = f"  [{c['points']} pts]" if c.get("points") else (f"  [{c['status']}]" if c.get("status") not in
                                                                         (None, "Unlimited") else "")
            text.append(f"{c['count']} {c['name']}{tail}")
    breakdown = {"totals": check["totals"]}
    if spec.points:
        breakdown["pointed_cards"] = [f"{c['count']}x {c['name']} = {c['points_total']}"
                                      for c in check["cards"] if c.get("points")]
    else:
        breakdown["restricted_cards"] = [f"{c['count']}x {c['name']} ({c['status']})"
                                         for c in check["cards"] if c.get("status") not in (None, "Unlimited")]

    DECKS_DIR.mkdir(parents=True, exist_ok=True)
    stem = f"{slug(name)}.{format}"
    ydk_path_out, meta_path = DECKS_DIR / f"{stem}.ydk", DECKS_DIR / f"{stem}.json"
    now = datetime.now(timezone.utc).replace(microsecond=0)
    replaced = None
    if ydk_path_out.exists():
        hist = DECKS_DIR / "history"
        hist.mkdir(exist_ok=True)
        replaced = hist / f"{stem}.{now.strftime('%Y%m%dT%H%M%SZ')}.ydk"
        shutil.copy2(ydk_path_out, replaced)
    ydk_path_out.write_text(ydk_text(zones, name), encoding="utf-8", newline="\n")
    meta = {"name": name, "format": spec.title, "format_key": format, "saved_at": now.isoformat(),
            "ydk": str(ydk_path_out), "ydke": ydke(zones), "summary": check["summary"], "text": "\n".join(text),
            "breakdown": breakdown, "notes": notes, "data": check["data"]}
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    out = {"saved": True, **meta}
    if replaced:
        out["previous_version"] = str(replaced)
    return out


def saved_decks(con: sqlite3.Connection | None = None, format: str | None = None) -> dict:
    """Decks saved by finalize_deck, newest first (con unused; keeps the MCP call shape)."""
    out = []
    for p in sorted(DECKS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            m = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if format and m.get("format_key") != format:
            continue
        out.append({k: m.get(k) for k in ("name", "format", "saved_at", "summary", "ydk", "ydke")})
    return {"decks": out, "folder": str(DECKS_DIR)}
