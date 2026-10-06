"""Project OCG tournament lists into TCG-legal lists for a given date.

For each OCG archetype's representative list:
  1. drop cards not TCG-released by `as_of`
  2. cut copies down to the TCG banlist (side first, then extra, then main)
  3. refill emptied slots, in order of trust:
       other OCG lists of the same archetype -> the closest TCG archetype -> cross-archetype TCG staples
  4. run the full legality check; an illegal result is never written

Every card in the output carries the source it came from.
"""
import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import date

from .api import DATA_DIR
from .banlist import tcg_banlist
from .cards import card_db, name
from .deck import Deck
from .meta import Archetype, build_meta, card_set, jaccard, slugify

ZONE_SIZE = {"main": 40, "extra": 15, "side": 15}
MIN_PLAY_RATE = 0.25      # ignore one-off tech when refilling
MIN_TCG_MATCH = 0.40      # staple-free Jaccard overlap to count as the same deck (matches score >=0.5, non-matches <=0.17)
STAPLE_SHARE = 0.15       # cards in this share of all TCG lists are ignored when matching
LOW_CONFIDENCE = 0.15     # share of main deck lost to release dates or banlist cuts


@dataclass
class Projection:
    archetype: str
    ocg_lists: int
    deck: Deck
    tcg_match: str | None
    original_main: int
    ocg_share: float = 0.0  # recency-weighted share of OCG topping lists
    rows: list[dict] = field(default_factory=list)      # provenance of every copy
    removed: list[dict] = field(default_factory=list)   # what was cut and why
    error: str | None = None

    @property
    def main_lost(self) -> float:
        """Share of the OCG main deck that had to go, to release dates or the TCG banlist.
        A deck gutted by the banlist (e.g. Kewl Tune without Rotary) shouldn't read as healthy."""
        lost = sum(r["copies"] for r in self.removed if r["zone"] == "main")
        return lost / max(1, self.original_main)

    @property
    def confidence(self) -> str:
        return "low" if self.error or self.main_lost > LOW_CONFIDENCE else "ok"


def _core_forbidden(ocg: Archetype) -> list[str]:
    """The archetype's own cards, run in most OCG lists, that the TCG forbids. Copy count is
    ignored: the OCG may already limit the card (OCG Kewl Tune runs 1 Rotary).
    Losing one usually means the deck doesn't exist in the TCG, whatever we refill with."""
    db, banlist, arch = card_db(), tcg_banlist(), ocg.name.lower()
    out = []
    for row in ocg.inclusion():
        card = db.get(row["id"])
        if row["zone"] in ("main", "extra") and row["play_rate"] >= 0.75 \
                and card and card.archetype and card.archetype.lower() in arch \
                and banlist.limit(card.id) == 0:
            out.append(card.name)
    return out


def generic_cards(tcg: list[Archetype]) -> frozenset[int]:
    """Cards in at least STAPLE_SHARE of all TCG lists (hand traps, generic extra deck).
    They say nothing about which deck a list is, so matching ignores them."""
    lists = [d for a in tcg for d in a.lists]
    freq = Counter(c for d in lists for c in card_set(d))
    return frozenset(c for c, n in freq.items() if n / max(1, len(lists)) >= STAPLE_SHARE)


def closest_tcg(deck: Deck, tcg: list[Archetype], generic: frozenset[int],
                min_score: float = MIN_TCG_MATCH) -> Archetype | None:
    """The TCG deck containing the single list closest to `deck`, staples excluded. Matching
    against every list, not just the representative, keeps a merged deck's minority builds matchable."""
    best, best_score = None, min_score
    cards = card_set(deck) - generic
    for arch in tcg:
        score = max(jaccard(cards, card_set(d) - generic) for d in arch.lists)
        if score >= best_score:
            best, best_score = arch, score
    return best


