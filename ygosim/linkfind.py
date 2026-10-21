"""find_links: cards that connect to a deck, from the link graph in links.py.

Sections: members of your archetypes the list doesn't run yet, outside cards that reach your cards
(searchers, summoners), what your cards already reach
outside the list (grouped by archetype), bridges into other engines, and Extra Deck monsters your
monsters can be material for. Everything respects the format (legal cards only) and, for Genesys,
the points left. Locks in your deck flag suggestions that would break them.
"""
import json
import sqlite3
from collections import Counter, defaultdict
from datetime import date

from .formats import FORMATS, DeckInputError, card_status, parse_input, resolve
from .links import facts_of, matches, specificity

HUB_ARCHETYPES = 8  # an effect reaching more archetypes than this is generic, not a bridge


class Pool:
    """Everything find_links needs, loaded once per index build, format and day."""

    def __init__(self, con: sqlite3.Connection, spec, day: date):
        mentions = defaultdict(set)
        for cid, m in con.execute("SELECT canonical_id, mention FROM mentions"):
            mentions[cid].add(m)
        rows = con.execute("SELECT * FROM cards WHERE passcode = canonical_id "
                           "AND type NOT IN ('Token','Skill Card')").fetchall()
        self.facts = {r["canonical_id"]: facts_of(r, frozenset(mentions[r["canonical_id"]])) for r in rows}
        self.tag = {r["canonical_id"]: r["archetype"] for r in rows}
        self.status = {r["canonical_id"]: card_status(con, spec, r, day) for r in rows}
        self.effects = defaultdict(list)
        for r in con.execute("SELECT * FROM effects"):
            self.effects[r["canonical_id"]].append({
                "verb": r["verb"], "zones": r["zones"], "filter": json.loads(r["filter"]),
                "evidence": r["evidence"], "cost": bool(r["cost"]), "flags": json.loads(r["flags"])})
        self.materials = {r["canonical_id"]: (json.loads(r["components"]), r["line"])
                          for r in con.execute("SELECT * FROM materials")}
        self.locks = defaultdict(list)
        for r in con.execute("SELECT * FROM locks"):
            self.locks[r["canonical_id"]].append({"scope": r["scope"], "filter": json.loads(r["filter"]),
                                                  "evidence": r["evidence"]})
        self._targets: dict[str, list[int]] = {}

    def targets(self, f: dict) -> list[int]:
        key = json.dumps(f, sort_keys=True)
        if key not in self._targets:
            self._targets[key] = [cid for cid, c in self.facts.items() if matches(c, f)]
        return self._targets[key]


_POOLS: dict[tuple, Pool] = {}


def _pool(con: sqlite3.Connection, spec, day: date) -> Pool:
    fetch = con.execute("SELECT max(fetch_id) FROM fetches").fetchone()[0]
    path = con.execute("PRAGMA database_list").fetchone()[2] or f"memory:{id(con)}"
    key = (path, fetch, spec.key, day)
    if key not in _POOLS:
        _POOLS.clear()  # keep one pool in memory
        _POOLS[key] = Pool(con, spec, day)
    return _POOLS[key]


def _strong(f: dict) -> bool:
    """Names, archetypes or quoted mentions: a deliberate link, not just a shared Attribute or Type."""
    return bool(f.get("names") or f.get("archetypes") or f.get("mentions"))


def _brief(pool: Pool, cid: int, spec) -> dict:
    c, st = pool.facts[cid], pool.status[cid]
    out = {"name": c.name, "passcode": cid, "type": c.type}
    if spec.points:
        out["points"] = st.get("points", 0)
    if spec.limits and st["limit"] < 3:
        out["limit"] = st["limit"]
    if pool.tag.get(cid):
        out["archetype"] = pool.tag[cid]
    return out


def _evidence(e: dict) -> dict:
    out = {"how": f"{e['verb']} from {e['zones']}", "evidence": e["evidence"][:220]}
    flags = list(e["flags"])
    if e["cost"]:
        flags.append("this is a cost, not an effect (matters for 'by card effect' rulings)")
    if flags:
        out["ruling_flags"] = flags
    return out


