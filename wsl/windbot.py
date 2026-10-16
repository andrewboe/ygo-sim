"""WindBot-style rule layer for the card handlers (docs/windbot_plan.md, phase 1).

Rules ported from WindBot executors (IceYGO/windbot, MIT; see THIRD_PARTY_NOTICES.md) keep WindBot's API
names - Bot / Enemy fields, Duel, Util, AI, Card, ExecutorType, ordered AddExecutor rows - so a ported rule
reads side by side with the C# it came from. Names are WindBot's PascalCase on purpose.

Views are built from the env's info for one decision of one env, from the deciding player's side
(Controller 0 = the bot, 1 = the enemy): the enemy's hand, face-down cards, Deck and Extra Deck stay hidden.
Not available from the env (yet): IsDisabled (always False), equip/target relations, which monsters
already attacked, counters.

How a WindBot executor becomes priors (card_handlers.windbot_offsets):
  WindBot walks its rows in order and takes the first action whose condition returns True. Here, for each
  option, the first row matching (type, card) is evaluated: the option WindBot would take gets PICK, other
  options with a passing row get ALSO, options whose rows all fail get REJECT (WindBot wouldn't do them),
  options without rows get 0 (the search decides). Conditions run once per option on a copy of the
  executor's state; their side effects (flags, AI.SelectCard preferences for the next prompts) are kept
  only for the option the player actually chooses (card_handlers.chosen).
"""
import json
import os
import sqlite3
from dataclasses import dataclass, field

_HERE = os.path.dirname(os.path.abspath(__file__))
_LISTS = json.load(open(os.path.join(_HERE, "windbot_lists.json")))["lists"]
LIST = {k: set(v) for k, v in _LISTS.items()}


class CardLocation:
    Deck, Hand, MonsterZone, SpellZone, Grave, Removed, Extra, Overlay = 0x1, 0x2, 0x4, 0x8, 0x10, 0x20, 0x40, 0x80
    Onfield = 0x0C
    FieldZone, PendulumZone = 0x100, 0x200


class CardPosition:
    FaceUpAttack, FaceDownAttack, FaceUpDefence, FaceDownDefence = 0x1, 0x2, 0x4, 0x8
    FaceUp, FaceDown, Attack, Defence = 0x5, 0xA, 0x3, 0xC


class CardType:
    Monster, Spell, Trap = 0x1, 0x2, 0x4
    Normal, Effect, Fusion, Ritual, TrapMonster = 0x10, 0x20, 0x40, 0x80, 0x100
    Spirit, Union, Gemini, Tuner, Synchro, Token = 0x200, 0x400, 0x800, 0x1000, 0x2000, 0x4000
    QuickPlay, Continuous, Equip, Field, Counter, Flip = 0x10000, 0x20000, 0x40000, 0x80000, 0x100000, 0x200000
    Toon, Xyz, Pendulum, SpSummon, Link = 0x400000, 0x800000, 0x1000000, 0x2000000, 0x4000000


class CardAttribute:
    Earth, Water, Fire, Wind, Light, Dark, Divine = 0x1, 0x2, 0x4, 0x8, 0x10, 0x20, 0x40


class DuelPhase:
    Draw, Standby, Main1, BattleStart, BattleStep, Damage, DamageCal, Battle, Main2, End = \
        0x1, 0x2, 0x4, 0x8, 0x10, 0x20, 0x40, 0x80, 0x100, 0x200


class ExecutorType:
    Summon, SpSummon, Repos, MonsterSet, SpellSet, Activate, SummonOrSet = range(7)
    GoToBattlePhase, GoToMainPhase2, GoToEndPhase = 7, 8, 9


_DB = None


def card_data(code) -> tuple:
    """passcode -> (alias, setcode, type, level, attribute, race, atk, def) from cards.cdb."""
    global _DB
    if _DB is None:
        db = sqlite3.connect(os.path.expanduser("~/ygo/run/cards.cdb"))
        _DB = {r[0]: r[1:] for r in db.execute("select id, alias, setcode, type, level, attribute, race, atk, def from datas")}
    return _DB.get(code, (0, 0, 0, 0, 0, 0, 0, 0))