def _staples(tcg: list[Archetype]) -> list[dict]:
    """Cards most TCG archetypes play: hand traps, board breakers, generic extra deck."""
    counts, copies = Counter(), Counter()
    for arch in tcg:
        for row in arch.inclusion():
            if row["play_rate"] >= 0.5:
                counts[(row["zone"], row["id"])] += 1
                copies[(row["zone"], row["id"])] += row["avg_copies"]
    need = max(2, len(tcg) // 4)
    return [{"zone": z, "id": cid, "play_rate": n / len(tcg), "avg_copies": copies[(z, cid)] / n}
            for (z, cid), n in counts.most_common() if n >= need]


def project_one(ocg: Archetype, tcg: list[Archetype], staples: list[dict], as_of: date,
                generic: frozenset[int] = frozenset()) -> Projection:
    db, banlist = card_db(), tcg_banlist()
    rep = ocg.representative
    match = closest_tcg(rep, tcg, generic)
    proj = Projection(ocg.name, len(ocg.lists), Deck(f"{ocg.name} (TCG projection)"),
                      match.name if match else None, sum(rep.main.values()))
    target = {z: max(ZONE_SIZE[z], sum(c.values())) if z == "main" else sum(c.values())
              for z, c in rep.zones().items()}

    def add(zone: str, cid: int, copies: int, source: str):
        proj.deck.zones()[zone][cid] += copies
        proj.rows.append({"zone": zone, "id": cid, "name": name(cid), "copies": copies, "source": source})

    # 1. Unreleased cards out.
    for zone, cards in rep.zones().items():
        for cid, n in cards.items():
            card = db.get(cid)
            if card is None or not card.released_by(as_of):
                proj.removed.append({"zone": zone, "id": cid, "name": name(cid), "copies": n,
                                     "reason": "not released"})
            else:
                add(zone, cid, n, "ocg list")

    # 2. Banlist cuts, taken from the side deck first so the main deck stays intact.
    totals = proj.deck.total()
    for cid, n in totals.items():
        excess = n - banlist.limit(cid)
        for zone in ("side", "extra", "main"):
            if excess <= 0:
                break
            cards = proj.deck.zones()[zone]
            cut = min(excess, cards[cid])
            if cut:
                cards[cid] -= cut
                excess -= cut
                proj.removed.append({"zone": zone, "id": cid, "name": name(cid), "copies": cut,
                                     "reason": f"TCG limit {banlist.limit(cid)}"})
    for cards in proj.deck.zones().values():
        cards += Counter()  # drop zero counts
    proj.rows = [r for r in proj.rows if proj.deck.zones()[r["zone"]][r["id"]] > 0]
    for r in proj.rows:
        r["copies"] = proj.deck.zones()[r["zone"]][r["id"]]

    # 3. Refill emptied slots.
    pools = [("ocg archetype", ocg.inclusion())]
    if match:
        pools.append((f"tcg {match.name}", match.inclusion()))
    pools.append(("tcg staple", staples))
    for zone in ("main", "extra", "side"):
        cards = proj.deck.zones()[zone]
        for source, rows in pools:
            for row in rows:
                need = target[zone] - sum(cards.values())
                if need <= 0:
                    break
                cid = row["id"]
                card = db.get(cid)
                if row["zone"] != zone or row["play_rate"] < MIN_PLAY_RATE or card is None:
                    continue
                if not card.released_by(as_of) or (zone == "main" and card.is_extra) \
                        or (zone == "extra" and not card.is_extra):
                    continue
                room = min(banlist.limit(cid), 3) - proj.deck.total()[cid]
                copies = min(round(row["avg_copies"]) or 1, room, need)
                if copies > 0:
                    add(zone, cid, copies, source)

    # 4. Final gate.
    if errors := proj.deck.legality_errors(as_of):
        proj.error = "; ".join(errors)
    elif core := _core_forbidden(ocg):
        proj.error = "core card forbidden in TCG: " + ", ".join(core)
    return proj


def project_meta(max_days: int, min_lists: int, as_of: date,
                 tcg: list[Archetype]) -> list[Projection]:
    ocg, _ = build_meta(max_days, 1, ocg=True)
    today = date.today()
    total = sum(a.weight(today) for a in ocg) or 1
    staples, generic = _staples(tcg), generic_cards(tcg)
    out = []
    for a in ocg:
        if len(a.lists) >= min_lists:
            p = project_one(a, tcg, staples, as_of, generic)
            p.ocg_share = a.weight(today) / total
            out.append(p)
    return out


def export_projections(projections: list[Projection], as_of: date) -> None:
    out = DATA_DIR / "projected"
    out.mkdir(parents=True, exist_ok=True)
    summary = []
    for p in projections:
        slug = slugify(p.archetype)
        if p.error is None:
            p.deck.to_ydk(out / f"{slug}.ydk", as_of)  # re-checks legality before writing
        report = {"archetype": p.archetype, "as_of": as_of.isoformat(),
                  "banlist": tcg_banlist().title, "ocg_lists": p.ocg_lists,
                  "tcg_match": p.tcg_match, "confidence": p.confidence,
                  "main_lost_to_unreleased": round(p.main_lost, 3), "error": p.error,
                  "removed": p.removed, "cards": p.rows}
        (out / f"{slug}.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
        summary.append({k: report[k] for k in ("archetype", "ocg_lists", "tcg_match", "confidence",
                                               "main_lost_to_unreleased", "error")})
    (out / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
