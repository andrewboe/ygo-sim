"""WindBot-style rule layer for the card handlers (docs/windbot_plan.md).

Rules ported from WindBot executors (IceYGO/windbot, MIT; see THIRD_PARTY_NOTICES.md) keep WindBot's API
names - Bot / Enemy fields, Duel, Util, AI, Card, ExecutorType, ordered AddExecutor rows - so a ported rule
reads side by side with the C# it came from. Names are WindBot's PascalCase on purpose.

This module is WindBot's data model: ClientCard (Card), ClientField (Field), Duel (DuelView), ChainInfo,
MainPhase / BattlePhase, AIUtil (Util), CardSelector, the CardContainer / CardExtension helpers, the enums
and the Executor base class with WindBot's virtual defaults. windbot_gameai.py is GameAI (how answers become
choices, the AI.Select* queues, message callbacks); windbot_default.py is DefaultExecutor.

Views are built from the env's info for one decision of one env, from the deciding player's side
(Controller 0 = the bot, 1 = the enemy): the enemy's hand, face-down cards, Deck and Extra Deck stay hidden.
Cards are rebuilt every decision, so a Card is identified by (Id, Controller, Location, Sequence) where WindBot
keeps the same object: `card in list` and `==` compare that key. Not available from the env: IsDisabled
(always False), equip / target relations, which monsters already attacked, counters, announces.
"""
import json
import os
import random
import sqlite3

_HERE = os.path.dirname(os.path.abspath(__file__))
_LISTS = json.load(open(os.path.join(_HERE, "windbot_lists.json")))["lists"]
LIST = {k: set(v) for k, v in _LISTS.items() if isinstance(v, list)}
Rand = random.Random(0)  # WindBot's Program.Rand


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


class CardRace:
    Warrior, SpellCaster, Fairy, Fiend, Zombie, Machine, Aqua, Pyro = 0x1, 0x2, 0x4, 0x8, 0x10, 0x20, 0x40, 0x80
    Rock, WindBeast, Plant, Insect, Thunder, Dragon, Beast, BeastWarrior = \
        0x100, 0x200, 0x400, 0x800, 0x1000, 0x2000, 0x4000, 0x8000
    Dinosaur, Fish, SeaSerpent, Reptile, Psycho, DivineBeast, CreatorGod, Wyrm = \
        0x10000, 0x20000, 0x40000, 0x80000, 0x100000, 0x200000, 0x400000, 0x800000
    Cyberse, Illusion = 0x1000000, 0x2000000


class DuelPhase:
    Draw, Standby, Main1, BattleStart, BattleStep, Damage, DamageCal, Battle, Main2, End = \
        0x1, 0x2, 0x4, 0x8, 0x10, 0x20, 0x40, 0x80, 0x100, 0x200


class ExecutorType:
    Summon, SpSummon, Repos, MonsterSet, SpellSet, Activate, SummonOrSet = range(7)
    GoToBattlePhase, GoToMainPhase2, GoToEndPhase = 7, 8, 9


class HintMsg:
    Release, Discard, Destroy, Remove, ToGrave, ReturnToHand, AddToHand, ToDeck = 500, 501, 502, 503, 504, 505, 506, 507
    Summon, SpSummon, Set, FusionMaterial, SynchroMaterial, XyzMaterial = 508, 509, 510, 511, 512, 513
    Faceup, Facedown, Attack, Defense, Equip, RemoveXyz, Control, DestroyReplace = 514, 515, 516, 517, 518, 519, 520, 521
    FaceupAttack, FaceupDefense, FacedownAttack, FacedownDefense = 522, 523, 524, 525
    Confirm, ToField, PosChange, Self, Oppo, Tribute, DeattachFrom, LinkMaterial = 526, 527, 528, 529, 530, 531, 532, 533
    AttackTarget, Effect, Target, Coin, Dice, CardType, Option, ResolveEffect = 549, 550, 551, 552, 553, 554, 555, 556
    Select, Position, Attribute, Race, Code, Number, LvRank, ResolveCard = 560, 561, 562, 563, 564, 565, 567, 568
    Zone, DisableZone, ToZone, Counter, Disable, OperateCard = 569, 570, 571, 572, 573, 574
    RITUAL, FUSION, SYNCHRO, XYZ, PENDULUM = 1057, 1056, 1063, 1073, 1074


class Zones:
    z0, z1, z2, z3, z4, z5, z6 = 0x1, 0x2, 0x4, 0x8, 0x10, 0x20, 0x40
    FieldZone, MonsterZones, MainMonsterZones, ExtraMonsterZones = 0x20, 0x7f, 0x1f, 0x60
    SpellZones, PendulumZones, LinkedZones, NotLinkedZones = 0x1f, 0x3, 0x10000, 0x20000


_DB = None
_NAMES = None
_TEXTS = None


def card_data(code) -> tuple:
    """passcode -> (alias, setcode, type, level, attribute, race, atk, def) from cards.cdb."""
    global _DB
    if _DB is None:
        db = sqlite3.connect(os.path.expanduser("~/ygo/run/cards.cdb"))
        _DB = {r[0]: r[1:] for r in db.execute("select id, alias, setcode, type, level, attribute, race, atk, def from datas")}
    return _DB.get(code, (0, 0, 0, 0, 0, 0, 0, 0))


