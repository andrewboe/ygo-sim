"""card_rulings with a fake YGOResources: caching, manifest invalidation, with_card, query, fetch cap."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from ygosim import carddata, rulings
from ygosim.formats import DeckInputError

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture
def con():
    con = carddata.connect(":memory:")
    dump = json.loads((FIX / "genesys_subset.json").read_text(encoding="utf-8"))
    carddata.build(con, dump, (FIX / "tcg_lflist.conf").read_text(encoding="utf-8"), {},
                   {"database_version": "fixture", "last_update": "2026-10-20"}, datetime(2026, 10, 20, tzinfo=timezone.utc))
    return con


def kid(con, name):
    return con.execute("SELECT konami_id FROM cards WHERE name = ?", (name,)).fetchone()[0]


class FakeYR:
    def __init__(self, con):
        self.gate, self.mal = kid(con, "Illusion Gate"), kid(con, "Destiny HERO - Malicious")
        self.calls, self.rev, self.changed = [], 100, {}
        self.cards = {self.gate: [3, 2, 1], self.mal: [2]}
        self.qas = {
            1: {"title": "Old one", "question": "Q1 about <<%d>>" % self.gate, "answer": "Yes."},
            2: {"title": "Gate and <<%d>>" % self.mal, "question": "Can <<%d>> be summoned?" % self.mal,
                "answer": "No, it cannot, because it is a cost."},
            3: {"title": "Damage Step", "question": "Can you activate it during the Damage Step?",
                "answer": "No. Also see <<999999>>."},
        }

    def __call__(self, path):
        self.calls.append(path)
        if path.startswith("/manifest/"):
            return {"data": self.changed}, self.rev
        if path.startswith("/data/card/"):
            k = int(path.rsplit("/", 1)[1])
            return {"faqData": {"entries": {"1": [{"en": "About this card's effect:"}, {"en": "It is a Quick Effect."}],
                                            "2": [{"ja": "untranslated"}]}},
                    "qaIndex": self.cards.get(k, [])}, self.rev
        if path.startswith("/data/qa/"):
            q = int(path.rsplit("/", 1)[1])
            en = {**self.qas[q], "thisSrc": {"date": f"2025-0{q}-01"}, "translationStatus": "confirmed"}
            return {"cards": [self.gate], "qaData": {"en": en}}, self.rev
        if path == "/data/idx/card/name/en":
            return {"Some OCG Card": [999999]}, self.rev
        raise AssertionError(path)


def test_faq_qas_newest_first_and_names(con):
    fake = FakeYR(con)
    r = rulings.card_rulings(con, "Illusion Gate", fetch=fake)
    assert r["faq"] == ["About this card's effect: It is a Quick Effect."]  # untranslated entry skipped
    assert [q["id"] for q in r["qa"]] == [3, 2, 1] and r["qa_total"] == 3
    assert '"Destiny HERO - Malicious"' in r["qa"][1]["question"]  # <<konami id>> -> local name
    assert '"Some OCG Card"' in r["qa"][0]["answer"]  # unknown locally -> name index (one request)
    assert r["qa"][0]["url"].endswith("/qa#3") and "OCG rulings" in r["source"]


def test_cached_after_first_call(con):
    fake = FakeYR(con)
    rulings.card_rulings(con, "Illusion Gate", fetch=fake)
    n = len(fake.calls)
    r = rulings.card_rulings(con, "Illusion Gate", fetch=fake)
    assert len(fake.calls) == n and r["cache"]["fetched_now"] == 0


def test_with_card_intersects_qa_indexes(con):
    r = rulings.card_rulings(con, "Illusion Gate", with_card="Destiny HERO - Malicious", fetch=FakeYR(con))
    assert r["with_card"] == "Destiny HERO - Malicious" and [q["id"] for q in r["qa"]] == [2]


def test_query_filters_words(con):
    r = rulings.card_rulings(con, "Illusion Gate", query="damage step", fetch=FakeYR(con))
    assert [q["id"] for q in r["qa"]] == [3]


def test_manifest_drops_changed_entries(con):
    fake = FakeYR(con)
    rulings.card_rulings(con, "Illusion Gate", fetch=fake)
    # A day later YGOResources reports QA 3 changed: only it is refetched.
    with con:
        con.execute("UPDATE rul_state SET value = ? WHERE key = 'checked_at'",
                    ((datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),))
    fake.changed, fake.qas[3]["answer"] = {"qa": {"3": 1}}, "Updated answer."
    fake.calls.clear()
    r = rulings.card_rulings(con, "Illusion Gate", fetch=fake)
    assert fake.calls == ["/manifest/100", "/data/qa/3"]
    assert r["qa"][0]["answer"] == "Updated answer." and r["cache"]["sync"].startswith("synced")


def test_fetch_cap(con, monkeypatch):
    monkeypatch.setattr(rulings, "MAX_FETCH", 2)
    r = rulings.card_rulings(con, "Illusion Gate", fetch=FakeYR(con))
    assert r["qa_shown"] < 3 and "fetch cap" in r["note"]


def test_errors_are_clear(con):
    with pytest.raises(DeckInputError, match="no card named"):
        rulings.card_rulings(con, "D.D. Ground", fetch=FakeYR(con))

    def down(path):
        raise ConnectionError("offline")
    with pytest.raises(DeckInputError, match="YGOResources request failed"):
        rulings.card_rulings(con, "Illusion Gate", fetch=down)
