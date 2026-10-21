"""Card link graph: what each card's effects reach, what Extra Deck monsters need, and locks.

Full pass at build time (extract_all): every card's text is parsed with rules for the common
Konami templates into
  effects(canonical_id, verb, zones, filter, evidence, cost, flags)   add / summon / send / banish / set
  materials(canonical_id, components, line)                          Extra Deck material lines
  locks(canonical_id, scope, filter, evidence)                       "cannot Special Summon ... except X"
A filter is JSON: names, archetypes (name contains, or "always treated as"), mentions, exclude,
attributes, races, level/atk/def ranges, kinds / not_kinds. Links are joins of filters against card
facts, done on demand by find_links. Rules miss unusual wordings (and Fusion Summon spells); what
is extracted is evidence-backed, what is missing is just absent.
"""
import json
import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field

ATTRIBUTES = ("DARK", "LIGHT", "EARTH", "WATER", "FIRE", "WIND", "DIVINE")
RACES = ("Beast-Warrior", "Winged Beast", "Sea Serpent", "Divine-Beast", "Creator God", "Aqua", "Beast",
         "Cyberse", "Dinosaur", "Dragon", "Fairy", "Fiend", "Fish", "Illusion", "Insect", "Machine", "Plant",
         "Psychic", "Pyro", "Reptile", "Rock", "Spellcaster", "Thunder", "Warrior", "Wyrm", "Zombie")
# Longest first, so "Normal Spell" wins over "Spell" and "non-Tuner" over "Tuner".
KIND_WORDS = [
    ("Spell/Trap", {"spell", "trap"}), ("Spell or Trap", {"spell", "trap"}),
    ("Quick-Play Spell", {"quick-play"}), ("Continuous Spell", {"continuous spell"}),
    ("Normal Spell", {"normal spell"}), ("Field Spell", {"field spell"}), ("Equip Spell", {"equip spell"}),
    ("Ritual Spell", {"ritual spell"}), ("Normal Trap", {"normal trap"}), ("Continuous Trap", {"continuous trap"}),
    ("Counter Trap", {"counter trap"}), ("Fusion Monster", {"fusion"}), ("Synchro Monster", {"synchro"}),
    ("Xyz Monster", {"xyz"}), ("XYZ Monster", {"xyz"}), ("Link Monster", {"link"}), ("Ritual Monster", {"ritual"}),
    ("Pendulum Monster", {"pendulum"}), ("Normal Monster", {"normal monster"}), ("Effect Monster", {"effect"}),
    ("Spell", {"spell"}), ("Trap", {"trap"}), ("monster", {"monster"}), ("Monster", {"monster"}),
]
NON_KIND = {"Normal": "normal monster", "XYZ": "xyz"}
SUBTYPES = ("Tuner", "Flip", "Gemini", "Spirit", "Union", "Toon")
VERBS = {"add": "add", "special summon": "summon", "send": "send", "banish": "banish", "set": "set"}
ZONE = r"(?:hand|Deck|GY|Graveyard|Extra Deck|banishment|banished cards|banished)"
REACH = re.compile(
    r"\b(?P<verb>add|Special Summon|send|banish|Set)\s+(?P<count>\d+|up to \d+|any number of|a|an)\s+"
    # Quoted names may contain commas; ", or 1 ..." joins alternatives.
    r'(?P<desc>(?:"[^"\n]{1,80}"|,(?=\s+(?:or\s+|except\s+)?[A-Z"])|[^;:.,●\n"]){1,120}?),?\s+(?:directly\s+)?'
    r'from\s+(?:among\s+)?(?:your\s+)?'
    rf"(?P<zones>{ZONE}(?:(?:,\s*|\s+or\s+|,\s*or\s+|\s+and/or\s+)(?:your\s+)?{ZONE})*)", re.I)
LOCK = re.compile(r"cannot Special Summon(?P<mid>[^.;]*?),?\s+except (?P<desc>[^.;]+?)(?=\.|;|$)", re.I)
# 'always treated as a "Magistus" and "Witchcrafter" card': every quoted name in the clause counts.
TREATED = re.compile(r'always treated as (?:an? )?"[^"]+"'
                     r'(?:(?: card)?(?:,\s+(?:and\s+|or\s+)?|\s+and\s+|\s+or\s+)(?:an? )?"[^"]+")*', re.I)
MENTIONS_IT = re.compile(r"\b(that|which) (mentions?|lists?) it\b")
EXCEPT = re.compile(r'except "([^"]+)"')
HARD_OPT = re.compile(r"You can only (?:use (?:each|this|the)\b[^.]*?|activate 1 [^.]*?)once per turn|"
                      r"You can only activate 1 \"[^\"]+\" per turn", re.I)
