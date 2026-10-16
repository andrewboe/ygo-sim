"""Elfnote executor, ported from IceYGO/windbot Game/AI/Decks/ElfnoteExecutor.cs (MIT, see THIRD_PARTY_NOTICES.md).

Approximations: what the env can't show (docs/windbot_porting.md): IsDisabled() is always False, EquipCards are
empty, BattlingMonster is None, LastLocation is 0, hint descriptions don't arrive. ClientCard reference equality
is the shim's (Id, Controller, Location, Sequence) key, so SameFieldCard and `==` agree. Logging calls dropped.

Module-level helpers (WindBot members the shim lacks): DefaultCheckWhetherBotWillBeBanishedByType (the
DefaultExecutor (type, location) overload of DefaultCheckWhetherBotWillBeBanished) and
DefaultIsDimensionalFissureTarget. C# overloads are merged: CheckShouldNoMoreSpSummon(loc=None),
CheckWhetherBotWillBeBanished(card=None, location=None) (type, location form when location is given),
CanRbySwapNow(card or id, ...); `out` parameters become returned tuples.
"""
from windbot import *
from windbot_default import DefaultExecutor, _CardId, _Setcode
from windbot_gameai import BattlePhaseAction


class CardId:
    MixedHellGod = 70488851
    GreatRighteousThief = 24203749
    WhitePendulum = 10266279
    ElvenotesRed = 13597785
    ElvenotesBlue = 59581480
    ElvenotesYellow = 85976588
    ElvenotesWind = 56651978
    MediusTheInnocent = 97556336
    JailChicken = 12375297
    JailGodGate = 25661743
    InnocentArt = 37279096
    GreenField = 64491754
    RedField = 24092792

    ChaosAngel = 22850702
    White10 = 5559570
    BaronneDeFleur = 84815190
    AssaultBlackwing = 31114334
    ThousandSpearDragon = 65424481
    AncientFishDragon = 87188910
    CrystalWing = 50954680
    PSYFramelordOmega = 74586817
    AccelSynchroStardust = 30983281
    StardustDragon = 44508094
    HelldiveBomber = 66122213
    BlackRoseDragon = 73580471
    FormulaAthleteLightning = 33158448
    White7 = 42302563
    SuperLibrarian = 90953320


SetcodeElvenotes = 0x1d8
SetcodeJailGod = 0x1ce
SetcodeTimeLord = 0x4a
SetcodeOrcust = 0x11b
SetcodePhantomKnight = 0xdb
SetcodeHorus = 0x19d
HintTimingMainEnd = 0x4


def _OrderByAttackDesc(cards):
    """LINQ OrderByDescending(card => card.Attack) (stable)."""
    return sorted(cards, key=lambda c: -c.Attack)


def _FirstByAttackDesc(cards):
    ordered = _OrderByAttackDesc(cards)
    return ordered[0] if ordered else None


