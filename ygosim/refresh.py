"""Pull every source, detect what changed, rebuild the field only when needed.

Triggers: first run, TCG banlist change, a set reaching its TCG release date, new tournament
lists, or a change in data/inbox/. Each rebuild writes data/snapshots/<date>/ and prepends
an entry to data/CHANGELOG.md comparing against the previous snapshot.
"""
import hashlib
import json
from datetime import date

from .api import CARDSETS_URL, DATA_DIR, cached, get_json
from .banlist import tcg_banlist
from .cards import card_db, name
from .field import build_field, export_field
from .meta import build_meta
from .project import project_meta
from .sources import INBOX, _names, inbox_decks, pull_all

STATE = DATA_DIR / "state.json"
SNAPSHOTS = DATA_DIR / "snapshots"
CHANGELOG = DATA_DIR / "CHANGELOG.md"
WEIGHT_CHANGE = 0.01  # report field weight moves of at least 1 point


def _load_state() -> dict:
    return json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}


def _clear_caches(cards: bool) -> None:
    if cards:
        (DATA_DIR / "cards.json").unlink(missing_ok=True)
        (DATA_DIR / "cardsets.json").unlink(missing_ok=True)
        card_db.cache_clear()
        _names.cache_clear()
    (DATA_DIR / "ignis_tcg_lflist.json").unlink(missing_ok=True)
    tcg_banlist.cache_clear()


def _inbox_fingerprint() -> str:
    files = sorted((p.name, p.stat().st_mtime_ns) for p in INBOX.glob("*.ydk"))
    return hashlib.sha256(json.dumps(files).encode()).hexdigest()


def _previous_snapshot(today: date) -> dict | None:
    dirs = sorted(p for p in SNAPSHOTS.glob("*") if p.is_dir() and p.name < today.isoformat())
    if not dirs:
        return None
    return json.loads((dirs[-1] / "field" / "field.json").read_text(encoding="utf-8"))


def _diff_fields(old: dict | None, new: dict) -> list[str]:
    if old is None:
        return ["First snapshot."]
    lines = []
    before = {e["deck"]: e for e in old["entries"]}
    after = {e["deck"]: e for e in new["entries"]}
    for d in after.keys() - before.keys():
        lines.append(f"New in field: {d} ({after[d]['weight']:.1%}, {after[d]['source']})")
    for d in before.keys() - after.keys():
        lines.append(f"Left field: {d} (was {before[d]['weight']:.1%})")
    for d in after.keys() & before.keys():
        delta = after[d]["weight"] - before[d]["weight"]
        if abs(delta) >= WEIGHT_CHANGE:
            lines.append(f"{d}: {before[d]['weight']:.1%} -> {after[d]['weight']:.1%}")
        added = after[d]["lists"].keys() - before[d]["lists"].keys()
        removed = before[d]["lists"].keys() - after[d]["lists"].keys()
        if added:
            lines.append(f"{d}: new candidate lists {sorted(added)}")
        if removed:
            lines.append(f"{d}: dropped candidate lists {sorted(removed)}")
    for n in set(new["notes"]) - set(old["notes"]):
        if "rejected" in n:
            lines.append(f"Projection: {n}")
    return lines or ["No field changes."]


def refresh(days: int, ocg_days: int, min_share: float, new_share: float,
            as_of: date | None = None, force: bool = False, min_ocg_share: float = 0.04) -> dict:
    today = date.today()
    as_of = as_of or today
    state = _load_state()
    last_run = date.fromisoformat(state["last_run"]) if "last_run" in state else None
    triggers = [] if state else ["first run"]

    # Set releases since the last run invalidate the card database (new cards become legal).
    sets = get_json(CARDSETS_URL)
    released = sorted({s["set_name"] for s in sets if s.get("tcg_date")
                       and (last_run is None or last_run.isoformat() < s["tcg_date"])
                       and s["tcg_date"] <= today.isoformat()})
    if last_run and released:
        triggers.append(f"set released: {', '.join(released)}")
    _clear_caches(cards=bool(released) or last_run is None or (today - last_run).days >= 7)

    # Banlist: always fetched fresh.
    bl = tcg_banlist()
    bl_hash = hashlib.sha256(json.dumps(sorted(bl.limits.items())).encode()).hexdigest()
    banlist_changes = []
    if state.get("banlist_hash") and state["banlist_hash"] != bl_hash:
        old_limits = {int(k): v for k, v in state.get("banlist_limits", {}).items()}
        for cid in old_limits.keys() | bl.limits.keys():
            a, b = old_limits.get(cid, 3), bl.limits.get(cid, 3)
            if a != b:
                banlist_changes.append(f"{name(cid)}: {a} -> {b}")
        triggers.append(f"banlist changed: {state.get('banlist_title')} -> {bl.title}")

    pulled = pull_all(max(days, ocg_days), max_age_hours=0, today=today)
    if pulled["new"] and state:
        triggers.append(f"new lists: {pulled['new']}")

    inbox = _inbox_fingerprint()
    if state.get("inbox") not in (None, inbox):
        triggers.append("inbox changed")
    if force and not triggers:
        triggers.append("forced")

    report = {"triggers": triggers, "pulled": pulled, "banlist": bl.title,
              "banlist_conflicts": list(bl.conflicts), "banlist_changes": banlist_changes}
    if triggers:
        tcg, _ = build_meta(days, 1)
        projections = project_meta(ocg_days, 2, as_of, tcg)
        f = build_field(tcg, projections, inbox_decks(), min_share, new_share, as_of, today, min_ocg_share)
        export_field(f, as_of)
        snap = export_field(f, as_of, SNAPSHOTS / today.isoformat() / "field")
        report["field"] = snap
        report["changes"] = _diff_fields(_previous_snapshot(today), snap)
        _write_changelog(today, report)

    STATE.write_text(json.dumps({
        "last_run": today.isoformat(), "banlist_title": bl.title, "banlist_hash": bl_hash,
        "banlist_limits": {str(k): v for k, v in bl.limits.items()}, "inbox": inbox,
    }), encoding="utf-8")
    return report


def _write_changelog(today: date, r: dict) -> None:
    lines = [f"## {today.isoformat()}", "", f"Triggers: {'; '.join(r['triggers'])}", "",
             f"Banlist: {r['banlist']}"]
    lines += [f"- banlist change: {c}" for c in r["banlist_changes"]]
    lines += [f"- sources disagree, stricter applied: {c}" for c in r["banlist_conflicts"]]
    if r["pulled"]["unknown_names"]:
        lines.append(f"- lists skipped for unmatched card names: {r['pulled']['unknown_names']}")
    lines += ["", *[f"- {c}" for c in r["changes"]], "", ""]
    old = CHANGELOG.read_text(encoding="utf-8") if CHANGELOG.exists() else ""
    CHANGELOG.write_text("\n".join(lines) + old, encoding="utf-8")
