"""Per-card CPU hints: Master Duel's card-specific AI behaviour, as prior offsets (docs/cpu_handlers.md).

Konami's CPU keeps its card knowledge in per-card branches of its think code (switches on card ID).
Each handler here restates one card's branch as behaviour, keyed by passcode, in the style of
card_tags / hint_priors (MTG Forge's card AI hints):
 - @on_option(*codes): scores each option that names the card (activate, summon, chain, attack,
   effect yes/no). Returns a logit offset: > 0 prefer, < 0 avoid, 0 no opinion.
 - @on_select(*codes): scores each candidate at a selection prompt (targets, costs, materials) while
   that card's effect is choosing.
hint_priors adds the offsets to the turn player's priors (search can still overrule them); respond()
follows them for the other player, so both players' turns use them. The specs the handlers come from,
with their Konami evidence, are in cpu_handler_specs.jsonl; how to refresh them: docs/cpu_handlers.md.
"""
import copy
import os
from dataclasses import dataclass

import numpy as np

import board
import windbot

ENABLED = os.environ.get("YGOSIM_CARD_HANDLERS", "0") != "0"
if ENABLED:  # the env adds Deck / Extra Deck contents to info (goldfish_info.inc) only when asked
    os.environ.setdefault("YGOSIM_CONTEXT", "1")
BATTLECMD, IDLE, EFFECTYN, YESNO, SELECT_CARD, CHAIN, POSITION = 10, 11, 12, 13, 15, 16, 19
TRIBUTE, SELECT_SUM, UNSELECT_CARD = 20, 23, 26
SELECTS = (SELECT_CARD, TRIBUTE, SELECT_SUM, UNSELECT_CARD)
OPTION_MSGS = (BATTLECMD, IDLE, EFFECTYN, YESNO, CHAIN)
# Offsets for the specs' strengths: "always" outweighs the end/phase priors (-3) and a learned weight
# of a few points; "usually" is a default search can overturn; "tiebreak" only orders equals.
ALWAYS, USUALLY, TIEBREAK = 6.0, 2.5, 0.5
_ON_OPTION: dict = {}
_ON_SELECT: dict = {}


def on_option(*codes):
    def register(fn):
        for c in codes:
            _ON_OPTION[c] = fn
        return fn
    return register


def on_select(*codes):
    def register(fn):
        for c in codes:
            _ON_SELECT[c] = fn
        return fn
    return register


@dataclass
class Ctx:
    """One option of one decision, from the deciding player's side."""
    info: dict
    i: int
    o: int          # the option being scored
    msg: int
    act: str        # option letter: v activate, s summon, c special summon, a attack, h from hand...
    card: int       # passcode the option names (the candidate, at selection prompts); 0 if none
    source: int     # passcode of the card whose effect is choosing (selection prompts); 0 if unknown
    player: int
    opp_source: int = 0  # passcode of the card the opponent used last (what a chain responds to); 0 if unknown

    @property
    def opp(self) -> int:
        return 1 - self.player

    @property
    def my_turn(self) -> bool:
        return int(self.info["turn_player"][self.i]) == self.player

    def lp(self, p) -> int:
        return int(self.info["lp_"][self.i][p])

    def monsters(self, p) -> list:
        """(passcode, ATK, DEF, position) of p's Monster Zone cards (board.monsters)."""
        return board.monsters(self.info, self.i, p)

    def field(self, p) -> list:
        """Passcodes of every card p controls; face-down ones negative."""
        return [int(c) for c in self.info["field_codes_"][self.i][p] if c]

    def hand(self, p) -> list:
        return [int(c) for c in self.info["hand_codes_"][self.i][p] if c]

    def printed(self, code) -> tuple:
        return board.card_stats().get(code, (0, 0))

    def public(self, p) -> list:
        """Passcodes in p's GY and face-up banished."""
        return [int(c) for c in self.info["public_codes_"][self.i][p] if c]

    def zone(self, p, code):
        """Monster Zone slot (0-4 main, 5-6 Extra) of p's monster `code`, or None."""
        codes = [abs(int(c)) for c in self.info["field_codes_"][self.i][p][:int(self.info["board_"][self.i][p][0])]]
        slots = [s for s, st in enumerate(self.info["field_stats_"][self.i][p]) if int(st[2])]
        return next((s for c, s in zip(codes, slots) if c == code), None)

    @property
    def location(self) -> str:
        """Where a selection candidate is: h hand, m/s own zones, om/os the opponent's, g GY, r banished,
        x Extra Deck, d Deck (the option string's location letter)."""
        a = self.act
        return "d" if a.isdigit() else a

    def candidate_owner(self):
        """Whose card the candidate is, when it is on the field (None if not on the field)."""
        for p in (self.player, self.opp):
            if self.card and self.card in {abs(c) for c in self.field(p)}:
                return p
        return None