def _deck_counts(con, cards, ydk_path, ydk_text, decklist) -> tuple[Counter, list[str]]:
    counts: Counter = Counter()
    errors: list[str] = []
    if cards is not None:
        pids = []
        for q in cards:
            pid, note = resolve(con, q)
            if pid is None:
                errors.append(note)
            else:
                pids.append(pid)
    else:
        deck = parse_input(con, ydk_path, ydk_text, decklist)
        errors += deck.errors
        pids = [p for z in deck.zones.values() for p in z]
    for p in pids:
        row = con.execute("SELECT canonical_id FROM cards WHERE passcode = ?", (p,)).fetchone()
        if row is None:
            errors.append(f"unknown passcode {p}")
        else:
            counts[row[0]] += 1
    return counts, errors


def find_links(con: sqlite3.Connection, format: str, ydk_path: str | None = None, ydk_text: str | None = None,
               decklist: dict | None = None, cards: list[str] | None = None, archetypes: list[str] | None = None,
               max_points: int | None = None, point_cap: int | None = None, limit: int = 12,
               as_of: str | None = None) -> dict:
    spec = FORMATS.get(format)
    if spec is None:
        raise DeckInputError(f"unknown format {format!r}; known: {', '.join(FORMATS)}")
    if cards is None and ydk_path is None and ydk_text is None and decklist is None:
        raise DeckInputError("pass a deck (ydk_path, ydk_text, decklist) or a list of cards")
    day = date.fromisoformat(as_of) if as_of else date.today()
    counts, errors = _deck_counts(con, cards, ydk_path, ydk_text, decklist)
    if errors:
        return {"error": "input problems; nothing was guessed", "parse_errors": errors}
    pool = _pool(con, spec, day)
    in_deck = set(counts)

    used = sum(pool.status[c].get("points", 0) * n for c, n in counts.items() if c in pool.status)
    budget = max_points
    if spec.points and budget is None and cards is None:
        budget = (point_cap if point_cap is not None else spec.default_cap) - used
    if not archetypes:
        tags = Counter(pool.tag[c] for c in in_deck if pool.tag.get(c))
        archetypes = [t for t, n in tags.most_common() if n >= 2] or [t for t, _ in tags.most_common(1)]
    deck_tags = set(archetypes)
    deck_locks = [(pool.facts[c].name, lk) for c in in_deck for lk in pool.locks.get(c, [])
                  if specificity(lk["filter"])]

    def ok(cid: int) -> bool:
        st = pool.status.get(cid)
        return bool(st and st["legal"] and cid not in in_deck and (budget is None or st.get("points", 0) <= budget))

    def item(cid: int, extra: dict) -> dict:
        out = {**_brief(pool, cid, spec), **extra}
        c = pool.facts[cid]
        if c.is_monster:
            is_extra = bool({"fusion", "synchro", "xyz", "link"} & c.kinds)
            broken = [f"{src}: {lk['evidence'][:160]}" for src, lk in deck_locks
                      if (lk["scope"] == "all" or is_extra) and not matches(c, lk["filter"])]
            if broken:
                out["breaks_deck_locks"] = broken
        own = [lk for lk in pool.locks.get(cid, []) if specificity(lk["filter"])]
        if own:
            blocked = sum(1 for d in in_deck if pool.facts[d].is_monster and not matches(pool.facts[d], own[0]["filter"]))
            out["its_lock"] = {"text": own[0]["evidence"][:200], "your_monsters_it_blocks": blocked}
        return out

    # A. outside cards whose effects reach your cards
    into = []
    for cid, effs in pool.effects.items():
        if not ok(cid):
            continue
        hits, best, best_score = set(), None, 0
        for e in effs:
            if not specificity(e["filter"]) or e["filter"].get("names") == [pool.facts[cid].name]:
                continue
            m = {d for d in in_deck if matches(pool.facts[d], e["filter"])}
            if m:
                hits |= m
                # Searching/summoning by name or archetype beats sharing an Attribute; add/summon beats send/banish.
                s = len(m) * (3 if _strong(e["filter"]) else 1) * (2 if e["verb"] in ("add", "summon") else 1)
                if s > best_score:
                    best, best_score = e, s
        if hits:
            into.append((best_score, cid, hits, best))
    into.sort(key=lambda t: (-t[0], pool.status[t[1]].get("points", 0)))
    into_deck = [item(cid, {"reaches_your": sorted(pool.facts[h].name for h in hits)[:6], **_evidence(e)})
                 for _, cid, hits, e in into[:limit]]

    # B. what your cards already reach outside the list, grouped by archetype tag
    groups: dict[str, dict] = {}
    for d in in_deck:
        for e in pool.effects.get(d, []):
            if not specificity(e["filter"]):
                continue
            for t in pool.targets(e["filter"]):
                if ok(t):
                    g = groups.setdefault(pool.tag.get(t) or "(no archetype)",
                                          {"cards": set(), "strong": set(), "via": {}})
                    g["cards"].add(t)
                    if _strong(e["filter"]):
                        g["strong"].add(t)
                    g["via"].setdefault(pool.facts[d].name, _evidence(e))
    # Your own archetypes first: support you could run but don't is the most useful find.
    deck_reaches = [
        {"archetype": tag, "count": len(g["cards"]),
         "examples": [_brief(pool, c, spec) for c in
                      sorted(g["cards"], key=lambda c: (c not in g["strong"], pool.status[c].get("points", 0),
                                                        pool.facts[c].name))[:5]],
         "via": [{"card": k, **v} for k, v in list(g["via"].items())[:3]]}
        for tag, g in sorted(groups.items(), key=lambda kv: (kv[0] not in deck_tags, -len(kv[1]["strong"]),
                                                            -len(kv[1]["cards"])))][:limit]

    # B2. members of your archetypes (by tag, name or "always treated as") that the list doesn't run,
    # ranked by how tightly they connect: your cards that fetch them, and your cards they fetch.
    def strong_hits(src: int, dst: int) -> dict | None:
        """src's first add/summon/Set effect (not a cost) that fetches dst by name, archetype or mention."""
        c = pool.facts[dst]
        main_only = not ({"fusion", "synchro", "xyz", "link"} & c.kinds) or None
        for e in pool.effects.get(src, []):
            if e["cost"] or e["verb"] not in ("add", "summon", "set") or not _strong(e["filter"]) \
                    or e["filter"].get("names") == [pool.facts[src].name]:
                continue
            if not main_only and set(e["zones"].split(",")) <= {"hand", "Deck"}:
                continue  # an Extra Deck monster is never in your hand or Deck
            if matches(c, e["filter"]):
                return e
        return None

    unplayed = []
    for cid, c in pool.facts.items():
        if not ok(cid) or not (pool.tag.get(cid) in deck_tags or any(t in c.name or t in c.treated for t in deck_tags)):
            continue
        reached_by = [(d, e) for d in in_deck if (e := strong_hits(d, cid))]
        reaches = [d for d in in_deck if strong_hits(cid, d)]
        if reached_by or reaches:
            unplayed.append([cid, reached_by, reaches])
    # Links between unplayed members count too (Genni, the Maid -> Verre, the Maid): add them as a pair.
    cands = [u[0] for u in unplayed]
    for u in unplayed:
        u.append([o for o in cands if o != u[0] and strong_hits(u[0], o)])
    # A two-way link (your cards fetch it and it fetches yours) is the strongest sign it belongs; a link
    # through another unplayed card counts for less, or broad searchers win on partners alone.
    def score(u) -> int:
        _, by, reaches, partners = u
        return (2 * len(by) + 2 * len(reaches) + min(len(partners), 2)
                + (3 if by and reaches else 2 if by and partners else 0))
    unplayed.sort(key=lambda u: (-score(u), pool.status[u[0]].get("points", 0), pool.facts[u[0]].name))
    own_unplayed = [item(cid, {
        "reached_by": [{"card": pool.facts[d].name, **_evidence(e)} for d, e in reached_by[:3]],
        "reaches_your": sorted(pool.facts[d].name for d in reaches)[:6],
        **({"reaches_unplayed": sorted(pool.facts[o].name for o in partners)[:4]} if partners else {})})
        for cid, reached_by, reaches, partners in unplayed[:limit]]

    # C. bridges: a card tied to your deck that belongs to, or reaches, another archetype
    bridges: dict[str, dict] = {}
    linked = [(cid, "reaches your cards") for _, cid, _, e in into[:60] if _strong(e["filter"])]
    linked += [(c, "your cards reach it") for g in groups.values() for c in sorted(g["strong"])[:20]]
    for cid, why in linked:
        engines = set()
        if (own := pool.tag.get(cid)) and own not in deck_tags:
            engines.add(own)
        for e in pool.effects.get(cid, []):
            if not _strong(e["filter"]):  # "add 1 DARK monster" reaches every DARK archetype: not a bridge
                continue
            reached = {pool.tag[t] for t in pool.targets(e["filter"])
                       if pool.tag.get(t) and pool.tag[t] not in deck_tags and ok(t)}
            if len(reached) <= HUB_ARCHETYPES:  # e.g. anything named "...Fusion" spans dozens: a hub, not a bridge
                engines |= reached
        for b in engines:
            bridges.setdefault(b, {"engine": b, "via": {}})["via"].setdefault(pool.facts[cid].name, why)
    legal_by_tag = Counter(t for c, t in pool.tag.items() if t and ok(c))
    bridge_list = sorted(({"engine": b["engine"], "engine_cards_in_budget": legal_by_tag[b["engine"]],
                           "via": [{"card": k, "link": v} for k, v in list(b["via"].items())[:4]],
                           "connections": len(b["via"])} for b in bridges.values()),
                         key=lambda b: -b["connections"])[:limit]

    # D. Extra Deck monsters your monsters can be material for
    deck_mons = [(d, counts[d]) for d in in_deck if pool.facts[d].is_monster]
    extra = []
    for cid, (comps, line) in pool.materials.items():
        if not ok(cid):
            continue
        score = 0
        for comp in comps:
            matched = [(d, n) for d, n in deck_mons if matches(pool.facts[d], comp["filter"])]
            if sum(n for _, n in matched) < comp["count"]:
                break
            score += specificity(comp["filter"])
            if set(comp["filter"].get("archetypes", [])) & deck_tags or \
                    any(pool.tag.get(d) in deck_tags for d, _ in matched if comp["filter"].get("names")):
                score += 3
        else:
            if score:
                extra.append((score, cid, line))
    extra.sort(key=lambda t: (-t[0], pool.status[t[1]].get("points", 0)))
    extra_deck = [item(cid, {"materials": line}) for _, cid, line in extra[:limit]]

    out = {
        "format": spec.title, "deck_cards": len(in_deck), "deck_archetypes": sorted(deck_tags),
        "your_archetypes_unplayed": own_unplayed,
        "into_your_deck": into_deck, "your_deck_reaches": deck_reaches, "bridges": bridge_list,
        "extra_deck_options": extra_deck,
        "deck_locks": [{"card": src, "lock": lk["evidence"][:200]} for src, lk in deck_locks],
        "notes": ["Links come from rule-based parsing of card text (add / Special Summon / send / banish / Set, "
                  "materials, Special Summon locks). Fusion Summon spells and unusual wordings are not "
                  "modelled, and nothing here is a verified ruling: check ruling_flags and rulings links.",
                  "Extra Deck options are checked by material type only, not by whether the summon is achievable."],
    }
    if spec.points:
        out["points"] = {"deck_uses": used, "max_points_per_suggestion": budget}
    return out
