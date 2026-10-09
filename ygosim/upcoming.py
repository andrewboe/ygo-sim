"""Upcoming TCG cards for any new set (ygosim upcoming), from data we already pull.

YGOProDeck's cardinfo (misc=yes) lists unreleased cards with their TCG and OCG dates. TCG core sets are the
OCG set plus 16-20 TCG-only cards, about 13 weeks (9-15) after the OCG release
(docs/research/release_pipeline.md). So for any upcoming set we can know, weeks ahead:
  - announced: cards with a TCG date after today, grouped by date and set;
  - expected: OCG-only cards from the last six months, with a projected TCG date of OCG date + 13 weeks;
  - signal: how often each of those cards already appears in OCG tournament lists (the early read on
    which new cards matter, and which decks to project and simulate).
Known API quirks (release_pipeline.md): some sets have swapped TCG/OCG dates, some cards miss a TCG date,
and prerelease ids can linger after release, so treat dates as estimates.
"""
import json
from collections import Counter, defaultdict
from datetime import date, timedelta

from .api import CARDINFO_URL, CARDSETS_URL, DATA_DIR, cached, get_json

OCG_TO_TCG = timedelta(weeks=13)
OCG_LISTS = ("tournament_meta_decks_ocg_30d.json", "tournament_meta_decks_ocg_60d.json")


def _d(s):
    try:
        return date.fromisoformat(s) if s else None
    except ValueError:
        return None


def _ocg_play_counts() -> Counter:
    """Copies of each card across recent OCG tournament lists (main + extra + side)."""
    counts = Counter()
    for fname in OCG_LISTS:
        path = DATA_DIR / fname
        if not path.exists():
            continue
        for deck in json.loads(path.read_text(encoding="utf-8")):
            for zone in ("main_deck", "extra_deck", "side_deck"):
                raw = deck.get(zone) or []
                ids = json.loads(raw) if isinstance(raw, str) else raw
                for c in ids:
                    try:
                        counts[int(c)] += 1
                    except (TypeError, ValueError):
                        pass
        break  # the 30-day window when present; 60-day only as a fallback
    return counts


def upcoming(today: date | None = None, ocg_window_days: int = 183) -> dict:
    today = today or date.today()
    raw = cached("cards.json", 24, lambda: get_json(CARDINFO_URL, {"misc": "yes"}))
    sets = cached("cardsets.json", 24, lambda: get_json(CARDSETS_URL))
    set_dates = {s["set_name"]: _d(s.get("tcg_date")) for s in sets}
    plays = _ocg_play_counts()
    announced = defaultdict(list)   # TCG date -> cards
    expected = defaultdict(list)    # projected TCG date (by OCG release) -> cards
    for c in raw["data"]:
        misc = (c.get("misc_info") or [{}])[0]
        tcg, ocg = _d(misc.get("tcg_date")), _d(misc.get("ocg_date"))
        card_sets = [s["set_name"] for s in c.get("card_sets") or []]
        if tcg is None and card_sets:
            tcg = min((d for s in card_sets if (d := set_dates.get(s))), default=None)
        ids = [img["id"] for img in c.get("card_images", [])] or [c["id"]]
        row = {"id": c["id"], "name": c["name"], "archetype": c.get("archetype"), "tcg": tcg, "ocg": ocg,
               "sets": sorted({s for s in card_sets if (set_dates.get(s) or date.min) > today}),
               "ocg_play": sum(plays.get(i, 0) for i in ids)}
        if tcg and tcg > today:
            announced[tcg].append(row)
        elif tcg is None and ocg and today - timedelta(days=ocg_window_days) <= ocg:
            expected[ocg + OCG_TO_TCG].append(row)
    return {"today": today, "announced": dict(sorted(announced.items())), "expected": dict(sorted(expected.items())),
            "next_sets": sorted((d, n) for n, d in set_dates.items() if d and d > today)}


def print_report(rep: dict, top: int = 8) -> None:
    print(f"Upcoming TCG cards as of {rep['today']}\n")
    print("Announced TCG sets:")
    for d, n in rep["next_sets"][:8]:
        print(f"  {d}  {n}")
    print("\nAnnounced cards by TCG date:")
    for d, rows in rep["announced"].items():
        archs = Counter(r["archetype"] or "-" for r in rows).most_common(4)
        lead = [(r["tcg"] - r["ocg"]).days // 7 for r in rows if r["ocg"]]
        lead_s = f", OCG lead ~{sorted(lead)[len(lead) // 2]} weeks" if lead else ""
        print(f"  {d}: {len(rows)} cards{lead_s}; archetypes {', '.join(f'{a} {k}' for a, k in archs)}")
        for r in sorted(rows, key=lambda r: -r["ocg_play"])[:top]:
            if r["ocg_play"]:
                print(f"      {r['name']:45} OCG lists: {r['ocg_play']}")
    print("\nOCG-only cards, projected TCG date (OCG + 13 weeks):")
    for d, rows in rep["expected"].items():
        if d < rep["today"]:
            continue  # projected date already passed without a TCG release: not coming soon
        played = sorted((r for r in rows if r["ocg_play"]), key=lambda r: -r["ocg_play"])
        archs = Counter(r["archetype"] or "-" for r in rows).most_common(4)
        print(f"  ~{d} (OCG {rows[0]['ocg']}): {len(rows)} cards; archetypes {', '.join(f'{a} {k}' for a, k in archs)}")
        for r in played[:top]:
            print(f"      {r['name']:45} OCG lists: {r['ocg_play']}")