@dataclass(eq=False)
class Card:
    """ClientCard: a card as the bot sees it. Id 0 = unknown (hidden)."""
    Id: int
    Location: int
    Sequence: int = 0
    Controller: int = 0
    Position: int = CardPosition.FaceUpAttack
    Attack: int = 0
    Defense: int = 0
    Level: int = 0
    OverlayCount: int = 0

    def __post_init__(self):
        alias, setcode, self.Type, level, self.Attribute, self.Race, atk, dfn = card_data(self.Id)
        self.Alias = alias
        self.Setcodes = [(setcode >> (16 * k)) & 0xFFFF for k in range(4) if (setcode >> (16 * k)) & 0xFFFF]
        if self.Location not in (CardLocation.MonsterZone,):  # stats off the field: the printed ones
            self.Attack, self.Defense, self.Level = max(atk, 0), max(dfn, 0), level & 0xFF
        self.RealPower = self.Attack      # battle power the battle rules adjust (WindBot's RealPower)
        self.IsLastAttacker = False
        self.IsSpecialSummoned = False    # not exposed by the env
        self.LastLocation = 0             # not exposed by the env

    @property
    def Overlays(self) -> list:
        return [0] * self.OverlayCount  # material codes aren't exposed, only how many

    def IsCode(self, *ids) -> bool:
        flat = [i for x in ids for i in (x if isinstance(x, (list, tuple, set)) else [x])]
        return bool(self.Id) and (self.Id in flat or (self.Alias and self.Alias in flat))

    def IsOriginalCode(self, id_) -> bool:
        return self.Id == id_ or self.Alias == id_

    def HasType(self, t) -> bool:
        return bool(self.Type & t)

    def IsMonster(self):
        return self.HasType(CardType.Monster)

    def IsSpell(self):
        return self.HasType(CardType.Spell)

    def IsTrap(self):
        return self.HasType(CardType.Trap)

    def IsFaceup(self):
        return bool(self.Position & CardPosition.FaceUp)

    def IsFacedown(self):
        return bool(self.Position & CardPosition.FaceDown)

    def IsAttack(self):
        return bool(self.Position & CardPosition.Attack)

    def IsDefense(self):
        return bool(self.Position & CardPosition.Defence)

    def HasPosition(self, p):
        return bool(self.Position & p)

    def HasAttribute(self, a):
        return bool(self.Attribute & a)

    def HasRace(self, r):
        return bool(self.Race & r)

    def HasSetcode(self, setcode) -> bool:
        """ygopro set-code match: same base series (low 12 bits) and every sub-series bit of `setcode`."""
        return any((s & 0xFFF) == (setcode & 0xFFF) and (s & setcode) == setcode for s in self.Setcodes)

    def HasXyzMaterial(self, count=1, cardid=None) -> bool:
        return self.OverlayCount >= count  # cardid can't be checked: material codes aren't exposed

    def IsDisabled(self) -> bool:
        return False  # not exposed by the env

    def IsFloodgate(self):
        return self.Id in LIST["Floodgate"]

    def IsMonsterDangerous(self):
        return self.Id in LIST["DangerousMonster"]

    def IsMonsterInvincible(self):
        return self.Id in LIST["InvincibleBotMonster" if self.Controller == 0 else "InvincibleEnemyMonster"]

    def IsMonsterAttackWhileInDefPos(self):
        return self.IsFaceup() and self.IsDefense() and self.Id in LIST["DefenseAttackMonster"]

    def IsShouldNotBeSpellTrapTarget(self):
        return self.IsFaceup() and self.Id in LIST["ShouldNotBeSpellTrapTarget"]

    def IsShouldNotBeMonsterTarget(self):
        return self.IsFaceup() and self.Id in LIST["ShouldNotBeMonsterTarget"]

    def IsMonsterHasPreventActivationEffectInBattle(self):
        return self.Id in LIST["PreventActivationEffectInBattle"]

    def IsMonsterShouldBeDisabledBeforeItUseEffect(self):
        return self.IsFaceup() and self.Id in LIST["ShouldBeDisabledBeforeItUseEffectMonster"]

    def IsExtraCard(self):
        return self.HasType(CardType.Fusion | CardType.Synchro | CardType.Xyz | CardType.Link)

    def IsCanRevive(self):
        return self.IsMonster()  # summoning conditions aren't exposed

    def IsShouldNotBeTarget(self):
        return self.IsFaceup() and not self.HasType(CardType.Normal) and self.Id in LIST["ShouldNotBeTarget"]

    def GetDefensePower(self) -> int:
        """WindBot's 'power': ATK, or DEF for monsters that attack from Defense Position."""
        if self.IsMonsterAttackWhileInDefPos() and self.Id not in LIST["DefenseAttackWithAttackValueMonster"]:
            return self.Defense
        return self.Attack

    GetAttackPower = GetDefensePower