def offsets(info, i, n, id_to_code, source_cid=0, opp_cid=0) -> np.ndarray:
    """Handler offsets for every option of decision i (zeros when no handler has an opinion)."""
    out = np.zeros(n)
    msg = int(info["msg"][i])
    if not ENABLED:
        return out
    if not (msg in OPTION_MSGS or msg in SELECTS):  # position / place / option prompts: executors only
        return out + windbot_offsets(info, i, n, id_to_code)
    code = lambda cid: id_to_code[cid] if 0 < cid < len(id_to_code) else 0
    source = code(int(source_cid))
    select = _ON_SELECT.get(source) if msg in SELECTS else None
    p = int(info["to_play"][i])
    for o in range(n):
        ctx = Ctx(info, i, o, msg, chr(int(info["option_act_"][i][o])), code(int(info["option_card_"][i][o])),
                  source, p, code(int(opp_cid)))
        if msg in SELECTS:
            fns = ([select] if select else []) + GENERIC_SELECT
        else:
            fns = [_ON_OPTION[ctx.card]] if ctx.card in _ON_OPTION else []
        out[o] = sum(fn(ctx) or 0.0 for fn in fns)
    return out + windbot_offsets(info, i, n, id_to_code)


# --- WindBot executors ------------------------------------------------------------------------------
# Each player runs the executor of its deck (DECK_EXECUTORS, by ygo-sim deck name; DEFAULT_EXECUTOR for the
# rest), one instance per env so per-game flags stay with their rollout. windbot.py explains the mapping.
PICK, ALSO, REJECT = USUALLY, TIEBREAK, -USUALLY
DECK_EXECUTORS: dict = {}          # deck name -> windbot.Executor subclass
DEFAULT_EXECUTOR = windbot.Executor  # replaced by the DefaultExecutor port
_decks = ["", ""]
_instances: dict = {}               # (env, player) -> executor
_pending: dict = {}                 # (env, player) -> {option: executor state if that option is chosen}


def set_decks(first, second):
    """Deck names of player 0 and player 1 (game.py)."""
    _decks[0], _decks[1] = first, second
    _instances.clear()


def reset(k=None):
    """Forget executor state (new rollout batch: every env restarts the game)."""
    _instances.clear()
    _pending.clear()


def _executor(i, p):
    ex = _instances.get((i, p))
    if ex is None:
        ex = _instances[(i, p)] = DECK_EXECUTORS.get(_decks[p], DEFAULT_EXECUTOR)()
    return ex


def _card_for(bot, code, act, zone):
    """The bot's Card an option names (code from option_card_), found where the option letter points."""
    places = {"h": bot.Hand, "m": bot.MonsterZone, "s": bot.SpellZone, "g": bot.Graveyard, "r": bot.Banished,
              "x": bot.ExtraDeck}
    first = places.get(act)
    for cards in ([first] if first else []) + [bot.Hand, bot.MonsterZone, bot.SpellZone, bot.Graveyard,
                                               bot.Banished, bot.ExtraDeck, bot.Deck]:
        for c in cards:
            if c is not None and c.Id == code and (not zone or cards is not first or c.Location not in
                                                    (windbot.CardLocation.MonsterZone, windbot.CardLocation.SpellZone)
                                                    or c.Sequence == zone - 1):
                return c
    return windbot.Card(code, windbot.CardLocation.Hand) if code else None


def _matches(pref, card, code):
    if isinstance(pref, windbot.Card):
        return card is not None and pref.Id == card.Id and pref.Controller == card.Controller and             pref.Location == card.Location and pref.Sequence == card.Sequence
    return int(pref) == code


