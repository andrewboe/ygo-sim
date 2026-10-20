"""validate_deck against a pinned card subset (tests/fixtures), built from the mistakes that
motivated it: Cambroraster is a Link, Herald was banned, Eclipse / D.D. Ground / Illusion Gate
are pointed, Cupsy is limited, a wrong Dreadnought Servant passcode, a .ydk that lost cards."""
import base64
import json
import struct
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from ygosim import carddata
from ygosim.formats import DeckInputError, parse_ydk, validate_deck

FIX = Path(__file__).parent / "fixtures"
FETCHED = datetime(2026, 10, 20, tzinfo=timezone.utc)
CAMBRORASTER, HERALD_ARC, ECLIPSE_WYVERN = 36346532, 79606837, 51858306
DD_GROUND, ILLUSION_GATE, CUPSY, CUPSY_WAY = 31849106, 33017964, 31425736, 31603289
DREADNOUGHT_SERVANT, JUNOLDO, DROLL, DROLL_ALT, COLORED_FISH = 98931282, 10266279, 94145021, 94145022, 23771716
FILLER = [34541863, 64163367, 73262676, 44256816, 86988864, 83994646, 67048711,
          86198326, 14261867, 24140059, 6850209, 49140998, 68170903, 21597117]


def build(dump=None):
    con = carddata.connect(":memory:")
    dump = dump or json.loads((FIX / "genesys_subset.json").read_text(encoding="utf-8"))
    lflist = (FIX / "tcg_lflist.conf").read_text(encoding="utf-8")
    carddata.build(con, dump, lflist, {}, {"database_version": "fixture", "last_update": "2026-10-20"}, FETCHED)
    return con


@pytest.fixture(scope="module")
def con():
    return build()


def ydk(main=(), extra=(), side=(), fill_to=40) -> str:
    main = list(main)
    for cid in FILLER:
        while len(main) < fill_to and main.count(cid) < 3:
            main.append(cid)
    return "\n".join(["#created by test", "#main", *map(str, main), "#extra", *map(str, extra),
                      "!side", *map(str, side)]) + "\n"


def check(con, fmt, text, **kw):
    return validate_deck(con, fmt, ydk_text=text, as_of="2026-10-20", **kw)


def has(result, *words):
    return any(all(w in p for w in words) for p in result.get("problems", []) + result.get("parse_errors", []))


def test_filler_deck_legal_in_both(con):
    for fmt in ("tcg_advanced", "genesys"):
        r = check(con, fmt, ydk())
        assert r["legal"] is True, r["problems"]
        assert r["totals"]["main"]["cards"] == 40


def test_cambroraster_is_a_link(con):
    assert check(con, "tcg_advanced", ydk(extra=[CAMBRORASTER]))["legal"] is True
    r = check(con, "genesys", ydk(extra=[CAMBRORASTER]))
    assert has(r, "Paleozoic Cambroraster", "Link Monster", "not allowed in Genesys")
    assert has(check(con, "genesys", ydk(side=[CAMBRORASTER])), "Link Monster")  # the Side Deck counts too


def test_pendulum_banned_in_genesys(con):
    assert has(check(con, "genesys", ydk([JUNOLDO])), "Pendulum Monster", "not allowed in Genesys")


def test_herald_forbidden_in_advanced_but_pointed_in_genesys(con):
    assert has(check(con, "tcg_advanced", ydk(extra=[HERALD_ARC])), "Herald of the Arc Light", "Forbidden allows 0")
    r = check(con, "genesys", ydk(extra=[HERALD_ARC]))
    assert r["legal"] is True  # Genesys does not use the Forbidden & Limited list
    assert r["totals"]["deck_points"] == 50


def test_eclipse_wyvern_forbidden_in_advanced_and_pointed_in_genesys(con):
    assert has(check(con, "tcg_advanced", ydk([ECLIPSE_WYVERN])), "Eclipse Wyvern", "Forbidden")
    r = check(con, "genesys", ydk([ECLIPSE_WYVERN]))
    assert r["legal"] is True and r["totals"]["deck_points"] == 11


def test_dd_ground_shorthand_is_not_guessed(con):
    r = validate_deck(con, "genesys", decklist={"main": ["D.D. Ground"]})
    assert r["legal"] is None and has(r, "no card named 'D.D. Ground'")
    r = validate_deck(con, "genesys", decklist={"main": ["Different Dimension Ground"]})
    assert r["cards"][0]["passcode"] == DD_GROUND and r["cards"][0]["points"] == 10


def test_illusion_gate_points_per_copy(con):
    r = check(con, "genesys", ydk([ILLUSION_GATE] * 2))
    row = next(c for c in r["cards"] if c["passcode"] == ILLUSION_GATE)
    assert (row["points"], row["points_total"]) == (10, 20)