@dataclass
class Field:
    """ClientField: one player's cards (hidden ones only for the enemy)."""
    Hand: list = field(default_factory=list)
    MonsterZone: list = field(default_factory=lambda: [None] * 7)
    SpellZone: list = field(default_factory=lambda: [None] * 8)
    Graveyard: list = field(default_factory=list)
    Banished: list = field(default_factory=list)
    Deck: list = field(default_factory=list)
    ExtraDeck: list = field(default_factory=list)
    LifePoints: int = 8000

    # --- zone contents
    def GetMonsters(self):
        return [c for c in self.MonsterZone if c is not None]

    def GetSpells(self):
        return [c for c in self.SpellZone if c is not None]

    def GetFaceupMonsters(self):
        return [c for c in self.GetMonsters() if c.IsFaceup()]

    def GetMonstersInMainZone(self):
        return [c for c in self.MonsterZone[:5] if c is not None]

    def GetMonstersInExtraZone(self):
        return [c for c in self.MonsterZone[5:] if c is not None]

    def GetGraveyardMonsters(self):
        return [c for c in self.Graveyard if c.IsMonster()]

    def GetGraveyardSpells(self):
        return [c for c in self.Graveyard if c.IsSpell()]

    # --- counts
    def GetMonsterCount(self):
        return len(self.GetMonsters())

    def GetMonstersExtraZoneCount(self):
        return len(self.GetMonstersInExtraZone())

    def GetSpellCount(self):
        return len(self.GetSpells())

    def GetSpellCountWithoutField(self):
        return len([c for c in self.SpellZone[:5] if c is not None])

    def GetHandCount(self):
        return len(self.Hand)

    def GetFieldCount(self):
        return self.GetMonsterCount() + self.GetSpellCount()

    def GetFieldHandCount(self):
        return self.GetFieldCount() + self.GetHandCount()

    def GetCardCountInDeck(self, id_):
        return sum(1 for c in self.Deck if c.IsCode(id_))

    # --- membership (ids: one id or a list)
    @staticmethod
    def _has(cards, ids, faceup=False):
        return any(c is not None and c.IsCode(ids) and (not faceup or c.IsFaceup()) for c in cards)

    def HasInHand(self, ids):
        return self._has(self.Hand, ids)

    def HasInMonstersZone(self, ids, notDisabled=False, hasXyzMaterial=False, faceUp=False):
        return any(c is not None and c.IsCode(ids) and (not faceUp or c.IsFaceup()) and
                   (not hasXyzMaterial or c.OverlayCount) for c in self.MonsterZone)

    def HasInSpellZone(self, ids, notDisabled=False, faceUp=False):
        return self._has(self.SpellZone, ids, faceUp)

    def HasInGraveyard(self, ids):
        return self._has(self.Graveyard, ids)

    def HasInBanished(self, ids):
        return self._has(self.Banished, ids)

    def HasInExtra(self, ids):
        return self._has(self.ExtraDeck, ids)

    def HasInDeck(self, ids):
        return self._has(self.Deck, ids)

    def HasInHandOrInSpellZone(self, ids):
        return self.HasInHand(ids) or self.HasInSpellZone(ids)

    def HasInHandOrHasInMonstersZone(self, ids):
        return self.HasInHand(ids) or self.HasInMonstersZone(ids)

    def HasInHandOrInGraveyard(self, ids):
        return self.HasInHand(ids) or self.HasInGraveyard(ids)

    def HasInMonstersZoneOrInGraveyard(self, ids):
        return self.HasInMonstersZone(ids) or self.HasInGraveyard(ids)

    def HasInSpellZoneOrInGraveyard(self, ids):
        return self.HasInSpellZone(ids) or self.HasInGraveyard(ids)

    def HasInGraveyardOrInBanished(self, ids):
        return self.HasInGraveyard(ids) or self.HasInBanished(ids)

    def HasInHandOrInMonstersZoneOrInGraveyard(self, ids):
        return self.HasInHand(ids) or self.HasInMonstersZone(ids) or self.HasInGraveyard(ids)

    def HasInHandOrInSpellZoneOrInGraveyard(self, ids):
        return self.HasInHand(ids) or self.HasInSpellZone(ids) or self.HasInGraveyard(ids)

    def HasInPendulumZone(self, ids, faceUp=False):
        return any(c is not None and c.IsCode(ids) and c.HasType(CardType.Pendulum) and (not faceUp or c.IsFaceup())
                   for c in (self.SpellZone[0], self.SpellZone[4]))

    def HasAttackingMonster(self):
        return any(c.IsAttack() for c in self.GetMonsters())