WHEN_TRIGGER = re.compile(r"^\s*When\b[^:]*:\s*You can", re.I)


# ---------------------------------------------------------------- descriptors

def parse_descriptor(desc: str, card_names: frozenset[str]) -> dict:
    """'1 Level 4 or lower DARK "HERO" monster' -> filter dict. Unknown words are ignored."""
    f: dict = defaultdict(list)
    d = " " + desc.strip() + " "
    for m in re.finditer(r'(?:that|which) (?:mentions?|lists?) "([^"]+)"', d):
        f["mentions"].append(m.group(1))
    d = re.sub(r'(?:that|which) (?:mentions?|lists?) "[^"]+"(?: as material)?', " ", d)
    for m in re.finditer(r'"([^"]+)"', d):
        q = m.group(1).strip()  # some texts have '" Dragonmaid "'
        after = d[m.end():m.end() + 25]
        if q in card_names and not re.match(r"\s*(?:monsters?|cards?|Spells?|Traps?|Spell/Trap|Normal|Quick|"
                                            r"Continuous|Field|Equip|Ritual|Fusion|Synchro|Xyz|Link|Tuner)",
                                            after):
            f["names"].append(q)
        else:
            f["archetypes"].append(q)
    d = re.sub(r'"[^"]+"', " ", d)
    if m := re.search(r"Level (\d+) or (lower|less|higher|more)", d, re.I):
        n = int(m.group(1))
        f["level"] = [0, n] if m.group(2).lower() in ("lower", "less") else [n, 99]
    elif m := re.search(r"Levels? (\d+)(?: or (\d+))?", d):
        f["level"] = [int(m.group(1)), int(m.group(2) or m.group(1))]
    for stat in ("ATK", "DEF"):
        if m := re.search(rf"(\d+) or (less|lower|more|higher) {stat}", d):
            n = int(m.group(1))
            f[stat.lower()] = [0, n] if m.group(2) in ("less", "lower") else [n, 99999]
        elif m := re.search(rf"with (\d+) {stat}", d):
            f[stat.lower()] = [int(m.group(1))] * 2
    f["attributes"] = [a for a in ATTRIBUTES if re.search(rf"\b{a}\b", d)]
    rest = d
    for r in RACES:
        if re.search(rf"\b{re.escape(r)}\b", rest):
            f["races"].append(r)
            rest = re.sub(rf"\b{re.escape(r)}\b", " ", rest)
    for m in re.finditer(r"\bnon-(Tuner|Ritual|Fusion|Synchro|Xyz|XYZ|Link|Effect|Pendulum|Normal)\b", rest):
        f["not_kinds"].append(NON_KIND.get(m.group(1), m.group(1).lower()))
    rest = re.sub(r"\bnon-\w+", " ", rest)
    if re.search(r"\bTuners?\b", rest):
        f["kinds"].append("tuner")
    for m in re.finditer(r"\b(Flip|Gemini|Spirit|Union|Toon)\b", rest):
        f["kinds"].append(m.group(1).lower())
    for word, kinds in KIND_WORDS:
        if re.search(rf"\b{re.escape(word)}s?\b", rest):
            f["kinds"] += sorted(kinds)
            rest = re.sub(rf"\b{re.escape(word)}s?\b", " ", rest)
    return {k: v for k, v in f.items() if v}


def specificity(f: dict) -> int:
    return sum(1 for k in ("names", "archetypes", "mentions", "attributes", "races", "level", "atk", "def") if f.get(k))


# ---------------------------------------------------------------- card facts

@dataclass
class Facts:
    cid: int
    name: str
    frame: str
    type: str
    race: str
    attribute: str | None
    level: int | None
    atk: int | None
    def_: int | None
    treated: tuple[str, ...]
    mentions: frozenset[str]
    kinds: set[str] = field(default_factory=set)

    @property
    def is_monster(self) -> bool:
        return self.frame not in ("spell", "trap", "token", "skill")


def treated_as(desc: str) -> tuple[str, ...]:
    return tuple(q for m in TREATED.finditer(desc) for q in re.findall(r'"([^"]+)"', m.group(0)))