def test_cupsy_limited_and_distinct_from_cupsy_way(con):
    assert has(check(con, "tcg_advanced", ydk([CUPSY] * 2)), "Cupsy☆Yummy", "2 copies", "Limited allows 1")
    assert check(con, "genesys", ydk([CUPSY] * 2))["legal"] is True
    r = validate_deck(con, "tcg_advanced", decklist={"main": ["Cupsy Yummy"], "extra": ["Cupsy★Yummy Way"]})
    assert {c["passcode"] for c in r["cards"]} == {CUPSY, CUPSY_WAY}
    assert "'Cupsy Yummy' -> 'Cupsy☆Yummy'" in r["resolved_names"]


def test_wrong_passcode_fails_loudly(con):
    r = check(con, "tcg_advanced", ydk([DREADNOUGHT_SERVANT + 1]))
    assert r["legal"] is None and "cards" not in r
    assert has(r, f"unknown passcode {DREADNOUGHT_SERVANT + 1}")


def test_release_date_gate(con):
    text = ydk([DREADNOUGHT_SERVANT])
    assert has(validate_deck(con, "tcg_advanced", ydk_text=text, as_of="2026-10-07"), "not TCG-released by 2026-10-07")
    assert validate_deck(con, "tcg_advanced", ydk_text=text, as_of="2026-10-08")["legal"] is True


def test_short_main_deck_reported(con):
    assert has(check(con, "tcg_advanced", ydk(fill_to=36)), "Main Deck has 36 cards")


@pytest.mark.parametrize("line,expect", [
    ("14261867 # comment", "line 3: unreadable line"),
    ("14261867x", "unreadable line"),
    ("#side", "'#side' is not a section marker"),
])
def test_ydk_bad_lines_are_errors_not_drops(con, line, expect):
    r = check(con, "tcg_advanced", ydk().replace("#main\n", f"#main\n{line}\n", 1))
    assert r["legal"] is None and has(r, expect)


def test_card_before_marker_is_error():
    assert any("before any" in e for e in parse_ydk("123\n#main\n").errors)


def test_crlf_and_bom_accepted_with_warning(con):
    r = check(con, "tcg_advanced", "﻿" + ydk().replace("\n", "\r\n"))
    assert r["legal"] is True and r["totals"]["main"]["cards"] == 40
    assert any("CRLF" in w for w in r["warnings"])


def test_ydke_url(con):
    main = [cid for cid in FILLER for _ in range(3)][:40]

    def enc(ids):
        return base64.b64encode(b"".join(struct.pack("<I", i) for i in ids)).decode()

    r = check(con, "genesys", f"ydke://{enc(main)}!{enc([HERALD_ARC])}!{enc([])}!")
    assert r["legal"] is True and r["totals"]["deck_points"] == 50


def test_point_cap_edges(con):
    exactly_100 = dict(main=[ILLUSION_GATE] * 3 + [DD_GROUND] * 2, extra=[HERALD_ARC])  # 30 + 20 + 50
    assert check(con, "genesys", ydk(**exactly_100))["legal"] is True
    assert has(check(con, "genesys", ydk(**exactly_100, side=[ECLIPSE_WYVERN])), "Points 111 > cap 100")
    assert has(check(con, "genesys", ydk(**exactly_100), point_cap=50), "Points 100 > cap 50")


def test_alt_art_counts_toward_limit(con):
    r = check(con, "tcg_advanced", ydk([DROLL, DROLL_ALT]))
    assert has(r, "Droll & Lock Bird", "2 copies", "Limited allows 1")
    assert next(c for c in r["cards"] if c["passcode"] == DROLL)["alt_passcodes"] == [DROLL_ALT]


def test_extra_deck_monster_in_main(con):
    assert has(check(con, "genesys", ydk([HERALD_ARC])), "Extra Deck monster in the Main Deck")


def test_stricter_banlist_source_wins(con):
    # 7 Colored Fish is unrestricted on YGOProDeck but Limited in the fixture Ignis list.
    assert has(check(con, "tcg_advanced", ydk([COLORED_FISH] * 2)), "7 Colored Fish", "Limited allows 1")


def test_card_names_starting_with_a_number(con):
    r = validate_deck(con, "genesys", decklist={"main": ["7 Colored Fish", "2 7 Colored Fish"]})
    assert r["totals"]["main"]["cards"] == 3 and r["cards"][0]["passcode"] == COLORED_FISH


def test_unknown_format(con):
    with pytest.raises(DeckInputError):
        validate_deck(con, "speed_duel", ydk_text=ydk())


def test_freshness_goes_stale(con):
    assert carddata.freshness(con, FETCHED + timedelta(days=1))["stale"] is False
    assert carddata.freshness(con, FETCHED + timedelta(days=8))["stale"] is True


def test_points_history_records_changes():
    con = build()
    dump = json.loads((FIX / "genesys_subset.json").read_text(encoding="utf-8"))
    next(c for c in dump["data"] if c["id"] == ILLUSION_GATE)["misc_info"][0]["genesys_points"] = 7
    lflist = (FIX / "tcg_lflist.conf").read_text(encoding="utf-8")
    carddata.build(con, dump, lflist, {}, {}, FETCHED)
    assert [tuple(r)[1:] for r in con.execute("SELECT * FROM points_history")] == [("genesys", ILLUSION_GATE, 10, 7)]