def windbot_offsets(info, i, n, id_to_code) -> np.ndarray:
    out = np.zeros(n)
    msg = int(info["msg"][i])
    if not ENABLED or not n:
        return out
    p = int(info["to_play"][i])
    ex = _executor(i, p)
    turn = int(info["turn"][i])
    if ex._turn != turn:
        ex._turn = turn
        ex.OnNewTurn()
    bot, enemy, duel = windbot.build_views(info, i, p)
    ex.Bot, ex.Enemy, ex.Duel, ex.Util = bot, enemy, duel, windbot.Util(bot, enemy, duel)
    code = lambda o: id_to_code[int(info["option_card_"][i][o])] if 0 < int(info["option_card_"][i][o]) < len(id_to_code) else 0
    acts = [chr(int(a)) for a in info["option_act_"][i][:n]]
    zones = [int(z) for z in info["option_zone_"][i][:n]]
    kinds = info["option_kinds_"][i][:n]
    pending = {}
    if msg in (windbot.IDLE, windbot.BATTLECMD, windbot.CHAIN, windbot.EFFECTYN):
        base = copy.deepcopy(ex._state())
        ranks, rejected = {}, set()
        for o in range(n):
            types = windbot.option_types(msg, acts[o], int(kinds[o]) == 1)
            if not types:
                continue
            card = _card_for(bot, code(o), acts[o], zones[o])
            ex.Card, ex.ActivateDescription = card, windbot.activate_description(int(info["option_desc_"][i][o]), code(o))
            matched = False
            for r, (t, cid, fn) in enumerate(ex.rows):
                if t not in types or (cid is not None and (card is None or not card.IsCode(cid))):
                    continue
                matched = True
                ex.__dict__.update(copy.deepcopy(base))
                if fn is None or fn():
                    ranks[o] = r
                    pending[o] = copy.deepcopy(ex._state())
                    break
            ex.__dict__.update(copy.deepcopy(base))
            if matched and o not in ranks:
                rejected.add(o)
        best = min(ranks, key=ranks.get) if ranks else None
        for o in ranks:
            out[o] = PICK if o == best else ALSO
        for o in rejected:
            out[o] = REJECT
    elif msg in SELECTS and (ex.AI.cards or ex.AI.materials):
        prefs = ex.AI.cards[0] if ex.AI.cards else ex.AI.materials[0]
        for o in range(n):
            card = _card_for(bot, code(o), acts[o], zones[o]) if acts[o] not in "o" else None
            k = next((k for k, pr in enumerate(prefs) if _matches(pr, card, code(o))), None)
            if k is not None:
                out[o] = PICK + TIEBREAK * (len(prefs) - k) / len(prefs)
    elif msg == windbot.POSITION and ex.AI.positions:
        want = windbot._POSITION_LETTER.get(ex.AI.positions[0])
        out[:] = [PICK if a == want else 0.0 for a in acts]
    elif msg == windbot.YESNO and ex.AI.yesno:
        out[:] = [PICK if (int(kinds[o]) != 1) == ex.AI.yesno[0] else 0.0 for o in range(n)]
    elif msg == windbot.SELECT_OPTION and ex.AI.options:
        out[:] = [PICK if o == ex.AI.options[0] else 0.0 for o in range(n)]
    elif msg in (windbot.SELECT_PLACE, windbot.SELECT_DISFIELD) and ex.AI.places:
        out[:] = [PICK if zones[o] and ex.AI.places[0] >> (zones[o] - 1) & 1 else 0.0 for o in range(n)]
    _pending[(i, p)] = (msg, pending)
    return out


def chosen(i, p, o):
    """The player took option o at decision i: keep that option's executor side effects, use up a pre-set
    selection the prompt answered."""
    msg, pending = _pending.pop((i, p), (0, {}))
    ex = _instances.get((i, p))
    if ex is None:
        return
    if o in pending:
        ex.__dict__.update(pending[o])
    queue = {windbot.SELECT_CARD: ex.AI.cards or ex.AI.materials, windbot.TRIBUTE: ex.AI.cards or ex.AI.materials,
             windbot.SELECT_SUM: ex.AI.cards or ex.AI.materials, windbot.POSITION: ex.AI.positions,
             windbot.YESNO: ex.AI.yesno, windbot.SELECT_OPTION: ex.AI.options, windbot.SELECT_PLACE: ex.AI.places,
             windbot.SELECT_DISFIELD: ex.AI.places}.get(msg)
    if queue:
        queue.pop(0)


