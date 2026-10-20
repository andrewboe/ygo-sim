"""search_cards / card_lookup / archetype / meta tools against the pinned fixture."""
import json
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from ygosim import carddata, formatmeta
from ygosim.cardtools import archetype, card_lookup, search_cards
from ygosim.formats import DeckInputError

FIX = Path(__file__).parent / "fixtures"
MALICIOUS, DARK_ANGEL, DARK_CITY, DESTINY_DRAW, STRATOS = 9411399, 26964762, 53527835, 45809008, 40044918
CAMBRORASTER, HERALD_ARC, ILLUSION_GATE, CUPSY = 36346532, 79606837, 33017964, 31425736


@pytest.fixture(scope="module")
def con():
    con = carddata.connect(":memory:")
    dump = json.loads((FIX / "genesys_subset.json").read_text(encoding="utf-8"))
    carddata.build(con, dump, (FIX / "tcg_lflist.conf").read_text(encoding="utf-8"), {},
                   {"database_version": "fixture", "last_update": "2026-10-20"}, datetime(2026, 10, 20, tzinfo=timezone.utc))
    con.executescript(formatmeta.SCHEMA)
    return con


def names(res):
    return {c["name"] for c in res["cards"]}


def test_archetype_members_by_name_and_tagged_support(con):
    a = archetype(con, "Destiny HERO", "genesys")
    ids = {c["passcode"] for c in a["cards"]}
    assert {MALICIOUS, DARK_ANGEL} <= ids and DARK_CITY not in ids  # Dark City is tagged, not named
    support = {c["passcode"] for c in a["support"]}
    assert {DARK_CITY, DESTINY_DRAW} <= support
    angel = next(c for c in a["cards"] if c["passcode"] == DARK_ANGEL)
    assert angel["genesys"]["points"] == 100


def test_archetype_is_case_sensitive_and_suggests(con):
    assert archetype(con, "destiny hero", "genesys")["members"] == []


def test_search_mentions_finds_bridges(con):
    # Stratos searches "HERO" monsters: an Elemental HERO card that reaches Destiny HEROes.
    res = search_cards(con, "genesys", mentions="HERO", kind="monster")
    assert "Elemental HERO Stratos" in names(res)


def test_search_text_and_points_filter(con):
    res = search_cards(con, "genesys", text="Destiny HERO", max_points=0, full_text=True)
    assert all(c["genesys"]["points"] == 0 for c in res["cards"])
    assert "Destiny HERO - Dark Angel" not in names(res)  # 100 points


def test_search_hides_illegal_unless_asked(con):
    res = search_cards(con, "genesys", kind="link")
    assert CAMBRORASTER not in {c["passcode"] for c in res["cards"]} and res["hidden_illegal"] >= 1
    res = search_cards(con, "genesys", kind="link", include_illegal=True)
    assert CAMBRORASTER in {c["passcode"] for c in res["cards"]}
    adv = search_cards(con, "tcg_advanced", name="Herald of the Arc Light")
    assert adv["matches"] == 0  # Forbidden in Advanced


def test_search_pattern_and_bad_query(con):
    res = search_cards(con, "tcg_advanced", pattern=r"draw 2 cards")
    assert "Destiny Draw" in names(res)
    with pytest.raises(DeckInputError):
        search_cards(con, "tcg_advanced", text='"unbalanced')


def test_card_lookup_both_formats(con):
    r = card_lookup(con, "Herald of the Arc Light")["card"]
    assert r["formats"]["tcg_advanced"]["legal"] is False and r["formats"]["tcg_advanced"]["status"] == "Forbidden"
    assert r["formats"]["genesys"] == {"limit": 3, "points": 50, "legal": True}
    assert any("db.yugioh-card.com" in u for u in r["rulings_links"])
    c = card_lookup(con, "Paleozoic Cambroraster")["card"]["formats"]["genesys"]
    assert c["legal"] is False and "Link Monster" in c["why_not"]


def test_card_lookup_never_guesses(con):
    r = card_lookup(con, "D.D. Ground")
    assert r["match"] == "none"
    assert card_lookup(con, "Cupsy Yummy")["card"]["passcode"] == CUPSY


def _raw(i, fmt, deck_type, main, placement=1, extra=(), days_ago=5):
    day = (date.today() - timedelta(days=days_ago)).isoformat()
    return {"_id": str(i), "created": day + "T00:00:00.000Z", "genesys": fmt == "genesys", "ocg": False,
            "deckType": {"name": deck_type}, "tournamentPlacement": placement,
            "tournamentType": {"shortName": "Genesys" if fmt == "genesys" else "WCQ Regional"},
            "event": {"name": f"Event {i}"},
            "main": [{"card": {"name": n}, "amount": a} for n, a in main],
            "extra": [{"card": {"name": n}, "amount": a} for n, a in extra], "side": []}


def test_meta_snapshot_and_inclusion(con):
    raw = [
        _raw(1, "genesys", "D-HERO", [("Destiny HERO - Malicious", 3), ("Illusion Gate", 3)]),  # 30 pts
        _raw(2, "genesys", "D-HERO", [("Destiny HERO - Malicious", 2), ("Destiny HERO - Dark Angel", 1)]),  # 100
        _raw(3, "genesys", "Other", [("Illusion Gate", 3), ("Destiny HERO - Dark Angel", 1)], placement=8),  # 130
        _raw(4, "tcg_advanced", "Herald", [("Herald of the Arc Light", 1)]),  # Forbidden now
        _raw(5, "genesys", "D-HERO", [("Card That Does Not Exist", 3)]),
        _raw(6, "genesys", "D-HERO", [("Destiny HERO - Malicious", 3)], days_ago=200),  # outside the window
    ]
    formatmeta.load(con, raw, time.time(), "2026-01-01")
    s = formatmeta.meta_snapshot(con, "genesys", days=60)
    assert s["lists"] == 4 and s["unmatched_lists"] == 1
    dhero = next(d for d in s["deck_types"] if d["deck_type"] == "D-HERO")
    assert dhero["lists"] == 3 and dhero["legal_now"] == 2
    assert next(d for d in s["deck_types"] if d["deck_type"] == "Other")["legal_now"] == 0  # 130 > 100
    assert formatmeta.meta_snapshot(con, "tcg_advanced")["legal_now"] == 0

    inc = formatmeta.meta_inclusion(con, "genesys", card="Destiny HERO - Malicious")
    assert (inc["playing"], inc["avg_copies"]) == (2, 2.5)
    table = formatmeta.meta_inclusion(con, "genesys", deck_type="d-hero")["cards"]
    assert any(r.get("unmatched_name") for r in table)
    assert formatmeta.meta_inclusion(con, "genesys", deck_type="HERO")["similar_deck_types"] == ["D-HERO"]