class ChainInfo:
    """One chain link: the card (RelatedCard), who activated it (ActivatePlayer), its first target."""

    def __init__(self, card, target=None, negated=False):
        self.RelatedCard, self.ActivatePlayer, self.Negated = card, card.Controller, negated
        self.Targets = [target] if target is not None else []

    def IsCode(self, *ids):
        return self.RelatedCard.IsCode(*ids)

    IsActivateCode = IsCode


@dataclass
class DuelView:
    """Duel: whose turn, phase, the chain being built and what was just summoned (players relative)."""
    Player: int = 0                 # turn player (0 = bot)
    Phase: int = DuelPhase.Main1
    Turn: int = 1
    CurrentChain: list = field(default_factory=list)   # Card per link, link 1 first
    ChainTargets: list = field(default_factory=list)   # Card per target of the latest link
    LastSummonedCards: list = field(default_factory=list)
    LastSummonPlayer: int = -1
    CurrentChainInfo: list = field(default_factory=list)  # ChainInfo per link
    ResolvedThisTurn: list = field(default_factory=list)  # ChainInfo per resolved link (OnChainSolved)

    @property
    def SummoningCards(self):
        return []  # summons in progress aren't exposed separately from LastSummonedCards

    @property
    def LastChainPlayer(self) -> int:
        return self.CurrentChain[-1].Controller if self.CurrentChain else -1

    @property
    def MainPhase(self):
        return self.Phase in (DuelPhase.Main1, DuelPhase.Main2)

    def GetCurrentChainCard(self):  # the chain link being added (WindBot: Duel.CurrentChain last)
        return self.CurrentChain[-1] if self.CurrentChain else None