# --- Handlers ---------------------------------------------------------------------------------------
# One per card (or per group sharing a branch), named after the card, with the spec line it implements.

RAYE, ROZE, HORNET_DRONES, ENGAGE = 26077387, 37351133, 52340444, 63166095


@on_select(ENGAGE)
def engage(ctx):
    """Sky Striker Mobilize - Engage! search: Raye by default; Hornet Drones (which feeds Kagari) when Raye is
    already in hand or not in the Deck. (spec: Engage!, Raye, Hornet Drones; medium)"""
    if ctx.msg != SELECT_CARD or ctx.location != "d":
        return 0.0
    raye_held = RAYE in ctx.hand(ctx.player)
    if ctx.card == RAYE and not raye_held:
        return USUALLY
    if ctx.card == HORNET_DRONES and raye_held:
        return USUALLY
    return 0.0


@on_option(102380)
def lava_golem(ctx):
    """Lava Golem: summon it onto the opponent's field when they control exactly 2 monsters. (spec: medium)"""
    return USUALLY if ctx.msg == IDLE and ctx.act == "c" and len(ctx.monsters(ctx.opp)) == 2 else 0.0


@on_option(25311006)
def triple_tactics_talent(ctx):
    """Triple Tactics Talent: activate as soon as the opponent's Main Phase monster effect makes it live. (medium)"""
    return USUALLY if ctx.act in "v" else 0.0


@on_option(87746184)
def albion(ctx):
    """Albion the Branded Dragon: use its End Phase GY trigger (add/Set a Branded Spell/Trap). (medium)"""
    if ctx.msg in (EFFECTYN, CHAIN) and ctx.act not in ("n", "c") and ctx.card in ctx.public(ctx.player):
        return USUALLY
    return 0.0


def roze_bonus(ctx):
    """Sky Striker Ace - Roze in your GY revives when a monster in the Extra Monster Zone leaves: removal effects
    prefer the opponent's Extra Monster Zone monster. (spec: Roze; medium)"""
    if ctx.msg == SELECT_CARD and ctx.location == "o" and ROZE in ctx.public(ctx.player) and \
            ctx.card not in ctx.field(ctx.player):
        slot = ctx.zone(ctx.opp, ctx.card)
        return TIEBREAK if slot is not None and slot >= 5 else 0.0
    return 0.0


STARDUST, ACCEL_STARDUST, CHAOS_ANGEL, FRAKTALL, KITT = 44508094, 30983281, 22850702, 87209160, 56196385
ATTR_LIGHT, ATTR_DARK = 0x10, 0x20
_CARD_DB = None


def card_db() -> dict:
    """passcode -> (attribute, card text, type)."""
    global _CARD_DB
    if _CARD_DB is None:
        import sqlite3
        db = sqlite3.connect(os.path.expanduser("~/ygo/run/cards.cdb"))
        _CARD_DB = {c: (a, d or "", t) for c, a, d, t in
                    db.execute("select datas.id, attribute, desc, type from datas join texts on datas.id = texts.id")}
    return _CARD_DB


@on_option(STARDUST)
def stardust_dragon(ctx):
    """Stardust Dragon: summon it first when the opponent controls a face-up card that destroys. (spec: medium)"""
    if ctx.msg == IDLE and ctx.act == "c" and any("destroy" in card_db().get(c, (0, ""))[1].lower()
                                                  for c in ctx.field(ctx.opp) if c > 0):
        return USUALLY
    return 0.0


@on_select(ACCEL_STARDUST)
def accel_synchro_stardust(ctx):
    """Accel Synchro Stardust Dragon's Quick Effect Synchro Summon: bring out Stardust Dragon. (spec: medium)"""
    return ALWAYS if ctx.card == STARDUST and ctx.location == "x" else 0.0


