"""Banlist and release-date guards. These hit cached YGOProDeck/Ignis data in data/."""
from collections import Counter
from datetime import date

import pytest

from ygosim.api import DATA_DIR
from ygosim.banlist import parse_lflist, tcg_banlist
from ygosim.cards import by_name, card_db
from ygosim.deck import Deck, IllegalDeckError

ASH = by_name("Ash Blossom & Joyous Spring").id


def filler(n: int, skip: set[int] = frozenset()) -> Counter:
    """n legal main-deck cards at 1 copy each, for building otherwise-legal test decks."""
    bl, out = tcg_banlist(), Counter()
    for card in {c.id: c for c in card_db().values()}.values():
        if len(out) == n:
            break
        if card.id not in skip and not card.is_extra and bl.limit(card.id) >= 1 \
                and card.released_by(date(2020, 1, 1)) and "Token" not in card.type:
            out[card.id] = 1
    return out


def deck_with(card_id: int, copies: int) -> Deck:
    main = filler(40 - copies, {card_id})
    main[card_id] = copies
    return Deck("test", main)


def test_filler_deck_is_legal():
    assert deck_with(ASH, 3).legality_errors() == []


def test_four_copies_illegal():
    assert any("4 copies" in e for e in deck_with(ASH, 4).legality_errors())


def test_forbidden_card_illegal():
    rotary = by_name("Kewl Tune Rotary").id
    assert tcg_banlist().limit(rotary) == 0
    assert deck_with(rotary, 1).legality_errors()


def test_alt_art_cannot_dodge_banlist():
    db, bl = card_db(), tcg_banlist()
    alt = next(pid for pid, c in db.items() if pid != c.id and bl.limit(c.id) == 0 and not c.is_extra)
    assert any("TCG limit 0" in e for e in deck_with(alt, 1).legality_errors())


def test_alt_arts_count_toward_same_limit():
    db = card_db()
    pid, card = next((p, c) for p, c in db.items() if p != c.id and not c.is_extra
                     and tcg_banlist().limit(c.id) == 3 and c.released_by(date.today()))
    main = filler(36, {card.id})
    main[card.id], main[pid] = 2, 2
    assert any("4 copies" in e for e in Deck("t", main).legality_errors())


def test_unreleased_card_illegal_before_tcg_date():
    card = by_name('Ars Magna "Citrinitas"')
    assert card.tcg_date == date(2026, 10, 8)
    deck = deck_with(card.id, 1)
    assert any("not TCG-released" in e for e in deck.legality_errors(date(2026, 10, 7)))
    assert not any("not TCG-released" in e for e in deck.legality_errors(date(2026, 10, 8)))


def test_unknown_card_illegal():
    assert any("unknown card" in e for e in deck_with(999_999_999, 1).legality_errors())


def test_extra_deck_card_in_main_illegal():
    link = next(c for c in card_db().values() if "Link" in c.type and tcg_banlist().limit(c.id) == 3)
    assert any("extra deck card in main" in e for e in deck_with(link.id, 1).legality_errors())


def test_to_ydk_refuses_illegal(tmp_path):
    with pytest.raises(IllegalDeckError):
        deck_with(ASH, 4).to_ydk(tmp_path / "x.ydk")
    assert not (tmp_path / "x.ydk").exists()


def test_parse_lflist_reads_only_first_list():
    title, limits = parse_lflist("#[A]\n!A\n#Forbidden\n1 0 --x\n2 1 --y\n!B\n3 0 --z\n")
    assert title == "A" and limits == {1: 0, 2: 1}


def test_stricter_source_wins():
    bl = tcg_banlist()
    for c in {c.id: c for c in card_db().values()}.values():
        assert bl.limit(c.id) <= c.ygoprodeck_limit


def test_projector_rejects_deck_with_forbidden_core_card():
    from ygosim.meta import Archetype
    from ygosim.project import project_one

    rotary, cue = by_name("Kewl Tune Rotary").id, by_name("Kewl Tune Cue").id
    main = filler(36, {rotary, cue})
    main[cue], main[rotary] = 3, 1
    ocg = Archetype("Kewl Tune", [Deck("Kewl Tune", main)], set())
    proj = project_one(ocg, [], [], date.today())
    assert proj.error and "Kewl Tune Rotary" in proj.error


@pytest.mark.parametrize("folder", ["meta", "projected"])
def test_every_exported_ydk_is_legal(folder):
    files = list((DATA_DIR / folder).glob("*.ydk"))
    as_of = None
    if folder == "projected" and (DATA_DIR / folder / "summary.json").exists():
        import json
        reports = [json.loads(p.read_text()) for p in (DATA_DIR / folder).glob("*.json") if p.name != "summary.json"]
        as_of = date.fromisoformat(reports[0]["as_of"]) if reports else None
    for f in files:
        assert Deck.from_ydk(f).legality_errors(as_of) == [], f.name