class Util:
    """AIUtil: the helpers WindBot executors use most."""

    def __init__(self, bot, enemy, duel):
        self.Bot, self.Enemy, self.Duel = bot, enemy, duel

    @staticmethod
    def GetStringId(id_, option):
        return id_ * 16 + option

    def IsTurn1OrMain2(self):
        return self.Duel.Turn == 1 or self.Duel.Phase == DuelPhase.Main2

    def GetLastChainCard(self):
        return self.Duel.CurrentChain[-1] if self.Duel.CurrentChain else None

    def ChainContainsCard(self, ids):
        return any(c.IsCode(ids) for c in self.Duel.CurrentChain)

    def ChainCountPlayer(self, player):
        return sum(1 for c in self.Duel.CurrentChain if c.Controller == player)

    def ChainContainPlayer(self, player):
        return any(c.Controller == player for c in self.Duel.CurrentChain)

    def HasChainedTrap(self, player):
        return any(c.Controller == player and c.HasType(CardType.Trap) for c in self.Duel.CurrentChain)

    def IsChainTarget(self, card):
        return card is not None and any(t.IsCode(card.Id) and t.Controller == card.Controller
                                        for t in self.Duel.ChainTargets)

    def IsChainTargetOnly(self, card):
        return len(self.Duel.ChainTargets) == 1 and self.IsChainTarget(card)

    def GetTotalAttackingMonsterAttack(self, player):
        f = self.Bot if player == 0 else self.Enemy
        return sum(m.GetAttackPower() for m in f.GetMonsters() if m.IsAttack() or m.IsMonsterAttackWhileInDefPos())

    def GetBestPower(self, f, onlyATK=False):
        powers = [c.GetDefensePower() for c in f.GetMonsters() if not onlyATK or c.IsAttack()]
        return max(powers) if powers else -1

    def GetBestAttack(self, f):
        return self.GetBestPower(f, True)

    def IsOneEnemyBetterThanValue(self, value, onlyATK):
        return any(c.GetDefensePower() > value and (not onlyATK or c.IsAttack()) for c in self.Enemy.GetMonsters())

    def IsAllEnemyBetterThanValue(self, value, onlyATK):
        m = self.Enemy.GetMonsters()
        return bool(m) and all(c.GetDefensePower() > value and (not onlyATK or c.IsAttack()) for c in m)

    def IsOneEnemyBetter(self, onlyATK=False):
        return self.IsOneEnemyBetterThanValue(self.GetBestPower(self.Bot, onlyATK), onlyATK)

    def IsAllEnemyBetter(self, onlyATK=False):
        return self.IsAllEnemyBetterThanValue(self.GetBestPower(self.Bot, onlyATK), onlyATK)

    def GetBestBotMonster(self, onlyATK=False):
        m = [c for c in self.Bot.GetMonsters() if not onlyATK or c.IsAttack()]
        return max(m, key=lambda c: c.GetDefensePower(), default=None)

    def GetWorstBotMonster(self, onlyATK=False):
        m = [c for c in self.Bot.GetMonsters() if not onlyATK or c.IsAttack()]
        return min(m, key=lambda c: c.GetDefensePower(), default=None)

    def GetWorstEnemyMonster(self, onlyATK=False):
        m = [c for c in self.Enemy.GetMonsters() if not onlyATK or c.IsAttack()]
        return min(m, key=lambda c: c.GetDefensePower(), default=None)

    def GetOneEnemyBetterThanValue(self, value, onlyATK=False, canBeTarget=False):
        return next((c for c in self.Enemy.GetMonsters() if c.GetDefensePower() >= value and
                     (not onlyATK or c.IsAttack()) and (not canBeTarget or not c.IsShouldNotBeTarget())), None)

    def GetOneEnemyBetterThanMyBest(self, onlyATK=False, canBeTarget=False):
        return self.GetOneEnemyBetterThanValue(self.GetBestPower(self.Bot, onlyATK), onlyATK, canBeTarget)

    def _first(self, cards, test, canBeTarget):
        return next((c for c in cards if c.IsFaceup() and test(c) and (not canBeTarget or not c.IsShouldNotBeTarget())), None)

    def GetProblematicEnemyMonster(self, attack=0, canBeTarget=False):
        m = self.Enemy.GetMonsters()
        card = (self._first(m, Card.IsFloodgate, canBeTarget) or self._first(m, Card.IsMonsterDangerous, canBeTarget)
                or self._first(m, Card.IsMonsterInvincible, canBeTarget))
        return card or self.GetOneEnemyBetterThanValue(attack or self.GetBestAttack(self.Bot), True, canBeTarget)

    def GetProblematicEnemySpell(self):
        return self._first(self.Enemy.GetSpells(), Card.IsFloodgate, False)

    def GetProblematicEnemyCard(self, attack=0, canBeTarget=False):
        card = self._first(self.Enemy.GetMonsters(), Card.IsFloodgate, canBeTarget) or self.GetProblematicEnemySpell()
        return card or self.GetProblematicEnemyMonster(attack, canBeTarget)

    def GetBestEnemyMonster(self, onlyFaceup=False, canBeTarget=False):
        card = self.GetProblematicEnemyMonster(0, canBeTarget)
        if card:
            return card
        up = [c for c in self.Enemy.GetMonsters() if c.IsFaceup() and (not canBeTarget or not c.IsShouldNotBeTarget())]
        if up:
            return max(up, key=lambda c: c.Attack)
        if not onlyFaceup:
            return next((c for c in self.Enemy.GetMonsters() if not canBeTarget or not c.IsShouldNotBeTarget()), None)
        return None

    def GetBestEnemySpell(self, onlyFaceup=False):
        card = self.GetProblematicEnemySpell()
        if card:
            return card
        spells = self.Enemy.GetSpells()
        card = next((c for c in spells if c.IsFaceup() and c.HasType(CardType.Continuous | CardType.Field)), None)
        return card or (spells[0] if spells and not onlyFaceup else None)

    def GetBestEnemyCard(self, onlyFaceup=False, canBeTarget=False):
        return self.GetBestEnemyMonster(onlyFaceup, canBeTarget) or self.GetBestEnemySpell(onlyFaceup)