class ElfnoteExecutor(DefaultExecutor):
    DECK_EXECUTOR = True

    def __init__(self):
        super().__init__()
        A, S, SS = ExecutorType.Activate, ExecutorType.Summon, ExecutorType.SpSummon
        self.AddExecutor(A, _CardId.EffectVeiler, self.EffectVeilerActivate)
        self.AddExecutor(A, _CardId.AshBlossom, self.AshBlossomActivate)
        self.AddExecutor(A, CardId.BaronneDeFleur, self.BaronneNegateActivate)
        self.AddExecutor(A, CardId.CrystalWing, self.CrystalWingActivate)
        self.AddExecutor(A, CardId.FormulaAthleteLightning, self.FormulaAthleteActivate)
        self.AddExecutor(A, CardId.GreatRighteousThief, self.GreatRighteousThiefNegateActivate)
        self.AddExecutor(A, CardId.AccelSynchroStardust, self.AccelStardustActivate)
        self.AddExecutor(A, CardId.StardustDragon, self.StardustDragonActivate)
        self.AddExecutor(A, CardId.PSYFramelordOmega, self.PSYOmegaActivate)
        self.AddExecutor(A, CardId.ChaosAngel, self.ChaosAngelActivate)
        self.AddExecutor(A, CardId.RedField, self.RedFieldActivate)
        self.AddExecutor(A, CardId.White10, self.White10Activate)
        self.AddExecutor(A, CardId.White7, self.White7Activate)
        self.AddExecutor(A, CardId.BaronneDeFleur, self.BaronneDestroyActivate)

        self.AddExecutor(A, _CardId.MaxxC, self.MaxxCActivate)
        self.AddExecutor(A, _CardId.MulcharmyFuwalos, self.MulcharmyFuwalosActivate)
        self.AddExecutor(A, _CardId.MulcharmyPurulia, self.MulcharmyPuruliaActivate)
        self.AddExecutor(A, _CardId.LockBird, self.LockBirdActivate)

        # Tribute opponent monsters before our own Activate / SpSummon, so they cannot negate the combo.
        self.AddExecutor(S, CardId.GreatRighteousThief, self.GreatRighteousThiefSummon)

        self.AddExecutor(A, CardId.InnocentArt, self.InnocentArtActivate)
        self.AddExecutor(A, CardId.JailGodGate, self.JailGodGateActivate)
        self.AddExecutor(A, CardId.MixedHellGod, self.MixedHellGodActivate)
        self.AddExecutor(S, CardId.JailChicken, self.JailChickenSummonForWhite10Dodge)
        self.AddExecutor(SS, CardId.ElvenotesRed, self.ElvenotesRedSpSummon)
        self.AddExecutor(A, CardId.ElvenotesRed, self.ElvenotesRedActivate)
        self.AddExecutor(SS, CardId.ElvenotesBlue, self.ElvenotesBlueSpSummon)
        self.AddExecutor(A, CardId.ElvenotesBlue, self.ElvenotesBlueActivate)
        self.AddExecutor(A, CardId.GreenField, self.GreenFieldActivateFromHand)
        self.AddExecutor(SS, CardId.ElvenotesYellow, self.ElvenotesYellowSpSummon)
        self.AddExecutor(A, CardId.ElvenotesYellow, self.ElvenotesYellowActivate)
        self.AddExecutor(A, CardId.ElvenotesWind, self.ElvenotesWindActivate)
        self.AddExecutor(A, CardId.MediusTheInnocent, self.MediusActivate)
        self.AddExecutor(A, CardId.WhitePendulum, self.WhitePendulumActivate)
        # Same-window triggers: White P draw, Chicken GY search, White P recycle, Black Rose, Wind GY recycle.
        self.AddExecutor(A, CardId.WhitePendulum, self.WhitePendulumDrawActivate)
        self.AddExecutor(A, CardId.JailChicken, self.JailChickenGySearchActivate)
        self.AddExecutor(A, CardId.WhitePendulum, self.WhitePendulumRecycleActivate)
        self.AddExecutor(A, CardId.BlackRoseDragon, self.BlackRoseActivate)
        self.AddExecutor(A, CardId.ElvenotesWind, self.ElvenotesWindGyRecycleActivate)

        self.AddExecutor(SS, CardId.BlackRoseDragon, self.BlackRoseSpSummon)
        self.AddExecutor(SS, CardId.White7, self.White7SpSummon)
        self.AddExecutor(SS, CardId.SuperLibrarian, self.SuperLibrarianSpSummon)
        self.AddExecutor(SS, CardId.AccelSynchroStardust, self.AccelStardustSpSummon)
        self.AddExecutor(SS, CardId.CrystalWing, self.CrystalWingSpSummon)
        self.AddExecutor(SS, CardId.White10, self.White10SpSummon)
        self.AddExecutor(SS, CardId.BaronneDeFleur, self.BaronneSpSummon)
        self.AddExecutor(SS, CardId.FormulaAthleteLightning, self.FormulaAthleteSpSummon)
        self.AddExecutor(SS, CardId.PSYFramelordOmega, self.PSYOmegaSpSummon)
        self.AddExecutor(SS, CardId.AncientFishDragon, self.AncientFishSpSummon)
        self.AddExecutor(SS, CardId.ThousandSpearDragon, self.ThousandSpearSpSummon)
        self.AddExecutor(SS, CardId.AssaultBlackwing, self.AssaultBlackwingSpSummon)
        self.AddExecutor(SS, CardId.HelldiveBomber, self.HelldiveBomberSpSummon)
        self.AddExecutor(SS, CardId.ChaosAngel, self.ChaosAngelSpSummon)

        self.AddExecutor(S, CardId.MediusTheInnocent, self.MediusSummon)
        self.AddExecutor(S, CardId.JailChicken, self.JailChickenSummon)
        self.AddExecutor(S, _CardId.EffectVeiler, self.EffectVeilerSummon)

        self.AddExecutor(A, CardId.GreenField, self.GreenFieldActivate)
        self.AddExecutor(A, CardId.JailChicken, self.JailChickenActivate)
        self.AddExecutor(A, CardId.ThousandSpearDragon, self.ThousandSpearActivate)
        self.AddExecutor(A, CardId.HelldiveBomber, self.HelldiveBomberActivate)
        self.AddExecutor(A, CardId.AncientFishDragon, self.AncientFishActivate)
        self.AddExecutor(A, CardId.GreatRighteousThief, self.GreatRighteousThiefBattleActivate)
        self.AddExecutor(A, CardId.SuperLibrarian, self.SuperLibrarianActivate)

        self.AddExecutor(ExecutorType.Repos, self.ElfnoteMonsterRepos)
        self.AddExecutor(ExecutorType.Repos, self.DefaultMonsterRepos)
        self.AddExecutor(ExecutorType.SpellSet, self.SpellSetCheck)

        self.NotToNegateIdList = [58699500, 20343502, 25451383, 19403423]
        self.NotToDestroySpellTrap = [50005218, 6767771]
        self.targetNegateIdList = [
            _CardId.EffectVeiler, _CardId.InfiniteImpermanence, _CardId.GhostMournerMoonlitChill,
            _CardId.BreakthroughSkill, 74003290, 67037924, 9753964, 66192538, 23204029, 73445448, 35103106,
            30286474, 45002991, 5795980, 38511382, 53742162, 30430448]

        self.summonCount = 1
        self.artSearched = False
        self.white10GyWhite7LineThisChain = False
        self.white10TwoZoneWhite7ChickenThisChain = False
        self.white10PickedGyChickenThisChain = False
        self.white10EnemyPickedCodesThisChain = []
        self.white10EnemyWindMissingDeckId = 0
        self.white10MissingPlaceLineThisChain = False
        self.redFieldPendingNegateTarget = None
        self.preferNegateCard = None
        self.nsChickenOffCenterForWhite10 = False
        self.chickenDodgeSynchroThisChain = False
        self.chickenDodgeSynchroCardId = 0
        self.accel2PreferWindChicken = False
        self.jailGateResolvedThisTurn = False

        self.currentNegateCardList = []
        self.currentDestroyCardList = []
        self.activatedCardIdList = []
        self.spSummonedCardIdList = []
        self.enemyPlaceThisTurn = []
        self.mediusSsByOwnGyEffect = []

    # --- helpers --------------------------------------------------------------------------------------------
    def CardStr(self, card):
        if card is None:
            return "null"
        name = card.Name or str(card.Id)
        return f"{name}@{card.Location}#{card.Sequence}"

    def SameFieldCard(self, a, b):
        if a is None or b is None:
            return False
        if a is b:
            return True
        return a.Id == b.Id and a.Controller == b.Controller and a.Location == b.Location and a.Sequence == b.Sequence

    def CheckCanBeTargeted(self, card, canBeTarget, selfType):
        if card is None:
            return True
        if canBeTarget:
            if card.IsShouldNotBeTarget():
                return False
            if (selfType & CardType.Monster) > 0 and card.IsShouldNotBeMonsterTarget():
                return False
            if (selfType & CardType.Spell) > 0 and card.IsShouldNotBeSpellTrapTarget():
                return False
            if (selfType & CardType.Trap) > 0 and (card.IsShouldNotBeSpellTrapTarget() and not card.IsDisabled()):
                return False
        return True

    def CheckWhetherNegated(self, disablecheck=True, toFieldCheck=False, type_=0, ignore41=False):
        Card = self.Card
        isMonster = type_ == 0 and Card.IsMonster()
        isMonster |= (type_ & CardType.Monster) != 0
        isSpellOrTrap = type_ == 0 and (Card.IsSpell() or Card.IsTrap())
        isSpellOrTrap |= ((type_ & CardType.Spell) != 0) or ((type_ & CardType.Trap) != 0)
        isCounter = (type_ & CardType.Counter) != 0
        if isSpellOrTrap and toFieldCheck and self.CheckSpellWillBeNegate(isCounter):
            return True
        if self.DefaultCheckWhetherCardIsNegated(Card):
            return True
        if isMonster and (toFieldCheck or Card.Location == CardLocation.MonsterZone):
            if not ignore41 and ((toFieldCheck and ((type_ & CardType.Link) == 0)) or Card.IsDefense()):
                if self.DefaultCheckWhetherNumber41IsActive():
                    return True
            if self.Enemy.HasInSpellZone(_CardId.SkillDrain, True, True):
                return True
        if disablecheck:
            return (Card.Location == CardLocation.MonsterZone or Card.Location == CardLocation.SpellZone) \
                and Card.IsDisabled() and Card.IsFaceup()
        return False

    def CheckSpellWillBeNegate(self, isCounter=False, target=None):
        if target is None:
            target = self.Card
        if target.Location != CardLocation.SpellZone and target.Location != CardLocation.Hand:
            return False
        Bot, Enemy = self.Bot, self.Enemy
        if Enemy.HasInMonstersZone(_CardId.NaturalExterio, True) and not isCounter:
            return True
        if target.IsSpell():
            if Enemy.HasInMonstersZone(_CardId.NaturiaBeast, True):
                return True
            if Enemy.HasInSpellZone(_CardId.ImperialOrder, True) or Bot.HasInSpellZone(_CardId.ImperialOrder, True):
                return True
            if Enemy.HasInMonstersZone(_CardId.SwordsmanLV7, True) or Bot.HasInMonstersZone(_CardId.SwordsmanLV7, True):
                return True
        if target.IsTrap() and (Enemy.HasInSpellZone(_CardId.RoyalDecreel, True) or Bot.HasInSpellZone(_CardId.RoyalDecreel, True)):
            return True
        return self.DefaultCheckWhetherSpellActivateWillBeNegated(target)

    def CheckLastChainShouldNegated(self):
        lastcard = self.Util.GetLastChainCard()
        if lastcard is None or lastcard.Controller != 1:
            return False
        return self.CheckCardShouldNegate(lastcard)

    def CheckCardShouldNegate(self, card):
        if card is None:
            return False
        if card in self.currentNegateCardList:
            return False
        if card.IsMonster() and card.HasSetcode(SetcodeTimeLord) and self.Duel.Phase == DuelPhase.Standby:
            return False
        if card.Id in self.NotToNegateIdList:
            return False
        if card.HasSetcode(_Setcode.Danger) and card.Location == CardLocation.Hand:
            return False
        if card.IsMonster() and card.Location == CardLocation.MonsterZone and card.HasPosition(CardPosition.Defence):
            if self.DefaultCheckWhetherNumber41IsActive():
                return False
        if self.DefaultCheckWhetherCardIsNegated(card):
            return False
        if self.Duel.Player == 1 and card.IsCode(_CardId.MulcharmyPurulia, _CardId.MulcharmyFuwalos, _CardId.MulcharmyNyalus):
            return False
        if card.IsDisabled():
            return False
        if self.CheckAtAdvantage() and self.Duel.Player == 0 and card.IsCode(_CardId.MulcharmyPurulia, _CardId.MulcharmyFuwalos, _CardId.MaxxC):
            return False
        return True

    def CheckAtAdvantage(self):
        if self.GetProblematicEnemyMonster() is not None:
            return False
        if not (self.Duel.Player == 0 or self.Bot.GetMonsterCount() > 0):
            return False
        return self.CheckHasStopBoard()

    def CheckHasStopBoard(self):
        Bot = self.Bot
        extraWhite10 = Bot.HasInExtra(CardId.White10)
        windCanJumpCenter = self.CanWindJumpToCenter()
        if windCanJumpCenter and Bot.HasInDeck(CardId.JailChicken) and extraWhite10:
            return True
        if self.HasChickenAndLevel6OnField() and extraWhite10:
            return True
        hasSynchro = any(c is not None and c.HasType(CardType.Synchro) and c.IsFaceup() for c in Bot.GetMonsters())
        gyWhite = Bot.HasInGraveyard(CardId.White7) or Bot.HasInGraveyard(CardId.White10)
        hasRedField = Bot.HasInSpellZone(CardId.RedField, True, True) or Bot.HasInHand(CardId.RedField) or Bot.HasInDeck(CardId.RedField)
        if (hasSynchro or gyWhite) and hasRedField:
            return True
        return False

    def CheckShouldNoMoreSpSummon(self, loc=None):
        if loc is None:
            if self.CheckAtAdvantage() and _CardId.MaxxC in self.enemyResolvedEffectIdList and self.DefaultCheckWhetherEnemyCanDraw():
                return True
            return False
        if self.CheckShouldNoMoreSpSummon():
            return True
        Duel = self.Duel
        if not self.DefaultCheckWhetherEnemyCanDraw() or (Duel.Turn > 1 and Duel.Phase < DuelPhase.Main2):
            return False
        if not self.CheckAtAdvantage() and Duel.Player == 0 and Duel.Turn > 1:
            if len(self.GetProblematicEnemyCardList(False, False, 0)) > 0:
                return False
        if _CardId.MulcharmyPurulia in self.enemyResolvedEffectIdList and (loc & CardLocation.Hand) != 0:
            return True
        if _CardId.MulcharmyFuwalos in self.enemyResolvedEffectIdList and (loc & (CardLocation.Deck | CardLocation.Extra)) != 0:
            return True
        if _CardId.MulcharmyNyalus in self.enemyResolvedEffectIdList and (loc & (CardLocation.Grave | CardLocation.Removed)) != 0:
            return True
        return False

    def CheckWhetherCanSummon(self):
        return self.Duel.Player == 0 and self.Duel.Phase < DuelPhase.End and self.summonCount > 0

    def IsOpeningComboTurn(self):
        Duel = self.Duel
        if Duel.Player != 0:
            return False
        if Duel.Turn == 1:
            return True
        if Duel.Turn == 2 and not Duel.IsFirst and self.Enemy.GetMonsterCount() == 0 and self.Enemy.GetSpellCount() == 0:
            return True
        return False

    def BanishRedirectPrevented(self):
        return _CardId.ArtifactLancea in self.resolvedEffectIdList \
            or self.Bot.HasInSpellZone(_CardId.ImperialIronWall, True, True) \
            or self.Enemy.HasInSpellZone(_CardId.ImperialIronWall, True, True)

    def CheckWhetherBotWillBeBanished(self, card=None, location=None):
        if location is not None:  # (CardType type, CardLocation location) overload
            if self.BanishRedirectPrevented():
                return False
            return self.DefaultCheckWhetherBotWillBeBanished(card, location)
        if self.BanishRedirectPrevented():
            return False
        if self.DefaultCheckWhetherBotWillBeBanished(card):
            return True
        if card is not None and card in self.mediusSsByOwnGyEffect:
            return True
        return False

    def MonstersLeavingFieldWillBeBanished(self):
        return self.CheckWhetherBotWillBeBanished(CardType.Monster, CardLocation.MonsterZone)

    def ShouldRerouteChickenSixUnderBanish(self):
        if self.Duel.Player != 0:
            return False
        if not self.HasChickenAndLevel6OnField():
            return False
        return self.MonstersLeavingFieldWillBeBanished()

    def IsFuwalosOnlyOpeningCompromise(self):
        if not self.IsOpeningComboTurn():
            return False
        lst = self.enemyResolvedEffectIdList
        if _CardId.MulcharmyFuwalos not in lst:
            return False
        if _CardId.MulcharmyPurulia in lst:
            return False
        if _CardId.MaxxC in lst:
            return False
        if not self.DefaultCheckWhetherEnemyCanDraw():
            return False
        return True

    def ShouldSkipExtraSynchroForFuwalosCompromise(self):
        return self.IsFuwalosOnlyOpeningCompromise()

    def CanChickenPlus3Accel(self):
        Bot = self.Bot
        if CardId.JailChicken + 1 in self.activatedCardIdList:
            return False
        if not Bot.HasInExtra(CardId.AccelSynchroStardust):
            return False
        if not any(c is not None and c.IsCode(CardId.JailChicken) and c.IsFaceup() for c in Bot.GetMonsters()):
            return False
        center = self.GetCenterMonster()
        if center is None:
            return False
        if center.IsCode(CardId.MediusTheInnocent) and center.Level + 3 + 1 == 8:
            return True
        if center.IsCode(CardId.JailChicken) and any(c is not None and c != center and c.IsCode(CardId.MediusTheInnocent)
                                                     and c.IsFaceup() for c in Bot.GetMonsters()):
            return True
        return False

    def ShouldFuwalosCompromiseIdleBaronne(self):
        if not self.IsFuwalosOnlyOpeningCompromise():
            return False
        if CardId.JailChicken + 1 not in self.activatedCardIdList:
            return False
        if not self.Bot.HasInExtra(CardId.BaronneDeFleur):
            return False
        return self.CanSynchroLevel(10)

    def ShouldFuwalosCompromiseIdleAccel(self):
        Bot = self.Bot
        if not self.IsFuwalosOnlyOpeningCompromise():
            return False
        if CardId.JailChicken + 1 not in self.activatedCardIdList:
            return False
        if not Bot.HasInExtra(CardId.AccelSynchroStardust):
            return False
        if not any(c is not None and c.IsCode(CardId.JailChicken) and c.IsFaceup() for c in Bot.GetMonsters()):
            return False
        center = self.GetCenterMonster()
        if center is None:
            return False
        if center.IsCode(CardId.MediusTheInnocent):
            return True
        if center.IsCode(CardId.JailChicken) and any(c is not None and c != center and c.IsCode(CardId.MediusTheInnocent)
                                                     and c.IsFaceup() for c in Bot.GetMonsters()):
            return True
        return False

    def OpeningYellowPlaceMissing(self):
        if self.Bot.HasInSpellZone(CardId.RedField, True, True):
            return False
        return self.Bot.HasInDeck(CardId.RedField) or self.Bot.HasInHand(CardId.RedField)

    def OpeningBluePlaceMissing(self):
        Bot = self.Bot
        needGreen = Bot.HasInDeck(CardId.GreenField) and not Bot.HasInSpellZone(CardId.GreenField) and not Bot.HasInHand(CardId.GreenField)
        if needGreen:
            return True
        if not Bot.HasInDeck(CardId.InnocentArt):
            return False
        if Bot.HasInHand(CardId.MediusTheInnocent):
            return False
        if not self.DefaultCheckWhetherBotCanSearch():
            return False
        return True

    def ShouldOpeningWhite10ForMissingPlace(self):
        Bot = self.Bot
        if not self.IsOpeningComboTurn():
            return False
        if self.IsFuwalosOnlyOpeningCompromise():
            return False
        if _CardId.MulcharmyFuwalos in self.enemyResolvedEffectIdList:
            return False
        if CardId.JailChicken not in self.activatedCardIdList:
            return False
        if Bot.HasInHand(CardId.ElvenotesRed) or Bot.HasInHand(CardId.ElvenotesBlue) \
                or Bot.HasInHand(CardId.ElvenotesYellow) or Bot.HasInHand(CardId.ElvenotesWind):
            return False
        if not self.HasChickenAndLevel6OnField():
            return False
        if self.CenterElvenotesStillNeedsIgnition():
            return False
        if not self.OpeningYellowPlaceMissing() and not self.OpeningBluePlaceMissing():
            return False
        if not self.White10EffectStillAvailable():
            return False
        if self.GetChickenPlus3SynchroLevel() != 10:
            return False
        if self.CheckShouldNoMoreSpSummon(CardLocation.Extra):
            return False
        if self.ShouldRerouteChickenSixUnderBanish():
            return False
        return True

    def ShouldFuwalosGreenFieldSummonRed(self):
        if not self.IsFuwalosOnlyOpeningCompromise():
            return False
        if CardId.GreenField in self.activatedCardIdList:
            return False
        if CardId.ElvenotesBlue not in self.activatedCardIdList:
            return False
        if not self.Bot.HasInDeck(CardId.ElvenotesRed):
            return False
        center = self.GetCenterMonster()
        if center is None or not center.IsCode(CardId.ElvenotesBlue):
            return False
        if self.CheckWhetherBotWillBeBanished(center):
            return False
        return self.IsGreenFieldAcceptableCost(center, CardAttribute.Fire)

    def ShouldFuwalosMediusSsChickenFromDeck(self):
        Bot = self.Bot
        if not self.IsFuwalosOnlyOpeningCompromise():
            return False
        if Bot.HasInGraveyard(CardId.JailChicken) and CardId.MixedHellGod not in self.activatedCardIdList:
            if Bot.HasInDeck(CardId.MixedHellGod) or Bot.HasInHand(CardId.MixedHellGod) or Bot.HasInSpellZone(CardId.MixedHellGod):
                return False
        return Bot.HasInDeck(CardId.JailChicken)

    def CanChickenPlus3Baronne(self):
        Bot = self.Bot
        if CardId.JailChicken + 1 in self.activatedCardIdList:
            return False
        if not Bot.HasInExtra(CardId.BaronneDeFleur):
            return False
        center = self.GetCenterMonster()
        if center is None:
            return False
        if center.IsCode(CardId.JailChicken):
            return any(c is not None and c != center and self.IsElvenotesSixStar(c) and c.IsFaceup() for c in Bot.GetMonsters())
        if self.IsElvenotesSixStar(center) and center.Level + 3 + 1 == 10:
            if any(c is not None and c.IsCode(CardId.JailChicken) and c.IsFaceup() for c in Bot.GetMonsters()):
                return True
            if Bot.HasInHand(CardId.JailChicken) and self.CheckWhetherCanSummon():
                return True
        return False

    def GetCenterMonster(self):
        return self.Bot.MonsterZone[2]

    def IsCenterEmpty(self):
        return self.Bot.MonsterZone[2] is None

    def IsElvenotesSixStar(self, card):
        if card is None:
            return False
        return card.IsCode(CardId.ElvenotesRed, CardId.ElvenotesBlue, CardId.ElvenotesYellow, CardId.ElvenotesWind)

    def IsPendulumZoneCard(self, card):
        if card is None:
            return False
        if card.Location == CardLocation.PendulumZone:
            return True
        if card.Location == CardLocation.SpellZone and (card.Sequence == 0 or card.Sequence == 4):
            return True
        return False

    def HasChickenAndLevel6OnField(self):
        mons = self.Bot.GetMonsters()
        chicken = any(c is not None and c.IsCode(CardId.JailChicken) and c.IsFaceup() for c in mons)
        six = any(c is not None and self.IsElvenotesSixStar(c) and c.IsFaceup() for c in mons)
        return chicken and six

    def CountFaceupChickenOnField(self):
        return sum(1 for c in self.Bot.GetMonsters() if c is not None and c.IsCode(CardId.JailChicken) and c.IsFaceup())

    def ShouldKeepSixStarForChickenPlus3(self):
        Bot = self.Bot
        if CardId.JailChicken + 1 in self.activatedCardIdList:
            return False
        if self.HandHasSixStarWaitingToSs():
            return False
        if self.Duel.Player == 0 and self.MonstersLeavingFieldWillBeBanished():
            return self.CanChickenPlus3Baronne()
        if self.IsFuwalosOnlyOpeningCompromise():
            return self.CanChickenPlus3Baronne()
        if not self.White10EffectStillAvailable():
            return False
        center = self.GetCenterMonster()
        if center is None:
            return False
        if center.IsCode(CardId.JailChicken):
            return any(c is not None and c != center and self.IsElvenotesSixStar(c) and c.IsFaceup() for c in Bot.GetMonsters())
        if self.IsElvenotesSixStar(center) and center.Level + 3 + 1 == 10:
            if Bot.HasInMonstersZone(CardId.JailChicken):
                return True
            if Bot.HasInHand(CardId.JailChicken) and self.CheckWhetherCanSummon():
                return True
        return False

    def White7StillWantsGyChicken(self):
        return self.Bot.HasInMonstersZone(CardId.White7) and CardId.White7 not in self.activatedCardIdList \
            and self.Bot.HasInGraveyard(CardId.JailChicken)

    def CanWindJumpToCenter(self):
        Bot = self.Bot
        if not Bot.HasInHand(CardId.ElvenotesWind):
            return False
        if CardId.ElvenotesWind in self.activatedCardIdList and sum(1 for c in Bot.Hand if c.IsCode(CardId.ElvenotesWind)) == 0:
            return False
        cost = self.GetWindCostCard()
        if cost is None:
            return False
        if self.IsCenterEmpty():
            return True
        center = self.GetCenterMonster()
        return center is not None and center == cost

    def IsUsedElvenotesBody(self, card):
        if card is None or not card.IsFaceup():
            return False
        if card.IsCode(CardId.ElvenotesBlue) and CardId.ElvenotesBlue in self.activatedCardIdList:
            return True
        if card.IsCode(CardId.ElvenotesRed) and not self.CanElvenotesRedSearch():
            return True
        if card.IsCode(CardId.ElvenotesYellow) and CardId.ElvenotesYellow in self.activatedCardIdList:
            return True
        return False

    def HasElvenotesSearchTargetInDeck(self):
        Bot = self.Bot
        return Bot.HasInDeck(CardId.ElvenotesBlue) or Bot.HasInDeck(CardId.ElvenotesYellow) \
            or Bot.HasInDeck(CardId.ElvenotesWind) or Bot.HasInDeck(CardId.JailChicken) \
            or Bot.HasInDeck(CardId.WhitePendulum)

    def CanElvenotesRedSearch(self):
        if CardId.ElvenotesRed in self.activatedCardIdList:
            return False
        if not self.DefaultCheckWhetherBotCanSearch():
            return False
        return self.HasElvenotesSearchTargetInDeck()

    def ShouldKeepGyChickenForMixedHellGod(self):
        Bot = self.Bot
        if CardId.MixedHellGod in self.activatedCardIdList:
            return False
        if not Bot.HasInGraveyard(CardId.JailChicken):
            return False
        if self.CountFreeMainMonsterZones() < 1:
            return False
        return Bot.HasInHand(CardId.MixedHellGod) or Bot.HasInSpellZone(CardId.MixedHellGod)

    def HasEightSynchroOnField(self):
        return any(c is not None and c.IsFaceup() and c.IsCode(CardId.CrystalWing, CardId.AccelSynchroStardust)
                   for c in self.Bot.GetMonsters())

    def ShouldSsYellowFirstAfterEightSynchro(self):
        if self.Duel.Player != 0:
            return False
        if not self.Bot.HasInHand(CardId.ElvenotesYellow):
            return False
        if self.HasEightSynchroOnField():
            return True
        if self.IsFuwalosOnlyOpeningCompromise() and any(c is not None and c.IsFaceup() and c.IsCode(CardId.BaronneDeFleur)
                                                         for c in self.Bot.GetMonsters()):
            return True
        return False

    def ShouldSsYellowFirstToPlaceRedField(self):
        Bot = self.Bot
        if self.Duel.Player != 0:
            return False
        if not Bot.HasInHand(CardId.ElvenotesYellow):
            return False
        if CardId.ElvenotesYellow in self.spSummonedCardIdList:
            return False
        if CardId.ElvenotesYellow in self.activatedCardIdList:
            return False
        if Bot.HasInSpellZone(CardId.RedField, True, True):
            return False
        if not Bot.HasInDeck(CardId.RedField) and not Bot.HasInHand(CardId.RedField):
            return False
        nsWithOneStar = self.CheckWhetherCanSummon() and any(c is not None and c.IsCode(CardId.JailChicken, _CardId.EffectVeiler)
                                                             for c in Bot.Hand)
        gyChicken = Bot.HasInGraveyard(CardId.JailChicken)
        return nsWithOneStar or gyChicken

    def HandHasSixStarWaitingToSs(self):
        Bot, ss = self.Bot, self.spSummonedCardIdList
        if Bot.HasInHand(CardId.ElvenotesRed) and CardId.ElvenotesRed not in ss:
            return True
        if Bot.HasInHand(CardId.ElvenotesBlue) and CardId.ElvenotesBlue not in ss:
            return True
        if Bot.HasInHand(CardId.ElvenotesYellow) and CardId.ElvenotesYellow not in ss:
            return True
        return False

    def ChickenGySearchWillAddHandSixStar(self):
        Bot, ss, act = self.Bot, self.spSummonedCardIdList, self.activatedCardIdList
        if self.Duel.Player != 0:
            return False
        if not self.DefaultCheckWhetherBotCanSearch():
            return False
        if CardId.JailChicken in act:
            return False
        if not Bot.HasInGraveyard(CardId.JailChicken):
            return False
        if Bot.HasInDeck(CardId.ElvenotesBlue) and CardId.ElvenotesBlue not in ss \
                and not Bot.HasInHand(CardId.ElvenotesBlue) and CardId.ElvenotesBlue not in act:
            return True
        if Bot.HasInDeck(CardId.ElvenotesYellow) and CardId.ElvenotesYellow not in ss \
                and not Bot.HasInHand(CardId.ElvenotesYellow) and CardId.ElvenotesYellow not in act:
            return True
        if Bot.HasInDeck(CardId.ElvenotesRed) and CardId.ElvenotesRed not in ss and not Bot.HasInHand(CardId.ElvenotesRed):
            return True
        return False

    def HasOtherElfnoteExtensionWithoutVeiler(self):
        Bot = self.Bot
        if Bot.HasInHand(CardId.JailChicken) and any(c is not None and self.IsElvenotesSixStar(c) and c.IsFaceup()
                                                     for c in Bot.GetMonsters()):
            return True
        if self.HasChickenAndLevel6OnField():
            return True
        if self.CanWindJumpToCenter():
            return True
        if self.CanMixedHellGodPendulumSs():
            return True
        if self.IsCenterEmpty() and self.HandHasSixStarWaitingToSs():
            return True
        if Bot.HasInSpellZone(CardId.GreenField) and not self.CheckShouldNoMoreSpSummon(CardLocation.Deck):
            center = self.GetCenterMonster()
            canEnterCenter = self.IsCenterEmpty() or self.IsUsedElvenotesBody(center)
            if canEnterCenter and (self.WantGreenFieldSummonWind() or Bot.HasInDeck(CardId.JailChicken)
                                   or Bot.HasInDeck(CardId.ElvenotesYellow) or Bot.HasInDeck(CardId.ElvenotesBlue)
                                   or Bot.HasInDeck(CardId.ElvenotesRed)):
                return True
        return False

    def WhitePendulumWaitingForElvenotesSs(self):
        if not self.DefaultCheckWhetherBotCanDraw():
            return False
        if CardId.WhitePendulum in self.activatedCardIdList:
            return False
        if self.Bot.HasInSpellZone(CardId.WhitePendulum):
            return True
        return self.Bot.HasInHand(CardId.WhitePendulum) and self.NeedPendulumScale()

    def ShouldNormalSummonVeilerForWhite7(self):
        if not self.CheckWhetherCanSummon():
            return False
        if self.CheckShouldNoMoreSpSummon(CardLocation.Extra):
            return False
        if not self.White7EffectStillAvailable():
            return False
        if CardId.White7 in self.activatedCardIdList:
            return False
        if not any(c is not None and self.IsElvenotesSixStar(c) and c.IsFaceup() for c in self.Bot.GetMonsters()):
            return False
        if self.HasOtherElfnoteExtensionWithoutVeiler():
            return False
        center = self.GetCenterMonster()
        blockedHandSix = self.HandHasSixStarWaitingToSs() and center is not None and self.IsElvenotesSixStar(center)
        return self.WhitePendulumWaitingForElvenotesSs() or blockedHandSix

    def CenterYellowStillNeedsToPlaceRedField(self):
        if self.Duel.Player != 0:
            return False
        center = self.GetCenterMonster()
        if center is None or not center.IsCode(CardId.ElvenotesYellow):
            return False
        if CardId.ElvenotesYellow in self.activatedCardIdList:
            return False
        if self.Bot.HasInSpellZone(CardId.RedField, True, True):
            return False
        return self.Bot.HasInDeck(CardId.RedField) or self.Bot.HasInHand(CardId.RedField)

    def EnemyHasFloodgateMonster(self):
        return any(c is not None and c.IsFaceup() and c.IsFloodgate() for c in self.Enemy.GetMonsters())

    def CenterElvenotesStillNeedsIgnition(self):
        Bot = self.Bot
        if self.Duel.Player != 0:
            return False
        center = self.GetCenterMonster()
        if center is None or not center.IsFaceup():
            return False
        if self.DefaultCheckWhetherCardIsNegated(center):
            return False
        if self.Enemy.HasInSpellZone(_CardId.SkillDrain, True, True):
            return False
        if center.IsDefense() and self.DefaultCheckWhetherNumber41IsActive():
            return False
        if center.IsCode(CardId.ElvenotesRed):
            return self.CanElvenotesRedSearch()
        if center.IsCode(CardId.ElvenotesBlue):
            if CardId.ElvenotesBlue in self.activatedCardIdList:
                return False
            if Bot.GetSpellCountWithoutField() >= 5:
                return False
            needGreen = Bot.HasInDeck(CardId.GreenField) and not Bot.HasInSpellZone(CardId.GreenField) \
                and not Bot.HasInHand(CardId.GreenField)
            if not self.DefaultCheckWhetherBotCanSearch() and not needGreen:
                return False
            return Bot.HasInDeck(CardId.GreenField) or Bot.HasInDeck(CardId.InnocentArt)
        if center.IsCode(CardId.ElvenotesYellow):
            return self.CenterYellowStillNeedsToPlaceRedField()
        return False

    def ShouldActivateRedFieldOnOurTurn(self):
        Bot = self.Bot
        white7OnChain = False
        if self.Duel.CurrentChain is not None:
            for card in self.Duel.CurrentChain:
                if card is not None and card.Controller == 0 and card.IsCode(CardId.White7):
                    white7OnChain = True
                    break
        white7CanReviveChicken = Bot.HasInMonstersZone(CardId.White7) \
            and (CardId.White7 not in self.activatedCardIdList or white7OnChain) \
            and (Bot.HasInGraveyard(CardId.JailChicken) or Bot.HasInHand(CardId.JailChicken))
        if white7CanReviveChicken:
            return False
        if self.White10OnFieldSecondEffectReady():
            return False
        center = self.GetCenterMonster()
        if self.CenterYellowStillNeedsToPlaceRedField():
            return False
        gyChicken = Bot.HasInGraveyard(CardId.JailChicken) and not Bot.HasInMonstersZone(CardId.JailChicken)
        gyWhite7 = Bot.HasInGraveyard(CardId.White7) and not Bot.HasInMonstersZone(CardId.White7)
        gyWhite10 = Bot.HasInGraveyard(CardId.White10) and not Bot.HasInMonstersZone(CardId.White10)
        hasSix = any(c is not None and self.IsElvenotesSixStar(c) and c.IsFaceup() for c in Bot.GetMonsters())
        extraOk = not self.CheckShouldNoMoreSpSummon(CardLocation.Extra)

        if center is not None and center.IsCode(CardId.ElvenotesYellow) and CardId.ElvenotesYellow in self.activatedCardIdList:
            if gyChicken and self.HandHasSixStarWaitingToSs():
                return True

        if gyChicken and extraOk:
            if hasSix and self.White7EffectStillAvailable():
                return True
            if Bot.HasInMonstersZone(CardId.White7) and (Bot.HasInExtra(CardId.AccelSynchroStardust) or Bot.HasInExtra(CardId.CrystalWing)):
                return True
            if CardId.JailChicken + 1 not in self.activatedCardIdList and self.White10EffectStillAvailable() \
                    and center is not None and self.IsElvenotesSixStar(center) and center.Level + 3 + 1 == 10:
                return True
            if center is not None and center.Level == 9 and self.White10EffectStillAvailable():
                return True
            if any(c is not None and c.IsFaceup() and c.Level == 4 for c in Bot.GetMonsters()) and Bot.HasInExtra(CardId.SuperLibrarian):
                return True

        if gyWhite7 and extraOk and Bot.HasInMonstersZone(CardId.JailChicken) \
                and (Bot.HasInExtra(CardId.AccelSynchroStardust) or Bot.HasInExtra(CardId.CrystalWing)):
            return True

        if gyWhite7 or gyWhite10:
            return True
        return False

    def RedFieldChickenEnablesSynchro(self):
        Bot = self.Bot
        if self.CheckShouldNoMoreSpSummon(CardLocation.Extra):
            return False
        center = self.GetCenterMonster()
        hasSix = any(c is not None and self.IsElvenotesSixStar(c) and c.IsFaceup() for c in Bot.GetMonsters())
        if hasSix and self.White7EffectStillAvailable():
            return True
        if hasSix and Bot.HasInExtra(CardId.FormulaAthleteLightning):
            return True
        if Bot.HasInMonstersZone(CardId.White7) and (Bot.HasInExtra(CardId.AccelSynchroStardust) or Bot.HasInExtra(CardId.CrystalWing)):
            return True
        if CardId.JailChicken + 1 not in self.activatedCardIdList and self.White10EffectStillAvailable() \
                and center is not None and self.IsElvenotesSixStar(center) and center.Level + 3 + 1 == 10:
            return True
        if center is not None and center.Level == 9 and self.White10EffectStillAvailable():
            return True
        if any(c is not None and c.IsFaceup() and c.Level == 4 for c in Bot.GetMonsters()) and Bot.HasInExtra(CardId.SuperLibrarian):
            return True
        return False

    def ShouldPreferRedFieldGyWhite7(self):
        Bot = self.Bot
        if not Bot.HasInGraveyard(CardId.White7) or Bot.HasInMonstersZone(CardId.White7):
            return False
        chickenOnField = any(c is not None and c.IsCode(CardId.JailChicken) and c.IsFaceup() for c in Bot.GetMonsters())
        canEight = Bot.HasInExtra([CardId.CrystalWing, CardId.AccelSynchroStardust, CardId.PSYFramelordOmega])
        if chickenOnField and canEight:
            return True
        return not self.RedFieldChickenEnablesSynchro()

    def ShouldNsChickenInsteadOfMixedHandSs(self):
        Bot = self.Bot
        if not self.CheckWhetherCanSummon():
            return False
        if not Bot.HasInHand(CardId.JailChicken) or Bot.HasInMonstersZone(CardId.JailChicken):
            return False
        if any(c is not None and (self.IsElvenotesSixStar(c) or c.Level == 4) for c in Bot.GetMonsters()):
            return True
        if self.HandHasSixStarWaitingToSs() and self.IsCenterEmpty():
            return True
        if self.CanWindJumpToCenter():
            return True
        return False

    def CanMixedHellGodPendulumSs(self):
        Bot = self.Bot
        if Bot.HasInGraveyard(CardId.JailChicken) and not self.CheckShouldNoMoreSpSummon(CardLocation.Grave):
            return True
        if Bot.HasInHand(CardId.JailChicken) and not Bot.HasInMonstersZone(CardId.JailChicken) \
                and not self.CheckShouldNoMoreSpSummon(CardLocation.Hand):
            skipForNs = self.ShouldNsChickenInsteadOfMixedHandSs()
            if skipForNs:
                return False
            return True
        return False

    def InnocentArtCanStillSearchMedius(self):
        if self.artSearched:
            return False
        if not self.DefaultCheckWhetherBotCanSearch():
            return False
        if not self.Bot.HasInDeck(CardId.MediusTheInnocent):
            return False
        return self.Bot.HasInHand(CardId.InnocentArt) or self.Bot.HasInSpellZone(CardId.InnocentArt)

    def JailGatePredictedMillWouldBeBanished(self):
        Bot = self.Bot
        chickenAlready = Bot.HasInMonstersZone(CardId.JailChicken) or Bot.HasInGraveyard(CardId.JailChicken)
        deckBanish = self.CheckWhetherBotWillBeBanished(CardType.Monster, CardLocation.Deck)
        extraBanish = self.CheckWhetherBotWillBeBanished(CardType.Monster, CardLocation.Extra)
        extraMill = Bot.HasInExtra(CardId.WhitePendulum) or Bot.HasInExtra(CardId.MixedHellGod)
        deckMill = Bot.HasInDeck(CardId.JailChicken) or Bot.HasInDeck(CardId.MixedHellGod) or Bot.HasInDeck(CardId.WhitePendulum)
        if not chickenAlready and Bot.HasInDeck(CardId.JailChicken) and not deckBanish:
            return False
        if extraMill and not extraBanish:
            return False
        if deckMill and not deckBanish:
            return False
        return True

    def CanMixedHellGodPendulumAtkBuff(self):
        Bot = self.Bot
        if CardId.JailGodGate in self.activatedCardIdList:
            return False
        if Bot.HasInHand(CardId.JailGodGate) or Bot.HasInSpellZone(CardId.JailGodGate):
            return False
        if not self.DefaultCheckWhetherBotCanSearch():
            return False
        if not Bot.HasInDeck(CardId.JailGodGate):
            return False
        if not Bot.HasInDeck(CardId.MediusTheInnocent):
            return False
        if Bot.HasInHand(CardId.MediusTheInnocent):
            return False
        if Bot.HasInMonstersZone(CardId.MediusTheInnocent):
            return False
        if self.ShouldSkipJailGodGateForAttack():
            return False
        if self.InnocentArtCanStillSearchMedius():
            return False
        if self.CheckWhetherBotWillBeBanished():
            return False
        if self.JailGatePredictedMillWouldBeBanished():
            return False
        return True

    def CountFreeMainMonsterZones(self):
        return 5 - len(self.Bot.GetMonstersInMainZone())

    def CountChickenInHandDeckGrave(self):
        count = self.Bot.GetCardCountInDeck(CardId.JailChicken)
        for card in self.Bot.Hand:
            if card is not None and card.IsCode(CardId.JailChicken):
                count += 1
        for card in self.Bot.Graveyard:
            if card is not None and card.IsCode(CardId.JailChicken):
                count += 1
        return count

    def CanSynchroToFreeMainZone(self):
        Bot, Duel = self.Bot, self.Duel
        if Duel.Player != 0:
            return False
        if Duel.Phase != DuelPhase.Main1 and Duel.Phase != DuelPhase.Main2:
            return False
        if self.CheckShouldNoMoreSpSummon(CardLocation.Extra):
            return False
        tuner = nonTuner = False
        for card in Bot.GetMonsters():
            if card is None or not card.IsFaceup() or card.Level <= 0:
                continue
            if card.HasType(CardType.Xyz | CardType.Link):
                continue
            if card.IsTuner():
                tuner = True
            else:
                nonTuner = True
        if not tuner or not nonTuner:
            return False
        return any(Bot.HasInExtra(i) for i in (
            CardId.White7, CardId.SuperLibrarian, CardId.AccelSynchroStardust, CardId.CrystalWing, CardId.White10,
            CardId.BaronneDeFleur, CardId.FormulaAthleteLightning, CardId.PSYFramelordOmega, CardId.ChaosAngel,
            CardId.BlackRoseDragon, CardId.AncientFishDragon, CardId.ThousandSpearDragon, CardId.AssaultBlackwing))

    def CanYellowBounceToHand(self, card):
        if card is None or not card.IsFaceup():
            return False
        if card.IsDisabled():
            return False
        if card.HasType(CardType.Pendulum):
            return False
        if not card.IsSpell() and not card.IsTrap():
            return False
        return card.HasType(CardType.Continuous | CardType.Equip | CardType.Field)

    def EnemyHasYellowBounceTarget(self):
        for card in self.Enemy.GetSpells():
            if self.CanYellowBounceToHand(card) and not self.IsAlreadyMarkedNegate(card):
                return True
        return False

    def RedBounceStat(self, card):
        if card is None:
            return 0
        atk = card.Attack
        def_ = card.GetDefensePower()
        if atk > def_:
            return atk
        return def_

    def GetRedBounceableMonsters(self):
        result = []
        for card in self.Enemy.GetMonsters():
            if card is None or not card.IsFaceup():
                continue
            if card.Level < 1 or card.Level > 6:
                continue
            if self.IsAlreadyMarkedNegate(card):
                continue
            result.append(card)
        return result

    def RedBounceBreaksSynchroPair(self, bounce):
        if bounce is None:
            return False
        hadTuner = hadNonTuner = tunerLeft = nonTunerLeft = False
        for card in self.Enemy.GetMonsters():
            if card is None or not card.IsFaceup():
                continue
            tuner = card.IsTuner()
            if tuner:
                hadTuner = True
            else:
                hadNonTuner = True
            if card == bounce:
                continue
            if tuner:
                tunerLeft = True
            else:
                nonTunerLeft = True
        return hadTuner and hadNonTuner and not (tunerLeft and nonTunerLeft)

    def ShouldActivateRedSwap(self):
        bounceable = self.GetRedBounceableMonsters()
        if len(bounceable) == 0:
            return False
        if (self.Duel.Phase == DuelPhase.Draw or self.Duel.Phase == DuelPhase.Standby) \
                and self.GetProblematicEnemyMonster() is None and not self.DefaultOnBecomeTarget():
            return False
        problems = self.GetProblematicEnemyCardList(False, False, CardType.Monster)
        for card in bounceable:
            if card in problems:
                return True
        for a in bounceable:
            for b in bounceable:
                if a != b and a.Level == b.Level:
                    return True
        for card in bounceable:
            if self.RedBounceBreaksSynchroPair(card):
                return True
        hasLink = any(c is not None and c.IsFaceup() and c.HasType(CardType.Link) for c in self.Enemy.GetMonsters())
        if hasLink:
            return True
        if self.DefaultOnBecomeTarget():
            return True
        return False

    def SelectRedBounceTarget(self, cards, min_, max_):
        bounceable = []
        for card in cards:
            if card is None or card.Controller != 1:
                continue
            if not card.IsFaceup() or card.Level < 1 or card.Level > 6:
                continue
            if self.IsAlreadyMarkedNegate(card):
                continue
            bounceable.append(card)
        ranked = []
        problems = self.GetProblematicEnemyCardList(False, False, CardType.Monster)
        for card in problems:
            if card in bounceable and card not in ranked:
                ranked.append(card)
        breakers = []
        for card in bounceable:
            if self.RedBounceBreaksSynchroPair(card) and card not in ranked:
                breakers.append(card)
        canBreakTuner = canBreakNonTuner = False
        for card in breakers:
            if card.IsTuner():
                canBreakTuner = True
            else:
                canBreakNonTuner = True
        if canBreakTuner and canBreakNonTuner:
            for card in breakers:
                if card.IsTuner() and card not in ranked:
                    ranked.append(card)
        for card in breakers:
            if card not in ranked:
                ranked.append(card)
        sameLevel = []
        for card in bounceable:
            if card in ranked:
                continue
            count = 0
            for other in bounceable:
                if other.Level == card.Level:
                    count += 1
            if count >= 2:
                sameLevel.append(card)
        sameLevel = sorted(sameLevel, key=lambda c: -self.RedBounceStat(c))
        for card in sameLevel:
            if card not in ranked:
                ranked.append(card)
        rest = sorted([c for c in bounceable if c not in ranked], key=lambda c: -self.RedBounceStat(c))
        ranked.extend(rest)
        for card in cards:
            if card is not None and card not in ranked:
                ranked.append(card)
        return self.Util.CheckSelectCount(ranked, cards, min_, max_)

    def WantGreenFieldSummonWind(self):
        if CardId.ElvenotesWind + 1 in self.activatedCardIdList:
            return False
        return self.Bot.HasInDeck(CardId.ElvenotesWind) and not self.Bot.HasInHand(CardId.ElvenotesWind) \
            and not self.Bot.HasInMonstersZone(CardId.ElvenotesWind)

    def CanGreenFieldSendCenterForWind(self, center):
        if center is None or center.Controller != 0:
            return False
        if not self.IsUsedElvenotesBody(center):
            return False
        if center.IsCode(CardId.ElvenotesYellow):
            return False
        if self.CheckWhetherBotWillBeBanished(center):
            return False
        return self.IsGreenFieldAcceptableCost(center, CardAttribute.Wind)

    def GetWindDodgeTarget(self):
        Duel, Bot = self.Duel, self.Bot
        if Duel.CurrentChainInfo is None or len(Duel.CurrentChainInfo) < 2:
            return None
        searchMonster = None
        searchIndex = -1
        for i, info in enumerate(Duel.CurrentChainInfo):
            if info is None or info.ActivatePlayer != 0:
                continue
            if not info.IsActivateCode(CardId.ElvenotesRed, CardId.ElvenotesBlue, CardId.ElvenotesYellow):
                continue
            if not info.HasLocation(CardLocation.MonsterZone):
                continue
            searchDesc = self.Util.GetStringId(info.ActivateId, 0)
            if info.ActivateDescription != searchDesc and info.ActivateDescription != -1:
                continue
            monster = info.RelatedCard
            if monster is None or monster.Controller != 0 or monster.Location != CardLocation.MonsterZone:
                if 0 <= info.ActivateSequence <= 4:
                    monster = Bot.MonsterZone[info.ActivateSequence]
            if monster is None or monster.Controller != 0 or monster.Location != CardLocation.MonsterZone:
                continue
            if not monster.IsCode(CardId.ElvenotesRed, CardId.ElvenotesBlue, CardId.ElvenotesYellow):
                continue
            searchMonster = monster
            searchIndex = i
            break
        if searchMonster is None:
            return None
        targeted = False
        if Duel.LastChainTargets is not None:
            for t in Duel.LastChainTargets:
                if self.SameFieldCard(t, searchMonster):
                    targeted = True
                    break
        if not targeted and self.Util.IsChainTarget(searchMonster):
            targeted = True
        if not targeted and Duel.ChainTargets is not None:
            for t in Duel.ChainTargets:
                if self.SameFieldCard(t, searchMonster):
                    targeted = True
                    break
        if not targeted and searchIndex >= 0:
            for i in range(searchIndex + 1, len(Duel.CurrentChainInfo)):
                info = Duel.CurrentChainInfo[i]
                if info is None or info.ActivatePlayer != 1 or info.Targets is None:
                    continue
                for t in info.Targets:
                    if self.SameFieldCard(t, searchMonster):
                        targeted = True
                        break
                if targeted:
                    break
        if not targeted:
            return None
        center = self.GetCenterMonster()
        if not self.IsCenterEmpty() and center is not None and not self.SameFieldCard(center, searchMonster):
            return None
        if self.CheckWhetherBotWillBeBanished(searchMonster):
            return None
        return searchMonster

    def GetWindCostCard(self, exclude=None):
        Bot, Duel, act = self.Bot, self.Duel, self.activatedCardIdList
        dodge = self.GetWindDodgeTarget()
        if dodge is not None:
            return dodge
        candidates = []
        candidates.extend(Bot.GetMonsters())
        candidates.extend(c for c in Bot.Hand if c is not None and c.IsMonster())
        candidates.extend(c for c in Bot.GetSpells() if c is not None and c.HasSetcode(SetcodeElvenotes))
        legal = []
        for card in candidates:
            if card is None:
                continue
            if exclude is not None and card == exclude:
                continue
            if card.IsCode(CardId.ElvenotesWind):
                windCopies = sum(1 for c in Bot.Hand if c is not None and c.IsCode(CardId.ElvenotesWind)) \
                    + sum(1 for c in Bot.GetMonsters() if c is not None and c.IsCode(CardId.ElvenotesWind) and c.IsFaceup())
                if windCopies < 2:
                    continue
            if not card.HasSetcode(SetcodeElvenotes):
                continue
            if self.IsPendulumZoneCard(card):
                continue
            if (card.Location == CardLocation.SpellZone or card.Location == CardLocation.MonsterZone) and card.IsFacedown():
                continue
            if card.IsCode(CardId.RedField) and Duel.Player == 0:
                continue
            if card.IsCode(CardId.RedField) and Duel.Player == 1 and CardId.RedField not in act:
                continue
            if not card.IsCode(CardId.ElvenotesRed, CardId.ElvenotesBlue, CardId.ElvenotesYellow, CardId.ElvenotesWind,
                               CardId.WhitePendulum, CardId.GreenField, CardId.InnocentArt, CardId.White7, CardId.White10,
                               CardId.JailChicken):
                if not card.HasSetcode(SetcodeElvenotes):
                    continue
            if card.IsCode(CardId.JailChicken):
                continue
            if card.HasType(CardType.Synchro) and not card.IsDisabled():
                continue
            if card.IsCode(CardId.White7, CardId.White10) and not card.IsDisabled():
                continue
            if card in Duel.CurrentChain:
                continue
            if card.IsCode(CardId.WhitePendulum) and self.IsPendulumZoneCard(card):
                continue
            if card.IsCode(CardId.GreenField) and CardId.GreenField not in act and Duel.Player == 0 \
                    and self.GetGreenFieldCostMonster() is not None:
                continue
            if card.IsCode(CardId.ElvenotesRed) and self.CanElvenotesRedSearch():
                continue
            if card.IsCode(CardId.ElvenotesBlue) and CardId.ElvenotesBlue not in act:
                continue
            if card.IsCode(CardId.ElvenotesYellow) and CardId.ElvenotesYellow not in act:
                continue
            if card.IsCode(CardId.InnocentArt) and not self.artSearched:
                continue
            if self.CheckWhetherBotWillBeBanished(card):
                continue
            legal.append(card)

        first = lambda f: next((c for c in legal if f(c)), None)
        if Duel.Player == 1:
            centerElvenotes = first(lambda c: c.Location == CardLocation.MonsterZone and c.Sequence == 2 and c.HasSetcode(SetcodeElvenotes))
            if centerElvenotes is not None:
                return centerElvenotes
            usedArt = first(lambda c: c.IsCode(CardId.InnocentArt) and self.artSearched)
            if usedArt is not None:
                return usedArt
            for id_ in (CardId.ElvenotesBlue, CardId.ElvenotesRed, CardId.ElvenotesYellow, CardId.WhitePendulum):
                dup = first(lambda c: c.Location == CardLocation.Hand and c.IsCode(id_)
                            and sum(1 for h in Bot.Hand if h is not None and h.IsCode(id_)) > 1)
                if dup is not None:
                    return dup
            green = first(lambda c: c.IsCode(CardId.GreenField))
            if green is not None:
                return green
            handOther = first(lambda c: c.Location == CardLocation.Hand and c.HasSetcode(SetcodeElvenotes) and not c.IsCode(CardId.ElvenotesWind))
            if handOther is not None:
                return handOther
            fieldOther = first(lambda c: (c.Location == CardLocation.MonsterZone or c.Location == CardLocation.SpellZone)
                               and c.HasSetcode(SetcodeElvenotes) and not c.IsCode(CardId.RedField))
            if fieldOther is not None:
                return fieldOther
            usedRedField = first(lambda c: c.IsCode(CardId.RedField) and CardId.RedField in act and c not in Duel.CurrentChain)
            if usedRedField is not None:
                return usedRedField
            return legal[0] if legal else None

        usedBlue = first(lambda c: c.Location == CardLocation.MonsterZone and c.IsCode(CardId.ElvenotesBlue))
        if usedBlue is not None:
            return usedBlue
        extraSix = [c for c in legal if c.Location == CardLocation.Hand and self.IsElvenotesSixStar(c)
                    and sum(1 for h in Bot.Hand if h is not None and h.IsCode(c.Id)) > 1]
        if len(extraSix) > 0:
            return extraSix[0]
        usedArtOwn = first(lambda c: c.IsCode(CardId.InnocentArt) and self.artSearched)
        if usedArtOwn is not None:
            return usedArtOwn
        usedGreen = first(lambda c: c.IsCode(CardId.GreenField) and CardId.GreenField in act
                          and (Bot.HasInMonstersZone(CardId.ElvenotesWind) or Bot.HasInHand(CardId.ElvenotesWind)))
        if usedGreen is not None:
            return usedGreen
        if Bot.HasInSpellZone(CardId.RedField) or (not Bot.HasInDeck(CardId.RedField) and not Bot.HasInHand(CardId.RedField)):
            yellow = first(lambda c: c.IsCode(CardId.ElvenotesYellow))
            if yellow is not None:
                return yellow
        greenOwn = first(lambda c: c.IsCode(CardId.GreenField))
        if greenOwn is not None:
            return greenOwn
        return legal[0] if legal else None

    def CanSynchroEightWithWhite7(self):
        Bot = self.Bot
        if self.Duel.Player == 1:
            return False
        if not Bot.HasInMonstersZone(CardId.White7):
            return False
        if not Bot.HasInMonstersZone(CardId.JailChicken):
            return False
        if self.CheckShouldNoMoreSpSummon(CardLocation.Extra):
            return False
        if Bot.HasInExtra(CardId.CrystalWing):
            return True
        if Bot.HasInExtra(CardId.AccelSynchroStardust) and not Bot.HasInMonstersZone(CardId.CrystalWing):
            return True
        if Bot.HasInExtra(CardId.PSYFramelordOmega):
            return True
        return False

    def CanSynchroSevenWithChicken(self):
        if not self.HasChickenAndLevel6OnField():
            return False
        if self.CheckShouldNoMoreSpSummon(CardLocation.Extra):
            return False
        return self.Bot.HasInExtra(CardId.FormulaAthleteLightning)

    def CanSynchroEightWithTwoChickens(self):
        Bot = self.Bot
        if self.CountFaceupChickenOnField() < 2:
            return False
        if self.CheckShouldNoMoreSpSummon(CardLocation.Extra):
            return False
        if not Bot.HasInExtra(CardId.PSYFramelordOmega) and not Bot.HasInExtra(CardId.CrystalWing) \
                and not (Bot.HasInExtra(CardId.AccelSynchroStardust) and not Bot.HasInMonstersZone(CardId.CrystalWing)):
            return False
        return any(c is not None and c.IsFaceup() and not c.IsTuner() and c.Level == 6
                   and not c.IsCode(CardId.CrystalWing, CardId.FormulaAthleteLightning, CardId.BaronneDeFleur, CardId.SuperLibrarian)
                   for c in Bot.GetMonsters())

    def CanLibrarianThenEightSynchro(self):
        Bot = self.Bot
        if not Bot.HasInMonstersZone(CardId.White7):
            return False
        if self.CountFaceupChickenOnField() < 2:
            return False
        if not any(c is not None and c.IsFaceup() and c.Level == 4 for c in Bot.GetMonsters()):
            return False
        if not Bot.HasInMonstersZone(CardId.CrystalWing):
            return False
        if Bot.HasInMonstersZone(CardId.SuperLibrarian, True, False, True):
            return False
        if not Bot.HasInExtra(CardId.AccelSynchroStardust):
            return False
        if self.CheckShouldNoMoreSpSummon(CardLocation.Extra):
            return False
        return True

    def CanChickenLevelForWhite10(self):
        if not self.White10EffectStillAvailable():
            return False
        if CardId.JailChicken + 1 in self.activatedCardIdList:
            return False
        chicken = next((c for c in self.Bot.GetMonsters() if c is not None and c.IsCode(CardId.JailChicken) and c.IsFaceup()), None)
        center = self.GetCenterMonster()
        if chicken is None or center is None or center.Level < 1:
            return False
        if center.IsCode(CardId.White7):
            return False
        return center.Level + 3 + chicken.Level == 10

    def ShouldWaitOwnChainToResolve(self, waitForWhiteP=False):
        Duel = self.Duel
        if Duel.CurrentChain is None or len(Duel.CurrentChain) == 0:
            return False
        if Duel.LastChainPlayer == 1:
            return False
        hasWaitable = False
        for card in Duel.CurrentChain:
            if card is not None and card.Controller == 1:
                return False
            if card is not None and card.IsCode(CardId.WhitePendulum) and not waitForWhiteP:
                continue
            if card is not None and card.Controller == 0:
                hasWaitable = True
        return hasWaitable

    def ShouldWaitOwnEnemyTurnDisruption(self, waitForWind, waitForChicken):
        Duel = self.Duel
        if Duel.CurrentChain is None or len(Duel.CurrentChain) == 0:
            return False
        if Duel.LastChainPlayer == 1:
            return False
        hasWaitable = False
        for card in Duel.CurrentChain:
            if card is None:
                continue
            if card.Controller == 1:
                return False
            if card.Controller != 0:
                continue
            if card.IsCode(CardId.White7, CardId.RedField, CardId.White10):
                hasWaitable = True
            elif waitForChicken and card.IsCode(CardId.JailChicken):
                hasWaitable = True
            elif waitForWind and card.IsCode(CardId.ElvenotesWind):
                hasWaitable = True
        return hasWaitable

    def Accel2OwnWaitableOnChain(self):
        chain = self.Duel.CurrentChain
        if chain is None or len(chain) == 0:
            return False
        lastWaitable = -1
        for i, card in enumerate(chain):
            if card is None or card.Controller != 0:
                continue
            if card.IsCode(CardId.JailChicken, CardId.White10, CardId.ElvenotesWind):
                lastWaitable = i
        if lastWaitable < 0:
            return False
        for i in range(lastWaitable + 1, len(chain)):
            card = chain[i]
            if card is not None and card.Controller == 1:
                return False
        return True

    def ShouldWaitChickenWhite10BeforeAccel2(self):
        Bot = self.Bot
        if self.Duel.Player != 1:
            return False
        if CardId.ElvenotesWind + 1 not in self.activatedCardIdList and not self.CheckShouldNoMoreSpSummon(CardLocation.Deck):
            windCenter = self.GetCenterMonster()
            if windCenter is not None and windCenter.IsFaceup() and windCenter.IsCode(CardId.ElvenotesWind):
                return True
        if Bot.HasInMonstersZone(CardId.White10, True, False, True) and CardId.White10 not in self.activatedCardIdList:
            return True
        if CardId.JailChicken + 1 in self.activatedCardIdList:
            return False
        if not self.White10EffectStillAvailable():
            return False
        if self.CanSynchroEightWithWhite7():
            return False
        if self.CenterElvenotesStillNeedsIgnition():
            return False
        chicken = None
        for card in Bot.GetMonsters():
            if card is not None and card.IsFaceup() and card.IsCode(CardId.JailChicken):
                chicken = card
                break
        if chicken is None:
            return False
        center = self.GetCenterMonster()
        if center is None or center == chicken or center.Level < 1:
            return False
        if center.Level + 3 + chicken.Level != 10:
            return False
        return True

    def ShouldWaitRedFieldBeforeWhite7(self):
        Duel = self.Duel
        if Duel.CurrentChain is None or len(Duel.CurrentChain) == 0:
            return False
        if Duel.LastChainPlayer == 1:
            return False
        for card in Duel.CurrentChain:
            if card is not None and card.Controller == 0 and card.IsCode(CardId.RedField):
                return True
        return False

    def EnemyHasTightDangerCard(self):
        for monster in self.Enemy.GetMonsters():
            if monster is None or monster.Data is None or not monster.IsFaceup():
                continue
            if monster.IsFloodgate() or monster.IsMonsterDangerous() or monster.IsMonsterInvincible():
                return True
        for spell in self.Enemy.GetSpells():
            if spell is None or spell.Data is None or not spell.IsFaceup():
                continue
            if spell.IsFloodgate():
                return True
        return False

    def EnemyHasTightDangerMonster(self):
        for monster in self.Enemy.GetMonsters():
            if monster is None or monster.Data is None or not monster.IsFaceup():
                continue
            if monster.IsFloodgate() or monster.IsMonsterDangerous() or monster.IsMonsterInvincible():
                return True
            if monster.HasType(CardType.Fusion | CardType.Ritual | CardType.Synchro | CardType.Xyz) \
                    or (monster.HasType(CardType.Link) and monster.LinkCount >= 2):
                return True
        bestBotAtk = self.Util.GetBestAttack(self.Bot)
        for monster in self.Enemy.GetMonsters():
            if monster is None or not monster.IsFaceup() or not monster.IsAttack():
                continue
            power = monster.GetDefensePower()
            if power > 0 and power >= bestBotAtk:
                return True
        return False

    def ShouldKeepThousandSpearForRedFieldCost(self):
        return any(c is not None and c.IsFaceup() and c.IsCode(CardId.ThousandSpearDragon) for c in self.Bot.GetMonsters()) \
            and self.Bot.HasInSpellZone(CardId.RedField, True)

    def ShouldAllowThousandSpearAsBaronneMaterial(self):
        if not self.Bot.HasInExtra(CardId.BaronneDeFleur):
            return False
        if self.CheckWhetherNegated(True, True, CardType.Monster):
            return False
        if self.Duel.Phase == DuelPhase.Main2:
            return True
        return self.Duel.Phase == DuelPhase.Main1 and self.EnemyHasTightDangerCard()

    def HasJailGodMonsterInDeck(self):
        Bot = self.Bot
        return Bot.HasInDeck(CardId.JailChicken) or Bot.HasInDeck(CardId.MixedHellGod) \
            or Bot.HasInDeck(CardId.WhitePendulum) or Bot.HasInDeck(CardId.MediusTheInnocent)

    def MediusEffect1CanFireAfterGySs(self):
        return CardId.MediusTheInnocent not in self.activatedCardIdList and self.HasJailGodMonsterInDeck()

    def CanFieldMakeExtraSynchro(self):
        Bot = self.Bot
        if Bot.HasInExtra(CardId.SuperLibrarian) and self.CanSynchroLevel(5):
            return True
        if (Bot.HasInExtra(CardId.White7) or Bot.HasInExtra(CardId.FormulaAthleteLightning)
                or Bot.HasInExtra(CardId.BlackRoseDragon) or Bot.HasInExtra(CardId.AssaultBlackwing)) and self.CanSynchroLevel(7):
            return True
        if (Bot.HasInExtra(CardId.CrystalWing) or Bot.HasInExtra(CardId.AccelSynchroStardust)
                or Bot.HasInExtra(CardId.PSYFramelordOmega) or Bot.HasInExtra(CardId.ChaosAngel)) and self.CanSynchroLevel(8):
            return True
        if (Bot.HasInExtra(CardId.AncientFishDragon) or Bot.HasInExtra(CardId.ThousandSpearDragon)) and self.CanSynchroLevel(9):
            return True
        if self.CanMakeWhite10Synchro():
            return True
        if Bot.HasInExtra(CardId.BaronneDeFleur) and self.CanSynchroLevel(10):
            return True
        return False

    def CanMediusGySsForLibrarianAfterEffect1Used(self):
        Bot = self.Bot
        if not Bot.HasInExtra(CardId.SuperLibrarian):
            return False
        faceup = [c for c in Bot.GetMonsters() if c is not None and c.IsFaceup()]
        tuners = [c for c in faceup if c.IsTuner()]
        if len(tuners) == 0:
            return False
        for tuner in tuners:
            if tuner is None or not tuner.IsCode(CardId.JailChicken):
                return False
        if self.CanFieldMakeExtraSynchro():
            return False
        chickenOnField = any(c.IsCode(CardId.JailChicken) for c in faceup)
        if not chickenOnField:
            return False
        fieldBounce = any(not c.IsCode(CardId.JailChicken) and not c.HasType(CardType.Synchro) for c in faceup)
        handBounce = any(c is not None and c.IsMonster() and not c.IsCode(CardId.JailChicken) for c in Bot.Hand) \
            and len(Bot.GetMonstersInMainZone()) < 5
        return fieldBounce or handBounce

    def EnemyHasUnbeatableJailGateDanger(self):
        bestBotAtk = self.Util.GetBestAttack(self.Bot)
        for monster in self.Enemy.GetMonsters():
            if monster is None or monster.Data is None or not monster.IsFaceup():
                continue
            if monster.IsFloodgate() or monster.IsMonsterDangerous() or monster.IsMonsterInvincible():
                return True
            extraBody = monster.HasType(CardType.Fusion | CardType.Ritual | CardType.Synchro | CardType.Xyz) \
                or (monster.HasType(CardType.Link) and monster.LinkCount >= 2)
            if extraBody and monster.GetDefensePower() >= bestBotAtk:
                return True
        for monster in self.Enemy.GetMonsters():
            if monster is None or not monster.IsFaceup() or not monster.IsAttack():
                continue
            power = monster.GetDefensePower()
            if power > 0 and power >= bestBotAtk:
                return True
        return False

    def ShouldSkipJailGodGateForAttack(self):
        Duel = self.Duel
        if Duel.Player != 0 or Duel.Phase != DuelPhase.Main1:
            return False
        canAttackThisTurn = not (Duel.Turn == 1 and Duel.IsFirst)
        if not canAttackThisTurn:
            return False
        if self.EnemyHasUnbeatableJailGateDanger():
            return False
        if self.CanFieldMakeExtraSynchro() or self.HandHasSixStarWaitingToSs():
            return True
        bestBotAtk = 0
        for monster in self.Bot.GetMonsters():
            if monster is not None and monster.IsFaceup() and monster.Attack > bestBotAtk:
                bestBotAtk = monster.Attack
        if bestBotAtk <= 0:
            return False
        if self.Enemy.LifePoints <= bestBotAtk:
            return True
        if self.Enemy.GetMonsterCount() == 0:
            return True
        bestEnemy = 0
        for monster in self.Enemy.GetMonsters():
            if monster is None:
                continue
            power = monster.GetDefensePower()
            if power > bestEnemy:
                bestEnemy = power
        return bestBotAtk > bestEnemy

    def HasEightSynchroInExtra(self):
        return self.Bot.HasInExtra([CardId.CrystalWing, CardId.AccelSynchroStardust, CardId.PSYFramelordOmega])

    def CanRbySwapNow(self, cardId, assumeCenterFilled):
        if isinstance(cardId, Card) or cardId is None:  # (ClientCard card, bool) overload
            if cardId is None:
                return False
            cardId = cardId.Id
        Duel = self.Duel
        if Duel.Player != 1:
            return False
        if not assumeCenterFilled and self.GetCenterMonster() is None:
            return False
        if cardId == CardId.ElvenotesRed:
            if CardId.ElvenotesRed + 3 in self.activatedCardIdList:
                return False
            return self.ShouldActivateRedSwap()
        if cardId == CardId.ElvenotesBlue:
            if CardId.ElvenotesBlue + 3 in self.activatedCardIdList:
                return False
            if Duel.Phase == DuelPhase.End:
                return False
            return len(self.Enemy.Hand) > 0
        if cardId == CardId.ElvenotesYellow:
            if CardId.ElvenotesYellow + 3 in self.activatedCardIdList:
                return False
            return self.EnemyHasYellowBounceTarget()
        return False

    def HasFaceupRbyReadyToSwap(self, cardId):
        for card in self.Bot.GetMonsters():
            if card is None or not card.IsFaceup() or not card.IsCode(cardId):
                continue
            if card.Sequence >= 5 or card.Sequence == 2:
                continue
            return True
        return False

    def GyRbyWorthWhite7Pull(self, cardId):
        if not self.Bot.HasInGraveyard(cardId):
            return False
        if not self.CanRbySwapNow(cardId, True):
            return False
        if self.HasFaceupRbyReadyToSwap(cardId):
            return False
        return True

    def White10EffectStillAvailable(self):
        return self.Bot.HasInExtra(CardId.White10) and CardId.White10 not in self.activatedCardIdList

    def White7EffectStillAvailable(self):
        return self.Bot.HasInExtra(CardId.White7) and CardId.White7 not in self.activatedCardIdList

    def ElvenotesSynchroSecondWouldBeNegatedOnSummon(self, synchroId):
        Duel = self.Duel
        if self.Enemy.HasInSpellZone(_CardId.SkillDrain, True, True):
            return True
        if not self.DefaultCheckWhetherNumber41IsActive():
            return False
        data = NamedCard.Get(synchroId)
        if data is None:
            return True
        if data.Attack == 0:
            return True
        if (Duel.Turn == 1 or Duel.Phase >= DuelPhase.Main2) and data.Attack <= data.Defense:
            return True
        if Duel.Player == 1 and (data.Defense >= data.Attack or data.Attack < 2000):
            return True
        return False

    def GetChickenPlus3SynchroLevel(self):
        center = self.GetCenterMonster()
        chicken = next((c for c in self.Bot.GetMonsters() if c is not None and c.IsCode(CardId.JailChicken) and c.IsFaceup()), None)
        if center is None or chicken is None or center.Level < 1:
            return 0
        return center.Level + 3 + chicken.Level

    def GetChickenDodgeSynchroId(self):
        lv = self.GetChickenPlus3SynchroLevel()
        if lv == 10 and self.White10EffectStillAvailable() and not self.ElvenotesSynchroSecondWouldBeNegatedOnSummon(CardId.White10):
            return CardId.White10
        if lv == 7 and self.White7EffectStillAvailable() and not self.ElvenotesSynchroSecondWouldBeNegatedOnSummon(CardId.White7):
            return CardId.White7
        return 0

    def ShouldChickenPlus3DodgeNegate(self):
        Duel = self.Duel
        if CardId.JailChicken + 1 in self.activatedCardIdList:
            return False
        if not any(c is not None and c.IsCode(CardId.JailChicken) and c.IsFaceup() for c in self.Bot.GetMonsters()):
            return False
        if Duel.CurrentChain is None or len(Duel.CurrentChain) < 2:
            return False
        if Duel.LastChainPlayer != 1:
            return False
        prev = Duel.CurrentChain[-2]
        if prev is None or prev.Controller != 0:
            return False
        if not self.IsElvenotesSixStar(prev):
            return False
        if prev.Location != CardLocation.MonsterZone or prev.Sequence != 2:
            return False
        targeted = self.Util.IsChainTarget(prev) \
            or (Duel.LastChainTargets is not None and any(t is not None and t == prev for t in Duel.LastChainTargets))
        last = Duel.CurrentChain[-1]
        ghostOgre = last is not None and last.IsCode(_CardId.GhostOgreAndSnowRabbit)
        if not targeted and not ghostOgre:
            return False
        synchroId = self.GetChickenDodgeSynchroId()
        if synchroId == 0:
            return False
        return True

    def White10OnFieldSecondEffectReady(self):
        if CardId.White10 in self.activatedCardIdList:
            return False
        if self.Duel.Phase != DuelPhase.Main1 and self.Duel.Phase != DuelPhase.Main2:
            return False
        white10 = next((c for c in self.Bot.GetMonsters() if c is not None and c.IsCode(CardId.White10)
                        and c.IsFaceup() and c.Sequence == 2 and not c.IsDisabled()), None)
        return white10 is not None

    def ShouldKeepAssaultBlackwingForBattle(self):
        Duel = self.Duel
        if Duel.Player != 0 or Duel.Phase != DuelPhase.Main1 or Duel.Turn <= 1:
            return False
        return any(c is not None and c.IsCode(CardId.AssaultBlackwing) and c.IsFaceup() and not c.IsDisabled()
                   for c in self.Bot.GetMonsters())

    def CanWindEnemyTurnWhite10Line(self):
        if not self.White10EffectStillAvailable():
            return False
        if not self.Bot.HasInDeck(CardId.JailChicken):
            return False
        if CardId.JailChicken + 1 in self.activatedCardIdList:
            return False
        if CardId.ElvenotesWind + 1 in self.activatedCardIdList:
            return False
        cost = self.GetWindCostCard()
        freeAfter = self.CountFreeMainMonsterZones()
        if cost is not None and cost.Location == CardLocation.MonsterZone:
            freeAfter += 1
        if self.IsCenterEmpty() or (cost is not None and self.GetCenterMonster() == cost):
            if freeAfter < 1:
                return False
        else:
            return False
        return True

    def DeckHasRbySwapTarget(self):
        for id_ in (CardId.ElvenotesRed, CardId.ElvenotesBlue, CardId.ElvenotesYellow):
            if not self.Bot.HasInDeck(id_):
                continue
            if self.CanRbySwapNow(id_, True):
                return True
        return False

    def IsBattlePhaseNow(self):
        return DuelPhase.Main1 < self.Duel.Phase < DuelPhase.Main2

    def EnemyHasMonsterThatBeatsChicken(self):
        chickenData = NamedCard.Get(CardId.JailChicken)
        chickenAtk = chickenData.Attack if chickenData is not None else 300
        return any(c is not None and c.IsAttack() and c.Attack > chickenAtk for c in self.Enemy.GetMonsters())

    def WantWindEnemyTurnSsChicken(self):
        if self.IsBattlePhaseNow():
            return False
        if not self.Bot.HasInDeck(CardId.JailChicken):
            return False
        if not self.White10EffectStillAvailable():
            return False
        if CardId.JailChicken + 1 in self.activatedCardIdList:
            return False
        return True

    def CanSynchroLevel(self, level):
        monsters = [c for c in self.Bot.GetMonsters() if c is not None and c.IsFaceup()]
        tuners = [c for c in monsters if c.IsTuner()]
        nonTuners = [c for c in monsters if not c.IsTuner()]
        for tuner in tuners:
            for nonTuner in nonTuners:
                if tuner.Level + nonTuner.Level == level:
                    return True
        for tuner in tuners:
            for i in range(len(nonTuners)):
                for j in range(i + 1, len(nonTuners)):
                    if tuner.Level + nonTuners[i].Level + nonTuners[j].Level == level:
                        return True
        return False

    def CanMakeWhite10Synchro(self):
        if not self.White10EffectStillAvailable():
            return False
        monsters = [c for c in self.Bot.GetMonsters() if c is not None and c.IsFaceup()]
        tuners = [c for c in monsters if c.IsTuner()]
        spellNonTuners = [c for c in monsters if not c.IsTuner() and c.HasRace(CardRace.SpellCaster)]
        for tuner in tuners:
            for nonTuner in spellNonTuners:
                if tuner.Level + nonTuner.Level == 10:
                    return True
        for tuner in tuners:
            for i in range(len(spellNonTuners)):
                for j in range(i + 1, len(spellNonTuners)):
                    if tuner.Level + spellNonTuners[i].Level + spellNonTuners[j].Level == 10:
                        return True
        return False

    def ShouldPreferWhite10Synchro(self):
        if self.ShouldRerouteChickenSixUnderBanish():
            return False
        if self.ShouldFuwalosCompromiseIdleBaronne():
            return False
        return self.CanMakeWhite10Synchro()

    def IsLightOrDark(self, card):
        if card is None:
            return False
        return card.HasAttribute(CardAttribute.Light | CardAttribute.Dark)

    def IsChaosAngelTunerSlot(self, card):
        return card is not None and (card.IsTuner() or self.IsLightOrDark(card))

    def IsChaosAngelNonTunerLd(self, card):
        return card is not None and not card.IsTuner() and self.IsLightOrDark(card)

    def ChaosAngelPairOk(self, a, b):
        if a is None or b is None or a == b:
            return False
        if a.Level + b.Level != 10:
            return False
        return (self.IsChaosAngelTunerSlot(a) and self.IsChaosAngelNonTunerLd(b)) \
            or (self.IsChaosAngelTunerSlot(b) and self.IsChaosAngelNonTunerLd(a))

    def GetChaosAngelMaterialPool(self, allowFaLine):
        monsters = [c for c in self.Bot.GetMonsters() if c is not None and c.IsFaceup()]
        monsters = [c for c in monsters if not c.IsCode(CardId.CrystalWing, CardId.BaronneDeFleur, CardId.White10)]
        if self.ShouldKeepAssaultBlackwingForBattle():
            monsters = [c for c in monsters if not c.IsCode(CardId.AssaultBlackwing) or c.IsDisabled()]
        if not allowFaLine:
            monsters = [c for c in monsters if not c.IsCode(CardId.FormulaAthleteLightning)]
        else:
            monsters = [c for c in monsters if not c.IsCode(CardId.FormulaAthleteLightning) or c.Level == 5]
        return monsters

    def FindChaosAngelMaterials(self, allowFaLine):
        monsters = self.GetChaosAngelMaterialPool(allowFaLine)
        FA = CardId.FormulaAthleteLightning
        yellow = next((c for c in monsters if c.IsCode(CardId.ElvenotesYellow)), None)
        medius = next((c for c in monsters if c.IsCode(CardId.MediusTheInnocent)), None)
        if self.ChaosAngelPairOk(yellow, medius):
            return [yellow, medius]
        for i in range(len(monsters)):
            for j in range(i + 1, len(monsters)):
                if monsters[i].IsCode(FA) or monsters[j].IsCode(FA):
                    continue
                if self.ChaosAngelPairOk(monsters[i], monsters[j]):
                    return [monsters[i], monsters[j]]
        if allowFaLine:
            librarian = next((c for c in monsters if c.IsCode(CardId.SuperLibrarian)), None)
            fa = next((c for c in monsters if c.IsCode(FA) and c.Level == 5), None)
            if self.ChaosAngelPairOk(librarian, fa):
                return [librarian, fa]
        T, L = self.IsChaosAngelTunerSlot, self.IsChaosAngelNonTunerLd
        for i in range(len(monsters)):
            for j in range(i + 1, len(monsters)):
                for k in range(j + 1, len(monsters)):
                    a, b, c = monsters[i], monsters[j], monsters[k]
                    if a.Level + b.Level + c.Level != 10:
                        continue
                    if not allowFaLine and (a.IsCode(FA) or b.IsCode(FA) or c.IsCode(FA)):
                        continue
                    ok = (T(a) and L(b) and L(c)) or (T(b) and L(a) and L(c)) or (T(c) and L(a) and L(b))
                    if ok:
                        return [a, b, c]
        return None

    def EnemyHasChaosAngelBanishTarget(self):
        if self.BanishRedirectPrevented():
            return False
        for card in self.Enemy.GetMonsters():
            if card is None or card.HasType(CardType.Token):
                continue
            if self.CheckCanBeTargeted(card, True, CardType.Monster):
                return True
        for card in self.Enemy.GetSpells():
            if card is None:
                continue
            if self.CheckCanBeTargeted(card, True, CardType.Monster):
                return True
        return False

    def ShouldSummonChaosAngel(self):
        if not self.Bot.HasInExtra(CardId.ChaosAngel):
            return False
        banish = self.EnemyHasChaosAngelBanishTarget()
        mats = self.FindChaosAngelMaterials(banish)
        if mats is None:
            return False
        if self.CanMakeWhite10Synchro() and not self.ShouldRerouteChickenSixUnderBanish():
            return False
        if banish:
            return True
        if self.CanSynchroLevel(10):
            return False
        if self.Duel.Phase == DuelPhase.Main2:
            return True
        atk = 0
        for mat in mats:
            if mat is not None:
                atk += mat.Attack
        return atk < 3500

    def NeedCenterCard(self, cardId):
        return cardId in (CardId.ElvenotesRed, CardId.ElvenotesBlue, CardId.ElvenotesYellow, CardId.White7, CardId.White10)

    def CountHandNegates(self):
        hand = self.Bot.Hand
        count = 0
        for id_ in (_CardId.MaxxC, _CardId.AshBlossom, _CardId.LockBird, _CardId.EffectVeiler):
            count += sum(1 for c in hand if c is not None and c.IsCode(id_))
        return count

    def CheckThousandSpearGoingFirstLine(self):
        Bot = self.Bot
        if len(Bot.Hand) >= 4 and any(c is not None and c.IsFaceup() and c.IsCode(CardId.SuperLibrarian) and not c.IsDisabled()
                                      for c in Bot.GetMonsters()):
            return True
        if self.CountHandNegates() < 2:
            return False
        if not (Bot.HasInSpellZone(CardId.RedField, True, True) or Bot.HasInHand(CardId.RedField) or Bot.HasInDeck(CardId.RedField)
                or any(c is not None and c.IsCode(CardId.ElvenotesYellow) for c in Bot.GetMonsters())):
            return False
        return True

    def EnemyHasThousandSpearBanishWorth(self):
        Enemy = self.Enemy
        if len(Enemy.Graveyard) >= 2:
            return True
        if len(self.GetDangerousCardinEnemyGrave(False)) > 0:
            return True
        if len(self.GetProblematicEnemyCardList(False, False, 0)) > 0:
            return True
        for card in Enemy.GetMonsters():
            if card is None:
                continue
            if card.HasType(CardType.Fusion | CardType.Ritual | CardType.Synchro | CardType.Xyz | CardType.Link):
                return True
            if card.IsFaceup():
                return True
        for card in Enemy.GetSpells():
            if card is None or not card.IsFaceup():
                continue
            if card.HasType(CardType.Continuous | CardType.Equip | CardType.Field | CardType.Pendulum):
                return True
        return False

    def CheckThousandSpearGoingSecondLine(self):
        if not any(c is not None for c in self.Bot.Hand):
            return False
        banisable = 0
        for card in self.Enemy.GetMonsters():
            if card is not None:
                banisable += 1
        for card in self.Enemy.GetSpells():
            if card is not None:
                banisable += 1
        banisable += len(self.Enemy.Graveyard)
        if banisable < 2:
            return False
        return self.EnemyHasThousandSpearBanishWorth()

    def GetDangerousCardinEnemyGrave(self, onlyMonster=False):
        grave = self.Enemy.Graveyard
        result = GetMatchingCards(grave, lambda card: (not onlyMonster or card.IsMonster()) and (
            card.HasSetcode(SetcodeOrcust) or card.HasSetcode(SetcodePhantomKnight) or card.HasSetcode(SetcodeHorus)))
        dangerMonsterIdList = [99937011, 63542003, 9411399, 28954097, 30680659]
        result.extend(GetMatchingCards(grave, lambda card: card.Id in dangerMonsterIdList))
        return result

    def GetProblematicEnemyMonster(self, attack=0, canBeTarget=False, ignoreCurrentDestroy=False, selfType=0):
        Enemy, destroy = self.Enemy, self.currentDestroyCardList
        ok = lambda c: ignoreCurrentDestroy or c not in destroy
        floodagateCard = _FirstByAttackDesc(c for c in Enemy.GetMonsters() if c is not None and c.Data is not None and ok(c)
                                            and c.IsFloodgate() and c.IsFaceup() and self.CheckCanBeTargeted(c, canBeTarget, selfType))
        if floodagateCard is not None:
            return floodagateCard
        dangerCard = _FirstByAttackDesc(c for c in Enemy.MonsterZone if c is not None and c.Data is not None and ok(c)
                                        and c.IsMonsterDangerous() and c.IsFaceup() and self.CheckCanBeTargeted(c, canBeTarget, selfType))
        if dangerCard is not None:
            return dangerCard
        invincibleCard = _FirstByAttackDesc(c for c in Enemy.MonsterZone if c is not None and c.Data is not None and ok(c)
                                            and c.IsMonsterInvincible() and c.IsFaceup() and self.CheckCanBeTargeted(c, canBeTarget, selfType))
        if invincibleCard is not None:
            return invincibleCard
        equippedCard = _FirstByAttackDesc(c for c in Enemy.MonsterZone if c is not None and c.Data is not None and ok(c)
                                          and len(c.EquipCards) > 0 and self.CheckCanBeTargeted(c, canBeTarget, selfType))
        if equippedCard is not None:
            return equippedCard
        enemyExtraMonster = _FirstByAttackDesc(
            c for c in Enemy.MonsterZone if c is not None and ok(c)
            and (c.HasType(CardType.Fusion | CardType.Ritual | CardType.Synchro | CardType.Xyz) or (c.HasType(CardType.Link) and c.LinkCount >= 2))
            and self.CheckCanBeTargeted(c, canBeTarget, selfType))
        if enemyExtraMonster is not None:
            return enemyExtraMonster
        if attack >= 0:
            if attack == 0:
                attack = self.Util.GetBestAttack(self.Bot)
            betterCard = _FirstByAttackDesc(
                card for card in Enemy.MonsterZone if card is not None and card.GetDefensePower() >= attack
                and card.GetDefensePower() > 0 and card.IsAttack() and self.CheckCanBeTargeted(card, canBeTarget, selfType)
                and ok(card))
            if betterCard is not None:
                return betterCard
        return None

    def GetProblematicEnemyCardList(self, canBeTarget=False, ignoreSpells=False, selfType=0):
        Enemy, Duel, destroy = self.Enemy, self.Duel, self.currentDestroyCardList
        tgt = lambda c: self.CheckCanBeTargeted(c, canBeTarget, selfType)
        resultList = []
        floodagateList = _OrderByAttackDesc(c for c in Enemy.MonsterZone if c is not None and c.Data is not None and c not in destroy
                                            and c.IsFloodgate() and c.IsFaceup() and tgt(c))
        resultList.extend(floodagateList)
        problemEnemySpellList = [c for c in Enemy.SpellZone if c is not None and c.Data is not None and c not in resultList
                                 and c not in destroy and c.IsFloodgate() and c.IsFaceup() and tgt(c)]
        resultList.extend(problemEnemySpellList)
        dangerList = _OrderByAttackDesc(c for c in Enemy.MonsterZone if c is not None and c.Data is not None and c not in resultList
                                        and c not in destroy and c.IsMonsterDangerous() and c.IsFaceup() and tgt(c))
        if len(dangerList) > 0 and (Duel.Player == 0 or (DuelPhase.Main1 < Duel.Phase < DuelPhase.Main2)):
            resultList.extend(dangerList)
        invincibleList = _OrderByAttackDesc(c for c in Enemy.MonsterZone if c is not None and c.Data is not None and c not in resultList
                                            and c not in destroy and c.IsMonsterInvincible() and c.IsFaceup() and tgt(c))
        resultList.extend(invincibleList)
        enemyMonsters = _OrderByAttackDesc(c for c in Enemy.GetMonsters() if c not in destroy)
        for target in enemyMonsters:
            if (target.HasType(CardType.Fusion | CardType.Ritual | CardType.Synchro | CardType.Xyz)
                    or (target.HasType(CardType.Link) and target.LinkCount >= 2)) \
                    and target not in resultList and tgt(target):
                resultList.append(target)
        spells = [c for c in Enemy.GetSpells() if c.IsFaceup() and c not in destroy
                  and c.HasType(CardType.Equip | CardType.Pendulum | CardType.Field | CardType.Continuous) and tgt(c)
                  and c.Id not in self.NotToDestroySpellTrap]
        if len(spells) > 0 and not ignoreSpells:
            resultList.extend(spells)
        return resultList

    def GetNormalEnemyTargetList(self, canBeTarget=True, ignoreCurrentDestroy=True, selfType=0):
        Enemy, neg, destroy = self.Enemy, self.currentNegateCardList, self.currentDestroyCardList
        targetList = self.GetProblematicEnemyCardList(canBeTarget, False, selfType)
        enemyMonster = [card for card in Enemy.GetMonsters() if card is not None and card.IsFaceup() and card not in targetList
                        and (not ignoreCurrentDestroy or card not in neg) and card not in destroy]
        enemyMonster.sort(key=CompareCardAttack)
        enemyMonster.reverse()
        targetList.extend(enemyMonster)
        targetList.extend(self.Util.ShuffleList([card for card in Enemy.GetSpells() if card is not None
                                                 and (not ignoreCurrentDestroy or card not in neg) and card not in destroy
                                                 and card in self.enemyPlaceThisTurn and card.IsFacedown()]))
        targetList.extend(self.Util.ShuffleList([card for card in Enemy.GetSpells() if card is not None
                                                 and (not ignoreCurrentDestroy or card not in neg) and card not in destroy
                                                 and card not in self.enemyPlaceThisTurn and card.IsFacedown()]))
        targetList.extend(self.Util.ShuffleList([card for card in Enemy.GetMonsters() if card is not None and card.IsFacedown()
                                                 and (not ignoreCurrentDestroy or card not in neg) and card not in destroy]))
        return targetList

    def GetMonsterListForTargetNegate(self, canBeTarget=False, selfType=0):
        resultList = []
        if self.CheckWhetherNegated():
            return resultList
        target = next((card for card in self.Enemy.MonsterZone if card is not None and card.Data is not None
                       and card.IsMonsterShouldBeDisabledBeforeItUseEffect() and card.IsFaceup() and not card.IsShouldNotBeTarget()
                       and self.CheckCanBeTargeted(card, canBeTarget, selfType) and not self.IsAlreadyMarkedNegate(card)), None)
        if target is not None:
            resultList.append(target)
        for chainingCard in self.Duel.CurrentChain:
            if chainingCard is None or chainingCard.Controller != 1:
                continue
            if chainingCard.Location != CardLocation.MonsterZone or chainingCard.IsDisabled():
                continue
            if not self.CheckCanBeTargeted(chainingCard, canBeTarget, selfType):
                continue
            if self.IsAlreadyMarkedNegate(chainingCard):
                continue
            if chainingCard.HasPosition(CardPosition.Defence) and self.DefaultCheckWhetherNumber41IsActive():
                continue
            if not self.CheckCardShouldNegate(chainingCard):
                continue
            resultList.append(chainingCard)
        return resultList

    def IsAlreadyMarkedNegate(self, card):
        if card is None:
            return False
        p = self.preferNegateCard
        if p is not None:
            if p == card:
                return True
            if p.Id == card.Id and p.Controller == card.Controller and p.Location == card.Location and p.Sequence == card.Sequence:
                return True
        for marked in self.currentNegateCardList:
            if marked is None:
                continue
            if marked == card:
                return True
            if marked.Id == card.Id and marked.Controller == card.Controller and marked.Location == card.Location \
                    and marked.Sequence == card.Sequence:
                return True
        return False

    def ShouldSkipAncientFishDestroy(self, card):
        if card is None:
            return True
        if card.IsDisabled():
            return True
        if self.IsAlreadyMarkedNegate(card):
            return True
        if card in self.currentDestroyCardList:
            return True
        r = self.redFieldPendingNegateTarget
        if r is not None:
            if r == card:
                return True
            if r.Id == card.Id and r.Controller == card.Controller and r.Location == card.Location and r.Sequence == card.Sequence:
                return True
        return False

    def GetAncientFishDestroyTargets(self):
        result = []
        for card in self.GetProblematicEnemyCardList(True, False, 0):
            if self.ShouldSkipAncientFishDestroy(card):
                continue
            result.append(card)
        return result

    def EnemyHasFaceupCardOnChain(self):
        chain = self.Duel.CurrentChain
        if chain is None or len(chain) == 0:
            return False
        for card in chain:
            if card is None or card.Controller != 1:
                continue
            if not card.IsOnField() or not card.IsFaceup():
                continue
            if not self.CheckCardShouldNegate(card):
                continue
            return True
        return False

    def EnemyHasWorthNegate(self):
        if self.EnemyHasFaceupCardOnChain():
            return True
        problems = self.GetProblematicEnemyCardList(False, False, CardType.Monster | CardType.Spell | CardType.Trap)
        for card in problems:
            if card is None or not card.IsFaceup():
                continue
            if not self.CheckCardShouldNegate(card):
                continue
            serious = card.IsFloodgate() or card.IsMonsterDangerous() or card.IsMonsterInvincible() or (card.IsSpell() or card.IsTrap())
            onlyGenericExtra = card.IsMonster() and (card.HasType(CardType.Fusion | CardType.Ritual | CardType.Synchro | CardType.Xyz)
                                                     or (card.HasType(CardType.Link) and card.LinkCount >= 2)) and not serious
            if onlyGenericExtra:
                continue
            return True
        return False

    def GetRedFieldDisableOrder(self, cards):
        picked = []
        chain = self.Duel.CurrentChain
        if chain is not None:
            for i in range(len(chain) - 1, -1, -1):
                chainCard = chain[i]
                if chainCard is None or chainCard.Controller != 1:
                    continue
                if not chainCard.IsOnField() or not chainCard.IsFaceup():
                    continue
                if chainCard not in cards or chainCard in picked:
                    continue
                if not self.CheckCardShouldNegate(chainCard):
                    continue
                picked.append(chainCard)
        problems = self.GetProblematicEnemyCardList(False, False, CardType.Monster | CardType.Spell | CardType.Trap)
        for card in problems:
            if card is not None and card in cards and card not in picked and self.CheckCardShouldNegate(card):
                picked.append(card)
        for card in cards:
            if card is not None and card.IsFaceup() and card.Controller == 1 and card not in picked and self.CheckCardShouldNegate(card):
                picked.append(card)
        for card in cards:
            if card is not None and card.IsFaceup() and card not in picked:
                picked.append(card)
        return picked

    def SetRedFieldPendingNegate(self):
        negateCandidates = []
        for monster in self.Enemy.GetMonsters():
            if monster is not None and monster.IsFaceup():
                negateCandidates.append(monster)
        for spell in self.Enemy.GetSpells():
            if spell is not None and spell.IsFaceup():
                negateCandidates.append(spell)
        negateOrder = self.GetRedFieldDisableOrder(negateCandidates)
        if len(negateOrder) > 0:
            self.redFieldPendingNegateTarget = negateOrder[0]

    def GetFieldCostMonster(self, forWhite7, forWhite10, preferThousandSpear, avoidAttribute=0, forNegate=False,
                            allowHandTriggers=False):
        Bot, act = self.Bot, self.activatedCardIdList
        ok = lambda c: self.CostAttributeOk(c, forWhite7, forWhite10, avoidAttribute)
        if preferThousandSpear:
            spear = next((c for c in Bot.GetMonsters() if c is not None and c.IsCode(CardId.ThousandSpearDragon)), None)
            if spear is not None and ok(spear):
                return spear
        if self.Duel.Player == 0:
            unusedMediusFirst = next((c for c in Bot.Hand if c is not None and c.IsCode(CardId.MediusTheInnocent)
                                      and CardId.MediusTheInnocent not in act and CardId.MediusTheInnocent + 1 not in act
                                      and ok(c)), None)
            if unusedMediusFirst is not None:
                return unusedMediusFirst
        mulcharmy = next((c for c in Bot.Hand if c is not None and c.IsCode(_CardId.MulcharmyFuwalos, _CardId.MulcharmyPurulia,
                                                                           _CardId.MulcharmyNyalus)), None)
        if mulcharmy is not None and ok(mulcharmy):
            return mulcharmy
        if Bot.GetMonsterCount() > 0:
            thief = next((c for c in Bot.Hand if c is not None and c.IsCode(CardId.GreatRighteousThief)), None)
            if thief is not None and ok(thief):
                return thief
        usedBlue = next((c for c in Bot.GetMonsters() if c is not None and c.IsCode(CardId.ElvenotesBlue)
                         and CardId.ElvenotesBlue in act), None)
        if usedBlue is not None and ok(usedBlue):
            return usedBlue
        usedRed = next((c for c in Bot.GetMonsters() if c is not None and c.IsCode(CardId.ElvenotesRed)
                        and self.IsUsedElvenotesBody(c)), None)
        if usedRed is not None and ok(usedRed):
            return usedRed
        usedYellow = next((c for c in Bot.GetMonsters() if c is not None and c.IsCode(CardId.ElvenotesYellow)
                           and CardId.ElvenotesYellow in act), None)
        if usedYellow is not None and ok(usedYellow) and not self.ShouldKeepSixStarForChickenPlus3():
            return usedYellow
        unusedMedius = next((c for c in Bot.Hand if c is not None and c.IsCode(CardId.MediusTheInnocent)
                             and CardId.MediusTheInnocent + 1 not in act and ok(c)), None)
        if unusedMedius is not None:
            return unusedMedius
        if CardId.ElvenotesWind + 1 in act:
            usedWind = next((c for c in Bot.GetMonsters() if c is not None and c.IsCode(CardId.ElvenotesWind) and ok(c)), None)
            if usedWind is not None:
                return usedWind
        if forNegate:
            wind = next((c for c in list(Bot.Hand) + Bot.GetMonsters() if c is not None and c.IsCode(CardId.ElvenotesWind)
                         and ok(c)), None)
            if wind is not None:
                return wind
            unusedSix = next((c for c in list(Bot.Hand) + Bot.GetMonsters() if c is not None
                              and c.IsCode(CardId.ElvenotesBlue, CardId.ElvenotesYellow, CardId.ElvenotesRed) and ok(c)), None)
            if unusedSix is not None:
                return unusedSix
        for monster in list(Bot.Hand) + Bot.GetMonsters():
            if monster is None or not monster.IsMonster():
                continue
            if monster.IsCode(CardId.ElvenotesWind, CardId.JailChicken, CardId.ElvenotesRed) and not self.IsUsedElvenotesBody(monster) \
                    and not forNegate:
                continue
            if monster.IsCode(CardId.MediusTheInnocent) and monster.Location == CardLocation.MonsterZone \
                    and CardId.MediusTheInnocent + 1 not in act:
                continue
            if monster.IsCode(_CardId.MaxxC, _CardId.AshBlossom, _CardId.LockBird, _CardId.EffectVeiler) and not allowHandTriggers:
                continue
            if monster.IsCode(CardId.White7, CardId.White10) or monster.HasType(CardType.Synchro):
                continue
            if self.ShouldKeepSixStarForChickenPlus3() and monster.Location == CardLocation.MonsterZone \
                    and self.IsElvenotesSixStar(monster):
                continue
            if ok(monster):
                return monster
        return None

    def CostAttributeOk(self, cost, forWhite7, forWhite10, avoidAttribute=0):
        if cost is None:
            return False
        if self.CheckWhetherBotWillBeBanished(cost):
            return False
        if avoidAttribute != 0 and cost.HasAttribute(avoidAttribute):
            return False
        if forWhite7 and cost.HasAttribute(CardAttribute.Fire):
            return False
        if forWhite10 and cost.HasAttribute(CardAttribute.Light):
            return False
        return True

    def GetRedFieldCostMonster(self, canWhite7, canWhite10, preferSpear, forNegate, avoidAttribute=0):
        if forNegate:
            if canWhite10:
                cost10 = self.GetFieldCostMonster(False, True, preferSpear, avoidAttribute, forNegate)
                if cost10 is not None:
                    return cost10
            if canWhite7:
                cost7 = self.GetFieldCostMonster(True, False, preferSpear, avoidAttribute, forNegate)
                if cost7 is not None:
                    return cost7
            return self.GetFieldCostMonster(False, False, preferSpear, avoidAttribute, forNegate)
        if canWhite7:
            cost7 = self.GetFieldCostMonster(True, False, preferSpear, avoidAttribute, forNegate)
            if cost7 is not None:
                return cost7
        if canWhite10:
            cost10 = self.GetFieldCostMonster(False, True, preferSpear, avoidAttribute, forNegate)
            if cost10 is not None:
                return cost10
        return self.GetFieldCostMonster(False, False, preferSpear, avoidAttribute, forNegate)

    def IsGreenFieldEndBoardCost(self, cost):
        if cost is None:
            return True
        if cost.HasType(CardType.Synchro):
            return True
        return cost.IsCode(CardId.White7, CardId.White10, CardId.ThousandSpearDragon, CardId.CrystalWing,
                           CardId.PSYFramelordOmega, CardId.StardustDragon, CardId.SuperLibrarian, CardId.AccelSynchroStardust,
                           CardId.FormulaAthleteLightning, CardId.BaronneDeFleur)

    def GreenFieldDeckHasSsForCost(self, cost):
        if cost is None or cost.Data is None:
            return False
        costAttr = cost.Data.Attribute
        for id_ in (CardId.ElvenotesWind, CardId.JailChicken, CardId.ElvenotesYellow, CardId.ElvenotesBlue, CardId.ElvenotesRed):
            if not self.Bot.HasInDeck(id_):
                continue
            data = NamedCard.Get(id_)
            if data is None:
                continue
            if (data.Attribute & costAttr) == 0:
                return True
        return False

    def IsGreenFieldAcceptableCost(self, cost, avoidAttribute):
        if cost is None or not cost.IsMonster():
            return False
        if self.IsGreenFieldEndBoardCost(cost):
            return False
        if not self.CostAttributeOk(cost, False, False, avoidAttribute):
            return False
        if not self.GreenFieldDeckHasSsForCost(cost):
            return False
        if cost.Location == CardLocation.Hand and self.CountFreeMainMonsterZones() < 1:
            return False
        return True

    def GetGreenFieldCostMonster(self, avoidAttribute=0):
        Bot = self.Bot
        preferred = self.GetFieldCostMonster(False, False, False, avoidAttribute, False, True)
        if self.IsGreenFieldAcceptableCost(preferred, avoidAttribute):
            return preferred
        if CardId.ElvenotesWind + 1 in self.activatedCardIdList:
            for card in list(Bot.Hand) + Bot.GetMonsters():
                if card is not None and card.IsCode(CardId.ElvenotesWind) and self.IsGreenFieldAcceptableCost(card, avoidAttribute):
                    return card
        for monster in list(Bot.Hand) + Bot.GetMonsters():
            if not self.IsGreenFieldAcceptableCost(monster, avoidAttribute):
                continue
            if monster.IsCode(_CardId.MaxxC, _CardId.AshBlossom, _CardId.LockBird, _CardId.EffectVeiler) \
                    and sum(1 for c in Bot.Hand if c is not None and c.IsCode(monster.Id)) <= 1:
                continue
            return monster
        return None

    def ShouldKeepInHand(self, card):
        Bot, act = self.Bot, self.activatedCardIdList
        if card is None:
            return False
        handCount = lambda id_: sum(1 for c in Bot.Hand if c is not None and c.IsCode(id_))
        if card.IsCode(_CardId.MaxxC, _CardId.AshBlossom, _CardId.LockBird):
            return True
        if card.IsCode(CardId.ElvenotesWind):
            return True
        if card.IsCode(_CardId.EffectVeiler) and handCount(_CardId.EffectVeiler) <= 1:
            return True
        if card.IsCode(CardId.ElvenotesRed) and self.CanElvenotesRedSearch() and handCount(CardId.ElvenotesRed) <= 1 \
                and not Bot.HasInMonstersZone(CardId.ElvenotesRed):
            return True
        if card.IsCode(CardId.MediusTheInnocent) and CardId.MediusTheInnocent + 1 not in act and handCount(CardId.MediusTheInnocent) <= 1:
            return True
        if card.IsCode(CardId.GreenField) and not Bot.HasInSpellZone(CardId.GreenField) and CardId.GreenField not in act:
            return True
        if card.IsCode(CardId.RedField) and not Bot.HasInSpellZone(CardId.RedField):
            return True
        if card.IsCode(CardId.JailChicken) and not Bot.HasInMonstersZone(CardId.JailChicken) and not Bot.HasInGraveyard(CardId.JailChicken) \
                and handCount(CardId.JailChicken) <= 1:
            return True
        return False

    def SelectElfnoteTributes(self, cards, min_, max_):
        if cards is None or len(cards) == 0:
            return None
        ranked = []
        problems = self.GetProblematicEnemyCardList(False, True, CardType.Monster)
        for card in problems:
            if card is not None and card in cards and card not in ranked:
                ranked.append(card)
        for card in cards:
            if card is not None and card.Controller == 1 and card not in ranked:
                ranked.append(card)
        unusedMedius = None
        for card in cards:
            if card is not None and card.Controller == 0 and card.IsCode(CardId.MediusTheInnocent) \
                    and CardId.MediusTheInnocent not in self.activatedCardIdList and card not in ranked:
                unusedMedius = card
                break
        if unusedMedius is not None:
            ranked.append(unusedMedius)
        for card in cards:
            if card is not None and card.Controller == 0 \
                    and card.IsCode(_CardId.MulcharmyFuwalos, _CardId.MulcharmyPurulia, _CardId.MulcharmyNyalus) and card not in ranked:
                ranked.append(card)
        for card in cards:
            if card is not None and card.Controller == 0 and card.IsCode(CardId.MediusTheInnocent) and card not in ranked:
                ranked.append(card)
        for card in cards:
            if card is None or card in ranked:
                continue
            if card.Location == CardLocation.Hand and self.ShouldKeepInHand(card):
                continue
            ranked.append(card)
        for card in cards:
            if card is not None and card not in ranked:
                ranked.append(card)
        return self.Util.CheckSelectCount(ranked, cards, min_, max_)

    def CanMediusGySsAfterThiefTribute(self):
        if CardId.MediusTheInnocent + 1 in self.activatedCardIdList:
            return False
        if self.CheckShouldNoMoreSpSummon(CardLocation.Grave):
            return False
        medius, otherMonsters = [], []
        for card in self.Bot.Hand:
            if card is None or not card.IsMonster():
                continue
            if card.IsCode(CardId.GreatRighteousThief):
                continue
            if card.IsCode(CardId.MediusTheInnocent):
                medius.append(card)
            else:
                otherMonsters.append(card)
        if len(medius) == 0:
            return False
        if not any(c is not None and not self.CheckWhetherBotWillBeBanished(c) for c in medius):
            return False
        need = 2
        enemy = self.Enemy.GetMonsterCount()
        if enemy > need:
            enemy = need
        need -= enemy
        if need <= 0:
            return False
        need -= 1
        extraMedius = len(medius) - 1
        dumps = len(otherMonsters)
        if need > dumps + extraMedius:
            return False
        dumpsLeft, extraLeft = dumps, extraMedius
        if need > 0:
            useDump = need if need < dumpsLeft else dumpsLeft
            dumpsLeft -= useDump
            need -= useDump
        if need > 0:
            extraLeft -= need
        return dumpsLeft + extraLeft > 0

    def SelectMediusToDeck(self, cards, min_, max_):
        keepWhite10Mat = self.CanChickenLevelForWhite10() or self.ShouldPreferWhite10Synchro() \
            or (self.ShouldRerouteChickenSixUnderBanish() and self.CanChickenPlus3Baronne())
        center = self.GetCenterMonster()
        ranked = []
        handChicken = None
        for card in cards:
            if card is not None and card.Location == CardLocation.Hand and card.IsCode(CardId.JailChicken):
                handChicken = card
                break
        if not self.CheckWhetherCanSummon() and handChicken is not None:
            ranked.append(handChicken)
            return self.Util.CheckSelectCount(ranked, cards, min_, max_)
        for card in cards:
            if card is not None and card.Location == CardLocation.MonsterZone and self.IsUsedElvenotesBody(card) and card not in ranked:
                if keepWhite10Mat and center is not None and card == center:
                    continue
                ranked.append(card)
        for card in cards:
            if card is not None and card.Location == CardLocation.Hand and card.IsCode(CardId.MediusTheInnocent) and card not in ranked:
                ranked.append(card)
        for card in cards:
            if card is not None and card.IsCode(_CardId.MulcharmyFuwalos, _CardId.MulcharmyPurulia, _CardId.MulcharmyNyalus) \
                    and card not in ranked:
                ranked.append(card)
        for card in cards:
            if card is None or card in ranked:
                continue
            if card.IsCode(CardId.JailChicken, CardId.ElvenotesWind, CardId.GreatRighteousThief):
                continue
            if keepWhite10Mat and center is not None and card == center:
                continue
            ranked.append(card)
        for card in cards:
            if card is not None and card not in ranked:
                ranked.append(card)
        return self.Util.CheckSelectCount(ranked, cards, min_, max_)

    def SelectHandDiscard(self, cards, min_, max_):
        dumpFirst = [_CardId.MulcharmyFuwalos, _CardId.MulcharmyPurulia, _CardId.MulcharmyNyalus,
                     CardId.ElvenotesBlue, CardId.ElvenotesYellow, CardId.GreatRighteousThief, CardId.InnocentArt, CardId.GreenField]
        ranked = []
        for id_ in dumpFirst:
            for card in cards:
                if card is not None and card.IsCode(id_) and not self.ShouldKeepInHand(card) and card not in ranked:
                    ranked.append(card)
        for card in cards:
            if card is not None and not self.ShouldKeepInHand(card) and card not in ranked:
                ranked.append(card)
        for card in cards:
            if card is not None and card not in ranked:
                ranked.append(card)
        return self.Util.CheckSelectCount(ranked, cards, min_, max_)

    def ComboIsStuck(self):
        Bot = self.Bot
        hasSix = Bot.HasInHand(CardId.ElvenotesRed) or Bot.HasInHand(CardId.ElvenotesBlue) or Bot.HasInHand(CardId.ElvenotesYellow) \
            or Bot.HasInMonstersZone(CardId.ElvenotesRed) or Bot.HasInMonstersZone(CardId.ElvenotesBlue) \
            or Bot.HasInMonstersZone(CardId.ElvenotesYellow) or Bot.HasInMonstersZone(CardId.ElvenotesWind)
        hasChicken = Bot.HasInHand(CardId.JailChicken) or Bot.HasInMonstersZone(CardId.JailChicken) \
            or Bot.HasInGraveyard(CardId.JailChicken) or Bot.HasInDeck(CardId.JailChicken)
        if not hasSix or not hasChicken:
            return True
        if not self.DefaultCheckWhetherBotCanSearch() or _CardId.AshBlossom in self.enemyResolvedEffectIdList:
            if not any(c is not None and c.HasType(CardType.Synchro) for c in Bot.GetMonsters()):
                return True
        return False

    def WindGyRecycleAvailable(self):
        return CardId.ElvenotesWind + 2 not in self.activatedCardIdList

    def CanAccelSecondSynchroUseWindForSeven(self):
        if not self.WindGyRecycleAvailable():
            return False
        wind = next((c for c in self.Bot.GetMonsters() if c is not None and c.IsFaceup() and c.IsCode(CardId.ElvenotesWind)), None)
        if wind is None:
            return False
        chicken = next((c for c in self.Bot.GetMonsters() if c is not None and c.IsFaceup() and c.IsCode(CardId.JailChicken)), None)
        if chicken is None:
            return False
        return chicken.Level + wind.Level == 7

    def SelectAccel2WindChickenMaterials(self, cards, min_, max_):
        if not self.accel2PreferWindChicken or cards is None or len(cards) == 0:
            return None
        ranked = []
        for card in cards:
            if card is not None and card.IsCode(CardId.ElvenotesWind) and card not in ranked:
                ranked.append(card)
        for card in cards:
            if card is not None and card.IsCode(CardId.JailChicken) and card not in ranked:
                ranked.append(card)
        if len(ranked) == 0:
            return None
        for card in cards:
            if card is None or card in ranked:
                continue
            if card.IsCode(CardId.ElvenotesRed, CardId.ElvenotesBlue, CardId.ElvenotesYellow):
                continue
            ranked.append(card)
        for card in cards:
            if card is not None and card not in ranked:
                ranked.append(card)
        return self.Util.CheckSelectCount(ranked, cards, min_, max_)

    def PreferWindAmongNonTuners(self, nonTuners):
        if not self.WindGyRecycleAvailable():
            return nonTuners
        preferred = []
        for card in nonTuners:
            if card is not None and card.IsCode(CardId.ElvenotesWind):
                preferred.append(card)
        for card in nonTuners:
            if card is not None and card not in preferred:
                preferred.append(card)
        return preferred

    def FindSynchroMaterials(self, level, avoidCrystalWing, forBaronne=False):
        monsters = [c for c in self.Bot.GetMonsters() if c is not None and c.IsFaceup()]
        if avoidCrystalWing:
            monsters = [c for c in monsters if not c.IsCode(CardId.CrystalWing)]
        monsters = [c for c in monsters if not c.IsCode(CardId.FormulaAthleteLightning, CardId.BaronneDeFleur)]
        if self.ShouldKeepAssaultBlackwingForBattle():
            monsters = [c for c in monsters if not c.IsCode(CardId.AssaultBlackwing) or c.IsDisabled()]
        if self.ShouldKeepThousandSpearForRedFieldCost() and not (forBaronne and self.ShouldAllowThousandSpearAsBaronneMaterial()):
            monsters = [c for c in monsters if not c.IsCode(CardId.ThousandSpearDragon)]
        tuners = [c for c in monsters if c.IsTuner()]
        nonTuners = self.PreferWindAmongNonTuners([c for c in monsters if not c.IsTuner()])
        if level == 9:
            stardust = next((c for c in monsters if c is not None and c.IsCode(CardId.StardustDragon)), None)
            chicken = next((c for c in monsters if c is not None and c.IsCode(CardId.JailChicken) and c.IsTuner()), None)
            if stardust is not None and chicken is not None and chicken.Level + stardust.Level == 9:
                return [chicken, stardust]
        for tuner in tuners:
            for nonTuner in nonTuners:
                if tuner.Level + nonTuner.Level == level:
                    return [tuner, nonTuner]
        for tuner in tuners:
            for i in range(len(nonTuners)):
                for j in range(i + 1, len(nonTuners)):
                    if tuner.Level + nonTuners[i].Level + nonTuners[j].Level == level:
                        return [tuner, nonTuners[i], nonTuners[j]]
        for i in range(len(tuners)):
            for j in range(i + 1, len(tuners)):
                for nonTuner in nonTuners:
                    if tuners[i].Level + tuners[j].Level + nonTuner.Level == level:
                        return [tuners[i], tuners[j], nonTuner]
        return None

    def SelectSynchroMaterials(self, level, avoidCrystalWing, forBaronne=False):
        mats = self.FindSynchroMaterials(level, avoidCrystalWing, forBaronne)
        if mats is None:
            return False
        self.AI.SelectMaterials(mats)
        return True

    def BomberDestroyLevel(self, card):
        if card is None or not card.IsFaceup():
            return 0
        if card.HasType(CardType.Xyz | CardType.Link):
            return 0
        if card.Data is not None and card.Data.Level > 0:
            return card.Data.Level
        return card.Level if card.Level > 0 else 0

    def BomberEffectWouldDestroy(self, card):
        if card is None or not card.IsFaceup():
            return False
        if card.Controller == 0 and card.Sequence == 2 and self.Bot.HasInSpellZone(CardId.GreenField, True, True):
            return False
        return True

    def EstimateBomberDamage(self, leaving=None, includeBomber=False):
        levelSum = 0
        for card in self.Bot.GetMonsters() + self.Enemy.GetMonsters():
            if card is None:
                continue
            if leaving is not None and card in leaving:
                continue
            if not self.BomberEffectWouldDestroy(card):
                continue
            levelSum += self.BomberDestroyLevel(card)
        if includeBomber:
            bomber = NamedCard.Get(CardId.HelldiveBomber)
            levelSum += bomber.Level if bomber is not None and bomber.Level > 0 else 7
        return levelSum * 200

    def ShouldSkipBattleForBomber(self):
        if not self.HelldiveBomberDestroyEffectCanApply():
            return False
        for monster in self.Enemy.GetMonsters():
            if monster is None or monster.Data is None or not monster.IsFaceup():
                continue
            if monster.IsFloodgate():
                return False
        bomberOnField = any(c is not None and c.IsFaceup() and c.IsCode(CardId.HelldiveBomber) and not c.IsDisabled()
                            for c in self.Bot.GetMonsters())
        if bomberOnField:
            dmg = self.EstimateBomberDamage()
        elif self.HasChickenAndLevel6OnField() and self.Bot.HasInExtra(CardId.HelldiveBomber):
            mats = self.FindSynchroMaterials(7, True)
            if mats is None:
                return False
            dmg = self.EstimateBomberDamage(mats, True)
        else:
            return False
        if dmg < self.Enemy.LifePoints:
            return False
        if self.jailGateResolvedThisTurn:
            return True
        return self.Enemy.GetMonsterCount() > 0

    def HelldiveBomberDestroyEffectCanApply(self):
        if CardId.HelldiveBomber in self.activatedCardIdList:
            return False
        if self.ElvenotesSynchroSecondWouldBeNegatedOnSummon(CardId.HelldiveBomber):
            return False
        return True

    def ShouldDeferSynchroForHelldiveBomber(self):
        if self.Duel.Turn == 1:
            return False
        if not self.HelldiveBomberDestroyEffectCanApply():
            return False
        if not self.Bot.HasInExtra(CardId.HelldiveBomber):
            return False
        if any(c is not None and c.IsFaceup() and c.IsCode(CardId.HelldiveBomber) and not c.IsDisabled() for c in self.Bot.GetMonsters()):
            return False
        mats = self.FindSynchroMaterials(7, True)
        if mats is None:
            return False
        return self.EstimateBomberDamage(mats, True) > self.Enemy.LifePoints

    def JailGateCannotRemove(self):
        return self.BanishRedirectPrevented()

    def JailGateGyBanishReady(self):
        if CardId.JailGodGate + 1 in self.activatedCardIdList:
            return False
        if not self.Bot.HasInGraveyard(CardId.JailGodGate):
            return False
        if self.JailGateCannotRemove():
            return False
        return True

    def EnemyMonsterAcceptsJailGateBanish(self, defender):
        if defender is None or not defender.IsMonster():
            return False
        if defender.HasType(CardType.Token):
            return False
        if self.JailGateCannotRemove():
            return False
        return True

    def PickJailGateBanishTarget(self, defenders):
        if defenders is None:
            return None
        best, bestPower = None, -1
        for defender in defenders:
            if not self.EnemyMonsterAcceptsJailGateBanish(defender):
                continue
            power = defender.GetDefensePower()
            if best is None or power > bestPower:
                best, bestPower = defender, power
        return best

    def PreferCards(self, cards, idOrder, min_, max_):
        selected = []
        for id_ in idOrder:
            for card in cards:
                if card is not None and card.IsCode(id_) and card not in selected:
                    selected.append(card)
                    if len(selected) >= max_:
                        return self.Util.CheckSelectCount(selected, cards, min_, max_)
        if min_ == 0:
            if len(selected) == 0:
                return []
            return self.Util.CheckSelectCount(selected, cards, min_, max_)
        for card in cards:
            if card not in selected:
                selected.append(card)
                if len(selected) >= max_:
                    break
        return self.Util.CheckSelectCount(selected, cards, min_, max_)

    def HasUsableOneStar(self):
        Bot = self.Bot
        return Bot.HasInHand(CardId.JailChicken) or Bot.HasInMonstersZone(CardId.JailChicken) or Bot.HasInGraveyard(CardId.JailChicken)

    def AlreadyHasWhitePendulum(self):
        return self.Bot.HasInHand(CardId.WhitePendulum) or self.Bot.HasInSpellZone(CardId.WhitePendulum)

    def RedSearchWhitePCanTriggerDraw(self):
        Bot, Duel = self.Bot, self.Duel
        if not self.DefaultCheckWhetherBotCanDraw():
            return False
        if not self.NeedPendulumScale():
            return False
        if self.AlreadyHasWhitePendulum():
            return False
        skipHandSs = self.CheckShouldNoMoreSpSummon(CardLocation.Hand) and self.CheckHasStopBoard()
        skipWhite10 = self.CheckShouldNoMoreSpSummon(CardLocation.Deck) and self.CheckHasStopBoard()
        if self.White10OnFieldSecondEffectReady() and not skipWhite10:
            return True
        if self.HasChickenAndLevel6OnField() and Bot.HasInExtra(CardId.White7):
            return True
        white7Ready = any(c is not None and c.IsCode(CardId.White7) and c.IsFaceup() and not c.IsDisabled() for c in Bot.GetMonsters()) \
            and CardId.White7 not in self.activatedCardIdList \
            and (Duel.Phase == DuelPhase.Main1 or Duel.Phase == DuelPhase.Main2)
        if white7Ready:
            hasPull = any(c is not None and c.HasSetcode(SetcodeElvenotes) and c.Level <= 6 for c in Bot.Hand) \
                or any(c is not None and c.HasSetcode(SetcodeElvenotes) and c.Level <= 6 for c in Bot.Graveyard)
            if hasPull:
                return True
        if not skipHandSs and self.IsCenterEmpty():
            if self.ChickenGySearchWillAddHandSixStar():
                return True
            if self.HandHasSixStarWaitingToSs():
                return True
        return False

    def CountOwnedWhitePendulum(self):
        count = 0
        for card in self.Bot.Hand:
            if card is not None and card.IsCode(CardId.WhitePendulum):
                count += 1
        for card in self.Bot.GetSpells():
            if card is not None and card.IsCode(CardId.WhitePendulum):
                count += 1
        return count

    def CanTriggerWhitePendulumThisTurn(self):
        Bot = self.Bot
        if not self.DefaultCheckWhetherBotCanDraw():
            return False
        if CardId.WhitePendulum in self.activatedCardIdList:
            return False
        if not self.NeedPendulumScale() and not Bot.HasInSpellZone(CardId.WhitePendulum) and not Bot.HasInHand(CardId.WhitePendulum):
            return False
        if self.WantGreenFieldSummonWind() and not self.CheckShouldNoMoreSpSummon(CardLocation.Deck):
            haveGreen = Bot.HasInSpellZone(CardId.GreenField) or Bot.HasInHand(CardId.GreenField)
            canPlaceGreen = Bot.HasInDeck(CardId.GreenField) and (Bot.HasInHand(CardId.ElvenotesBlue)
                                                                  or Bot.HasInMonstersZone(CardId.ElvenotesBlue)
                                                                  or Bot.HasInDeck(CardId.ElvenotesBlue))
            if haveGreen or canPlaceGreen:
                return True
        if Bot.HasInMonstersZone(CardId.ElvenotesWind) and Bot.HasInDeck(CardId.ElvenotesYellow) \
                and not self.CheckShouldNoMoreSpSummon(CardLocation.Deck):
            return True
        if Bot.HasInMonstersZone(CardId.White7):
            if Bot.HasInHand(CardId.JailChicken) or Bot.HasInGraveyard(CardId.JailChicken):
                return True
            if any(c is not None and c.HasSetcode(SetcodeElvenotes) and c.Level <= 6 for c in Bot.Hand):
                return True
            if any(c is not None and c.HasSetcode(SetcodeElvenotes) and c.Level <= 6 for c in Bot.Graveyard):
                return True
        if Bot.HasInSpellZone(CardId.RedField, True, True) \
                and any(c is not None and (c.HasSetcode(SetcodeElvenotes) or c.IsCode(CardId.JailChicken)) for c in Bot.Graveyard):
            return True
        return False

    def SelectWhite7SpSummon(self, cards, min_, max_):
        Duel, act = self.Duel, self.activatedCardIdList
        ranked = []

        def add(pred):
            for card in cards:
                if card is not None and pred(card) and card not in ranked:
                    ranked.append(card)

        canEight = self.HasEightSynchroInExtra()
        sixStars = [CardId.ElvenotesBlue, CardId.ElvenotesRed, CardId.ElvenotesWind, CardId.ElvenotesYellow]
        G, H = CardLocation.Grave, CardLocation.Hand
        if Duel.Player == 1:
            centerFilled = self.GetCenterMonster() is not None
            if self.IsCenterEmpty() and CardId.ElvenotesWind + 1 not in act \
                    and (self.WantWindEnemyTurnSsChicken() or self.DeckHasRbySwapTarget()):
                add(lambda c: c.IsCode(CardId.ElvenotesWind) and c.Location == G)
            if centerFilled:
                for id_ in (CardId.ElvenotesRed, CardId.ElvenotesBlue, CardId.ElvenotesYellow):
                    if not self.GyRbyWorthWhite7Pull(id_):
                        continue
                    add(lambda c: c.IsCode(id_) and c.Location == G)
            if CardId.JailChicken + 1 not in act and (canEight or self.White10EffectStillAvailable()):
                add(lambda c: c.IsCode(CardId.JailChicken) and c.Location == G)
            if len(ranked) == 0 and centerFilled:
                for id_ in (CardId.ElvenotesRed, CardId.ElvenotesBlue, CardId.ElvenotesYellow):
                    if not self.CanRbySwapNow(id_, True) or self.HasFaceupRbyReadyToSwap(id_):
                        continue
                    add(lambda c: c.IsCode(id_) and c.Location == H)
            if len(ranked) == 0 and (self.CurrentTiming & HintTimingMainEnd) != 0:
                main2End = Duel.Phase == DuelPhase.Main2
                pullChicken = canEight and (main2End or not self.EnemyHasMonsterThatBeatsChicken())
                if pullChicken:
                    add(lambda c: c.IsCode(CardId.JailChicken) and c.Location == G)
                gyBodies = _OrderByAttackDesc(c for c in cards if c is not None and c.Location == G
                                              and c.HasSetcode(SetcodeElvenotes) and c.Level <= 6 and c not in ranked)
                ranked.extend(gyBodies)
            for card in cards:
                if card is None or card in ranked:
                    continue
                if card.Location != G:
                    continue
                if not card.HasSetcode(SetcodeElvenotes) or card.Level > 6:
                    continue
                if card.IsCode(CardId.ElvenotesWind):
                    continue
                ranked.append(card)
            return self.Util.CheckSelectCount(ranked, cards, min_, max_)
        if not canEight:
            for id_ in sixStars:
                add(lambda c: c.IsCode(id_) and c.Location == G)
            for id_ in sixStars:
                add(lambda c: c.IsCode(id_) and c.Location == H)
        add(lambda c: c.IsCode(CardId.JailChicken) and c.Location == G)
        add(lambda c: c.Location == G and c.Level <= 1)
        add(lambda c: c.IsCode(CardId.JailChicken) and c.Location == H)
        add(lambda c: c.Location == H and c.Level <= 1)
        if canEight:
            for id_ in sixStars:
                add(lambda c: c.IsCode(id_) and c.Location == G)
            for id_ in sixStars:
                add(lambda c: c.IsCode(id_) and c.Location == H)
        add(lambda c: True)
        return self.Util.CheckSelectCount(ranked, cards, min_, max_)

    def SelectWindDeckSpSummon(self, cards, min_, max_):
        Bot, act = self.Bot, self.activatedCardIdList
        if self.Duel.Player == 1:
            ranked = []

            def add(pred):
                for card in cards:
                    if card is not None and pred(card) and card not in ranked:
                        ranked.append(card)

            wantChicken = self.WantWindEnemyTurnSsChicken()
            w10Used = CardId.White10 in act
            if wantChicken:
                add(lambda c: c.IsCode(CardId.JailChicken))
            if self.white10EnemyWindMissingDeckId != 0:
                add(lambda c: c.IsCode(self.white10EnemyWindMissingDeckId))
            rbyOrder = [CardId.ElvenotesRed, CardId.ElvenotesBlue, CardId.ElvenotesYellow]
            for id_ in rbyOrder:
                if not self.CanRbySwapNow(id_, True):
                    continue
                add(lambda c: c.IsCode(id_))
            if w10Used:
                for id_ in rbyOrder:
                    if id_ == CardId.ElvenotesRed and CardId.ElvenotesRed + 3 in act:
                        continue
                    if id_ == CardId.ElvenotesBlue and CardId.ElvenotesBlue + 3 in act:
                        continue
                    if id_ == CardId.ElvenotesYellow and CardId.ElvenotesYellow + 3 in act:
                        continue
                    if self.HasFaceupRbyReadyToSwap(id_):
                        continue
                    add(lambda c: c.IsCode(id_))
            byAtk = _OrderByAttackDesc(c for c in cards if c is not None and c.HasSetcode(SetcodeElvenotes)
                                       and not c.IsCode(CardId.ElvenotesWind) and c not in ranked)
            ranked.extend(byAtk)
            add(lambda c: True)
            return self.Util.CheckSelectCount(ranked, cards, min_, max_)

        hasTuner = any(c is not None and c.IsFaceup() and c.IsTuner() for c in Bot.GetMonsters())
        blue2Used = CardId.ElvenotesBlue in act
        blueOnFieldFor2 = not blue2Used and any(c is not None and c.IsCode(CardId.ElvenotesBlue) and c.IsFaceup() for c in Bot.GetMonsters())
        red2Unused = self.CanElvenotesRedSearch()
        needYellowForRed = not Bot.HasInSpellZone(CardId.RedField) \
            and (Bot.HasInDeck(CardId.RedField) or Bot.HasInHand(CardId.RedField)) \
            and not Bot.HasInHand(CardId.ElvenotesYellow) and not Bot.HasInMonstersZone(CardId.ElvenotesYellow)
        if self.IsFuwalosOnlyOpeningCompromise() and not hasTuner:
            order = [CardId.JailChicken, CardId.ElvenotesYellow, CardId.ElvenotesBlue, CardId.ElvenotesRed]
        elif needYellowForRed and self.HasEightSynchroOnField() and Bot.HasInGraveyard(CardId.JailChicken):
            order = [CardId.ElvenotesYellow, CardId.JailChicken, CardId.ElvenotesBlue, CardId.ElvenotesRed]
        elif not hasTuner:
            order = [CardId.JailChicken, CardId.ElvenotesYellow, CardId.ElvenotesBlue, CardId.ElvenotesRed]
        elif needYellowForRed:
            order = [CardId.ElvenotesYellow, CardId.ElvenotesBlue, CardId.JailChicken, CardId.ElvenotesRed]
        elif red2Unused:
            order = [CardId.ElvenotesRed, CardId.JailChicken, CardId.ElvenotesBlue, CardId.ElvenotesYellow]
        elif not blue2Used and not blueOnFieldFor2:
            order = [CardId.ElvenotesBlue, CardId.JailChicken, CardId.ElvenotesYellow, CardId.ElvenotesRed]
        else:
            order = [CardId.JailChicken, CardId.ElvenotesYellow, CardId.ElvenotesBlue, CardId.ElvenotesRed]
        return self.PreferCards(cards, order, min_, max_)

    def CountWhite10FollowupSynchroBodies(self):
        """C# out-parameters: returns (tuners, nonTuners)."""
        tuners = nonTuners = 0
        for card in self.Bot.GetMonsters():
            if card is None or not card.IsFaceup():
                continue
            if card.IsCode(CardId.White10, CardId.CrystalWing, CardId.FormulaAthleteLightning, CardId.BaronneDeFleur,
                           CardId.SuperLibrarian):
                continue
            if card.Level <= 0:
                continue
            if card.HasType(CardType.Xyz | CardType.Link):
                continue
            if card.IsTuner():
                tuners += 1
            else:
                nonTuners += 1
        return tuners, nonTuners

    def IsWhite10HandSixStar(self, card):
        return card is not None and card.Location == CardLocation.Hand \
            and card.IsCode(CardId.ElvenotesRed, CardId.ElvenotesBlue, CardId.ElvenotesYellow)

    def CountHandCode(self, cardId):
        count = 0
        for card in self.Bot.Hand:
            if card is not None and card.IsCode(cardId):
                count += 1
        return count

    def PickWhite10HandSixStar(self, cards):
        for card in cards:
            if self.IsWhite10HandSixStar(card) and self.White10Body2StillAvailable(card.Id):
                return card
        for card in cards:
            if self.IsWhite10HandSixStar(card) and self.CountHandCode(card.Id) >= 2:
                return card
        for card in cards:
            if self.IsWhite10HandSixStar(card):
                return card
        return None

    def AddWhite10HandSixStars(self, ranked, cards):
        for card in cards:
            if self.IsWhite10HandSixStar(card) and self.White10Body2StillAvailable(card.Id) and card not in ranked:
                ranked.append(card)
        for card in cards:
            if self.IsWhite10HandSixStar(card) and self.CountHandCode(card.Id) >= 2 and card not in ranked:
                ranked.append(card)
        for card in cards:
            if self.IsWhite10HandSixStar(card) and card not in ranked:
                ranked.append(card)

    def White10Body2StillAvailable(self, cardId):
        if cardId == CardId.ElvenotesRed:
            return self.CanElvenotesRedSearch()
        if cardId == CardId.ElvenotesYellow:
            return CardId.ElvenotesYellow not in self.activatedCardIdList
        if cardId == CardId.ElvenotesBlue:
            return CardId.ElvenotesBlue not in self.activatedCardIdList
        return False

    def PickWhite10DeckSixStar(self, cards):
        for id_ in (CardId.ElvenotesRed, CardId.ElvenotesYellow, CardId.ElvenotesBlue):
            if self.Bot.HasInHand(id_):
                continue
            if not self.White10Body2StillAvailable(id_):
                continue
            for card in cards:
                if card is not None and card.IsCode(id_) and card.Location == CardLocation.Deck:
                    return card
        return None

    def CanWhite10DeckSsWind(self, cards):
        if CardId.ElvenotesWind + 1 in self.activatedCardIdList:
            return False
        center = self.GetCenterMonster()
        if center is not None and center.IsCode(CardId.ElvenotesWind) and center.Sequence == 2:
            return False
        for card in cards:
            if card is not None and card.IsCode(CardId.ElvenotesWind) and card.Location == CardLocation.Deck:
                return True
        return False

    def ShouldWhite10DeckSsChicken(self, cards):
        tuners, nonTuners = self.CountWhite10FollowupSynchroBodies()
        gyChickenCounted = self.white10PickedGyChickenThisChain
        if not gyChickenCounted:
            for card in cards:
                if card is not None and card.IsCode(CardId.JailChicken) and card.Location == CardLocation.Grave:
                    gyChickenCounted = True
                    break
        if gyChickenCounted:
            tuners += 1
        if nonTuners <= tuners:
            return False
        deckChicken = 0
        hasHandChicken = False
        for card in cards:
            if card is None:
                continue
            if card.IsCode(CardId.JailChicken) and card.Location == CardLocation.Deck:
                deckChicken += 1
            if card.IsCode(CardId.JailChicken) and card.Location == CardLocation.Hand:
                hasHandChicken = True
        if deckChicken <= 0:
            deckChicken = self.Bot.GetCardCountInDeck(CardId.JailChicken)
        if self.Duel.Player == 0:
            return deckChicken >= 2 or (hasHandChicken and deckChicken >= 1)
        return deckChicken >= 1

    def SelectWhite10SpSummon(self, cards, min_, max_):
        Bot, Duel = self.Bot, self.Duel
        G, H, D = CardLocation.Grave, CardLocation.Hand, CardLocation.Deck
        if Duel.Player == 1:
            return self.SelectWhite10SpSummonEnemyTurn(cards, min_, max_)
        if self.white10MissingPlaceLineThisChain:
            forced = []
            gyChicken = next((c for c in cards if c is not None and c.IsCode(CardId.JailChicken) and c.Location == G), None)
            deckId = CardId.ElvenotesYellow if self.OpeningYellowPlaceMissing() else CardId.ElvenotesBlue
            deckColor = next((c for c in cards if c is not None and c.IsCode(deckId) and c.Location == D), None)
            if gyChicken is None or deckColor is None:
                pass
            else:
                forced.append(gyChicken)
                forced.append(deckColor)
                handSix = self.PickWhite10HandSixStar(cards)
                if handSix is not None:
                    forced.append(handSix)
                return self.FinishWhite10OwnSelect(forced, cards, min_, max_)

        ranked = []
        tuners, nonTuners = self.CountWhite10FollowupSynchroBodies()
        deckChicken = 0
        hasGyWhite7 = hasHandElvenotes = hasDeckChickenCard = hasHandChicken = False
        for card in cards:
            if card is None:
                continue
            if card.IsCode(CardId.JailChicken) and card.Location == D:
                deckChicken += 1
                hasDeckChickenCard = True
            if card.IsCode(CardId.JailChicken) and card.Location == H:
                hasHandChicken = True
            if card.IsCode(CardId.White7) and card.Location == G:
                hasGyWhite7 = True
            if self.IsWhite10HandSixStar(card):
                hasHandElvenotes = True
        if deckChicken <= 0:
            deckChicken = Bot.GetCardCountInDeck(CardId.JailChicken)
        freeMain = self.CountFreeMainMonsterZones()
        chickenOffField = self.CountChickenInHandDeckGrave()
        canEight = self.HasEightSynchroInExtra()
        twoZoneWhite7Chicken = self.white10TwoZoneWhite7ChickenThisChain \
            or (Duel.Player == 0 and freeMain == 2 and hasGyWhite7 and chickenOffField >= 2
                and (hasHandChicken or hasDeckChickenCard) and canEight
                and not self.CheckShouldNoMoreSpSummon(CardLocation.Grave))
        if twoZoneWhite7Chicken:
            self.white10TwoZoneWhite7ChickenThisChain = True
            gyWhite7 = handChicken = deckChickenCard = None
            for card in cards:
                if card is None:
                    continue
                if gyWhite7 is None and card.IsCode(CardId.White7) and card.Location == G:
                    gyWhite7 = card
                if handChicken is None and card.IsCode(CardId.JailChicken) and card.Location == H:
                    handChicken = card
                if deckChickenCard is None and card.IsCode(CardId.JailChicken) and card.Location == D:
                    deckChickenCard = card
            if gyWhite7 is not None:
                ranked.append(gyWhite7)
            if handChicken is not None:
                ranked.append(handChicken)
            elif deckChickenCard is not None:
                ranked.append(deckChickenCard)
            return self.FinishWhite10OwnSelect(ranked, cards, min_, max_)
        twoChickensKeepOneInDeck = deckChicken >= 2 or (hasHandChicken and hasDeckChickenCard)
        gyWhite7HandChicken = hasHandChicken and hasDeckChickenCard
        gyWhite7AfterEight = Duel.Player == 0 and self.HasEightSynchroOnField() and hasGyWhite7 \
            and (hasDeckChickenCard or hasHandChicken) and self.HasEightSynchroInExtra() \
            and not self.CheckShouldNoMoreSpSummon(CardLocation.Grave) and not self.CheckShouldNoMoreSpSummon(CardLocation.Deck)
        gyWhite7Line = self.white10GyWhite7LineThisChain or gyWhite7AfterEight \
            or (Duel.Player == 0 and twoChickensKeepOneInDeck and nonTuners <= tuners
                and hasGyWhite7 and (gyWhite7HandChicken or (hasHandElvenotes and hasDeckChickenCard))
                and not self.CheckShouldNoMoreSpSummon(CardLocation.Deck))
        if gyWhite7Line:
            self.white10GyWhite7LineThisChain = True
            gyWhite7 = deckChickenCard = handChicken = None
            for card in cards:
                if card is None:
                    continue
                if gyWhite7 is None and card.IsCode(CardId.White7) and card.Location == G:
                    gyWhite7 = card
                if deckChickenCard is None and card.IsCode(CardId.JailChicken) and card.Location == D:
                    deckChickenCard = card
                if handChicken is None and card.IsCode(CardId.JailChicken) and card.Location == H:
                    handChicken = card
            if gyWhite7 is not None:
                ranked.append(gyWhite7)
            if handChicken is not None:
                ranked.append(handChicken)
                deckSixStar = self.PickWhite10DeckSixStar(cards)
                if deckSixStar is not None:
                    ranked.append(deckSixStar)
            else:
                if deckChickenCard is not None:
                    ranked.append(deckChickenCard)
                handElvenotes = self.PickWhite10HandSixStar(cards)
                if handElvenotes is not None:
                    ranked.append(handElvenotes)
            return self.FinishWhite10OwnSelect(ranked, cards, min_, max_)

        def add(pred):
            for card in cards:
                if card is not None and pred(card) and card not in ranked:
                    ranked.append(card)

        for card in cards:
            if card is not None and card.IsCode(CardId.JailChicken) and card.Location == G and card not in ranked:
                ranked.append(card)
                self.white10PickedGyChickenThisChain = True
        wantFollowupChicken = self.ShouldWhite10DeckSsChicken(cards)
        takeHandChickenKeepDeck = hasHandChicken and hasDeckChickenCard and wantFollowupChicken
        if takeHandChickenKeepDeck:
            add(lambda c: c.IsCode(CardId.JailChicken) and c.Location == H)
        else:
            self.AddWhite10HandSixStars(ranked, cards)
        if not self.CheckShouldNoMoreSpSummon(CardLocation.Deck):
            wantDeckChicken = wantFollowupChicken and not takeHandChickenKeepDeck
            wantDeckWind = not wantDeckChicken and self.CanWhite10DeckSsWind(cards)
            if wantDeckWind:
                add(lambda c: c.IsCode(CardId.ElvenotesWind) and c.Location == D)
            if wantDeckChicken:
                add(lambda c: c.IsCode(CardId.JailChicken) and c.Location == D)
            for id_ in (CardId.ElvenotesRed, CardId.ElvenotesYellow, CardId.ElvenotesBlue):
                if Bot.HasInHand(id_):
                    continue
                if not self.White10Body2StillAvailable(id_):
                    continue
                add(lambda c: c.IsCode(id_) and c.Location == D)
            if not wantDeckWind:
                add(lambda c: c.IsCode(CardId.ElvenotesWind) and c.Location == D)
        add(lambda c: c.IsCode(CardId.White7) and c.Location == G)
        plannedTuners, plannedNonTuners = tuners, nonTuners
        countedHand = countedDeck = countedGy = False
        for card in ranked:
            if card is None:
                continue
            isTunerMat = card.IsCode(CardId.JailChicken)
            isNonTunerMat = card.IsCode(CardId.White7) or self.IsElvenotesSixStar(card)
            if not isTunerMat and not isNonTunerMat:
                continue
            if card.Location == H:
                if countedHand:
                    continue
                countedHand = True
            elif card.Location == D:
                if countedDeck:
                    continue
                countedDeck = True
            elif card.Location == G:
                if countedGy:
                    continue
                countedGy = True
            else:
                continue
            if isTunerMat:
                plannedTuners += 1
            else:
                plannedNonTuners += 1
        skipGySixStarFlood = plannedNonTuners >= plannedTuners
        if not skipGySixStarFlood:
            add(lambda c: self.IsElvenotesSixStar(c) and c.Location == G)
        add(lambda c: c.IsCode(CardId.JailChicken) and c.Location == H)
        return self.FinishWhite10OwnSelect(ranked, cards, min_, max_)

    def FinishWhite10OwnSelect(self, ranked, cards, min_, max_):
        if len(ranked) == 0 and min_ == 0:
            picked = []
        else:
            picked = self.Util.CheckSelectCount(ranked, cards, min_, max_)
        return picked

    def FindWhite10Candidate(self, cards, cardId, loc):
        if cardId in self.white10EnemyPickedCodesThisChain:
            return None
        for card in cards:
            if card is not None and card.IsCode(cardId) and card.Location == loc:
                return card
        return None

    def White10EnemySkipCode(self, picked, cardId):
        if cardId in self.white10EnemyPickedCodesThisChain:
            return True
        if picked is not None and any(p is not None and p.IsCode(cardId) for p in picked):
            return True
        if any(c is not None and c.IsFaceup() and c.IsCode(cardId) for c in self.Bot.GetMonsters()):
            return True
        return False

    def FinishWhite10EnemySelect(self, ranked, cards, min_, max_):
        if len(ranked) == 0 and min_ == 0:
            return []
        result = self.Util.CheckSelectCount(ranked, cards, min_, max_)
        if result is not None:
            for card in result:
                if card is not None and card.Id not in self.white10EnemyPickedCodesThisChain:
                    self.white10EnemyPickedCodesThisChain.append(card.Id)
        return result

    def White10EnemyTurnCenterCardId(self):
        picked = self.white10EnemyPickedCodesThisChain
        wind2 = CardId.ElvenotesWind + 1 not in self.activatedCardIdList
        if wind2 and CardId.ElvenotesWind in picked:
            return CardId.ElvenotesWind
        if CardId.JailChicken in picked:
            return CardId.JailChicken
        if CardId.ElvenotesYellow in picked:
            return CardId.ElvenotesYellow
        if CardId.ElvenotesRed in picked:
            return CardId.ElvenotesRed
        if CardId.ElvenotesBlue in picked:
            return CardId.ElvenotesBlue
        if CardId.ElvenotesWind in picked:
            return CardId.ElvenotesWind
        return 0

    def White10EnemyTurnWantsThisCardInCenter(self, cardId):
        want = self.White10EnemyTurnCenterCardId()
        if want != 0:
            return cardId == want
        if cardId == CardId.ElvenotesWind and CardId.ElvenotesWind + 1 not in self.activatedCardIdList:
            return True
        if cardId == CardId.JailChicken:
            return True
        if cardId in (CardId.ElvenotesYellow, CardId.ElvenotesRed, CardId.ElvenotesBlue):
            return True
        return False

    def SelectWhite10SpSummonEnemyTurn(self, cards, min_, max_):
        Bot, act = self.Bot, self.activatedCardIdList
        G, H, D = CardLocation.Grave, CardLocation.Hand, CardLocation.Deck
        if min_ == 0 and len(self.white10EnemyPickedCodesThisChain) >= 3:
            return []
        ranked = []
        freeAfter = self.CountFreeMainMonsterZones() + 1
        gyWhite7 = self.FindWhite10Candidate(cards, CardId.White7, G)
        windGy = self.FindWhite10Candidate(cards, CardId.ElvenotesWind, G)
        windDeck = self.FindWhite10Candidate(cards, CardId.ElvenotesWind, D)
        windHand = self.FindWhite10Candidate(cards, CardId.ElvenotesWind, H)
        windPick = windGy or windDeck or windHand
        alreadyWind = CardId.ElvenotesWind in self.white10EnemyPickedCodesThisChain
        rbyIds = [CardId.ElvenotesRed, CardId.ElvenotesBlue, CardId.ElvenotesYellow]

        if freeAfter >= 4 and gyWhite7 is not None and CardId.White7 not in act and not self.CheckShouldNoMoreSpSummon(CardLocation.Grave):
            handPick = deckPick = None
            have = []
            for id_ in rbyIds:
                if handPick is None:
                    h = self.FindWhite10Candidate(cards, id_, H)
                    if h is not None:
                        handPick = h
                        have.append(id_)
            for id_ in rbyIds:
                if id_ in have:
                    continue
                if deckPick is None:
                    d = self.FindWhite10Candidate(cards, id_, D)
                    if d is not None:
                        deckPick = d
                        have.append(id_)
            thirdInGy = False
            for id_ in rbyIds:
                if id_ in have:
                    continue
                if Bot.HasInGraveyard(id_):
                    thirdInGy = True
                    have.append(id_)
                    break
            threeColors = thirdInGy and CardId.ElvenotesRed in have and CardId.ElvenotesBlue in have and CardId.ElvenotesYellow in have
            if threeColors and handPick is not None and deckPick is not None:
                yellow = None
                if handPick.IsCode(CardId.ElvenotesYellow):
                    yellow = handPick
                elif deckPick.IsCode(CardId.ElvenotesYellow):
                    yellow = deckPick
                if yellow is not None:
                    ranked.append(yellow)
                ranked.append(gyWhite7)
                if handPick not in ranked:
                    ranked.append(handPick)
                if deckPick not in ranked:
                    ranked.append(deckPick)
                return self.FinishWhite10EnemySelect(ranked, cards, min_, max_)

        if freeAfter >= 4 and (windPick is not None or alreadyWind) and CardId.ElvenotesWind + 1 not in act \
                and not self.CheckShouldNoMoreSpSummon(CardLocation.Deck):
            gyPick = handPick = None
            have = []
            for id_ in rbyIds:
                if gyPick is None:
                    g = self.FindWhite10Candidate(cards, id_, G)
                    if g is not None:
                        gyPick = g
                        have.append(id_)
            for id_ in rbyIds:
                if id_ in have:
                    continue
                if handPick is None:
                    h = self.FindWhite10Candidate(cards, id_, H)
                    if h is not None:
                        handPick = h
                        have.append(id_)
            thirdInDeck = False
            missingId = 0
            for id_ in rbyIds:
                if id_ in have:
                    continue
                if Bot.HasInDeck(id_):
                    thirdInDeck = True
                    missingId = id_
                    have.append(id_)
                    break
            threeColors = CardId.ElvenotesRed in have and CardId.ElvenotesBlue in have and CardId.ElvenotesYellow in have
            if threeColors and gyPick is not None and handPick is not None and thirdInDeck and missingId != 0:
                if windPick is not None:
                    ranked.append(windPick)
                if gyPick not in ranked:
                    ranked.append(gyPick)
                if handPick not in ranked:
                    ranked.append(handPick)
                self.white10EnemyWindMissingDeckId = missingId
                return self.FinishWhite10EnemySelect(ranked, cards, min_, max_)

        picked = []
        used = {G: False, H: False, D: False}

        def take(card):
            picked.append(card)
            if card.Location in used:
                used[card.Location] = True

        for id_ in rbyIds:
            if len(picked) >= 3:
                break
            if self.White10EnemySkipCode(picked, id_):
                continue
            if not self.CanRbySwapNow(id_, True):
                continue
            pick = None
            if not used[G]:
                pick = self.FindWhite10Candidate(cards, id_, G)
            if pick is not None:
                take(pick)
                continue
            if not used[H]:
                pick = self.FindWhite10Candidate(cards, id_, H)
            if pick is not None:
                take(pick)
                continue
            if not used[D]:
                pick = self.FindWhite10Candidate(cards, id_, D)
            if pick is not None:
                take(pick)
                continue
        if len(picked) < 3:
            rbyAll = _OrderByAttackDesc(c for c in cards if c is not None
                                        and (c.IsCode(CardId.ElvenotesRed) or c.IsCode(CardId.ElvenotesBlue) or c.IsCode(CardId.ElvenotesYellow))
                                        and c not in picked)
            for card in rbyAll:
                if len(picked) >= 3:
                    break
                if self.White10EnemySkipCode(picked, card.Id):
                    continue
                if card.Location in used and used[card.Location]:
                    continue
                take(card)
        if len(picked) < 3:
            chicken = None
            if not self.White10EnemySkipCode(picked, CardId.JailChicken):
                if not used[G]:
                    chicken = self.FindWhite10Candidate(cards, CardId.JailChicken, G)
                if chicken is None and not used[H]:
                    chicken = self.FindWhite10Candidate(cards, CardId.JailChicken, H)
                if chicken is None and not used[D]:
                    chicken = self.FindWhite10Candidate(cards, CardId.JailChicken, D)
            if chicken is not None:
                take(chicken)
        if len(picked) < 3:
            others = _OrderByAttackDesc(c for c in cards if c is not None and c.HasSetcode(SetcodeElvenotes) and c not in picked)
            for card in others:
                if len(picked) >= 3:
                    break
                if self.White10EnemySkipCode(picked, card.Id):
                    continue
                if card.Location in used and used[card.Location]:
                    continue
                take(card)
        for id_ in (CardId.ElvenotesYellow, CardId.ElvenotesRed, CardId.ElvenotesBlue):
            for card in picked:
                if card is not None and card.IsCode(id_) and card not in ranked:
                    ranked.append(card)
        for card in picked:
            if card is not None and card not in ranked:
                ranked.append(card)
        return self.FinishWhite10EnemySelect(ranked, cards, min_, max_)

    def SelectJailGateMill(self, cards, min_, max_):
        Bot = self.Bot
        chickenAlready = Bot.HasInMonstersZone(CardId.JailChicken) or Bot.HasInGraveyard(CardId.JailChicken)
        gyOk = []
        for card in cards:
            if card is not None and not self.CheckWhetherBotWillBeBanished(card) and card not in gyOk:
                gyOk.append(card)
        millPool = gyOk if len(gyOk) > 0 else cards
        if not chickenAlready and any(c is not None and c.IsCode(CardId.JailChicken) and not self.CheckWhetherBotWillBeBanished(c)
                                      for c in millPool):
            return self.PreferCards(millPool, [CardId.JailChicken, CardId.MixedHellGod, CardId.WhitePendulum], min_, max_)
        millRanked = []

        def add(pred):
            for card in millPool:
                if card is not None and pred(card) and card not in millRanked:
                    millRanked.append(card)

        add(lambda c: c.IsCode(CardId.WhitePendulum) and c.Location == CardLocation.Extra)
        add(lambda c: c.IsCode(CardId.MixedHellGod) and c.Location == CardLocation.Extra)
        add(lambda c: c.IsCode(CardId.WhitePendulum))
        add(lambda c: c.IsCode(CardId.MixedHellGod))
        add(lambda c: c.IsCode(CardId.JailChicken))
        return self.Util.CheckSelectCount(millRanked, millPool, min_, max_)

    def SelectMixedHellGodSearch(self, cards, min_, max_):
        Bot, act = self.Bot, self.activatedCardIdList
        if min_ == 0:
            return []
        needChicken = not self.HasUsableOneStar()
        wantWhiteP = any(c is not None and c.IsCode(CardId.WhitePendulum) for c in cards) and self.CountOwnedWhitePendulum() < 2
        canTrigger = self.CanTriggerWhitePendulumThisTurn()
        wantGate = any(c is not None and c.IsCode(CardId.JailGodGate) for c in cards) \
            and not Bot.HasInHand(CardId.JailGodGate) and not Bot.HasInSpellZone(CardId.JailGodGate) \
            and CardId.JailGodGate not in act \
            and self.Duel.Player == 0 \
            and self.DefaultCheckWhetherBotCanSearch() \
            and self.CheckWhetherCanSummon() \
            and not Bot.HasInHand(CardId.MediusTheInnocent) \
            and not Bot.HasInMonstersZone(CardId.MediusTheInnocent) \
            and CardId.MediusTheInnocent not in act \
            and not any(c is not None and self.IsElvenotesSixStar(c) and c.IsFaceup() for c in Bot.GetMonsters()) \
            and not self.HandHasSixStarWaitingToSs()
        p2Gate = CardId.MixedHellGod + 1 in act and any(c is not None and c.IsCode(CardId.JailGodGate) for c in cards)
        if p2Gate:
            order = [CardId.JailGodGate, CardId.JailChicken, CardId.WhitePendulum, CardId.MixedHellGod]
        elif needChicken:
            order = [CardId.JailChicken, CardId.JailGodGate, CardId.WhitePendulum, CardId.MixedHellGod]
        elif wantGate:
            order = [CardId.JailGodGate, CardId.WhitePendulum, CardId.MixedHellGod, CardId.JailChicken]
        elif wantWhiteP and canTrigger:
            order = [CardId.WhitePendulum, CardId.JailChicken, CardId.MixedHellGod, CardId.JailGodGate]
        elif wantWhiteP:
            order = [CardId.WhitePendulum, CardId.MixedHellGod, CardId.JailChicken, CardId.JailGodGate]
        else:
            order = [CardId.MixedHellGod, CardId.WhitePendulum, CardId.JailChicken, CardId.JailGodGate]
        return self.PreferCards(cards, order, min_, max_)

    def PickMixedHellGodPendulumOption(self, options):
        Bot = self.Bot
        ss_desc, atk_desc = self.Util.GetStringId(CardId.MixedHellGod, 1), self.Util.GetStringId(CardId.MixedHellGod, 2)
        ssIdx = options.index(ss_desc) if ss_desc in options else -1
        atkIdx = options.index(atk_desc) if atk_desc in options else -1
        if ssIdx < 0 and atkIdx < 0:
            return -1
        gyJail = Bot.HasInGraveyard(CardId.JailChicken)
        handJail = Bot.HasInHand(CardId.JailChicken)
        fieldJail = Bot.HasInMonstersZone(CardId.JailChicken)
        hasZone = self.CountFreeMainMonsterZones() >= 1
        pick = atkIdx if atkIdx >= 0 else ssIdx
        if ssIdx >= 0 and hasZone and gyJail and not self.CheckShouldNoMoreSpSummon(CardLocation.Grave):
            pick = ssIdx
        elif ssIdx >= 0 and hasZone and handJail and not fieldJail and not self.CheckShouldNoMoreSpSummon(CardLocation.Hand) \
                and not self.ShouldNsChickenInsteadOfMixedHandSs():
            pick = ssIdx
        elif atkIdx >= 0 and self.CanMixedHellGodPendulumAtkBuff():
            pick = atkIdx
            if CardId.MixedHellGod + 1 not in self.activatedCardIdList:
                self.activatedCardIdList.append(CardId.MixedHellGod + 1)
        return pick

    # --- lifecycle --------------------------------------------------------------------------------------------
    def OnSelectHand(self):
        return True

    def OnNewTurn(self):
        self.summonCount = 1
        self.activatedCardIdList.clear()
        self.spSummonedCardIdList.clear()
        self.enemyPlaceThisTurn.clear()
        self.currentNegateCardList.clear()
        self.currentDestroyCardList.clear()
        self.white10GyWhite7LineThisChain = False
        self.white10TwoZoneWhite7ChickenThisChain = False
        self.white10PickedGyChickenThisChain = False
        self.white10EnemyPickedCodesThisChain.clear()
        self.white10EnemyWindMissingDeckId = 0
        self.white10MissingPlaceLineThisChain = False
        self.redFieldPendingNegateTarget = None
        self.preferNegateCard = None
        self.nsChickenOffCenterForWhite10 = False
        self.chickenDodgeSynchroThisChain = False
        self.chickenDodgeSynchroCardId = 0
        self.accel2PreferWindChicken = False
        self.jailGateResolvedThisTurn = False
        super().OnNewTurn()

    def OnChainSolved(self, chainIndex):
        currentChain = self.Duel.GetCurrentSolvingChainInfo()
        if currentChain is not None and currentChain.ActivatePlayer == 0 and currentChain.IsActivateCode(CardId.JailGodGate) \
                and (self.Duel.Phase == DuelPhase.Main1 or self.Duel.Phase == DuelPhase.Main2) \
                and not self.Duel.IsCurrentSolvingChainNegated():
            self.jailGateResolvedThisTurn = True
        super().OnChainSolved(chainIndex)

    def OnChainEnd(self):
        self.currentNegateCardList.clear()
        self.currentDestroyCardList.clear()
        self.white10GyWhite7LineThisChain = False
        self.white10TwoZoneWhite7ChickenThisChain = False
        self.white10PickedGyChickenThisChain = False
        self.white10EnemyPickedCodesThisChain.clear()
        self.redFieldPendingNegateTarget = None
        self.preferNegateCard = None
        self.chickenDodgeSynchroThisChain = False
        self.chickenDodgeSynchroCardId = 0
        self.accel2PreferWindChicken = False
        for idx in range(len(self.enemyPlaceThisTurn) - 1, -1, -1):
            checkTarget = self.enemyPlaceThisTurn[idx]
            if checkTarget is None or not checkTarget.IsOnField():
                del self.enemyPlaceThisTurn[idx]
        super().OnChainEnd()

    def OnMove(self, card, previousControler, previousLocation, currentControler, currentLocation):
        if card is not None and card.IsCode(CardId.MediusTheInnocent):
            if previousControler == 0 and previousLocation == CardLocation.Grave \
                    and currentControler == 0 and currentLocation == CardLocation.MonsterZone:
                solving = self.Duel.GetCurrentSolvingChainInfo()
                if solving is not None and solving.ActivatePlayer == 0 and solving.IsActivateCode(CardId.MediusTheInnocent) \
                        and solving.ActivateDescription == self.Util.GetStringId(CardId.MediusTheInnocent, 1):
                    if card not in self.mediusSsByOwnGyEffect:
                        self.mediusSsByOwnGyEffect.append(card)
            if card in self.mediusSsByOwnGyEffect and (currentLocation & CardLocation.MonsterZone) == 0:
                self.mediusSsByOwnGyEffect.remove(card)
        if card is not None and card.IsCode(CardId.InnocentArt) and (previousControler == 0 or currentControler == 0):
            self.artSearched = False
        if card is not None and previousControler == 1:
            if currentControler == 1 and (currentLocation == CardLocation.MonsterZone or currentLocation == CardLocation.SpellZone):
                if card not in self.enemyPlaceThisTurn:
                    self.enemyPlaceThisTurn.append(card)
        super().OnMove(card, previousControler, previousLocation, currentControler, currentLocation)

    def OnPosChange(self, card, previousPosition, currentPosition):
        if card is not None and card in self.mediusSsByOwnGyEffect:
            self.mediusSsByOwnGyEffect.remove(card)
        super().OnPosChange(card, previousPosition, currentPosition)

    def OnSelectAttacker(self, attackers, defenders):
        if self.JailGateGyBanishReady() and self.PickJailGateBanishTarget(defenders) is not None:
            jail = next((c for c in attackers if c is not None and c.HasSetcode(SetcodeJailGod)), None)
            if jail is not None:
                return jail
        return super().OnSelectAttacker(attackers, defenders)

    def OnSelectAttackTarget(self, attacker, defenders):
        if attacker is not None and attacker.HasSetcode(SetcodeJailGod) and self.JailGateGyBanishReady():
            best = self.PickJailGateBanishTarget(defenders)
            if best is not None:
                return self.AI.Attack(attacker, best)
        return super().OnSelectAttackTarget(attacker, defenders)

    def OnBattle(self, attackers, defenders):
        if self.ShouldSkipBattleForBomber() and self.Duel.BattlePhase.CanMainPhaseTwo:
            return BattlePhaseAction(BattlePhaseAction.BattleAction.ToMainPhaseTwo)
        if self.JailGateGyBanishReady():
            jail = next((c for c in attackers if c is not None and c.HasSetcode(SetcodeJailGod)), None)
            if jail is not None and defenders is not None and len(defenders) > 0:
                hit = self.OnSelectAttackTarget(jail, defenders)
                if hit is not None:
                    return hit
        return super().OnBattle(attackers, defenders)

    # --- selects ----------------------------------------------------------------------------------------------
    def SpellZoneFacesEnemySet(self, zoneId):
        if zoneId < 0 or zoneId > 4:
            return False
        enemySpell = self.Enemy.SpellZone[4 - zoneId]
        return enemySpell is not None and enemySpell.IsFacedown()

    def EnemyFacedownSpellSeqStr(self):
        return ",".join(str(i) for i in range(5) if self.Enemy.SpellZone[i] is not None and self.Enemy.SpellZone[i].IsFacedown())

    def _FirstFreeZone(self, available, zoneIds):
        """The shuffled-zone loops of OnSelectPlace: first free main / extra zone of zoneIds, else 0."""
        for zoneId in self.Util.ShuffleList(zoneIds):
            zone = 1 << zoneId
            if (available & zone) != 0 and self.Bot.MonsterZone[zoneId] is None:
                return zone
        return 0

    def OnSelectPlace(self, cardId, player, location, available):
        Bot, Duel, act = self.Bot, self.Duel, self.activatedCardIdList
        if player != 0:
            return super().OnSelectPlace(cardId, player, location, available)
        if location == CardLocation.SpellZone or location == CardLocation.PendulumZone:
            if cardId == CardId.WhitePendulum or cardId == CardId.MixedHellGod:
                z0Avail = (available & Zones.z0) != 0
                z4Avail = (available & Zones.z4) != 0
                z0Safe = z0Avail and not self.SpellZoneFacesEnemySet(0) and 0 not in self.infiniteImpermanenceNegatedColumns
                z4Safe = z4Avail and not self.SpellZoneFacesEnemySet(4) and 4 not in self.infiniteImpermanenceNegatedColumns
                picked = 0
                if z0Safe:
                    picked = Zones.z0
                elif z4Safe:
                    picked = Zones.z4
                elif z0Avail:
                    picked = Zones.z0
                elif z4Avail:
                    picked = Zones.z4
                if picked != 0:
                    return picked
            else:
                spellZones = self.Util.ShuffleList([1, 2, 3])
                spellZones.extend(self.Util.ShuffleList([0, 4]))
                fallbackSet = fallbackImperm = 0
                for zoneId in spellZones:
                    zone = 1 << zoneId
                    if (available & zone) == 0 or Bot.SpellZone[zoneId] is not None:
                        continue
                    if zoneId in self.infiniteImpermanenceNegatedColumns:
                        if fallbackImperm == 0:
                            fallbackImperm = zone
                        continue
                    if self.SpellZoneFacesEnemySet(zoneId):
                        if fallbackSet == 0:
                            fallbackSet = zone
                        continue
                    return zone
                if fallbackSet != 0:
                    return fallbackSet
                if fallbackImperm != 0:
                    return fallbackImperm

        if location == CardLocation.MonsterZone:
            side = [0, 4, 1, 3]
            if cardId == CardId.JailChicken and self.nsChickenOffCenterForWhite10:
                extraDodge = self.SelectExtraMonsterZone(available)
                if extraDodge != 0:
                    return extraDodge
                z = self._FirstFreeZone(available, side)
                if z:
                    return z
            if self.IsOpeningComboTurn() and cardId == CardId.JailChicken:
                chickenSolving = Duel.GetCurrentSolvingChainInfo()
                ownSolving = chickenSolving is not None and chickenSolving.ActivatePlayer == 0
                accelReviveChicken = ownSolving and chickenSolving.IsActivateCode(CardId.AccelSynchroStardust)
                mediusOrMixedChicken = ownSolving and chickenSolving.IsActivateCode(CardId.MediusTheInnocent, CardId.MixedHellGod)
                if accelReviveChicken:
                    extraAccel = self.SelectExtraMonsterZone(available)
                    if extraAccel != 0:
                        return extraAccel
                    z = self._FirstFreeZone(available, side)
                    if z:
                        return z
                elif mediusOrMixedChicken and (available & Zones.z2) != 0 and Bot.MonsterZone[2] is None:
                    return Zones.z2
            mustCenter = self.NeedCenterCard(cardId) or cardId == CardId.ElvenotesWind
            solving = Duel.GetCurrentSolvingChainInfo()
            white10Solving = solving is not None and solving.ActivatePlayer == 0 and solving.IsActivateCode(CardId.White10)
            white7Solving = solving is not None and solving.ActivatePlayer == 0 and solving.IsActivateCode(CardId.White7)
            rby = (CardId.ElvenotesRed, CardId.ElvenotesBlue, CardId.ElvenotesYellow)
            if white10Solving and Duel.Player == 1:
                if (available & Zones.z2) != 0 and Bot.MonsterZone[2] is None and self.White10EnemyTurnWantsThisCardInCenter(cardId):
                    return Zones.z2
                if cardId in rby:
                    z = self._FirstFreeZone(available, side)
                    if z:
                        return z
                extraPlace = self.SelectExtraMonsterZone(available)
                if extraPlace != 0:
                    return extraPlace
                z = self._FirstFreeZone(available, side)
                if z:
                    return z
            if white10Solving and Duel.Player == 0:
                chickenWantsCenter = cardId == CardId.JailChicken and CardId.JailChicken + 1 not in act \
                    and Bot.HasInExtra(CardId.White10) and (available & Zones.z2) != 0 and Bot.MonsterZone[2] is None
                if chickenWantsCenter:
                    return Zones.z2
                windWantsCenter = cardId == CardId.ElvenotesWind and CardId.ElvenotesWind + 1 not in act \
                    and (available & Zones.z2) != 0 and Bot.MonsterZone[2] is None
                if windWantsCenter:
                    return Zones.z2
                extraOur = self.SelectExtraMonsterZone(available)
                if extraOur != 0:
                    return extraOur
                z = self._FirstFreeZone(available, side)
                if z:
                    return z
            if cardId == CardId.White7 and Duel.Player == 0 \
                    and (self.HandHasSixStarWaitingToSs() or self.ChickenGySearchWillAddHandSixStar()):
                extraWhite7 = self.SelectExtraMonsterZone(available)
                if extraWhite7 != 0:
                    return extraWhite7
                z = self._FirstFreeZone(available, side)
                if z:
                    return z
            if white7Solving and Duel.Player == 0 and cardId in rby \
                    and (self.HandHasSixStarWaitingToSs() or self.ChickenGySearchWillAddHandSixStar()):
                z = self._FirstFreeZone(available, side)
                if z:
                    return z
            if cardId == CardId.White7 and Duel.Player == 1:
                keepCenterForWindOrRby = self.WantWindEnemyTurnSsChicken() or self.DeckHasRbySwapTarget() \
                    or (Bot.HasInGraveyard(CardId.ElvenotesWind) and CardId.ElvenotesWind + 1 not in act) \
                    or any(c is not None and self.CanRbySwapNow(c.Id, True) for c in Bot.Graveyard)
                if keepCenterForWindOrRby or Bot.MonsterZone[2] is not None:
                    extraEnemy = self.SelectExtraMonsterZone(available)
                    if extraEnemy != 0:
                        return extraEnemy
                    z = self._FirstFreeZone(available, side)
                    if z:
                        return z
            if Duel.Player == 1 and Bot.MonsterZone[2] is not None and cardId in rby:
                z = self._FirstFreeZone(available, side)
                if z:
                    return z
            if mustCenter:
                if (available & Zones.z2) != 0 and Bot.MonsterZone[2] is None:
                    return Zones.z2
            else:
                extraPlace = self.SelectExtraMonsterZone(available)
                if extraPlace != 0:
                    return extraPlace
                z = self._FirstFreeZone(available, side)
                if z:
                    return z
            if (available & Zones.z2) != 0 and Bot.MonsterZone[2] is None and mustCenter:
                return Zones.z2
        return super().OnSelectPlace(cardId, player, location, available)

    def SelectExtraMonsterZone(self, available):
        for zoneId in self.Util.ShuffleList([5, 6]):
            zone = 1 << zoneId
            if (available & zone) != 0 and self.Bot.MonsterZone[zoneId] is None:
                return zone
        return 0

    def OnSelectPosition(self, cardId, positions):
        if self.AI.HaveSelectedPosition():
            return 0
        Duel, Util = self.Duel, self.Util
        FUD, FDD = CardPosition.FaceUpDefence, CardPosition.FaceDownDefence
        cardData = NamedCard.Get(cardId)
        if cardData is not None:
            cardAttack = cardData.Attack
            if cardId == CardId.FormulaAthleteLightning:
                cardAttack = 2100
                if Util.IsTurn1OrMain2():
                    if FUD in positions:
                        return FUD
                    if FDD in positions:
                        return FDD
            if Duel.Turn == 1 or Duel.Phase >= DuelPhase.Main2:
                if cardAttack <= cardData.Defense:
                    if FUD in positions:
                        return FUD
                    if FDD in positions:
                        return FDD
            if Duel.Player == 1:
                if cardData.Defense >= cardAttack or Util.IsOneEnemyBetterThanValue(cardAttack, True) or cardAttack < 2000:
                    if FUD in positions:
                        return FUD
                    if FDD in positions:
                        return FDD
            bestBotAttack = max(Util.GetBestPower(self.Bot, True), cardAttack)
            if Util.IsAllEnemyBetterThanValue(bestBotAttack, True):
                if FUD in positions:
                    return FUD
                if FDD in positions:
                    return FDD
        if cardData is not None and cardData.Attack == 0 and cardId != CardId.FormulaAthleteLightning and FUD in positions:
            return FUD
        if cardId == CardId.FormulaAthleteLightning:
            return 0
        return super().OnSelectPosition(cardId, positions)

    def ElfnoteMonsterRepos(self):
        Card, Duel, Util = self.Card, self.Duel, self.Util
        if Card is None or not Card.IsFaceup():
            return False
        center = self.Bot.MonsterZone[2]
        lockedByWhite10 = center is not None and center.IsCode(CardId.White10) and center.IsFaceup() and not center.IsDisabled() \
            and Card.Sequence != 2
        white7OffCenter = Card.IsCode(CardId.White7) and Card.Sequence != 2
        if lockedByWhite10:
            return Card.IsAttack()
        if white7OffCenter and Card.IsAttack():
            return True
        if Duel.Player == 1 or Util.IsTurn1OrMain2():
            if Card.Defense >= Card.Attack and Card.IsAttack():
                return True
            if Duel.Player == 1 and Util.IsOneEnemyBetterThanValue(Card.Attack, True) and Card.IsAttack():
                return True
            bestBotAttack = max(Util.GetBestPower(self.Bot, True), Card.Attack)
            if Util.IsAllEnemyBetterThanValue(bestBotAttack, True) and Card.IsAttack():
                return True
        return False

    def OnSelectYesNo(self, desc):
        Bot, Enemy, Duel, Util, act = self.Bot, self.Enemy, self.Duel, self.Util, self.activatedCardIdList
        if desc == Util.GetStringId(CardId.White7, 1):
            if Duel.Player == 0 and Bot.HasInMonstersZone(CardId.White7) and Bot.HasInMonstersZone(CardId.JailChicken) \
                    and self.HasEightSynchroInExtra():
                return False
            if Bot.HasInExtra(CardId.SuperLibrarian) and Bot.HasInMonstersZone(CardId.JailChicken) \
                    and any(c is not None and c.IsCode(CardId.White7) for c in Bot.GetMonsters()):
                if Bot.HasInMonstersZone(CardId.MediusTheInnocent) or sum(1 for c in Bot.GetMonsters() if c is not None and c.Level == 4) > 0:
                    return True
                if not Bot.HasInExtra(CardId.CrystalWing) and not Bot.HasInExtra(CardId.AccelSynchroStardust) \
                        and not Bot.HasInMonstersZone(CardId.CrystalWing) and not Bot.HasInMonstersZone(CardId.AccelSynchroStardust):
                    return True
            if Duel.Player == 1:
                keepWindLevel = any(c is not None and c.IsCode(CardId.ElvenotesWind) and c.IsFaceup() and c.Level >= 4
                                    for c in Bot.GetMonsters()) and CardId.ElvenotesWind + 1 not in act
                if keepWindLevel:
                    return False
                enemyHigh = any(c is not None and c.IsFaceup() and c.Level >= 4 and not c.IsDisabled() and not self.IsAlreadyMarkedNegate(c)
                                for c in Enemy.GetMonsters())
                return enemyHigh
            return False

        if desc == Util.GetStringId(CardId.JailGodGate, 2):
            if not self.DefaultCheckWhetherBotCanSearch():
                return False
            return Bot.HasInDeck(CardId.MediusTheInnocent) or Bot.HasInDeck(CardId.MixedHellGod)

        if desc == Util.GetStringId(CardId.JailChicken, 2):
            if self.chickenDodgeSynchroThisChain:
                return True
            if self.white10MissingPlaceLineThisChain or self.ShouldOpeningWhite10ForMissingPlace():
                return Bot.HasInExtra(CardId.White10)
            if (self.ShouldRerouteChickenSixUnderBanish() or self.IsFuwalosOnlyOpeningCompromise()) and Bot.HasInExtra(CardId.BaronneDeFleur):
                return False
            center = self.GetCenterMonster()
            chicken = next((c for c in Bot.GetMonsters() if c is not None and c.IsCode(CardId.JailChicken) and c.IsFaceup()), None)
            if center is not None and center.IsCode(CardId.JailChicken):
                selfPlus3 = Bot.HasInExtra(CardId.White10) and any(c is not None and c != center and self.IsElvenotesSixStar(c) and c.IsFaceup()
                                                                   for c in Bot.GetMonsters())
                return selfPlus3
            chickenLv = chicken.Level if chicken is not None else 1
            centerLv = center.Level if center is not None else 0
            extraWhite10 = Bot.HasInExtra(CardId.White10)
            alreadyTen = extraWhite10 and center is not None and centerLv + chickenLv == 10
            plus3MakesTen = extraWhite10 and center is not None and centerLv + 3 + chickenLv == 10
            answer = alreadyTen or plus3MakesTen
            if answer and self.CenterYellowStillNeedsToPlaceRedField() and not self.EnemyHasFloodgateMonster():
                return False
            return answer

        if desc == Util.GetStringId(CardId.RedField, 1):
            return self.EnemyHasWorthNegate()
        if desc == Util.GetStringId(CardId.ElvenotesRed, 1):
            return Duel.Player == 1 and any(c is not None and c.Level <= 6 and c.IsFaceup() and c.HasSetcode(SetcodeElvenotes)
                                            for c in Bot.GetMonsters())
        if desc == Util.GetStringId(CardId.ElvenotesRed, 2):
            return len(self.GetRedBounceableMonsters()) > 0
        if desc == Util.GetStringId(CardId.ElvenotesBlue, 2):
            return len(Enemy.Hand) > 0 and Duel.Player == 1
        if desc == Util.GetStringId(CardId.ElvenotesYellow, 2):
            return Duel.Player == 1 and self.EnemyHasYellowBounceTarget()
        if desc == Util.GetStringId(CardId.BlackRoseDragon, 0):
            return self.ShouldBlackRoseWipe()
        if desc == Util.GetStringId(CardId.ThousandSpearDragon, 3):
            return len(Enemy.Hand) > 0
        if desc == Util.GetStringId(CardId.AccelSynchroStardust, 1) or desc == Util.GetStringId(CardId.AccelSynchroStardust, 2):
            return Bot.HasInMonstersZone(CardId.JailChicken) or Bot.HasInGraveyard(CardId.JailChicken) \
                or any(c is not None and c.IsTuner() for c in Bot.GetMonsters())
        return super().OnSelectYesNo(desc)

    def OnSelectOption(self, options):
        Bot, Duel = self.Bot, self.Duel
        idx = lambda v: options.index(v) if v in options else -1
        if len(options) == 2 and 1190 in options and 1152 in options:
            solving = Duel.GetCurrentSolvingChainInfo()
            if solving is not None and solving.IsActivateCode(CardId.MediusTheInnocent):
                maxx = _CardId.MaxxC in self.enemyResolvedEffectIdList
                noZone = len(Bot.GetMonstersInMainZone()) >= 5
                selectedHint = None
                mixedPUsed = CardId.MixedHellGod in self.activatedCardIdList
                if not self.DefaultCheckWhetherBotCanSearch():
                    return idx(1152)
                if self.ShouldFuwalosMediusSsChickenFromDeck():
                    return idx(1152)
                if Bot.HasInGraveyard(CardId.JailChicken) and not mixedPUsed:
                    return idx(1190)
                if maxx or noZone:
                    return idx(1190)
                if selectedHint is not None and selectedHint.IsCode(CardId.WhitePendulum):
                    return idx(1190)
                if selectedHint is not None and selectedHint.IsCode(CardId.MixedHellGod):
                    return idx(1190)
                if self.CheckShouldNoMoreSpSummon(CardLocation.Deck):
                    return idx(1190)
                return idx(1152)
        current = None if Duel.GetCurrentChainCard() is not None else Duel.GetCurrentSolvingChainInfo()
        chainCard = Duel.GetCurrentChainCard()
        if chainCard is not None and chainCard.IsCode(CardId.MixedHellGod) and chainCard.Location == CardLocation.SpellZone:
            mixedPick = self.PickMixedHellGodPendulumOption(options)
            if mixedPick >= 0:
                return mixedPick
        if current is not None and current.IsActivateCode(CardId.MixedHellGod):
            mixedPick = self.PickMixedHellGodPendulumOption(options)
            if mixedPick >= 0:
                return mixedPick
        return super().OnSelectOption(options)

    def OnSelectCard(self, cards, min_, max_, hint, cancelable):
        if self.AI.HaveSelectedCards():
            return None
        if hint == HintMsg.SynchroMaterial or hint == HintMsg.SYNCHRO:
            accelMats = self.SelectAccel2WindChickenMaterials(cards, min_, max_)
            if accelMats is not None:
                return accelMats
            return super().OnSelectCard(cards, min_, max_, hint, cancelable)
        activating = self.Duel.GetCurrentChainCard()
        solving = self.Duel.GetCurrentSolvingChainInfo()
        if hint == HintMsg.Tribute or hint == HintMsg.Release:
            return self.SelectElfnoteTributes(cards, min_, max_)
        if activating is not None:
            costPick = self.SelectForActivatingCard(activating, cards, min_, max_, hint)
            if costPick is not None:
                return costPick
        if solving is not None:
            solvePick = self.SelectForSolvingCard(solving, cards, min_, max_, hint)
            if solvePick is not None:
                return solvePick
        if hint in (HintMsg.Disable, HintMsg.Target, HintMsg.Destroy, HintMsg.Remove):
            problems = self.GetProblematicEnemyCardList(True, False, 0)
            picked = []
            for card in problems:
                if card in cards and card not in self.currentNegateCardList and card not in self.currentDestroyCardList:
                    picked.append(card)
            for card in cards:
                if card is not None and card.Controller == 1 and card not in picked \
                        and card not in self.currentNegateCardList and card not in self.currentDestroyCardList:
                    picked.append(card)
            if len(picked) > 0:
                return self.Util.CheckSelectCount(picked, cards, min_, max_)
        if (hint == HintMsg.Discard or hint == HintMsg.ToGrave) and cards is not None and len(cards) > 0 \
                and all(c is not None and c.Controller == 0 and c.Location == CardLocation.Hand for c in cards):
            return self.SelectHandDiscard(cards, min_, max_)
        return super().OnSelectCard(cards, min_, max_, hint, cancelable)

    def OnSelectTribute(self, cards, min_, max_, hint, cancelable):
        picked = self.SelectElfnoteTributes(cards, min_, max_)
        if picked is not None:
            return picked
        return super().OnSelectTribute(cards, min_, max_, hint, cancelable)

    def OnSelectSynchroMaterial(self, cards, mandatoryCards, sum_, min_, max_):
        accelMats = self.SelectAccel2WindChickenMaterials(cards, min_, max_)
        if accelMats is not None:
            return accelMats
        return None

    def SelectForActivatingCard(self, activating, cards, min_, max_, hint):
        Bot, Duel, Util = self.Bot, self.Duel, self.Util
        if activating.IsCode(CardId.BaronneDeFleur) and (hint == HintMsg.Destroy or hint == HintMsg.Target):
            ranked = self.GetNormalEnemyTargetList(True, False)
            picked = []
            for card in ranked:
                if card in cards and card not in picked:
                    picked.append(card)
            if len(picked) > 0:
                if picked[0] not in self.currentDestroyCardList:
                    self.currentDestroyCardList.append(picked[0])
                return Util.CheckSelectCount(picked, cards, min_, max_)

        if activating.IsCode(_CardId.EffectVeiler) and (hint == HintMsg.Disable or hint == HintMsg.Target):
            veilerPick = None
            p = self.preferNegateCard
            if p is not None:
                for card in cards:
                    if card is None:
                        continue
                    if card == p or (card.Id == p.Id and card.Controller == p.Controller and card.Location == p.Location
                                     and card.Sequence == p.Sequence):
                        veilerPick = card
                        break
            if veilerPick is None:
                if Duel.CurrentChain is not None:
                    for i in range(len(Duel.CurrentChain) - 1, -1, -1):
                        chainingCard = Duel.CurrentChain[i]
                        if chainingCard is None or chainingCard == activating:
                            continue
                        if chainingCard.Controller != 1:
                            continue
                        if chainingCard.Location != CardLocation.MonsterZone:
                            continue
                        if chainingCard not in cards:
                            continue
                        veilerPick = chainingCard
                        break
                if veilerPick is None:
                    for card in self.GetMonsterListForTargetNegate(True, CardType.Monster):
                        if card is not None and card in cards:
                            veilerPick = card
                            break
            self.preferNegateCard = None
            if veilerPick is not None:
                if veilerPick not in self.currentNegateCardList:
                    self.currentNegateCardList.append(veilerPick)
                return Util.CheckSelectCount([veilerPick], cards, min_, max_)

        if activating.IsCode(CardId.ElvenotesWind) and hint == HintMsg.ToGrave:
            dodge = self.GetWindDodgeTarget()
            cost = self.GetWindCostCard(activating)
            matched = None
            want = dodge if dodge is not None else cost
            if want is not None and cards is not None:
                for card in cards:
                    if self.SameFieldCard(card, want):
                        matched = card
                        break
                if matched is None and dodge is not None:
                    for card in cards:
                        if card is None or card.Controller != 0:
                            continue
                        if card.Location != CardLocation.MonsterZone:
                            continue
                        if not card.IsCode(dodge.Id):
                            continue
                        matched = card
                        break
            if matched is not None:
                return Util.CheckSelectCount([matched], cards, min_, max_)
            if dodge is not None:
                if min_ == 0:
                    return []
                return None
            fallback = [c for c in cards if c is not None and not self.IsPendulumZoneCard(c)
                        and c.HasSetcode(SetcodeElvenotes) and not c.HasType(CardType.Synchro)
                        and not c.IsCode(CardId.JailChicken, CardId.RedField)
                        and not self.CheckWhetherBotWillBeBanished(c)
                        and not (c.IsFacedown() and (c.Location == CardLocation.SpellZone or c.Location == CardLocation.MonsterZone))]
            green = next((c for c in fallback if c.IsCode(CardId.GreenField)), None)
            if green is not None:
                return Util.CheckSelectCount([green], cards, min_, max_)
            if len(fallback) > 0:
                return Util.CheckSelectCount(fallback, cards, min_, max_)
            if min_ == 0:
                return []

        if activating.IsCode(CardId.GreenField, CardId.RedField) and hint == HintMsg.ToGrave:
            if activating.IsCode(CardId.GreenField) and self.ShouldFuwalosGreenFieldSummonRed() and not self.IsCenterEmpty():
                centerRed = self.GetCenterMonster()
                if centerRed is not None and centerRed in cards and centerRed.IsCode(CardId.ElvenotesBlue) \
                        and self.IsGreenFieldAcceptableCost(centerRed, CardAttribute.Fire):
                    return Util.CheckSelectCount([centerRed], cards, min_, max_)
            if activating.IsCode(CardId.GreenField) and self.WantGreenFieldSummonWind() and not self.IsCenterEmpty():
                center = self.GetCenterMonster()
                if center is not None and center in cards and self.CanGreenFieldSendCenterForWind(center):
                    return Util.CheckSelectCount([center], cards, min_, max_)
            canWhite7 = activating.IsCode(CardId.RedField) and Bot.HasInGraveyard(CardId.White7)
            canWhite10 = activating.IsCode(CardId.RedField) and Bot.HasInGraveyard(CardId.White10)
            preferSpear = Duel.Player == 1 and Bot.HasInMonstersZone(CardId.ThousandSpearDragon) and self.EnemyHasWorthNegate()
            forNegate = activating.IsCode(CardId.RedField) and Duel.Player == 1 and self.EnemyHasWorthNegate()
            avoidAttr = 0
            if activating.IsCode(CardId.GreenField):
                if self.WantGreenFieldSummonWind():
                    avoidAttr = CardAttribute.Wind
                elif Bot.HasInDeck(CardId.JailChicken):
                    avoidAttr = CardAttribute.Fire
            if activating.IsCode(CardId.GreenField):
                greenCost = self.GetGreenFieldCostMonster(avoidAttr)
                if greenCost is not None and greenCost in cards:
                    return Util.CheckSelectCount([greenCost], cards, min_, max_)
                legal = None
                for card in cards:
                    if self.IsGreenFieldAcceptableCost(card, avoidAttr):
                        legal = card
                        break
                if legal is not None:
                    return Util.CheckSelectCount([legal], cards, min_, max_)
                if min_ == 0:
                    return []
                nonEnd = [card for card in cards if card is not None and not self.IsGreenFieldEndBoardCost(card)]
                if len(nonEnd) > 0:
                    return Util.CheckSelectCount(nonEnd, cards, min_, max_)
                return Util.CheckSelectCount(cards, cards, min_, max_)
            cost = self.GetRedFieldCostMonster(canWhite7, canWhite10, preferSpear, forNegate, avoidAttr)
            if cost is None or cost not in cards:
                cost = self.GetRedFieldCostMonster(canWhite7, canWhite10, preferSpear, forNegate, 0)
            if cost is not None and cost in cards:
                return Util.CheckSelectCount([cost], cards, min_, max_)
            order = [CardId.MediusTheInnocent, _CardId.MulcharmyFuwalos, _CardId.MulcharmyPurulia, CardId.GreatRighteousThief,
                     CardId.ElvenotesWind, CardId.ElvenotesBlue, CardId.ElvenotesYellow]
            return self.PreferCards(cards, order, min_, max_)

        if activating.IsCode(CardId.RedField) and (hint == HintMsg.SpSummon or hint == HintMsg.Target):
            chickenOnField = any(c is not None and c.IsCode(CardId.JailChicken) and c.IsFaceup() for c in Bot.GetMonsters())
            if Duel.Player == 1:
                order = [CardId.White10, CardId.White7]
                if not chickenOnField:
                    order.append(CardId.JailChicken)
                order.extend([CardId.ElvenotesWind, CardId.ElvenotesRed, CardId.ElvenotesBlue, CardId.ElvenotesYellow])
                if chickenOnField:
                    order.append(CardId.JailChicken)
                return self.PreferCards(cards, order, min_, max_)
            gyWhite7 = any(c is not None and c.IsCode(CardId.White7) and c.Location == CardLocation.Grave for c in cards)
            preferWhite7Select = self.ShouldPreferRedFieldGyWhite7()
            if gyWhite7 and preferWhite7Select:
                white7First = [CardId.White7, CardId.White10, CardId.JailChicken, CardId.ElvenotesYellow, CardId.ElvenotesBlue]
                return self.PreferCards(cards, white7First, min_, max_)
            selfOrder = [CardId.JailChicken, CardId.White10, CardId.White7, CardId.ElvenotesYellow, CardId.ElvenotesBlue]
            return self.PreferCards(cards, selfOrder, min_, max_)

        if activating.IsCode(CardId.ThousandSpearDragon) and hint == HintMsg.Discard:
            order = [_CardId.MulcharmyFuwalos, _CardId.MulcharmyPurulia, CardId.ElvenotesBlue, CardId.GreatRighteousThief]
            return self.PreferCards(cards, order, min_, max_)

        if activating.IsCode(CardId.AncientFishDragon) and hint == HintMsg.Discard:
            return self.SelectHandDiscard(cards, min_, max_)

        if activating.IsCode(CardId.AncientFishDragon) and (hint == HintMsg.Destroy or hint == HintMsg.Target):
            picked = []
            for card in self.GetAncientFishDestroyTargets():
                if card in cards:
                    picked.append(card)
            for card in cards:
                if card is not None and card.Controller == 1 and card not in picked and not self.ShouldSkipAncientFishDestroy(card):
                    picked.append(card)
            if len(picked) > 0:
                return Util.CheckSelectCount(picked, cards, min_, max_)

        if activating.IsCode(CardId.ThousandSpearDragon) and hint == HintMsg.Remove:
            return self.SelectThousandSpearBanish(cards, min_, max_)

        if activating.IsCode(CardId.JailChicken) and hint == HintMsg.Target:
            center = next((c for c in cards if c is not None and c.Sequence == 2 and c.Controller == 0), None)
            if center is not None:
                return Util.CheckSelectCount([center], cards, min_, max_)

        if activating.IsCode(CardId.MediusTheInnocent) and hint == HintMsg.ToDeck:
            return self.SelectMediusToDeck(cards, min_, max_)

        if activating.IsCode(CardId.White7) and hint == HintMsg.SpSummon:
            return self.SelectWhite7SpSummon(cards, min_, max_)

        if activating.Controller == 0 and activating.IsCode(CardId.PSYFramelordOmega) \
                and activating.Location == CardLocation.Grave and hint == HintMsg.ToDeck:
            return self.SelectOmegaGyToDeck(cards, min_, max_)
        return None

    def SelectForSolvingCard(self, solving, cards, min_, max_, hint):
        Bot, Util, act = self.Bot, self.Util, self.activatedCardIdList
        G = CardLocation.Grave
        Prefer = self.PreferCards
        if solving.IsActivateCode(CardId.ElvenotesRed) and hint == HintMsg.AddToHand:
            chickenFirst = not Bot.HasInHand(CardId.JailChicken) and _CardId.LockBird not in self.enemyResolvedEffectIdList \
                and not Bot.HasInMonstersZone(CardId.JailChicken) and self.CheckWhetherCanSummon()
            needYellowForRedField = not chickenFirst and CardId.ElvenotesYellow not in act \
                and not Bot.HasInSpellZone(CardId.RedField, True, True) \
                and (Bot.HasInDeck(CardId.RedField) or Bot.HasInHand(CardId.RedField)) \
                and not Bot.HasInHand(CardId.ElvenotesYellow) and not Bot.HasInMonstersZone(CardId.ElvenotesYellow) \
                and CardId.ElvenotesYellow not in self.spSummonedCardIdList and self.IsCenterEmpty()
            wantWhiteP = self.RedSearchWhitePCanTriggerDraw()
            order = []
            if chickenFirst:
                order.append(CardId.JailChicken)
            elif needYellowForRedField:
                order.append(CardId.ElvenotesYellow)
            if wantWhiteP:
                order.append(CardId.WhitePendulum)
            order.extend([CardId.ElvenotesWind, CardId.ElvenotesBlue, CardId.ElvenotesYellow])
            if self.CountOwnedWhitePendulum() < 2 and CardId.WhitePendulum not in order:
                order.append(CardId.WhitePendulum)
            if not chickenFirst:
                order.append(CardId.JailChicken)
            return Prefer(cards, order, min_, max_)

        if solving.IsActivateCode(CardId.ElvenotesRed) and hint == HintMsg.ReturnToHand:
            return self.SelectRedBounceTarget(cards, min_, max_)

        if solving.IsActivateCode(CardId.ElvenotesBlue) and hint == HintMsg.ToField:
            if not self.DefaultCheckWhetherBotCanSearch():
                return Prefer(cards, [CardId.GreenField, CardId.InnocentArt], min_, max_)
            greenInDeck = any(c is not None and c.IsCode(CardId.GreenField) for c in cards)
            artInDeck = any(c is not None and c.IsCode(CardId.InnocentArt) for c in cards)
            needGreen = greenInDeck and not Bot.HasInSpellZone(CardId.GreenField) and not Bot.HasInHand(CardId.GreenField)
            needArt = artInDeck and not Bot.HasInHand(CardId.MediusTheInnocent) and not needGreen
            if needGreen:
                return Prefer(cards, [CardId.GreenField, CardId.InnocentArt], min_, max_)
            if needArt:
                return Prefer(cards, [CardId.InnocentArt, CardId.GreenField], min_, max_)
            if greenInDeck:
                return Prefer(cards, [CardId.GreenField, CardId.InnocentArt], min_, max_)
            return Prefer(cards, [CardId.InnocentArt, CardId.GreenField], min_, max_)

        if solving.IsActivateCode(CardId.ElvenotesYellow) and hint == HintMsg.ToField:
            return Prefer(cards, [CardId.RedField], min_, max_)

        if solving.IsActivateCode(CardId.ElvenotesYellow) and hint == HintMsg.ReturnToHand:
            ranked = []
            for card in cards:
                if card is not None and card.Controller == 1 and self.CanYellowBounceToHand(card) \
                        and not self.IsAlreadyMarkedNegate(card) and card not in ranked:
                    ranked.append(card)
            for card in cards:
                if card is None or card in ranked:
                    continue
                if self.IsAlreadyMarkedNegate(card):
                    continue
                if card.IsCode(CardId.RedField, CardId.GreenField) and card.Controller == 0:
                    continue
                if self.CanYellowBounceToHand(card):
                    ranked.append(card)
            if len(ranked) == 0:
                return []
            return Util.CheckSelectCount(ranked, cards, min_, max_)

        if solving.IsActivateCode(CardId.JailChicken) and hint == HintMsg.SpSummon:
            synchroOrder = [CardId.White10]
            if self.chickenDodgeSynchroThisChain and self.chickenDodgeSynchroCardId == CardId.White7:
                synchroOrder = [CardId.White7, CardId.White10]
            elif self.chickenDodgeSynchroThisChain:
                synchroOrder = [CardId.White10, CardId.White7]
            return Prefer(cards, synchroOrder, min_, max_)

        if solving.IsActivateCode(CardId.JailChicken) and hint == HintMsg.AddToHand:
            blueGreen = Bot.HasInDeck(CardId.GreenField) and CardId.GreenField not in act
            blueArt = Bot.HasInDeck(CardId.InnocentArt) and Bot.HasInDeck(CardId.MediusTheInnocent) \
                and CardId.MediusTheInnocent not in act and self.CheckWhetherCanSummon()
            pickBlue = blueGreen or blueArt
            if self.IsFuwalosOnlyOpeningCompromise():
                return Prefer(cards, [CardId.ElvenotesYellow, CardId.ElvenotesWind, CardId.ElvenotesRed, CardId.ElvenotesBlue], min_, max_)
            if pickBlue:
                order = [CardId.ElvenotesBlue, CardId.ElvenotesYellow, CardId.ElvenotesWind, CardId.ElvenotesRed]
            else:
                order = [CardId.ElvenotesYellow, CardId.ElvenotesWind, CardId.ElvenotesRed, CardId.ElvenotesBlue]
            if not self.DefaultCheckWhetherBotCanSearch():
                if pickBlue:
                    order = [CardId.ElvenotesBlue, CardId.ElvenotesYellow, CardId.ElvenotesWind]
                else:
                    order = [CardId.ElvenotesYellow, CardId.ElvenotesWind, CardId.ElvenotesBlue]
            elif Bot.HasInHand(CardId.ElvenotesBlue) or Bot.HasInMonstersZone(CardId.ElvenotesBlue) or CardId.ElvenotesBlue in act:
                order = [CardId.ElvenotesYellow, CardId.ElvenotesWind, CardId.ElvenotesRed, CardId.ElvenotesBlue]
            if pickBlue and self.DefaultCheckWhetherBotCanSearch() and Bot.HasInSpellZone(CardId.RedField):
                if not Bot.HasInHand(CardId.ElvenotesBlue) and not Bot.HasInMonstersZone(CardId.ElvenotesBlue):
                    order = [CardId.ElvenotesBlue, CardId.ElvenotesWind, CardId.ElvenotesRed]
            return Prefer(cards, order, min_, max_)

        if solving.IsActivateCode(CardId.MediusTheInnocent) and hint == HintMsg.ToDeck:
            return self.SelectMediusToDeck(cards, min_, max_)

        if solving.IsActivateCode(CardId.MediusTheInnocent) and hint == HintMsg.OperateCard:
            maxx = _CardId.MaxxC in self.enemyResolvedEffectIdList
            noZone = len(Bot.GetMonstersInMainZone()) >= 4
            mixedPUsed = CardId.MixedHellGod in act
            J, M, W = CardId.JailChicken, CardId.MixedHellGod, CardId.WhitePendulum
            if self.ShouldFuwalosMediusSsChickenFromDeck():
                return Prefer(cards, [J, M, W], min_, max_)
            if not self.DefaultCheckWhetherBotCanSearch():
                return Prefer(cards, [J], min_, max_)
            if not mixedPUsed and (maxx or noZone):
                return Prefer(cards, [M, W, J], min_, max_)
            if mixedPUsed and (maxx or len(Bot.GetMonstersInMainZone()) >= 5):
                return Prefer(cards, [W, J, M], min_, max_)
            if Bot.HasInGraveyard(J) and not mixedPUsed:
                return Prefer(cards, [M, W, J], min_, max_)
            if not Bot.HasInGraveyard(J) and Bot.HasInExtra(CardId.SuperLibrarian) and not noZone:
                return Prefer(cards, [J, M, W], min_, max_)
            if self.NeedPendulumScale() and not mixedPUsed:
                return Prefer(cards, [W, J, M], min_, max_)
            return Prefer(cards, [J, M, W], min_, max_)

        if solving.IsActivateCode(CardId.JailGodGate) and hint == HintMsg.ToGrave:
            return self.SelectJailGateMill(cards, min_, max_)

        if solving.IsActivateCode(CardId.JailGodGate) and hint == HintMsg.AddToHand:
            hasMedius = Bot.HasInHand(CardId.MediusTheInnocent) or Bot.HasInMonstersZone(CardId.MediusTheInnocent)
            if not hasMedius and any(c is not None and c.IsCode(CardId.MediusTheInnocent) for c in cards):
                return Prefer(cards, [CardId.MediusTheInnocent, CardId.MixedHellGod], min_, max_)
            return Prefer(cards, [CardId.MixedHellGod, CardId.MediusTheInnocent], min_, max_)

        if solving.IsActivateCode(CardId.GreenField) and hint == HintMsg.SpSummon:
            if self.ShouldFuwalosGreenFieldSummonRed():
                order = [CardId.ElvenotesRed, CardId.JailChicken, CardId.ElvenotesYellow, CardId.ElvenotesBlue, CardId.ElvenotesWind]
            elif self.WantGreenFieldSummonWind():
                order = [CardId.ElvenotesWind, CardId.JailChicken, CardId.ElvenotesYellow, CardId.ElvenotesBlue, CardId.ElvenotesRed]
            elif self.CountFaceupChickenOnField() == 0:
                order = [CardId.JailChicken, CardId.ElvenotesYellow, CardId.ElvenotesBlue, CardId.ElvenotesRed]
            else:
                order = [CardId.ElvenotesYellow, CardId.ElvenotesBlue, CardId.ElvenotesRed, CardId.JailChicken]
            return Prefer(cards, order, min_, max_)

        if solving.IsActivateCode(CardId.ElvenotesWind) and hint == HintMsg.SpSummon:
            return self.SelectWindDeckSpSummon(cards, min_, max_)

        if solving.IsActivateCode(CardId.White7) and hint == HintMsg.SpSummon:
            return self.SelectWhite7SpSummon(cards, min_, max_)

        if solving.IsActivateCode(CardId.White10) and hint == HintMsg.SpSummon:
            return self.SelectWhite10SpSummon(cards, min_, max_)

        if solving.ActivatePlayer == 0 and solving.IsActivateCode(CardId.PSYFramelordOmega) and hint == HintMsg.ToDeck:
            return self.SelectOmegaGyToDeck(cards, min_, max_)

        if solving.IsActivateCode(CardId.WhitePendulum) and hint == HintMsg.Discard:
            return Prefer(cards, [_CardId.MulcharmyFuwalos, _CardId.MulcharmyPurulia, CardId.ElvenotesBlue, CardId.ElvenotesRed], min_, max_)

        if solving.IsActivateCode(CardId.WhitePendulum) and hint == HintMsg.AddToHand:
            ranked = []
            green = next((c for c in cards if c is not None and c.IsCode(CardId.GreenField) and c.Location == G), None)
            if green is not None and not Bot.HasInHand(CardId.GreenField) and not Bot.HasInSpellZone(CardId.GreenField):
                ranked.append(green)
            unusedRed = next((c for c in cards if c is not None and c.IsCode(CardId.ElvenotesRed) and c.Location == G
                              and self.CanElvenotesRedSearch()), None)
            unusedYellow = next((c for c in cards if c is not None and c.IsCode(CardId.ElvenotesYellow) and c.Location == G
                                 and CardId.ElvenotesYellow not in act), None)
            if unusedRed is not None:
                ranked.append(unusedRed)
            if unusedYellow is not None:
                ranked.append(unusedYellow)
            field = next((c for c in cards if c is not None and (c.IsCode(CardId.RedField) or c.IsCode(CardId.GreenField))), None)
            if field is not None and field not in ranked:
                ranked.append(field)
            mixedPUsedThisTurn = CardId.MixedHellGod in act
            usedMixed = []
            for card in cards:
                if card is None or not card.IsCode(CardId.MixedHellGod) or card in ranked:
                    continue
                if mixedPUsedThisTurn and card.Location == CardLocation.Extra:
                    usedMixed.append(card)
                else:
                    ranked.append(card)
            keepChickenForWhite7 = self.White7StillWantsGyChicken()
            remaining, extraMonsters = [], []
            for card in cards:
                if card is None or card in ranked or card in usedMixed:
                    continue
                if card.HasType(CardType.Fusion | CardType.Ritual | CardType.Synchro | CardType.Xyz | CardType.Link):
                    extraMonsters.append(card)
                    continue
                if keepChickenForWhite7 and card.IsCode(CardId.JailChicken) and card.Location == G:
                    continue
                remaining.append(card)
            if keepChickenForWhite7:
                for card in cards:
                    if card is not None and card.IsCode(CardId.JailChicken) and card.Location == G and card not in ranked:
                        ranked.append(card)
            for card in usedMixed + remaining + extraMonsters:
                if card not in ranked:
                    ranked.append(card)
            return Util.CheckSelectCount(ranked, cards, min_, max_)

        if solving.IsActivateCode(CardId.InnocentArt) and hint == HintMsg.AddToHand:
            return Prefer(cards, [CardId.MediusTheInnocent], min_, max_)

        if solving.IsActivateCode(CardId.AccelSynchroStardust) and hint == HintMsg.SpSummon:
            if any(c is not None and c.IsCode(CardId.JailChicken) and c.Location == G for c in cards):
                return Prefer(cards, [CardId.JailChicken], min_, max_)
            if any(c is not None and c.IsCode(CardId.StardustDragon) for c in cards):
                return Prefer(cards, [CardId.StardustDragon, CardId.AncientFishDragon, CardId.ThousandSpearDragon], min_, max_)
            secondOrder = []
            if self.CanAccelSecondSynchroUseWindForSeven():
                hasFormula = any(c is not None and c.IsCode(CardId.FormulaAthleteLightning) for c in cards)
                hasWhite7 = self.White7EffectStillAvailable() and any(c is not None and c.IsCode(CardId.White7) for c in cards)
                if hasFormula or hasWhite7:
                    if hasFormula:
                        secondOrder.append(CardId.FormulaAthleteLightning)
                    else:
                        secondOrder.append(CardId.White7)
                    self.accel2PreferWindChicken = True
                    return Prefer(cards, secondOrder, min_, max_)
            if self.CheckThousandSpearGoingFirstLine() or self.CheckThousandSpearGoingSecondLine():
                self.SelectSynchroMaterials(9, True)
                secondOrder.append(CardId.ThousandSpearDragon)
                secondOrder.append(CardId.AncientFishDragon)
                return Prefer(cards, secondOrder, min_, max_)
            self.SelectSynchroMaterials(9, True)
            secondOrder.extend([CardId.AncientFishDragon, CardId.ThousandSpearDragon, CardId.StardustDragon])
            return Prefer(cards, secondOrder, min_, max_)

        if solving.IsActivateCode(CardId.ThousandSpearDragon) and (hint == HintMsg.Remove or hint == HintMsg.ReturnToHand):
            return self.SelectThousandSpearBanish(cards, min_, max_)

        if solving.IsActivateCode(CardId.MixedHellGod) and hint == HintMsg.SpSummon:
            gyChicken = next((c for c in cards if c is not None and c.IsCode(CardId.JailChicken) and c.Location == G), None)
            if gyChicken is not None:
                return Util.CheckSelectCount([gyChicken], cards, min_, max_)
            return Prefer(cards, [CardId.JailChicken], min_, max_)

        if solving.IsActivateCode(CardId.MixedHellGod) and hint == HintMsg.AddToHand:
            return self.SelectMixedHellGodSearch(cards, min_, max_)

        if solving.IsActivateCode(CardId.RedField) and hint == HintMsg.Disable:
            picked = self.GetRedFieldDisableOrder(cards)
            if len(picked) > 0:
                self.currentNegateCardList.append(picked[0])
                return Util.CheckSelectCount(picked, cards, min_, max_)
        return None

    def SelectThousandSpearBanish(self, cards, min_, max_):
        ranked = []
        dangerGy = self.GetDangerousCardinEnemyGrave(False)
        problems = self.GetProblematicEnemyCardList(False, False, 0)
        for card in dangerGy + problems:
            if card in cards and card not in ranked and card not in self.currentNegateCardList and card not in self.currentDestroyCardList:
                ranked.append(card)
        for card in cards:
            if card is not None and card.Controller == 1 and card not in ranked:
                ranked.append(card)
        return self.Util.CheckSelectCount(ranked, cards, min_, max_)

    def NeedPendulumScale(self):
        sz = self.Bot.SpellZone
        left = sz[0] is not None and sz[0].HasType(CardType.Pendulum)
        right = sz[4] is not None and sz[4].HasType(CardType.Pendulum)
        return not left or not right

    # --- counters and hand traps ------------------------------------------------------------------------------
    def EffectVeilerActivate(self):
        if self.CheckWhetherNegated(True):
            return False
        shouldNegateList = self.GetMonsterListForTargetNegate(True, CardType.Monster)
        if len(shouldNegateList) > 0:
            last = self.Util.GetLastChainCard()
            if last is not None and last.IsCode(CardId.ElvenotesWind) and last.Controller == 1 and len(shouldNegateList) == 1:
                return False
            target = shouldNegateList[0]
            if last is not None and last.Controller == 1 and last.Location == CardLocation.MonsterZone and last in shouldNegateList:
                target = last
            self.preferNegateCard = target
            return True
        return False

    def AshBlossomActivate(self):
        if self.CheckWhetherNegated(True) or not self.CheckLastChainShouldNegated():
            return False
        last = self.Util.GetLastChainCard()
        if self.DefaultAshBlossomAndJoyousSpring():
            if last is not None:
                self.currentNegateCardList.append(last)
            return True
        return False

    def BaronneNegateActivate(self):
        if self.ActivateDescription != self.Util.GetStringId(CardId.BaronneDeFleur, 1) and self.ActivateDescription != -1:
            return False
        if self.CheckWhetherNegated(True) or not self.CheckLastChainShouldNegated():
            return False
        last = self.Util.GetLastChainCard()
        if last is not None:
            self.currentNegateCardList.append(last)
        return True

    def BaronneDestroyActivate(self):
        if self.ActivateDescription == self.Util.GetStringId(CardId.BaronneDeFleur, 1):
            return False
        if self.Duel.Phase == DuelPhase.Standby or self.ActivateDescription == self.Util.GetStringId(CardId.BaronneDeFleur, 2):
            return self.BaronneStandbyReviveActivate()
        if self.CheckWhetherNegated(True):
            return False
        targetList = self.GetNormalEnemyTargetList(True, False)
        if len(targetList) == 0:
            return False
        self.currentDestroyCardList.append(targetList[0])
        return True

    def BaronneStandbyReviveActivate(self):
        return False  # WindBot TODO: Baronne Standby revive not implemented

    def CrystalWingActivate(self):
        if self.CheckWhetherNegated(True) or not self.CheckLastChainShouldNegated():
            return False
        last = self.Util.GetLastChainCard()
        if last is None or not last.IsMonster():
            return False
        self.currentNegateCardList.append(last)
        return True

    def FormulaAthleteActivate(self):
        if self.CheckWhetherNegated(True) or not self.CheckLastChainShouldNegated():
            return False
        last = self.Util.GetLastChainCard()
        if last is None or (not last.IsSpell() and not last.IsTrap()):
            return False
        self.currentNegateCardList.append(last)
        return True

    def GreatRighteousThiefNegateActivate(self):
        if self.CheckWhetherNegated(True) or not self.CheckLastChainShouldNegated():
            return False
        if self.ActivateDescription == self.Util.GetStringId(CardId.GreatRighteousThief, 2):
            return False
        last = self.Util.GetLastChainCard()
        if last is None:
            return False
        if last.Location != CardLocation.Hand and last.Location != CardLocation.Grave and last.Location != CardLocation.Removed:
            return False
        self.currentNegateCardList.append(last)
        return True

    def GreatRighteousThiefBattleActivate(self):
        if self.ActivateDescription != self.Util.GetStringId(CardId.GreatRighteousThief, 2) and self.ActivateDescription != -1:
            return False
        if self.Duel.Phase < DuelPhase.BattleStart or self.Duel.Phase > DuelPhase.Battle:
            return False
        return any(c is not None and c.IsAttack() for c in self.Enemy.GetMonsters())

    def AccelStardustActivate(self):
        Bot, Duel, Util = self.Bot, self.Duel, self.Util
        if self.CheckWhetherNegated(True):
            return False
        if self.Card.Location != CardLocation.MonsterZone:
            return False
        if self.ActivateDescription == Util.GetStringId(CardId.AccelSynchroStardust, 0) or self.ActivateDescription == -1:
            if Bot.HasInGraveyard(CardId.JailChicken) and not self.CheckShouldNoMoreSpSummon(CardLocation.Grave):
                self.activatedCardIdList.append(CardId.AccelSynchroStardust)
                return True
            if self.ActivateDescription == Util.GetStringId(CardId.AccelSynchroStardust, 0):
                return any(c is not None and c.IsTuner() and c.Level <= 2 for c in Bot.Graveyard)
        if Duel.Phase != DuelPhase.Main1 and Duel.Phase != DuelPhase.Main2:
            return False
        librarian = Bot.HasInMonstersZone(CardId.SuperLibrarian, True, False, True)
        if Duel.Player == 0 and librarian:
            self.activatedCardIdList.append(CardId.AccelSynchroStardust + 1)
            return True
        if Duel.Player == 1:
            if self.Accel2OwnWaitableOnChain():
                return False
            if self.ShouldWaitChickenWhite10BeforeAccel2():
                return False
            self.activatedCardIdList.append(CardId.AccelSynchroStardust + 1)
            return True
        return False

    def StardustDragonActivate(self):
        if self.CheckWhetherNegated(True):
            return False
        last = self.Util.GetLastChainCard()
        if last is None:
            return True
        return self.Duel.LastChainPlayer == 1

    def IsExtraDeckMonster(self, card):
        if card is None:
            return False
        return card.HasType(CardType.Fusion | CardType.Synchro | CardType.Xyz | CardType.Link)

    def IsOwnUsedUpOmegaRecycleCard(self, card):
        act = self.activatedCardIdList
        if card is None or card.Controller != 0:
            return False
        if card.IsCode(CardId.ElvenotesWind):
            return CardId.ElvenotesWind in act or CardId.ElvenotesWind + 1 in act
        if card.IsCode(CardId.JailChicken):
            return CardId.JailChicken in act or CardId.JailChicken + 1 in act
        if card.IsCode(CardId.MediusTheInnocent):
            return CardId.MediusTheInnocent in act
        if card.IsCode(CardId.InnocentArt):
            return self.artSearched
        return card.Id in act

    def SelectOmegaGyToDeck(self, cards, min_, max_):
        if cards is None:
            return None
        G = CardLocation.Grave
        omegaSelf = self.Duel.GetCurrentChainCard()
        pool = []
        for card in cards:
            if card is None:
                continue
            if omegaSelf is not None and card == omegaSelf:
                continue
            if card.Controller == 0 and card.Location == G and card.IsCode(CardId.PSYFramelordOmega):
                continue
            pool.append(card)
        ranked = []
        for fieldId in (CardId.RedField, CardId.GreenField):
            for card in pool:
                if card in ranked:
                    continue
                if card.Controller != 0 or card.Location != G:
                    continue
                if not card.IsCode(fieldId):
                    continue
                ranked.append(card)
        for danger in self.GetDangerousCardinEnemyGrave(False):
            if danger is None or danger not in pool or danger in ranked:
                continue
            ranked.append(danger)
        own = lambda c: c not in ranked and c.Location == G and c.Controller == 0
        for card in pool:
            if own(card) and self.IsExtraDeckMonster(card) and not card.IsCode(CardId.White10, CardId.White7):
                ranked.append(card)
        for card in pool:
            if own(card) and not self.IsExtraDeckMonster(card) and self.IsOwnUsedUpOmegaRecycleCard(card):
                ranked.append(card)
        for card in pool:
            if own(card) and card.IsCode(CardId.White10):
                ranked.append(card)
        for card in pool:
            if own(card) and card.IsCode(CardId.White7):
                ranked.append(card)
        if len(ranked) == 0:
            return None
        return self.Util.CheckSelectCount(ranked, cards, min_, max_)

    def PSYOmegaActivate(self):
        Bot, Enemy, Duel, Card = self.Bot, self.Enemy, self.Duel, self.Card
        if self.CheckWhetherNegated(True):
            return False
        if Card.Location == CardLocation.Grave:
            dangerGy = len(self.GetDangerousCardinEnemyGrave(False))
            redFieldGy = Bot.HasInGraveyard(CardId.RedField)
            if dangerGy > 0 or redFieldGy:
                return True
            return len(Enemy.Graveyard) > 0
        if Card.Location != CardLocation.MonsterZone:
            return False
        if Duel.Phase == DuelPhase.Standby:
            return Duel.Player == 1 and (any(c is not None for c in Bot.Banished) or any(c is not None for c in Enemy.Banished))
        if Duel.Phase != DuelPhase.Main1 and Duel.Phase != DuelPhase.Main2:
            return False
        if len(Enemy.Hand) <= 0:
            return False
        if len(Duel.CurrentChain) > 0 and Duel.LastChainPlayer == 0:
            return False
        if Duel.Player == 0 and Duel.Turn != 1 and Duel.Phase != DuelPhase.Main2:
            return False
        return True

    def ChaosAngelActivate(self):
        if self.CheckWhetherNegated(True):
            return False
        return self.EnemyHasChaosAngelBanishTarget()

    def MaxxCActivate(self):
        if self.CheckWhetherNegated(True) or self.Duel.LastChainPlayer == 0 or not self.DefaultCheckWhetherBotCanDraw():
            return False
        return self.DefaultMaxxC()

    def MulcharmyFuwalosActivate(self):
        Duel = self.Duel
        if self.CheckWhetherNegated(True) or Duel.Player == 0:
            return False
        if not self.DefaultCheckWhetherBotCanDraw() or any(c.IsCode(_CardId.LockBird) for c in Duel.CurrentChain):
            return False
        if Duel.Phase > DuelPhase.Main1:
            return False
        if self.CountActivatedMulcharmy() >= 2:
            return False
        self.activatedCardIdList.append(_CardId.MulcharmyFuwalos)
        return True

    def MulcharmyPuruliaActivate(self):
        Duel = self.Duel
        if self.CheckWhetherNegated(True) or Duel.Player == 0:
            return False
        if not self.DefaultCheckWhetherBotCanDraw() or any(c.IsCode(_CardId.LockBird) for c in Duel.CurrentChain):
            return False
        if Duel.Phase > DuelPhase.Main1:
            return False
        if self.CountActivatedMulcharmy() >= 2:
            return False
        self.activatedCardIdList.append(_CardId.MulcharmyPurulia)
        return True

    def CountActivatedMulcharmy(self):
        return sum(1 for id_ in self.activatedCardIdList
                   if id_ in (_CardId.MulcharmyFuwalos, _CardId.MulcharmyPurulia, _CardId.MulcharmyNyalus))

    def LockBirdActivate(self):
        if self.CheckWhetherNegated(True):
            return False
        if self.Duel.Player == 0:
            return False
        return True

    # --- starters ---------------------------------------------------------------------------------------------
    def ElvenotesRedSpSummon(self):
        Bot = self.Bot
        if self.CheckWhetherNegated(True, True, CardType.Monster):
            return False
        if self.CheckShouldNoMoreSpSummon(CardLocation.Hand) and self.CheckHasStopBoard():
            if not (_CardId.MulcharmyFuwalos in self.enemyResolvedEffectIdList and self.IsCenterEmpty()):
                return False
        if self.CheckShouldNoMoreSpSummon() and self.CheckHasStopBoard():
            return False
        if not self.IsCenterEmpty() and self.Card.Location == CardLocation.Hand:
            return False
        if self.ShouldSsYellowFirstAfterEightSynchro():
            return False
        if self.ShouldSsYellowFirstToPlaceRedField():
            return False
        if self.CanSynchroEightWithWhite7():
            return False
        if self.CanSynchroSevenWithChicken():
            return False
        if not self.DefaultCheckWhetherBotCanSearch() and not Bot.HasInHand(CardId.JailChicken) \
                and not Bot.HasInMonstersZone(CardId.JailChicken) and not Bot.HasInGraveyard(CardId.JailChicken):
            return False
        self.spSummonedCardIdList.append(CardId.ElvenotesRed)
        return True

    def ElvenotesBlueSpSummon(self):
        Bot = self.Bot
        if self.CheckWhetherNegated(True, True, CardType.Monster):
            return False
        if self.CheckShouldNoMoreSpSummon(CardLocation.Hand) and self.CheckHasStopBoard():
            return False
        if not self.IsCenterEmpty():
            return False
        if self.ShouldSsYellowFirstAfterEightSynchro():
            return False
        if self.ShouldSsYellowFirstToPlaceRedField():
            return False
        if self.CanSynchroEightWithWhite7():
            return False
        if self.CanSynchroSevenWithChicken():
            return False
        if self.Duel.Player == 0 and Bot.HasInHand(CardId.ElvenotesWind) and CardId.ElvenotesBlue not in self.activatedCardIdList \
                and Bot.HasInHand(CardId.ElvenotesRed) and self.IsCenterEmpty():
            redStillUseful = self.DefaultCheckWhetherBotCanSearch() or Bot.HasInHand(CardId.JailChicken) \
                or Bot.HasInMonstersZone(CardId.JailChicken) or Bot.HasInGraveyard(CardId.JailChicken)
            if redStillUseful:
                return False
        self.spSummonedCardIdList.append(CardId.ElvenotesBlue)
        return True

    def ElvenotesYellowSpSummon(self):
        if self.CheckWhetherNegated(True, True, CardType.Monster):
            return False
        if self.CheckShouldNoMoreSpSummon(CardLocation.Hand) and self.CheckHasStopBoard():
            return False
        if not self.IsCenterEmpty():
            return False
        if self.ShouldKeepGyChickenForMixedHellGod():
            return False
        if self.CanSynchroEightWithWhite7():
            return False
        if self.CanSynchroSevenWithChicken():
            return False
        self.spSummonedCardIdList.append(CardId.ElvenotesYellow)
        return True

    def ElvenotesRedActivate(self):
        Duel, Card, Util = self.Duel, self.Card, self.Util
        if self.CheckWhetherNegated(True):
            return False
        if Duel.Player == 0 and (self.ActivateDescription == Util.GetStringId(CardId.ElvenotesRed, 0) or self.ActivateDescription == -1):
            if Card.Location != CardLocation.MonsterZone:
                return False
            if not self.DefaultCheckWhetherBotCanSearch():
                return False
            if not self.HasElvenotesSearchTargetInDeck():
                return False
            self.activatedCardIdList.append(CardId.ElvenotesRed)
            return True
        if Duel.Player == 1 and Card.Location == CardLocation.MonsterZone and Card.Sequence != 2:
            center = self.GetCenterMonster()
            if center is None or center.Sequence != 2:
                return False
            if Duel.CurrentChain is not None:
                for chainCard in Duel.CurrentChain:
                    if chainCard is None or chainCard.Controller != 0:
                        continue
                    if chainCard.Id in self.targetNegateIdList:
                        return False
            if not self.ShouldActivateRedSwap():
                return False
            self.activatedCardIdList.append(CardId.ElvenotesRed + 3)
            return True
        return False

    def ElvenotesBlueActivate(self):
        Bot, Duel, Card = self.Bot, self.Duel, self.Card
        if self.CheckWhetherNegated(True):
            return False
        if Duel.Player == 0 and Card.Location == CardLocation.MonsterZone \
                and (self.ActivateDescription == self.Util.GetStringId(CardId.ElvenotesBlue, 0) or self.ActivateDescription == -1) \
                and Bot.GetSpellCountWithoutField() < 5:
            needGreen = Bot.HasInDeck(CardId.GreenField) and not Bot.HasInSpellZone(CardId.GreenField) and not Bot.HasInHand(CardId.GreenField)
            if not self.DefaultCheckWhetherBotCanSearch() and not needGreen:
                return False
            if not Bot.HasInDeck(CardId.GreenField) and not Bot.HasInDeck(CardId.InnocentArt):
                return False
            self.activatedCardIdList.append(CardId.ElvenotesBlue)
            return True
        if Duel.Player == 1 and Card.Location == CardLocation.MonsterZone and Card.Sequence != 2 and self.GetCenterMonster() is not None:
            if len(self.Enemy.Hand) <= 0:
                return False
            self.activatedCardIdList.append(CardId.ElvenotesBlue + 3)
            return True
        return False

    def ElvenotesYellowActivate(self):
        Bot, Duel, Card = self.Bot, self.Duel, self.Card
        if self.CheckWhetherNegated(True):
            return False
        if Duel.Player == 0 and Card.Location == CardLocation.MonsterZone:
            if Bot.HasInSpellZone(CardId.RedField, True, True):
                return False
            if not Bot.HasInDeck(CardId.RedField) and not Bot.HasInHand(CardId.RedField):
                return False
            self.activatedCardIdList.append(CardId.ElvenotesYellow)
            return True
        if Duel.Player == 1 and Card.Location == CardLocation.MonsterZone and Card.Sequence != 2 and self.GetCenterMonster() is not None:
            bounce = self.EnemyHasYellowBounceTarget()
            if not bounce:
                return False
            self.activatedCardIdList.append(CardId.ElvenotesYellow + 3)
            return True
        return False

    def ElvenotesWindActivate(self):
        Bot, Enemy, Duel, Card, act = self.Bot, self.Enemy, self.Duel, self.Card, self.activatedCardIdList
        if self.CheckWhetherNegated(True):
            return False
        if Card.Location == CardLocation.Hand:
            dodge = self.GetWindDodgeTarget()
            if dodge is not None:
                act.append(CardId.ElvenotesWind)
                return True
            if self.CheckShouldNoMoreSpSummon(CardLocation.Deck) or self.CheckShouldNoMoreSpSummon():
                fuwalosWind = self.IsFuwalosOnlyOpeningCompromise() and Duel.Player == 0 \
                    and (Bot.HasInDeck(CardId.JailChicken) or (Bot.HasInHand(CardId.JailChicken) and self.CheckWhetherCanSummon()))
                if not fuwalosWind:
                    return False
            if Duel.Phase == DuelPhase.Draw or Duel.Phase == DuelPhase.Standby:
                return False
            if len(Duel.CurrentChain) > 0 and Duel.LastChainPlayer == 0:
                return False
            cost = self.GetWindCostCard(Card)
            if cost is None:
                return False
            if cost.HasType(CardType.Synchro):
                return False
            if not self.IsCenterEmpty() and self.GetCenterMonster() != cost:
                return False
            if Duel.Player == 0 and Bot.HasInSpellZone(CardId.GreenField) and CardId.GreenField not in act \
                    and self.GetGreenFieldCostMonster() is not None:
                return False
            if Duel.Player == 0 and self.CanSynchroEightWithWhite7():
                return False
            if Duel.Player == 0 and self.HasChickenAndLevel6OnField():
                return False
            if self.CheckWhetherCanSummon() and Bot.HasInHand(CardId.JailChicken) \
                    and any(c is not None and self.IsElvenotesSixStar(c) and c.IsFaceup() for c in Bot.GetMonsters()):
                return False
            centerNow = self.GetCenterMonster()
            if Duel.Player == 0 and centerNow is not None and centerNow.IsCode(CardId.JailChicken):
                return False
            if Duel.Player == 0:
                if cost.IsCode(CardId.ElvenotesRed, CardId.ElvenotesBlue, CardId.ElvenotesYellow) and cost.Location == CardLocation.Hand:
                    return False
            if Duel.Player == 0 and CardId.ElvenotesWind + 1 in act:
                return False
            if Duel.Player == 1:
                if self.ShouldWaitOwnEnemyTurnDisruption(False, True):
                    return False
                inMain = Duel.Phase == DuelPhase.Main1 or Duel.Phase == DuelPhase.Main2
                white10Line = self.CanWindEnemyTurnWhite10Line()
                if inMain:
                    if not white10Line:
                        return False
                    act.append(CardId.ElvenotesWind)
                    return True
                if self.IsBattlePhaseNow() and Bot.GetMonsterCount() == 0 and Bot.UnderAttack \
                        and Bot.BattlingMonster is None and Enemy.BattlingMonster is not None:
                    windData = NamedCard.Get(CardId.ElvenotesWind)
                    windAtk = windData.Attack if windData is not None else 2000
                    enemyAtk = Enemy.BattlingMonster.Attack
                    if enemyAtk < windAtk or enemyAtk >= Bot.LifePoints:
                        act.append(CardId.ElvenotesWind)
                        return True
                    return False
                if not white10Line and CardId.ElvenotesWind + 1 not in act \
                        and (self.IsCenterEmpty() or self.GetCenterMonster() == cost) and self.DeckHasRbySwapTarget():
                    act.append(CardId.ElvenotesWind)
                    return True
                return False
            act.append(CardId.ElvenotesWind)
            return True
        if Card.Location == CardLocation.MonsterZone and Card.Sequence == 2:
            if self.CheckShouldNoMoreSpSummon(CardLocation.Deck):
                fuwalosWind2 = self.IsFuwalosOnlyOpeningCompromise() and Bot.HasInDeck(CardId.JailChicken) \
                    and not Bot.HasInMonstersZone(CardId.JailChicken) and not Bot.HasInHand(CardId.JailChicken)
                if not fuwalosWind2:
                    return False
            act.append(CardId.ElvenotesWind + 1)
            return True
        return False

    def ElvenotesWindGyRecycleActivate(self):
        if self.CheckWhetherNegated(True):
            return False
        if self.Card.Location != CardLocation.Grave:
            return False
        self.activatedCardIdList.append(CardId.ElvenotesWind + 2)
        return True

    def GreenFieldActivateFromHand(self):
        if self.Card.Location != CardLocation.Hand:
            return False
        if self.CheckWhetherNegated(True, True, CardType.Spell):
            return False
        if self.Bot.HasInSpellZone(CardId.GreenField):
            return False
        if CardId.ElvenotesBlue not in self.activatedCardIdList:
            return False
        return True

    def GreenFieldActivate(self):
        Bot = self.Bot
        if self.CheckWhetherNegated(True, True, CardType.Spell):
            return False
        if self.Card.Location == CardLocation.Hand:
            if Bot.HasInSpellZone(CardId.GreenField):
                return False
            return True
        if self.CheckShouldNoMoreSpSummon(CardLocation.Deck) and not self.ShouldFuwalosGreenFieldSummonRed():
            return False
        if self.ShouldFuwalosGreenFieldSummonRed():
            self.activatedCardIdList.append(CardId.GreenField)
            return True
        if self.ShouldKeepSixStarForChickenPlus3():
            return False
        if self.CountFaceupChickenOnField() >= 2 and not self.WantGreenFieldSummonWind():
            canSsSix = Bot.HasInDeck(CardId.ElvenotesYellow) or Bot.HasInDeck(CardId.ElvenotesBlue) or Bot.HasInDeck(CardId.ElvenotesRed)
            if not canSsSix:
                return False
        greenAvoid = 0
        if self.WantGreenFieldSummonWind():
            greenAvoid = CardAttribute.Wind
        elif Bot.HasInDeck(CardId.JailChicken):
            greenAvoid = CardAttribute.Fire
        greenCost = self.GetGreenFieldCostMonster(greenAvoid)
        if greenCost is None:
            return False
        if greenCost.IsCode(CardId.ElvenotesYellow) and CardId.ElvenotesYellow in self.activatedCardIdList:
            return False
        if not Bot.HasInDeck(CardId.ElvenotesWind) and not Bot.HasInDeck(CardId.JailChicken) \
                and not Bot.HasInDeck(CardId.ElvenotesYellow) and not Bot.HasInDeck(CardId.ElvenotesBlue) \
                and not Bot.HasInDeck(CardId.ElvenotesRed):
            return False
        if self.WantGreenFieldSummonWind():
            if not self.IsCenterEmpty():
                center = self.GetCenterMonster()
                if not self.CanGreenFieldSendCenterForWind(center):
                    return False
        self.activatedCardIdList.append(CardId.GreenField)
        return True

    def RedFieldActivate(self):
        Bot, Duel, Card = self.Bot, self.Duel, self.Card
        if self.CheckWhetherNegated(True, True, CardType.Trap):
            return False
        if Card.Location == CardLocation.Hand:
            return False
        effect2Desc = self.Util.GetStringId(CardId.RedField, 0)
        if self.ActivateDescription == 0:
            if Card.IsFacedown() and Card.Location == CardLocation.SpellZone:
                inBattle = DuelPhase.BattleStart <= Duel.Phase < DuelPhase.Main2
                if inBattle and self.GetCenterMonster() is not None:
                    return True
            return False
        if self.ActivateDescription != effect2Desc:
            return False
        if Duel.Player == 1:
            if Duel.Phase == DuelPhase.Draw or Duel.Phase == DuelPhase.Standby:
                return False
            wantNegate = self.EnemyHasWorthNegate()
            if not wantNegate:
                return False
            gyWhite7 = Bot.HasInGraveyard(CardId.White7)
            gyWhite10 = Bot.HasInGraveyard(CardId.White10)
            gyBoss = gyWhite7 or gyWhite10
            if not gyBoss:
                canRevive = any(c is not None and c.HasSetcode(SetcodeElvenotes) for c in Bot.Graveyard)
                if canRevive:
                    self.SetRedFieldPendingNegate()
                return canRevive
            preferSpear = Bot.HasInMonstersZone(CardId.ThousandSpearDragon) and wantNegate
            cost = self.GetRedFieldCostMonster(gyWhite7, gyWhite10, preferSpear, wantNegate)
            if cost is None:
                return False
            if cost.IsCode(CardId.ThousandSpearDragon) and not wantNegate:
                return False
            self.SetRedFieldPendingNegate()
            self.activatedCardIdList.append(CardId.RedField)
            return True
        if self.ShouldKeepGyChickenForMixedHellGod():
            return False
        if self.ShouldWaitOwnChainToResolve():
            return False
        if not self.ShouldActivateRedFieldOnOurTurn():
            return False
        reviveWhite7 = Bot.HasInGraveyard(CardId.White7) and not Bot.HasInMonstersZone(CardId.White7)
        reviveWhite10 = Bot.HasInGraveyard(CardId.White10) and not Bot.HasInMonstersZone(CardId.White10)
        preferWhite7 = self.ShouldPreferRedFieldGyWhite7()
        selfCost = self.GetRedFieldCostMonster(True, False, False, False) if preferWhite7 \
            else self.GetRedFieldCostMonster(reviveWhite7, reviveWhite10, False, False)
        if selfCost is None:
            return False
        self.activatedCardIdList.append(CardId.RedField)
        return True

    def JailGodGateActivate(self):
        Bot = self.Bot
        if self.CheckWhetherNegated(True, True, CardType.Spell):
            return False
        if self.Card.Location == CardLocation.Grave:
            if not self.EnemyMonsterAcceptsJailGateBanish(self.Enemy.BattlingMonster):
                return False
            self.activatedCardIdList.append(CardId.JailGodGate + 1)
            return True
        if not self.DefaultCheckWhetherBotCanSearch():
            return False
        if self.JailGatePredictedMillWouldBeBanished():
            return False
        if Bot.HasInHand(CardId.InnocentArt) and not self.artSearched and Bot.HasInDeck(CardId.MediusTheInnocent):
            return False
        if self.CheckShouldNoMoreSpSummon() and self.CheckHasStopBoard():
            return False
        if not self.Util.IsTurn1OrMain2() and any(c is not None and c.IsFaceup() and c.HasType(CardType.Synchro) for c in Bot.GetMonsters()):
            return False
        if self.ShouldSkipJailGodGateForAttack():
            return False
        if not Bot.HasInDeck(CardId.JailChicken) and not Bot.HasInDeck(CardId.MixedHellGod) and not Bot.HasInDeck(CardId.WhitePendulum) \
                and not Bot.HasInExtra(CardId.MixedHellGod) and not Bot.HasInExtra(CardId.WhitePendulum):
            return False
        self.activatedCardIdList.append(CardId.JailGodGate)
        return True

    def InnocentArtActivate(self):
        Bot = self.Bot
        if self.CheckWhetherNegated(True, True, CardType.Spell):
            return False
        if self.Card.Location == CardLocation.Hand:
            if CardId.ElvenotesBlue not in self.activatedCardIdList \
                    and any(c is not None and c.IsCode(CardId.ElvenotesBlue) and c.IsFaceup() for c in Bot.GetMonsters()):
                return False
            return self.DefaultCheckWhetherBotCanSearch()
        if not self.DefaultCheckWhetherBotCanSearch():
            return False
        if not Bot.HasInDeck(CardId.MediusTheInnocent):
            return False
        self.artSearched = True
        self.activatedCardIdList.append(CardId.InnocentArt)
        return True

    def MediusSummon(self):
        if not self.CheckWhetherCanSummon():
            return False
        if CardId.MediusTheInnocent in self.activatedCardIdList:
            return False
        if self.CheckShouldNoMoreSpSummon() and self.CheckHasStopBoard():
            return False
        chickenInHand = self.Bot.HasInHand(CardId.JailChicken)
        sixOnField = any(c is not None and self.IsElvenotesSixStar(c) and c.IsFaceup() for c in self.Bot.GetMonsters())
        if chickenInHand and sixOnField:
            return False
        self.summonCount -= 1
        return True

    def MediusActivate(self):
        Bot = self.Bot
        if self.CheckWhetherNegated(True):
            return False
        if self.Card.Location == CardLocation.Grave:
            if self.CheckShouldNoMoreSpSummon(CardLocation.Grave):
                return False
            if not self.ShouldRerouteChickenSixUnderBanish() and (self.CanChickenLevelForWhite10() or self.ShouldPreferWhite10Synchro()):
                return False
            effect1CanFire = self.MediusEffect1CanFireAfterGySs()
            librarianLine = self.CanMediusGySsForLibrarianAfterEffect1Used()
            if not effect1CanFire and not librarianLine:
                return False
            self.activatedCardIdList.append(CardId.MediusTheInnocent + 1)
            return True
        if CardId.MediusTheInnocent in self.activatedCardIdList:
            return False
        if not self.DefaultCheckWhetherBotCanSearch():
            if self.CheckShouldNoMoreSpSummon(CardLocation.Deck) or not Bot.HasInDeck(CardId.JailChicken) \
                    or len(Bot.GetMonstersInMainZone()) >= 5:
                return False
        self.activatedCardIdList.append(CardId.MediusTheInnocent)
        return True

    def MixedHellGodActivate(self):
        Bot, Card = self.Bot, self.Card
        if self.CheckWhetherNegated(True):
            return False
        if Card.Location == CardLocation.Hand:
            if CardId.MixedHellGod in self.activatedCardIdList:
                return False
            if Bot.HasInSpellZone(CardId.MixedHellGod):
                return False
            canSsPlace = self.CanMixedHellGodPendulumSs()
            canBuffPlace = self.CanMixedHellGodPendulumAtkBuff()
            if not canSsPlace and not canBuffPlace:
                return False
            return self.NeedPendulumScale()
        if self.IsPendulumZoneCard(Card):
            canSs = self.CanMixedHellGodPendulumSs()
            canBuff = self.CanMixedHellGodPendulumAtkBuff()
            if not canSs and not canBuff:
                return False
            if canSs and self.CountFreeMainMonsterZones() < 1 and self.CanSynchroToFreeMainZone():
                return False
            self.activatedCardIdList.append(CardId.MixedHellGod)
            return True
        if Card.Location == CardLocation.Extra:
            if not self.DefaultCheckWhetherBotCanSearch():
                return False
            return True
        return Card.Location == CardLocation.Grave

    def WhitePendulumActivate(self):
        if self.CheckWhetherNegated(True):
            return False
        if self.Card.Location == CardLocation.Hand:
            if self.Duel.Player != 0:
                return False
            if self.Bot.HasInSpellZone(CardId.WhitePendulum) and len(self.Bot.Hand) <= 7:
                return False
            return self.NeedPendulumScale()
        return False

    def WhitePendulumDrawActivate(self):
        if self.CheckWhetherNegated(True):
            return False
        if not self.IsPendulumZoneCard(self.Card):
            return False
        return self.DefaultCheckWhetherBotCanDraw()

    def WhitePendulumRecycleActivate(self):
        if self.CheckWhetherNegated(True):
            return False
        if self.Card.Location != CardLocation.Extra or not self.Card.IsFaceup():
            return False
        return True

    def JailChickenGySearchActivate(self):
        if self.Card.Location != CardLocation.Grave:
            return False
        return self.JailChickenActivate()

    def JailChickenActivate(self):
        Bot, Duel, Card, act = self.Bot, self.Duel, self.Card, self.activatedCardIdList
        if self.CheckWhetherNegated(True):
            return False
        if Card.Location == CardLocation.Grave:
            if not self.DefaultCheckWhetherBotCanSearch():
                return False
            act.append(CardId.JailChicken)
            return True
        if Card.Location == CardLocation.MonsterZone:
            if CardId.JailChicken + 1 in act:
                return False
            if self.ShouldChickenPlus3DodgeNegate():
                self.chickenDodgeSynchroThisChain = True
                self.chickenDodgeSynchroCardId = self.GetChickenDodgeSynchroId()
                act.append(CardId.JailChicken + 1)
                return True
            if self.ShouldWaitOwnEnemyTurnDisruption(True, False):
                return False
            if self.IsOpeningComboTurn() and CardId.White7 not in act and not Bot.HasInMonstersZone(CardId.White7) \
                    and not Bot.HasInGraveyard(CardId.White7) and _CardId.LockBird not in self.enemyResolvedEffectIdList:
                fuwalosPlus3 = self.IsFuwalosOnlyOpeningCompromise() and (self.CanChickenPlus3Baronne() or self.CanChickenPlus3Accel())
                missingPlacePlus3 = self.ShouldOpeningWhite10ForMissingPlace()
                if not fuwalosPlus3 and not missingPlacePlus3 \
                        and (not self.ShouldRerouteChickenSixUnderBanish() or not self.CanChickenPlus3Baronne()):
                    return False
            center = self.GetCenterMonster()
            if center is None or center.Level < 1:
                return False
            if self.CanSynchroEightWithWhite7():
                return False
            if self.CenterElvenotesStillNeedsIgnition() and not self.EnemyHasFloodgateMonster():
                return False
            plus3TenExtra = Bot.HasInExtra(CardId.BaronneDeFleur) \
                if (self.ShouldRerouteChickenSixUnderBanish() or self.IsFuwalosOnlyOpeningCompromise()) \
                else Bot.HasInExtra(CardId.White10)
            if self.IsFuwalosOnlyOpeningCompromise() and self.CanChickenPlus3Accel():
                act.append(CardId.JailChicken + 1)
                return True
            if center.Level + 3 + Card.Level == 10 and plus3TenExtra:
                if Duel.Player == 1 and CardId.White10 in act:
                    return False
                if self.ShouldOpeningWhite10ForMissingPlace():
                    self.white10MissingPlaceLineThisChain = True
                act.append(CardId.JailChicken + 1)
                return True
            if center == Card and plus3TenExtra \
                    and any(c is not None and c != Card and self.IsElvenotesSixStar(c) and c.IsFaceup() for c in Bot.GetMonsters()):
                if Duel.Player == 1 and CardId.White10 in act:
                    return False
                act.append(CardId.JailChicken + 1)
                return True
        return False

    def JailChickenSummonForWhite10Dodge(self):
        Bot, Duel = self.Bot, self.Duel
        if not self.CheckWhetherCanSummon():
            return False
        if any(c is not None and c.IsCode(CardId.JailChicken) and c.IsFaceup() for c in Bot.GetMonsters()):
            return False
        if CardId.JailChicken + 1 in self.activatedCardIdList:
            return False
        if not self.White10EffectStillAvailable():
            return False
        if self.ElvenotesSynchroSecondWouldBeNegatedOnSummon(CardId.White10):
            return False
        if Duel.MainPhase is None or Duel.MainPhase.SpecialSummonableCards is None:
            return False
        canSsRby = any(c is not None and c.IsCode(CardId.ElvenotesRed, CardId.ElvenotesBlue, CardId.ElvenotesYellow)
                       for c in Duel.MainPhase.SpecialSummonableCards)
        if not canSsRby:
            return False
        self.nsChickenOffCenterForWhite10 = True
        self.summonCount -= 1
        return True

    def JailChickenSummon(self):
        Bot = self.Bot
        if not self.CheckWhetherCanSummon():
            return False
        if self.CheckShouldNoMoreSpSummon() and self.CheckHasStopBoard() and not self.HasChickenAndLevel6OnField():
            if any(c is not None and self.IsElvenotesSixStar(c) for c in Bot.GetMonsters()):
                self.summonCount -= 1
                return True
            return False
        if any(c is not None and (self.IsElvenotesSixStar(c) or c.Level == 4) for c in Bot.GetMonsters()):
            self.summonCount -= 1
            return True
        return False

    def EffectVeilerSummon(self):
        if not self.ShouldNormalSummonVeilerForWhite7():
            return False
        self.summonCount -= 1
        return True

    def GreatRighteousThiefSummon(self):
        Bot, Enemy = self.Bot, self.Enemy
        if not self.CheckWhetherCanSummon():
            return False
        if self.Duel.Turn == 1:
            if Bot.GetMonsterCount() > 0:
                return False
            if Bot.HasInHand(CardId.JailChicken) and self.HandHasSixStarWaitingToSs():
                return False
            mediusGyLine = self.CanMediusGySsAfterThiefTribute()
            if Bot.HasInHand(CardId.MediusTheInnocent) and CardId.MediusTheInnocent + 1 not in self.activatedCardIdList \
                    and not mediusGyLine:
                return False
            fodder = sum(1 for c in Bot.Hand if c is not None
                         and c.IsCode(_CardId.MulcharmyFuwalos, _CardId.MulcharmyPurulia, _CardId.MulcharmyNyalus, CardId.MediusTheInnocent)
                         and not c.IsCode(CardId.GreatRighteousThief))
            fodder += Enemy.GetMonsterCount()
            if not mediusGyLine and fodder < 2:
                return False
            self.summonCount -= 1
            return True
        if Bot.GetMonsterCount() == 0 and Enemy.GetMonsterCount() > 0:
            self.summonCount -= 1
            return True
        return False

    def White7Activate(self):
        Bot, Duel, act = self.Bot, self.Duel, self.activatedCardIdList
        if self.CheckWhetherNegated(True):
            return False
        if self.ShouldWaitOwnChainToResolve():
            return False
        if self.ShouldWaitRedFieldBeforeWhite7():
            return False
        if Duel.Phase != DuelPhase.Main1 and Duel.Phase != DuelPhase.Main2:
            return False
        if self.CheckShouldNoMoreSpSummon(CardLocation.Grave) and self.CheckShouldNoMoreSpSummon(CardLocation.Hand):
            return False
        if Duel.Player == 0:
            hasChicken = Bot.HasInGraveyard(CardId.JailChicken) or Bot.HasInHand(CardId.JailChicken)
            hasOtherElvenotes = any(c is not None and c.HasSetcode(SetcodeElvenotes) and c.Level <= 6 for c in Bot.Hand) \
                or any(c is not None and c.HasSetcode(SetcodeElvenotes) and c.Level <= 6 for c in Bot.Graveyard)
            if not hasChicken and not hasOtherElvenotes:
                return False
            act.append(CardId.White7)
            return True
        centerFilled = self.GetCenterMonster() is not None
        gyWind = Bot.HasInGraveyard(CardId.ElvenotesWind) and self.IsCenterEmpty() and CardId.ElvenotesWind + 1 not in act \
            and (self.WantWindEnemyTurnSsChicken() or self.DeckHasRbySwapTarget())
        gyRby = centerFilled and (self.GyRbyWorthWhite7Pull(CardId.ElvenotesRed) or self.GyRbyWorthWhite7Pull(CardId.ElvenotesBlue)
                                  or self.GyRbyWorthWhite7Pull(CardId.ElvenotesYellow))
        gyChicken = Bot.HasInGraveyard(CardId.JailChicken) and CardId.JailChicken + 1 not in act \
            and (self.HasEightSynchroInExtra() or self.White10EffectStillAvailable())
        handRby = centerFilled and any(Bot.HasInHand(i) and self.CanRbySwapNow(i, True) and not self.HasFaceupRbyReadyToSwap(i)
                                       for i in (CardId.ElvenotesRed, CardId.ElvenotesBlue, CardId.ElvenotesYellow))
        mainEndBody = (self.CurrentTiming & HintTimingMainEnd) != 0 \
            and any(c is not None and c.HasSetcode(SetcodeElvenotes) and c.Level <= 6
                    and not self.CheckShouldNoMoreSpSummon(CardLocation.Grave) for c in Bot.Graveyard)
        if not gyWind and not gyRby and not gyChicken and not handRby and not mainEndBody:
            return False
        act.append(CardId.White7)
        return True

    def White10Activate(self):
        Bot, Duel = self.Bot, self.Duel
        if self.CheckWhetherNegated(True):
            return False
        if self.ShouldWaitOwnChainToResolve(True):
            return False
        if Duel.Player == 0 and Bot.HasInHand(CardId.WhitePendulum) and self.NeedPendulumScale() \
                and not Bot.HasInSpellZone(CardId.WhitePendulum) and CardId.WhitePendulum not in self.activatedCardIdList \
                and self.DefaultCheckWhetherBotCanDraw():
            return False
        if self.Card.Sequence != 2:
            return False
        if Duel.Phase != DuelPhase.Main1 and Duel.Phase != DuelPhase.Main2:
            return False
        if self.CheckShouldNoMoreSpSummon(CardLocation.Deck) and Duel.Player == 0 and self.CheckHasStopBoard():
            return False
        self.activatedCardIdList.append(CardId.White10)
        return True

    # --- synchro ----------------------------------------------------------------------------------------------
    def White7SpSummon(self):
        if self.ShouldSkipExtraSynchroForFuwalosCompromise():
            return False
        if self.CheckShouldNoMoreSpSummon(CardLocation.Extra):
            return False
        if self.ShouldDeferSynchroForHelldiveBomber():
            return False
        if self.ShouldRerouteChickenSixUnderBanish():
            return False
        if self.ShouldOpeningWhite10ForMissingPlace():
            return False
        if CardId.White7 in self.activatedCardIdList:
            return False
        return self.SelectSynchroMaterials(7, False)

    def SuperLibrarianSpSummon(self):
        if self.ShouldSkipExtraSynchroForFuwalosCompromise():
            return False
        if self.CheckShouldNoMoreSpSummon(CardLocation.Extra):
            return False
        if self.ShouldDeferSynchroForHelldiveBomber():
            return False
        if self.ShouldPreferWhite10Synchro():
            return False
        if self.CanSynchroEightWithWhite7() and not self.CanLibrarianThenEightSynchro():
            return False
        if not self.CanLibrarianThenEightSynchro() and self.CountFaceupChickenOnField() < 2:
            sixForSeven = any(c is not None and c.IsFaceup() and not c.IsTuner() and c.Level == 6
                              and not c.IsCode(CardId.CrystalWing, CardId.FormulaAthleteLightning, CardId.BaronneDeFleur,
                                               CardId.SuperLibrarian)
                              for c in self.Bot.GetMonsters())
            if sixForSeven:
                return False
        return self.SelectSynchroMaterials(5, False)

    def AccelStardustSpSummon(self):
        Bot = self.Bot
        if self.ShouldFuwalosCompromiseIdleAccel():
            return self.SelectSynchroMaterials(8, False)
        if self.ShouldSkipExtraSynchroForFuwalosCompromise():
            return False
        if self.CheckShouldNoMoreSpSummon(CardLocation.Extra):
            return False
        if self.ShouldDeferSynchroForHelldiveBomber():
            return False
        if self.ShouldRerouteChickenSixUnderBanish():
            return False
        librarian = Bot.HasInMonstersZone(CardId.SuperLibrarian, True, False, True)
        wantNegate = self.Duel.Player == 0 and not Bot.HasInMonstersZone(CardId.CrystalWing) and not librarian \
            and Bot.HasInExtra(CardId.CrystalWing)
        if wantNegate and not librarian:
            return False
        if not librarian and Bot.HasInMonstersZone(CardId.CrystalWing):
            return False
        if not librarian and self.ShouldPreferWhite10Synchro():
            return False
        return self.SelectSynchroMaterials(8, False)

    def CrystalWingSpSummon(self):
        Bot = self.Bot
        if self.ShouldSkipExtraSynchroForFuwalosCompromise():
            return False
        if self.CheckShouldNoMoreSpSummon(CardLocation.Extra):
            return False
        if self.ShouldDeferSynchroForHelldiveBomber():
            return False
        if self.ShouldRerouteChickenSixUnderBanish():
            return False
        if Bot.HasInMonstersZone(CardId.SuperLibrarian, True, False, True) and Bot.HasInExtra(CardId.AccelSynchroStardust):
            return False
        if self.ShouldPreferWhite10Synchro():
            return False
        return self.SelectSynchroMaterials(8, False)

    def White10SpSummon(self):
        if self.ShouldSkipExtraSynchroForFuwalosCompromise():
            return False
        if self.CheckShouldNoMoreSpSummon(CardLocation.Extra):
            return False
        if self.ShouldDeferSynchroForHelldiveBomber():
            return False
        if not self.White10EffectStillAvailable():
            return False
        if self.ShouldRerouteChickenSixUnderBanish():
            return False
        return self.SelectSynchroMaterials(10, False)

    def BaronneSpSummon(self):
        if self.ShouldFuwalosCompromiseIdleBaronne():
            return self.SelectSynchroMaterials(10, False, True)
        if self.ShouldSkipExtraSynchroForFuwalosCompromise():
            return False
        if self.CheckShouldNoMoreSpSummon(CardLocation.Extra):
            return False
        if self.ShouldDeferSynchroForHelldiveBomber():
            return False
        if self.ShouldKeepSixStarForChickenPlus3():
            return False
        if not self.ShouldRerouteChickenSixUnderBanish() and self.CanMakeWhite10Synchro() \
                and any(c is not None and c.HasSetcode(SetcodeElvenotes) for c in self.Bot.GetMonsters()):
            return False
        if self.ShouldSummonChaosAngel():
            return False
        return self.SelectSynchroMaterials(10, False, True)

    def FormulaAthleteSpSummon(self):
        if self.ShouldSkipExtraSynchroForFuwalosCompromise():
            return False
        if self.CheckShouldNoMoreSpSummon(CardLocation.Extra):
            return False
        if self.ShouldDeferSynchroForHelldiveBomber():
            return False
        if self.ShouldKeepSixStarForChickenPlus3():
            return False
        if self.ShouldOpeningWhite10ForMissingPlace():
            return False
        if self.ShouldRerouteChickenSixUnderBanish() and self.Duel.Turn >= 2 and self.Bot.HasInExtra(CardId.BlackRoseDragon) \
                and self.ShouldBlackRoseWipe(True):
            return False
        if not self.ShouldRerouteChickenSixUnderBanish() and (self.CanChickenLevelForWhite10() or self.ShouldPreferWhite10Synchro()):
            return False
        if self.CanSynchroEightWithWhite7() or self.CanSynchroEightWithTwoChickens():
            return False
        return self.SelectSynchroMaterials(7, False)

    def PSYOmegaSpSummon(self):
        if self.ShouldSkipExtraSynchroForFuwalosCompromise():
            return False
        if self.CheckShouldNoMoreSpSummon(CardLocation.Extra):
            return False
        if self.ShouldDeferSynchroForHelldiveBomber():
            return False
        if self.CanLibrarianThenEightSynchro():
            return False
        return self.SelectSynchroMaterials(8, False)

    def ChaosAngelSpSummon(self):
        if self.ShouldSkipExtraSynchroForFuwalosCompromise():
            return False
        if self.CheckShouldNoMoreSpSummon(CardLocation.Extra):
            return False
        if not self.ShouldSummonChaosAngel():
            return False
        allowFa = self.EnemyHasChaosAngelBanishTarget()
        mats = self.FindChaosAngelMaterials(allowFa)
        if mats is None or len(mats) == 0:
            return False
        self.AI.SelectMaterials(mats)
        return True

    def ShouldBlackRoseWipe(self, forSummon=False):
        Bot, Enemy = self.Bot, self.Enemy
        if self.Duel.Turn == 1:
            return False
        problems = self.GetProblematicEnemyCardList(False, False, 0)
        enemyFloodgate = enemyInvincible = enemyDangerous = False
        for card in problems:
            if card is None or card.IsDisabled():
                continue
            if card.IsCode(CardId.RedField):
                continue
            if card.IsFloodgate():
                if not card.IsMonster() or not any(m is not None and m.IsFaceup() and m.Attack > card.Attack for m in Bot.GetMonsters()):
                    enemyFloodgate = True
            if card.IsMonsterInvincible():
                enemyInvincible = True
            if card.IsMonsterDangerous():
                enemyDangerous = True
        ownTerminal = False
        for monster in Bot.GetMonsters():
            if monster is None or not monster.IsFaceup() or monster.IsCode(CardId.BlackRoseDragon):
                continue
            if monster.IsCode(CardId.CrystalWing, CardId.AccelSynchroStardust, CardId.PSYFramelordOmega,
                              CardId.FormulaAthleteLightning, CardId.BaronneDeFleur, CardId.SuperLibrarian):
                ownTerminal = True
                break
        if ownTerminal and not enemyFloodgate and not enemyInvincible:
            return False
        hardThreat = enemyFloodgate or enemyInvincible or enemyDangerous
        if hardThreat:
            return True
        if len(problems) == 0 and Enemy.GetFieldCount() < 2:
            return False
        if not forSummon:
            return True
        mats = self.FindSynchroMaterials(7, False)
        own = Bot.GetFieldCount()
        enemy = Enemy.GetFieldCount()
        leftover = own - len(mats) if mats is not None else own
        if mats is None or leftover >= 2 or own > enemy:
            return False
        return True

    def BlackRoseSpSummon(self):
        Duel = self.Duel
        if Duel.Turn == 1:
            return False
        if self.ShouldSkipExtraSynchroForFuwalosCompromise():
            return False
        if not self.ShouldBlackRoseWipe(True):
            return False
        if self.CheckShouldNoMoreSpSummon(CardLocation.Extra) and len(self.GetProblematicEnemyCardList()) == 0:
            return False
        if Duel.Player == 0 and Duel.Turn > 1:
            if self.SelectSynchroMaterials(7, False):
                return True
        return False

    def AncientFishSpSummon(self):
        if self.ShouldSkipExtraSynchroForFuwalosCompromise():
            return False
        if self.CheckShouldNoMoreSpSummon(CardLocation.Extra):
            return False
        if self.ShouldDeferSynchroForHelldiveBomber():
            return False
        if self.CheckThousandSpearGoingFirstLine() or self.CheckThousandSpearGoingSecondLine():
            return False
        return self.SelectSynchroMaterials(9, True)

    def ThousandSpearSpSummon(self):
        if self.ShouldSkipExtraSynchroForFuwalosCompromise():
            return False
        if self.CheckShouldNoMoreSpSummon(CardLocation.Extra):
            return False
        if self.ShouldDeferSynchroForHelldiveBomber():
            return False
        if not (self.CheckThousandSpearGoingFirstLine() or self.CheckThousandSpearGoingSecondLine()):
            return False
        return self.SelectSynchroMaterials(9, True)

    def AssaultBlackwingSpSummon(self):
        Enemy = self.Enemy
        if self.Duel.Turn == 1:
            return False
        if self.ShouldSkipExtraSynchroForFuwalosCompromise():
            return False
        if self.ShouldDeferSynchroForHelldiveBomber():
            return False
        if self.CheckShouldNoMoreSpSummon(CardLocation.Extra) and Enemy.LifePoints > 4000:
            return False
        atk = 0
        for card in self.Bot.GetMonsters():
            if card is not None and card.HasType(CardType.Synchro):
                atk += card.Attack
        if atk + 3000 < Enemy.LifePoints and Enemy.GetMonsterCount() == 0:
            return False
        return self.SelectSynchroMaterials(9, True)

    def HelldiveBomberSpSummon(self):
        if self.Duel.Turn == 1:
            return False
        if self.ShouldSkipExtraSynchroForFuwalosCompromise():
            return False
        if self.CheckShouldNoMoreSpSummon(CardLocation.Extra):
            return False
        if not self.HelldiveBomberDestroyEffectCanApply():
            return False
        if any(c is not None and c.IsFaceup() and c.IsCode(CardId.HelldiveBomber) and not c.IsDisabled() for c in self.Bot.GetMonsters()):
            return False
        mats = self.FindSynchroMaterials(7, True)
        if mats is None:
            return False
        dmg = self.EstimateBomberDamage(mats, True)
        if dmg <= self.Enemy.LifePoints:
            return False
        self.AI.SelectMaterials(mats)
        return True

    def ThousandSpearActivate(self):
        Enemy, Util = self.Enemy, self.Util
        if self.CheckWhetherNegated(True):
            return False
        hasDanger = len(self.GetDangerousCardinEnemyGrave(False)) > 0 or len(self.GetProblematicEnemyCardList(False, False, 0)) > 0
        if self.ActivateDescription == Util.GetStringId(CardId.ThousandSpearDragon, 0) \
                or (self.ActivateDescription == -1 and self.Duel.LastChainPlayer != 1):
            if not self.EnemyHasThousandSpearBanishWorth():
                return False
            removable = Enemy.GetMonsterCount() + Enemy.GetSpellCount() + len(Enemy.Graveyard)
            if removable < 2:
                return False
            self.activatedCardIdList.append(CardId.ThousandSpearDragon)
            return True
        if self.ActivateDescription == Util.GetStringId(CardId.ThousandSpearDragon, 1):
            if not hasDanger:
                return False
            if sum(1 for c in self.Bot.Hand if c is not None
                   and not c.IsCode(_CardId.AshBlossom, _CardId.MaxxC, _CardId.LockBird, _CardId.EffectVeiler)) == 0:
                return False
            self.activatedCardIdList.append(CardId.ThousandSpearDragon + 1)
            return True
        if self.ActivateDescription == Util.GetStringId(CardId.ThousandSpearDragon, 2) or self.Card.Location == CardLocation.Grave:
            self.activatedCardIdList.append(CardId.ThousandSpearDragon + 2)
            return True
        return False

    def HelldiveBomberActivate(self):
        if self.CheckWhetherNegated(True):
            return False
        if self.Duel.Phase != DuelPhase.Main2:
            return False
        if CardId.HelldiveBomber in self.activatedCardIdList:
            return False
        if self.EstimateBomberDamage() <= 0:
            return False
        self.activatedCardIdList.append(CardId.HelldiveBomber)
        return True

    def BlackRoseActivate(self):
        if self.CheckWhetherNegated(True):
            return False
        destroyDesc = self.Util.GetStringId(CardId.BlackRoseDragon, 0)
        if self.ActivateDescription != destroyDesc and self.ActivateDescription != -1:
            return False
        if not self.ShouldBlackRoseWipe():
            return False
        return True

    def AncientFishActivate(self):
        if self.CheckWhetherNegated(True):
            return False
        drawDesc = self.Util.GetStringId(CardId.AncientFishDragon, 0)
        destroyDesc = self.Util.GetStringId(CardId.AncientFishDragon, 1)
        if self.ActivateDescription == drawDesc or (self.ActivateDescription == -1 and self.ActivateDescription != destroyDesc
                                                    and CardId.AncientFishDragon not in self.activatedCardIdList):
            self.activatedCardIdList.append(CardId.AncientFishDragon)
            return True
        destroyTargets = self.GetAncientFishDestroyTargets()
        if len(destroyTargets) == 0:
            return False
        return True

    def SuperLibrarianActivate(self):
        return True

    def SpellSetCheck(self):
        Bot, Duel, Card = self.Bot, self.Duel, self.Card
        if Card.IsCode(CardId.GreenField, CardId.InnocentArt, CardId.JailGodGate):
            return False
        if Card.IsCode(CardId.RedField):
            if Bot.HasInSpellZone(CardId.RedField):
                return False
            if CardId.ElvenotesYellow not in self.activatedCardIdList:
                yellowOnField = any(c is not None and c.IsCode(CardId.ElvenotesYellow) and c.IsFaceup() for c in Bot.GetMonsters())
                if yellowOnField:
                    return False
                if Bot.HasInHand(CardId.ElvenotesYellow) and self.IsCenterEmpty():
                    return False
            if Duel.Phase == DuelPhase.Main1 and Bot.HasAttackingMonster() and Duel.Turn > 1:
                return False
            return True
        if Duel.Phase == DuelPhase.Main1 and Bot.HasAttackingMonster() and Duel.Turn > 1:
            return False
        if Card.IsTrap() or Card.HasType(CardType.QuickPlay):
            return True
        return False