def facts_of(row: sqlite3.Row, mentions: frozenset[str]) -> Facts:
    f = Facts(row["canonical_id"], row["name"], row["frame_type"], row["type"], row["race"] or "",
              row["attribute"], row["level"], row["atk"], row["def"],
              treated_as(row["desc"] or ""), mentions)
    parts = set(f.frame.split("_"))
    if f.is_monster:
        f.kinds |= {"monster", "card"} | parts
        if "normal" in parts:
            f.kinds.add("normal monster")
        f.kinds |= {s.lower() for s in SUBTYPES if s in f.type}
    elif f.frame in ("spell", "trap"):
        f.kinds |= {f.frame, "card"}
        sub = {"Quick-Play": "quick-play", "Continuous": f"continuous {f.frame}", "Normal": f"normal {f.frame}",
               "Field": "field spell", "Equip": "equip spell", "Ritual": "ritual spell", "Counter": "counter trap"}
        if f.race in sub:
            f.kinds.add(sub[f.race])
    return f


def matches(c: Facts, f: dict) -> bool:
    if c.name in f.get("exclude", ()):
        return False
    if (f.get("names") or f.get("archetypes")) and not (c.name in f.get("names", ()) or
                                                        _in_archetype(c, f.get("archetypes", ()))):
        return False
    if f.get("mentions") and not (set(f["mentions"]) & c.mentions):
        return False
    if f.get("kinds") and not (set(f["kinds"]) & c.kinds):
        return False
    if f.get("not_kinds") and set(f["not_kinds"]) & c.kinds:
        return False
    if f.get("attributes") and c.attribute not in f["attributes"]:
        return False
    if f.get("races") and c.race not in f["races"]:
        return False
    if (lv := f.get("level")) and not (c.is_monster and c.level is not None and not {"xyz", "link"} & c.kinds
                                       and lv[0] <= c.level <= lv[1]):
        return False
    for key, val in (("atk", c.atk), ("def", c.def_)):
        if (rng := f.get(key)) and not (val is not None and rng[0] <= val <= rng[1]):
            return False
    if (f.get("level") or f.get("attributes") or f.get("races") or f.get("atk")) and not c.is_monster:
        return False
    return True


def _in_archetype(c: Facts, archetypes: list[str]) -> bool:
    return any(a in c.name or a in c.treated for a in archetypes)


# ---------------------------------------------------------------- extraction

def _sentence(text: str, start: int, end: int) -> tuple[str, int]:
    """The sentence around [start, end) and the match offset inside it."""
    s = max(text.rfind(". ", 0, start) + 2 if text.rfind(". ", 0, start) >= 0 else 0,
            text.rfind("\n", 0, start) + 1, text.rfind("●", 0, start) + 1)
    e = min((i for i in (text.find(". ", end), text.find("\n", end)) if i >= 0), default=len(text))
    return text[s:e + 1].strip(), start - s


def _effect_head(text: str, start: int) -> str:
    """The opening sentence of the effect containing `start`; for a "●" bullet, the line it hangs from."""
    line = text.rfind("\n", 0, start) + 1
    while line > 0 and text[line:].lstrip().startswith("●"):
        line = text.rfind("\n", 0, line - 1) + 1
    end = start if not text[text.rfind("\n", 0, start) + 1:].lstrip().startswith("●") else text.find("\n", line)
    head_start = max(line, text.rfind(". ", line, end) + 2 if text.rfind(". ", line, end) >= 0 else line)
    return text[head_start:end if end > head_start else start]


def _resolve_it(desc: str) -> str:
    """'"Regulus" or 1 monster that mentions it' -> '... that mentions "Regulus"' (the last quoted name before)."""
    def sub(m: re.Match) -> str:
        before = re.findall(r'"([^"]+)"', desc[:m.start()])
        return f'{m.group(1)} {m.group(2)} "{before[-1]}"' if before else m.group(0)
    return MENTIONS_IT.sub(sub, desc)


def extract_card(desc: str, card_names: frozenset[str]) -> dict:
    """Effects, materials and locks of one card's text."""
    text = (desc or "").replace("\r\n", "\n")
    text = re.sub(r'",\s+(?:or\s+)?"', '" or "', text)  # "X", "Y", or "Z" -> one list of names
    card_flags = ["hard once per turn"] if HARD_OPT.search(text) else []
    effects = []
    for m in REACH.finditer(text):
        sentence, off = _sentence(text, m.start(), m.end())
        rest = text[m.end(): text.find(".", m.end()) if text.find(".", m.end()) >= 0 else len(text)]
        desc_text = m.group("desc")
        excluded = EXCEPT.findall(desc_text) + EXCEPT.findall(rest)
        desc_text = re.sub(r',?\s*except\s+"[^"]+"', "", desc_text)
        desc_text = _resolve_it(desc_text)
        for alt in re.split(r",?\s+or\s+(?:1|a|an)\s+", desc_text):
            f = parse_descriptor(alt, card_names)
            if not f:
                continue
            if excluded:
                f["exclude"] = excluded
            semi = sentence.find(";")
            flags = list(card_flags)
            if WHEN_TRIGGER.search(sentence) or WHEN_TRIGGER.search(_effect_head(text, m.start())):
                flags.append("optional 'When' trigger (can miss the timing)")
            zones = re.split(r",\s*or\s+|,\s*|\s+or\s+|\s+and/or\s+", m.group("zones"))
            effects.append({"verb": VERBS[m.group("verb").lower()],
                            "zones": [z.replace("your ", "").replace("Graveyard", "GY") for z in zones],
                            "filter": f, "evidence": sentence[:300], "cost": 0 <= off < semi, "flags": flags})
    locks = []
    for m in LOCK.finditer(text):
        f = parse_descriptor(m.group("desc"), card_names)
        if f:  # evidence is the lock clause itself; the sentence around it can be very long
            locks.append({"scope": "extra" if "Extra Deck" in m.group("mid") else "all", "filter": f,
                          "evidence": "you " + m.group(0)[:250]})
    return {"effects": effects, "locks": locks}