class AIRecorder:
    """AI: the selections an executor pre-sets for the prompts that follow its action (AI.SelectCard etc.).
    Each queue holds preference lists (ids or Cards, best first) for the next prompts of that kind."""

    def __init__(self):
        self.cards = []        # SelectCard / SelectNextCard / SelectThirdCard, in prompt order
        self.materials = []    # SelectMaterials
        self.places = []       # SelectPlace (zone bitmasks)
        self.positions = []    # SelectPosition
        self.yesno = []        # SelectYesNo
        self.options = []      # SelectOption

    @staticmethod
    def _prefs(args):
        out = []
        for a in args:
            out.extend(a if isinstance(a, (list, tuple)) else [a])
        return out

    def SelectCard(self, *args):
        self.cards[:1] = [self._prefs(args)]

    def SelectNextCard(self, *args):
        while len(self.cards) < 1:
            self.cards.append([])
        self.cards[1:2] = [self._prefs(args)]

    def SelectThirdCard(self, *args):
        while len(self.cards) < 2:
            self.cards.append([])
        self.cards[2:3] = [self._prefs(args)]

    def SelectMaterials(self, *args):
        self.materials.append(self._prefs(args))

    def SelectPlace(self, zones):
        self.places.append(zones)

    def SelectPosition(self, pos):
        self.positions.append(pos)

    def SelectYesNo(self, yes):
        self.yesno.append(bool(yes))

    def SelectOption(self, option):
        self.options.append(option)

    def Clear(self):
        """GameAI.ClearSelections: WindBot drops unused selections at each new phase and when a chain ends."""
        for queue in (self.cards, self.materials, self.places, self.positions, self.yesno, self.options):
            queue.clear()


# --- CardContainer queries (WindBot's extension methods on card lists) ----------------------------------

def GetHighestAttackMonster(cards, canBeTarget=False):
    up = [c for c in cards if c is not None and c.IsFaceup() and (not canBeTarget or not c.IsShouldNotBeTarget())]
    return max(up, key=lambda c: c.Attack, default=None)


