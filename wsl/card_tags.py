"""Keyword rules over card text: how much each card interrupts the opponent's turn.

Values, roughly "interruptions":
  field (face-up)  1.0 quick-effect negate, 0.75 other quick effect, 0.5 floodgate ("your opponent cannot")
  field (set)      traps: 1.0 negate, 0.75 other; Quick-Play spells: 0.5
  hand             1.0 hand trap (activatable from the hand on the opponent's turn); monster hand
                   traps are worth 0 on the field
Rules mislabel some cards; card_tag_overrides.json ({"id": {"field": x, "hand": y}}) corrects them.
"""
import json
import os
import re
import sqlite3
from functools import cache

RUN = os.path.expanduser("~/ygo/run")
OVERRIDES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "card_tag_overrides.json")
TYPE_MONSTER, TYPE_SPELL, TYPE_TRAP = 0x1, 0x2, 0x4
TYPE_CONTINUOUS, TYPE_QUICKPLAY, TYPE_TOKEN = 0x20000, 0x10000, 0x4000

QUICK = re.compile(r"\(Quick Effect\)|during your opponent's turn|during either player's turn|"
                   r"when your opponent activates|when a card or effect is activated", re.I)
NEGATE = re.compile(r"\bnegate\b", re.I)
FLOODGATE = re.compile(r"your opponent cannot|neither player can", re.I)
# Costs/conditions that mean the effect is used from the hand.
FROM_HAND = re.compile(r"discard this card|send this card from your hand|reveal this card in your hand|"
                       r"activate this card from your hand|special summon this card from your hand|"
                       r"banish this card from your hand", re.I)
EFFECT_SPLIT = re.compile(r"(?<=\.)\s+(?=[A-Z(●])|\n+|●")
OPPONENT_TRIGGER = re.compile(r"your opponent (normal or special |special |normal )?summons|"
                              r"your opponent activates|opponent's (main phase|turn)", re.I)


def tag(type_: int, desc: str) -> dict:
    quick, negate = bool(QUICK.search(desc)), bool(NEGATE.search(desc))
    field = 0.0
    if type_ & TYPE_TOKEN:
        field = 0.0
    elif type_ & TYPE_TRAP:
        field = 1.0 if negate else 0.75
        if type_ & TYPE_CONTINUOUS and not quick and FLOODGATE.search(desc):
            field = 0.5
    elif quick:
        field = 1.0 if negate else 0.75
    elif FLOODGATE.search(desc):
        field = 0.5
    set_value = field if type_ & TYPE_TRAP else (0.5 if type_ & TYPE_QUICKPLAY and quick else 0.0)
    # Hand traps: one effect that is both used from the hand and usable on the opponent's turn
    # (Ash, Impermanence, Nibiru, ...). Checked per effect so combo starters with a separate
    # quick effect don't qualify.
    hand = 0.0
    if type_ & TYPE_TRAP and re.search(r"activate this card from your hand", desc, re.I):
        hand = 1.0  # Infinite Impermanence, Dominus traps
    elif not type_ & TYPE_SPELL:
        for effect in EFFECT_SPLIT.split(desc):
            if FROM_HAND.search(effect) and (QUICK.search(effect) or OPPONENT_TRIGGER.search(effect)):
                hand = 1.0
                break
    if hand and type_ & TYPE_MONSTER:
        field = 0.0  # a summoned Ash/Veiler/Nibiru does nothing on the field
    return {"field": field, "set": set_value, "hand": hand}


@cache
def all_tags() -> dict[int, dict]:
    con = sqlite3.connect(f"{RUN}/cards.cdb")
    rows = con.execute("select d.id, d.type, d.alias, t.desc from datas d join texts t on t.id = d.id")
    tags = {cid: tag(type_, desc or "") for cid, type_, _alias, desc in rows}
    if os.path.exists(OVERRIDES):
        by_name: dict[str, list[int]] = {}
        for cid, name in con.execute("select id, name from texts"):
            by_name.setdefault(name, []).append(cid)
        for name, over in json.load(open(OVERRIDES)).items():
            if name not in by_name:
                raise KeyError(f"card_tag_overrides.json: no card named {name!r}")
            values = {k: v for k, v in over.items() if k in ("field", "set", "hand")}
            for cid in by_name[name]:  # alt arts share the name
                tags[cid].update(values)
    return tags


if __name__ == "__main__":
    import glob
    names = dict(sqlite3.connect(f"{RUN}/cards.cdb").execute("select id, name from texts"))
    ids = {int(l) for p in glob.glob(f"{RUN}/decks/[!_]*.ydk") for l in open(p) if l.strip().isdigit()}
    tags = all_tags()
    rows = sorted(((tags[i]["field"], tags[i]["set"], tags[i]["hand"], names.get(i, i)) for i in ids if i in tags),
                  key=lambda r: (-r[2], -r[0], r[3]))
    for f, s, h, n in rows:
        if f or s or h:
            print(f"field {f:.2f}  set {s:.2f}  hand {h:.0f}  {n}")
    print(f"{sum(1 for r in rows if any(r[:3]))} of {len(rows)} field-deck cards tagged")