def card_name(code) -> str:
    global _NAMES
    if _NAMES is None:
        db = sqlite3.connect(os.path.expanduser("~/ygo/run/cards.cdb"))
        _NAMES = dict(db.execute("select id, name from texts"))
    return _NAMES.get(code, "")


def card_text(code) -> str:
    global _TEXTS
    if _TEXTS is None:
        db = sqlite3.connect(os.path.expanduser("~/ygo/run/cards.cdb"))
        _TEXTS = dict(db.execute("select id, desc from texts"))
    return _TEXTS.get(code, "") or ""


class NamedCard:
    """The printed card (WindBot's NamedCard, a card's .Data)."""

    def __init__(self, code):
        self.Id = code
        self.Alias, self.Setcode, self.Type, level, self.Attribute, self.Race, atk, dfn = card_data(code)
        self.Level, self.LScale, self.RScale = level & 0xFF, (level >> 24) & 0xFF, (level >> 16) & 0xFF
        self.Attack, self.Defense = max(atk, 0), max(dfn, 0)
        self.Name = card_name(code)

    @property
    def Description(self):
        return card_text(self.Id)

    def HasType(self, t):
        return bool(self.Type & t)

    def IsExtraCard(self):
        return self.HasType(CardType.Fusion | CardType.Synchro | CardType.Xyz | CardType.Link)

    _cache = {}

    @staticmethod
    def Get(code):
        if not code or not card_data(code)[2]:
            return None
        data = NamedCard._cache.get(code)
        if data is None:
            data = NamedCard._cache[code] = NamedCard(code)
        return data