def GetFloodgate(cards, canBeTarget=False):
    return next((c for c in cards if c is not None and c.IsFaceup() and c.IsFloodgate() and
                 (not canBeTarget or not c.IsShouldNotBeTarget())), None)


def GetShouldBeDisabledBeforeItUseEffectMonster(cards, canBeTarget=True):
    return next((c for c in cards if c is not None and c.IsMonsterShouldBeDisabledBeforeItUseEffect() and
                 (not canBeTarget or not c.IsShouldNotBeTarget())), None)


# --- Views from env info ------------------------------------------------------------------------------

def _cards(codes, location, controller, hide=False):
    out = []
    for c in codes:
        c = int(c)
        if c:
            out.append(Card(0 if (hide or c < 0) and controller == 1 else abs(c), location, Controller=controller,
                            Position=CardPosition.FaceDown if c < 0 else CardPosition.FaceUpAttack))
    return out


def build_views(info, i, player):
    """(Bot, Enemy, Duel) for decision i from `player`'s side. Needs the context fields (YGOSIM_CONTEXT=1)."""
    fields = []
    for rel, p in ((0, player), (1, 1 - player)):
        f = Field(LifePoints=int(info["lp_"][i][p]))
        zc = info["zone_cards_"][i][p]
        for row in range(16):
            code, pos, atk, dfn, lvl, ov = (int(x) for x in zc[row])
            if not code:
                continue
            hidden = rel == 1 and pos & CardPosition.FaceDown
            loc = CardLocation.MonsterZone if row < 8 else CardLocation.SpellZone
            seq = row if row < 8 else row - 8
            c = Card(0 if hidden else code, loc, seq, rel, pos, 0 if hidden else atk, 0 if hidden else dfn,
                     0 if hidden else lvl, ov)
            if row < 7:
                f.MonsterZone[seq] = c
            elif row >= 8:
                f.SpellZone[seq] = c
        hand = [int(c) for c in info["hand_codes_"][i][p] if c]
        f.Hand = _cards(hand, CardLocation.Hand, rel, hide=True)
        f.Graveyard = _cards(info["grave_codes_"][i][p], CardLocation.Grave, rel)
        f.Banished = _cards(info["banished_codes_"][i][p], CardLocation.Removed, rel)
        if rel == 0:  # own Deck / Extra Deck only (present when the env runs with YGOSIM_CONTEXT)
            f.Deck = _cards(info["deck_codes_"][i][p], CardLocation.Deck, 0)
            f.ExtraDeck = [Card(abs(int(c)), CardLocation.Extra, Controller=0,
                                Position=CardPosition.FaceUp if c < 0 else CardPosition.FaceDown)
                           for c in info["extra_codes_"][i][p] if c]
        fields.append(f)
    bot, enemy = fields
    rel = lambda p: 0 if int(p) == player else 1
    on_field = {(c.Id, c.Controller): c for f in fields for c in f.GetMonsters() + f.GetSpells() if c.Id}

    def find(code):
        return on_field.get((code, 0)) or on_field.get((code, 1)) or Card(code, CardLocation.Onfield, Controller=-1)

    links = [(int(code), int(ctl), int(loc), int(tgt)) for code, ctl, loc, tgt in info["chain_"][i] if code]
    chain = [Card(code, loc, Controller=rel(ctl)) for code, ctl, loc, _ in links]
    chain_info = [ChainInfo(card, find(tgt) if tgt else None) for card, (_, _, _, tgt) in zip(chain, links)]
    resolved = [ChainInfo(Card(int(code), CardLocation.Onfield, Controller=rel(ctl)), Card(int(tgt), CardLocation.Onfield)
                          if tgt else None, bool(neg)) for code, ctl, neg, tgt in info["resolved_"][i] if code]
    targets = []
    for code in info["chain_targets_"][i]:
        if code:
            card = on_field.get((int(code), 0)) or on_field.get((int(code), 1)) or Card(int(code), CardLocation.Onfield, Controller=-1)
            targets.append(card)
    summoned = [Card(int(code), CardLocation.MonsterZone, Controller=rel(ctl)) for code, ctl in info["summoned_"][i] if code]
    duel = DuelView(Player=rel(info["turn_player"][i]), Phase=int(info["phase"][i]) or DuelPhase.Main1,
                    Turn=int(info["turn"][i]), CurrentChain=chain, ChainTargets=targets, LastSummonedCards=summoned,
                    LastSummonPlayer=summoned[-1].Controller if summoned else -1,
                    CurrentChainInfo=chain_info, ResolvedThisTurn=resolved)
    return bot, enemy, duel


