"""Albaz executor, ported from IceYGO/windbot Game/AI/Decks/AlbazExecutor.cs (MIT, see THIRD_PARTY_NOTICES.md).

Approximations: the env limits in docs/windbot_porting.md (IsDisabled always False, BattlingMonster None and
UnderAttack False, EquipCards empty, IsSpecialSummoned False so CheckAlbazFusion's Sprind branch never fires).
CurrentTiming is always -1 (GameAI.OnSelectChain gets no chain timing), so the hintTimingMainEnd / hintBattleStart
branches never fire and the `CurrentTiming == -1` checks always pass. ClientCard lists kept across decisions
(sendToGYThisTurn, enemyPlaceThisTurn, the fusion material lists, currentNegate/DestroyCardList, fusionTarget) hold
snapshots; OnMove follows a moved card with FindMovedCard (id + previous controller / location) where WindBot keeps
one object. C# `out` parameters are returned as tuples (CheckAlbazFusion(exceptCost, out=True) is the out overload);
LINQ Intersect / Except / OrderBy are order-preserving helpers; Duel.LastChainTargets.Clear() in OnChaining clears
the replayed chain mirror. The C# quirks are kept as written (the material-adding else branches of the fusion
checks write to the selectedFusionMaterial field; Util.GetWorstBotMonster() is dereferenced unguarded where the C#
does). DefaultExecutor's SpellSet DefaultSetForDiabellze row, missing from windbot_default.py, is added first so the
Albaz override has its row. Logging dropped.

Module-level helpers (WindBot members the shim lacks): DefaultCheckWhetherBotWillBeBanished (both DefaultExecutor
overloads: ClientCard or (CardType, CardLocation)), DefaultIsDimensionalFissureTarget, DefaultSetForDiabellze (the
base), ShuffleListInPlace (AIUtil), FindMovedCard (the ClientCard identity stand-in)."""
from windbot import *
from windbot_default import DefaultExecutor, _CardId, _Setcode
from windbot_gameai import BattlePhaseAction


class CardId:
    TheBystialLubellion = 32731036
    AlbionTheShroudedDragon = 25451383
    BystialSaronir = 60242223
    AluberTheJesterOfDespia = 62962630
    FallenOfAlbaz = 68468459
    SpringansKitt = 45484331
    GuidingQuemTheVirtuous = 45883110
    BlazingCartesiaTheVirtuous = 95515789
    TriBrigadeMercourier = 19096726
    DespianTragedy = 36577931

    NadirServant = 1984618
    FusionDeployment = 6498706
    BrandedInWhite = 34995106
    BrandedFusion = 44362883
    GoldSarcophagus = 75500286
    FoolishBurial = 81439173
    BrandedInHighSpirits = 29948294
    BrandedOpening = 36637374
    BrandedInRed = 82738008
    BrandedLost = 18973184

    BrightestBlazingBrandedKing = 19271881
    BrandedBeast = 32756828
    BrandedRetribution = 17751597

    GuardianChimera = 11321089
    AlbionTheSanctifireDragon = 38811586
    MirrorjadeTheIcebladeDragon = 44146295
    BorreloadFuriousDragon = 92892239
    LubellionTheSearingDragon = 70534340
    AlbaLenatusTheAbyssDragon = 3410461
    GranguignolTheDuskDragon = 24915933
    DespianQuaeritis = 72272462
    SprindTheIrondashDragon = 1906812
    TitanikladTheAshDragon = 41373230
    RindbrummTheStrikingDragon = 51409648
    AlbionTheBrandedDragon = 87746184
    DespianLuluwalilith = 53971455

    NaturalExterio = 99916754
    NaturalBeast = 33198837
    ImperialOrder = 61740673
    SwordsmanLV7 = 37267041
    RoyalDecree = 51452091
    Number41BagooskatheTerriblyTiredTapir = 90590303
    InspectorBoarder = 15397015
    SkillDrain = 82732705

    KashtiraAriseHeart = 48626373
    AccesscodeTalker = 86066372
    GhostMournerMoonlitChill = 52038441
    NibiruThePrimalBeing = 27204311


SetcodeTimeLord = 0x4a
SetcodePhantom = 0xdb
SetcodeOrcust = 0x11b
SetcodeBranded = 0x15d
SetcodeDespain = 0x164
SetcodeBystial = 0x188
SetcodeHorus = 0x19d
hintTimingMainEnd = 0x4
hintBattleStart = 0x8


def _flat(ids):
    return [i for x in ids for i in (x if isinstance(x, (list, tuple, set)) else [x])]


def _OrderByDesc(cards, key):
    """LINQ OrderByDescending (stable)."""
    return sorted(cards, key=lambda c: -key(c))


def _Intersect(first, second):
    """LINQ Intersect: distinct cards of first that are in second, in first's order."""
    result = []
    for c in first:
        if c in second and c not in result:
            result.append(c)
    return result


def _Except(first, second):
    """LINQ Except: distinct cards of first that are not in second, in first's order."""
    result = []
    for c in first:
        if c not in second and c not in result:
            result.append(c)
    return result


def _OrderBy(cards, key):
    """LINQ OrderBy (stable)."""
    return sorted(cards, key=key)


def _IndexOf(items, value):
    """List.IndexOf: -1 when absent."""
    return items.index(value) if value in items else -1


# ClientCard lists the executor keeps across decisions (OnMove follows their cards, see FindMovedCard)
_TRACKED_CARD_LISTS = ("cartesiaMaterialList", "brandedInRedMaterialList", "currentNegateCardList",
                       "currentDestroyCardList", "sendToGYThisTurn", "selectedFusionMaterial", "enemyPlaceThisTurn")