def parse_materials(line: str, card_names: frozenset[str]) -> list[dict] | None:
    """'1 Level 6 or higher "HERO" monster + 1 "Destiny HERO" monster' -> components."""
    if not line or ";" in line or ":" in line or len(line) > 200:
        return None
    comps = []
    for part in line.split(" + "):
        part = part.strip()
        if m := re.match(r"^(\d+)(\+)?\s+(.+)$", part):
            n, more, desc = int(m.group(1)), bool(m.group(2)), m.group(3)
        elif re.fullmatch(r'"[^"]+"(?: or "[^"]+")*', part):  # "A" or "B"
            comps.append({"count": 1, "or_more": False, "text": part,
                          "filter": {"names": re.findall(r'"([^"]+)"', part), "kinds": ["monster"]}})
            continue
        else:
            return None
        f = parse_descriptor(desc, card_names)
        if desc.startswith('"') and desc.endswith('"') and desc.strip('"') in card_names:
            f = {"names": [desc.strip('"')]}
        f.setdefault("kinds", ["monster"])
        comps.append({"count": n, "or_more": more, "filter": f, "text": part})
    return comps


SCHEMA = """
CREATE TABLE IF NOT EXISTS effects (canonical_id INTEGER, verb TEXT, zones TEXT, filter TEXT,
  evidence TEXT, cost INTEGER, flags TEXT);
CREATE INDEX IF NOT EXISTS effects_cid ON effects(canonical_id);
CREATE TABLE IF NOT EXISTS materials (canonical_id INTEGER PRIMARY KEY, components TEXT, line TEXT);
CREATE TABLE IF NOT EXISTS locks (canonical_id INTEGER, scope TEXT, filter TEXT, evidence TEXT);
"""


def extract_all(con: sqlite3.Connection) -> dict:
    """The full pass: parse every canonical card's text into effects, materials and locks."""
    con.executescript(SCHEMA)
    rows = con.execute("SELECT * FROM cards WHERE passcode = canonical_id AND type NOT IN ('Token','Skill Card')").fetchall()
    names = frozenset(r["name"] for r in rows)
    eff, mats, lks = [], [], []
    for r in rows:
        x = extract_card(r["desc"], names)
        for e in x["effects"]:
            eff.append((r["canonical_id"], e["verb"], ",".join(e["zones"]), json.dumps(e["filter"]),
                        e["evidence"], int(e["cost"]), json.dumps(e["flags"])))
        for lk in x["locks"]:
            lks.append((r["canonical_id"], lk["scope"], json.dumps(lk["filter"]), lk["evidence"]))
        if set(r["frame_type"].split("_")) & {"fusion", "synchro", "xyz", "link"}:
            text = (r["desc"] or "").replace("\r\n", "\n")
            if "[ Monster Effect ]" in text:  # Pendulum Extra Deck monsters: materials follow this header
                text = text.split("[ Monster Effect ]", 1)[1].strip()
            line = text.split("\n")[0]
            comps = parse_materials(line, names)
            if comps:
                mats.append((r["canonical_id"], json.dumps(comps), line))
    with con:
        con.executescript("DELETE FROM effects; DELETE FROM materials; DELETE FROM locks;")
        con.executemany("INSERT INTO effects VALUES (?,?,?,?,?,?,?)", eff)
        con.executemany("INSERT INTO materials VALUES (?,?,?)", mats)
        con.executemany("INSERT INTO locks VALUES (?,?,?,?)", lks)
    return {"cards": len(rows), "effects": len(eff), "materials": len(mats), "locks": len(lks)}