class Card:
    """ClientCard: a card as the bot sees it. Id 0 = unknown (hidden)."""

    def __init__(self, Id, Location, Sequence=0, Controller=0, Position=CardPosition.FaceUpAttack, Attack=None,
                 Defense=None, Level=None, OverlayCount=0):
        self.Id, self.Location, self.Sequence, self.Controller, self.Position = Id, Location, Sequence, Controller, Position
        alias, setcode, self.Type, level, self.Attribute, self.Race, atk, dfn = card_data(Id)
        self.Alias = alias
        self.Setcodes = [(setcode >> (16 * k)) & 0xFFFF for k in range(4) if (setcode >> (16 * k)) & 0xFFFF]
        self.Data = NamedCard.Get(Id)
        self.Name = self.Data.Name if self.Data else None
        printed_level = level & 0xFF
        self.LScale, self.RScale = (level >> 24) & 0xFF, (level >> 16) & 0xFF
        self.BaseAttack, self.BaseDefense = max(atk, 0), max(dfn, 0)
        on_field = Location == CardLocation.MonsterZone
        self.Attack = Attack if on_field and Attack is not None else self.BaseAttack
        self.Defense = Defense if on_field and Defense is not None else self.BaseDefense
        lvl = Level if on_field and Level is not None else printed_level
        # WindBot keeps Level, Rank and LinkCount apart (Xyz monsters have a Rank, Links a Link Rating)
        self.Level = 0 if self.Type & (CardType.Xyz | CardType.Link) else lvl
        self.Rank = lvl if self.Type & CardType.Xyz else 0
        self.LinkCount = printed_level if self.Type & CardType.Link else 0
        self.LinkMarker = 0
        self.OverlayCount = OverlayCount
        self.Overlays = [0] * OverlayCount  # material codes aren't exposed, only how many
        self.Owner = Controller
        self.Disabled = 0          # not exposed by the env
        self.ProcCompleted = 0     # not exposed by the env
        self.RealPower = self.Attack  # battle power the battle rules adjust
        self.IsLastAttacker = False
        self.IsSpecialSummoned = False  # not exposed by the env
        self.LastLocation = 0           # not exposed by the env
        self.CanDirectAttack = False
        self.Attacked = False
        self.SelectSeq = 0
        self.OpParam1 = self.OpParam2 = 0
        self.EquipCards, self.OwnTargets, self.TargetCards = [], [], []
        self.ActionIndex = None

    # identity: WindBot compares card objects; views are rebuilt per decision, so compare by place
    def _key(self):
        return self.Id, self.Controller, self.Location, self.Sequence

    def __eq__(self, other):
        return isinstance(other, Card) and self._key() == other._key()

    def __hash__(self):
        return hash(self._key())

    def __deepcopy__(self, memo):
        return self  # a view's cards are values: executor state snapshots share them

    def __repr__(self):
        return f"Card({self.Name or self.Id}, ctl={self.Controller}, loc={self.Location:#x}, seq={self.Sequence})"

    def SetId(self, id_):
        if id_ != self.Id:
            self.__init__(id_, self.Location, self.Sequence, self.Controller, self.Position)

    def IsCode(self, *ids) -> bool:
        flat = [i for x in ids for i in (x if isinstance(x, (list, tuple, set)) else [x])]
        return bool(self.Id) and (self.Id in flat or (bool(self.Alias) and self.Alias in flat))

    def IsOriginalCode(self, id_) -> bool:
        return self.Id == id_ or (self.Alias == id_ and abs(self.Id - self.Alias) < 10)  # alt-art alias

    def GetOriginCode(self):
        return (self.Data.Alias or self.Data.Id) if self.Data else self.Id

    def GetNonAltartCode(self):
        return self.Alias if self.Alias and abs(self.Id - self.Alias) < 10 else self.Id

    def HasType(self, t) -> bool:
        return bool(self.Type & t)

    def HasPosition(self, p):
        return bool(self.Position & p)

    def HasLocation(self, loc):
        return bool(self.Location & loc)

    def HasAttribute(self, a):
        return bool(self.Attribute & a)

    def HasRace(self, r):
        return bool(self.Race & r)

    def HasSetcode(self, setcode) -> bool:
        """ygopro set-code match: same base series (low 12 bits) and every sub-series bit of `setcode`."""
        return any((s & 0xFFF) == (setcode & 0xFFF) and (s & setcode) == setcode for s in self.Setcodes)

    def HasLinkMarker(self, d):
        return bool(self.LinkMarker & d)

    def GetLinkedZones(self):
        return 0  # link markers aren't exposed

    def IsMonster(self):
        return self.HasType(CardType.Monster)

    def IsTuner(self):
        return self.HasType(CardType.Tuner)

    def IsSpell(self):
        return self.HasType(CardType.Spell)

    def IsTrap(self):
        return self.HasType(CardType.Trap)

    def IsExtraCard(self):
        return self.HasType(CardType.Fusion | CardType.Synchro | CardType.Xyz | CardType.Link)

    def IsFaceup(self):
        return self.HasPosition(CardPosition.FaceUp)

    def IsFacedown(self):
        return self.HasPosition(CardPosition.FaceDown)

    def IsAttack(self):
        return self.HasPosition(CardPosition.Attack)

    def IsDefense(self):
        return self.HasPosition(CardPosition.Defence)

    def IsDisabled(self) -> bool:
        return self.Disabled != 0

    def IsCanRevive(self):
        return self.ProcCompleted != 0 or not (self.IsExtraCard() or self.HasType(CardType.Ritual | CardType.SpSummon))

    def IsOnField(self):
        return self.Location in (CardLocation.MonsterZone, CardLocation.SpellZone, CardLocation.PendulumZone,
                                 CardLocation.FieldZone)

    def HasXyzMaterial(self, count=1, cardid=None) -> bool:
        return self.OverlayCount >= count and (cardid is None or cardid in self.Overlays)

    def GetDefensePower(self) -> int:
        """ClientCard.GetDefensePower: ATK in Attack Position, DEF in Defense Position."""
        return self.Attack if self.IsAttack() else self.Defense

    # --- CardExtension
    def GetAttackPower(self) -> int:
        """The power this monster attacks with: DEF for monsters that attack from Defense Position."""
        if self.IsMonsterAttackWhileInDefPos() and self.Id not in LIST["DefenseAttackWithAttackValueMonster"]:
            return self.Defense
        return self.Attack

    def IsMonsterInvincible(self):
        return self.IsFaceup() and self.Id in LIST["InvincibleBotMonster" if self.Controller == 0 else "InvincibleEnemyMonster"]

    def IsMonsterDangerous(self):
        return self.IsFaceup() and self.Id in LIST["DangerousMonster"]

    def IsMonsterHasPreventActivationEffectInBattle(self):
        return self.IsFaceup() and self.Id in LIST["PreventActivationEffectInBattle"]

    def IsMonsterAttackWhileInDefPos(self):
        return self.IsFaceup() and self.IsDefense() and self.Id in LIST["DefenseAttackMonster"]

    def IsShouldNotBeTarget(self):
        return self.IsFaceup() and not self.HasType(CardType.Normal) and self.Id in LIST["ShouldNotBeTarget"]

    def IsShouldNotBeMonsterTarget(self):
        return self.IsFaceup() and self.Id in LIST["ShouldNotBeMonsterTarget"]

    def IsShouldNotBeSpellTrapTarget(self):
        return self.IsFaceup() and self.Id in LIST["ShouldNotBeSpellTrapTarget"]

    def IsMonsterShouldBeDisabledBeforeItUseEffect(self):
        return self.IsFaceup() and self.Id in LIST["ShouldBeDisabledBeforeItUseEffectMonster"]

    def IsFloodgate(self):
        return self.IsFaceup() and self.Id in LIST["Floodgate"]

    def IsOneForXyz(self):
        return self.Id in LIST.get("OneForXyz", ())

    def IsFusionSpell(self):
        return self.Id in LIST.get("FusionSpell", ())

    def IsMonsterNotBeSynchroMaterial(self):
        return self.Id in LIST.get("NotBeSynchroMaterialMonster", ())

    def IsMonsterNotBeXyzMaterial(self):
        return self.Id in LIST.get("NotBeXyzMaterialMonster", ())

    def IsMonsterNotBeSummonTribute(self):
        return self.Id in LIST.get("NotBeSummonTributeMonster", ())