class AlbazExecutor(DefaultExecutor):
    DECK_EXECUTOR = True

    def __init__(self):
        super().__init__()
        A, S, SS, MS = ExecutorType.Activate, ExecutorType.Summon, ExecutorType.SpSummon, ExecutorType.MonsterSet
        # DefaultExecutor's last base row (windbot_default.py leaves it out); Albaz overrides it

        self.AddExecutor(A, _CardId.MaxxC, self.MaxxCActivate)

        self.AddExecutor(S, self.AdvanceSummon)
        self.AddExecutor(SS, CardId.AlbaLenatusTheAbyssDragon, self.AlbaLenatusTheAbyssDragonSpSummon)
        self.AddExecutor(MS, CardId.FallenOfAlbaz, self.FallenOfAlbazSet)
        self.AddExecutor(A, CardId.BlazingCartesiaTheVirtuous, self.BlazingCartesiaTheVirtuousActivateInGrave)

        # quick effect
        self.AddExecutor(A, CardId.BrandedRetribution, self.BrandedRetributionActivate)
        self.AddExecutor(A, _CardId.CalledByTheGrave, self.CalledbytheGraveActivate)
        self.AddExecutor(A, _CardId.CrossoutDesignator, self.CrossoutDesignatorActivate)
        self.AddExecutor(A, _CardId.InfiniteImpermanence, self.InfiniteImpermanenceActivate)
        self.AddExecutor(A, _CardId.AshBlossom, self.AshBlossomActivate)
        self.AddExecutor(A, CardId.BrandedBeast, self.BrandedBeastActivate)
        self.AddExecutor(A, CardId.BrightestBlazingBrandedKing, self.BrightestBlazingBrandedKingActivate)
        self.AddExecutor(A, CardId.BrandedOpening, self.BrandedOpeningActivate)
        self.AddExecutor(A, CardId.BrandedInHighSpirits, self.BrandedInHighSpiritsActivate)
        self.AddExecutor(A, CardId.RindbrummTheStrikingDragon, self.RindbrummTheStrikingDragonActivate)

        # remove
        self.AddExecutor(A, CardId.GuardianChimera, self.GuardianChimeraActivate)
        self.AddExecutor(A, CardId.BorreloadFuriousDragon, self.BorreloadFuriousDragonActivate)
        self.AddExecutor(A, CardId.TriBrigadeMercourier, self.TriBrigadeMercourierActivate)
        self.AddExecutor(A, CardId.DespianQuaeritis, self.DespianQuaeritisActivate)
        self.AddExecutor(A, CardId.MirrorjadeTheIcebladeDragon, self.MirrorjadeTheIcebladeDragonActivate)

        # search
        self.AddExecutor(A, CardId.TheBystialLubellion, self.TheBystialLubellionActivate)
        self.AddExecutor(SS, CardId.TheBystialLubellion, self.TheBystialLubellionSpSummon)
        self.AddExecutor(A, CardId.FoolishBurial, self.FoolishBurialActivate)
        self.AddExecutor(A, CardId.GoldSarcophagus, self.GoldSarcophagusActivate)
        self.AddExecutor(A, CardId.AluberTheJesterOfDespia, self.AluberTheJesterOfDespiaActivate)

        self.AddExecutor(A, CardId.AlbionTheSanctifireDragon, self.AlbionTheSanctifireDragonActivate)

        # blazing
        self.AddExecutor(A, CardId.FusionDeployment, self.FusionDeploymentActivate)

        self.AddExecutor(A, CardId.AlbionTheShroudedDragon, self.AlbionTheShroudedDragonActivate)
        self.AddExecutor(A, CardId.BystialSaronir, self.BystialSaronirActivate)

        # summon for search
        self.AddExecutor(S, CardId.AluberTheJesterOfDespia, self.AluberTheJesterOfDespiaSummon)
        self.AddExecutor(S, CardId.GuidingQuemTheVirtuous, self.GuidingQuemTheVirtuousSummonForSearch)
        self.AddExecutor(A, CardId.SpringansKitt, self.SpringansKittActivate)
        self.AddExecutor(S, CardId.SpringansKitt, self.SpringansKittSummon)

        # fusion & lost
        self.AddExecutor(A, CardId.BrandedLost, self.BrandedLostCardActivate)
        self.AddExecutor(A, CardId.GranguignolTheDuskDragon, self.GranguignolTheDuskDragonActivate)
        self.AddExecutor(A, CardId.AlbaLenatusTheAbyssDragon, self.AlbaLenatusTheAbyssDragonActivate)
        self.AddExecutor(A, CardId.SprindTheIrondashDragon, self.SprindTheIrondashDragonActivate)
        self.AddExecutor(A, CardId.TitanikladTheAshDragon, self.TitanikladTheAshDragonActivate)
        self.AddExecutor(A, CardId.AlbionTheBrandedDragon, self.AlbionTheBrandedDragonActivate)
        self.AddExecutor(A, CardId.LubellionTheSearingDragon, self.LubellionTheSearingDragonActivate)
        self.AddExecutor(S, CardId.BlazingCartesiaTheVirtuous, self.BlazingCartesiaTheVirtuousSummon)
        self.AddExecutor(A, CardId.FallenOfAlbaz, self.FallenOfAlbazActivate)
        self.AddExecutor(A, CardId.BrandedFusion, self.BrandedFusionActivate)
        self.AddExecutor(A, CardId.BlazingCartesiaTheVirtuous, self.BlazingCartesiaTheVirtuousActivate)
        self.AddExecutor(A, CardId.BrandedInWhite, self.BrandedInWhiteActivate)
        self.AddExecutor(A, CardId.BrandedInRed, self.BrandedInRedActivate)
        self.AddExecutor(A, CardId.BrandedLost, self.BrandedLostActivate)

        # albaz summon
        self.AddExecutor(S, CardId.FallenOfAlbaz, self.FallenOfAlbazSummon)
        self.AddExecutor(S, CardId.GuidingQuemTheVirtuous, self.GuidingQuemTheVirtuousSummon)

        # delay
        self.AddExecutor(A, CardId.DespianTragedy, self.DespianTragedyActivate)
        self.AddExecutor(A, CardId.TriBrigadeMercourier, self.TriBrigadeMercourierActivateForSearch)
        self.AddExecutor(A, CardId.NadirServant, self.NadirServantActivate)

        self.AddExecutor(MS, self.SetForChimera)
        self.AddExecutor(MS, CardId.DespianTragedy, self.DespianTragedySet)
        self.AddExecutor(ExecutorType.Repos, self.DefaultMonsterRepos)
        self.AddExecutor(ExecutorType.SpellSet, self.SpellSetCheck)
        self.AddExecutor(A, CardId.GuidingQuemTheVirtuous, self.GuidingQuemTheVirtuousActivate)
        self.AddExecutor(A, CardId.DespianLuluwalilith, self.DespianLuluwalilithActivate)

        self.AddExecutor(A, self.FloogateActivate)

        self.notToNegateIdList = [58699500, 20343502, CardId.AlbionTheShroudedDragon, 19403423]
        self.cannotBeFusionMaterialIdList = [
            CardId.AlbaLenatusTheAbyssDragon, CardId.AlbionTheSanctifireDragon, 79229522, 65029288, 30864377, 33964637,
            87116928, 13735899, 28226490, 80453041, _CardId.EaterOfMillions, 2992467, 16366810, 40217358, 47346782,
            50893987, 71459017, 84433295, 85101097]
        self.albazFusionMonster = [
            CardId.TitanikladTheAshDragon, CardId.SprindTheIrondashDragon, CardId.AlbionTheBrandedDragon,
            CardId.LubellionTheSearingDragon, CardId.AlbaLenatusTheAbyssDragon, CardId.MirrorjadeTheIcebladeDragon,
            CardId.RindbrummTheStrikingDragon, CardId.AlbionTheSanctifireDragon]
        self.dangerousDragonIdList = [27548199, 92892239, 98630720, 9753964, 99585850, 24361622, 27572350, 69120785,
                                      96402918, 74294676, 42752141, 18511599, 35103106, 26268488]
        self.notToDestroySpellTrap = [50005218, 6767771]
        self.targetNegateIdList = [
            _CardId.EffectVeiler, _CardId.InfiniteImpermanence, CardId.GhostMournerMoonlitChill,
            _CardId.BreakthroughSkill, 74003290, 67037924, 9753964, 66192538, 23204029, 73445448, 35103106, 30286474,
            45002991, 5795980, 38511382, 53742162, 30430448]

        self.summoned = False
        self.enemyActivateInfiniteImpermanenceFromHand = False
        self.theBystialLubellionSelecting = False
        self.albionTheShroudedDragonSelecting = False
        self.nadirActivated = False
        self.fusionToGYFlag = False
        self.spSummoningAlbaz = False
        self.cartesiaSummonGoal = 0
        self.sanctifireSelectPositionCount = 0
        self.quemSummonFlag = 0
        self.cartesiaMaterialList = []
        self.brandedInRedMaterialList = []
        self.infiniteImpermanenceList = []
        self.currentNegateCardList = []
        self.currentDestroyCardList = []
        self.sendToGYThisTurn = []
        self.activatedCardIdList = []
        self.fusionTarget = None
        self.selectedFusionMaterial = []
        self.enemyPlaceThisTurn = []

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

    def CheckWhetherNegated(self, disablecheck=True, toFieldCheck=False, type_=0):
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
            if (toFieldCheck and ((type_ & CardType.Link) == 0)) or Card.IsDefense():
                if self.DefaultCheckWhetherNumber41IsActive():
                    return True
            if self.Enemy.HasInSpellZone(CardId.SkillDrain, True, True):
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
        if Enemy.HasInMonstersZone(CardId.NaturalExterio, True) and not isCounter:
            return True
        if target.IsSpell():
            if Enemy.HasInMonstersZone(CardId.NaturalBeast, True):
                return True
            if Enemy.HasInSpellZone(CardId.ImperialOrder, True) or Bot.HasInSpellZone(CardId.ImperialOrder, True):
                return True
            if Enemy.HasInMonstersZone(CardId.SwordsmanLV7, True) or Bot.HasInMonstersZone(CardId.SwordsmanLV7, True):
                return True
        if target.IsTrap() and (Enemy.HasInSpellZone(CardId.RoyalDecree, True) or Bot.HasInSpellZone(CardId.RoyalDecree, True)):
            return True
        if target.Location == CardLocation.SpellZone and (target.IsSpell() or target.IsTrap()):
            selfSeq = -1
            for i in range(5):
                if Bot.SpellZone[i] == self.Card:
                    selfSeq = i
            if selfSeq in self.infiniteImpermanenceList:
                return True
        return False

    def CheckLastChainShouldNegated(self):
        lastcard = self.Util.GetLastChainCard()
        if lastcard is None or lastcard.Controller != 1:
            return False
        if lastcard.IsMonster() and lastcard.HasSetcode(SetcodeTimeLord) and self.Duel.Phase == DuelPhase.Standby:
            return False
        if lastcard.Id in self.notToNegateIdList:
            return False
        if self.DefaultCheckWhetherCardIsNegated(lastcard):
            return False
        if self.Duel.Turn == 1 and lastcard.IsCode(_CardId.MaxxC):
            return False
        return True

    def CheckAtAdvantage(self):
        if self.GetProblematicEnemyMonster() is None and (self.Duel.Player == 0 or self.Bot.GetMonsterCount() > 0):
            return True
        return False

    def CheckShouldNoMoreSpSummon(self, loc=None):
        if loc is None:
            if self.CheckAtAdvantage() and _CardId.MaxxC in self.enemyResolvedEffectIdList \
                    and self.DefaultCheckWhetherEnemyCanDraw() \
                    and (self.Duel.Turn == 1 or self.Duel.Phase >= DuelPhase.Main2):
                return True
            return False
        if self.CheckShouldNoMoreSpSummon():
            return True
        Duel = self.Duel
        if not self.DefaultCheckWhetherEnemyCanDraw() or (Duel.Turn > 1 and Duel.Phase < DuelPhase.Main2):
            return False
        if _CardId.MulcharmyPurulia in self.enemyResolvedEffectIdList and (loc & CardLocation.Hand) != 0:
            return True
        if _CardId.MulcharmyFuwalos in self.enemyResolvedEffectIdList and (loc & (CardLocation.Deck | CardLocation.Extra)) != 0:
            return True
        if _CardId.MulcharmyNyalus in self.enemyResolvedEffectIdList and (loc & (CardLocation.Grave | CardLocation.Removed)) != 0:
            return True
        return False

    def CheckWhetherCanSummon(self):
        return self.Duel.Player == 0 and self.Duel.Phase < DuelPhase.End and not self.summoned

    def CheckWhetherShouldKeepInGrave(self, c):
        if c.IsCode(CardId.GranguignolTheDuskDragon) and c.Location == CardLocation.Grave:
            return True
        if not c.IsCode([CardId.AlbaLenatusTheAbyssDragon, CardId.AlbionTheBrandedDragon, CardId.TitanikladTheAshDragon,
                         CardId.DespianLuluwalilith, CardId.SprindTheIrondashDragon]):
            return False
        return c in self.sendToGYThisTurn and c.Location == CardLocation.Grave

    def GetProblematicEnemyMonster(self, attack=0, canBeTarget=False, ignoreCurrentDestroy=False, selfType=0):
        Enemy = self.Enemy
        cdl = self.currentDestroyCardList
        floodagateCard = next(iter(_OrderByDesc(
            [c for c in Enemy.GetMonsters() if c is not None and c.Data is not None
             and (ignoreCurrentDestroy or c not in cdl) and c.IsFloodgate() and c.IsFaceup()
             and self.CheckCanBeTargeted(c, canBeTarget, selfType) and self.CheckShouldNotIgnore(c)],
            lambda c: c.Attack)), None)
        if floodagateCard is not None:
            return floodagateCard

        dangerCard = next(iter(_OrderByDesc(
            [c for c in Enemy.MonsterZone if c is not None and c.Data is not None
             and (ignoreCurrentDestroy or c not in cdl) and c.IsMonsterDangerous() and c.IsFaceup()
             and self.CheckCanBeTargeted(c, canBeTarget, selfType) and self.CheckShouldNotIgnore(c)],
            lambda c: c.Attack)), None)
        if dangerCard is not None:
            return dangerCard

        invincibleCard = next(iter(_OrderByDesc(
            [c for c in Enemy.MonsterZone if c is not None and c.Data is not None
             and (ignoreCurrentDestroy or c not in cdl) and c.IsMonsterInvincible() and c.IsFaceup()
             and self.CheckCanBeTargeted(c, canBeTarget, selfType) and self.CheckShouldNotIgnore(c)],
            lambda c: c.Attack)), None)
        if invincibleCard is not None:
            return invincibleCard

        equippedCard = next(iter(_OrderByDesc(
            [c for c in Enemy.MonsterZone if c is not None and c.Data is not None
             and (ignoreCurrentDestroy or c not in cdl) and len(c.EquipCards) > 0
             and self.CheckCanBeTargeted(c, canBeTarget, selfType) and self.CheckShouldNotIgnore(c)],
            lambda c: c.Attack)), None)
        if equippedCard is not None:
            return equippedCard

        enemyExtraMonster = next(iter(_OrderByDesc(
            [c for c in Enemy.MonsterZone if c is not None and (ignoreCurrentDestroy or c not in cdl)
             and (c.HasType(CardType.Fusion | CardType.Ritual | CardType.Synchro | CardType.Xyz)
                  or (c.HasType(CardType.Link) and c.LinkCount >= 2))
             and self.CheckCanBeTargeted(c, canBeTarget, selfType) and self.CheckShouldNotIgnore(c)],
            lambda c: c.Attack)), None)
        if enemyExtraMonster is not None:
            return enemyExtraMonster

        activatingAlbaz = next((c for c in Enemy.MonsterZone if c is not None and c.IsCode(CardId.FallenOfAlbaz)
                                and not c.IsDisabled() and c not in cdl and c not in self.currentNegateCardList
                                and c in self.Duel.CurrentChain), None)
        if activatingAlbaz is not None:
            return activatingAlbaz

        if attack >= 0:
            if attack == 0:
                attack = self.Util.GetBestAttack(self.Bot)
            betterCard = next(iter(_OrderByDesc(
                [card for card in Enemy.MonsterZone if card is not None
                 and card.GetDefensePower() >= attack and card.GetDefensePower() > 0 and card.IsAttack()
                 and self.CheckCanBeTargeted(card, canBeTarget, selfType)
                 and (ignoreCurrentDestroy or card not in cdl)],
                lambda c: c.Attack)), None)
            if betterCard is not None:
                return betterCard
        return None

    def CheckShouldNotIgnore(self, cards, ignore=False):
        return not ignore or (cards not in self.currentDestroyCardList and cards not in self.currentNegateCardList)

    def GetDangerousCardinEnemyGrave(self, onlyMonster=False):
        result = GetMatchingCards(self.Enemy.Graveyard, lambda card:
                                  (not onlyMonster or card.IsMonster()) and (card.HasSetcode(SetcodeOrcust) or
                                                                             card.HasSetcode(SetcodePhantom) or
                                                                             card.HasSetcode(SetcodeHorus)))
        dangerMonsterIdList = [99937011, 63542003, 9411399, 28954097, 30680659]
        result.extend(GetMatchingCards(self.Enemy.Graveyard, lambda card: card.Id in dangerMonsterIdList))
        return result

    def GetProblematicEnemyCardList(self, canBeTarget=False, ignoreSpells=False, selfType=0):
        Enemy = self.Enemy
        cdl = self.currentDestroyCardList
        resultList = []

        floodagateList = _OrderByDesc(
            [c for c in Enemy.MonsterZone if c is not None and c.Data is not None and c not in cdl
             and c.IsFloodgate() and c.IsFaceup() and self.CheckCanBeTargeted(c, canBeTarget, selfType)],
            lambda c: c.Attack)
        if len(floodagateList) > 0:
            resultList.extend(floodagateList)

        problemEnemySpellList = [c for c in Enemy.SpellZone if c is not None and c.Data is not None
                                 and c not in resultList and c not in cdl and c.IsFloodgate() and c.IsFaceup()
                                 and self.CheckCanBeTargeted(c, canBeTarget, selfType)]
        if len(problemEnemySpellList) > 0:
            resultList.extend(self.Util.ShuffleList(problemEnemySpellList))

        dangerList = _OrderByDesc(
            [c for c in Enemy.MonsterZone if c is not None and c.Data is not None and c not in resultList
             and c not in cdl and c.IsMonsterDangerous() and c.IsFaceup()
             and self.CheckCanBeTargeted(c, canBeTarget, selfType)],
            lambda c: c.Attack)
        if len(dangerList) > 0 \
                and (self.Duel.Player == 0 or (self.Duel.Phase > DuelPhase.Main1 and self.Duel.Phase < DuelPhase.Main2)):
            resultList.extend(dangerList)

        invincibleList = _OrderByDesc(
            [c for c in Enemy.MonsterZone if c is not None and c.Data is not None and c not in resultList
             and c not in cdl and c.IsMonsterInvincible() and c.IsFaceup()
             and self.CheckCanBeTargeted(c, canBeTarget, selfType)],
            lambda c: c.Attack)
        if len(invincibleList) > 0:
            resultList.extend(invincibleList)

        enemyMonsters = _OrderByDesc([c for c in Enemy.GetMonsters() if c not in cdl], lambda c: c.Attack)
        if len(enemyMonsters) > 0:
            for target in enemyMonsters:
                if (target.HasType(CardType.Fusion | CardType.Ritual | CardType.Synchro | CardType.Xyz)
                        or (target.HasType(CardType.Link) and target.LinkCount >= 2)) \
                        and target not in resultList and self.CheckCanBeTargeted(target, canBeTarget, selfType):
                    resultList.append(target)

        spells = [c for c in Enemy.GetSpells() if c.IsFaceup() and c not in cdl
                  and c.HasType(CardType.Equip | CardType.Pendulum | CardType.Field | CardType.Continuous)
                  and self.CheckCanBeTargeted(c, canBeTarget, selfType) and c.Id not in self.notToDestroySpellTrap]
        if len(spells) > 0 and not ignoreSpells:
            resultList.extend(self.Util.ShuffleList(spells))

        return resultList

    def GetNormalEnemyTargetList(self, canBeTarget=True, ignoreCurrentDestroy=False, selfType=0):
        Enemy = self.Enemy
        cdl = self.currentDestroyCardList
        targetList = self.GetProblematicEnemyCardList(canBeTarget, selfType=selfType)
        enemyMonster = [card for card in Enemy.GetMonsters() if card.IsFaceup() and card not in targetList
                        and (not ignoreCurrentDestroy or card not in cdl)]
        enemyMonster.sort(key=CompareCardAttack)
        enemyMonster.reverse()
        targetList.extend(enemyMonster)
        targetList.extend(self.Util.ShuffleList([card for card in Enemy.GetSpells()
                                                 if (not ignoreCurrentDestroy or card not in cdl)
                                                 and card in self.enemyPlaceThisTurn]))
        targetList.extend(self.Util.ShuffleList([card for card in Enemy.GetSpells()
                                                 if (not ignoreCurrentDestroy or card not in cdl)
                                                 and card not in self.enemyPlaceThisTurn]))
        targetList.extend(self.Util.ShuffleList([card for card in Enemy.GetMonsters() if card.IsFacedown()
                                                 and (not ignoreCurrentDestroy or card not in cdl)]))
        return targetList

    def GetMonsterListForTargetNegate(self, canBeTarget=False, selfType=0):
        resultList = []
        if self.CheckWhetherNegated():
            return resultList

        target = next((card for card in self.Enemy.MonsterZone if card is not None and card.Data is not None
                       and card.IsMonsterShouldBeDisabledBeforeItUseEffect() and card.IsFaceup()
                       and not card.IsShouldNotBeTarget() and self.CheckCanBeTargeted(card, canBeTarget, selfType)
                       and card not in self.currentNegateCardList), None)
        if target is not None:
            resultList.append(target)

        for chainingCard in self.Duel.CurrentChain:
            if chainingCard.Location == CardLocation.MonsterZone and chainingCard.Controller == 1 \
                    and not chainingCard.IsDisabled() and self.CheckCanBeTargeted(chainingCard, canBeTarget, selfType) \
                    and chainingCard not in self.currentNegateCardList:
                resultList.append(chainingCard)

        return resultList

    def OnBattle(self, attackers, defenders):
        if len(attackers) > 0 and len(defenders) > 0:
            sortedAttacker = sorted(attackers, key=lambda card: card.GetAttackPower())
            abyssDragon = next((c for c in attackers if c.IsCode(CardId.AlbaLenatusTheAbyssDragon) and not c.IsDisabled()), None)
            if abyssDragon is not None:
                sortedAttacker.remove(abyssDragon)
                sortedAttacker.insert(0, abyssDragon)
            for k in range(len(sortedAttacker)):
                attacker = sortedAttacker[k]
                attacker.IsLastAttacker = k == len(sortedAttacker) - 1
                result = self.OnSelectAttackTarget(attacker, defenders)
                if result is not None:
                    return result

        return super().OnBattle(attackers, defenders)

    def OnSelectHand(self):
        return True

    def OnSelectCard(self, cards, min_, max_, hint, cancelable):
        Bot, Enemy, Duel, Util = self.Bot, self.Enemy, self.Duel, self.Util
        acl = self.activatedCardIdList
        currentSolvingChain = Duel.GetCurrentSolvingChainInfo()
        if currentSolvingChain is not None:
            if currentSolvingChain.ActivatePlayer == 1 and currentSolvingChain.IsActivateCode(_CardId.EvenlyMatched):
                banishList = []
                botMonsters = [card for card in Bot.GetMonsters() if not card.HasType(CardType.Token)]

                # monster
                faceDownMonsters = [card for card in botMonsters if card.IsFacedown()]
                banishList.extend(faceDownMonsters)
                dumpMainMonsterList = [card for card in botMonsters if card not in banishList
                                       and Bot.HasInDeck(card.GetNonAltartCode())]
                dumpMainMonsterList.sort(key=CompareCardAttack)
                banishList.extend(dumpMainMonsterList)

                # spells
                faceUpSpells = [c for c in Bot.GetSpells() if c.IsFaceup()]
                banishList.extend(Util.ShuffleList(faceUpSpells))
                faceDownSpells = [c for c in Bot.GetSpells() if c.IsFacedown()]
                banishList.extend(Util.ShuffleList(faceDownSpells))

                uniqueMainMonster = [card for card in botMonsters if card not in banishList
                                     and not card.HasType(CardType.Fusion | CardType.Synchro | CardType.Xyz | CardType.Link)
                                     and not Bot.HasInDeck(card.GetNonAltartCode())]
                uniqueMainMonster.sort(key=CompareCardAttack)
                banishList.extend(uniqueMainMonster)

                dumpExtraMonsterList = [card for card in botMonsters if card not in banishList
                                        and card.HasType(CardType.Fusion | CardType.Synchro | CardType.Xyz | CardType.Link)
                                        and Bot.HasInExtra(card.Id)]
                dumpExtraMonsterList.sort(key=CompareCardAttack)
                banishList.extend(dumpExtraMonsterList)

                uniqueExtraMonsterList = [card for card in botMonsters if card not in banishList
                                          and card.HasType(CardType.Fusion | CardType.Synchro | CardType.Xyz | CardType.Link)
                                          and not Bot.HasInExtra(card.Id)]
                uniqueExtraMonsterList.sort(key=CompareCardAttack)
                banishList.extend(uniqueExtraMonsterList)

                return Util.CheckSelectCount(banishList, cards, min_, max_)

            # search operation
            if hint == HintMsg.AddToHand:
                checkDict = {}
                aid = currentSolvingChain.ActivateId
                if aid in (CardId.AluberTheJesterOfDespia, CardId.AluberTheJesterOfDespia + 1, CardId.SpringansKitt):
                    checkDict = self.GetAluberKittSearchCheckDict(cards)
                elif aid == CardId.NadirServant:
                    if not self.summoned:
                        quem = next((c for c in cards if c.IsCode(CardId.GuidingQuemTheVirtuous)), None)
                        if quem is not None:
                            return Util.CheckSelectCount([quem], cards, min_, max_)
                    locList = [CardLocation.Grave, CardLocation.Deck]
                    if Bot.HasInGraveyard(CardId.RindbrummTheStrikingDragon) and \
                            sum(1 for c in cards if c.IsOriginalCode(CardId.FallenOfAlbaz) and c.Location == CardLocation.Grave) == 1:
                        locList = [CardLocation.Deck, CardLocation.Grave]
                    for checkId in (CardId.FallenOfAlbaz, CardId.GuidingQuemTheVirtuous):
                        for loc in locList:
                            target = next((c for c in cards if c.IsOriginalCode(checkId) and c.Location == loc), None)
                            if target is not None:
                                return Util.CheckSelectCount([target], cards, min_, max_)
                elif aid in (CardId.BrandedLost, CardId.TriBrigadeMercourier, CardId.BrandedInHighSpirits):
                    checkDict = {
                        CardId.TriBrigadeMercourier: lambda: any(c.IsFaceup() and c.IsCode(self.albazFusionMonster) for c in Bot.GetMonsters())
                        or (Bot.HasInMonstersZone(CardId.BlazingCartesiaTheVirtuous) and Bot.HasInHandOrHasInMonstersZone(CardId.FallenOfAlbaz)),
                        CardId.SpringansKitt: lambda: self.CheckWhetherCanSummon() and CardId.SpringansKitt + 1 not in acl,
                        CardId.FallenOfAlbaz: lambda: (self.CheckWhetherCanSummon() and self.CheckAlbazFusion())
                        or Bot.HasInMonstersZone(CardId.BlazingCartesiaTheVirtuous),
                        CardId.GuidingQuemTheVirtuous: lambda: self.CheckWhetherCanSummon(),
                        CardId.BlazingCartesiaTheVirtuous: lambda: self.CheckWhetherCanSummon()
                        or (not self.CheckShouldNoMoreSpSummon(CardLocation.Hand) and Bot.HasInMonstersZoneOrInGraveyard(CardId.FallenOfAlbaz)),
                        CardId.AlbionTheShroudedDragon: lambda: not self.DefaultCheckWhetherBotWillBeBanished(CardType.Spell | CardType.Trap, CardLocation.Hand | CardLocation.Deck)
                        and CardId.AlbionTheShroudedDragon not in acl,
                    }
                elif aid == CardId.AlbaLenatusTheAbyssDragon:
                    checkDict = {
                        CardId.BrandedFusion: lambda: self.BrandedFusionActivateCheck(False),
                        CardId.FusionDeployment: lambda: True,
                    }

                for key, func in checkDict.items():
                    target = next((card for card in cards if card.IsCode(key)), None)
                    if target is not None and func():
                        return Util.CheckSelectCount([target], cards, min_, max_)

            aid = currentSolvingChain.ActivateId
            # for lubellion
            if aid == CardId.TheBystialLubellion:
                lubellionCheckDict = {}
                if hint == HintMsg.ToField:
                    def brandedLostCheck():
                        fusionFlag = Bot.HasInHandOrHasInMonstersZone(CardId.BlazingCartesiaTheVirtuous)
                        if CardId.BrandedFusion not in acl:
                            if Bot.HasInHand(CardId.BrandedFusion) or (not self.summoned and Bot.HasInDeck(CardId.BrandedFusion)
                                                                       and Bot.HasInHand([CardId.AluberTheJesterOfDespia, CardId.SpringansKitt])):
                                fusionFlag = True
                        fusionFlag |= not self.summoned and Bot.HasInHand(CardId.FallenOfAlbaz) and self.CheckAlbazFusion()
                        fusionFlag |= Bot.HasInHandOrInSpellZone(CardId.BrandedInWhite) and self.BrandedInWhiteActivateCheck()
                        fusionFlag |= Bot.HasInHandOrInSpellZone(CardId.BrandedInRed) and self.BrandedInRedActivateCheck() is not None
                        return fusionFlag
                    lubellionCheckDict[CardId.BrandedLost] = brandedLostCheck
                    lubellionCheckDict[CardId.BrandedBeast] = lambda: True
                elif hint == HintMsg.AddToHand:
                    lubellionCheckDict[CardId.BystialSaronir] = lambda: True

                for key, func in lubellionCheckDict.items():
                    target = next((c for c in cards if c.Id == key), None)
                    if target is not None and func():
                        self.SelectSTPlace(target, False)
                        return Util.CheckSelectCount([target], cards, min_, max_)

            # for albaz
            elif aid in (CardId.FallenOfAlbaz, CardId.FallenOfAlbaz + 1):
                if hint == HintMsg.SpSummon:
                    fusionTargetIdList = [
                        CardId.MirrorjadeTheIcebladeDragon, CardId.AlbaLenatusTheAbyssDragon, CardId.AlbionTheBrandedDragon,
                        CardId.AlbionTheSanctifireDragon, CardId.LubellionTheSearingDragon, CardId.BorreloadFuriousDragon,
                        CardId.TitanikladTheAshDragon, CardId.RindbrummTheStrikingDragon]
                    for targetId in fusionTargetIdList:
                        if targetId == CardId.LubellionTheSearingDragon and len(Bot.Hand) == 0:
                            continue
                        target = next((c for c in cards if c.IsCode(targetId)), None)
                        if target is not None:
                            self.fusionTarget = target
                            return Util.CheckSelectCount([target], cards, min_, max_)
                if hint == HintMsg.FusionMaterial:
                    if len(cards) == 1:
                        self.selectedFusionMaterial.extend(cards)
                        return Util.CheckSelectCount(cards, cards, min_, max_)
                    # select best enemy monster
                    sortedResult = _OrderByDesc(cards, lambda card: card.GetDefensePower())
                    self.selectedFusionMaterial.append(sortedResult[0])
                    return Util.CheckSelectCount(sortedResult, cards, min_, max_)

            # for quem
            elif aid == CardId.GuidingQuemTheVirtuous:
                _, quemDumpCard = self.GetQuemSendToGraveTargetId(cards)
                if quemDumpCard is not None:
                    return Util.CheckSelectCount([quemDumpCard], cards, min_, max_)

            # for cartesia
            elif aid in (CardId.BlazingCartesiaTheVirtuous, CardId.BlazingCartesiaTheVirtuous + 1):
                if hint == HintMsg.SpSummon:
                    # fix material list
                    self.cartesiaMaterialList = [c for c in self.cartesiaMaterialList if c is not None and
                                                 (c.Location == CardLocation.MonsterZone or c.Location == CardLocation.Hand)]

                    # filter normal material
                    materialList = [c for c in Bot.MonsterZone if c is not None and c.GetDefensePower() <= 2500
                                    and not c.IsCode(self.cannotBeFusionMaterialIdList)]
                    materialList.extend(c for c in Bot.Hand if c.IsMonster() and not (self.CheckWhetherCanSummon() and (
                        (CardId.AluberTheJesterOfDespia not in acl and c.IsCode(CardId.AluberTheJesterOfDespia))
                        or (CardId.SpringansKitt not in acl and c.IsCode(CardId.SpringansKitt)))))

                    if self.cartesiaSummonGoal > 0:
                        _fusionTarget1, _ = self.BlazingCartesiaTheVirtuousFusionCheck(
                            cards, self.cartesiaSummonGoal, materialList, self.cartesiaMaterialList)
                        if _fusionTarget1 is not None:
                            self.fusionTarget = _fusionTarget1
                            return Util.CheckSelectCount([self.fusionTarget], cards, min_, max_)
                    _fusionTarget2, _ = self.BlazingCartesiaTheVirtuousFusionCheck(
                        cards, 0, materialList, self.cartesiaMaterialList)
                    if _fusionTarget2 is not None:
                        self.fusionTarget = _fusionTarget2
                        return Util.CheckSelectCount([self.fusionTarget], cards, min_, max_)

                if hint == HintMsg.FusionMaterial:
                    mustSelectMaterialList = _Intersect(self.cartesiaMaterialList, cards)
                    if len(mustSelectMaterialList) > 0:
                        self.selectedFusionMaterial.append(mustSelectMaterialList[0])
                        return Util.CheckSelectCount(mustSelectMaterialList, cards, min_, max_)

                    lubellion = next((c for c in cards if c is not None and c.IsCode(CardId.TheBystialLubellion)
                                      and c.Location == CardLocation.MonsterZone), None)
                    if lubellion is not None and not Bot.HasInHandOrInSpellZone(CardId.BrandedBeast):
                        if CardId.TheBystialLubellion + 1 in acl or not Bot.HasInDeck(CardId.BrandedLost, CardId.BrandedBeast):
                            if Util.IsTurn1OrMain2() or sum(1 for c in Enemy.MonsterZone if c is not None and c.GetDefensePower() < 2500) > 0:
                                return Util.CheckSelectCount([lubellion], cards, min_, max_)

                    selectTarget = next(iter(_OrderBy(
                        [c for c in cards if c.Attack <= 2500 and not (self.CheckWhetherCanSummon() and (
                            (CardId.AluberTheJesterOfDespia not in acl and c.IsCode(CardId.AluberTheJesterOfDespia))
                            or (CardId.SpringansKitt not in acl and c.IsCode(CardId.SpringansKitt))))],
                        lambda c: c.GetDefensePower())), None)
                    if selectTarget is not None:
                        self.selectedFusionMaterial.append(selectTarget)
                        return Util.CheckSelectCount([selectTarget], cards, min_, max_)
                    selectTarget = next(iter(_OrderBy(cards, lambda c: c.GetDefensePower())), None)
                    if selectTarget is not None:
                        self.selectedFusionMaterial.append(selectTarget)
                        return Util.CheckSelectCount([selectTarget], cards, min_, max_)

            # for nadir
            elif aid == CardId.NadirServant:
                if hint == HintMsg.ToGrave:
                    if self.summoned:
                        if Bot.HasInDeck(CardId.BlazingCartesiaTheVirtuous):
                            lulu = next((c for c in cards if c.IsOriginalCode(CardId.DespianLuluwalilith)), None)
                            if lulu is not None:
                                return Util.CheckSelectCount([lulu], cards, min_, max_)
                        if not any(c is not None and c.HasType(CardType.Fusion) for c in Bot.MonsterZone) \
                                and Bot.HasInDeck(CardId.SpringansKitt):
                            ironDragon = next((c for c in cards if c.IsOriginalCode(CardId.SprindTheIrondashDragon)), None)
                            if ironDragon is not None:
                                return Util.CheckSelectCount([ironDragon], cards, min_, max_)
                    _, target = self.NadirServantActivateCheck(cards, True)
                    if target is not None:
                        return Util.CheckSelectCount([target], cards, min_, max_)

            # for deployment
            elif aid == CardId.FusionDeployment:
                summonId = self.FusionDeploymentSpSummonTarget()
                if summonId > 0:
                    if hint == HintMsg.Confirm:
                        if summonId == CardId.BlazingCartesiaTheVirtuous:
                            target = next((card for card in cards if card.IsCode(CardId.GranguignolTheDuskDragon)), None)
                            if target is not None:
                                return Util.CheckSelectCount([target], cards, min_, max_)
                        elif summonId == CardId.FallenOfAlbaz:
                            shuffleList = Util.ShuffleList(cards)
                            for target in shuffleList:
                                if target.IsCode(self.albazFusionMonster):
                                    return Util.CheckSelectCount([target], cards, min_, max_)
                    if hint == HintMsg.SpSummon:
                        for target in cards:
                            if target.IsCode(summonId):
                                return Util.CheckSelectCount([target], cards, min_, max_)

            # for branded in white
            elif aid == CardId.BrandedInWhite:
                if hint == HintMsg.SpSummon:
                    _, target = self.BrandedInWhiteFusionTarget(cards)
                    if target is not None:
                        self.fusionTarget = target
                        return Util.CheckSelectCount([target], cards, min_, max_)
                if hint == HintMsg.FusionMaterial and self.fusionTarget is not None:
                    fusionTarget = self.fusionTarget
                    keep = self.CheckWhetherShouldKeepInGrave
                    if fusionTarget.IsCode(CardId.BorreloadFuriousDragon):
                        # select 2 dark dragon monster
                        for loc in (CardLocation.Grave, CardLocation.Hand, CardLocation.MonsterZone):
                            cardsInLoc = _OrderBy([c for c in cards if c.Location == loc], lambda c: c.GetDefensePower())
                            banishedAlbazCount = sum(1 for c in Bot.Banished if c.IsOriginalCode(CardId.FallenOfAlbaz))
                            banishedAlbazCount += sum(1 for c in self.selectedFusionMaterial if c.IsOriginalCode(CardId.FallenOfAlbaz))
                            for target in cardsInLoc:
                                # keep albaz
                                if target.IsOriginalCode(CardId.FallenOfAlbaz) and banishedAlbazCount > 0:
                                    continue
                                self.selectedFusionMaterial.append(target)
                                return Util.CheckSelectCount([target], cards, min_, max_)
                    if fusionTarget.IsCode(CardId.DespianQuaeritis):
                        # select despain
                        if len(self.selectedFusionMaterial) == 0:
                            for loc in (CardLocation.Grave, CardLocation.Hand, CardLocation.MonsterZone):
                                cardsInLoc = _OrderBy([c for c in cards if c.Location == loc and c.HasSetcode(SetcodeDespain)
                                                       and (loc != CardLocation.Grave or not keep(c))], lambda c: c.GetDefensePower())
                                if len(cardsInLoc) > 0:
                                    self.selectedFusionMaterial.append(cardsInLoc[0])
                                    return Util.CheckSelectCount(cardsInLoc, cards, min_, max_)
                        # select light/dark
                        else:
                            for loc in (CardLocation.Grave, CardLocation.Hand, CardLocation.MonsterZone):
                                cardsInLoc = _OrderBy([c for c in cards if c.Location == loc
                                                       and c.HasAttribute(CardAttribute.Light | CardAttribute.Dark)
                                                       and (loc != CardLocation.Grave or not keep(c))], lambda c: c.GetDefensePower())
                                if len(cardsInLoc) > 0:
                                    if CardId.TriBrigadeMercourier + 1 not in self.activatedCardIdList:
                                        mercourier = next((c for c in cardsInLoc if c.IsCode(CardId.TriBrigadeMercourier)), None)
                                        if mercourier is not None:
                                            self.selectedFusionMaterial.append(mercourier)
                                            return Util.CheckSelectCount([mercourier], cards, min_, max_)
                                    if CardId.DespianTragedy not in self.activatedCardIdList and \
                                            Bot.HasInDeck(CardId.AluberTheJesterOfDespia, CardId.GuidingQuemTheVirtuous):
                                        tragedy = next((c for c in cardsInLoc if c.IsCode(CardId.DespianTragedy)), None)
                                        if tragedy is not None:
                                            self.selectedFusionMaterial.append(tragedy)
                                            return Util.CheckSelectCount([tragedy], cards, min_, max_)

                                    self.selectedFusionMaterial.append(cardsInLoc[0])
                                    return Util.CheckSelectCount(cardsInLoc, cards, min_, max_)
                    if fusionTarget.IsCode(CardId.GuardianChimera):
                        goalMaterialList = _Intersect(self.ChimeraFusionMaterialList(), cards)
                        if len(goalMaterialList) > 0:
                            return Util.CheckSelectCount(goalMaterialList, cards, min_, max_)
                    if fusionTarget.IsCode(self.albazFusionMonster):
                        # selecting albaz
                        if len(self.selectedFusionMaterial) == 0:
                            for loc in (CardLocation.Grave, CardLocation.MonsterZone, CardLocation.Hand):
                                albaz = next(iter(_OrderBy([c for c in cards if c.IsCode(CardId.FallenOfAlbaz)],
                                                           lambda c: c.GetDefensePower())), None)
                                if albaz is not None:
                                    self.selectedFusionMaterial.append(albaz)
                                    return Util.CheckSelectCount([albaz], cards, min_, max_)
                        else:
                            if fusionTarget.IsOriginalCode(CardId.AlbaLenatusTheAbyssDragon) and cancelable:
                                return None
                            if Util.IsTurn1OrMain2():
                                duskDragon = next((c for c in cards if c.IsCode(CardId.GranguignolTheDuskDragon)
                                                   and c.Location == CardLocation.MonsterZone
                                                   and not self.DefaultCheckWhetherBotWillBeBanished(c)), None)
                                if duskDragon is not None:
                                    self.selectedFusionMaterial.append(duskDragon)
                                    return Util.CheckSelectCount([duskDragon], cards, min_, max_)
                            funcList = [
                                lambda c: c.Location == CardLocation.Grave and not keep(c),
                                lambda c: c.Location == CardLocation.MonsterZone and c.GetDefensePower() <= 2000,
                                lambda c: c.Location == CardLocation.Hand,
                                lambda c: c.Location == CardLocation.Grave,
                                lambda c: c.Location == CardLocation.MonsterZone,
                            ]
                            for func in funcList:
                                targetList = _OrderBy([c for c in cards if func(c)], lambda c: c.GetDefensePower())
                                if len(targetList) > 0:
                                    self.selectedFusionMaterial.append(targetList[0])
                                    return Util.CheckSelectCount([targetList[0]], cards, min_, max_)

            # for branded fusion
            elif aid == CardId.BrandedFusion:
                if hint == HintMsg.SpSummon:
                    def albionBrandedCheck():
                        checkFlag = any(c is not None and c.IsMonster() and c.HasAttribute(CardAttribute.Dark)
                                        and not c.IsCode(self.cannotBeFusionMaterialIdList) for c in Bot.Graveyard)
                        checkFlag |= Bot.HasInHandOrHasInMonstersZone(CardId.TriBrigadeMercourier)
                        checkFlag |= any(c.GetDefensePower() <= 1800 and c.HasAttribute(CardAttribute.Dark)
                                         and not c.IsCode(self.cannotBeFusionMaterialIdList) for c in Bot.GetMonsters())
                        return checkFlag
                    brandedFusionCheckDict = {
                        CardId.TitanikladTheAshDragon: lambda: Enemy.HasInMonstersZone(CardId.KashtiraAriseHeart),
                        CardId.RindbrummTheStrikingDragon: lambda: self.DefaultCheckWhetherBotWillBeBanished(CardType.Monster, CardLocation.Deck) and Bot.HasInDeck(CardId.TriBrigadeMercourier),
                        CardId.AlbionTheSanctifireDragon: lambda: self.CheckShouldNoMoreSpSummon(CardLocation.Extra),
                        CardId.AlbionTheBrandedDragon: albionBrandedCheck,
                        CardId.LubellionTheSearingDragon: lambda: not self.CheckWhetherNegated(True, True, CardType.Monster)
                        and len(Bot.Hand) > 0,
                        CardId.MirrorjadeTheIcebladeDragon: lambda: Bot.HasInMonstersZone([
                            CardId.GranguignolTheDuskDragon, CardId.AlbionTheBrandedDragon, CardId.LubellionTheSearingDragon]),
                    }
                    for key, func in brandedFusionCheckDict.items():
                        target = next((card for card in cards if card.IsCode(key)), None)
                        if target is not None and func():
                            self.fusionTarget = target
                            return Util.CheckSelectCount([target], cards, min_, max_)
                if hint == HintMsg.FusionMaterial:
                    # selecting albaz
                    if len(self.selectedFusionMaterial) == 0:
                        for loc in (CardLocation.Deck, CardLocation.Hand, CardLocation.MonsterZone):
                            target = next((c for c in cards if c.IsOriginalCode(CardId.FallenOfAlbaz) and c.Location == loc), None)
                            if target is not None:
                                self.selectedFusionMaterial.append(target)
                                return Util.CheckSelectCount([target], cards, min_, max_)
                    # selecting another material
                    if self.fusionTarget is not None:
                        materialDict = {
                            CardId.AlbionTheSanctifireDragon: [CardId.BlazingCartesiaTheVirtuous, _CardId.EffectVeiler,
                                                               CardId.GuidingQuemTheVirtuous],
                            CardId.MirrorjadeTheIcebladeDragon: [CardId.GranguignolTheDuskDragon, CardId.AlbionTheBrandedDragon,
                                                                 CardId.DespianLuluwalilith],
                            CardId.LubellionTheSearingDragon: [CardId.DespianTragedy, CardId.BystialSaronir,
                                                               CardId.AlbionTheShroudedDragon, CardId.AluberTheJesterOfDespia,
                                                               CardId.TriBrigadeMercourier],
                            CardId.TitanikladTheAshDragon: [CardId.TheBystialLubellion, CardId.AlbionTheShroudedDragon,
                                                            CardId.BystialSaronir],
                            CardId.RindbrummTheStrikingDragon: [CardId.TriBrigadeMercourier, CardId.SpringansKitt],
                            CardId.AlbionTheBrandedDragon: [CardId.TheBystialLubellion, CardId.BlazingCartesiaTheVirtuous,
                                                            CardId.GuidingQuemTheVirtuous],
                        }
                        checkIdList = materialDict.get(self.fusionTarget.GetOriginCode())
                        if checkIdList is not None and len(checkIdList) > 0:
                            for location in (CardLocation.Deck, CardLocation.Hand, CardLocation.MonsterZone):
                                for checkId in checkIdList:
                                    target = next((c for c in cards if c.Location == location and c.IsCode(checkId)), None)
                                    if target is not None:
                                        self.selectedFusionMaterial.append(target)
                                        return Util.CheckSelectCount([target], cards, min_, max_)

            # for Sarcophagus
            elif aid == CardId.GoldSarcophagus:
                _, sarcophagusTarget = self.GoldSarcophagusTarget(cards)
                if sarcophagusTarget is not None:
                    return Util.CheckSelectCount([sarcophagusTarget], cards, min_, max_)

            # for burial
            elif aid in (CardId.FoolishBurial, CardId.FoolishBurial + 1):
                _, burialTarget = self.FoolishBurialTarget(cards)
                if burialTarget is not None:
                    return Util.CheckSelectCount([burialTarget], cards, min_, max_)

            # for high spirit
            elif aid == CardId.BrandedInHighSpirits:
                # confirm
                if hint == HintMsg.Confirm:
                    if Duel.Phase == DuelPhase.End and Bot.HasInMonstersZone(CardId.GuidingQuemTheVirtuous):
                        cartesia = next((c for c in cards if c.IsOriginalCode(CardId.BlazingCartesiaTheVirtuous)), None)
                        if cartesia is not None:
                            self.fusionTarget = cartesia
                            return Util.CheckSelectCount([cartesia], cards, min_, max_)
                    activatingShroudedFlag = any(c.IsOriginalCode(CardId.AlbionTheShroudedDragon) and c.Location == CardLocation.Hand
                                                 for c in Duel.CurrentChain)
                    if activatingShroudedFlag:
                        shrouded = next((c for c in cards if c.IsOriginalCode(CardId.AlbionTheShroudedDragon)), None)
                        if shrouded is not None:
                            self.fusionTarget = shrouded
                            return Util.CheckSelectCount([shrouded], cards, min_, max_)
                    discardIdList = [CardId.BystialSaronir, CardId.AlbionTheShroudedDragon, CardId.TheBystialLubellion,
                                     CardId.BlazingCartesiaTheVirtuous, CardId.FallenOfAlbaz, CardId.TriBrigadeMercourier]
                    for discardId in discardIdList:
                        target = next((c for c in cards if c.IsOriginalCode(discardId)), None)
                        if target is not None:
                            # lubellion check
                            if discardId == CardId.TheBystialLubellion and Duel.Player == 0 and \
                                    (Duel.Phase <= DuelPhase.Main1 or Duel.Phase == DuelPhase.Main2) and \
                                    Bot.HasInDeck(CardId.BystialSaronir) and CardId.TheBystialLubellion not in acl:
                                continue
                            self.fusionTarget = target
                            return Util.CheckSelectCount([target], cards, min_, max_)
                # discard
                if hint == HintMsg.ToGrave:
                    discardIdList = [CardId.AlbionTheBrandedDragon, CardId.TitanikladTheAshDragon,
                                     CardId.RindbrummTheStrikingDragon, CardId.AlbaLenatusTheAbyssDragon,
                                     CardId.GranguignolTheDuskDragon]
                    for discardId in discardIdList:
                        if any(c.IsOriginalCode(discardId) for c in self.sendToGYThisTurn):
                            continue
                        target = next((c for c in cards if c.IsOriginalCode(discardId)), None)
                        if target is not None:
                            return Util.CheckSelectCount([target], cards, min_, max_)

            # for opening
            elif aid == CardId.BrandedOpening:
                if hint == HintMsg.OperateCard:
                    openingCheckDict = {
                        CardId.AluberTheJesterOfDespia: lambda: CardId.AluberTheJesterOfDespia not in acl
                        and not self.DefaultCheckWhetherCardIdIsNegated(CardId.AluberTheJesterOfDespia)
                        and not (self.CheckWhetherCanSummon() and Bot.HasInHand(CardId.AluberTheJesterOfDespia)),
                        CardId.GuidingQuemTheVirtuous: lambda: True,
                        CardId.DespianTragedy: lambda: True,
                    }
                    for key, func in openingCheckDict.items():
                        target = next((card for card in cards if card.IsCode(key)), None)
                        if target is not None and func():
                            return Util.CheckSelectCount([target], cards, min_, max_)

            # for branded in red
            elif aid == CardId.BrandedInRed:
                if hint == HintMsg.SpSummon:
                    # filter normal material
                    materialList = [c for c in Bot.MonsterZone if c is not None and c.GetDefensePower() <= 2500
                                    and not c.IsCode(self.cannotBeFusionMaterialIdList)]
                    materialList.extend(c for c in Bot.Hand if c.IsMonster() and not (self.CheckWhetherCanSummon() and (
                        (CardId.AluberTheJesterOfDespia not in acl and c.IsCode(CardId.AluberTheJesterOfDespia))
                        or (CardId.SpringansKitt not in acl and c.IsCode(CardId.SpringansKitt)))))

                    _fusionTarget, _ = self.BrandedInRedFusionCheck(cards, 0, materialList, self.brandedInRedMaterialList)
                    if _fusionTarget is not None:
                        self.fusionTarget = _fusionTarget
                        return Util.CheckSelectCount([self.fusionTarget], cards, min_, max_)

                if hint == HintMsg.FusionMaterial:
                    mustSelectMaterialList = _Intersect(self.brandedInRedMaterialList, cards)
                    if len(mustSelectMaterialList) > 0:
                        self.selectedFusionMaterial.append(mustSelectMaterialList[0])
                        return Util.CheckSelectCount(mustSelectMaterialList, cards, min_, max_)

                    selectTarget = next(iter(_OrderBy(
                        [c for c in cards if c.Attack <= 2500 and not (self.CheckWhetherCanSummon() and (
                            (CardId.AluberTheJesterOfDespia not in acl and c.IsCode(CardId.AluberTheJesterOfDespia))
                            or (CardId.SpringansKitt not in acl and c.IsCode(CardId.SpringansKitt))))],
                        lambda c: c.GetDefensePower())), None)
                    if selectTarget is not None:
                        self.selectedFusionMaterial.append(selectTarget)
                        return Util.CheckSelectCount([selectTarget], cards, min_, max_)
                    selectTarget = next(iter(_OrderBy(cards, lambda c: c.GetDefensePower())), None)
                    if selectTarget is not None:
                        self.selectedFusionMaterial.append(selectTarget)
                        return Util.CheckSelectCount([selectTarget], cards, min_, max_)

            # for branded king
            elif aid == CardId.BrightestBlazingBrandedKing:
                if hint == HintMsg.Faceup:
                    targetIdList = [CardId.MirrorjadeTheIcebladeDragon, CardId.AlbionTheSanctifireDragon,
                                    CardId.RindbrummTheStrikingDragon]
                    funcList = [lambda c: c in Duel.CurrentChain, lambda c: True]
                    for func in funcList:
                        chainedList = [c for c in cards if func(c)]
                        if len(chainedList) > 0:
                            for checkId in targetIdList:
                                target = next((c for c in chainedList if c.IsOriginalCode(checkId)), None)
                                if target is not None:
                                    return Util.CheckSelectCount([target], cards, min_, max_)
                            otherChainTarget = next((c for c in chainedList if c in Duel.CurrentChain), None)
                            if otherChainTarget is not None:
                                return Util.CheckSelectCount([otherChainTarget], cards, min_, max_)

            # for retribution
            elif aid == CardId.BrandedRetribution:
                searing = next((c for c in cards if c.IsCode(CardId.LubellionTheSearingDragon)), None)
                if searing is not None:
                    self.selectedFusionMaterial.append(searing)
                    return Util.CheckSelectCount([searing], cards, min_, max_)
                checkIdList = [CardId.AlbionTheBrandedDragon, CardId.MirrorjadeTheIcebladeDragon, CardId.TitanikladTheAshDragon,
                               CardId.AlbaLenatusTheAbyssDragon, CardId.AlbionTheSanctifireDragon, CardId.SprindTheIrondashDragon]
                for checkId in checkIdList:
                    gravePriorityList = [c for c in cards if c is not None and c.IsCode(checkId) and c.Location == CardLocation.Grave
                                         and not self.CheckWhetherShouldKeepInGrave(c)]
                    if len(gravePriorityList) > 0:
                        self.selectedFusionMaterial.append(gravePriorityList[0])
                        return Util.CheckSelectCount([gravePriorityList[0]], cards, min_, max_)
                graveList = [c for c in cards if c is not None and c.Location == CardLocation.Grave]
                if len(graveList) > 0:
                    self.selectedFusionMaterial.append(graveList[0])
                    return Util.CheckSelectCount([graveList[0]], cards, min_, max_)
                monsterOnField = next(iter(_OrderBy([c for c in cards if c is not None and c.Location == CardLocation.MonsterZone],
                                                    lambda c: c.GetDefensePower())), None)
                if monsterOnField is not None:
                    self.selectedFusionMaterial.append(monsterOnField)
                    return Util.CheckSelectCount([monsterOnField], cards, min_, max_)

            # for chimera
            elif aid == CardId.GuardianChimera:
                targetList = []
                targetList.extend(self.GetProblematicEnemyCardList(False, False, CardType.Monster))
                bestBotPower = Util.GetBestPower(Bot)
                targetList.extend(_OrderByDesc([c for c in Enemy.MonsterZone if c is not None and c not in targetList
                                                and c.GetDefensePower() >= bestBotPower], lambda c: c.GetDefensePower()))
                targetList.extend(Util.ShuffleList(self.enemyPlaceThisTurn))
                return Util.CheckSelectCount(targetList, cards, min_, max_)

            # for sanctifire
            elif aid == CardId.AlbionTheSanctifireDragon:
                if hint == Util.GetStringId(CardId.AlbionTheSanctifireDragon, 1):
                    albaz = next((c for c in cards if c.IsOriginalCode(CardId.FallenOfAlbaz)), None)
                    if albaz is not None and self.CheckAlbazFusion():
                        return Util.CheckSelectCount([albaz], cards, min_, max_)

                    floogate = next(iter(_OrderByDesc([c for c in cards if c.IsFloodgate()], lambda c: c.GetDefensePower())), None)
                    if floogate is not None:
                        return Util.CheckSelectCount([floogate], cards, min_, max_)

                    return Util.CheckSelectCount(_OrderByDesc(cards, lambda c: c.GetDefensePower()), cards, min_, max_)

            # for mirrorjade
            elif aid == CardId.MirrorjadeTheIcebladeDragon:
                floodgateList = Util.ShuffleList([c for c in cards if c.Controller == 1 and c.IsFloodgate()])
                if len(floodgateList) > 0:
                    return Util.CheckSelectCount(floodgateList, cards, min_, max_)

                extraMonsterList = _OrderByDesc([c for c in cards if c.Controller == 1 and (
                    c.HasType(CardType.Fusion | CardType.Ritual | CardType.Synchro | CardType.Xyz)
                    or (c.HasType(CardType.Link) and c.LinkCount >= 2))], lambda c: c.GetDefensePower())
                if len(extraMonsterList) > 0:
                    return Util.CheckSelectCount(extraMonsterList, cards, min_, max_)

                worstBotMonster = Util.GetWorstBotMonster()
                worstBotPower = 0 if worstBotMonster is None else worstBotMonster.GetDefensePower()
                betterMonsterList = _OrderByDesc([c for c in cards if c.Controller == 1 and c.GetDefensePower() >= worstBotPower],
                                                 lambda c: c.GetDefensePower())
                if len(betterMonsterList) > 0:
                    return Util.CheckSelectCount(betterMonsterList, cards, min_, max_)

                dangerMonsterList = _OrderByDesc([c for c in cards if c.Controller == 1 and
                                                  (c.IsMonsterDangerous() or c.IsMonsterInvincible())],
                                                 lambda c: c.GetDefensePower())
                if len(dangerMonsterList) > 0:
                    return Util.CheckSelectCount(dangerMonsterList, cards, min_, max_)

                allEnemyMonsterList = _OrderByDesc([c for c in cards if c.Controller == 1],
                                                   lambda c: 0 if c.IsFacedown() else c.GetDefensePower())
                if len(allEnemyMonsterList) > 0:
                    return Util.CheckSelectCount(allEnemyMonsterList, cards, min_, max_)

                botMonsterWithEffect = next((c for c in cards if c.Controller == 0 and
                                             c.IsCode([CardId.DespianTragedy, CardId.TriBrigadeMercourier])), None)
                if botMonsterWithEffect is not None:
                    return Util.CheckSelectCount([botMonsterWithEffect], cards, min_, max_)
                botLubellion = next((c for c in cards if c.Controller == 0 and c.IsCode(CardId.TheBystialLubellion)), None)
                if botLubellion is not None:
                    return Util.CheckSelectCount([botLubellion], cards, min_, max_)

                allBotMonster = _OrderBy([c for c in cards if c.Controller == 0],
                                         lambda c: 0 if c.IsFacedown() else c.GetDefensePower())
                if len(allBotMonster) > 0:
                    return Util.CheckSelectCount(allBotMonster, cards, min_, max_)

            # for searing dragon
            elif aid == CardId.LubellionTheSearingDragon:
                if hint == HintMsg.SpSummon:
                    _, target = self.LubellionTheSearingDragonFusionTarget(cards)
                    if target is not None:
                        self.fusionTarget = target
                        return Util.CheckSelectCount([target], cards, min_, max_)
                if hint == HintMsg.FusionMaterial and self.fusionTarget is not None:
                    fusionTarget = self.fusionTarget
                    keep = self.CheckWhetherShouldKeepInGrave
                    if fusionTarget.IsCode(CardId.BorreloadFuriousDragon):
                        # select 2 dark dragon monster
                        furiousFuncList = [
                            lambda c: c.IsFaceup() and c.Location == CardLocation.Removed and c.IsCode(CardId.AlbionTheBrandedDragon),
                            lambda c: c.IsFaceup() and c.Location == CardLocation.Removed and c.IsCode(CardId.FallenOfAlbaz),
                            lambda c: c.Location == CardLocation.Grave and c.IsCode(CardId.AlbionTheBrandedDragon) and not keep(c),
                            lambda c: c.IsFaceup() and c.Location == CardLocation.Removed and c.IsCode(CardId.TitanikladTheAshDragon),
                            lambda c: c.IsFaceup() and c.Location == CardLocation.Removed,
                            lambda c: c.Location == CardLocation.Grave and not keep(c),
                            lambda c: c.Location == CardLocation.Grave,
                            lambda c: c.Location == CardLocation.Hand or c.Location == CardLocation.MonsterZone,
                        ]
                        for func in furiousFuncList:
                            cardWithFunc = _OrderBy([c for c in cards if func(c)], lambda c: c.GetDefensePower())
                            if len(cardWithFunc) > 0:
                                self.selectedFusionMaterial.append(cardWithFunc[0])
                                return Util.CheckSelectCount([cardWithFunc[0]], cards, min_, max_)
                    funcList = [
                        lambda c: c.IsFaceup() and c.Location == CardLocation.Removed,
                        lambda c: c.Location == CardLocation.Grave and not keep(c),
                        lambda c: c.IsCode(CardId.LubellionTheSearingDragon),
                        lambda c: c.Location == CardLocation.Grave,
                        lambda c: c.Location == CardLocation.MonsterZone,
                        lambda c: c.Location == CardLocation.Hand,
                    ]
                    if len(self.selectedFusionMaterial) == 0:
                        if fusionTarget.IsOriginalCode(CardId.DespianQuaeritis):
                            for func in funcList:
                                cardsWithFunc = _OrderBy([c for c in cards if func(c) and c.HasSetcode(SetcodeDespain)],
                                                         lambda c: c.GetDefensePower())
                                if len(cardsWithFunc) > 0:
                                    self.selectedFusionMaterial.append(cardsWithFunc[0])
                                    return Util.CheckSelectCount(cardsWithFunc, cards, min_, max_)
                        if fusionTarget.IsCode(self.albazFusionMonster):
                            for func in funcList:
                                cardsWithFunc = _OrderBy([c for c in cards if func(c) and c.IsCode(CardId.FallenOfAlbaz)],
                                                         lambda c: c.GetDefensePower())
                                if len(cardsWithFunc) > 0:
                                    self.selectedFusionMaterial.append(cardsWithFunc[0])
                                    return Util.CheckSelectCount(cardsWithFunc, cards, min_, max_)
                    if fusionTarget.IsCode(CardId.AlbaLenatusTheAbyssDragon):
                        # select non-albaz
                        if len(self.selectedFusionMaterial) > 0:
                            funcList = [
                                lambda c: c.IsFaceup() and c.Location == CardLocation.Removed,
                                lambda c: c.Location == CardLocation.Grave and not keep(c),
                                lambda c: c.IsCode(CardId.LubellionTheSearingDragon),
                            ]
                    for func in funcList:
                        cardsWithFunc = _OrderBy([c for c in cards if func(c)], lambda c: c.GetDefensePower())
                        if len(cardsWithFunc) > 0:
                            self.selectedFusionMaterial.append(cardsWithFunc[0])
                            return Util.CheckSelectCount(cardsWithFunc, cards, min_, max_)
                    if fusionTarget.IsOriginalCode(CardId.AlbaLenatusTheAbyssDragon) and cancelable:
                        return None

            # for granguignol
            elif aid == CardId.GranguignolTheDuskDragon:
                if hint == HintMsg.ToGrave:
                    _, target = self.GranguignolTheDuskDragonSendToGYTarget(cards)
                    if target is not None:
                        return Util.CheckSelectCount([target], cards, min_, max_)
                if hint == HintMsg.SpSummon:
                    checkDict = {
                        CardId.DespianQuaeritis: lambda: any(c is not None and c.IsFaceup() and c.Attack >= Util.GetBestPower(Bot)
                                                             and not (c.HasType(CardType.Fusion) and c.Level >= 8)
                                                             for c in Enemy.MonsterZone),
                        CardId.GuidingQuemTheVirtuous: lambda: Bot.HasInMonstersZone(CardId.MirrorjadeTheIcebladeDragon)
                        or Util.GetOneEnemyBetterThanValue(1500) is None,
                        CardId.DespianLuluwalilith: lambda: not (Duel.Player == 0 and Bot.HasInHandOrInSpellZone(CardId.BrandedFusion)),
                    }
                    for key, func in checkDict.items():
                        target = next((c for c in cards if c.IsOriginalCode(key)), None)
                        if target is not None and func():
                            return Util.CheckSelectCount([target], cards, min_, max_)

            # for Quaeritis
            elif aid == CardId.DespianQuaeritis:
                checkDict = {
                    CardId.FallenOfAlbaz: lambda: self.CheckAlbazFusion(),
                    CardId.GuidingQuemTheVirtuous: lambda: not self.DefaultCheckWhetherCardIdIsNegated(CardId.GuidingQuemTheVirtuous),
                    CardId.AluberTheJesterOfDespia: lambda: not self.DefaultCheckWhetherCardIdIsNegated(CardId.AluberTheJesterOfDespia),
                    CardId.DespianTragedy: lambda: True,
                }
                for key, func in checkDict.items():
                    target = next((card for card in cards if card.IsCode(key)), None)
                    if target is not None and func():
                        self.fusionTarget = target
                        return Util.CheckSelectCount([target], cards, min_, max_)

            # for irondash dragon
            elif aid == CardId.SprindTheIrondashDragon:
                checkDict = {
                    CardId.FallenOfAlbaz: lambda: self.CheckAlbazFusion(),
                    CardId.SpringansKitt: lambda: not self.DefaultCheckWhetherCardIdIsNegated(CardId.SpringansKitt),
                }
                for key, func in checkDict.items():
                    target = next((card for card in cards if card.IsCode(key)), None)
                    if target is not None and func():
                        self.fusionTarget = target
                        return Util.CheckSelectCount([target], cards, min_, max_)

            # for ash dragon
            elif aid == CardId.TitanikladTheAshDragon:
                checkDict = {
                    CardId.FallenOfAlbaz: lambda: self.CheckAlbazFusion(),
                    CardId.GuidingQuemTheVirtuous: lambda: not self.DefaultCheckWhetherCardIdIsNegated(CardId.GuidingQuemTheVirtuous),
                }
                for key, func in checkDict.items():
                    target = next((card for card in cards if card.IsCode(key)), None)
                    if target is not None and func():
                        self.fusionTarget = target
                        return Util.CheckSelectCount([target], cards, min_, max_)

            # for rindrumm
            elif aid == CardId.RindbrummTheStrikingDragon:
                if hint == HintMsg.SpSummon:
                    checkDict = {
                        CardId.FallenOfAlbaz: lambda: self.CheckAlbazFusion(),
                        CardId.RindbrummTheStrikingDragon: lambda: True,
                        CardId.AlbionTheShroudedDragon: lambda: True,
                    }
                    for key, func in checkDict.items():
                        target = next((c for c in cards if c.IsOriginalCode(key)), None)
                        if target is not None and func():
                            return Util.CheckSelectCount([target], cards, min_, max_)
                if hint == HintMsg.ReturnToHand:
                    problemList = _OrderByDesc(_Intersect(self.GetProblematicEnemyCardList(False, True, CardType.Monster), cards),
                                               lambda c: c.GetDefensePower())
                    if len(problemList) > 0:
                        return Util.CheckSelectCount(problemList, cards, min_, max_)
                    worstBotMonster = Util.GetWorstBotMonster()
                    worstBotPower = 0 if worstBotMonster is None else worstBotMonster.GetDefensePower()
                    dangerList = _OrderByDesc([c for c in cards if c.IsFaceup() and c.Controller == 1
                                               and c.GetDefensePower() > worstBotPower], lambda c: c.GetDefensePower())
                    if len(dangerList) > 0:
                        return Util.CheckSelectCount(dangerList, cards, min_, max_)
                    checkIdList = [CardId.AluberTheJesterOfDespia, CardId.SpringansKitt]
                    for checkId in checkIdList:
                        target = next((c for c in cards if c.Controller == 0 and c.IsCode(checkId)), None)
                        if target is not None:
                            return Util.CheckSelectCount([target], cards, min_, max_)
                    enemyMonsterList = _OrderByDesc([c for c in cards if c.Controller == 1], lambda c: c.GetDefensePower())
                    if len(enemyMonsterList) > 0:
                        return Util.CheckSelectCount(enemyMonsterList, cards, min_, max_)
                    return Util.CheckSelectCount(_OrderByDesc([c for c in cards if c.Controller == 0],
                                                              lambda c: c.GetDefensePower()), cards, min_, max_)

            # for branded dragon
            elif aid == CardId.AlbionTheBrandedDragon:
                if hint == HintMsg.SpSummon:
                    _, target = self.AlbionTheBrandedDragonFusionTarget(cards)
                    if target is not None:
                        self.fusionTarget = target
                        return Util.CheckSelectCount([target], cards, min_, max_)
                if hint == HintMsg.FusionMaterial and self.fusionTarget is not None:
                    fusionTarget = self.fusionTarget
                    keep = self.CheckWhetherShouldKeepInGrave
                    if fusionTarget.IsCode(CardId.BorreloadFuriousDragon):
                        # select 2 dark dragon monster
                        for loc in (CardLocation.Grave, CardLocation.Hand, CardLocation.MonsterZone):
                            cardsInLoc = _OrderBy([c for c in cards if c.Location == loc], lambda c: c.GetDefensePower())
                            banishedAlbazCount = sum(1 for c in Bot.Banished if c.IsOriginalCode(CardId.FallenOfAlbaz))
                            banishedAlbazCount += sum(1 for c in self.selectedFusionMaterial if c.IsOriginalCode(CardId.FallenOfAlbaz))
                            for target in cardsInLoc:
                                # keep albaz
                                if target.IsOriginalCode(CardId.FallenOfAlbaz) and banishedAlbazCount > 0:
                                    continue
                                self.selectedFusionMaterial.append(target)
                                return Util.CheckSelectCount([target], cards, min_, max_)
                    if fusionTarget.IsCode(CardId.DespianQuaeritis):
                        # select despain
                        if len(self.selectedFusionMaterial) == 0:
                            for loc in (CardLocation.Grave, CardLocation.Hand, CardLocation.MonsterZone):
                                cardsInLoc = _OrderBy([c for c in cards if c.Location == loc and c.HasSetcode(SetcodeDespain)
                                                       and (loc != CardLocation.Grave or not keep(c))], lambda c: c.GetDefensePower())
                                if len(cardsInLoc) > 0:
                                    self.selectedFusionMaterial.append(cardsInLoc[0])
                                    return Util.CheckSelectCount(cardsInLoc, cards, min_, max_)
                        # select light/dark
                        else:
                            for loc in (CardLocation.Grave, CardLocation.Hand, CardLocation.MonsterZone):
                                cardsInLoc = _OrderBy([c for c in cards if c.Location == loc
                                                       and c.HasAttribute(CardAttribute.Light | CardAttribute.Dark)
                                                       and (loc != CardLocation.Grave or not keep(c))], lambda c: c.GetDefensePower())
                                if len(cardsInLoc) > 0:
                                    if CardId.TriBrigadeMercourier + 1 not in self.activatedCardIdList:
                                        mercourier = next((c for c in cardsInLoc if c.IsCode(CardId.TriBrigadeMercourier)), None)
                                        if mercourier is not None:
                                            self.selectedFusionMaterial.append(mercourier)
                                            return Util.CheckSelectCount([mercourier], cards, min_, max_)
                                    if CardId.DespianTragedy not in self.activatedCardIdList and \
                                            Bot.HasInDeck(CardId.AluberTheJesterOfDespia, CardId.GuidingQuemTheVirtuous):
                                        tragedy = next((c for c in cardsInLoc if c.IsCode(CardId.DespianTragedy)), None)
                                        if tragedy is not None:
                                            self.selectedFusionMaterial.append(tragedy)
                                            return Util.CheckSelectCount([tragedy], cards, min_, max_)

                                    self.selectedFusionMaterial.append(cardsInLoc[0])
                                    return Util.CheckSelectCount(cardsInLoc, cards, min_, max_)
                    if fusionTarget.IsCode(self.albazFusionMonster):
                        # selecting albaz
                        if len(self.selectedFusionMaterial) == 0:
                            for loc in (CardLocation.Grave, CardLocation.MonsterZone, CardLocation.Hand):
                                albaz = next(iter(_OrderBy([c for c in cards if c.IsCode(CardId.FallenOfAlbaz)
                                                            and c.Location == loc],
                                                           lambda c: c.GetDefensePower())), None)
                                if albaz is not None:
                                    self.selectedFusionMaterial.append(albaz)
                                    return Util.CheckSelectCount([albaz], cards, min_, max_)
                        else:
                            if fusionTarget.IsOriginalCode(CardId.AlbaLenatusTheAbyssDragon) and cancelable:
                                return None
                            funcList = [
                                lambda c: c.Location == CardLocation.Grave and not keep(c),
                                lambda c: c.Location == CardLocation.MonsterZone and c.GetDefensePower() <= 2000,
                                lambda c: c.Location == CardLocation.Grave,
                                lambda c: c.Location == CardLocation.Hand,
                                lambda c: c.Location == CardLocation.MonsterZone,
                            ]
                            for func in funcList:
                                targetList = _OrderBy([c for c in cards if func(c)], lambda c: c.GetDefensePower())
                                if len(targetList) > 0:
                                    self.selectedFusionMaterial.append(targetList[0])
                                    return Util.CheckSelectCount([targetList[0]], cards, min_, max_)
                if hint == HintMsg.OperateCard:
                    checkDict = {
                        CardId.BrandedInHighSpirits: lambda: Bot.HasInMonstersZone(CardId.GuidingQuemTheVirtuous)
                        and self.BrandedInHighSpiritsActivateCheck(),
                        CardId.BrightestBlazingBrandedKing: lambda: any(c is not None and c.IsFaceup() and c.IsCode(self.albazFusionMonster)
                                                                        for c in Bot.MonsterZone),
                        CardId.BrandedInRed: lambda: any(c is not None and (c.HasSetcode(SetcodeDespain) or c.IsCode(CardId.FallenOfAlbaz))
                                                         for c in Bot.Graveyard),
                        CardId.BrandedRetribution: lambda: sum(1 for c in Bot.Graveyard if c is not None
                                                               and c.IsCode(self.albazFusionMonster)) > 1,
                        CardId.BrandedFusion: lambda: Bot.HasInDeck(CardId.FallenOfAlbaz),
                        CardId.BrandedBeast: lambda: any(c is not None and c.IsFaceup() and c.HasSetcode(SetcodeBystial)
                                                         for c in Bot.MonsterZone),
                        CardId.BrandedLost: lambda: True,
                        CardId.BrandedInWhite: lambda: True,
                    }
                    for key, func in checkDict.items():
                        target = next((c for c in cards if c.IsOriginalCode(key)), None)
                        if target is not None and func():
                            self.fusionTarget = target
                            return Util.CheckSelectCount([target], cards, min_, max_)

            # for luluwa
            elif aid == CardId.DespianLuluwalilith:
                if hint == HintMsg.Disable:
                    enemyCardList = [c for c in cards if c.IsFaceup() and c.Controller == 1]
                    problemCardList = _Intersect(self.GetProblematicEnemyCardList(False, False, 0), enemyCardList)
                    if len(problemCardList) > 0:
                        return Util.CheckSelectCount(Util.ShuffleList(problemCardList), cards, min_, max_)
                    monsterList = _Intersect(self.GetMonsterListForTargetNegate(False, 0), enemyCardList)
                    if len(monsterList) > 0:
                        return Util.CheckSelectCount(Util.ShuffleList(monsterList), cards, min_, max_)
                    if len(enemyCardList) > 0:
                        return Util.CheckSelectCount(Util.ShuffleList(enemyCardList), cards, min_, max_)
                if hint == HintMsg.SpSummon:
                    for loc in (CardLocation.Deck, CardLocation.Hand):
                        for checkId in (CardId.BlazingCartesiaTheVirtuous, CardId.GuidingQuemTheVirtuous):
                            target = next((c for c in cards if c.Location == loc and c.IsOriginalCode(checkId)), None)
                            if target is not None:
                                return Util.CheckSelectCount([target], cards, min_, max_)

        # drop 1 hand
        discardHand = hint == HintMsg.Discard
        handToDeck = hint == HintMsg.ToDeck and all(c.Location == CardLocation.Hand for c in cards)
        if min_ == 1 and max_ == 1 and (discardHand or handToDeck):
            if currentSolvingChain is not None and currentSolvingChain.IsActivateCode(CardId.BrandedOpening):
                tragedy = next((card for card in cards if card.IsCode(CardId.DespianTragedy)), None)
                if tragedy is not None:
                    return Util.CheckSelectCount([tragedy], cards, min_, max_)
            if discardHand:
                # discard activating shrouded
                for target in cards:
                    if target.IsCode(CardId.AlbionTheShroudedDragon) and target in Duel.CurrentChain:
                        return Util.CheckSelectCount([target], cards, min_, max_)

                discardList = [CardId.BrandedRetribution, CardId.AlbionTheShroudedDragon, CardId.BystialSaronir,
                               CardId.BrightestBlazingBrandedKing, CardId.BrandedInHighSpirits,
                               CardId.BlazingCartesiaTheVirtuous, CardId.DespianTragedy]
                for id_ in discardList:
                    card = next((c for c in cards if c.IsCode(id_)), None)
                    if card is not None:
                        return Util.CheckSelectCount([card], cards, min_, max_)
            # return dump card
            for card in cards:
                if sum(1 for c in cards if c.IsCode(card.Id)) > 1:
                    return Util.CheckSelectCount([card], cards, min_, max_)
            improperCardIdList = [
                CardId.BrandedRetribution, CardId.BrandedInHighSpirits, CardId.DespianTragedy, CardId.FusionDeployment,
                CardId.BrandedBeast, CardId.AlbionTheShroudedDragon, CardId.BrandedOpening, CardId.GoldSarcophagus,
                CardId.FoolishBurial, CardId.FallenOfAlbaz, CardId.BrandedInRed, _CardId.InfiniteImpermanence,
                CardId.TheBystialLubellion, CardId.BrandedLost, CardId.SpringansKitt, CardId.GuidingQuemTheVirtuous,
                _CardId.CrossoutDesignator, _CardId.CalledByTheGrave, CardId.TriBrigadeMercourier, _CardId.AshBlossom,
                _CardId.MaxxC]
            for id_ in improperCardIdList:
                if id_ == CardId.BrandedLost and Bot.HasInHand(CardId.BrandedFusion) and self.BrandedFusionActivateCheck():
                    continue
                target = next((c for c in cards if c.IsCode(id_)), None)
                if target is not None:
                    return Util.CheckSelectCount([target], cards, min_, max_)
        elif discardHand and min_ > 0 and min_ == max_:
            discardList = []
            graveEffectIdList = [CardId.AlbionTheShroudedDragon, CardId.BrandedRetribution, CardId.BrandedInHighSpirits,
                                 CardId.BrightestBlazingBrandedKing, CardId.DespianTragedy]
            discardList.extend(Util.ShuffleList([c for c in cards if c.IsCode(graveEffectIdList)]))
            remainHandList = _Except(cards, discardList)

            seenIds = set()
            for idx in range(len(remainHandList) - 1, -1, -1):
                currentCard = remainHandList[idx]
                if currentCard.Id in seenIds:
                    discardList.append(currentCard)
                    remainHandList.remove(currentCard)
                else:
                    seenIds.add(currentCard.Id)

            improperCardIdList = [
                CardId.FusionDeployment, CardId.BrandedBeast, CardId.AlbionTheShroudedDragon, CardId.BrandedOpening,
                CardId.GoldSarcophagus, CardId.FoolishBurial, CardId.FallenOfAlbaz, CardId.BrandedInRed,
                _CardId.InfiniteImpermanence, CardId.TheBystialLubellion, CardId.BrandedLost, CardId.SpringansKitt,
                CardId.GuidingQuemTheVirtuous, _CardId.CrossoutDesignator, _CardId.CalledByTheGrave,
                CardId.TriBrigadeMercourier, _CardId.AshBlossom, _CardId.MaxxC]
            for id_ in improperCardIdList:
                target = next((c for c in remainHandList if c.IsCode(id_)), None)
                if target is not None:
                    discardList.append(target)
            if len(discardList) > min_:
                discardList = discardList[:min_]

            return Util.CheckSelectCount(discardList, cards, min_, max_)

        # for The Bystial Lubellion
        if self.theBystialLubellionSelecting:
            self.theBystialLubellionSelecting = False
            target = self.TheBystialLubellionSpSummonCost(cards)
            if target is not None:
                return Util.CheckSelectCount([target], cards, min_, max_)
            else:
                targetList = list(cards)
                targetList.sort(key=CompareCardAttack)
                return Util.CheckSelectCount(targetList, cards, min_, max_)

        # for shrouded/saronir
        if self.albionTheShroudedDragonSelecting or (currentSolvingChain is not None and
                                                     currentSolvingChain.IsActivateCode(CardId.BystialSaronir)):
            # send retribution first
            retribution = next((c for c in cards if c.IsCode(CardId.BrandedRetribution)), None)
            if retribution is not None:
                if retribution.Location == CardLocation.Deck or \
                        sum(1 for c in Bot.GetGraveyardMonsters() if c.IsCode(self.albazFusionMonster)) < 2:
                    return Util.CheckSelectCount([retribution], cards, min_, max_)
            # send spells to recycle
            if Bot.HasInGraveyard(CardId.BrandedRetribution) or \
                    (Bot.HasInGraveyard(CardId.DespianTragedy) and CardId.DespianTragedy not in acl):
                def brandedLostCheck():
                    if Duel.Player == 0 and Duel.Phase >= DuelPhase.End:
                        return False
                    if Bot.HasInHandOrInSpellZone(CardId.BrandedFusion) and self.BrandedFusionActivateCheck():
                        return True
                    if Bot.HasInHandOrInSpellZone(CardId.BrandedInWhite) and self.BrandedInWhiteActivateCheck():
                        return True
                    if Bot.HasInHandOrInSpellZone(CardId.BrandedInRed) and self.BrandedInRedActivateCheck() is not None:
                        return True
                    if not self.summoned and Bot.HasInHand(CardId.FallenOfAlbaz) and self.CheckAlbazFusion():
                        return True
                    if Bot.HasInMonstersZone(CardId.BlazingCartesiaTheVirtuous) or \
                            (not self.summoned and Bot.HasInHand(CardId.BlazingCartesiaTheVirtuous)):
                        return True
                    return False
                deckCheckDict = {
                    CardId.BrandedFusion: lambda: self.BrandedFusionActivateCheck(),
                    CardId.BrandedLost: brandedLostCheck,
                    CardId.BrandedInHighSpirits: self.BrandedInHighSpiritsActivateCheck,
                    CardId.BrandedInRed: lambda: self.BrandedInRedActivateCheck() is not None,
                    CardId.BrandedInWhite: self.BrandedInWhiteActivateCheck,
                    CardId.BrandedRetribution: lambda: any(c.IsCode(CardId.BrandedRetribution) and c.Location == CardLocation.Removed
                                                           for c in cards),
                    CardId.BrightestBlazingBrandedKing: lambda: any(c.IsFaceup() and c.IsCode(self.albazFusionMonster)
                                                                    for c in Bot.GetMonsters()),
                    CardId.BrandedOpening: lambda: len(Bot.Hand) > 2,
                }
                for key, func in deckCheckDict.items():
                    target = next((card for card in cards if card.Location == CardLocation.Deck and card.IsCode(key)), None)
                    if target is not None and func():
                        return Util.CheckSelectCount([target], cards, min_, max_)

            # for abyss dragon
            if self.albionTheShroudedDragonSelecting and self.FallenOfAlbazSetCheck() and \
                    (self.summoned or not Bot.HasInHand([CardId.FallenOfAlbaz, CardId.BrandedInHighSpirits])):
                checkIdList = [CardId.BrandedRetribution, CardId.BrandedInHighSpirits, CardId.BrightestBlazingBrandedKing,
                               CardId.BrandedInWhite, CardId.BrandedOpening, CardId.BrandedInRed, CardId.BrandedBeast,
                               CardId.BrandedLost]
                if not self.BrandedFusionActivateCheck():
                    checkIdList.append(CardId.BrandedFusion)
                for checkId in checkIdList:
                    target = next((c for c in cards if c.Id == checkId), None)
                    if target is not None:
                        return Util.CheckSelectCount([target], cards, min_, max_)

            # send from deck
            checkList = [CardId.BrandedInHighSpirits, CardId.BrandedOpening, CardId.BrightestBlazingBrandedKing,
                         CardId.BrandedBeast, CardId.BrandedLost]
            for checkId in checkList:
                target = next((c for c in cards if c.IsCode(checkId) and c.Location == CardLocation.Deck), None)
                if target is not None:
                    return Util.CheckSelectCount([target], cards, min_, max_)
            return Util.CheckSelectCount(Util.ShuffleList(cards), cards, min_, max_)

        return super().OnSelectCard(cards, min_, max_, hint, cancelable)

    def OnSelectOption(self, options):
        Duel, Bot = self.Duel, self.Bot
        currentSolvingChain = Duel.GetCurrentSolvingChainInfo()
        if currentSolvingChain is not None:
            # 1190=Add to Hand, 1152=Special Summon
            if len(options) == 2 and 1190 in options and 1152 in options:
                if currentSolvingChain.IsActivateCode(CardId.BrandedOpening):
                    return _IndexOf(options, 1190) if (self.CheckShouldNoMoreSpSummon(CardLocation.Deck) and not self.summoned
                                                       and Duel.Player == 0) else _IndexOf(options, 1152)

                if self.fusionTarget is not None and (
                        currentSolvingChain.IsActivateCode(CardId.DespianQuaeritis)
                        or currentSolvingChain.IsActivateCode(CardId.TitanikladTheAshDragon)
                        or currentSolvingChain.IsActivateCode(CardId.SprindTheIrondashDragon)):
                    if self.fusionTarget.IsCode(CardId.FallenOfAlbaz):
                        return _IndexOf(options, 1152) if self.CheckAlbazFusion() else _IndexOf(options, 1190)
                    if self.fusionTarget.IsCode(CardId.GuidingQuemTheVirtuous, CardId.SpringansKitt):
                        return _IndexOf(options, 1190) if self.CheckShouldNoMoreSpSummon(CardLocation.Grave) else _IndexOf(options, 1152)
                    if self.fusionTarget.IsCode(CardId.AluberTheJesterOfDespia):
                        return _IndexOf(options, 1190) if CardId.AluberTheJesterOfDespia in self.activatedCardIdList \
                            else _IndexOf(options, 1152)
                    return _IndexOf(options, 1190) if (self.CheckShouldNoMoreSpSummon(CardLocation.Grave) and not self.summoned) \
                        else _IndexOf(options, 1152)

            # 1190=Add to Hand, 1153=Set
            if currentSolvingChain.IsActivateCode(CardId.AlbionTheBrandedDragon) and self.fusionTarget is not None:
                if self.fusionTarget.IsOriginalCode(CardId.BrandedInHighSpirits) and Duel.Player == 0:
                    return _IndexOf(options, 1190) if self.BrandedInHighSpiritsActivateCheck() else _IndexOf(options, 1153)
                if self.fusionTarget.IsOriginalCode(CardId.BrandedInRed) and Duel.Player == 0:
                    if self.nadirActivated:
                        return _IndexOf(options, 1153)
                    return _IndexOf(options, 1190) if self.BrandedInRedActivateCheck() is not None else _IndexOf(options, 1153)
                if self.fusionTarget.Data is not None:
                    setFlag = self.fusionTarget.Data.HasType(CardType.Trap)
                    setFlag |= self.fusionTarget.Data.HasType(CardType.QuickPlay) and Duel.Player == 0
                    setFlag |= len(Bot.Hand) >= 6 and Duel.Player == 0
                    return _IndexOf(options, 1153) if setFlag else _IndexOf(options, 1190)

        return super().OnSelectOption(options)

    def OnSelectPlace(self, cardId, player, location, available):
        if player == 0 and location == CardLocation.MonsterZone:
            zoneIdList = self.Util.ShuffleList([5, 6])
            zoneIdList.extend(self.Util.ShuffleList([0, 2, 4]))
            zoneIdList.extend(self.Util.ShuffleList([1, 3]))
            for zoneId in zoneIdList:
                zone = 2 ** zoneId
                if (available & zone) != 0 and self.Bot.MonsterZone[zoneId] is None:
                    return zone
        return super().OnSelectPlace(cardId, player, location, available)

    def OnSelectDisfield(self, hint, count, available):
        currentSovingChain = self.Duel.GetCurrentSolvingChainInfo()
        if currentSovingChain is not None and currentSovingChain.ActivatePlayer == 0 and \
                currentSovingChain.IsActivateCode(CardId.SprindTheIrondashDragon):
            selected = self.SprindTheIrondashDragonMoveZone(available & Zones.MainMonsterZones, None)
            if selected > 0 and (selected & available) != 0:
                return selected
        return super().OnSelectDisfield(hint, count, available)

    def OnSelectYesNo(self, desc):
        Bot, Enemy, Util = self.Bot, self.Enemy, self.Util
        if desc == Util.GetStringId(CardId.BrandedInHighSpirits, 2):
            if self.DefaultCheckWhetherBotWillBeBanished(CardType.Monster, CardLocation.Hand):
                return False
            if self.fusionTarget is not None and self.fusionTarget.IsOriginalCode(CardId.TriBrigadeMercourier):
                return not any(c is not None and c.IsFaceup() and c.IsCode(self.albazFusionMonster) for c in Bot.MonsterZone)

        if desc == Util.GetStringId(CardId.RindbrummTheStrikingDragon, 2):
            checkFlag = any(c is not None for c in Enemy.MonsterZone)
            checkFlag |= any(c is not None and (c.IsOriginalCode(CardId.AluberTheJesterOfDespia) or
                                                c.IsOriginalCode(CardId.SpringansKitt)) for c in Bot.MonsterZone)
            return checkFlag

        if desc == Util.GetStringId(CardId.DespianLuluwalilith, 2):
            checkFlag = any(c is not None and c.IsFaceup() and not c.IsDisabled() for c in Enemy.MonsterZone)
            checkFlag |= any(c is not None and c.IsFaceup() and not c.IsDisabled() for c in Enemy.SpellZone)
            return checkFlag

        if desc == Util.GetStringId(CardId.BrandedInRed, 0):
            # fix material list
            self.brandedInRedMaterialList = [c for c in self.brandedInRedMaterialList if c is not None and
                                             (c.Location == CardLocation.MonsterZone or c.Location == CardLocation.Hand)]

            acl = self.activatedCardIdList
            materialList = [c for c in Bot.MonsterZone if c is not None and c.Attack <= 2500
                            and not c.IsCode(self.cannotBeFusionMaterialIdList)]
            materialList.extend(c for c in Bot.Hand if c.IsMonster() and not (self.CheckWhetherCanSummon() and (
                (CardId.AluberTheJesterOfDespia not in acl and c.IsCode(CardId.AluberTheJesterOfDespia))
                or (CardId.SpringansKitt not in acl and c.IsCode(CardId.SpringansKitt)))))

            _fusionTarget, _ = self.BrandedInRedFusionCheck(Bot.ExtraDeck, 0, materialList, self.brandedInRedMaterialList)

            return _fusionTarget is not None

        if desc == Util.GetStringId(CardId.SprindTheIrondashDragon, 2):
            currentSolvingChain = self.Duel.GetCurrentSolvingChainInfo()
            if currentSolvingChain is not None:
                value = self.SprindTheIrondashDragonDestroyValue(currentSolvingChain.RelatedCard.Sequence)
                return value > 0

        return super().OnSelectYesNo(desc)

    def OnSelectPosition(self, cardId, positions):
        Duel, Util = self.Duel, self.Util
        currentSolvingChain = Duel.GetCurrentSolvingChainInfo()
        if currentSolvingChain is not None and currentSolvingChain.IsActivateCode(CardId.AlbionTheSanctifireDragon):
            self.sanctifireSelectPositionCount += 1
            if self.sanctifireSelectPositionCount >= 2:
                if Duel.Phase <= DuelPhase.Main2:
                    return CardPosition.FaceUpDefence

        cardData = NamedCard.Get(cardId)
        if cardData is not None:
            if Duel.Turn == 1 or Duel.Phase >= DuelPhase.Main2:
                turnDefense = False
                if cardData.Attack <= cardData.Defense:
                    turnDefense = True
                if turnDefense:
                    return CardPosition.FaceUpDefence
            if Duel.Player == 1:
                if cardData.Defense >= cardData.Attack or Util.IsOneEnemyBetterThanValue(cardData.Attack, True):
                    return CardPosition.FaceUpDefence
            cardAttack = cardData.Attack
            bestBotAttack = max(Util.GetBestAttack(self.Bot), cardAttack)
            if Util.IsAllEnemyBetterThanValue(bestBotAttack, True):
                return CardPosition.FaceUpDefence
        return super().OnSelectPosition(cardId, positions)

    def OnNewTurn(self):
        self.summoned = False
        self.enemyActivateInfiniteImpermanenceFromHand = False
        self.nadirActivated = False
        self.fusionToGYFlag = False
        self.spSummoningAlbaz = False
        self.cartesiaSummonGoal = 0
        self.sanctifireSelectPositionCount = 0
        self.quemSummonFlag = 0
        self.cartesiaMaterialList.clear()
        self.brandedInRedMaterialList.clear()
        self.infiniteImpermanenceList.clear()
        self.currentNegateCardList.clear()
        self.currentDestroyCardList.clear()
        self.sendToGYThisTurn.clear()
        self.activatedCardIdList.clear()
        self.enemyPlaceThisTurn.clear()
        super().OnNewTurn()

    def OnChaining(self, player, card):
        self.Duel.LastChainTargets.clear()
        if card is None:
            return

        if player == 1:
            if card.IsCode(_CardId.InfiniteImpermanence):
                if self.enemyActivateInfiniteImpermanenceFromHand:
                    self.enemyActivateInfiniteImpermanenceFromHand = False
                else:
                    for i in range(5):
                        if self.Enemy.SpellZone[i] == card:
                            self.infiniteImpermanenceList.append(4 - i)
                            break
        super().OnChaining(player, card)

    def OnChainSolved(self, chainIndex):
        currentChain = self.Duel.GetCurrentSolvingChainInfo()
        if currentChain is not None:
            # if activation is negated, it can activate again.
            if currentChain.ActivatePlayer == 0:
                activateCheck = [CardId.NadirServant, CardId.FusionDeployment, CardId.BrandedFusion, CardId.BrandedInRed]
                if currentChain.IsActivateCode(activateCheck):
                    self.activatedCardIdList.append(currentChain.ActivateId)
            if not self.Duel.IsCurrentSolvingChainNegated():
                if currentChain.ActivatePlayer == 0 and currentChain.IsActivateCode(CardId.NadirServant):
                    self.nadirActivated = True
        self.fusionTarget = None
        self.selectedFusionMaterial.clear()
        self.sanctifireSelectPositionCount = 0

        super().OnChainSolved(chainIndex)

    def OnChainEnd(self):
        self.cartesiaSummonGoal = 0
        self.cartesiaMaterialList.clear()
        self.brandedInRedMaterialList.clear()
        self.currentNegateCardList.clear()
        self.currentDestroyCardList.clear()
        self.enemyActivateInfiniteImpermanenceFromHand = False
        self.theBystialLubellionSelecting = False
        self.albionTheShroudedDragonSelecting = False
        self.spSummoningAlbaz = False
        for idx in range(len(self.enemyPlaceThisTurn) - 1, -1, -1):
            checkTarget = self.enemyPlaceThisTurn[idx]
            if checkTarget is None or (checkTarget.Location != CardLocation.SpellZone and
                                       checkTarget.Location != CardLocation.MonsterZone):
                del self.enemyPlaceThisTurn[idx]
        if self.quemSummonFlag > 0:
            self.quemSummonFlag -= 1
        super().OnChainEnd()

    def OnMove(self, card, previousControler, previousLocation, currentControler, currentLocation):
        # WindBot's ClientCard objects move with the card: follow the tracked ones (ClientCard identity stand-in)
        if card is not None:
            for name in _TRACKED_CARD_LISTS:
                tracked = getattr(self, name)
                old = FindMovedCard(tracked, card, previousControler, previousLocation)
                if old is not None and old != card:
                    tracked[tracked.index(old)] = card
            if self.fusionTarget is not None and FindMovedCard([self.fusionTarget], card, previousControler,
                                                               previousLocation) is not None:
                self.fusionTarget = card

        if previousControler == 1:
            if card is not None:
                if card.IsCode(_CardId.InfiniteImpermanence) and previousLocation == CardLocation.Hand and \
                        currentLocation == CardLocation.SpellZone:
                    self.enemyActivateInfiniteImpermanenceFromHand = True
        if card is not None:
            if currentControler == 1 and (currentLocation == CardLocation.MonsterZone or currentLocation == CardLocation.SpellZone):
                self.enemyPlaceThisTurn.append(card)
            if currentControler == 0:
                if previousLocation == CardLocation.Grave and currentLocation != CardLocation.Grave:
                    if card in self.sendToGYThisTurn:
                        self.sendToGYThisTurn.remove(card)
                if currentLocation == CardLocation.Grave:
                    if card.HasType(CardType.Fusion):
                        self.fusionToGYFlag = True
                    self.sendToGYThisTurn.append(card)
                if currentLocation == CardLocation.MonsterZone and card is not None and card.IsCode(CardId.GuidingQuemTheVirtuous):
                    self.quemSummonFlag = 2

        super().OnMove(card, previousControler, previousLocation, currentControler, currentLocation)

    def SelectSTPlace(self, card=None, avoidImpermanence=False, avoidList=None):
        Bot = self.Bot
        if card is None:
            card = self.Card
        lst = []
        for seq in range(5):
            if Bot.SpellZone[seq] is None:
                if card is not None and card.Location == CardLocation.Hand and avoidImpermanence and \
                        seq in self.infiniteImpermanenceList:
                    continue
                if avoidList is not None and seq in avoidList:
                    continue
                lst.append(seq)
        ShuffleListInPlace(lst)
        if avoidImpermanence and any(c.IsFaceup() and not c.IsDisabled() for c in Bot.GetMonsters()):
            for seq in lst:
                enemySpell = self.Enemy.SpellZone[4 - seq]
                if enemySpell is not None and enemySpell.IsFacedown():
                    continue
                zone = 2 ** seq
                self.AI.SelectPlace(zone)
                return
        for seq in lst:
            zone = 2 ** seq
            self.AI.SelectPlace(zone)
            return
        self.AI.SelectPlace(0)

    def TheBystialLubellionSpSummon(self):
        if self.Card.Location == CardLocation.Hand:
            return False
        costTarget = self.TheBystialLubellionSpSummonCost(self.Bot.GetMonsters())
        if costTarget is not None:
            self.theBystialLubellionSelecting = True
            self.activatedCardIdList.append(self.Card.Id - 1)
            return True
        return False

    def TheBystialLubellionSpSummonCost(self, costList):
        Util, Bot = self.Util, self.Bot
        checkDict = {
            CardId.AlbionTheBrandedDragon: lambda card: all(not c.IsCode(CardId.AlbionTheBrandedDragon) for c in self.sendToGYThisTurn),
            CardId.BystialSaronir: lambda card: CardId.BystialSaronir + 1 not in self.activatedCardIdList
            and not self.DefaultCheckWhetherBotWillBeBanished(card),
            CardId.TitanikladTheAshDragon: lambda card: Util.IsTurn1OrMain2() or card.GetDefensePower() < 2500,
            CardId.AlbaLenatusTheAbyssDragon: lambda card: Util.IsTurn1OrMain2() or card.IsDisabled() or card.GetDefensePower() < 2500,
            CardId.AlbionTheShroudedDragon: lambda card: Util.IsTurn1OrMain2() or card.GetDefensePower() < 2500,
            CardId.BorreloadFuriousDragon: lambda card: card.IsDisabled() and Bot.HasInDeck(CardId.BrandedBeast, CardId.BrandedLost),
        }
        for key, func in checkDict.items():
            targetList = [card for card in costList if card.IsCode(key)]
            for target in targetList:
                if target is not None and func(target):
                    return target
        return None

    def TheBystialLubellionActivate(self):
        if self.CheckWhetherNegated(True, self.Card.Location == CardLocation.MonsterZone, CardType.Monster):
            return False
        if self.Card.Location == CardLocation.Hand:
            self.activatedCardIdList.append(self.Card.Id)
        else:
            self.activatedCardIdList.append(self.Card.Id + 1)
        return True

    def AlbionTheShroudedDragonActivate(self):
        Bot = self.Bot
        if self.CheckWhetherNegated(True, False, CardType.Monster) or self.DefaultCheckWhetherBotWillBeBanished(CardType.Spell | CardType.Trap, CardLocation.Hand | CardLocation.Deck):
            return False
        checkFlag = Bot.HasInDeck(CardId.BrandedRetribution, CardId.BrandedOpening, CardId.BrightestBlazingBrandedKing,
                                  CardId.BrandedInHighSpirits)
        if Bot.HasInGraveyard(CardId.BrandedRetribution):
            checkFlag |= Bot.HasInDeck(CardId.BrandedFusion, CardId.BrandedBeast, CardId.BrandedInRed, CardId.BrandedInWhite,
                                       CardId.BrandedLost)
        if Bot.HasInSpellZone(CardId.BrandedBeast):
            checkFlag |= Bot.HasInDeck(CardId.BrandedLost)
        if self.Card.Location == CardLocation.Grave:
            checkFlag |= Bot.HasInDeck(CardId.BrandedInWhite)
        # for abyss dragon
        if self.FallenOfAlbazSetCheck() and (self.summoned or not Bot.HasInHand([CardId.FallenOfAlbaz, CardId.BrandedInHighSpirits])):
            checkFlag |= Bot.HasInHand([CardId.BrandedBeast, CardId.BrandedInHighSpirits, CardId.BrandedInWhite, CardId.BrandedInRed,
                                        CardId.BrandedLost, CardId.BrandedOpening, CardId.BrandedRetribution,
                                        CardId.BrightestBlazingBrandedKing])

        if checkFlag:
            self.activatedCardIdList.append(self.Card.Id)
            self.albionTheShroudedDragonSelecting = True
            return True
        return False

    def BystialSaronirActivate(self):
        Bot, Enemy, Duel, Util, AI = self.Bot, self.Enemy, self.Duel, self.Util, self.AI
        Card = self.Card
        acl = self.activatedCardIdList
        cdl = self.currentDestroyCardList
        if self.CheckWhetherNegated(True, False, CardType.Monster):
            return False
        # banish & spsummon
        if Card.Location == CardLocation.Hand:
            # banish enemy target
            if Util.GetLastChainCard() is not None and Duel.LastChainPlayer == 1:
                chainTargetList = [c for c in Duel.LastChainTargets if self.CheckBystialCanBanish(c)]
                if len(chainTargetList) > 0:
                    AI.SelectCard(chainTargetList)
                    cdl.append(chainTargetList[0])
                    acl.append(Card.Id)
                    return True

            enemyChainList = _OrderByDesc([c for c in Duel.CurrentChain if c is not None and c.Controller == 1
                                           and self.CheckBystialCanBanish(c) and c not in cdl], lambda c: c.GetDefensePower())
            if len(enemyChainList) > 0:
                AI.SelectCard(enemyChainList)
                cdl.append(enemyChainList[0])
                acl.append(Card.Id)
                return True

            # banish cards with effect
            if not self.CheckShouldNoMoreSpSummon(CardLocation.Hand):
                mercourier = next((c for c in Bot.Graveyard if c is not None and c.IsCode(CardId.TriBrigadeMercourier)), None)
                if mercourier is not None and CardId.TriBrigadeMercourier + 1 not in acl:
                    AI.SelectCard(mercourier)
                    cdl.append(mercourier)
                    acl.append(Card.Id)
                    return True
                tragedy = next((c for c in Bot.Graveyard if c is not None and c.IsCode(CardId.DespianTragedy)), None)
                if tragedy is not None and CardId.DespianTragedy not in acl:
                    AI.SelectCard(tragedy)
                    cdl.append(tragedy)
                    acl.append(Card.Id)
                    return True
                if Bot.HasInGraveyard(CardId.TheBystialLubellion) and CardId.TheBystialLubellion not in acl \
                        and Duel.Player == 0 and Bot.HasInDeck(CardId.BrandedLost, CardId.BrandedBeast) \
                        and self.CurrentTiming == -1:
                    targetList = _OrderByDesc([c for c in Enemy.Graveyard if c is not None and self.CheckBystialCanBanish(c)],
                                              lambda card: card.Attack)
                    targetList.extend(_OrderBy([c for c in Bot.Graveyard if c is not None and self.CheckBystialCanBanish(c)
                                                and not c.IsCode(CardId.TheBystialLubellion)
                                                and not self.CheckWhetherShouldKeepInGrave(c)], lambda card: card.Attack))
                    if len(targetList) > 0:
                        AI.SelectCard(targetList)
                        cdl.append(targetList[0])
                        acl.append(Card.Id)
                        return True

            # defense
            if Bot.UnderAttack and Bot.BattlingMonster is None:
                targetList = _OrderByDesc([c for c in Enemy.Graveyard if self.CheckBystialCanBanish(c)], lambda c: c.GetDefensePower())
                targetList.extend(_OrderBy([c for c in Bot.Graveyard if self.CheckBystialCanBanish(c)], lambda c: c.GetDefensePower()))
                if len(targetList) > 0:
                    AI.SelectCard(targetList)
                    cdl.append(targetList[0])
                    acl.append(Card.Id)
                    return True

            # trigger beast
            if Duel.Player == 1 and (Duel.Phase == DuelPhase.Main1 or Duel.Phase == DuelPhase.Main2) \
                    and CardId.BrandedBeast not in acl \
                    and any(c is not None and c.IsCode(CardId.BrandedBeast) and (c.IsFacedown() or not c.IsDisabled())
                            for c in Bot.SpellZone) \
                    and not any(c is not None and c.IsFaceup() and c.HasSetcode(SetcodeBystial) for c in Bot.MonsterZone):
                dangerList = self.GetProblematicEnemyCardList(True, False, CardType.Trap)
                if len(dangerList) > 0:
                    targetList = _OrderByDesc([c for c in Enemy.Graveyard if self.CheckBystialCanBanish(c)], lambda c: c.GetDefensePower())
                    targetList.extend(_OrderBy([c for c in Bot.Graveyard if self.CheckBystialCanBanish(c)], lambda c: c.GetDefensePower()))
                    if len(targetList) > 0:
                        AI.SelectCard(targetList)
                        cdl.append(targetList[0])
                        acl.append(Card.Id)
                        return True

        # send to GY
        if Card.Location == CardLocation.Grave and not self.DefaultCheckWhetherBotWillBeBanished(CardType.Spell | CardType.Trap,
                                                                                           CardLocation.Deck):
            if Bot.HasInGraveyard(CardId.BrandedRetribution):
                acl.append(Card.Id + 1)
                return True
            elif Bot.HasInDeck(CardId.TheBystialLubellion, CardId.BrandedRetribution, CardId.BrandedInHighSpirits,
                               CardId.BrightestBlazingBrandedKing, CardId.BrandedOpening):
                acl.append(Card.Id + 1)
                return True
        return False

    def CheckBystialCanBanish(self, c):
        return c is not None and c.Location == CardLocation.Grave and c.IsMonster() and \
            c.HasAttribute(CardAttribute.Light | CardAttribute.Dark)

    def AluberTheJesterOfDespiaSummon(self):
        if self.CheckWhetherNegated(True, True, CardType.Monster) or not self.DefaultCheckWhetherBotCanSearch() or \
                self.Card.Id in self.activatedCardIdList:
            return False
        self.summoned = True
        return True

    def AluberTheJesterOfDespiaActivate(self):
        # search
        if self.Card.Location == CardLocation.MonsterZone:
            if self.CheckWhetherNegated(True, True, CardType.Monster):
                return False
            self.activatedCardIdList.append(self.Card.Id)
            return True
        # spsummon
        else:
            targetCardList = self.GetMonsterListForTargetNegate(True, CardType.Monster)
            lastChainCard = self.Util.GetLastChainCard()
            # chain to protect
            if lastChainCard is not None and lastChainCard.Controller == 0:
                self.AI.SelectCard(targetCardList)
                self.activatedCardIdList.append(self.Card.Id)
                return True
            if self.CheckWhetherNegated(True, False, CardType.Monster):
                return False
            self.AI.SelectCard(targetCardList)
            self.activatedCardIdList.append(self.Card.Id)
            return True

    def FallenOfAlbazSummon(self):
        if self.CheckAlbazFusion(self.Card):
            self.summoned = True
            return True
        return False

    def FallenOfAlbazSet(self):
        if self.FallenOfAlbazSetCheck():
            self.summoned = True
            return True
        return False

    def FallenOfAlbazSetCheck(self):
        Bot, Enemy = self.Bot, self.Enemy
        if not Bot.HasInExtra(CardId.AlbaLenatusTheAbyssDragon) or self.nadirActivated:
            return False
        # check dangerous dragon
        if not Bot.HasInSpellZone(CardId.BrandedLost, True, True) or Bot.GetHandCount() < 2:
            for dangerId in self.dangerousDragonIdList:
                if Enemy.HasInMonstersZone(dangerId, True, False, True):
                    return True
        # check dragon count
        dragonCount = sum(1 for c in Enemy.GetMonsters() if c is not None and c.IsFaceup()
                          and not c.IsCode(self.cannotBeFusionMaterialIdList) and c.HasRace(CardRace.Dragon))
        if dragonCount > 1:
            return True
        return False

    def CheckAlbazFusion(self, exceptCost=None, out=False):
        """Both C# overloads: out=True is CheckAlbazFusion(exceptCost, out enemyMonsterList) -> (bool, list)."""
        result, enemyMonsterList = self._CheckAlbazFusion(exceptCost)
        return (result, enemyMonsterList) if out else result

    def _CheckAlbazFusion(self, exceptCost):
        Bot, Enemy = self.Bot, self.Enemy
        cbf = self.cannotBeFusionMaterialIdList
        enemyMonsterList = None
        costHandCount = sum(1 for c in Bot.Hand if c != exceptCost)
        if costHandCount <= 0 or Enemy.GetMonsterCount() == 0:
            return False, enemyMonsterList
        if self.CheckWhetherNegated(True, True, CardType.Monster) or CardId.FallenOfAlbaz in self.activatedCardIdList \
                or self.nadirActivated:
            return False, enemyMonsterList

        def best(f):
            return next(iter(_OrderByDesc([c for c in Enemy.GetMonsters() if c.IsFaceup() and not c.IsCode(cbf) and f(c)],
                                          lambda c: c.GetDefensePower())), None)

        if not Bot.HasInMonstersZone(CardId.MirrorjadeTheIcebladeDragon, faceUp=True) and \
                not Bot.HasInSpellZone(CardId.MirrorjadeTheIcebladeDragon) and Bot.HasInExtra(CardId.MirrorjadeTheIcebladeDragon):
            target = best(lambda c: c.HasType(CardType.Fusion | CardType.Synchro | CardType.Xyz | CardType.Link))
            if target is not None:
                return True, [target]
        if Bot.HasInExtra(CardId.AlbaLenatusTheAbyssDragon):
            targetList = _OrderByDesc([c for c in Enemy.GetMonsters() if c.IsFaceup() and not c.IsCode(cbf)
                                       and c.HasRace(CardRace.Dragon)], lambda c: c.GetDefensePower())
            if len(targetList) > 0:
                return True, targetList
        if Bot.HasInExtra(CardId.AlbionTheBrandedDragon):
            target = best(lambda c: c.HasAttribute(CardAttribute.Light))
            if target is not None:
                return True, [target]
        if Bot.HasInExtra(CardId.AlbionTheSanctifireDragon):
            target = best(lambda c: c.HasAttribute(CardAttribute.Light) and c.HasRace(CardRace.SpellCaster))
            if target is not None:
                return True, [target]
        if Bot.HasInExtra(CardId.LubellionTheSearingDragon):
            target = best(lambda c: c.HasAttribute(CardAttribute.Dark))
            if costHandCount >= 2 and target is not None:
                return True, [target]
        if Bot.HasInExtra(CardId.BorreloadFuriousDragon):
            target = best(lambda c: c.HasRace(CardRace.Dragon) and c.HasAttribute(CardAttribute.Dark))
            if target is not None:
                return True, [target]
        if Bot.HasInExtra(CardId.TitanikladTheAshDragon):
            target = best(lambda c: c.Attack >= 2500)
            if target is not None:
                return True, [target]
        if Bot.HasInExtra(CardId.RindbrummTheStrikingDragon):
            target = best(lambda c: c.HasRace(CardRace.Beast | CardRace.BeastWarrior | CardRace.WindBeast))
            if target is not None:
                return True, [target]
        if Bot.HasInExtra(CardId.SprindTheIrondashDragon):
            target = best(lambda c: c is not None and c in self.enemyPlaceThisTurn and c.IsSpecialSummoned
                          and c.GetDefensePower() >= self.Util.GetBestPower(Bot))
            if target is not None:
                return True, [target]

        return False, enemyMonsterList

    def FallenOfAlbazActivate(self):
        if self.Bot.HasInExtra(CardId.AlbaLenatusTheAbyssDragon) and \
                any(c is not None and c.IsFaceup() and c.IsCode(self.dangerousDragonIdList) for c in self.Enemy.MonsterZone):
            return False
        if self.CheckAlbazFusion():
            self.activatedCardIdList.append(self.Card.Id)
            return True
        return False

    def GetAluberKittSearchCheckDict(self, cards):
        Bot, Duel = self.Bot, self.Duel

        def brandedLostCheck():
            if Duel.Player == 0 and Duel.Phase >= DuelPhase.End:
                return False
            if Bot.HasInHandOrInSpellZone(CardId.BrandedFusion) and self.BrandedFusionActivateCheck():
                return True
            if Bot.HasInHandOrInSpellZone(CardId.BrandedInWhite) and self.BrandedInWhiteActivateCheck():
                return True
            if Bot.HasInHandOrInSpellZone(CardId.BrandedInRed) and self.BrandedInRedActivateCheck() is not None:
                return True
            if not self.summoned and Bot.HasInHand(CardId.FallenOfAlbaz) and self.CheckAlbazFusion():
                return True
            if Bot.HasInMonstersZone(CardId.BlazingCartesiaTheVirtuous) or \
                    (not self.summoned and Bot.HasInHand(CardId.BlazingCartesiaTheVirtuous)):
                return True
            return False

        def brandedRetributionCheck():
            if cards is not None:
                return any(c.IsCode(CardId.BrandedRetribution) and c.Location == CardLocation.Removed and c.IsFaceup()
                           for c in cards)
            return any(c is not None and c.IsFaceup() and c.IsCode(CardId.BrandedRetribution) for c in Bot.Banished)

        return {
            CardId.BrandedFusion: lambda: self.BrandedFusionActivateCheck(),
            CardId.BrandedLost: brandedLostCheck,
            CardId.BrandedInHighSpirits: self.BrandedInHighSpiritsActivateCheck,
            CardId.BrandedInRed: lambda: (Duel.Phase == DuelPhase.End and self.nadirActivated)
            or self.BrandedInRedActivateCheck() is not None,
            CardId.BrandedInWhite: self.BrandedInWhiteActivateCheck,
            CardId.BrandedRetribution: brandedRetributionCheck,
            CardId.BrightestBlazingBrandedKing: lambda: any(c.IsFaceup() and c.IsCode(self.albazFusionMonster) for c in Bot.GetMonsters()),
            CardId.BrandedOpening: lambda: len(Bot.Hand) > 2,
        }

    def CheckSpringansKittCanAddFromGraveOrBanished(self, cardId):
        if self.Bot.HasInGraveyard(cardId):
            return True
        return any(c is not None and c.IsFaceup() and c.IsCode(cardId) for c in self.Bot.Banished)

    def GetSpringansKittPreferredAddIdWithoutSearch(self):
        for key, func in self.GetAluberKittSearchCheckDict(None).items():
            if not func():
                continue
            if self.CheckSpringansKittCanAddFromGraveOrBanished(key):
                return key
        return 0

    def SpringansKittSummon(self):
        if self.CheckWhetherNegated(True, True, CardType.Monster) or self.Card.Id + 1 in self.activatedCardIdList:
            return False
        if not self.DefaultCheckWhetherBotCanSearch() and self.GetSpringansKittPreferredAddIdWithoutSearch() == 0:
            return False
        self.summoned = True
        return True

    def SpringansKittActivate(self):
        # spsummon
        if self.Card.Location == CardLocation.Hand:
            if self.CheckWhetherNegated(True, True, CardType.Monster):
                return False
            if self.CheckShouldNoMoreSpSummon(CardLocation.Hand):
                skipFlag = not self.summoned
                skipFlag |= CardId.BrandedFusion in self.activatedCardIdList
                skipFlag |= any(c is not None and c.IsFaceup() and c.HasType(CardType.Fusion | CardType.Synchro | CardType.Xyz | CardType.Link)
                                for c in self.Bot.MonsterZone)
                if skipFlag:
                    return False
            self.activatedCardIdList.append(self.Card.Id)
            return True
        # search
        if self.Card.Location == CardLocation.MonsterZone:
            if self.CheckWhetherNegated(True, True, CardType.Monster):
                return False
            self.activatedCardIdList.append(self.Card.Id + 1)
            return True

        return False

    def GetQuemSendToGraveTargetId(self, cards=None):
        """C# GetQuemSendToGraveTargetId(out ClientCard target, IList<ClientCard> cards = null) -> (id, target)."""
        Bot = self.Bot
        target = None
        quemCheckDict = {
            CardId.BlazingCartesiaTheVirtuous: lambda: any(c.IsCode(CardId.AlbionTheBrandedDragon) for c in self.sendToGYThisTurn)
            and Bot.HasInDeck(CardId.BrandedInHighSpirits)
            and not self.DefaultCheckWhetherBotWillBeBanished(CardType.Monster, CardLocation.Deck),
            CardId.BrandedFusion: lambda: Bot.HasInGraveyard(CardId.BrandedRetribution)
            and not self.DefaultCheckWhetherBotWillBeBanished(CardType.Spell, CardLocation.Deck),
            CardId.FallenOfAlbaz: lambda: not Bot.HasInGraveyard(CardId.FallenOfAlbaz)
            and not self.DefaultCheckWhetherBotWillBeBanished(CardType.Monster, CardLocation.Deck),
            CardId.TriBrigadeMercourier: lambda: Bot.HasInHandOrInSpellZone(CardId.BrandedInWhite)
            and not self.DefaultCheckWhetherBotWillBeBanished(CardType.Monster, CardLocation.Deck),
            CardId.BrandedRetribution: lambda: not self.DefaultCheckWhetherBotWillBeBanished(CardType.Trap, CardLocation.Deck),
            CardId.BrightestBlazingBrandedKing: lambda: not any(c is not None and c.IsFaceup() and c.IsCode(self.albazFusionMonster)
                                                                and self.fusionToGYFlag for c in Bot.MonsterZone)
            and not self.DefaultCheckWhetherBotWillBeBanished(CardType.Trap, CardLocation.Deck),
            CardId.BrandedInHighSpirits: lambda: self.fusionToGYFlag
            and not self.DefaultCheckWhetherBotWillBeBanished(CardType.Spell, CardLocation.Deck),
            CardId.AlbionTheShroudedDragon: lambda: not self.DefaultCheckWhetherBotWillBeBanished(CardType.Monster, CardLocation.Deck),
        }

        for key, func in quemCheckDict.items():
            if cards is not None:
                selected = next((card for card in cards if card.IsCode(key)), None)
                if selected is None or not func():
                    continue
                target = selected
                return key, target
            if not Bot.HasInDeck(key) or not func():
                continue
            return key, target
        return 0, target

    def GuidingQuemTheVirtuousSummon(self):
        if self.CheckWhetherNegated(True, True, CardType.Monster) or self.GetQuemSendToGraveTargetId()[0] == 0:
            return False
        if self.Card.Id in self.activatedCardIdList:
            return False
        self.summoned = True
        return True

    def GuidingQuemTheVirtuousSummonForSearch(self):
        Bot = self.Bot
        if self.CheckWhetherNegated(True, True, CardType.Monster) or self.GetQuemSendToGraveTargetId()[0] == 0:
            return False
        if self.Card.Id in self.activatedCardIdList:
            return False
        if Bot.HasInGraveyard(CardId.BrandedRetribution) and Bot.HasInDeck(CardId.BrandedFusion, CardId.BrandedLost,
                                                                           CardId.BrandedInWhite, CardId.BrandedInRed):
            self.summoned = True
            return True
        if Bot.HasInGraveyard([CardId.BrandedFusion, CardId.BrandedLost, CardId.BrandedBeast]) and \
                Bot.HasInDeck(CardId.BrandedRetribution):
            self.summoned = True
            return True
        return False

    def GuidingQuemTheVirtuousActivate(self):
        Bot, Duel, Util = self.Bot, self.Duel, self.Util
        acl = self.activatedCardIdList
        desc = -1
        if self.ActivateDescription >= Util.GetStringId(CardId.GuidingQuemTheVirtuous, 0):
            desc = self.ActivateDescription - Util.GetStringId(CardId.GuidingQuemTheVirtuous, 0)

        # spsummon
        if (self.ActivateDescription == -1 and self.quemSummonFlag == 0) or \
                self.ActivateDescription == Util.GetStringId(CardId.GuidingQuemTheVirtuous, 1):
            if self.CheckWhetherNegated(True, True, CardType.Monster):
                return False

            def albazCheck(c):
                albazCanFusionFlag, materialList = self.CheckAlbazFusion(None, out=True)
                if albazCanFusionFlag and not Util.ChainContainsCard([CardId.AlbionTheBrandedDragon, CardId.LubellionTheSearingDragon]) \
                        and not self.spSummoningAlbaz:
                    albazFlag = len(materialList) > 1
                    if len(materialList) > 0:
                        material = materialList[0]
                        albazFlag |= material.HasType(CardType.Ritual | CardType.Fusion | CardType.Synchro | CardType.Xyz | CardType.Link)
                        albazFlag |= material.IsFloodgate() or material.IsOneForXyz() or \
                            Util.GetWorstBotMonster().GetDefensePower() < material.Attack
                    return albazFlag
                return False

            checkList = [
                (CardId.AlbionTheSanctifireDragon, lambda c: c.IsCanRevive() and CardId.AlbionTheSanctifireDragon not in acl),
                (CardId.MirrorjadeTheIcebladeDragon, lambda c: c.IsCanRevive()),
                (CardId.FallenOfAlbaz, albazCheck),
                (CardId.AlbionTheBrandedDragon, lambda c: c.IsCanRevive() and Bot.HasInSpellZone(CardId.BrandedBeast)
                 and any(oc is not None and oc.IsFaceup() and oc.HasSetcode(SetcodeBystial) for oc in Bot.MonsterZone)),
                (CardId.BlazingCartesiaTheVirtuous, lambda c: Duel.Player == 0 or CardId.BlazingCartesiaTheVirtuous + 1 not in acl),
                (CardId.TriBrigadeMercourier, lambda c: any(oc is not None and oc.IsFaceup() and oc.IsCode(self.albazFusionMonster)
                                                            for oc in Bot.MonsterZone)),
                (CardId.AlbionTheSanctifireDragon, lambda c: c.IsCanRevive()),
                (CardId.SpringansKitt, lambda c: True),
            ]
            for key, func in checkList:
                target = next((c for c in Bot.Graveyard if c is not None and c.IsOriginalCode(key) and func(c)), None)
                if target is not None:
                    if target.IsOriginalCode(CardId.FallenOfAlbaz):
                        self.spSummoningAlbaz = True
                    self.AI.SelectCard(target)
                    acl.append(self.Card.Id + 1)
                    return True
        # send to GY
        if (self.ActivateDescription == -1 and self.quemSummonFlag > 0) or \
                self.ActivateDescription == Util.GetStringId(CardId.GuidingQuemTheVirtuous, 0):
            if self.CheckWhetherNegated(True, True, CardType.Monster) or self.GetQuemSendToGraveTargetId()[0] == 0:
                return False
            self.quemSummonFlag = 0
            acl.append(self.Card.Id)
            return True
        return False

    def BlazingCartesiaTheVirtuousSummon(self):
        Bot = self.Bot
        acl = self.activatedCardIdList
        if self.CheckWhetherNegated(True, True, CardType.Monster):
            return False
        checkFlag = Bot.HasInHandOrInSpellZone(CardId.BrandedOpening) and CardId.AluberTheJesterOfDespia not in acl and \
            Bot.HasInDeck(CardId.AluberTheJesterOfDespia)
        checkFlag |= Bot.HasInHand(CardId.AlbionTheShroudedDragon) and CardId.AlbionTheShroudedDragon not in acl
        checkFlag |= Bot.HasInHandOrHasInMonstersZone(CardId.BystialSaronir) and CardId.BystialSaronir + 1 not in acl
        if Bot.HasInExtra(CardId.GranguignolTheDuskDragon):
            hasMaterial = any(c != self.Card and c.Attack < 2000 and c.HasAttribute(CardAttribute.Light | CardAttribute.Dark)
                              for c in Bot.Hand)
            hasMaterial |= any(c is not None and not c.IsCode(self.cannotBeFusionMaterialIdList) and c.Attack < 2000
                               and c.HasAttribute(CardAttribute.Light | CardAttribute.Dark) for c in Bot.MonsterZone)
            checkFlag |= hasMaterial

        if checkFlag:
            self.summoned = True
            return True

        return False

    def BlazingCartesiaTheVirtuousActivate(self):
        Bot, Duel, Util = self.Bot, self.Duel, self.Util
        Card = self.Card
        acl = self.activatedCardIdList
        # sp summon
        if Card.Location == CardLocation.Hand:
            if self.CheckShouldNoMoreSpSummon(CardLocation.Hand) or self.CheckWhetherNegated(True, True, CardType.Monster):
                return False
            acl.append(Card.Id)
            return True
        # fusion
        if Card.Location == CardLocation.MonsterZone:
            if self.CheckWhetherNegated(True, True, CardType.Monster):
                return False
            if any(c is not None and c.Controller == 0 and c.IsCode(CardId.BrandedInRed) for c in Duel.CurrentChain):
                return False
            materialList = [c for c in Bot.MonsterZone if c is not None and c.Attack <= 2500
                            and not c.IsCode(self.cannotBeFusionMaterialIdList)]
            materialList.extend(c for c in Bot.Hand if c.IsMonster() and not (self.CheckWhetherCanSummon() and (
                (CardId.AluberTheJesterOfDespia not in acl and c.IsCode(CardId.AluberTheJesterOfDespia))
                or (CardId.SpringansKitt not in acl and c.IsCode(CardId.SpringansKitt)))))

            # escape target
            lastCahinCard = Util.GetLastChainCard()
            if lastCahinCard is not None and Duel.LastChainPlayer == 1:
                chainTargetList = [c for c in Duel.LastChainTargets if c.Controller == 0 and c.Location == CardLocation.MonsterZone
                                   and (not c.IsCode(self.cannotBeFusionMaterialIdList) or c.Attack <= 2500)]
                if len(chainTargetList) > 0:
                    if lastCahinCard.IsCode(self.targetNegateIdList):
                        chainTargetList = [c for c in chainTargetList if c.Attack <= 2500]
                    _fusionTarget, usedMaterialList = self.BlazingCartesiaTheVirtuousFusionCheck(
                        Bot.ExtraDeck, 0, materialList, chainTargetList)

                    if _fusionTarget is not None:
                        self.cartesiaMaterialList.extend(_Intersect(usedMaterialList, chainTargetList))
                        acl.append(Card.Id + 1)
                        return True

            # fusion shrouded
            skipShroudedFlag = self.CheckWhetherCanSummon() and CardId.AluberTheJesterOfDespia not in acl and \
                Bot.HasInHand(CardId.AluberTheJesterOfDespia)
            skipShroudedFlag |= self.CheckWhetherCanSummon() and CardId.SpringansKitt not in acl and Bot.HasInHand(CardId.SpringansKitt)
            if not skipShroudedFlag:
                shrouded = next((c for c in Duel.CurrentChain if c.Controller == 0 and c.Location == CardLocation.Hand
                                 and c.IsOriginalCode(CardId.AlbionTheShroudedDragon)), None)
                if shrouded is not None:
                    _fusionTarget, usedMaterialList = self.BlazingCartesiaTheVirtuousFusionCheck(
                        Bot.ExtraDeck, 0, materialList, [shrouded])

                    if _fusionTarget is not None:
                        self.cartesiaMaterialList.extend(_Intersect(usedMaterialList, [shrouded]))
                        acl.append(Card.Id + 1)
                        return True

            shouldActivateFlag = Duel.Player == 0 and not self.CheckShouldNoMoreSpSummon(CardLocation.Extra) or Duel.Player == 1

            # summon mirrorjade
            checkMirrorJadeFlag = not (Bot.HasInMonstersZone(CardId.MirrorjadeTheIcebladeDragon, faceUp=True) or
                                       Bot.HasInSpellZone(CardId.MirrorjadeTheIcebladeDragon, faceUp=True)) and shouldActivateFlag
            if checkMirrorJadeFlag:
                _fusionTarget, _ = self.BlazingCartesiaTheVirtuousFusionCheck(
                    Bot.ExtraDeck, CardId.MirrorjadeTheIcebladeDragon, materialList, None)

                if _fusionTarget is not None:
                    self.cartesiaSummonGoal = CardId.MirrorjadeTheIcebladeDragon
                    acl.append(Card.Id + 1)
                    return True

            # summon dusk dragon
            if shouldActivateFlag and Duel.Player == 0:
                checkDict = {
                    CardId.BystialSaronir: lambda: CardId.BystialSaronir + 1 not in acl
                    and not self.DefaultCheckWhetherCardIdIsNegated(CardId.BystialSaronir),
                    CardId.DespianTragedy: lambda: CardId.DespianTragedy not in acl
                    and not self.DefaultCheckWhetherCardIdIsNegated(CardId.DespianTragedy),
                }
                for key, func in checkDict.items():
                    targetMaterial = next((c for c in materialList if c.IsCode(key)), None)
                    if targetMaterial is not None and func():
                        _fusionTarget, usedMaterialList = self.BlazingCartesiaTheVirtuousFusionCheck(
                            Bot.ExtraDeck, CardId.GranguignolTheDuskDragon, materialList, [targetMaterial])
                        if _fusionTarget is not None:
                            self.cartesiaSummonGoal = CardId.GranguignolTheDuskDragon
                            self.cartesiaMaterialList.append(targetMaterial)
                            acl.append(Card.Id + 1)
                            return True

            # summon sanctifire
            if shouldActivateFlag:
                _fusionTarget, usedMaterialList = self.BlazingCartesiaTheVirtuousFusionCheck(
                    Bot.ExtraDeck, CardId.AlbionTheSanctifireDragon, materialList, [Card])
                if _fusionTarget is not None:
                    self.cartesiaSummonGoal = CardId.AlbionTheSanctifireDragon
                    self.cartesiaMaterialList.append(Card)
                    acl.append(Card.Id + 1)
                    return True

            if shouldActivateFlag and self.GetProblematicEnemyMonster(0, True, True, CardType.Monster) is not None:
                _fusionTarget, _ = self.BlazingCartesiaTheVirtuousFusionCheck(
                    Bot.ExtraDeck, CardId.BorreloadFuriousDragon, materialList, None)

                if _fusionTarget is not None:
                    self.cartesiaSummonGoal = CardId.BorreloadFuriousDragon
                    acl.append(Card.Id + 1)
                    return True

            if shouldActivateFlag:
                checkFlag = Duel.Player == 0 and self.CurrentTiming == -1
                checkFlag |= Duel.Player == 1 and (self.CurrentTiming & hintTimingMainEnd) != 0
                if checkFlag:
                    _fusionTarget, _ = self.BlazingCartesiaTheVirtuousFusionCheck(Bot.ExtraDeck, 0, materialList, None)

                    if _fusionTarget is not None:
                        acl.append(Card.Id + 1)
                        return True
        return False

    def BlazingCartesiaTheVirtuousActivateInGrave(self):
        # recycle
        if self.Card.Location == CardLocation.Grave:
            if self.CheckWhetherNegated(True, False, CardType.Monster):
                return False
            self.activatedCardIdList.append(self.Card.Id + 2)
            return True
        return False

    def BlazingCartesiaTheVirtuousFusionCheck(self, canSummonList, mustSummonId, materialList, mustMaterialList):
        """C# out parameters returned: (fusionTarget, selectedFusionMaterialList)."""
        Bot, Enemy, Util = self.Bot, self.Enemy, self.Util
        cbf = self.cannotBeFusionMaterialIdList
        fusionTarget = None
        selectedFusionMaterialList = []

        checkDict = {
            CardId.GranguignolTheDuskDragon: [
                lambda c: c.IsCode(CardId.BlazingCartesiaTheVirtuous),
                lambda c: not c.IsCode(cbf) and c.HasAttribute(CardAttribute.Light | CardAttribute.Dark)],
            CardId.AlbionTheSanctifireDragon: [
                lambda c: c.IsCode(CardId.FallenOfAlbaz),
                lambda c: not c.IsCode(cbf) and c.HasAttribute(CardAttribute.Light) and c.HasRace(CardRace.SpellCaster)],
            CardId.MirrorjadeTheIcebladeDragon: [
                lambda c: c.IsCode(CardId.FallenOfAlbaz),
                lambda c: not c.IsCode(cbf) and c.HasType(CardType.Fusion | CardType.Synchro | CardType.Xyz | CardType.Link)],
            CardId.AlbionTheBrandedDragon: [
                lambda c: c.IsCode(CardId.FallenOfAlbaz),
                lambda c: not c.IsCode(cbf) and c.HasAttribute(CardAttribute.Light)],
            CardId.LubellionTheSearingDragon: [
                lambda c: c.IsCode(CardId.FallenOfAlbaz),
                lambda c: not c.IsCode(cbf) and c.HasAttribute(CardAttribute.Dark)],
            CardId.DespianQuaeritis: [
                lambda c: c.HasSetcode(SetcodeDespain),
                lambda c: not c.IsCode(cbf) and c.HasAttribute(CardAttribute.Light | CardAttribute.Dark)],
            CardId.BorreloadFuriousDragon: [
                lambda c: not c.IsCode(cbf) and c.HasAttribute(CardAttribute.Dark) and c.HasRace(CardRace.Dragon),
                lambda c: not c.IsCode(cbf) and c.HasAttribute(CardAttribute.Dark) and c.HasRace(CardRace.Dragon)],
        }

        def sanctifireCheck(c1, c2):
            reviveCount = sum(1 for c in Bot.Graveyard if c is not None and c.IsMonster() and c.IsCanRevive())
            reviveCount += sum(1 for c in Enemy.Graveyard if c is not None and c.IsMonster() and c.IsCanRevive())
            if not self.DefaultCheckWhetherBotWillBeBanished(CardType.Monster) or \
                    (self.CurrentTiming & hintTimingMainEnd) > 0 and Util.GetOneEnemyBetterThanValue(self.Card.GetDefensePower()) is not None \
                    and Util.GetOneEnemyBetterThanValue(3000) is None:
                reviveCount += 2
            return reviveCount >= 2

        extraCheckDict = {
            CardId.AlbionTheSanctifireDragon: sanctifireCheck,
            CardId.LubellionTheSearingDragon: lambda c1, c2: sum(1 for c in Bot.Hand if c != c1 and c != c2) > 0,
            CardId.MirrorjadeTheIcebladeDragon: lambda c1, c2: not self.DefaultCheckWhetherBotWillBeBanished(CardType.Monster, CardLocation.Extra)
            and not Bot.HasInMonstersZone(CardId.MirrorjadeTheIcebladeDragon, faceUp=True)
            and not Bot.HasInSpellZone(CardId.MirrorjadeTheIcebladeDragon, faceUp=True),
        }

        for key, funcs in checkDict.items():
            if mustSummonId > 0 and mustSummonId != key:
                continue
            currentFusionTarget = next((c for c in canSummonList if c is not None and c.IsCode(key)), None)
            if currentFusionTarget is None:
                continue
            fusionFunc1 = funcs[0]
            fusionFunc2 = funcs[1]

            if mustMaterialList is not None and len(mustMaterialList) > 0:
                for mustMaterial in mustMaterialList:
                    if not fusionFunc1(mustMaterial) and not fusionFunc2(mustMaterial):
                        continue
                    for anotherMaterial in materialList:
                        if anotherMaterial == mustMaterial:
                            continue
                        checkFlag = fusionFunc1(mustMaterial) and fusionFunc2(anotherMaterial)
                        checkFlag |= fusionFunc2(mustMaterial) and fusionFunc1(anotherMaterial)
                        extraCheckFunc = extraCheckDict.get(key)
                        checkFlag &= (extraCheckFunc is None or extraCheckFunc(mustMaterial, anotherMaterial))
                        if checkFlag:
                            fusionTarget = currentFusionTarget
                            selectedFusionMaterialList.append(mustMaterial)
                            selectedFusionMaterialList.append(anotherMaterial)
                            return fusionTarget, selectedFusionMaterialList
            else:
                for index1 in range(len(materialList) - 1):
                    material1 = materialList[index1]
                    if not fusionFunc1(material1) and not fusionFunc2(material1):
                        continue
                    for index2 in range(index1 + 1, len(materialList)):
                        material2 = materialList[index2]
                        checkFlag = fusionFunc1(material1) and fusionFunc2(material2)
                        checkFlag |= fusionFunc2(material1) and fusionFunc1(material2)
                        extraCheckFunc = extraCheckDict.get(key)
                        checkFlag &= (extraCheckFunc is None or extraCheckFunc(material1, material2))
                        if checkFlag:
                            fusionTarget = currentFusionTarget
                            # (sic) the C# adds these to the selectedFusionMaterial field, not the out list
                            self.selectedFusionMaterial.append(material1)
                            self.selectedFusionMaterial.append(material2)
                            return fusionTarget, selectedFusionMaterialList
        return fusionTarget, selectedFusionMaterialList

    def TriBrigadeMercourierActivate(self):
        # negate
        if self.Card.Location == CardLocation.Hand or self.Card.Location == CardLocation.MonsterZone:
            if self.CheckWhetherNegated(True, False, CardType.Monster) or not self.CheckLastChainShouldNegated():
                return False
            if self.Util.GetLastChainCard().Location == CardLocation.MonsterZone:
                self.currentNegateCardList.append(self.Util.GetLastChainCard())
            self.activatedCardIdList.append(self.Card.Id)
            return True
        # search
        if self.Card.Location == CardLocation.Removed:
            return False
        return False

    def TriBrigadeMercourierActivateForSearch(self):
        # negate
        if self.Card.Location == CardLocation.Hand or self.Card.Location == CardLocation.MonsterZone:
            return False
        # search
        if self.Card.Location == CardLocation.Removed:
            if self.CheckWhetherNegated(True, False, CardType.Monster):
                return False
            self.activatedCardIdList.append(self.Card.Id + 1)
            return True
        return False

    def AshBlossomActivate(self):
        if self.CheckWhetherNegated() or not self.CheckLastChainShouldNegated():
            return False
        if self.Util.GetLastChainCard().IsCode(_CardId.MaxxC):
            return False
        if self.DefaultAshBlossomAndJoyousSpring():
            lastChainCard = self.Util.GetLastChainCard()
            if lastChainCard.Location == CardLocation.MonsterZone or lastChainCard.Location == CardLocation.SpellZone:
                self.currentNegateCardList.append(self.Util.GetLastChainCard())
            return True
        return False

    def MaxxCActivate(self):
        if self.CheckWhetherNegated(True) or self.Duel.LastChainPlayer == 0:
            return False
        return self.DefaultMaxxC()

    def DespianTragedyActivate(self):
        Bot, Duel = self.Bot, self.Duel
        # search
        if self.ActivateDescription != self.Util.GetStringId(self.Card.Id, 1):
            if self.CheckWhetherNegated(True, False, CardType.Monster):
                return False
            self.activatedCardIdList.append(self.Card.Id)
            return True
        # set
        else:
            if self.CheckWhetherNegated(True, False, CardType.Trap):
                return False

            def brandedLostCheck():
                if Duel.Player == 0 and Duel.Phase >= DuelPhase.End:
                    return False
                if Bot.HasInHandOrInSpellZone(CardId.BrandedFusion) and self.BrandedFusionActivateCheck():
                    return True
                if Bot.HasInHandOrInSpellZone(CardId.BrandedInWhite) and self.BrandedInWhiteActivateCheck():
                    return True
                if Bot.HasInHandOrInSpellZone(CardId.BrandedInRed) and self.BrandedInRedActivateCheck() is not None:
                    return True
                if not self.summoned and Bot.HasInHand(CardId.FallenOfAlbaz) and self.CheckAlbazFusion():
                    return True
                if Bot.HasInMonstersZone(CardId.BlazingCartesiaTheVirtuous) or \
                        (not self.summoned and Bot.HasInHand(CardId.BlazingCartesiaTheVirtuous)):
                    return True
                return False
            checkDict = {
                CardId.BrandedFusion: lambda: self.BrandedFusionActivateCheck(),
                CardId.BrandedLost: brandedLostCheck,
                CardId.BrandedInHighSpirits: self.BrandedInHighSpiritsActivateCheck,
                CardId.BrandedInRed: lambda: self.BrandedInRedActivateCheck() is not None,
                CardId.BrandedInWhite: self.BrandedInWhiteActivateCheck,
                CardId.BrightestBlazingBrandedKing: lambda: any(c.IsFaceup() and c.IsCode(self.albazFusionMonster)
                                                                for c in Bot.GetMonsters()),
                CardId.BrandedOpening: lambda: len(Bot.Hand) > 2 and CardId.BrandedOpening not in self.activatedCardIdList,
            }
            for key, func in checkDict.items():
                target = next((card for card in Bot.Graveyard if card.IsCode(key)), None)
                if target is not None and func():
                    self.activatedCardIdList.append(self.Card.Id)
                    self.AI.SelectCard(target)
                    self.SelectSTPlace(target, True)
                    return True
        return False

    def DespianTragedySet(self):
        if any(c is not None and c.HasType(CardType.Spell | CardType.Trap) and c.HasSetcode(SetcodeBranded)
               for c in self.Bot.Graveyard):
            self.summoned = True
            return True

        return False

    def NadirServantActivate(self):
        if self.CheckWhetherNegated(True, True, CardType.Spell) or \
                self.DefaultCheckWhetherBotWillBeBanished(CardType.Monster, CardLocation.Extra):
            return False
        checkResult, _ = self.NadirServantActivateCheck(None, False)
        if checkResult:
            self.SelectSTPlace(self.Card, True)
            return True
        return False

    def NadirServantActivateCheck(self, cards, force):
        """C# out ClientCard target returned: (result, target)."""
        Bot = self.Bot
        checkDict = {
            CardId.AlbionTheBrandedDragon: lambda: not any(c.IsCode(CardId.AlbionTheBrandedDragon) for c in self.sendToGYThisTurn),
            CardId.DespianLuluwalilith: lambda: Bot.HasInDeck(CardId.BlazingCartesiaTheVirtuous, CardId.GuidingQuemTheVirtuous),
            CardId.TitanikladTheAshDragon: lambda: Bot.HasInDeck(CardId.GuidingQuemTheVirtuous),
            CardId.SprindTheIrondashDragon: lambda: Bot.HasInDeck(CardId.SpringansKitt),
            CardId.RindbrummTheStrikingDragon: lambda: any(c is not None and c.IsOriginalCode(CardId.FallenOfAlbaz) for c in Bot.Graveyard),
            CardId.AlbaLenatusTheAbyssDragon: lambda: force and Bot.HasInDeck(CardId.FusionDeployment, CardId.BrandedFusion),
            CardId.GranguignolTheDuskDragon: lambda: force,
        }

        for key, func in checkDict.items():
            if cards is None:
                if Bot.HasInExtra(key) and func():
                    return True, None
            else:
                tg = next((c for c in cards if c.IsOriginalCode(key)), None)
                if tg is not None and func():
                    return True, tg

        return False, None

    def FusionDeploymentActivate(self):
        if self.CheckWhetherNegated(True, True, CardType.Spell):
            return False
        if self.FusionDeploymentSpSummonTarget() > 0 and not self.Bot.HasInHand(CardId.BrandedLost):
            self.SelectSTPlace(self.Card, True)
            return True

        return False

    def FusionDeploymentSpSummonTarget(self):
        Bot = self.Bot
        if Bot.HasInDeck(CardId.FallenOfAlbaz) and self.CheckAlbazFusion(self.Card) and \
                self.GetProblematicEnemyMonster(0, False, False, CardType.Monster) is not None:
            return CardId.FallenOfAlbaz
        if Bot.HasInDeck(CardId.BlazingCartesiaTheVirtuous) and Bot.HasInExtra(CardId.GranguignolTheDuskDragon):
            if any(c.IsMonster() and c.HasAttribute(CardAttribute.Light | CardAttribute.Dark) for c in Bot.Hand) \
                    or any(c.IsMonster() and c.HasAttribute(CardAttribute.Light | CardAttribute.Dark)
                           and not c.IsCode(self.cannotBeFusionMaterialIdList) for c in Bot.GetMonsters()):
                return CardId.BlazingCartesiaTheVirtuous
        if Bot.HasInDeck(CardId.FallenOfAlbaz) and self.CheckAlbazFusion(self.Card):
            return CardId.FallenOfAlbaz
        return 0

    def BrandedInWhiteActivate(self):
        if self.Card.Location == CardLocation.Grave:
            if self.CheckWhetherNegated(True, False, CardType.Spell):
                return False
            self.activatedCardIdList.append(self.Card.Id + 1)
            self.SelectSTPlace(self.Card)
            return True
        else:
            if self._BrandedInWhiteActivateCheck(True):
                self.activatedCardIdList.append(self.Card.Id)
                self.SelectSTPlace(self.Card, True)
                return True
        return False

    def BrandedInWhiteActivateCheck(self):
        return self._BrandedInWhiteActivateCheck(False)

    def _BrandedInWhiteActivateCheck(self, activate=False):
        if self.CheckWhetherNegated(True, True, CardType.Spell) or CardId.BrandedInWhite in self.activatedCardIdList or \
                self.nadirActivated:
            return False
        if self.CheckShouldNoMoreSpSummon(CardLocation.Extra) and \
                any(c is not None and c.GetDefensePower() >= 2000 for c in self.Bot.MonsterZone):
            return False
        if self.BrandedInWhiteFusionTarget(self.Bot.ExtraDeck)[0] > 0:
            return True

        return False

    def BrandedInWhiteFusionTarget(self, cards):
        """C# out ClientCard target returned: (id, target)."""
        Bot, Enemy, Duel, Util = self.Bot, self.Enemy, self.Duel, self.Util
        cbf = self.cannotBeFusionMaterialIdList
        keep = self.CheckWhetherShouldKeepInGrave

        def mirrorjadeCheck():
            if Bot.HasInMonstersZone(CardId.MirrorjadeTheIcebladeDragon, faceUp=True) or \
                    Bot.HasInSpellZone(CardId.MirrorjadeTheIcebladeDragon, faceUp=True):
                return False
            albazFlag = any(c.IsCode(CardId.FallenOfAlbaz) for c in Bot.Graveyard)
            albazFlag |= any(c is not None and c.IsOriginalCode(CardId.FallenOfAlbaz) for c in Bot.MonsterZone)
            albazFlag |= any(c.IsOriginalCode(CardId.FallenOfAlbaz) for c in Bot.Hand)
            if not albazFlag:
                return False

            checkFlag = any(c is not None and c not in self.sendToGYThisTurn and not c.IsCode(cbf)
                            and c.HasType(CardType.Fusion | CardType.Synchro | CardType.Xyz | CardType.Link) for c in Bot.Graveyard)
            checkFlag |= any(c is not None and not c.IsCode(cbf)
                             and (c.IsCode(self.albazFusionMonster) or c.IsCode(CardId.GranguignolTheDuskDragon)) for c in Bot.MonsterZone)
            return checkFlag

        def borreloadCheck():
            if Enemy.GetMonsterCount() + Enemy.GetSpellCount() > 0:
                darkDragonList = [c for c in Bot.Hand if c is not None and c.IsMonster() and c.HasAttribute(CardAttribute.Dark)
                                  and c.HasRace(CardRace.Dragon)]
                darkDragonList.extend(c for c in Bot.MonsterZone if c is not None and c.IsMonster() and c.HasAttribute(CardAttribute.Dark)
                                      and c.HasRace(CardRace.Dragon) and not c.IsCode(cbf))
                graveDarkDragonList = [c for c in Bot.Graveyard if c.HasRace(CardRace.Dragon) and c.HasAttribute(CardAttribute.Dark)
                                       and not c.IsCode(cbf) and not keep(c)]

                hasAlbaz = any(c.IsCode(CardId.FallenOfAlbaz) for c in darkDragonList) or \
                    any(c.IsCode(CardId.FallenOfAlbaz) for c in graveDarkDragonList)
                darkDragonCount = len(darkDragonList)
                if hasAlbaz:
                    darkDragonCount += len(graveDarkDragonList)
                return darkDragonCount >= 2
            return False

        def chimeraCheck():
            if self.CheckWhetherNegated(True, True, CardType.Monster) or self.DefaultCheckWhetherCardIdIsNegated(CardId.GuardianChimera):
                return False
            enemyCardCount = Enemy.GetMonsterCount() + Enemy.GetSpellCount()
            if enemyCardCount == 0:
                return False

            return len(self.ChimeraFusionMaterialList()) > 0

        def checkMaterialListOf():
            checkMaterialList = _OrderBy([c for c in Bot.Graveyard if c is not None and c.IsMonster()], lambda c: c.GetDefensePower())
            checkMaterialList.extend(_OrderBy(Bot.GetMonsters(), lambda c: c.GetDefensePower()))
            checkMaterialList.extend(Bot.Hand)
            return checkMaterialList

        def lubellionCheck():
            if CardId.LubellionTheSearingDragon in self.activatedCardIdList \
                    or self.DefaultCheckWhetherCardIdIsNegated(CardId.LubellionTheSearingDragon) \
                    or self.CheckWhetherNegated(True, True, CardType.Monster):
                return False
            checkMaterialList = checkMaterialListOf()
            albaz = next(iter(_OrderBy([c for c in checkMaterialList if c.IsCode(CardId.FallenOfAlbaz)],
                                       lambda c: c.GetDefensePower())), None)
            darkMonster = next((c for c in checkMaterialList if c != albaz and c.HasAttribute(CardAttribute.Dark)), None)
            if albaz is None or darkMonster is None:
                return False
            if sum(1 for c in Bot.Hand if c != albaz and c != darkMonster and not c.IsCode(CardId.BrandedInWhite)) == 0:
                return False

            return True

        def sanctifireCheck():
            checkMaterialList = checkMaterialListOf()
            albaz = next((c for c in checkMaterialList if c.IsCode(CardId.FallenOfAlbaz)), None)
            lightSpellcaster = next((c for c in checkMaterialList if c.HasRace(CardRace.SpellCaster)
                                     and c.HasAttribute(CardAttribute.Light)), None)
            if albaz is None or lightSpellcaster is None:
                return False

            remainMonsterCount = len(Enemy.GetGraveyardMonsters())
            remainMonsterCount += sum(1 for c in Bot.Graveyard if c.IsMonster() and c != albaz and c != lightSpellcaster)
            remainMonsterCount += 1 if Bot.HasInHand(_CardId.MaxxC) else 0
            return remainMonsterCount >= 2

        def rindbrummCheck():
            if not Bot.HasInGraveyard(CardId.TriBrigadeMercourier):
                return False
            albazCheck = Bot.HasInHandOrHasInMonstersZone(CardId.FallenOfAlbaz)
            albazCheck |= Bot.HasInGraveyard(CardId.FallenOfAlbaz)
            return albazCheck

        def quaeritisCheck():
            checkFlag = any(c is not None and c.IsFaceup() and c.Attack >= 2500 and not (c.HasType(CardType.Fusion) and c.Level >= 8)
                            for c in Enemy.MonsterZone)
            if checkFlag:
                despianInGrave = next(iter(_OrderBy([c for c in Bot.Graveyard if c is not None and c.HasSetcode(SetcodeDespain)
                                                     and not keep(c)], lambda c: c.GetDefensePower())), None)
                if despianInGrave is not None:
                    albazCheck = Bot.HasInHandOrHasInMonstersZone(CardId.FallenOfAlbaz)
                    albazCheck |= Bot.HasInGraveyard(CardId.FallenOfAlbaz)
                    return albazCheck
                fusionMaterialList = _OrderBy([c for c in Bot.Hand if c.IsMonster()], lambda c: c.GetDefensePower())
                fusionMaterialList.extend(_OrderBy([c for c in Bot.MonsterZone if c is not None and not c.IsCode(cbf)],
                                                   lambda c: c.GetDefensePower()))
                despian = next((c for c in fusionMaterialList if c.HasSetcode(SetcodeDespain)), None)
                if despian is not None:
                    checkFlag = any(c != despian and c.HasAttribute(CardAttribute.Light | CardAttribute.Dark) for c in fusionMaterialList)
                    checkFlag |= Bot.HasInGraveyard(CardId.FallenOfAlbaz)
                    return checkFlag

            return False

        def titanikladCheck():
            checkMaterialList = checkMaterialListOf()
            albaz = next(iter(_OrderBy([c for c in checkMaterialList if c.IsCode(CardId.FallenOfAlbaz)],
                                       lambda c: c.GetDefensePower())), None)

            for material in checkMaterialList:
                if material != albaz and material.IsMonster() and material.Attack >= 2500 and not material.IsCode(cbf) \
                        and not Util.IsTurn1OrMain2():
                    checkFlag = Enemy.GetMonsterCount() == 0 and not keep(material) and \
                        (material.IsFacedown() or material.Location != CardLocation.MonsterZone)

                    expectedAttack = 2900 + material.Level * 100
                    botBestPower = Util.GetBestPower(Bot)
                    beforeBetterCount = sum(1 for c in Enemy.MonsterZone if c is not None and c.GetDefensePower() >= botBestPower)
                    afterBetterCount = sum(1 for c in Enemy.MonsterZone if c is not None and c.GetDefensePower() >= expectedAttack)
                    checkFlag |= afterBetterCount < beforeBetterCount

                    return checkFlag
            return False

        def albaLenatusCheck():
            if Util.GetOneEnemyBetterThanMyBest() is None and Duel.MainPhase.CanBattlePhase:
                albaz = next((c for c in Bot.Graveyard if c is not None and c.IsOriginalCode(CardId.FallenOfAlbaz)), None)
                if albaz is None:
                    albaz = next((c for c in Bot.Graveyard if c is not None and c.IsCode(CardId.FallenOfAlbaz)), None)
                if albaz is None:
                    return False
                for material in Bot.Graveyard:
                    if material is not None and material != albaz and material.IsMonster() and material.HasRace(CardRace.Dragon) \
                            and not material.IsCode(cbf):
                        return True
            return False

        checkDict = {
            CardId.MirrorjadeTheIcebladeDragon: mirrorjadeCheck,
            CardId.BorreloadFuriousDragon: borreloadCheck,
            CardId.GuardianChimera: chimeraCheck,
            CardId.LubellionTheSearingDragon: lubellionCheck,
            CardId.AlbionTheSanctifireDragon: sanctifireCheck,
            CardId.RindbrummTheStrikingDragon: rindbrummCheck,
            CardId.DespianQuaeritis: quaeritisCheck,
            CardId.TitanikladTheAshDragon: titanikladCheck,
            CardId.AlbaLenatusTheAbyssDragon: albaLenatusCheck,
        }

        for key, func in checkDict.items():
            target = next((card for card in cards if card.IsCode(key)), None)
            if target is not None and func():
                return key, target

        return 0, None

    def ChimeraFusionMaterialList(self, dragonCheck=True):
        Bot, Enemy = self.Bot, self.Enemy
        enemyCardCount = Enemy.GetMonsterCount() + Enemy.GetSpellCount()

        fieldMonsterList = _OrderBy([c for c in Bot.MonsterZone if c is not None and c.GetDefensePower() <= 2500
                                     and not c.IsCode(self.cannotBeFusionMaterialIdList)], lambda c: c.GetDefensePower())
        handMonsterList = _OrderBy([c for c in Bot.Hand if c.IsMonster()], lambda c: c.GetDefensePower())
        # 2 monsters on field + 1 monster in hand
        if enemyCardCount >= 2 and len(fieldMonsterList) >= 2:
            if len(fieldMonsterList) < 2 or len(handMonsterList) < 1:
                return []
            for handMonster in handMonsterList:
                for fieldIndex1 in range(len(fieldMonsterList) - 1):
                    fieldMonster1 = fieldMonsterList[fieldIndex1]
                    if fieldMonster1.IsCode(handMonster.Id) or handMonster.IsCode(fieldMonster1.Id):
                        continue
                    for fieldIndex2 in range(fieldIndex1 + 1, len(fieldMonsterList)):
                        fieldMonster2 = fieldMonsterList[fieldIndex2]
                        if fieldMonster2.IsCode(handMonster.Id) or handMonster.IsCode(fieldMonster2.Id):
                            continue
                        if fieldMonster2.IsCode(fieldMonster1.Id) or fieldMonster1.IsCode(fieldMonster2.Id):
                            continue

                        materialList = [handMonster, fieldMonster1, fieldMonster2]
                        checkFlag = dragonCheck and any(c.HasRace(CardRace.Dragon) for c in materialList)
                        if checkFlag:
                            return materialList
        # 1 monster on field + 2 monsters in hand
        if enemyCardCount == 1 or len(fieldMonsterList) == 1:
            if len(fieldMonsterList) < 1 or len(handMonsterList) < 2:
                return []
            for fieldMonster in fieldMonsterList:
                for handIndex1 in range(len(handMonsterList) - 1):
                    handMonster1 = handMonsterList[handIndex1]
                    if handMonster1.IsCode(fieldMonster.Id) or fieldMonster.IsCode(handMonster1.Id):
                        continue
                    for handIndex2 in range(handIndex1 + 1, len(handMonsterList)):
                        handMonster2 = handMonsterList[handIndex2]
                        if handMonster2.IsCode(fieldMonster.Id) or fieldMonster.IsCode(handMonster2.Id):
                            continue
                        if handMonster2.IsCode(handMonster1.Id) or handMonster1.IsCode(handMonster2.Id):
                            continue

                        materialList = [fieldMonster, handMonster1, handMonster2]
                        checkFlag = dragonCheck and any(c.HasRace(CardRace.Dragon) for c in materialList)
                        if checkFlag:
                            return materialList

        return []

    def BrandedFusionActivate(self):
        if self.BrandedFusionActivateCheck():
            self.SelectSTPlace(self.Card, True)
            return True
        return False

    def BrandedFusionActivateCheck(self, endPhaseCheck=True):
        if self.CheckWhetherNegated(True, True, CardType.Spell) or CardId.BrandedFusion in self.activatedCardIdList:
            return False
        if not self.Bot.HasInHandOrHasInMonstersZone(CardId.FallenOfAlbaz) and not self.Bot.HasInDeck(CardId.FallenOfAlbaz):
            return False
        if endPhaseCheck and self.Duel.Phase >= DuelPhase.End:
            return False
        return True

    def GoldSarcophagusActivate(self):
        if self.CheckWhetherNegated(True, True, CardType.Spell):
            return False
        if self.GoldSarcophagusTarget(None)[0] > 0:
            self.SelectSTPlace(self.Card, True)
            return True
        return False

    def GoldSarcophagusTarget(self, cards):
        """C# out ClientCard target returned: (id, target)."""
        acl = self.activatedCardIdList
        checkDict = {
            CardId.DespianTragedy: lambda: CardId.DespianTragedy not in acl
            and not self.DefaultCheckWhetherCardIdIsNegated(CardId.DespianTragedy),
            CardId.TriBrigadeMercourier: lambda: CardId.TriBrigadeMercourier + 1 not in acl
            and not self.DefaultCheckWhetherCardIdIsNegated(CardId.TriBrigadeMercourier),
        }
        for key, func in checkDict.items():
            cardId = key
            if func():
                if cards is not None:
                    target = next((card for card in cards if card.IsCode(key)), None)
                    if target is not None and func():
                        return cardId, target
                elif self.Bot.HasInDeck(cardId):
                    return cardId, None

        return 0, None

    def FoolishBurialActivate(self):
        if self.CheckWhetherNegated(True, True, CardType.Spell) or \
                self.DefaultCheckWhetherBotWillBeBanished(CardType.Monster, CardLocation.Deck):
            return False
        if self.FoolishBurialTarget(None)[0] > 0:
            self.SelectSTPlace(self.Card, True)
            return True
        return False

    def FoolishBurialTarget(self, cards):
        """C# out ClientCard target returned: (id, target)."""
        Bot = self.Bot
        acl = self.activatedCardIdList
        # tragedy
        if CardId.DespianTragedy not in acl and not self.DefaultCheckWhetherCardIdIsNegated(CardId.DespianTragedy):
            if cards is not None:
                target = next((c for c in cards if c.IsCode(CardId.DespianTragedy)), None)
                if target is not None:
                    return CardId.DespianTragedy, target
            else:
                if Bot.HasInDeck(CardId.DespianTragedy):
                    return CardId.DespianTragedy, None

        if self.DefaultCheckWhetherBotWillBeBanished(CardType.Monster, CardLocation.Deck):
            # For Tri Brigade Mercourier
            if CardId.TriBrigadeMercourier + 1 not in acl and not self.DefaultCheckWhetherCardIdIsNegated(CardId.TriBrigadeMercourier):
                if cards is not None:
                    target = next((c for c in cards if c.IsCode(CardId.TriBrigadeMercourier)), None)
                    if target is not None:
                        return CardId.TriBrigadeMercourier, target
                else:
                    if Bot.HasInDeck(CardId.TriBrigadeMercourier):
                        return CardId.TriBrigadeMercourier, None

            # otherwise return null since monster will be banished
            return 0, None

        # send to GY check
        sendToGYFlag = Bot.HasInDeck(CardId.BrandedRetribution)
        sendToGYFlag |= Bot.HasInGraveyard(CardId.BrandedRetribution) and Bot.HasInDeck(CardId.BrandedFusion)
        if sendToGYFlag:
            checkDict = {
                CardId.BystialSaronir: lambda: CardId.BystialSaronir + 1 not in acl
                and not self.DefaultCheckWhetherCardIdIsNegated(CardId.BystialSaronir),
                CardId.AlbionTheShroudedDragon: lambda: CardId.AlbionTheShroudedDragon not in acl
                and not self.DefaultCheckWhetherCardIdIsNegated(CardId.AlbionTheShroudedDragon),
            }

            for key, func in checkDict.items():
                cardId = key
                if func():
                    if cards is not None:
                        target = next((card for card in cards if card.IsCode(key)), None)
                        if target is not None and func():
                            return cardId, target
                    elif Bot.HasInDeck(cardId):
                        return cardId, None

        # albaz
        if not Bot.HasInGraveyard(CardId.FallenOfAlbaz):
            albazCheckFlag = Bot.HasInHand([CardId.BrandedInRed, CardId.BrandedInWhite])
            albazCheckFlag |= Bot.HasInHand(CardId.BlazingCartesiaTheVirtuous) and \
                sum(1 for c in Bot.MonsterZone if c is not None and c.Sequence < 5) < 5
            if albazCheckFlag:
                albazCountCheck = 2 if Bot.HasInHandOrInSpellZone(CardId.BrandedFusion) else 1
                if cards is not None:
                    albazList = [c for c in cards if c.IsCode(CardId.FallenOfAlbaz)]
                    if len(albazList) >= albazCountCheck:
                        return CardId.FallenOfAlbaz, albazList[0]
                else:
                    if Bot.GetCardCountInDeck(CardId.FallenOfAlbaz) >= albazCountCheck:
                        return CardId.FallenOfAlbaz, None

        return 0, None

    def CalledbytheGraveActivate(self):
        Enemy, Duel, Util, AI = self.Enemy, self.Duel, self.Util, self.AI
        if self.CheckWhetherNegated() or not self.CheckLastChainShouldNegated():
            return False
        if self.CheckAtAdvantage() and Duel.LastChainPlayer == 1 and Util.GetLastChainCard().IsCode(_CardId.MaxxC):
            return False
        if Duel.LastChainPlayer == 1:
            # negate
            if Util.GetLastChainCard().IsMonster():
                code = Util.GetLastChainCard().GetOriginCode()
                if code == 0:
                    return False
                if self.DefaultCheckWhetherCardIdIsNegated(code):
                    return False
                if Util.GetLastChainCard().IsCode(_CardId.MaxxC) and self.CheckAtAdvantage():
                    return False
                graveTarget = GetFirstMatchingCard(Enemy.Graveyard, lambda card: card.IsMonster() and card.GetOriginCode() == code)
                if graveTarget is not None:
                    if not (self.Card.Location == CardLocation.SpellZone):
                        self.SelectSTPlace(None, True)
                    AI.SelectCard(graveTarget)
                    self.currentDestroyCardList.append(graveTarget)
                    return True

            # banish target
            for graveCard in Enemy.Graveyard:
                if graveCard in Duel.ChainTargets and graveCard.IsMonster():
                    if not (self.Card.Location == CardLocation.SpellZone):
                        self.SelectSTPlace(None, True)
                    code = graveCard.Id
                    AI.SelectCard(graveCard)
                    self.currentDestroyCardList.append(graveCard)
                    return True

            # become targets
            if self.Card in Duel.ChainTargets:
                enemyMonsters = GetMatchingCards(Enemy.Graveyard, lambda card: card.IsMonster())
                if len(enemyMonsters) > 0:
                    enemyMonsters.sort(key=CompareCardAttack)
                    enemyMonsters.reverse()
                    code = enemyMonsters[0].Id
                    AI.SelectCard(code)
                    self.currentDestroyCardList.append(enemyMonsters[0])
                    return True

        # avoid danger monster in grave
        if Duel.LastChainPlayer == 1:
            return False
        targets = self.GetDangerousCardinEnemyGrave(True)
        if len(targets) > 0:
            code = targets[0].Id
            if not (self.Card.Location == CardLocation.SpellZone):
                self.SelectSTPlace(None, True)
            AI.SelectCard(code)
            self.currentDestroyCardList.append(targets[0])
            return True

        return False

    def BrandedInHighSpiritsActivate(self):
        if self.Card.Location == CardLocation.Grave:
            if self.CheckWhetherNegated(True, False, CardType.Spell):
                return False
            self.activatedCardIdList.append(self.Card.Id)
            return True
        else:
            if self.BrandedInHighSpiritsActivateCheck():
                self.activatedCardIdList.append(self.Card.Id)
                self.SelectSTPlace(self.Card, True)
                return True
        return False

    def BrandedInHighSpiritsActivateCheck(self):
        Bot, Duel = self.Bot, self.Duel
        acl = self.activatedCardIdList
        lubellionCheck = Bot.HasInHand(CardId.TheBystialLubellion) and Bot.HasInDeck(CardId.BystialSaronir) and \
            CardId.TheBystialLubellion not in acl and Duel.Player == 0 and \
            (Duel.Phase <= DuelPhase.Main1 or Duel.Phase == DuelPhase.Main2) and \
            not self.DefaultCheckWhetherBotWillBeBanished(CardType.Monster, CardLocation.Extra | CardLocation.Hand)

        if self.CheckWhetherNegated(True, True, CardType.Spell) or CardId.BrandedInHighSpirits in acl or \
                self.DefaultCheckWhetherBotWillBeBanished(CardType.Monster, CardLocation.Extra | CardLocation.Hand):
            return False
        checkDict = {
            CardId.AlbionTheBrandedDragon: lambda: not any(c.IsCode(CardId.AlbionTheBrandedDragon) for c in self.sendToGYThisTurn)
            and not lubellionCheck and any(self.BrandedInHighSpiritDiscardDragonCheck(c) for c in Bot.Hand),
            CardId.TitanikladTheAshDragon: lambda: not any(c.IsCode(CardId.TitanikladTheAshDragon) for c in self.sendToGYThisTurn)
            and not lubellionCheck and any(self.BrandedInHighSpiritDiscardDragonCheck(c) for c in Bot.Hand)
            and Bot.HasInDeck(CardId.GuidingQuemTheVirtuous, CardId.FallenOfAlbaz),
            CardId.GranguignolTheDuskDragon: lambda: any(c.HasRace(CardRace.SpellCaster) and not (
                self.CheckWhetherCanSummon() and c.IsOriginalCode(CardId.GuidingQuemTheVirtuous)) for c in Bot.Hand),
            CardId.RindbrummTheStrikingDragon: lambda: any(c.HasRace(CardRace.WindBeast) and (
                not c.IsCode(CardId.TriBrigadeMercourier) or not any(c2 is not None and c2.IsFaceup() and c2.IsCode(self.albazFusionMonster)
                                                                     for c2 in Bot.MonsterZone)) for c in Bot.Hand),
        }

        for key, func in checkDict.items():
            if Bot.HasInExtra(key) and func():
                return True
        return False

    def BrandedInHighSpiritDiscardDragonCheck(self, card):
        Duel = self.Duel
        if not card.HasRace(CardRace.Dragon):
            return False
        if Duel.Player == 0 and (Duel.Phase <= DuelPhase.Main1 or Duel.Phase == DuelPhase.Main2):
            if card.IsOriginalCode(CardId.AlbionTheShroudedDragon) and CardId.AlbionTheShroudedDragon not in self.activatedCardIdList:
                return False
            if card.IsOriginalCode(CardId.TheBystialLubellion) and CardId.TheBystialLubellion not in self.activatedCardIdList and \
                    self.Bot.HasInDeck(CardId.BystialSaronir):
                return False

        return True

    def BrandedOpeningActivate(self):
        Bot, Duel = self.Bot, self.Duel
        acl = self.activatedCardIdList
        if self.CheckWhetherNegated(True, True, CardType.Spell):
            return False
        if Duel.Player == 0:
            if Bot.HasInHand(CardId.AlbionTheShroudedDragon) and \
                    not self.DefaultCheckWhetherBotWillBeBanished(CardType.Monster, CardLocation.Hand) and \
                    CardId.AlbionTheShroudedDragon not in acl:
                return False
            canCallCartesia = Bot.HasInHand(CardId.BlazingCartesiaTheVirtuous) and not self.summoned
            canCallCartesia |= CardId.FusionDeployment not in acl and Bot.HasInHandOrInSpellZone(CardId.FusionDeployment) \
                and not self.CheckShouldNoMoreSpSummon(CardLocation.Deck) and Bot.HasInExtra(CardId.GranguignolTheDuskDragon) \
                and Bot.HasInDeck(CardId.BlazingCartesiaTheVirtuous)
            if canCallCartesia:
                return False
        goal = Bot.HasInDeck(CardId.AluberTheJesterOfDespia) and CardId.AluberTheJesterOfDespia not in acl and \
            self.DefaultCheckWhetherBotCanSearch()
        goal |= Bot.HasInDeck(CardId.GuidingQuemTheVirtuous)
        if goal:
            self.SelectSTPlace(self.Card, True)
            acl.append(self.Card.Id)
            return True
        return False

    def CrossoutDesignatorActivate(self):
        if self.CheckWhetherNegated() or not self.CheckLastChainShouldNegated():
            return False
        # negate
        if self.Duel.LastChainPlayer == 1 and self.Util.GetLastChainCard() is not None:
            code = self.Util.GetLastChainCard().Id
            alias = self.Util.GetLastChainCard().Alias
            if alias != 0 and alias - code < 10:
                code = alias
            if code == 0:
                return False
            if self.DefaultCheckWhetherCardIdIsNegated(code):
                return False
            if self.Bot.HasInDeck(code):
                if not (self.Card.Location == CardLocation.SpellZone):
                    self.SelectSTPlace(None, True)
                self.AI.SelectAnnounceID(code)
                return True
        return False

    def BrandedInRedActivate(self):
        targetCard = self.BrandedInRedActivateCheck(True)
        if targetCard is not None:
            self.AI.SelectCard(targetCard)
            self.SelectSTPlace(self.Card, True)
            return True
        return False

    def BrandedInRedActivateCheck(self, updateMaterialList=False):
        Bot, Duel, Util = self.Bot, self.Duel, self.Util
        acl = self.activatedCardIdList
        if self.CheckWhetherNegated(True, True, CardType.Spell) or CardId.BrandedInRed in acl:
            return None
        if any(c is not None and c.Controller == 0 and c.IsCode(CardId.BlazingCartesiaTheVirtuous) for c in Duel.CurrentChain):
            return None
        if any(c is not None and c.Controller == 0 and c.IsCode(CardId.AlbionTheBrandedDragon) for c in Duel.CurrentChain) \
                and not Util.ChainContainPlayer(1):
            return None
        if self.nadirActivated:
            return None

        materialList = [c for c in Bot.MonsterZone if c is not None and c.Attack <= 2500
                        and not c.IsCode(self.cannotBeFusionMaterialIdList)]
        materialList.extend(c for c in Bot.Hand if c.IsMonster() and not (self.CheckWhetherCanSummon() and (
            (CardId.AluberTheJesterOfDespia not in acl and c.IsCode(CardId.AluberTheJesterOfDespia))
            or (CardId.SpringansKitt not in acl and c.IsCode(CardId.SpringansKitt)))))

        graveTargetList = [c for c in Bot.Graveyard if c is not None and c.IsMonster() and not c.HasType(CardType.Fusion | CardType.Synchro)
                           and (c.IsCode(CardId.FallenOfAlbaz) or c.HasSetcode(SetcodeDespain))]

        # select targeted monster
        if Duel.LastChainPlayer == 1:
            # escape grave monster
            targetedList = [c for c in Duel.LastChainTargets if c is not None and c.Location == CardLocation.Grave and c.Controller == 0
                            and not c.HasType(CardType.Fusion | CardType.Synchro)
                            and (c.IsCode(CardId.FallenOfAlbaz) or c.HasSetcode(SetcodeDespain))]

            if len(targetedList) > 0:
                for target in targetedList:
                    newMaterialList = list(materialList) + [target]
                    _fusionTarget, _ = self.BrandedInRedFusionCheck(Bot.ExtraDeck, 0, newMaterialList, [target])
                    if _fusionTarget is not None:
                        return target

            # escape target
            lastCahinCard = Util.GetLastChainCard()
            if lastCahinCard is not None:
                chainTargetList = [c for c in Duel.LastChainTargets if c.Controller == 0 and c.Location == CardLocation.MonsterZone
                                   and (not c.IsCode(self.cannotBeFusionMaterialIdList) or c.Attack <= 2500)]
                if len(chainTargetList) > 0:
                    if lastCahinCard.IsCode(self.targetNegateIdList):
                        chainTargetList = [c for c in chainTargetList if c.Attack <= 2500 and not c.IsCode(CardId.AlbionTheBrandedDragon)]

                    for target in graveTargetList:
                        newMaterialList = list(materialList) + [target]
                        _fusionTarget, usedMaterialList = self.BrandedInRedFusionCheck(Bot.ExtraDeck, 0, newMaterialList, chainTargetList)

                        if _fusionTarget is not None:
                            if updateMaterialList:
                                self.brandedInRedMaterialList.extend(_Intersect(usedMaterialList, chainTargetList))
                            return target

        shouldSummonFirst = Duel.Player == 0 and (Duel.Phase <= DuelPhase.Main1 or Duel.Phase == DuelPhase.Main2) and not self.summoned \
            and (Bot.HasInHand([CardId.AluberTheJesterOfDespia, CardId.GuidingQuemTheVirtuous, CardId.SpringansKitt])
                 or Bot.HasInHand(CardId.FallenOfAlbaz) and self.CheckAlbazFusion(self.Card))
        idleFlag = Duel.Player == 1 or self.CurrentTiming == -1

        if shouldSummonFirst or not idleFlag:
            return None

        # for fusion searing dragon
        if not any(c is not None and c.HasType(CardType.Fusion) for c in Bot.MonsterZone) and Duel.LastChainPlayer != 0 \
                and not self.CheckWhetherNegated(True, True, CardType.Monster) and CardId.LubellionTheSearingDragon not in acl:
            for target in graveTargetList:
                newMaterialList = list(materialList) + [target]
                _fusionTarget, _ = self.BrandedInRedFusionCheck(Bot.ExtraDeck, CardId.LubellionTheSearingDragon, newMaterialList, [target])
                if _fusionTarget is not None:
                    return target

        # remove cards
        problemCardList = self.GetProblematicEnemyCardList(False, False, CardType.Monster)
        if len(problemCardList) > 0 or (Duel.Phase == DuelPhase.End and Duel.Player == 1):
            if self.DefaultCheckWhetherBotCanDraw():
                for target in graveTargetList:
                    newMaterialList = list(materialList) + [target]
                    _fusionTarget, _ = self.BrandedInRedFusionCheck(Bot.ExtraDeck, CardId.GuardianChimera, newMaterialList, [target])
                    if _fusionTarget is not None:
                        return target

            for target in graveTargetList:
                newMaterialList = list(materialList) + [target]
                _fusionTarget, _ = self.BrandedInRedFusionCheck(Bot.ExtraDeck, CardId.BorreloadFuriousDragon, newMaterialList, [target])
                if _fusionTarget is not None:
                    return target

        return None

    def BrandedInRedFusionCheck(self, canSummonList, mustSummonId, materialList, mustMaterialList):
        """C# out parameters returned: (fusionTarget, selectedFusionMaterialList)."""
        Bot, Enemy = self.Bot, self.Enemy
        cbf = self.cannotBeFusionMaterialIdList
        fusionTarget = None
        selectedFusionMaterialList = []

        # fusion id, material condition, extra check function, search material function
        checkTupleList = [
            (CardId.MirrorjadeTheIcebladeDragon,
             [lambda c: c.IsCode(CardId.FallenOfAlbaz),
              lambda c: not c.IsCode(cbf) and c.HasType(CardType.Fusion | CardType.Synchro | CardType.Xyz | CardType.Link)],
             lambda l: not Bot.HasInMonstersZone(CardId.MirrorjadeTheIcebladeDragon, faceUp=True)
             and not Bot.HasInSpellZone(CardId.MirrorjadeTheIcebladeDragon, faceUp=True),
             self.BrandedInRedUsing2SubFunc),
            (CardId.LubellionTheSearingDragon,
             [lambda c: c.IsCode(CardId.FallenOfAlbaz),
              lambda c: not c.IsCode(cbf) and c.HasAttribute(CardAttribute.Dark)],
             lambda l: not Bot.HasInMonstersZone(CardId.MirrorjadeTheIcebladeDragon, faceUp=True)
             and not Bot.HasInSpellZone(CardId.MirrorjadeTheIcebladeDragon, faceUp=True)
             and sum(1 for c in Bot.Hand if c not in l) > 0 and CardId.LubellionTheSearingDragon not in self.activatedCardIdList,
             self.BrandedInRedUsing2SubFunc),
            (CardId.GuardianChimera, None, None, self.BrandedInRedForChimeraFunc),
            (CardId.DespianQuaeritis,
             [lambda c: c.HasSetcode(SetcodeDespain),
              lambda c: not c.IsCode(cbf) and c.HasAttribute(CardAttribute.Light | CardAttribute.Dark)],
             None,
             self.BrandedInRedUsing2SubFunc),
            (CardId.BorreloadFuriousDragon,
             [lambda c: not c.IsCode(cbf) and c.HasAttribute(CardAttribute.Dark) and c.HasRace(CardRace.Dragon),
              lambda c: not c.IsCode(cbf) and c.HasAttribute(CardAttribute.Dark) and c.HasRace(CardRace.Dragon)],
             None,
             self.BrandedInRedUsing2SubFunc),
            (CardId.AlbionTheSanctifireDragon,
             [lambda c: c.IsCode(CardId.FallenOfAlbaz),
              lambda c: not c.IsCode(cbf) and c.HasAttribute(CardAttribute.Light) and c.HasRace(CardRace.SpellCaster)],
             lambda l: sum(1 for c in Enemy.Graveyard if c is not None and c.IsMonster() and c.IsCanRevive())
             + sum(1 for c in Bot.Graveyard if c is not None and c not in l) >= 2,
             self.BrandedInRedUsing2SubFunc),
        ]

        for item1, item2, item3, item4 in checkTupleList:
            if mustSummonId > 0 and mustSummonId != item1:
                continue
            currentFusionTarget = next((c for c in canSummonList if c is not None and c.IsCode(item1)), None)
            if currentFusionTarget is None:
                continue
            materialFunc = item4

            currentMaterialList = materialFunc(materialList, mustMaterialList, item2, item3)
            if len(currentMaterialList) > 0:
                fusionTarget = currentFusionTarget
                selectedFusionMaterialList = currentMaterialList
                return fusionTarget, selectedFusionMaterialList
        return fusionTarget, selectedFusionMaterialList

    def BrandedInRedUsing2SubFunc(self, materialList, mustMaterialList, checkFuncList, extraCheckFunc):
        selectedFusionMaterialList = []

        fusionFunc1 = checkFuncList[0]
        fusionFunc2 = checkFuncList[1]

        if mustMaterialList is not None and len(mustMaterialList) > 0:
            for mustMaterial in mustMaterialList:
                if not fusionFunc1(mustMaterial) and not fusionFunc2(mustMaterial):
                    continue
                for anotherMaterial in materialList:
                    if anotherMaterial == mustMaterial:
                        continue
                    checkFlag = fusionFunc1(mustMaterial) and fusionFunc2(anotherMaterial)
                    checkFlag |= fusionFunc2(mustMaterial) and fusionFunc1(anotherMaterial)
                    checkFlag &= (extraCheckFunc is None or extraCheckFunc([mustMaterial, anotherMaterial]))
                    if checkFlag:
                        selectedFusionMaterialList.append(mustMaterial)
                        selectedFusionMaterialList.append(anotherMaterial)
                        return selectedFusionMaterialList
        else:
            for index1 in range(len(materialList) - 1):
                material1 = materialList[index1]
                if not fusionFunc1(material1) and not fusionFunc2(material1):
                    continue
                for index2 in range(index1 + 1, len(materialList)):
                    material2 = materialList[index2]
                    checkFlag = fusionFunc1(material1) and fusionFunc2(material2)
                    checkFlag |= fusionFunc2(material1) and fusionFunc1(material2)
                    checkFlag &= (extraCheckFunc is None or extraCheckFunc([material1, material2]))
                    if checkFlag:
                        # (sic) the C# adds these to the selectedFusionMaterial field and returns the empty local list
                        self.selectedFusionMaterial.append(material1)
                        self.selectedFusionMaterial.append(material2)
                        return selectedFusionMaterialList

        # (sic) the C# returns the selectedFusionMaterial field here
        return self.selectedFusionMaterial

    def BrandedInRedForChimeraFunc(self, materialList, mustMaterialList, checkFuncList, extraCheckFunc):
        Enemy = self.Enemy
        selectedFusionMaterialList = []

        enemyCardCount = sum(1 for c in Enemy.MonsterZone if c is not None)
        enemyCardCount += sum(1 for c in Enemy.SpellZone if c is not None and c.Type != CardType.Spell and c.Type != CardType.Trap)
        if enemyCardCount == 0 or self.CheckWhetherNegated(True, True, CardType.Monster):
            return selectedFusionMaterialList

        fieldMaterialList = _OrderBy([c for c in materialList if c.Location == CardLocation.MonsterZone], lambda c: c.Attack)
        handMaterialList = _OrderBy([c for c in materialList if c.Location == CardLocation.Hand or c.Location == CardLocation.Grave],
                                    lambda c: c.Attack)

        # 2 field monster + 1 hand monster
        if enemyCardCount >= 2:
            for handMonster in handMaterialList:
                for fieldIndex1 in range(len(fieldMaterialList) - 1):
                    fieldMonster1 = fieldMaterialList[fieldIndex1]
                    if fieldMonster1.IsCode(handMonster.Id) or handMonster.IsCode(fieldMonster1.Id):
                        continue
                    for fieldIndex2 in range(fieldIndex1 + 1, len(fieldMaterialList)):
                        fieldMonster2 = fieldMaterialList[fieldIndex2]
                        if fieldMonster2.IsCode(fieldMonster1.Id) or fieldMonster1.IsCode(fieldMonster2.Id):
                            continue
                        if fieldMonster2.IsCode(handMonster.Id) or handMonster.IsCode(fieldMonster2.Id):
                            continue

                        return [handMonster, fieldMonster1, fieldMonster2]

        # 1 field monster + 2 hand monster
        for fieldMonster in fieldMaterialList:
            for handIndex1 in range(len(handMaterialList) - 1):
                handMonster1 = handMaterialList[handIndex1]
                if handMonster1.IsCode(fieldMonster.Id) or fieldMonster.IsCode(handMonster1.Id):
                    continue
                for handIndex2 in range(handIndex1 + 1, len(handMaterialList)):
                    handMonster2 = handMaterialList[handIndex2]
                    if handMonster2.IsCode(handMonster1.Id) or handMonster1.IsCode(handMonster2.Id):
                        continue
                    if handMonster2.IsCode(fieldMonster.Id) or fieldMonster.IsCode(handMonster2.Id):
                        continue

                    return [fieldMonster, handMonster1, handMonster2]

        return selectedFusionMaterialList

    def BrandedLostActivate(self):
        # search
        if self.Card.Location == CardLocation.SpellZone and self.Card.IsFaceup():
            return True

        return False

    def BrandedLostCardActivate(self):
        # search
        if self.Card.Location == CardLocation.SpellZone and self.Card.IsFaceup():
            return False

        # activate
        if self.CheckWhetherNegated(True, True, CardType.Spell):
            return False
        if not self.summoned and self.Bot.HasInHand(CardId.FallenOfAlbaz) and self.CheckAlbazFusion() and len(self.Bot.Hand) < 3:
            return False
        self.SelectSTPlace(self.Card, True)
        return True

    def InfiniteImpermanenceActivate(self):
        Bot, Enemy, Duel, Util, AI = self.Bot, self.Enemy, self.Duel, self.Util, self.AI
        Card = self.Card
        if self.CheckWhetherNegated():
            return False

        LastChainCard = Util.GetLastChainCard()

        # negate spells
        if Card.Location == CardLocation.SpellZone:
            this_seq = -1
            that_seq = -1
            for i in range(5):
                if Bot.SpellZone[i] == Card:
                    this_seq = i
                if LastChainCard is not None and LastChainCard.Controller == 1 and \
                        LastChainCard.Location == CardLocation.SpellZone and Enemy.SpellZone[i] == LastChainCard:
                    that_seq = i
                elif Duel.Player == 0 and Util.GetProblematicEnemySpell() is not None and \
                        Enemy.SpellZone[i] is not None and Enemy.SpellZone[i].IsFloodgate():
                    that_seq = i
            if (this_seq * that_seq >= 0 and this_seq + that_seq == 4) \
                    or Util.IsChainTarget(Card) \
                    or (LastChainCard is not None and LastChainCard.Controller == 1 and LastChainCard.IsCode(_CardId.HarpiesFeatherDuster)):
                target = self.GetProblematicEnemyMonster(canBeTarget=True)
                if target is not None:
                    AI.SelectCard(target)
                else:
                    AI.SelectCard(Enemy.GetMonsters())
                self.infiniteImpermanenceList.append(this_seq)
                return True

        # negate monster
        shouldNegateList = self.GetMonsterListForTargetNegate(True, CardType.Trap)
        if len(shouldNegateList) > 0:
            negateTarget = shouldNegateList[0]
            self.currentNegateCardList.append(negateTarget)

            if Card.Location == CardLocation.SpellZone:
                for i in range(5):
                    if Bot.SpellZone[i] == Card:
                        self.infiniteImpermanenceList.append(i)
                        break
            if Card.Location == CardLocation.Hand:
                self.SelectSTPlace(Card, True)
            AI.SelectCard(negateTarget)
            return True

        return False

    def BrightestBlazingBrandedKingActivate(self):
        Duel, Enemy = self.Duel, self.Enemy
        if self.Card.Location == CardLocation.Grave:
            if self.CheckWhetherNegated(True, False, CardType.Trap):
                return False
            self.activatedCardIdList.append(self.Card.Id)
            return True
        if self.Card.Location == CardLocation.SpellZone:
            if any(c.Controller == 0 and c.IsFaceup() and (c.Location == CardLocation.MonsterZone or c.Location == CardLocation.SpellZone)
                   and not c.IsCode(self.albazFusionMonster) for c in Duel.CurrentChain):
                return False
            if any(c.Controller == 1 and c.IsFaceup() and c not in self.currentNegateCardList and c not in self.currentDestroyCardList
                   and (c.Location == CardLocation.MonsterZone or c.Location == CardLocation.SpellZone) for c in Duel.CurrentChain):
                self.currentNegateCardList.extend(c for c in Enemy.MonsterZone if c is not None and c.IsFaceup())
                self.currentNegateCardList.extend(c for c in Enemy.SpellZone if c is not None and c.IsFaceup())
                self.activatedCardIdList.append(self.Card.Id)
                return True
        return False

    def BrandedBeastActivate(self):
        Bot, Duel, Util, AI = self.Bot, self.Duel, self.Util, self.AI
        acl = self.activatedCardIdList
        if self.CheckWhetherNegated(True, True, CardType.Trap):
            return False

        desc = -1
        if self.ActivateDescription >= Util.GetStringId(CardId.BrandedBeast, 0):
            desc = self.ActivateDescription - Util.GetStringId(CardId.BrandedBeast, 0)

        def worstDragon():
            return next(iter(_OrderBy([c for c in Bot.MonsterZone if c is not None and c.HasRace(CardRace.Dragon)
                                       and not (c.IsOriginalCode(CardId.FallenOfAlbaz) and Util.ChainContainsCard(CardId.FallenOfAlbaz))],
                                      lambda c: c.GetDefensePower())), None)

        # destroy
        if self.ActivateDescription == Util.GetStringId(self.Card.Id, 0):
            destroyTarget = None
            releaseMonster = None
            dangerCardList = self.GetProblematicEnemyCardList(True, False, CardType.Trap)
            if len(dangerCardList) > 0:
                destroyTarget = dangerCardList[0]
            if destroyTarget is None:
                if Duel.Player == 1:
                    if (self.CurrentTiming & hintTimingMainEnd) > 0:
                        targetList = self.GetNormalEnemyTargetList(True, True, CardType.Trap)
                        if len(targetList) > 0:
                            destroyTarget = targetList[0]
                else:
                    destroyTarget = Util.GetOneEnemyBetterThanMyBest(True, True)

            forceActivateFlag = self.DefaultOnBecomeTarget()
            bystialCount = sum(1 for c in Bot.MonsterZone if c is not None and c.IsFaceup() and c.HasSetcode(SetcodeBystial))
            forceActivateFlag |= bystialCount > 0 and sum(1 for c in Duel.ChainTargets if c.Controller == 0 and c.Location == CardLocation.MonsterZone
                                                          and c.IsFaceup() and c.HasSetcode(SetcodeBystial)) == bystialCount
            forceActivateFlag |= any(c.Controller == 1 and c.Location == CardLocation.SpellZone and c.IsCode(_CardId.Raigeki)
                                     for c in Duel.CurrentChain)
            if destroyTarget is None and forceActivateFlag:
                releaseMonster = next((c for c in Duel.ChainTargets if c.Controller == 0 and c.Location == CardLocation.MonsterZone
                                       and c.IsFaceup() and c.HasSetcode(SetcodeBystial)), None)
                if releaseMonster is None:
                    if CardId.AlbionTheBrandedDragon + 1 not in acl and \
                            not any(c.IsCode(CardId.AlbionTheBrandedDragon) for c in self.sendToGYThisTurn):
                        brandedDragonList = _OrderBy([c for c in Bot.MonsterZone if c is not None and c.IsCode(CardId.AlbionTheBrandedDragon)],
                                                     lambda c: c.GetDefensePower())
                        if len(brandedDragonList) > 0:
                            releaseMonster = brandedDragonList[0]
                    if releaseMonster is None:
                        releaseMonster = worstDragon()

                targetList = self.GetNormalEnemyTargetList(True, True, CardType.Trap)
                if len(targetList) > 0:
                    destroyTarget = targetList[0]

            if destroyTarget is not None:
                if CardId.AlbionTheBrandedDragon + 1 not in acl and \
                        not any(c.IsCode(CardId.AlbionTheBrandedDragon) for c in self.sendToGYThisTurn):
                    brandedDragonList = _OrderBy([c for c in Bot.MonsterZone if c is not None and c.IsCode(CardId.AlbionTheBrandedDragon)],
                                                 lambda c: c.GetDefensePower())
                    if len(brandedDragonList) > 0:
                        releaseMonster = brandedDragonList[0]
                if releaseMonster is None:
                    releaseMonster = worstDragon()

            if releaseMonster is not None and destroyTarget is not None:
                acl.append(self.Card.Id)
                AI.SelectCard(releaseMonster)
                AI.SelectNextCard(destroyTarget)
                self.currentDestroyCardList.append(destroyTarget)
                return True

        # place
        if Duel.Phase == DuelPhase.End and Bot.HasInGraveyard(CardId.BrandedLost):
            acl.append(self.Card.Id + 1)
            AI.SelectCard(CardId.BrandedLost)
            return True

        return False

    def BrandedRetributionActivate(self):
        Bot, Duel = self.Bot, self.Duel
        if self.Card.Location == CardLocation.SpellZone and Duel.LastChainPlayer == 1:
            if self.CheckWhetherNegated(True, True, CardType.Trap):
                return False
            checkFlag = sum(1 for c in Bot.Graveyard if c is not None and c.IsCode(self.albazFusionMonster)) > 1
            checkFlag |= any(c is not None and c.IsFaceup() and c.IsCode([CardId.LubellionTheSearingDragon, CardId.SprindTheIrondashDragon,
                                                                        CardId.AlbaLenatusTheAbyssDragon]) for c in Bot.MonsterZone)
            if checkFlag:
                self.activatedCardIdList.append(self.Card.Id)
                return True
        if self.Card.Location == CardLocation.Grave:
            if self.CheckWhetherNegated(True, False, CardType.Trap):
                return False

            def brandedLostCheck():
                if Duel.Player == 0 and Duel.Phase >= DuelPhase.End:
                    return False
                if Bot.HasInHandOrInSpellZone(CardId.BrandedFusion) and self.BrandedFusionActivateCheck():
                    return True
                if Bot.HasInHandOrInSpellZone(CardId.BrandedInWhite) and self.BrandedInWhiteActivateCheck():
                    return True
                if Bot.HasInHandOrInSpellZone(CardId.BrandedInRed) and self.BrandedInRedActivateCheck() is not None:
                    return True
                if not self.summoned and Bot.HasInHand(CardId.FallenOfAlbaz) and self.CheckAlbazFusion():
                    return True
                if Bot.HasInMonstersZone(CardId.BlazingCartesiaTheVirtuous) or \
                        (not self.summoned and Bot.HasInHand(CardId.BlazingCartesiaTheVirtuous)):
                    return True
                return False
            checkDict = {
                CardId.BrandedFusion: lambda: self.BrandedFusionActivateCheck(),
                CardId.BrandedLost: brandedLostCheck,
                CardId.BrandedInHighSpirits: lambda: not (Duel.Player == 1 and (self.fusionToGYFlag or Duel.Phase != DuelPhase.End))
                and self.BrandedInHighSpiritsActivateCheck(),
                CardId.BrandedInRed: lambda: self.BrandedInRedActivateCheck() is not None,
                CardId.BrandedInWhite: self.BrandedInWhiteActivateCheck,
                CardId.BrightestBlazingBrandedKing: lambda: not (Duel.Player == 1 and (self.fusionToGYFlag or Duel.Phase != DuelPhase.End))
                and any(c.IsFaceup() and c.IsCode(self.albazFusionMonster) for c in Bot.GetMonsters()),
                CardId.BrandedOpening: lambda: len(Bot.Hand) > 2 and CardId.BrandedOpening not in self.activatedCardIdList,
            }
            for key, func in checkDict.items():
                target = next((card for card in Bot.Graveyard if card.IsCode(key)), None)
                if target is not None and func():
                    self.activatedCardIdList.append(self.Card.Id)
                    self.AI.SelectCard(target)
                    return True
        return False

    def GuardianChimeraActivate(self):
        if self.CheckWhetherNegated(True, True, CardType.Monster):
            return False
        return True

    def AlbionTheSanctifireDragonActivate(self):
        Bot, Enemy, Duel, Util, AI = self.Bot, self.Enemy, self.Duel, self.Util, self.AI
        acl = self.activatedCardIdList
        # spsummon from grave
        if self.Card.Location == CardLocation.MonsterZone:
            if self.CheckWhetherNegated(True, True, CardType.Monster):
                return False
            allTargetList = [c for c in Enemy.Graveyard if c is not None and c.IsMonster() and c.IsCanRevive()]
            allTargetList.extend(c for c in Bot.Graveyard if c is not None and c.IsMonster() and c.IsCanRevive())

            targetList = []

            # spsummon albaz
            albazFusion, materialList = self.CheckAlbazFusion(None, out=True)
            if albazFusion and not self.spSummoningAlbaz:
                albazFlag = len(materialList) > 1
                if len(materialList) > 0:
                    material = materialList[0]
                    albazFlag |= material.HasType(CardType.Ritual | CardType.Fusion | CardType.Synchro | CardType.Xyz | CardType.Link)
                    albazFlag |= material.IsFloodgate() or material.IsOneForXyz() or \
                        Util.GetWorstBotMonster().GetDefensePower() < material.Attack
                    albazFlag |= Duel.Player == 1 and Duel.Phase == DuelPhase.End and Duel.LastChainPlayer == -1

                if albazFlag:
                    albaz = next((c for c in allTargetList if c.IsOriginalCode(CardId.FallenOfAlbaz)), None)
                    worstMonster = next(iter(_OrderBy([c for c in allTargetList if c != albaz and c not in self.currentDestroyCardList],
                                                      lambda c: c.GetDefensePower())), None)
                    if albaz is not None and worstMonster is not None \
                            and (self.GetProblematicEnemyMonster(0, False, False, CardType.Monster) is not None
                                 or max(worstMonster.Attack, worstMonster.Defense) <= albaz.Defense):
                        targetList.extend([albaz, worstMonster])
                        self.spSummoningAlbaz = True

            # spsummon floogate
            if len(targetList) == 0:
                floogateCard = next(iter(_OrderByDesc([c for c in allTargetList if c.IsFloodgate()], lambda c: c.GetDefensePower())), None)
                if floogateCard is not None:
                    # select worst monster
                    worstMonster = next(iter(_OrderBy([c for c in allTargetList if c != floogateCard], lambda c: c.GetDefensePower())), None)
                    if worstMonster is not None:
                        targetList.extend([floogateCard, worstMonster])

            # spsummon target
            if len(targetList) == 0 and Duel.LastChainPlayer == 1:
                targetedList = _Intersect(Duel.LastChainTargets, allTargetList)
                if len(targetedList) > 0:
                    target = Util.ShuffleList(targetedList)[0]
                    anotherTarget = None
                    if target.GetDefensePower() >= 2000:
                        # select worst
                        anotherTarget = next(iter(_OrderBy([c for c in allTargetList if c != target], lambda c: c.GetDefensePower())), None)
                    else:
                        # select best
                        anotherTarget = next(iter(_OrderByDesc([c for c in allTargetList if c != target], lambda c: c.GetDefensePower())), None)
                    if anotherTarget is not None:
                        targetList.extend([target, anotherTarget])

            # spsummon useful monster
            if len(targetList) == 0 and Duel.Player == 1 and Duel.Phase == DuelPhase.End:
                checkDict = {
                    CardId.BorreloadFuriousDragon: lambda: Enemy.GetSpellCount() > 0,
                    CardId.MirrorjadeTheIcebladeDragon: lambda: not Bot.HasInMonstersZone(CardId.MirrorjadeTheIcebladeDragon, faceUp=True)
                    and not Bot.HasInSpellZone(CardId.MirrorjadeTheIcebladeDragon, faceUp=True),
                    CardId.AluberTheJesterOfDespia: lambda: CardId.AluberTheJesterOfDespia not in acl,
                    CardId.SpringansKitt: lambda: CardId.SpringansKitt + 1 not in acl,
                }

                for key, func in checkDict.items():
                    target = next((c for c in allTargetList if c.IsCode(key)), None)
                    if target is not None and func():
                        # select worst
                        anotherTarget = next(iter(_OrderBy([c for c in allTargetList if c != target], lambda c: c.GetDefensePower())), None)
                        targetList.append(target)
                        targetList.append(anotherTarget)
                        break

            # avoid evenly match
            if len(targetList) == 0 and Duel.Player == 1 and len(Enemy.Hand) > 0 and Enemy.GetMonsterCount() + Enemy.GetSpellCount() == 0 \
                    and (self.CurrentTiming & hintBattleStart) > 0:
                summonTarget = next(iter(_OrderByDesc(allTargetList, lambda c: c.Attack)), None)
                checkDict = {
                    CardId.MirrorjadeTheIcebladeDragon: lambda: not Bot.HasInMonstersZone(CardId.MirrorjadeTheIcebladeDragon, faceUp=True)
                    and not Bot.HasInSpellZone(CardId.MirrorjadeTheIcebladeDragon, faceUp=True),
                    CardId.AluberTheJesterOfDespia: lambda: CardId.AluberTheJesterOfDespia not in acl,
                }
                for key, func in checkDict.items():
                    target = next((c for c in allTargetList if c.IsCode(key)), None)
                    if target is not None and func():
                        summonTarget = target
                        break
                if summonTarget is not None:
                    # select worst
                    anotherTarget = next(iter(_OrderBy([c for c in allTargetList if c != summonTarget], lambda c: c.GetDefensePower())), None)
                    targetList.append(summonTarget)
                    targetList.append(anotherTarget)

            if len(targetList) > 0:
                AI.SelectMaterials(targetList, HintMsg.SpSummon)
                self.currentDestroyCardList.extend(targetList)
                acl.append(self.Card.Id)
                return True
        # spsummon itself
        if self.Card.Location == CardLocation.Grave:
            if self.CheckWhetherNegated(True, False, CardType.Monster):
                return False
            botCards = [Bot.MonsterZone[2], Bot.MonsterZone[5], Bot.MonsterZone[6]]
            enemyCards = [Enemy.MonsterZone[2], Enemy.MonsterZone[5], Enemy.MonsterZone[6]]
            if any(c is not None and (c.IsFloodgate() or c.IsMonsterDangerous()) for c in enemyCards):
                return True
            return sum(0 if c is None else c.GetDefensePower() for c in botCards) < \
                sum(0 if c is None else c.GetDefensePower() for c in enemyCards)
        return False

    def MirrorjadeTheIcebladeDragonActivate(self):
        Bot, Enemy, Duel = self.Bot, self.Enemy, self.Duel
        if self.Card.Location != CardLocation.MonsterZone:
            if self.CheckWhetherNegated(True, False, CardType.Monster):
                return False
            return True
        if self.Card.Location == CardLocation.MonsterZone:
            checkFlag = self.GetProblematicEnemyMonster(0, False, False, CardType.Monster) is not None
            if Enemy.GetMonsterCount() > 0:
                checkFlag |= Duel.Player == 1 and Duel.Phase == DuelPhase.End and Duel.LastChainPlayer != 0
                enemyBattlePower = 0 if Enemy.BattlingMonster is None else Enemy.BattlingMonster.GetDefensePower()
                botBattlePower = 0 if Bot.BattlingMonster is None else Bot.BattlingMonster.GetDefensePower()
                checkFlag |= enemyBattlePower > 0 and enemyBattlePower > botBattlePower and Duel.LastChainPlayer != 0 \
                    and Enemy.BattlingMonster not in self.currentDestroyCardList
                checkFlag |= self.DefaultOnBecomeTarget() and Duel.LastChainPlayer != 0
            if any(c.IsCode(CardId.NibiruThePrimalBeing) and not self.DefaultCheckWhetherCardIdIsNegated(CardId.NibiruThePrimalBeing)
                   for c in Duel.CurrentChain):
                checkFlag |= Enemy.GetMonsterCount() > 0
                checkFlag |= Bot.HasInMonstersZone([CardId.TheBystialLubellion, CardId.DespianTragedy, CardId.TriBrigadeMercourier])

            if checkFlag:
                checkDict = {
                    CardId.AlbionTheBrandedDragon: lambda: not any(c.IsCode(CardId.AlbionTheBrandedDragon) for c in self.sendToGYThisTurn)
                    and not self.DefaultCheckWhetherCardIdIsNegated(CardId.AlbionTheBrandedDragon)
                    and not (Duel.Player == 0 and Bot.HasInMonstersZone(CardId.AlbionTheBrandedDragon)
                             and Bot.HasInGraveyard(CardId.TheBystialLubellion)),
                    CardId.RindbrummTheStrikingDragon: lambda: Duel.Player == 1
                    and any(c.IsOriginalCode(CardId.FallenOfAlbaz) for c in Bot.Graveyard) and len(Bot.Hand) > 0
                    and CardId.FallenOfAlbaz not in self.activatedCardIdList
                    and not self.DefaultCheckWhetherCardIdIsNegated(CardId.FallenOfAlbaz),
                    CardId.TitanikladTheAshDragon: lambda: Bot.HasInDeck(CardId.GuidingQuemTheVirtuous),
                    CardId.SprindTheIrondashDragon: lambda: Bot.HasInDeck(CardId.SpringansKitt),
                    CardId.AlbaLenatusTheAbyssDragon: lambda: Bot.HasInDeck(CardId.FusionDeployment, CardId.BrandedFusion),
                    CardId.LubellionTheSearingDragon: lambda: True,
                    CardId.AlbionTheSanctifireDragon: lambda: True,
                }

                for key, func in checkDict.items():
                    if Bot.HasInExtra(key) and func():
                        self.AI.SelectCard(key)
                        return True
        return False

    def BorreloadFuriousDragonActivate(self):
        Bot, Duel, Util, AI = self.Bot, self.Duel, self.Util, self.AI
        cdl = self.currentDestroyCardList
        if self.CheckWhetherNegated(True, True, CardType.Monster):
            return False

        # destroy dangerous card
        dangerList = self.GetProblematicEnemyCardList(True, False, CardType.Monster)
        if len(dangerList) > 0:
            botTarget = next(iter(_OrderBy(Bot.GetMonsters(), lambda c: c.GetDefensePower() + (1 if c.IsCode(self.albazFusionMonster) else 0))),
                             None)
            if botTarget is not None:
                AI.SelectCard(botTarget)
                AI.SelectNextCard(dangerList)
                cdl.append(botTarget)
                cdl.append(dangerList[0])
                self.activatedCardIdList.append(self.Card.Id)
                return True

        enemyTargetList = self.GetNormalEnemyTargetList(True, True, CardType.Monster)

        # become target
        if Duel.LastChainPlayer == 1:
            targetedBotMonsterList = [c for c in Duel.LastChainTargets if c.Location == CardLocation.MonsterZone and c.Controller == 0]
            lastChainCard = Util.GetLastChainCard()
            becomeTargetDestroyList = [c for c in enemyTargetList if c.Location == CardLocation.MonsterZone]
            if len(becomeTargetDestroyList) == 0:
                becomeTargetDestroyList = [c for c in enemyTargetList if c.Location == CardLocation.SpellZone
                                           and (c != lastChainCard or c.HasType(CardType.Continuous | CardType.Equip | CardType.Field | CardType.Pendulum))]
            # if it's a negate effect, only destroy not important monster
            if lastChainCard is not None and lastChainCard.IsCode(self.targetNegateIdList):
                targetedBotMonsterList = _OrderBy([c for c in targetedBotMonsterList
                                                   if not c.IsCode(CardId.BlazingCartesiaTheVirtuous) or c.Attack < 2500], lambda c: c.Attack)
            if len(targetedBotMonsterList) > 0 and len(becomeTargetDestroyList) > 0:
                AI.SelectCard(targetedBotMonsterList)
                AI.SelectNextCard(becomeTargetDestroyList)
                cdl.append(targetedBotMonsterList[0])
                cdl.append(becomeTargetDestroyList[0])
                self.activatedCardIdList.append(self.Card.Id)
                return True

        # end phase
        if Duel.Player == 1 and Duel.Phase == DuelPhase.End and len(enemyTargetList) > 0:
            botTargetList = _OrderBy([c for c in Bot.MonsterZone if c is not None and c.GetDefensePower() <= 2500], lambda c: c.GetDefensePower())
            if len(botTargetList) > 0:
                AI.SelectCard(botTargetList)
                AI.SelectNextCard(enemyTargetList)
                cdl.append(botTargetList[0])
                cdl.append(enemyTargetList[0])
                self.activatedCardIdList.append(self.Card.Id)
                return True

        return False

    def LubellionTheSearingDragonActivate(self):
        if self.CheckWhetherNegated(True, True, CardType.Monster):
            return False
        if self.Card.Location == CardLocation.MonsterZone:
            fusionTarget, _ = self.LubellionTheSearingDragonFusionTarget(self.Bot.ExtraDeck)
            if fusionTarget > 0:
                self.activatedCardIdList.append(self.Card.Id)
                return True
        return False

    def LubellionTheSearingDragonFusionTarget(self, cards):
        """C# out ClientCard target returned: (id, target)."""
        Bot, Enemy, Duel, Util = self.Bot, self.Enemy, self.Duel, self.Util
        cbf = self.cannotBeFusionMaterialIdList
        hasAlbaz = any(c is not None and c.IsFaceup() and c.IsOriginalCode(CardId.FallenOfAlbaz) for c in Bot.Banished)
        hasAlbaz |= any(c is not None and c.IsFaceup() and c.IsOriginalCode(CardId.FallenOfAlbaz) for c in Bot.Graveyard)

        def borreloadCheck():
            darkDragonCount = sum(1 for c in Bot.Banished if c.IsFaceup() and c.HasRace(CardRace.Dragon) and c.HasAttribute(CardAttribute.Dark)
                                  and not c.IsCode(cbf))
            darkDragonCount += sum(1 for c in Bot.Graveyard if c.HasRace(CardRace.Dragon) and c.HasAttribute(CardAttribute.Dark)
                                   and not c.IsCode(cbf) and (Duel.Player == 1 or not self.CheckWhetherShouldKeepInGrave(c)))
            return darkDragonCount >= 2

        def titanikladCheck():
            if not hasAlbaz:
                return False
            enemyMonster = Util.GetBestEnemyMonster(True)
            botMonster = Util.GetBestBotMonster(True)
            enemyPower = 0 if enemyMonster is None else enemyMonster.GetDefensePower()
            botPower = 0 if botMonster is None else botMonster.Attack
            if enemyPower > 0 and enemyPower >= botPower:
                materialList = list(Bot.Banished)
                materialList.extend(Bot.Graveyard)
                for material in materialList:
                    if material is not None and material.IsFaceup() and material.Attack >= 2500 and (2900 + material.Level >= enemyPower):
                        return True
            return False

        def quaeritisCheck():
            if not any(c is not None and c.IsFaceup() and c.Attack > 2500 and not (c.HasType(CardType.Fusion) and c.Level >= 8)
                       for c in Enemy.MonsterZone):
                return False
            checkFlag = any(c is not None and c.IsFaceup() and c.HasSetcode(SetcodeDespain) for c in Bot.Banished)
            checkFlag |= any(c is not None and c.IsFaceup() and c.HasSetcode(SetcodeDespain) for c in Bot.Graveyard)

            return checkFlag

        def albionBrandedCheck():
            if CardId.AlbionTheBrandedDragon in self.activatedCardIdList or \
                    self.DefaultCheckWhetherCardIdIsNegated(CardId.AlbionTheBrandedDragon):
                return False
            checkFlag = any(c is not None and c.IsFaceup() and c.HasAttribute(CardAttribute.Light) for c in Bot.Banished)
            checkFlag |= any(c is not None and c.IsFaceup() and c.HasAttribute(CardAttribute.Light) for c in Bot.Graveyard)

            return checkFlag

        checkDict = {
            CardId.MirrorjadeTheIcebladeDragon: lambda: hasAlbaz and not self.DefaultCheckWhetherCardIdIsNegated(CardId.MirrorjadeTheIcebladeDragon),
            CardId.GranguignolTheDuskDragon: lambda: Bot.HasInBanished(CardId.BlazingCartesiaTheVirtuous),
            CardId.BorreloadFuriousDragon: borreloadCheck,
            CardId.RindbrummTheStrikingDragon: lambda: hasAlbaz and Bot.HasInBanished(CardId.TriBrigadeMercourier),
            CardId.TitanikladTheAshDragon: titanikladCheck,
            CardId.DespianQuaeritis: quaeritisCheck,
            CardId.AlbaLenatusTheAbyssDragon: lambda: hasAlbaz and not Bot.HasInExtra(CardId.AlbionTheBrandedDragon),
            CardId.AlbionTheBrandedDragon: albionBrandedCheck,
        }

        for key, func in checkDict.items():
            target = next((card for card in cards if card.IsCode(key)), None)
            if target is not None and func():
                return key, target

        return 0, None

    def AlbaLenatusTheAbyssDragonSpSummon(self):
        Bot, Enemy = self.Bot, self.Enemy
        # use albaz + enemy's dragon monster
        enemyDragon = [c for c in Enemy.GetMonsters() if c is not None and c.IsFaceup()
                       and not c.IsCode(self.cannotBeFusionMaterialIdList) and c.HasRace(CardRace.Dragon)]
        if len(enemyDragon) > 0:
            successFlag = len(enemyDragon) > 1
            bestBotPower = self.Util.GetBestAttack(Bot)
            successFlag |= any(c.GetDefensePower() >= bestBotPower for c in enemyDragon)
            if successFlag:
                if not any(c.IsCode(CardId.FallenOfAlbaz) for c in enemyDragon):
                    botAlbaz = next((c for c in Bot.MonsterZone if c is not None and c.IsCode(CardId.FallenOfAlbaz)), None)
                    if botAlbaz is not None:
                        enemyDragon.append(botAlbaz)
                self.AI.SelectMaterials(enemyDragon)
                return True

        return False

    def AlbaLenatusTheAbyssDragonActivate(self):
        if self.CheckWhetherNegated(True, False, CardType.Monster):
            return False
        self.activatedCardIdList.append(self.Card.Id)
        return True

    def GranguignolTheDuskDragonActivate(self):
        Util = self.Util
        desc = -1
        if self.ActivateDescription >= Util.GetStringId(CardId.GranguignolTheDuskDragon, 0):
            desc = self.ActivateDescription - Util.GetStringId(CardId.GranguignolTheDuskDragon, 0)

        # send to GY
        if self.ActivateDescription == -1 or self.ActivateDescription == Util.GetStringId(CardId.GranguignolTheDuskDragon, 0):
            if self.CheckWhetherNegated(True, True, CardType.Monster) or \
                    self.DefaultCheckWhetherBotWillBeBanished(CardType.Monster, CardLocation.Extra | CardLocation.Deck):
                return False
            checkId, _ = self.GranguignolTheDuskDragonSendToGYTarget(None)
            if checkId > 0:
                self.activatedCardIdList.append(self.Card.Id)
                return True
        # spsummon
        if self.ActivateDescription == Util.GetStringId(CardId.GranguignolTheDuskDragon, 1):
            if self.CheckWhetherNegated(True, self.Card.Location == CardLocation.MonsterZone, CardType.Monster):
                return False
            self.activatedCardIdList.append(self.Card.Id + 1)
            return True

        return False

    def GranguignolTheDuskDragonSendToGYTarget(self, cards):
        """C# out ClientCard target returned: (id, target)."""
        Bot, Duel = self.Bot, self.Duel
        acl = self.activatedCardIdList
        needSendBranded = Bot.HasInGraveyard(CardId.BrandedRetribution) and Bot.HasInDeck(CardId.BrandedFusion)
        if Bot.HasInDeck(CardId.BrandedRetribution):
            needSendBranded |= any(c is not None and c.HasType(CardType.Spell | CardType.Trap) and c.HasSetcode(SetcodeBranded)
                                   and not (self.fusionToGYFlag and c.IsCode(CardId.BrightestBlazingBrandedKing, CardId.BrandedInHighSpirits))
                                   for c in Bot.Graveyard)
            needSendBranded |= CardId.AlbionTheShroudedDragon not in acl and \
                not self.DefaultCheckWhetherBotWillBeBanished(CardType.Spell | CardType.Trap, CardLocation.Deck) and \
                Bot.HasInHandOrInGraveyard(CardId.AlbionTheShroudedDragon)
            needSendBranded |= any(c.Controller == 0 and c.Location == CardLocation.Grave and c.IsCode(CardId.BystialSaronir)
                                   for c in Duel.CurrentChain)
        checkList = [
            (CardId.BystialSaronir, lambda: CardId.BystialSaronir not in acl and needSendBranded),
            (CardId.AlbionTheShroudedDragon, lambda: CardId.AlbionTheShroudedDragon not in acl and needSendBranded),
            (CardId.AlbionTheBrandedDragon, lambda: CardId.AlbionTheBrandedDragon + 1 not in acl
             and not any(c.IsCode(CardId.AlbionTheBrandedDragon) for c in self.sendToGYThisTurn)),
            (CardId.TitanikladTheAshDragon, lambda: CardId.TitanikladTheAshDragon not in acl
             and not any(c.IsCode(CardId.TitanikladTheAshDragon) for c in self.sendToGYThisTurn)
             and Bot.HasInDeck(CardId.GuidingQuemTheVirtuous, CardId.FallenOfAlbaz)),
            (CardId.TheBystialLubellion, lambda: Bot.HasInMonstersZone([CardId.AlbionTheBrandedDragon, CardId.TitanikladTheAshDragon])
             and Bot.HasInDeck(CardId.BrandedLost, CardId.BrandedBeast)),
            (CardId.SprindTheIrondashDragon, lambda: CardId.SprindTheIrondashDragon not in acl
             and not any(c.IsCode(CardId.SprindTheIrondashDragon) for c in self.sendToGYThisTurn)
             and Bot.HasInDeck(CardId.SpringansKitt)),
            (CardId.DespianLuluwalilith, lambda: Bot.HasInDeck(CardId.BlazingCartesiaTheVirtuous, CardId.GuidingQuemTheVirtuous)),
            (CardId.AlbionTheShroudedDragon, lambda: True),
        ]

        for key, func in checkList:
            if cards is None:
                if (Bot.HasInDeck(key) or Bot.HasInExtra(key)) and func():
                    return key, None
            else:
                tg = next((c for c in cards if c.IsOriginalCode(key)), None)
                if tg is not None and func():
                    return key, tg

        return 0, None

    def DespianQuaeritisActivate(self):
        Enemy, Duel = self.Enemy, self.Duel
        if self.Card.Location == CardLocation.MonsterZone and Duel.Phase == DuelPhase.Main1 and \
                not self.CheckWhetherNegated(True, True, CardType.Monster):
            if (self.CurrentTiming & hintTimingMainEnd) != 0 and Duel.Player == 1:
                bestBotPower = self.Util.GetBestPower(self.Bot, False)
                if any(c.GetDefensePower() >= bestBotPower and c.IsAttack() and not (c.HasType(CardType.Fusion) and c.Level >= 8)
                       for c in Enemy.GetMonsters()):
                    self.activatedCardIdList.append(self.Card.Id)
                    return True
            if Duel.Player == 0 and any(c.IsAttack() and not (c.HasType(CardType.Fusion) and c.Level >= 8) for c in Enemy.GetMonsters()):
                self.activatedCardIdList.append(self.Card.Id)
                return True
        if self.Card.Location != CardLocation.MonsterZone:
            if self.CheckWhetherNegated(True, False, CardType.Monster):
                return True
            self.activatedCardIdList.append(self.Card.Id + 1)
            return True
        return False

    def SprindTheIrondashDragonActivate(self):
        # search
        if self.Card.Location == CardLocation.Grave:
            if self.CheckWhetherNegated(True, False, CardType.Monster):
                return False
            self.activatedCardIdList.append(self.Card.Id + 1)
            return True
        # destroy
        if self.Card.Location == CardLocation.MonsterZone:
            if self.CheckWhetherNegated(True, True, CardType.Monster):
                return False
            moveDest = self.SprindTheIrondashDragonMoveZone(0, self.Card)
            if moveDest > 0:
                self.activatedCardIdList.append(self.Card.Id)
                return True
        return False

    def SprindTheIrondashDragonMoveZone(self, available=0, selfCard=None):
        maxZone = -1
        maxValue = 0
        for zoneId in range(5):
            # check whether can move
            if self.Bot.MonsterZone[zoneId] is not None:
                continue
            zone = 2 ** zoneId
            if available > 0 and (available & zone) == 0:
                continue

            currentValue = self.SprindTheIrondashDragonDestroyValue(zoneId, selfCard)
            if currentValue > maxValue:
                maxZone = zone
                maxValue = currentValue
        return maxZone

    def SprindTheIrondashDragonDestroyValue(self, zoneId, selfCard=None):
        Bot, Enemy = self.Bot, self.Enemy
        value = 0
        if zoneId == 1 or zoneId == 3:
            botMonsterInExtraZone = Bot.MonsterZone[(zoneId + 9) // 2]
            if botMonsterInExtraZone is not None and botMonsterInExtraZone != selfCard and botMonsterInExtraZone.IsFaceup():
                value -= 5

            enemyMonserInExtraZone = Enemy.MonsterZone[(11 - zoneId) // 2]
            if enemyMonserInExtraZone is not None and enemyMonserInExtraZone.IsFaceup():
                value += 2
        botSpell = Bot.SpellZone[zoneId]
        if botSpell is not None and botSpell.IsFaceup():
            value -= 1
        enemyMonster = Enemy.MonsterZone[5 - zoneId]
        if enemyMonster is not None and enemyMonster.IsFaceup():
            value += 1
            if enemyMonster.IsFloodgate() or enemyMonster.IsMonsterDangerous():
                value += 5
        enemySpell = Enemy.SpellZone[5 - zoneId]
        if enemySpell is not None and enemySpell.IsFaceup():
            value += 1
            if enemySpell.IsFloodgate():
                value += 5

        return value

    def TitanikladTheAshDragonActivate(self):
        if self.Card.Location == CardLocation.Grave:
            if self.CheckWhetherNegated(True, False, CardType.Monster):
                return False
            self.activatedCardIdList.append(self.Card.Id)
            return True
        return False

    def RindbrummTheStrikingDragonActivate(self):
        Bot, Enemy, Duel, Util = self.Bot, self.Enemy, self.Duel, self.Util
        Card = self.Card
        if Card.Location == CardLocation.MonsterZone:
            if self.CheckWhetherNegated(True, True, CardType.Monster):
                return False
            checkFlag = False

            lastChainCard = Util.GetLastChainCard()
            if lastChainCard is not None:
                checkFlag = Duel.LastChainPlayer == 1
                checkFlag |= Duel.LastChainPlayer == 0 and lastChainCard.IsCode(CardId.MirrorjadeTheIcebladeDragon) and \
                    lastChainCard.Location == CardLocation.MonsterZone and Enemy.GetMonsterCount() == 0

            if checkFlag:
                self.activatedCardIdList.append(Card.Id)
                return True
        if Card.Location == CardLocation.Grave:
            if self.CheckWhetherNegated(True, True, CardType.Monster) or \
                    any(c.Controller == 0 and c.IsCode(CardId.GuidingQuemTheVirtuous) for c in Duel.CurrentChain):
                return False

            albaz = next((c for c in Bot.Graveyard if c.IsOriginalCode(CardId.FallenOfAlbaz)), None)
            checkFlag = Card.IsCanRevive() and any(c is not None and c.IsFaceup() and
                                                   c.HasType(CardType.Fusion | CardType.Synchro | CardType.Xyz | CardType.Link)
                                                   for c in Enemy.MonsterZone)
            albazFusion, materialList = self.CheckAlbazFusion(None, out=True)
            albazFlag = albazFusion and albaz is not None and not self.spSummoningAlbaz
            if albazFlag:
                checkFlag |= len(materialList) > 1
                if len(materialList) > 0:
                    material = materialList[0]
                    checkFlag |= material.HasType(CardType.Ritual | CardType.Fusion | CardType.Synchro | CardType.Xyz | CardType.Link)
                    worstBotMonster = Util.GetWorstBotMonster()
                    checkFlag |= material.IsFloodgate() or material.IsOneForXyz() or \
                        (worstBotMonster is not None and worstBotMonster.GetDefensePower() < material.Attack)
                    checkFlag |= Duel.Player == 1 and Duel.Phase == DuelPhase.End and Duel.LastChainPlayer == -1

            if checkFlag:
                albaz = next(iter(_OrderBy([c for c in Bot.Graveyard if c.IsCode(CardId.FallenOfAlbaz)], lambda c: c.GetDefensePower())), None)

                if checkFlag and albaz is not None:
                    self.spSummoningAlbaz = True
                    self.activatedCardIdList.append(Card.Id + 1)
                    self.AI.SelectCard(albaz)
                    return True
        return False

    def AlbionTheBrandedDragonActivate(self):
        if self.Card.Location == CardLocation.MonsterZone:
            if self.CheckWhetherNegated(True, True, CardType.Monster):
                return False
            fusionTarget, _ = self.AlbionTheBrandedDragonFusionTarget(self.Bot.ExtraDeck)
            if fusionTarget > 0:
                self.activatedCardIdList.append(self.Card.Id)
                return True
        if self.Card.Location == CardLocation.Grave:
            if self.CheckWhetherNegated(True, False, CardType.Monster):
                return False
            self.activatedCardIdList.append(self.Card.Id + 1)
            return True
        return False

    def AlbionTheBrandedDragonFusionTarget(self, cards):
        """C# out ClientCard target returned: (id, target)."""
        Bot, Enemy, Duel, Util = self.Bot, self.Enemy, self.Duel, self.Util
        cbf = self.cannotBeFusionMaterialIdList
        keep = self.CheckWhetherShouldKeepInGrave

        def mirrorjadeCheck():
            checkFlag = not self.CheckWhetherNegated() and self.CheckShouldNoMoreSpSummon(CardLocation.Extra)
            checkFlag |= any(c is not None and c not in self.sendToGYThisTurn and not c.IsCode(cbf)
                             and c.HasType(CardType.Fusion | CardType.Synchro | CardType.Xyz | CardType.Link) for c in Bot.Graveyard)
            return checkFlag

        def lubellionCheck():
            if CardId.LubellionTheSearingDragon not in self.activatedCardIdList:
                checkMaterialList = list(Bot.GetMonsters())
                checkMaterialList.extend(Bot.Graveyard)
                albazChecked = False
                hasOriginalAlbaz = any(c.IsOriginalCode(CardId.FallenOfAlbaz) for c in checkMaterialList)
                for checkCard in checkMaterialList:
                    if not albazChecked and checkCard.IsCode(CardId.FallenOfAlbaz) and \
                            (not hasOriginalAlbaz or not checkCard.IsOriginalCode(CardId.AlbionTheShroudedDragon)):
                        albazChecked = True
                        continue
                    if checkCard.HasAttribute(CardAttribute.Dark):
                        return True
                if Bot.HasInHand(CardId.TriBrigadeMercourier) and len(Bot.Hand) >= 2:
                    return True
            return False

        def borreloadCheck():
            if Enemy.GetMonsterCount() + Enemy.GetSpellCount() > 0:
                darkDragonCount = sum(1 for c in Bot.Graveyard if c.HasRace(CardRace.Dragon) and c.HasAttribute(CardAttribute.Dark)
                                      and not c.IsCode(cbf) and (Duel.Player == 1 or not keep(c)))
                if Duel.Player == 1 and any(c.HasRace(CardRace.Dragon) and c.HasAttribute(CardAttribute.Dark) and not c.IsCode(cbf)
                                            for c in Bot.GetMonsters()):
                    darkDragonCount += 1
                return darkDragonCount >= 2
            return False

        def sanctifireCheck():
            albaz = next((c for c in Bot.Graveyard if c.IsCode(CardId.FallenOfAlbaz)), None)
            lightSpellcaster = next((c for c in Bot.Graveyard if c.HasRace(CardRace.SpellCaster) and c.HasAttribute(CardAttribute.Light)), None)
            remainMonsterCount = len(Enemy.GetGraveyardMonsters())
            remainMonsterCount += sum(1 for c in Bot.Graveyard if c.IsMonster() and c != albaz and c != lightSpellcaster)
            remainMonsterCount += 1 if Bot.HasInHand(_CardId.MaxxC) else 0
            return remainMonsterCount >= 2

        def quaeritisCheck():
            checkFlag = any(c is not None and c.IsFaceup() and c.Attack >= 2500 and not (c.HasType(CardType.Fusion) and c.Level >= 8)
                            for c in Enemy.MonsterZone)
            if checkFlag:
                despian = next(iter(_OrderBy([c for c in Bot.Graveyard if c is not None and c.HasSetcode(SetcodeDespain) and not keep(c)],
                                             lambda c: c.GetDefensePower())), None)
                if despian is None:
                    despian = next(iter(_OrderBy([c for c in Bot.MonsterZone if c is not None and c.HasSetcode(SetcodeDespain)],
                                                 lambda c: c.GetDefensePower())), None)
                if despian is not None:
                    return any(c.HasAttribute(CardAttribute.Light | CardAttribute.Dark) and not keep(c) and c != despian
                               for c in Bot.Graveyard)

            return False

        def titanikladCheck():
            albaz = next((c for c in Bot.Graveyard if c is not None and c.IsOriginalCode(CardId.FallenOfAlbaz)), None)
            if albaz is None:
                albaz = next((c for c in Bot.Graveyard if c is not None and c.IsCode(CardId.FallenOfAlbaz)), None)
            for material in Bot.Graveyard:
                if material is not None and material != albaz and material.IsMonster() and material.Attack >= 2500 and \
                        not material.IsCode(cbf):
                    checkFlag = not Util.IsTurn1OrMain2() and Enemy.GetMonsterCount() == 0
                    checkFlag |= not keep(material)
                    return checkFlag
            return False

        def albaLenatusCheck():
            if Util.GetOneEnemyBetterThanMyBest() is None:
                albaz = next((c for c in Bot.Graveyard if c is not None and c.IsOriginalCode(CardId.FallenOfAlbaz)), None)
                if albaz is None:
                    albaz = next((c for c in Bot.Graveyard if c is not None and c.IsCode(CardId.FallenOfAlbaz)), None)
                for material in Bot.Graveyard:
                    if material is not None and material != albaz and material.IsMonster() and material.HasRace(CardRace.Dragon) \
                            and not material.IsCode(cbf):
                        return True
            return False

        def granguignolCheck():
            if cards is None:
                return False
            return True

        checkDict = {
            CardId.MirrorjadeTheIcebladeDragon: mirrorjadeCheck,
            CardId.LubellionTheSearingDragon: lubellionCheck,
            CardId.BorreloadFuriousDragon: borreloadCheck,
            CardId.AlbionTheSanctifireDragon: sanctifireCheck,
            CardId.RindbrummTheStrikingDragon: lambda: Bot.HasInGraveyard(CardId.TriBrigadeMercourier),
            CardId.DespianQuaeritis: quaeritisCheck,
            CardId.TitanikladTheAshDragon: titanikladCheck,
            CardId.AlbaLenatusTheAbyssDragon: albaLenatusCheck,
            CardId.GranguignolTheDuskDragon: granguignolCheck,
        }

        for key, func in checkDict.items():
            target = next((card for card in cards if card.IsCode(key)), None)
            if target is not None and func():
                return key, target

        return 0, None

    def DespianLuluwalilithActivate(self):
        if self.Card.Location == CardLocation.MonsterZone:
            if self.CheckWhetherNegated(True, True, CardType.Monster):
                return False
            self.activatedCardIdList.append(self.Card.Id)
            return True
        if self.Card.Location == CardLocation.Grave:
            if self.CheckWhetherNegated(True, False, CardType.Monster):
                return False
            if self.Bot.HasInDeck(CardId.GuidingQuemTheVirtuous, CardId.BlazingCartesiaTheVirtuous):
                self.activatedCardIdList.append(self.Card.Id + 1)
                return True
        return False

    def SetForChimera(self):
        Bot, Enemy = self.Bot, self.Enemy
        Card = self.Card
        if Card.Level <= 4:
            return False
        if Bot.GetMonsterCount() > 0 or not Bot.HasInHandOrInSpellZone(CardId.BrandedInWhite) or not Bot.HasInExtra(CardId.GuardianChimera):
            return False
        if self.DefaultCheckWhetherCardIdIsNegated(CardId.GuardianChimera) or self.CheckWhetherNegated(True, True, CardType.Monster):
            return False
        if all(c is None for c in Enemy.MonsterZone) and all(c is None for c in Enemy.SpellZone):
            return False

        for handIndex1 in range(len(Bot.Hand) - 1):
            hand1 = Bot.Hand[handIndex1]
            if not hand1.IsMonster() or hand1.IsCode(Card.Id) or Card.IsCode(hand1.Id):
                continue
            for handIndex2 in range(handIndex1 + 1, len(Bot.Hand)):
                hand2 = Bot.Hand[handIndex2]
                if not hand2.IsMonster():
                    continue
                if hand2.IsCode(Card.Id) or Card.IsCode(hand2.Id) or hand2.IsCode(hand1.Id) or hand1.IsCode(hand2.Id):
                    continue
                checkFlag = Card.HasRace(CardRace.Dragon) or hand1.HasRace(CardRace.Dragon) or hand2.HasRace(CardRace.Dragon)
                if checkFlag:
                    self.summoned = True
                    return True

        return False

    def AdvanceSummon(self):
        Bot, AI = self.Bot, self.AI
        Card = self.Card
        if Card.Level < 5:
            return False

        releaseGoal = [c for c in Bot.MonsterZone if c is not None and c.IsFaceup() and not c.IsDisabled() and c.IsCode(10158145)]
        if len(releaseGoal) > 0:
            if Card.Level <= 6:
                AI.SelectMaterials(releaseGoal)
                self.summoned = True
                return True

            if Card.Level >= 7:
                if len(releaseGoal) < 2:
                    anotherMaterial = next(iter(_OrderBy([c for c in Bot.MonsterZone if c is not None and c not in releaseGoal],
                                                         lambda c: c.GetDefensePower())), None)
                    if anotherMaterial.GetDefensePower() > Card.Attack:
                        return False
                    releaseGoal.append(anotherMaterial)
                if len(releaseGoal) >= 2:
                    AI.SelectMaterials(releaseGoal)
                    self.summoned = True
                    return True
        return False

    def SpellSetCheck(self):
        Bot, Enemy, Duel, AI = self.Bot, self.Enemy, self.Duel, self.AI
        Card = self.Card
        if Duel.Phase == DuelPhase.Main1 and Bot.HasAttackingMonster() and Duel.Turn > 1:
            return False
        if Card.Id == CardId.BrandedInHighSpirits:
            checkFlag = (Bot.HasInMonstersZone(CardId.GuidingQuemTheVirtuous)
                         or (Bot.HasInDeck(CardId.GuidingQuemTheVirtuous) and
                             any(c.IsCode(CardId.TitanikladTheAshDragon) for c in self.sendToGYThisTurn)))
            if not checkFlag:
                return False
        elif Card.Id == CardId.BrandedOpening:
            checkFlag = Bot.HasInDeck(CardId.AluberTheJesterOfDespia, CardId.GuidingQuemTheVirtuous)
            if not checkFlag:
                return False
        elif Card.Id == CardId.BrightestBlazingBrandedKing:
            checkFlag = any(c is not None and c.IsFaceup() and c.IsCode(self.albazFusionMonster) for c in Bot.MonsterZone)
            if not checkFlag:
                return False
        elif Card.Id == CardId.BrandedBeast:
            checkFlag = Bot.HasInGraveyard(CardId.BrandedLost) or \
                any(c is not None and c.IsFaceup() and c.HasSetcode(SetcodeBystial) for c in Bot.MonsterZone)
            checkFlag |= Bot.HasInHand(CardId.BystialSaronir) and (any(self.CheckBystialCanBanish(c) for c in Enemy.Graveyard) or
                                                                  any(self.CheckBystialCanBanish(c) for c in Bot.Graveyard))
            if not checkFlag:
                return False
        elif Card.Id == CardId.BrandedRetribution:
            checkFlag = sum(1 for c in Bot.Graveyard if c.IsCode(self.albazFusionMonster)) > 1
            checkFlag |= any(c is not None and c.IsFaceup() and c.IsCode(self.albazFusionMonster) for c in Bot.MonsterZone)
            if not checkFlag:
                return False

        # select place
        if Card.IsTrap() or Card.HasType(CardType.QuickPlay):
            avoid_list = []
            setForInfiniteImpermanence = 0
            for i in range(5):
                if Enemy.SpellZone[i] is not None and Enemy.SpellZone[i].IsFaceup() and Bot.SpellZone[4 - i] is None:
                    avoid_list.append(4 - i)
                    setForInfiniteImpermanence += 2 ** (4 - i)
            if Bot.HasInHand(_CardId.InfiniteImpermanence):
                if Card.IsCode(_CardId.InfiniteImpermanence):
                    AI.SelectPlace(setForInfiniteImpermanence)
                    return True
                else:
                    self.SelectSTPlace(Card, False, avoid_list)
                    return True
            else:
                self.SelectSTPlace()
            return True

        elif Enemy.HasInSpellZone(_CardId.AntiSpellFragrance, True) or Bot.HasInSpellZone(_CardId.AntiSpellFragrance, True):
            if Card.IsSpell() and not Bot.HasInSpellZone(Card.Id):
                self.SelectSTPlace()
                return True

        return False

    def DefaultSetForDiabellze(self):
        if super().DefaultSetForDiabellze():
            self.SelectSTPlace(self.Card, True)
            return True
        return False

    # for Sanctifire Dragon spsummoned monster
    def FloogateActivate(self):
        Card = self.Card
        if Card.Owner != 1 and not Card.IsFloodgate():
            return False
        if self.CheckWhetherNegated():
            return False
        if any(t == ExecutorType.Activate and cid is not None and Card.IsOriginalCode(cid) for t, cid, _ in self.rows):
            return False
        if self.Duel.LastChainPlayer == 1:
            lastChainCard = self.Util.GetLastChainCard()
            if lastChainCard is not None and lastChainCard.IsFaceup() and self.CheckCanBeTargeted(lastChainCard, True, CardType.Monster) \
                    and (lastChainCard.Location == CardLocation.MonsterZone or lastChainCard.Location == CardLocation.SpellZone):
                self.AI.SelectCard(lastChainCard)

        return self.Duel.LastChainPlayer == 1
