"""Link extraction rules and find_links, on hand-written texts and the pinned fixture."""
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from ygosim import carddata
from ygosim.linkfind import find_links
from ygosim.links import extract_card, parse_descriptor, parse_materials

FIX = Path(__file__).parent / "fixtures"
NAMES = frozenset({"Polymerization", "Redox, Dragon Ruler of Boulders", "X-Head Cannon", "Y-Dragon Head",
                   "Z-Metal Tank", "Rescue-ACE Hydrant", "Destiny HERO - Malicious"})


def effects(text):
    return extract_card(text, NAMES)["effects"]


def test_archetype_search():
    (e,) = effects('When this card is Normal or Special Summoned: You can activate 1 of these effects.\n'
                   '● Add 1 "HERO" monster from your Deck to your hand.')
    assert e["verb"] == "add" and e["zones"] == ["Deck"]
    assert e["filter"] == {"archetypes": ["HERO"], "kinds": ["monster"]}
    assert "optional 'When' trigger (can miss the timing)" in e["flags"]


def test_named_card_with_comma_and_name_lists():
    (e,) = effects('Special Summon 1 "Redox, Dragon Ruler of Boulders" from your Deck.')
    assert e["filter"] == {"names": ["Redox, Dragon Ruler of Boulders"]}
    (e,) = effects('You can Special Summon 1 "X-Head Cannon", "Y-Dragon Head", or "Z-Metal Tank" from your Deck.')
    assert e["filter"]["names"] == ["X-Head Cannon", "Y-Dragon Head", "Z-Metal Tank"]


def test_stats_types_and_exclusions():
    (e,) = effects("Add 1 Level 4 or lower Warrior monster from your Deck to your hand.")
    assert e["filter"] == {"level": [0, 4], "races": ["Warrior"], "kinds": ["monster"]}
    (e,) = effects('You can Special Summon 1 "Batteryman" monster, except "Batteryman Charger", from your hand or Deck.')
    assert e["filter"]["archetypes"] == ["Batteryman"] and e["filter"]["exclude"] == ["Batteryman Charger"]
    assert e["zones"] == ["hand", "Deck"]
    (e,) = effects("Special Summon 1 Fish, Sea Serpent, or Aqua monster from your GY.")
    assert set(e["filter"]["races"]) == {"Fish", "Sea Serpent", "Aqua"}
    (e,) = effects('Special Summon 1 non-Ritual "Prediction Princess" monster from your Deck.')
    assert e["filter"]["not_kinds"] == ["ritual"]
    (e,) = effects('Special Summon 1 " Dragonmaid " monster from your GY.')
    assert e["filter"]["archetypes"] == ["Dragonmaid"]


def test_cost_vs_effect_and_hard_opt():
    banish, add = effects('You can banish 1 Fish monster from your hand or GY; add 1 "Ghoti" monster from your Deck '
                          'to your hand. You can only use this effect of "X" once per turn.')
    assert banish["cost"] is True and add["cost"] is False  # before ';' is cost, after is effect
    assert "hard once per turn" in add["flags"]


def test_self_summon_is_not_a_link():
    assert effects("You can Special Summon this card from your hand.") == []


def test_lock_clause():
    (lk,) = extract_card('Fusion Summon 1 Fusion Monster, also for the rest of this turn after this card resolves, '
                         'you cannot Special Summon monsters, except DARK "HERO" monsters.', NAMES)["locks"]
    assert lk["scope"] == "all" and lk["filter"] == {"archetypes": ["HERO"], "attributes": ["DARK"], "kinds": ["monster"]}
    assert lk["evidence"].startswith("you cannot Special Summon")
    (lk,) = extract_card("you cannot Special Summon monsters from the Extra Deck, except Link Monsters.", NAMES)["locks"]
    assert lk["scope"] == "extra" and lk["filter"] == {"kinds": ["link"]}


def test_materials():
    comps = parse_materials('1 Level 6 or higher "HERO" monster + 1 "Destiny HERO" monster', NAMES)
    assert [c["filter"] for c in comps] == [{"archetypes": ["HERO"], "level": [6, 99], "kinds": ["monster"]},
                                           {"archetypes": ["Destiny HERO"], "kinds": ["monster"]}]
    comps = parse_materials("1 Tuner + 1+ non-Tuner monsters", NAMES)
    assert comps[0]["filter"]["kinds"] == ["tuner"] and comps[1]["filter"]["not_kinds"] == ["tuner"]
    comps = parse_materials('"Elemental HERO Avian" or "Elemental HERO Burstinatrix" + 1 "HERO" monster', NAMES)
    assert comps[0]["filter"]["names"] == ["Elemental HERO Avian", "Elemental HERO Burstinatrix"]
    assert parse_materials("Must be Special Summoned with \"Mask Change\".", NAMES) is None