class Field:
    """ClientField: one player's cards (hidden ones only for the enemy)."""

    def __init__(self, LifePoints=8000):
        self.Hand, self.Graveyard, self.Banished, self.Deck, self.ExtraDeck = [], [], [], [], []
        self.MonsterZone = [None] * 7
        self.SpellZone = [None] * 8
        self.LifePoints = LifePoints
        self.BattlingMonster = None  # not exposed by the env
        self.UnderAttack = False
        self.HintDescriptions = set()
        self.DeckTrackingActive = True

    # --- zone contents
    def GetMonsters(self):
        return [c for c in self.MonsterZone if c is not None]

    def GetSpells(self):
        return [c for c in self.SpellZone if c is not None]

    def GetFaceupMonsters(self):
        return [c for c in self.MonsterZone if c is not None and c.IsFaceup()]

    def GetMonstersInMainZone(self):
        return [c for c in self.GetMonsters() if c.Sequence < 5]

    def GetMonstersInExtraZone(self):
        return [c for c in self.GetMonsters() if c.Sequence >= 5]

    def GetGraveyardMonsters(self):
        return [c for c in self.Graveyard if c.HasType(CardType.Monster)]

    def GetGraveyardSpells(self):
        return [c for c in self.Graveyard if c.HasType(CardType.Spell)]

    def GetGraveyardTraps(self):
        return [c for c in self.Graveyard if c.HasType(CardType.Trap)]

    def GetFieldSpellCard(self):
        return self.SpellZone[5]

    # --- counts
    def GetMonsterCount(self):
        return len(self.GetMonsters())

    def GetMonstersExtraZoneCount(self):
        return sum(1 for c in self.MonsterZone[5:7] if c is not None)

    def GetSpellCount(self):
        return len(self.GetSpells())

    def GetSpellCountWithoutField(self):
        return sum(1 for c in self.SpellZone[:5] if c is not None)

    def GetHandCount(self):
        return len(self.Hand)

    def GetColumnCount(self, zone, IncludeExtraMonsterZone=True):
        count = (self.SpellZone[zone] is not None) + (self.MonsterZone[zone] is not None)
        if IncludeExtraMonsterZone and zone == 1 and self.MonsterZone[5] is not None:
            count += 1
        if IncludeExtraMonsterZone and zone == 3 and self.MonsterZone[6] is not None:
            count += 1
        return count

    def GetFieldCount(self):
        return self.GetMonsterCount() + self.GetSpellCount()

    def GetFieldHandCount(self):
        return self.GetFieldCount() + self.GetHandCount()

    def IsFieldEmpty(self):
        return not self.GetMonsters() and not self.GetSpells()

    def GetLinkedZones(self):
        return 0

    def GetCardCountInDeck(self, ids):
        ids = ids if isinstance(ids, (list, tuple, set)) else [ids]
        return sum(1 for c in self.Deck if c.Id in ids)

    GetRemainingCount = GetCardCountInDeck

    # --- membership (ids: one id or a list)
    @staticmethod
    def _has(cards, ids, notDisabled=False, hasXyzMaterial=False, faceUp=False):
        return any(c is not None and c.IsCode(ids) and (not notDisabled or not c.IsDisabled()) and
                   (not hasXyzMaterial or c.HasXyzMaterial()) and (not faceUp or c.IsFaceup()) for c in cards)

    def HasInDeck(self, *ids):
        flat = [i for x in ids for i in (x if isinstance(x, (list, tuple, set)) else [x])]
        return any(c.Id in flat for c in self.Deck)

    def HasInHand(self, ids):
        return self._has(self.Hand, ids)

    def HasInGraveyard(self, ids):
        return self._has(self.Graveyard, ids)

    def HasInBanished(self, ids):
        return self._has(self.Banished, ids)

    def HasInExtra(self, ids):
        return self._has(self.ExtraDeck, ids)

    def HasInMonstersZone(self, ids, notDisabled=False, hasXyzMaterial=False, faceUp=False):
        return self._has(self.MonsterZone, ids, notDisabled, hasXyzMaterial, faceUp)

    def HasInSpellZone(self, ids, notDisabled=False, faceUp=False):
        return self._has(self.SpellZone, ids, notDisabled, False, faceUp)

    def HasInPendulumZone(self, ids, notDisabled=False):
        return any(c is not None and c.IsCode(ids) and not c.IsFacedown() and c.HasType(CardType.Pendulum) and
                   (not notDisabled or not c.IsDisabled())
                   for c in (self.SpellZone[0], self.SpellZone[4], self.SpellZone[6], self.SpellZone[7]))

    def HasAttackingMonster(self, strict=False):
        return any(c.IsAttack() or (not strict and c.IsMonsterAttackWhileInDefPos()) for c in self.GetMonsters())

    def HasDefendingMonster(self):
        return any(c.IsDefense() for c in self.GetMonsters())

    def HasInHandOrInSpellZone(self, ids):
        return self.HasInHand(ids) or self.HasInSpellZone(ids)

    def HasInHandOrHasInMonstersZone(self, ids):
        return self.HasInHand(ids) or self.HasInMonstersZone(ids)

    def HasInHandOrInGraveyard(self, ids):
        return self.HasInHand(ids) or self.HasInGraveyard(ids)

    def HasInGraveyardOrInBanished(self, ids):
        return self.HasInBanished(ids) or self.HasInGraveyard(ids)

    def HasInMonstersZoneOrInGraveyard(self, ids):
        return self.HasInMonstersZone(ids) or self.HasInGraveyard(ids)

    def HasInSpellZoneOrInGraveyard(self, ids):
        return self.HasInSpellZone(ids) or self.HasInGraveyard(ids)

    def HasInHandOrInMonstersZoneOrInGraveyard(self, ids):
        return self.HasInHand(ids) or self.HasInMonstersZone(ids) or self.HasInGraveyard(ids)

    def HasInHandOrInSpellZoneOrInGraveyard(self, ids):
        return self.HasInHand(ids) or self.HasInSpellZone(ids) or self.HasInGraveyard(ids)


