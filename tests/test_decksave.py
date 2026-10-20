"""finalize_deck saves only legal decks; files round-trip through the validator."""
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from ygosim import carddata, decksave
from ygosim.formats import parse_ydke, validate_deck

FIX = Path(__file__).parent / "fixtures"
FILLER = ['"A" Cell Breeding Device', '"A" Cell Incubator', '"A" Cell Scatter Burst', "1st Movement Solo",
          "3-Hump Lacooda", "4-Starred Ladybug of Doom", "7", "7 Completed", "8-Claws Scorpion",
          "A Cat of Ill Omen", "A Deal with Dark Ruler", "A Feather of the Phoenix", "A Feint Plan"]


@pytest.fixture(scope="module")
def con():
    con = carddata.connect(":memory:")
    dump = json.loads((FIX / "genesys_subset.json").read_text(encoding="utf-8"))
    carddata.build(con, dump, (FIX / "tcg_lflist.conf").read_text(encoding="utf-8"), {},
                   {"database_version": "fixture", "last_update": "2026-10-20"}, datetime(2026, 10, 20, tzinfo=timezone.utc))
    return con


@pytest.fixture(autouse=True)
def decks_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(decksave, "DECKS_DIR", tmp_path / "decks")
    return tmp_path / "decks"


def deck(*extra_main, extra=()):
    return {"main": [f"3 {n}" for n in FILLER] + list(extra_main), "extra": list(extra), "side": []}


def test_saves_legal_genesys_deck(con, decks_dir):
    r = decksave.finalize_deck(con, "genesys", "D-HERO Test!", deck("Illusion Gate"),
                               notes="test", as_of="2026-10-20")
    assert r["saved"] is True and r["ydk"].endswith("d-hero-test.genesys.ydk")
    assert "1 Illusion Gate  [10 pts]" in r["text"] and r["breakdown"]["pointed_cards"] == ["1x Illusion Gate = 10"]
    # The saved .ydk and the ydke URL both validate to the same legal deck.
    assert validate_deck(con, "genesys", ydk_path=r["ydk"], as_of="2026-10-20")["legal"] is True
    assert sum(len(z) for z in parse_ydke(r["ydke"]).zones.values()) == 40
    assert "\r" not in Path(r["ydk"]).read_text(encoding="utf-8")
    assert decksave.saved_decks(format="genesys")["decks"][0]["name"] == "D-HERO Test!"


def test_refuses_illegal_deck_and_writes_nothing(con, decks_dir):
    r = decksave.finalize_deck(con, "tcg_advanced", "bad", deck("Eclipse Wyvern"), as_of="2026-10-20")
    assert r["saved"] is False and any("Forbidden" in p for p in r["problems"])
    assert not decks_dir.exists() or not list(decks_dir.glob("*.ydk"))
    r = decksave.finalize_deck(con, "genesys", "bad", {"main": ["D.D. Ground"]})
    assert r["saved"] is False and r["parse_errors"]


def test_resave_keeps_history(con, decks_dir):
    decksave.finalize_deck(con, "tcg_advanced", "List", deck("Illusion Gate"), as_of="2026-10-20")
    r = decksave.finalize_deck(con, "tcg_advanced", "List", deck("Illusion Gate", "Illusion Gate"), as_of="2026-10-20")
    assert Path(r["previous_version"]).exists()
    assert len(decksave.saved_decks()["decks"]) == 1