def test_descriptor_card_name_vs_archetype():
    assert parse_descriptor('"Polymerization"', NAMES) == {"names": ["Polymerization"]}
    assert parse_descriptor('"Polymerization" Spell', NAMES)["archetypes"] == ["Polymerization"]


@pytest.fixture(scope="module")
def con():
    con = carddata.connect(":memory:")
    dump = json.loads((FIX / "genesys_subset.json").read_text(encoding="utf-8"))
    carddata.build(con, dump, (FIX / "tcg_lflist.conf").read_text(encoding="utf-8"), {},
                   {"database_version": "fixture", "last_update": "2026-10-20"}, datetime(2026, 10, 20, tzinfo=timezone.utc))
    return con


DHERO = {"main": ["3 Destiny HERO - Malicious", "3 Destiny HERO - Dreadnought Servant", "3 Destiny HERO - Diamond Dude",
                  "Fusion Destiny"]}


def test_find_links_dhero(con):
    r = find_links(con, "genesys", decklist=DHERO, as_of="2026-10-20")
    into = {x["name"]: x for x in r["into_your_deck"]}
    assert "Elemental HERO Stratos" in into and "Elemental HERO Shadow Mist" in into
    assert "Destiny HERO - Malicious" in into["Elemental HERO Stratos"]["reaches_your"]
    # Stratos is WIND: Fusion Destiny's "except DARK HERO monsters" lock is flagged.
    assert any("Fusion Destiny" in b for b in into["Elemental HERO Stratos"]["breaks_deck_locks"])
    extra = {x["name"] for x in r["extra_deck_options"]}
    assert {"Destiny HERO - Destroyer Phoenix Enforcer", "Destiny HERO - Dystopia"} <= extra
    reach = {e["name"] for g in r["your_deck_reaches"] for e in g["examples"]}
    assert "Polymerization" in reach  # Dreadnought Servant adds "Polymerization"
    assert any(b["engine"] == "Elemental HERO" for b in r["bridges"])
    assert r["deck_locks"][0]["card"] == "Fusion Destiny"


def test_find_links_respects_points_budget(con):
    deck = {"main": DHERO["main"] + ["Destiny HERO - Dark Angel"]}  # 3 + 100 points: nothing left
    r = find_links(con, "genesys", decklist=deck, as_of="2026-10-20")
    assert r["points"]["max_points_per_suggestion"] < 0
    assert r["into_your_deck"] == [] and r["extra_deck_options"] == []
    r = find_links(con, "genesys", decklist=deck, max_points=10, as_of="2026-10-20")
    assert "Destiny HERO - Destroyer Phoenix Enforcer" in {x["name"] for x in r["extra_deck_options"]}  # 7 points


def test_find_links_with_cards_and_bad_names(con):
    r = find_links(con, "tcg_advanced", cards=["Destiny HERO - Malicious"], as_of="2026-10-20")
    assert "Elemental HERO Stratos" in {x["name"] for x in r["into_your_deck"]}
    r = find_links(con, "tcg_advanced", cards=["D-HERO Malicous"])
    assert r["error"].startswith("input problems") and r["parse_errors"]


def test_treated_as_every_quoted_archetype():
    from ygosim.links import treated_as
    assert treated_as('(This card is always treated as a "Magistus" and "Witchcrafter" card.)') == \
        ("Magistus", "Witchcrafter")
    assert treated_as('(This card is always treated as a "Zubaba", "Gagaga", "Gogogo", and "Dododo" card.)') == \
        ("Zubaba", "Gagaga", "Gogogo", "Dododo")
    assert treated_as('(This card is always treated as a "Witchcrafter" card.)') == ("Witchcrafter",)


def test_mentions_it_resolves_to_the_named_card():
    names = NAMES | {"Regulus, the Prince of Endymion"}
    by_name, by_mention, _ = extract_card(
        'When this card is activated: Add 1 "Regulus, the Prince of Endymion" or 1 monster that mentions it from '
        'your Deck to your hand, then you can Special Summon 1 Spellcaster monster from your hand.', names)["effects"]
    assert by_name["filter"] == {"names": ["Regulus, the Prince of Endymion"]}
    assert by_mention["filter"] == {"mentions": ["Regulus, the Prince of Endymion"], "kinds": ["monster"]}


def test_find_links_lists_own_archetype_cards_not_run(con):
    r = find_links(con, "genesys", decklist=DHERO, as_of="2026-10-20")
    unplayed = {x["name"]: x for x in r["your_archetypes_unplayed"]}
    assert "Destiny HERO - Dreadmaster" in unplayed  # a Destiny HERO the list doesn't run
    assert "Destiny HERO - Malicious" in unplayed["Destiny HERO - Dreadmaster"]["reaches_your"]
    assert not set(unplayed) & {"Destiny HERO - Malicious", "Destiny HERO - Diamond Dude"}  # already in the deck