class ChainInfo:
    """One chain link as activated: the card, who activated it, its effect description, its targets."""

    def __init__(self, card, player=None, desc=0):
        self.RelatedCard = card
        self.ActivatePlayer = card.Controller if player is None else player
        self.ActivateId, self.ActivateAlias = card.Id, card.Alias
        self.ActivateController, self.ActivatePosition = card.Controller, card.Position
        self.ActivateSequence, self.ActivateLocation = card.Sequence, card.Location
        self.ActivateLevel, self.ActivateRank, self.ActivateType = card.Level, card.Rank, card.Type
        self.ActivateRace, self.ActivateAttack, self.ActivateDefense = card.Race, card.Attack, card.Defense
        self.IsSpecialSummoned = card.IsSpecialSummoned
        self.ActivateDescription = desc
        self.Targets = []
        self.Announces = []
        self.Negated = False  # ygo-sim: the engine's negated / disabled flag for this link

    def IsCode(self, *ids):
        return self.RelatedCard.IsCode(*ids)

    def IsActivateCode(self, *ids):
        flat = [i for x in ids for i in (x if isinstance(x, (list, tuple, set)) else [x])]
        return bool(self.ActivateId) and (self.ActivateId in flat or (bool(self.ActivateAlias) and self.ActivateAlias in flat))

    def HasPosition(self, position):
        return bool(self.ActivatePosition & position)

    def HasLocation(self, location):
        return bool(self.ActivateLocation & location)

    def HasAnnounce(self, *descs):
        return any(d in self.Announces for d in descs)


class MainPhase:
    """The current idle command's available actions (MSG_SELECT_IDLECMD)."""

    def __init__(self):
        self.SummonableCards, self.SpecialSummonableCards, self.ReposableCards = [], [], []
        self.MonsterSetableCards, self.SpellSetableCards, self.ActivableCards, self.ActivableDescs = [], [], [], []
        self.CanBattlePhase = self.CanEndPhase = False


class BattlePhase:
    """The current battle command's available actions (MSG_SELECT_BATTLECMD)."""

    def __init__(self):
        self.AttackableCards, self.ActivableCards, self.ActivableDescs = [], [], []
        self.CanMainPhaseTwo = self.CanEndPhase = False


class DuelView:
    """Duel: both fields, whose turn, phase, the chain and what was just summoned (players relative)."""

    def __init__(self):
        self.Fields = [Field(), Field()]
        self.Player = 0                 # turn player (0 = bot)
        self.Phase = DuelPhase.Main1
        self.Turn = 1
        self.IsFirst = True
        self.IsNewRule = True
        self.CurrentChain = []          # Card per link, link 1 first
        self.CurrentChainInfo = []      # ChainInfo per link
        self.ChainTargets = []          # cards targeted by the chain so far
        self.LastChainTargets = []      # targets of the latest link
        self.ChainTargetOnly = []
        self.LastSummonedCards = []
        self.SummoningCards = []
        self.LastSummonPlayer = -1
        self.LastChainPlayer = -1
        self.LastChainLocation = 0
        self.SolvingChainIndex = 0      # 1-based, 0 when no link is resolving
        self.NegatedChainIndexList = []
        self.MainPhase = MainPhase()
        self.BattlePhase = BattlePhase()

    def GetCurrentChainCard(self):
        """The link being activated (costs and targets); None while a link resolves."""
        if self.SolvingChainIndex != 0 or not self.CurrentChain:
            return None
        return self.CurrentChain[-1]

    def GetCurrentSolvingChainInfo(self):
        if self.SolvingChainIndex == 0 or self.SolvingChainIndex > len(self.CurrentChainInfo):
            return None
        return self.CurrentChainInfo[self.SolvingChainIndex - 1]

    def GetCurrentSolvingChainCard(self):
        info = self.GetCurrentSolvingChainInfo()
        return info.RelatedCard if info else None

    def IsCurrentSolvingChainNegated(self):
        return self.SolvingChainIndex != 0 and self.SolvingChainIndex in self.NegatedChainIndexList

    def GetCard(self, player, location, sequence):
        f = self.Fields[player]
        if location == CardLocation.MonsterZone:
            return f.MonsterZone[sequence] if 0 <= sequence < 7 else None
        if location == CardLocation.SpellZone:
            return f.SpellZone[sequence] if 0 <= sequence < 8 else None
        cards = {CardLocation.Hand: f.Hand, CardLocation.Grave: f.Graveyard, CardLocation.Removed: f.Banished,
                 CardLocation.Deck: f.Deck, CardLocation.Extra: f.ExtraDeck}.get(location, [])
        return cards[sequence] if 0 <= sequence < len(cards) else None


class CardSelector:
    """What AI.SelectCard / SelectMaterials queue: a card, cards, an id, ids or a location."""

    def __init__(self, what):
        self.what = what

    def Select(self, cards, min_, max_):
        w, result = self.what, []
        if isinstance(w, Card):
            if w in cards:
                result.append(w)
        elif isinstance(w, (list, tuple)) and w and isinstance(w[0], Card):
            for c in w:
                if c in cards and c not in result:
                    result.append(c)
        elif isinstance(w, (list, tuple)):
            for id_ in w:
                for c in cards:
                    if c.IsCode(id_) and c not in result:
                        result.append(c)
        elif isinstance(w, int) and w < 0x400:  # a CardLocation (card ids are far larger)
            result = [c for c in cards if c.Location == w]
        elif isinstance(w, int):
            result = [c for c in cards if c.IsCode(w)]
        if len(result) < min_:
            for c in cards:
                if c not in result:
                    result.append(c)
                if len(result) >= min_:
                    break
        return result[:max_]