@on_select(CHAOS_ANGEL)
def chaos_angel(ctx):
    """Chaos Angel's Synchro Materials: cover LIGHT and DARK. LIGHT first, DARK first when the opponent has a
    monster at least as strong as your best (DARK gives battle protection). (spec: medium)"""
    attr = card_db().get(ctx.card, (0, ""))[0]
    if ctx.msg not in SELECTS or ctx.location not in ("m", "h") or not attr & (ATTR_LIGHT | ATTR_DARK):
        return 0.0
    best_own = max((a for _, a, _, _ in ctx.monsters(ctx.player)), default=0)
    first = ATTR_DARK if max((a for _, a, _, _ in ctx.monsters(ctx.opp)), default=0) >= best_own > 0 else ATTR_LIGHT
    return USUALLY + (TIEBREAK if attr & first else 0.0)


@on_select(FRAKTALL)
def fraktall(ctx):
    """Tri-Brigade Fraktall sends Tri-Brigade Kitt from the Deck (its GY effect then searches). (spec: medium)"""
    return USUALLY if ctx.card == KITT and ctx.location == "d" else 0.0


# Bystial Druiswurm, Golden Cloud Beast - Malong, Witch of the Black Forest: effects when sent from the field to the GY
GY_FODDER = {6637331, 93125329, 78010363}


def fodder_bonus(ctx):
    """Costs, materials and tributes: Konami values sending Druiswurm / Malong from the field (their GY effects).
    (spec: Bystial Druiswurm; medium)"""
    return TIEBREAK if ctx.msg in SELECTS and ctx.location == "m" and ctx.card in GY_FODDER else 0.0


TYPE_MONSTER, TYPE_SPELL = 0x1, 0x2
CALLED_BY_THE_GRAVE, HEAVY_POLY, LITTLE_KNIGHT = 24224830, 58570206, 29301450
SHARK_CANNON, WIDOW_ANCHOR = 51227866, 98338152


def card_type(code) -> int:
    return card_db().get(code, (0, "", 0))[2]


@on_option(CALLED_BY_THE_GRAVE)
def called_by_the_grave(ctx):
    """Called by the Grave: chain it when the opponent activates a monster effect whose same-name copy is in their
    GY; otherwise hold it. (spec: high; Crossout Designator shares the branch)"""
    if ctx.msg != CHAIN or ctx.act in ("c", "n"):
        return 0.0
    live = ctx.opp_source and card_type(ctx.opp_source) & TYPE_MONSTER and ctx.opp_source in ctx.public(ctx.opp)
    return ALWAYS if live else -USUALLY


@on_select(CALLED_BY_THE_GRAVE)
def called_by_the_grave_target(ctx):
    """...and target the GY copy of the monster just activated."""
    return ALWAYS if ctx.opp_source and ctx.card == ctx.opp_source else 0.0


@on_option(HEAVY_POLY)
def heavy_polymerization(ctx):
    """Heavy Polymerization: only with at least 3 materials available, whatever the Fusion needs. (spec: high)"""
    if ctx.act != "v":
        return 0.0
    materials = len(ctx.monsters(ctx.player)) + sum(1 for c in ctx.hand(ctx.player) if card_type(c) & TYPE_MONSTER)
    return -USUALLY if materials < 3 else 0.0


@on_option(LITTLE_KNIGHT)
def little_knight(ctx):
    """S:P Little Knight: its banish needs a face-up monster on the opponent's side to be worth it. (spec: medium)"""
    if ctx.msg in (IDLE, CHAIN) and ctx.act == "v" and not any(pos & 0x5 for _, _, _, pos in ctx.monsters(ctx.opp)):
        return -ALWAYS
    return 0.0


@on_option(SHARK_CANNON, WIDOW_ANCHOR)
def sky_striker_mecha_3_spells(ctx):
    """Shark Cannon / Widow Anchor: hold until 3+ Spells are in your GY (the stronger mode). (spec: medium)"""
    if ctx.act != "v":
        return 0.0
    spells = sum(1 for c in ctx.public(ctx.player) if card_type(c) & TYPE_SPELL)
    return -USUALLY if spells < 3 else 0.0


GENERIC_SELECT = [roze_bonus, fodder_bonus]  # apply at every selection prompt, whatever effect is choosing