def activate_description(raw, card_code) -> int:
    """WindBot's ActivateDescription (GetStringId(card, n) = card * 16 + n) from the env's 32-bit desc: EDOPro's
    code << 20 | n with the code cut to its low 12 bits. A string of another card (code bits don't match the
    option's card) is -1; a system string (no code part) is returned as is."""
    d = raw & 0xFFFFFFFF
    index, code_bits = d & 0xFFFFF, d >> 20
    if not code_bits:
        return index
    return card_code * 16 + index if card_code and (card_code & 0xFFF) == code_bits else -1


# --- Executors -----------------------------------------------------------------------------------------

class Executor:
    """A WindBot deck executor. Subclasses add rows in __init__ (AddExecutor, in WindBot's order) and keep
    their own per-game flags as attributes; OnNewTurn resets per-turn flags, as in WindBot."""

    def __init__(self):
        self.rows = []
        self.Bot = self.Enemy = self.Duel = self.Util = self.Card = None
        self.AI = AIRecorder()
        self.ActivateDescription = -1
        self._turn = None

    def AddExecutor(self, type_, card_id=None, func=None):
        self.rows.append((type_, card_id, func))

    def OnNewTurn(self):
        pass

    # state that conditions may change (flags, AI preferences), copied around dry runs
    def _state(self):
        return {k: v for k, v in self.__dict__.items() if k not in ("rows", "Bot", "Enemy", "Duel", "Util", "Card")}


# Which executor types an option can be, by (msg, option letter). CHAIN / effect yes-no: any non-pass option.
BATTLECMD, IDLE, EFFECTYN, YESNO, SELECT_OPTION, SELECT_CARD, CHAIN = 10, 11, 12, 13, 14, 15, 16
SELECT_PLACE, POSITION, TRIBUTE, SELECT_DISFIELD, SELECT_SUM, UNSELECT_CARD = 18, 19, 20, 24, 23, 26
_IDLE_TYPES = {"s": (ExecutorType.Summon, ExecutorType.SummonOrSet), "c": (ExecutorType.SpSummon,),
               "r": (ExecutorType.Repos,), "m": (ExecutorType.MonsterSet, ExecutorType.SummonOrSet),
               "t": (ExecutorType.SpellSet,), "v": (ExecutorType.Activate,),
               "b": (ExecutorType.GoToBattlePhase,), "e": (ExecutorType.GoToEndPhase,)}
_BATTLE_TYPES = {"v": (ExecutorType.Activate,), "m": (ExecutorType.GoToMainPhase2,), "e": (ExecutorType.GoToEndPhase,)}
_POSITION_LETTER = {CardPosition.FaceUpAttack: "1", CardPosition.FaceDownAttack: "2",
                    CardPosition.FaceUpDefence: "3", CardPosition.FaceDownDefence: "4"}


def option_types(msg, act, is_pass):
    if msg == IDLE:
        return _IDLE_TYPES.get(act, ())
    if msg == BATTLECMD:
        return _BATTLE_TYPES.get(act, ())
    if msg in (CHAIN, EFFECTYN) and not is_pass:
        return (ExecutorType.Activate,)
    return ()