class Util:
    """AIUtil: the helpers WindBot executors use."""

    def __init__(self, bot, enemy, duel):
        self.Bot, self.Enemy, self.Duel = bot, enemy, duel

    @staticmethod
    def GetStringId(id_, option):
        return id_ * 16 + option

    def IsTurn1OrMain2(self):
        return self.Duel.Turn == 1 or self.Duel.Phase == DuelPhase.Main2

    def GetPZone(self, player, id_):
        return self.Duel.Fields[player].SpellZone[id_ * 4]

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
        return card is not None and card in self.Duel.ChainTargets

    def IsChainTargetOnly(self, card):
        return len(self.Duel.ChainTargetOnly) == 1 and card in self.Duel.ChainTargetOnly

    def GetTotalAttackingMonsterAttack(self, player):
        f = self.Duel.Fields[player]
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

    def GetProblematicEnemyMonster(self, attack=0, canBeTarget=False):
        m = self.Enemy.GetMonsters()
        card = GetFloodgate(m, canBeTarget) or GetDangerousMonster(m, canBeTarget) or GetInvincibleMonster(m, canBeTarget)
        if card is not None:
            return card
        if attack == 0:
            attack = self.GetBestAttack(self.Bot)
        return self.GetOneEnemyBetterThanValue(attack, True, canBeTarget)

    def GetProblematicEnemySpell(self):
        return GetFloodgate(self.Enemy.GetSpells())

    def GetProblematicEnemyCard(self, attack=0, canBeTarget=False):
        card = GetFloodgate(self.Enemy.GetMonsters(), canBeTarget) or GetFloodgate(self.Enemy.GetSpells(), canBeTarget)
        if card is not None:
            return card
        m = self.Enemy.GetMonsters()
        card = GetDangerousMonster(m, canBeTarget) or GetInvincibleMonster(m, canBeTarget)
        if card is not None:
            return card
        if attack == 0:
            attack = self.GetBestAttack(self.Bot)
        return self.GetOneEnemyBetterThanValue(attack, True, canBeTarget)

    def GetBestEnemyMonster(self, onlyFaceup=False, canBeTarget=False):
        card = self.GetProblematicEnemyMonster(0, canBeTarget)
        if card is not None:
            return card
        card = GetHighestAttackMonster(self.Enemy.GetMonsters(), canBeTarget)
        if card is not None:
            return card
        if not onlyFaceup:
            return next((c for c in self.Enemy.GetMonsters() if not canBeTarget or not c.IsShouldNotBeTarget()), None)
        return None

    def GetBestEnemySpell(self, onlyFaceup=False):
        card = self.GetProblematicEnemySpell()
        if card is not None:
            return card
        spells = self.Enemy.GetSpells()
        card = next((c for c in spells if c.IsFaceup() and c.HasType(CardType.Continuous | CardType.Field)), None)
        if card is not None:
            return card
        return spells[0] if spells and not onlyFaceup else None

    def GetBestEnemyCard(self, onlyFaceup=False, canBeTarget=False):
        return self.GetBestEnemyMonster(onlyFaceup, canBeTarget) or self.GetBestEnemySpell(onlyFaceup)

    @staticmethod
    def CheckSelectCount(_selected, cards, min_, max_):
        selected = []
        for c in _selected:
            if c in cards and c not in selected:
                selected.append(c)
        if len(selected) < min_:
            for c in cards:
                if c not in selected:
                    selected.append(c)
                if len(selected) >= max_:
                    break
            if len(selected) < min_:
                return None
        return selected[:max_]

    @staticmethod
    def ShuffleList(items):
        result = list(items)
        Rand.shuffle(result)
        return result


# --- CardContainer: WindBot's extension methods on card lists ------------------------------------------
# Sort keys stand in for the C# comparers (CompareCardAttack etc.): sorted(cards, key=CompareCardAttack).

def CompareCardAttack(c):
    return c.Attack


def CompareCardAttackPower(c):
    return c.GetAttackPower()


def CompareCardLevel(c):
    return c.Level


def CompareCardLink(c):
    return c.LinkCount


def CompareDefensePower(c):
    return -10 ** 9 if c is None else c.GetDefensePower()


def _targetable(cards, canBeTarget):
    return [c for c in cards if c is not None and (not canBeTarget or not c.IsShouldNotBeTarget())]


def GetHighestAttackMonster(cards, canBeTarget=False):
    return max((c for c in _targetable(cards, canBeTarget) if c.IsFaceup()), key=lambda c: c.Attack, default=None)


def GetHighestDefenseMonster(cards, canBeTarget=False):
    return max((c for c in _targetable(cards, canBeTarget) if c.IsFaceup()), key=lambda c: c.Defense, default=None)


def GetLowestAttackMonster(cards, canBeTarget=False):
    return min((c for c in _targetable(cards, canBeTarget) if c.IsFaceup()), key=lambda c: c.Attack, default=None)


def GetLowestDefenseMonster(cards, canBeTarget=False):
    return min((c for c in _targetable(cards, canBeTarget) if c.IsFaceup()), key=lambda c: c.Defense, default=None)


def ContainsCardWithId(cards, id_):
    return any(c is not None and c.IsCode(id_) for c in cards)


def GetCardCount(cards, ids):
    return sum(1 for c in cards if c is not None and c.IsCode(ids))


def GetMonstersOf(cards):
    """CardContainer.GetMonsters on a card list."""
    return [c for c in cards if c is not None and c.HasType(CardType.Monster)]


def GetFaceupPendulumMonsters(cards):
    return [c for c in cards if c is not None and c.HasType(CardType.Monster) and c.IsFaceup() and
            c.HasType(CardType.Pendulum)]


def GetInvincibleMonster(cards, canBeTarget=False):
    return next((c for c in _targetable(cards, canBeTarget) if c.IsMonsterInvincible() and c.IsFaceup()), None)


def GetDangerousMonster(cards, canBeTarget=False):
    return next((c for c in _targetable(cards, canBeTarget) if c.IsMonsterDangerous() and c.IsFaceup()), None)


def GetFloodgate(cards, canBeTarget=False):
    return next((c for c in _targetable(cards, canBeTarget) if c.IsFloodgate() and c.IsFaceup()), None)


def GetFirstMatchingCard(cards, f):
    return next((c for c in cards if c is not None and f(c)), None)


def GetFirstMatchingFaceupCard(cards, f):
    return next((c for c in cards if c is not None and c.IsFaceup() and f(c)), None)


def GetMatchingCards(cards, f):
    return [c for c in cards if c is not None and f(c)]


def GetMatchingCardsCount(cards, f):
    return sum(1 for c in cards if c is not None and f(c))


def IsExistingMatchingCard(cards, f, count=1):
    return GetMatchingCardsCount(cards, f) >= count


def GetShouldBeDisabledBeforeItUseEffectMonster(cards, canBeTarget=True):
    return next((c for c in _targetable(cards, canBeTarget) if c.IsMonsterShouldBeDisabledBeforeItUseEffect()), None)


# --- Views from env info ------------------------------------------------------------------------------

def build_views(info, i, player):
    """(Bot, Enemy, Duel) for decision i from `player`'s side. Needs the context fields (YGOSIM_CONTEXT=1)."""
    duel = DuelView()
    rel = lambda p: 0 if int(p) == player else 1
    for r, p in ((0, player), (1, 1 - player)):
        f = duel.Fields[r]
        f.LifePoints = int(info["lp_"][i][p])
        zc = info["zone_cards_"][i][p]
        for row in range(16):
            code, pos, atk, dfn, lvl, ov = (int(x) for x in zc[row])
            if not code:
                continue
            hidden = r == 1 and pos & CardPosition.FaceDown
            loc = CardLocation.MonsterZone if row < 8 else CardLocation.SpellZone
            seq = row if row < 8 else row - 8
            c = Card(0 if hidden else code, loc, seq, r, pos, 0 if hidden else atk, 0 if hidden else dfn,
                     0 if hidden else lvl, ov)
            if row < 7:
                f.MonsterZone[seq] = c
            elif row >= 8:
                f.SpellZone[seq] = c
        f.Hand = [Card(0 if r == 1 else int(c), CardLocation.Hand, k, r)
                  for k, c in enumerate([c for c in info["hand_codes_"][i][p] if c])]
        f.Graveyard = [Card(int(c), CardLocation.Grave, k, r)
                       for k, c in enumerate([c for c in info["grave_codes_"][i][p] if c])]
        f.Banished = [Card(0 if r == 1 and c < 0 else abs(int(c)), CardLocation.Removed, k, r,
                           CardPosition.FaceDown if c < 0 else CardPosition.FaceUpAttack)
                      for k, c in enumerate([c for c in info["banished_codes_"][i][p] if c])]
        if r == 0:  # own Deck / Extra Deck only (present when the env runs with YGOSIM_CONTEXT)
            f.Deck = [Card(int(c), CardLocation.Deck, k, 0, CardPosition.FaceDownDefence)
                      for k, c in enumerate([c for c in info["deck_codes_"][i][p] if c])]
            f.ExtraDeck = [Card(abs(int(c)), CardLocation.Extra, k, 0,
                                CardPosition.FaceUp if c < 0 else CardPosition.FaceDown)
                           for k, c in enumerate([c for c in info["extra_codes_"][i][p] if c])]
    duel.Player = rel(info["turn_player"][i])
    duel.Phase = int(info["phase"][i]) or DuelPhase.Main1
    duel.Turn = int(info["turn"][i])
    duel.IsFirst = (duel.Turn % 2 == 1) == (duel.Player == 0)
    for row in info["chain_"][i]:
        code, ctl, loc, tgt, desc, neg, seq, act = (int(x) for x in row)
        if not code:
            continue
        card = duel.GetCard(rel(ctl), loc, seq) if loc in (CardLocation.MonsterZone, CardLocation.SpellZone) else None
        if card is None or card.Id != code:
            card = Card(code, loc, seq, rel(ctl))
        link = ChainInfo(card, rel(act), desc & 0xFFFFFFFF)
        if tgt:
            link.Targets.append(find_on_field(duel, tgt))
        link.Negated = bool(neg)
        duel.CurrentChain.append(card)
        duel.CurrentChainInfo.append(link)
        if neg:
            duel.NegatedChainIndexList.append(len(duel.CurrentChain))
    duel.SolvingChainIndex = int(info["solving_"][i])
    duel.LastChainPlayer = duel.CurrentChainInfo[-1].ActivatePlayer if duel.CurrentChainInfo else -1
    duel.LastChainLocation = duel.CurrentChain[-1].Location if duel.CurrentChain else 0
    duel.LastChainTargets = [find_on_field(duel, int(code)) for code in info["chain_targets_"][i] if code]
    duel.ChainTargets = [t for link in duel.CurrentChainInfo for t in link.Targets]
    duel.ChainTargets += [t for t in duel.LastChainTargets if t not in duel.ChainTargets]
    duel.ChainTargetOnly = list(duel.LastChainTargets)
    duel.LastSummonedCards = [find_on_field(duel, int(code), rel(ctl)) for code, ctl in info["summoned_"][i] if code]
    duel.LastSummonPlayer = duel.LastSummonedCards[-1].Controller if duel.LastSummonedCards else -1
    bot, enemy = duel.Fields
    return bot, enemy, duel


def find_on_field(duel, code, controller=None):
    for ctl in ((controller,) if controller is not None else (0, 1)):
        for c in duel.Fields[ctl].GetMonsters() + duel.Fields[ctl].GetSpells():
            if c.Id == code:
                return c
    return Card(code, CardLocation.Onfield, Controller=-1 if controller is None else controller)


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
    """A WindBot executor. Subclasses add rows in __init__ (AddExecutor, in WindBot's order), keep their own
    flags as attributes and override the On* virtuals below; windbot_gameai.GameAI drives them."""

    DECK_EXECUTOR = False  # True for deck executors: GameAI's fallbacks (end the turn, pass...) are its choices

    def __init__(self):
        from windbot_gameai import GameAI  # the AI.Select* queues the rows fill
        self.rows = []
        self.Bot = self.Enemy = self.Duel = self.Util = self.Card = None
        self.AI = GameAI()
        self.Type = None
        self.ActivateDescription = -1
        self.CurrentTiming = -1

    # --- rows
    def AddExecutor(self, type_, card_id=None, func=None):
        if callable(card_id) and func is None:   # AddExecutor(type, func)
            card_id, func = None, card_id
        if card_id is None and func is None:     # AddExecutor(type): cards no other row of this type handles
            func = self._DefaultNoExecutor
        self.rows.append((type_, card_id, func))

    def _DefaultNoExecutor(self):
        return all(t != self.Type or cid is None or not self.Card.IsOriginalCode(cid) for t, cid, _ in self.rows)

    def SetCard(self, type_, card, description, timing=-1):
        self.Type, self.Card, self.ActivateDescription, self.CurrentTiming = type_, card, description, timing

    # state that conditions may change (flags, AI queues), copied around dry runs
    def _state(self):
        return {k: v for k, v in self.__dict__.items() if k not in ("rows", "Bot", "Enemy", "Duel", "Util", "Card")}

    # --- WindBot's virtuals with their defaults
    def OnSelectHand(self):
        return True

    def OnBattle(self, attackers, defenders):
        return None

    def OnSelectAttacker(self, attackers, defenders):
        return None

    def OnSelectAttackTarget(self, attacker, defenders):
        return None

    def OnPreBattleBetween(self, attacker, defender):
        return True

    def OnPreActivate(self, card):
        return True

    def OnChaining(self, player, card):
        pass

    def OnChainSolved(self, chainIndex):
        pass

    def OnChainEnd(self):
        pass

    def OnNewPhase(self):
        pass

    def OnNewTurn(self):
        pass

    def OnDraw(self, player):
        pass

    def OnMove(self, card, previousControler, previousLocation, currentControler, currentLocation):
        pass

    def OnPosChange(self, card, previousPosition, currentPosition):
        pass

    def OnSelectCard(self, cards, min_, max_, hint, cancelable):
        return None

    def OnSelectTribute(self, cards, min_, max_, hint, cancelable):
        return None

    def OnSelectSum(self, cards, mandatoryCards, sum_, min_, max_, hint, exactEqual):
        return None

    def OnSelectFusionMaterial(self, cards, min_, max_):
        return None

    def OnSelectSynchroMaterial(self, cards, mandatoryCards, sum_, min_, max_):
        return None

    def OnSelectXyzMaterial(self, cards, min_, max_):
        return None

    def OnSelectLinkMaterial(self, cards, min_, max_):
        return None

    def OnSelectRitualTribute(self, cards, mandatoryCards, sum_, min_, max_, exactEqual):
        return None

    def OnSelectPendulumSummon(self, cards, min_, max_):
        return None

    def OnSelectChain(self, cards):
        pass

    def OnSelectYesNo(self, desc):
        return True

    def OnSelectOption(self, options):
        return -1

    def OnSelectPlace(self, cardId, player, location, available):
        return 0

    def OnSelectDisfield(self, hint, count, available):
        return 0

    def OnSelectPosition(self, cardId, positions):
        return 0

    def OnSelectBattleReplay(self):
        return False

    def OnSelectMonsterSummonOrSet(self, card):
        return False

    def OnSpSummoned(self):
        pass

    def OnSpSummoning(self):
        pass

    def OnSummoning(self):
        pass


# Message ids (ocgcore) of the decisions.
BATTLECMD, IDLE, EFFECTYN, YESNO, SELECT_OPTION, SELECT_CARD, CHAIN = 10, 11, 12, 13, 14, 15, 16
SELECT_PLACE, POSITION, TRIBUTE, SELECT_DISFIELD, SELECT_SUM, UNSELECT_CARD = 18, 19, 20, 24, 23, 26
SELECTS = (SELECT_CARD, TRIBUTE, SELECT_SUM, UNSELECT_CARD)
POSITION_LETTER = {CardPosition.FaceUpAttack: "1", CardPosition.FaceDownAttack: "2",
                   CardPosition.FaceUpDefence: "3", CardPosition.FaceDownDefence: "4"}
