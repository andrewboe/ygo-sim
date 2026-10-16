"""Sky Striker executor, ported from IceYGO/windbot Game/AI/Decks/SkyStrikerExecutor.cs (MIT, see THIRD_PARTY_NOTICES.md).

Approximations: the env limits in docs/windbot_porting.md: IsDisabled() is always False, Bot/Enemy.BattlingMonster
are None (so `WidowAnchorTarget == Enemy.BattlingMonster` is true only when WidowAnchorTarget is None, as in C#),
Attacked is False, IsSpecialSummoned is False (Knightmare Cerberus never finds a target), link markers are 0
(GetLinkedZones is 0, so the Topologic / Hayate zone rules in OnSelectPlace never fire). Cards kept across
decisions (MultiroleSetCards, ControlledEnemyCards, CurrentChainHandledCards, WidowAnchorTarget,
SharkCannonTarget) are snapshots of the decision that stored them; OnMove finds a tracked card with FindMovedCard
(id + previous controller / location) instead of object identity and follows it when it stays (a card that
stays in place keeps its key). OnNewTurn's RemoveAll reads those snapshots' Controller / Location, so removal
happens in OnMove. OnSelectYesNo's Shark Cannon question treats a missing SharkCannonTarget (the search took
an option this executor's row did not pass) as "don't revive" instead of WindBot's null dereference.
Logging calls dropped.

Module-level helpers (WindBot members the shim lacks): CanMakeLinkRating and GetBotAvailZonesFromExtraDeck
(AIUtil), IsNewRule2020 (Duel.IsNewRule2020; EDOPro duels use Master Rule 2020, so True when the view lacks
it), CardLinkMarker (the enum), and FindMovedCard (the ClientCard identity stand-in above, as in
chaos_ritual.py)."""
from windbot import *
from windbot_default import DefaultExecutor, _CardId, _Setcode
from windbot_gameai import BattlePhaseAction


class CardId:
    Raye = 26077387
    Kagari = 63288573
    Shizuku = 90673288
    Hayate = 8491308
    Token = 52340445

    Engage = 63166095
    HornetDrones = 52340444
    WidowAnchor = 98338152
    SharkCannon = 51227866
    Afterburners = 99550630
    JammingWaves = 25955749
    Multirole = 24010609
    HerculesBase = 97616504
    AreaZero = 50005218

    AshBlossom = 14558127
    GhostOgre = 59438930
    MaxxC = 23434538
    GlowUpBulb = 67441435
    EffectVeiler = 97268402

    ReinforcementOfTheArmy = 32807846
    FoolishBurialGoods = 35726888
    UpstartGoblin = 70368879
    MetalfoesFusion = 73594093
    TwinTwisters = 43898403
    SolemnJudgment = 41420027
    SolemnWarning = 84749824

    BorrelswordDragon = 85289965
    TopologicBomberDragon = 5821478
    KnightmareUnicorn = 38342335
    KnightmarePhoenix = 2857636
    KnightmareCerberus = 75452921
    CrystronHalqifibrax = 50588353
    Linkuriboh = 41999284


class SkyStrikerExecutor(DefaultExecutor):
    DECK_EXECUTOR = True

    def __init__(self):
        super().__init__()
        self.KagariSummoned = False
        self.ShizukuSummoned = False
        self.HayateSummoned = False
        self.BorrelswordAttackEffectUsed = False
        self.BorrelswordPositionEffectUsed = False
        self.GlowUpBulbEffectUsed = False  # Do not reset it
        self.BorrelswordComboStarted = False
        self.TopologicComboStarted = False
        self.NormalSummoned = False
        self.RayeGraveEffectUsed = False
        self.AreaZeroSetForJamming = False
        self.WidowAnchorTakeControl = False
        self.SharkCannonBanishOnly = False
        self.WidowAnchorTarget = None
        self.SharkCannonTarget = None
        self.CurrentChainHandledCards = []
        self.MultiroleSetCards = []
        self.ControlledEnemyCards = []

        A, S, SS, SET = ExecutorType.Activate, ExecutorType.Summon, ExecutorType.SpSummon, ExecutorType.SpellSet
        self.AddExecutor(A, CardId.AshBlossom, self.DefaultAshBlossomAndJoyousSpring)
        self.AddExecutor(A, CardId.GhostOgre, self.DefaultGhostOgreAndSnowRabbit)
        self.AddExecutor(A, CardId.EffectVeiler, self.DefaultEffectVeiler)
        self.AddExecutor(A, CardId.MaxxC, self.DefaultMaxxC)
        self.AddExecutor(A, CardId.SolemnWarning, self.DefaultSolemnWarning)
        self.AddExecutor(A, CardId.SolemnJudgment, self.DefaultSolemnJudgment)

        self.AddExecutor(A, CardId.Raye, self.RayeEffect)
        self.AddExecutor(A, CardId.TwinTwisters, self.TwinTwistersEffect)

        self.AddExecutor(A, CardId.ReinforcementOfTheArmy, self.ReinforcementOfTheArmyEffect)
        self.AddExecutor(A, CardId.FoolishBurialGoods, self.FoolishBurialGoodsEffect)
        self.AddExecutor(A, CardId.UpstartGoblin)

        self.AddExecutor(A, CardId.Multirole, self.MultiroleActivation)
        self.AddExecutor(A, CardId.WidowAnchor, self.WidowAnchorEffectFirst)
        self.AddExecutor(A, CardId.Afterburners, self.AfterburnersEffect)
        self.AddExecutor(A, CardId.JammingWaves, self.JammingWavesEffect)
        self.AddExecutor(SET, CardId.AreaZero, self.AreaZeroSetForJammingWaves)

        self.AddExecutor(A, CardId.WidowAnchor, self.WidowAnchorEffect)
        self.AddExecutor(A, CardId.SharkCannon, self.SharkCannonEffect)
        self.AddExecutor(A, CardId.Multirole, self.MultiroleIgnitionEffect)

        self.AddExecutor(A, CardId.Engage, self.EngageEffect)
        self.AddExecutor(A, CardId.HornetDrones, self.HornetDronesEffect)

        self.AddExecutor(A, CardId.MetalfoesFusion, self.MetalfoesFusionEffect)

        self.AddExecutor(SS, CardId.Linkuriboh, self.LinkuribohSummon)
        self.AddExecutor(SS, CardId.Kagari, self.KagariSummon)
        self.AddExecutor(A, CardId.Kagari, self.KagariEffect)

        self.AddExecutor(S, CardId.GlowUpBulb, self.TunerSummon)
        self.AddExecutor(S, CardId.EffectVeiler, self.TunerSummon)
        self.AddExecutor(S, CardId.GhostOgre, self.TunerSummon)
        self.AddExecutor(S, CardId.AshBlossom, self.TunerSummon)
        self.AddExecutor(SS, CardId.CrystronHalqifibrax, self.CrystronHalqifibraxSummon)
        self.AddExecutor(A, CardId.CrystronHalqifibrax, self.CrystronHalqifibraxEffect)
        self.AddExecutor(A, CardId.Linkuriboh, self.LinkuribohEffect)
        self.AddExecutor(A, CardId.GlowUpBulb, self.GlowUpBulbEffect)
        self.AddExecutor(SS, CardId.BorrelswordDragon, self.BorrelswordDragonSummon)
        self.AddExecutor(A, CardId.BorrelswordDragon, self.BorrelswordDragonEffect)

        self.AddExecutor(SS, CardId.KnightmarePhoenix, self.KnightmarePhoenixSummon)
        self.AddExecutor(A, CardId.KnightmarePhoenix, self.KnightmarePhoenixEffect)
        self.AddExecutor(SS, CardId.KnightmareCerberus, self.KnightmareCerberusSummon)
        self.AddExecutor(A, CardId.KnightmareCerberus, self.KnightmareCerberusEffect)
        self.AddExecutor(SS, CardId.KnightmareUnicorn, self.KnightmareUnicornSummon)
        self.AddExecutor(A, CardId.KnightmareUnicorn, self.KnightmareUnicornEffect)
        self.AddExecutor(SS, CardId.TopologicBomberDragon, self.TopologicBomberDragonSummon)
        self.AddExecutor(SS, CardId.KnightmarePhoenix, self.KnightmarePhoenixUnlockSummon)
        self.AddExecutor(SS, CardId.KnightmareCerberus, self.KnightmareCerberusUnlockSummon)

        self.AddExecutor(SS, CardId.Hayate, self.HayateSummon)
        self.AddExecutor(A, CardId.Hayate, self.HayateEffect)
        self.AddExecutor(SS, CardId.Shizuku, self.ShizukuSummon)
        self.AddExecutor(A, CardId.AreaZero, self.AreaZeroEffect)
        self.AddExecutor(S, CardId.Raye, self.RayeSummon)

        self.AddExecutor(A, CardId.HerculesBase, self.HerculesBaseEffect)

        # When Widow Anchor is absent from the GY, Shizuku can search it first,
        # use it on Shizuku, and let Multirole set it immediately afterwards.
        self.AddExecutor(A, CardId.Shizuku, self.ShizukuFirstEndPhaseEffect)
        self.AddExecutor(A, CardId.WidowAnchor, self.WidowAnchorEndPhaseEffect)
        self.AddExecutor(A, CardId.Multirole, self.MultiroleEndPhaseEffect)
        self.AddExecutor(A, CardId.Shizuku, self.ShizukuEffect)

        self.AddExecutor(SET, CardId.HornetDrones, self.SetHornetDrones)
        self.AddExecutor(SET, CardId.SolemnWarning, lambda: self.Util.IsTurn1OrMain2())
        self.AddExecutor(SET, CardId.SolemnJudgment, lambda: self.Util.IsTurn1OrMain2())
        self.AddExecutor(SET, CardId.WidowAnchor, lambda: self.Util.IsTurn1OrMain2())
        self.AddExecutor(SET, CardId.SharkCannon, lambda: self.Util.IsTurn1OrMain2())
        self.AddExecutor(SET, CardId.TwinTwisters, lambda: self.Util.IsTurn1OrMain2())
        self.AddExecutor(SET, CardId.MetalfoesFusion, lambda: self.Util.IsTurn1OrMain2())
        self.AddExecutor(SET, CardId.HerculesBase, self.SetWhenHandIsFull)

        self.AddExecutor(ExecutorType.Repos, self.DefaultMonsterRepos)

    # --- overrides ---------------------------------------------------------------------------------------
    def OnSelectHand(self):
        return True

    def OnNewTurn(self):
        self.KagariSummoned = False
        self.ShizukuSummoned = False
        self.HayateSummoned = False
        self.BorrelswordAttackEffectUsed = False
        self.BorrelswordPositionEffectUsed = False
        self.BorrelswordComboStarted = False
        self.TopologicComboStarted = False
        self.NormalSummoned = False
        self.RayeGraveEffectUsed = False
        self.AreaZeroSetForJamming = False
        self.WidowAnchorTakeControl = False
        self.SharkCannonBanishOnly = False
        self.WidowAnchorTarget = None
        self.SharkCannonTarget = None
        self.ControlledEnemyCards[:] = [card for card in self.ControlledEnemyCards
                                        if not (card is None or card.Controller != 0 or
                                                card.Location != CardLocation.MonsterZone)]
        self.CurrentChainHandledCards.clear()
        super().OnNewTurn()

    def OnSummoning(self):
        if self.Duel.LastSummonPlayer == 0:
            self.NormalSummoned = True
        super().OnSummoning()

    def OnChainEnd(self):
        self.CurrentChainHandledCards.clear()
        super().OnChainEnd()

    def OnMove(self, card, previousControler, previousLocation, currentControler, currentLocation):
        solving = self.Duel.GetCurrentSolvingChainInfo()
        tracked = FindMovedCard(self.MultiroleSetCards, card, previousControler, previousLocation)
        if card is not None and tracked is not None:
            if currentControler != 0 or currentLocation != CardLocation.SpellZone:
                self.MultiroleSetCards.remove(tracked)
            else:
                self.MultiroleSetCards[self.MultiroleSetCards.index(tracked)] = card

        tracked = FindMovedCard(self.ControlledEnemyCards, card, previousControler, previousLocation)
        if card is not None and tracked is not None:
            if currentControler != 0 or (currentLocation & CardLocation.MonsterZone) == 0:
                self.ControlledEnemyCards.remove(tracked)
            else:
                self.ControlledEnemyCards[self.ControlledEnemyCards.index(tracked)] = card

        if card is not None and previousControler == 0 and currentControler == 0 and \
                previousLocation == CardLocation.Grave and \
                currentLocation == CardLocation.SpellZone and \
                solving is not None and solving.ActivatePlayer == 0 and \
                solving.IsActivateCode(CardId.Multirole):
            self.MultiroleSetCards.append(card)

        gainedEnemyMonster = card is not None and previousControler == 1 and currentControler == 0 and \
            (currentLocation & CardLocation.MonsterZone) != 0 and \
            solving is not None and solving.ActivatePlayer == 0 and \
            solving.IsActivateCode(CardId.WidowAnchor, CardId.SharkCannon)
        if gainedEnemyMonster:
            if card not in self.ControlledEnemyCards:
                self.ControlledEnemyCards.append(card)
            if solving.IsActivateCode(CardId.WidowAnchor):
                self.WidowAnchorTarget = card

        if card is not None and currentControler == 0 and \
                (previousLocation & CardLocation.MonsterZone) == 0 and \
                (currentLocation & CardLocation.MonsterZone) != 0:
            if card.IsCode(CardId.Kagari):
                self.KagariSummoned = True
            elif card.IsCode(CardId.Shizuku):
                self.ShizukuSummoned = True
            elif card.IsCode(CardId.Hayate):
                self.HayateSummoned = True
        super().OnMove(card, previousControler, previousLocation, currentControler, currentLocation)

    def OnSelectCard(self, cards, min_, max_, hint, cancelable):
        solving = self.Duel.GetCurrentSolvingChainInfo()
        if solving is not None and solving.ActivatePlayer == 0 and solving.IsActivateCode(CardId.Multirole):
            ordered = self.OrderCardsById(cards, [
                CardId.Engage,
                CardId.WidowAnchor,
                CardId.SharkCannon,
                CardId.HornetDrones,
                CardId.Afterburners,
                CardId.JammingWaves,
            ], True)
            return self.Util.CheckSelectCount(ordered, cards, min_, max_)

        if solving is not None and solving.ActivatePlayer == 0 and solving.IsActivateCode(CardId.AreaZero):
            ordered = self.OrderCardsById(cards, self.GetSkyStrikerSearchPriority(True), False)
            return self.Util.CheckSelectCount(ordered, cards, min_, max_)

        return super().OnSelectCard(cards, min_, max_, hint, cancelable)

    def OnSelectPlace(self, cardId, player, location, available):
        if player == 0 and location == CardLocation.MonsterZone:
            if cardId == CardId.TopologicBomberDragon and (available & Zones.ExtraMonsterZones) != 0:
                return available & Zones.ExtraMonsterZones

            shouldTriggerTopologic = False
            topologicLinkedZones = 0
            topologic = next((card for card in self.Bot.GetMonsters()
                              if card.IsCode(CardId.TopologicBomberDragon) and not card.IsDisabled()), None)
            if topologic is not None:
                topologicLinkedZones = topologic.GetLinkedZones() & available & Zones.MainMonsterZones
                problematic = self.Util.GetProblematicEnemyMonster()
                shouldTriggerTopologic = topologicLinkedZones != 0 and \
                    (len(self.Enemy.GetMonstersInMainZone()) >= 2 or
                     (problematic is not None and problematic.Sequence < 5))

            if shouldTriggerTopologic:
                return topologicLinkedZones & -topologicLinkedZones

            shouldAvoidTopologicLinkedZones = topologicLinkedZones != 0 and (available & ~topologicLinkedZones) != 0
            if shouldAvoidTopologicLinkedZones:
                available &= ~topologicLinkedZones

            if (cardId == CardId.KnightmarePhoenix or cardId == CardId.KnightmareCerberus) and \
                    (available & Zones.ExtraMonsterZones) != 0:
                return available & Zones.ExtraMonsterZones

            if cardId == CardId.Hayate and (available & Zones.z5) != 0:
                return Zones.z5

            hayate = GetFirstMatchingCard(self.Bot.MonsterZone, lambda card: card.IsCode(CardId.Hayate))
            if (hayate is not None and cardId == CardId.Linkuriboh) or \
                    (hayate is not None and cardId == CardId.CrystronHalqifibrax) or \
                    (hayate is not None and cardId == CardId.BorrelswordDragon):
                linked = hayate.GetLinkedZones() & available & Zones.MainMonsterZones
                if linked != 0:
                    return linked & -linked

            if shouldAvoidTopologicLinkedZones:
                return available
        return super().OnSelectPlace(cardId, player, location, available)

    def OnSelectAttacker(self, attackers, defenders):
        hayate = next((card for card in attackers if card.IsCode(CardId.Hayate)), None)
        if hayate is not None and self.GetHayateCrashTarget(hayate, defenders) is not None:
            return hayate

        if self.Bot.HasInMonstersZone(CardId.BorrelswordDragon, True):
            raye = next((card for card in attackers if card.IsCode(CardId.Raye)), None)
            if raye is not None:
                return raye

            borrelsword = next((card for card in attackers if card.IsCode(CardId.BorrelswordDragon)), None)
            if borrelsword is not None:
                return borrelsword
        return super().OnSelectAttacker(attackers, defenders)

    def OnBattle(self, attackers, defenders):
        if len(defenders) == 0 and self.Bot.HasInMonstersZone(CardId.BorrelswordDragon, True):
            raye = next((card for card in attackers if card.IsCode(CardId.Raye)), None)
            if raye is not None:
                return self.AI.Attack(raye, None)
        return super().OnBattle(attackers, defenders)

    def OnSelectAttackTarget(self, attacker, defenders):
        if attacker.IsCode(CardId.Hayate):
            target = self.GetHayateCrashTarget(attacker, defenders)
            if target is not None:
                return self.AI.Attack(attacker, target)
            if attacker.CanDirectAttack:
                return self.AI.Attack(attacker, None)
        return super().OnSelectAttackTarget(attacker, defenders)

    def OnPreBattleBetween(self, attacker, defender):
        if not defender.IsMonsterHasPreventActivationEffectInBattle() and \
                attacker.IsCode(CardId.BorrelswordDragon) and not attacker.IsDisabled() and \
                not self.BorrelswordAttackEffectUsed and defender.IsFaceup():
            halfAttack = (defender.Attack + 1) // 2
            attacker.RealPower += halfAttack
            if defender.IsAttack():
                defender.RealPower = halfAttack
        return super().OnPreBattleBetween(attacker, defender)

    def OnSelectYesNo(self, desc):
        Util = self.Util
        if desc == Util.GetStringId(CardId.Engage, 0):
            return True
        if desc == Util.GetStringId(CardId.AreaZero, 2):
            return True
        if desc == Util.GetStringId(CardId.WidowAnchor, 0):
            if self.Duel.Player == 1:
                if self.Bot.UnderAttack and self.WidowAnchorTakeControl and \
                        self.WidowAnchorTarget == self.Enemy.BattlingMonster:
                    return True
                return not any(card.IsFacedown() and card.IsCode(CardId.WidowAnchor) for card in self.Bot.GetSpells())
            return self.WidowAnchorTakeControl and self.WidowAnchorTarget is not None
        if desc == Util.GetStringId(CardId.SharkCannon, 0):
            return not self.SharkCannonBanishOnly and self.SharkCannonTarget is not None and \
                self.ShouldReviveWithSharkCannon(self.SharkCannonTarget)
        if desc == Util.GetStringId(CardId.KnightmarePhoenix, 1) or \
                desc == Util.GetStringId(CardId.KnightmareCerberus, 1) or \
                desc == Util.GetStringId(CardId.KnightmareUnicorn, 1):
            return True
        if desc == Util.GetStringId(CardId.JammingWaves, 0):
            target = Util.GetBestEnemyMonster()
            if target is None:
                return False
            self.AI.SelectCard(target)
            return True
        if desc == Util.GetStringId(CardId.Afterburners, 0):
            target = Util.GetBestEnemySpell()
            if target is None:
                return False
            self.AI.SelectCard(target)
            return True
        return super().OnSelectYesNo(desc)

    # --- rows --------------------------------------------------------------------------------------------
    def ReinforcementOfTheArmyEffect(self):
        self.AI.SelectCard(CardId.Raye)
        return True

    def FoolishBurialGoodsEffect(self):
        if self.Bot.HasInDeck(CardId.MetalfoesFusion):
            self.AI.SelectCard(CardId.MetalfoesFusion)
        elif not self.KagariSummoned and self.Bot.HasInExtra(CardId.Kagari):
            self.AI.SelectCard(CardId.Engage, CardId.WidowAnchor, CardId.HornetDrones)
        else:
            self.AI.SelectCard(CardId.ReinforcementOfTheArmy, CardId.UpstartGoblin, CardId.TwinTwisters)
        return True

    def TwinTwistersEffect(self):
        if self.Util.ChainContainsCard(CardId.TwinTwisters):
            return False

        targets = [card for card in self.Enemy.GetSpells()
                   if card.IsFloodgate() or card.IsFacedown() or
                   card.HasType(CardType.Continuous) or card.HasType(CardType.Equip) or
                   card.HasType(CardType.Field) or card.HasType(CardType.Pendulum)]
        targets = list(dict.fromkeys(card for card in targets if not self.IsCurrentChainHandled(card)))
        if len(targets) == 0:
            return False

        hasPriorityTarget = any(card.IsFloodgate() or card.IsFaceup() for card in targets)
        if self.Duel.Player == 1 and not hasPriorityTarget and self.Duel.Phase != DuelPhase.End and \
                len(targets) < 2:
            return False

        targets = sorted(targets, key=lambda card: 0 if card.IsFloodgate() else 1 if card.IsFaceup() else 2)[:2]

        for target in targets:
            self.MarkCurrentChainHandled(target)
        self.SelectDiscard()
        self.AI.SelectNextCard(targets)
        return True

    def MultiroleActivation(self):
        return self.Card.Location == CardLocation.Hand or self.Card.IsFacedown()

    def MultiroleIgnitionEffect(self):
        Bot, Duel = self.Bot, self.Duel
        if self.Card.Location != CardLocation.SpellZone or self.Card.IsFacedown() or \
                (Duel.Phase != DuelPhase.Main1 and Duel.Phase != DuelPhase.Main2):
            return False

        stolen = next((card for card in Bot.GetMonsters() if card in self.ControlledEnemyCards), None)
        if stolen is not None and Duel.Phase == DuelPhase.Main2:
            self.AI.SelectCard(stolen)
            return True

        raye = next((card for card in Bot.GetMonsters()
                     if card.IsCode(CardId.Raye) and Bot.GetMonstersExtraZoneCount() == 0), None)
        if raye is not None and self.HasAvailableRayeExtraDeckTarget():
            self.AI.SelectCard(raye)
            return True

        areaZero = Bot.GetFieldSpellCard()
        if areaZero is not None and areaZero.IsCode(CardId.AreaZero) and \
                Bot.GetMonsterCount() == 0 and Bot.HasInDeck(CardId.Raye):
            self.AI.SelectCard(areaZero)
            return True

        preserveHornetDrones = self.HasTopologicComboPayoff() and \
            (self.TopologicComboStarted or self.ShouldStartTopologicCombo())
        spent = sorted((card for card in Bot.GetSpells()
                        if card != self.Card and card.IsSpell() and card not in self.MultiroleSetCards and
                        not card.IsCode(CardId.WidowAnchor, CardId.Engage) and
                        (not preserveHornetDrones or not card.IsCode(CardId.HornetDrones))),
                       key=lambda card: 0 if card.Id == CardId.MetalfoesFusion else 1)
        spentSpell = spent[0] if spent else None
        if spentSpell is not None and \
                (sum(1 for card in Bot.Graveyard if card.IsSpell()) == 2 or spentSpell.Id == CardId.MetalfoesFusion):
            self.AI.SelectCard(spentSpell)
            return True
        return False

    def MultiroleEndPhaseEffect(self):
        return self.Duel.Phase == DuelPhase.End

    def AfterburnersEffect(self):
        target = self.GetEnemyMonsterTarget(False)
        if target is None:
            return False
        self.MarkCurrentChainHandled(target)
        self.AI.SelectCard(target)
        return True

    def JammingWavesEffect(self):
        target = next((card for card in self.Enemy.GetSpells() if card.IsFacedown()), None)
        if target is None:
            field = self.Bot.GetFieldSpellCard()
            if field is not None and field.IsFacedown():
                target = field
        if target is None:
            return False
        self.AreaZeroSetForJamming = False
        self.MarkCurrentChainHandled(target)
        self.AI.SelectCard(target)
        return True

    def EngageEffect(self):
        self.AI.SelectCard(self.GetSkyStrikerSearchPriority(False))
        return True

    def HornetDronesEffect(self):
        Bot, Duel = self.Bot, self.Duel
        if Bot.HasInMonstersZone(CardId.TopologicBomberDragon, True) and \
                len(self.Enemy.GetMonstersInMainZone()) >= 2 and \
                not any(chain.ActivatePlayer == 0 and
                        chain.IsActivateCode(CardId.TopologicBomberDragon, CardId.HornetDrones)
                        for chain in Duel.CurrentChainInfo):
            return True

        if len(Duel.CurrentChain) > 0 or Duel.Player == 1:
            return False

        if Duel.Phase != DuelPhase.Main1:
            return False

        if Bot.GetMonstersExtraZoneCount() == 0:
            return True

        if not Bot.HasInMonstersZone(CardId.Linkuriboh):
            if not self.ShouldStartBorrelswordCombo(True):
                return False
            self.BorrelswordComboStarted = True
            return True

        return False

    def WidowAnchorEffectFirst(self):
        Duel = self.Duel
        if Duel.Player != 0 or len(Duel.CurrentChain) > 0:
            return False

        target = self.GetEnemyMonsterTarget(True)
        if target is None:
            return False

        canTakeControl = self.CanImmediatelyUseControlledMonster(target, Duel.Phase < DuelPhase.Main2)
        shouldNegate = target.IsFloodgate() or target.IsMonsterDangerous() or \
            target.IsMonsterInvincible() or target.IsMonsterShouldBeDisabledBeforeItUseEffect()
        if not shouldNegate and not canTakeControl:
            return False
        if not canTakeControl and self.Bot.HasInHand(CardId.Afterburners):
            return False

        self.WidowAnchorTarget = target
        self.WidowAnchorTakeControl = canTakeControl
        self.MarkCurrentChainHandled(target)
        self.AI.SelectCard(target)
        return True

    def WidowAnchorEffect(self):
        Bot, Duel = self.Bot, self.Duel
        if any(card.Controller == 0 and card.IsCode(CardId.WidowAnchor) for card in Duel.CurrentChain):
            return False

        target = self.Enemy.BattlingMonster
        if len(Duel.CurrentChain) == 0 and Duel.Player == 1 and Bot.UnderAttack and \
                self.HaveThreeSpellsInGrave() and target is not None and \
                target.HasType(CardType.Effect) and not target.IsDisabled() and \
                not target.IsShouldNotBeTarget() and not target.IsShouldNotBeSpellTrapTarget():
            defender = Bot.BattlingMonster
            defenderPower = 0 if defender is None else defender.GetDefensePower()
            wouldDestroyDefender = defender is not None and \
                (target.Attack > defenderPower or target.Attack == defenderPower and defender.IsAttack())
            battleDamage = target.Attack if defender is None else \
                max(0, target.Attack - defenderPower) if defender.IsAttack() else 0
            shouldStopAttack = battleDamage >= 2000 or battleDamage >= Bot.LifePoints or \
                wouldDestroyDefender and not self.IsDisposableMonster(defender)
            if shouldStopAttack:
                self.WidowAnchorTarget = target
                self.WidowAnchorTakeControl = True
                self.MarkCurrentChainHandled(target)
                self.AI.SelectCard(target)
                return True

        target = self.DefaultGetDisableMonsterTarget()
        if target is not None:
            self.WidowAnchorTarget = target
            self.WidowAnchorTakeControl = self.CanImmediatelyUseControlledMonster(
                target, Duel.Player == 0 and Duel.Phase < DuelPhase.Main2)
            self.MarkCurrentChainHandled(target)
            self.AI.SelectCard(target)
            return True

        if len(Duel.CurrentChain) > 0 or not self.HaveThreeSpellsInGrave() or Duel.Player != 0 or \
                Duel.Phase < DuelPhase.Main1 or Duel.Phase >= DuelPhase.Main2:
            return False

        target = self.GetEnemyMonsterTarget(False)
        if target is None or target.IsDisabled() or target.HasType(CardType.Normal):
            return False
        if not self.CanImmediatelyUseControlledMonster(target, True):
            return False
        self.WidowAnchorTakeControl = True
        self.WidowAnchorTarget = target
        self.MarkCurrentChainHandled(target)
        self.AI.SelectCard(target)
        return True

    def CanImmediatelyUseControlledMonster(self, target, canAttack):
        Bot, Duel, Util = self.Bot, self.Duel, self.Util
        if target is None or target.Controller != 1 or not self.HaveThreeSpellsInGrave() or Duel.Phase == DuelPhase.End:
            return False
        if Duel.Player == 1:
            return True

        if target.IsCode(CardId.Raye, CardId.Kagari, CardId.Shizuku, CardId.Hayate):
            canSummonKagari = not target.IsCode(CardId.Kagari) and not self.KagariSummoned and \
                Bot.HasInExtra(CardId.Kagari)
            canSummonHayate = not target.IsCode(CardId.Hayate) and not self.HayateSummoned and \
                Bot.HasInExtra(CardId.Hayate)
            if canSummonKagari or canSummonHayate:
                return True

        monsters = [card for card in Bot.GetMonsters()
                    if card.IsFaceup() and not card.IsCode(CardId.BorrelswordDragon)]
        hasDifferentNameMaterial = any(card.Id != target.Id for card in monsters)
        if hasDifferentNameMaterial:
            canUsePhoenix = Bot.HasInExtra(CardId.KnightmarePhoenix) and \
                Util.GetProblematicEnemySpell() is not None
            cerberusTarget = self.GetProblematicKnightmareCerberusTarget()
            canUseCerberus = Bot.HasInExtra(CardId.KnightmareCerberus) and \
                cerberusTarget is not None and cerberusTarget != target
            canUnlockSpell = \
                Bot.HasInHandOrInSpellZone([
                    CardId.Engage,
                    CardId.HornetDrones,
                    CardId.Afterburners,
                    CardId.JammingWaves,
                    CardId.SharkCannon,
                ]) and Bot.HasInExtra([
                    CardId.KnightmarePhoenix,
                    CardId.KnightmareCerberus,
                ])
            if canUsePhoenix or canUseCerberus or canUnlockSpell:
                return True

        if canAttack and target.Attack >= 2000:
            return True

        if Bot.HasInExtra(CardId.KnightmareUnicorn) and \
                Util.GetProblematicEnemyCard(0, True) is not None:
            if any(card.Id != target.Id and
                   (card.HasType(CardType.Link) and card.LinkCount == 2 or
                    target.HasType(CardType.Link) and target.LinkCount == 2) for card in monsters):
                return True
            if len({card.Id for card in monsters if card.Id != target.Id}) >= 2:
                return True

        if not Bot.HasInExtra(CardId.BorrelswordDragon) or not target.HasType(CardType.Effect):
            return False
        effectMonsters = [card for card in monsters if card.HasType(CardType.Effect)]
        effectMonsters.append(target)
        subsetCount = 1 << len(effectMonsters)
        for mask in range(1, subsetCount):
            selected = [effectMonsters[i] for i in range(len(effectMonsters)) if (mask & (1 << i)) != 0]
            if 3 <= len(selected) <= 4 and target in selected and CanMakeLinkRating(selected, 4):
                return True
        return False

    def SharkCannonEffect(self):
        Bot, Duel, Util = self.Bot, self.Duel, self.Util
        if Util.ChainContainsCard(CardId.SharkCannon):
            return False

        targets = sorted(self.Enemy.GetGraveyardMonsters(), key=lambda card: -card.Attack)

        lastChain = Duel.CurrentChainInfo[-1] if Duel.CurrentChainInfo else None
        if lastChain is not None and lastChain.ActivatePlayer == 1:
            chainTarget = next((card for card in targets if card in lastChain.Targets), None)
            if chainTarget is None and lastChain.HasLocation(CardLocation.Grave) and \
                    lastChain.RelatedCard is not None and lastChain.RelatedCard in targets:
                chainTarget = lastChain.RelatedCard
            if chainTarget is not None:
                self.SharkCannonBanishOnly = True
                self.SharkCannonTarget = chainTarget
                self.AI.SelectCard(chainTarget)
                return True

        if len(Duel.CurrentChain) > 0:
            return False

        if Duel.Player != 0 or Duel.Phase != DuelPhase.Main1 or \
                not self.EmptyMainMonsterZone() or not self.HaveThreeSpellsInGrave():
            return False

        if Bot.HasInMonstersZone(CardId.BorrelswordDragon, True) and \
                not self.BorrelswordPositionEffectUsed:
            borrelswordTarget = next((card for card in targets
                                      if card.IsCanRevive() and self.IsBorrelswordTargetableMonster(card)), None)
            if borrelswordTarget is not None:
                self.SharkCannonBanishOnly = False
                self.SharkCannonTarget = borrelswordTarget
                self.AI.SelectCard(borrelswordTarget)
                self.AI.SelectPosition(CardPosition.FaceUpAttack)
                return True

        if Bot.HasInMonstersZone(CardId.TopologicBomberDragon, True):
            problematic = Util.GetProblematicEnemyMonster()
            shouldTriggerTopologic = len(self.Enemy.GetMonstersInMainZone()) >= 2 or \
                (problematic is not None and problematic.Sequence < 5)
            if not shouldTriggerTopologic:
                return False

        target = next((card for card in targets if self.ShouldReviveWithSharkCannon(card)), None)
        if target is None:
            return False

        self.SharkCannonBanishOnly = False
        self.SharkCannonTarget = target
        self.AI.SelectCard(target)
        return True

    def ShouldReviveWithSharkCannon(self, target):
        if not target.IsCanRevive():
            return False
        if self.Bot.HasInMonstersZone(CardId.BorrelswordDragon, True) and \
                not self.BorrelswordPositionEffectUsed and self.IsBorrelswordTargetableMonster(target):
            return True
        return self.CanImmediatelyUseControlledMonster(target, False)

    def HerculesBaseEffect(self):
        Bot = self.Bot
        if self.Card.Location == CardLocation.SpellZone and not self.Card.IsFacedown():
            return True

        if self.Card.Location == CardLocation.Grave:
            targets = [card for card in Bot.Graveyard
                       if not card.IsCode(CardId.HerculesBase) and card.HasSetcode(0x115)]
            self.AI.SelectCard(self.OrderCardsById(targets, [
                CardId.Engage,
                CardId.Kagari,
                CardId.Shizuku,
                CardId.WidowAnchor,
                CardId.HornetDrones,
                CardId.SharkCannon,
                CardId.Afterburners,
                CardId.JammingWaves,
                CardId.Hayate,
                CardId.Raye,
                CardId.AreaZero,
                CardId.Multirole,
            ], False))
            return True

        if self.Util.IsTurn1OrMain2():
            return False
        monster = self.Util.GetBestBotMonster(True)
        if monster is None:
            return False

        beatable = sum(1 for target in self.Enemy.GetMonsters()
                       if target.GetDefensePower() < monster.Attack and not target.IsMonsterInvincible())
        if beatable == 0 or (beatable < 2 and not self.HaveThreeSpellsInGrave()):
            return False
        self.AI.SelectCard(monster)
        return True

    def AreaZeroSetForJammingWaves(self):
        Bot, Duel = self.Bot, self.Duel
        shouldSet = Duel.Player == 0 and Duel.Phase == DuelPhase.Main1 and self.EmptyMainMonsterZone() and \
            self.GetSpellCountInGrave() <= 2 and Bot.HasInHand(CardId.JammingWaves) and \
            Bot.HasInDeck(CardId.Raye) and not any(card.IsFacedown() for card in self.Enemy.GetSpells())
        if shouldSet:
            self.AreaZeroSetForJamming = True
        return shouldSet

    def AreaZeroEffect(self):
        Bot, Duel, Card_ = self.Bot, self.Duel, self.Card
        if Card_.Location == CardLocation.Hand:
            return Bot.GetFieldSpellCard() is None
        if Card_.IsFacedown():
            return not self.AreaZeroSetForJamming
        if Card_.Location == CardLocation.Grave:
            return Bot.GetMonsterCount() == 0 or not self.EmptyMainMonsterZone() or Duel.Player == 1

        if Card_.Location != CardLocation.SpellZone and Card_.Location != CardLocation.FieldZone:
            return False

        mainMonsters = Bot.GetMonstersInMainZone()
        hasBlockedSpell = self.HasUsefulBlockedSkyStrikerSpell()
        controlledMonster = next((card for card in mainMonsters if card in self.ControlledEnemyCards), None)
        if controlledMonster is not None and \
                (hasBlockedSpell or Duel.Phase == DuelPhase.Main2):
            self.AI.SelectCard(controlledMonster)
            return True

        disposable = sorted((card for card in mainMonsters if self.IsDisposableMonster(card)),
                            key=self.GetLinkMaterialValue)
        disposableMonster = disposable[0] if disposable else None
        if disposableMonster is not None and \
                (hasBlockedSpell or Duel.Phase == DuelPhase.Main2):
            self.AI.SelectCard(disposableMonster)
            return True

        raye = next((card for card in mainMonsters if card.IsCode(CardId.Raye)), None)
        if raye is not None and len(mainMonsters) == 1 and Bot.GetMonstersExtraZoneCount() == 0 and \
                self.HasAvailableRayeExtraDeckTarget():
            self.AI.SelectCard(raye)
            return True

        if Duel.Phase != DuelPhase.Main2 and not self.SetWhenHandIsFull():
            return False
        spentSpell = next((card for card in Bot.GetSpells()
                           if card != Card_ and card.IsSpell() and
                           not card.IsCode(CardId.Multirole, CardId.Engage, CardId.WidowAnchor,
                                           CardId.HornetDrones, CardId.SharkCannon)), None)
        if spentSpell is None:
            return False
        self.AI.SelectCard(spentSpell)
        return True

    def RayeSummon(self):
        return self.Bot.GetMonstersExtraZoneCount() == 0 or \
            (self.Enemy.GetMonsterCount() == 0 and self.Duel.Phase == DuelPhase.Main1)

    def HasAvailableRayeExtraDeckTarget(self):
        Bot = self.Bot
        return (not self.KagariSummoned and Bot.HasInExtra(CardId.Kagari)) or \
            (not self.ShizukuSummoned and Bot.HasInExtra(CardId.Shizuku)) or \
            (not self.HayateSummoned and Bot.HasInExtra(CardId.Hayate))

    def RayeEffect(self):
        Bot, Duel, Card_ = self.Bot, self.Duel, self.Card
        if self.DefaultCheckWhetherCardIsNegated(Card_):
            return False
        if Card_.Location == CardLocation.Grave:
            if self.RayeGraveEffectUsed:
                return False
            self.RayeGraveEffectUsed = True
            self.AI.SelectPosition(CardPosition.FaceUpAttack if Duel.Player == 0 else CardPosition.FaceUpDefence)
            return True
        shouldTag = self.Util.IsChainTarget(Card_) or \
            Card_ == Bot.BattlingMonster and Duel.Player == 1 or \
            Duel.Player == 0 and Duel.Phase == DuelPhase.Main2

        if Duel.Player == 0 and DuelPhase.Main1 < Duel.Phase < DuelPhase.Main2 and Card_.Attacked:
            if Bot.HasInMonstersZone(CardId.BorrelswordDragon, True) and \
                    not self.BorrelswordPositionEffectUsed:
                return False
            shouldTag = True

        if not shouldTag:
            return False
        self.RayeSelectTarget()
        return True

    def RayeSelectTarget(self):
        Bot, Duel = self.Bot, self.Duel
        if DuelPhase.Main1 < Duel.Phase < DuelPhase.Main2 and \
                Bot.HasInMonstersZone(CardId.BorrelswordDragon, True) and not self.ShizukuSummoned:
            self.AI.SelectCard(CardId.Shizuku, CardId.Kagari, CardId.Hayate)
            return

        if not self.KagariSummoned and Bot.HasInGraveyard([
            CardId.Engage,
            CardId.HornetDrones,
            CardId.WidowAnchor,
            CardId.Afterburners,
            CardId.JammingWaves,
        ]):
            self.AI.SelectCard(CardId.Kagari, CardId.Shizuku, CardId.Hayate)
        else:
            self.AI.SelectCard(CardId.Shizuku, CardId.Kagari, CardId.Hayate)

    def KagariSummon(self):
        if self.KagariSummoned:
            return False
        if not self.Bot.HasInGraveyard([
            CardId.Engage,
            CardId.HornetDrones,
            CardId.WidowAnchor,
            CardId.Afterburners,
            CardId.JammingWaves,
        ]):
            return False
        self.KagariSummoned = True
        return True

    def KagariEffect(self):
        Bot, Util = self.Bot, self.Util
        if self.DefaultCheckWhetherCardIsNegated(self.Card):
            return False
        target = next((card for card in Bot.GetGraveyardSpells() if card.IsCode(CardId.Engage)), None)
        if target is None and self.EmptyMainMonsterZone() and Util.GetProblematicEnemyMonster() is not None:
            target = next((card for card in Bot.GetGraveyardSpells() if card.IsCode(CardId.Afterburners)), None)
        if target is None and self.EmptyMainMonsterZone() and Util.GetProblematicEnemySpell() is not None:
            target = next((card for card in Bot.GetGraveyardSpells() if card.IsCode(CardId.JammingWaves)), None)
        if target is not None:
            self.AI.SelectCard(target)
        else:
            self.AI.SelectCard(CardId.HornetDrones, CardId.WidowAnchor, CardId.SharkCannon, CardId.Engage)
        return True

    def HayateSummon(self):
        if self.Util.IsTurn1OrMain2():
            return False
        if self.HaveThreeSpellsInGrave() and not self.Util.IsAllEnemyBetter():
            return False
        self.HayateSummoned = True
        return True

    def HayateEffect(self):
        Bot = self.Bot
        if self.DefaultCheckWhetherCardIsNegated(self.Card):
            return False
        if Bot.HasInMonstersZone(CardId.BorrelswordDragon, True) and \
                not Bot.HasInGraveyard(CardId.Raye) and Bot.HasInDeck(CardId.Raye):
            self.AI.SelectCard(CardId.Raye)
        elif not self.KagariSummoned and not Bot.HasInGraveyard(CardId.Engage) and Bot.HasInDeck(CardId.Engage):
            self.AI.SelectCard(CardId.Engage)
        elif not self.HaveThreeSpellsInGrave():
            self.AI.SelectCard(CardId.Engage, CardId.WidowAnchor, CardId.HornetDrones, CardId.SharkCannon)
        elif not Bot.HasInGraveyard(CardId.Raye) and Bot.HasInDeck(CardId.Raye):
            self.AI.SelectCard(CardId.Raye)
        else:
            self.AI.SelectCard(CardId.Engage, CardId.WidowAnchor, CardId.HornetDrones, CardId.SharkCannon)
        return True

    def GetHayateCrashTarget(self, hayate, defenders):
        Bot, Duel = self.Bot, self.Duel
        if Duel.Player != 0 or Duel.Phase <= DuelPhase.Main1 or Duel.Phase >= DuelPhase.Main2:
            return None
        if not Bot.HasInMonstersZone(CardId.BorrelswordDragon, True) or \
                self.RayeGraveEffectUsed or hayate.IsDisabled() or \
                not Bot.HasInGraveyard(CardId.Raye):
            return None

        crash = sorted((card for card in defenders if self.IsHayateCrashTarget(hayate, card)),
                       key=lambda card: card.GetDefensePower())
        return crash[0] if crash else None

    def IsHayateCrashTarget(self, hayate, target):
        if hayate is None or target is None or not target.IsAttack() or \
                target.IsMonsterHasPreventActivationEffectInBattle():
            return False
        hayatePower = hayate.GetAttackPower()
        return target.GetDefensePower() >= hayatePower and \
            target.GetDefensePower() - hayatePower < self.Bot.LifePoints

    def IsBorrelswordPositionTarget(self, target):
        return target is not None and target.IsFaceup() and target.IsAttack() and \
            self.IsBorrelswordTargetableMonster(target)

    def IsBorrelswordTargetableMonster(self, target):
        return target is not None and not target.HasType(CardType.Link) and \
            not target.IsShouldNotBeTarget() and not target.IsShouldNotBeMonsterTarget()

    def CanPrepareBorrelswordTargetWithSharkCannon(self):
        return self.HaveThreeSpellsInGrave() and \
            self.Bot.HasInHandOrInSpellZone(CardId.SharkCannon) and \
            any(card.IsCanRevive() and self.IsBorrelswordTargetableMonster(card)
                for card in self.Enemy.GetGraveyardMonsters())

    def CanUseGlowUpBulbEffect(self):
        return not self.GlowUpBulbEffectUsed and \
            (self.Bot.HasInDeck(CardId.GlowUpBulb) or
             self.Bot.HasInHandOrInGraveyard(CardId.GlowUpBulb))

    def ShouldStartBorrelswordCombo(self, hornetWillProvideMaterial):
        Bot, Duel, Enemy = self.Bot, self.Duel, self.Enemy
        if Duel.Player != 0 or Duel.Turn == 1 or Duel.Phase != DuelPhase.Main1 or \
                self.NormalSummoned or \
                not Bot.HasInExtra(CardId.CrystronHalqifibrax) or \
                not Bot.HasInExtra(CardId.BorrelswordDragon) or \
                not any(card.IsTuner() for card in Bot.Hand) or \
                not self.CanUseGlowUpBulbEffect():
            return False

        canBuildCombo = Bot.GetMonsterCount() >= 2 or \
            Bot.HasInMonstersZone(CardId.Linkuriboh) or \
            Bot.HasInMonstersZone(CardId.Token) and Bot.HasInExtra(CardId.Linkuriboh) or \
            hornetWillProvideMaterial and Bot.HasInExtra(CardId.Linkuriboh)
        if not canBuildCombo:
            return False

        hayate = next((card for card in Bot.GetMonsters() if card.IsCode(CardId.Hayate)), None)
        if hayate is not None:
            return not hayate.IsDisabled() and not self.RayeGraveEffectUsed and \
                Bot.HasInGraveyard(CardId.Raye) and \
                any(self.IsHayateCrashTarget(hayate, card) for card in Enemy.GetMonsters())

        enemyPositionTargets = sum(1 for card in Enemy.GetMonsters() if self.IsBorrelswordPositionTarget(card))
        hasOwnPositionTarget = any(self.IsBorrelswordPositionTarget(card) for card in Bot.GetMonsters())
        return enemyPositionTargets >= 3 or hasOwnPositionTarget or \
            self.CanPrepareBorrelswordTargetWithSharkCannon()

    def ShouldStartTopologicCombo(self):
        Bot, Duel = self.Bot, self.Duel
        material = next((card for card in Bot.GetMonsters()
                         if card.IsFaceup() and (self.IsDisposableMonster(card) or
                                                 card.IsCode(CardId.Raye, CardId.Kagari, CardId.Hayate,
                                                             CardId.Shizuku))), None)
        hasNormalSummonTuner = any(card.IsTuner() for card in Bot.Hand)
        return Duel.Player == 0 and Duel.Phase == DuelPhase.Main1 and \
            not self.BorrelswordComboStarted and not self.TopologicComboStarted and not self.NormalSummoned and \
            material is not None and hasNormalSummonTuner and \
            self.HasTopologicComboPayoff() and \
            Bot.HasInExtra(CardId.CrystronHalqifibrax) and \
            Bot.HasInExtra(CardId.KnightmareUnicorn) and \
            Bot.HasInExtra(CardId.TopologicBomberDragon) and \
            self.CanUseGlowUpBulbEffect()

    def HasTopologicComboPayoff(self):
        return (self.Util.IsTurn1OrMain2() or len(self.Enemy.GetMonstersInMainZone()) >= 2) and \
            self.Bot.HasInHandOrInSpellZone(CardId.HornetDrones)

    def MetalfoesFusionEffect(self):
        return sum(1 for card in self.Bot.Graveyard if card.IsSpell()) > 3 or self.Bot.GetHandCount() < 3

    def LinkuribohSummon(self):
        Bot = self.Bot
        token = next((card for card in Bot.GetMonsters() if card.IsCode(CardId.Token)), None)
        if token is None or not self.BorrelswordComboStarted or \
                not Bot.HasInExtra(CardId.BorrelswordDragon):
            return False
        self.AI.SelectMaterials(token)
        return True

    def TunerSummon(self):
        Bot, Duel = self.Bot, self.Duel
        if not Bot.HasInExtra(CardId.CrystronHalqifibrax):
            return False
        if Bot.GetMonsterCount() == 0:
            return False

        borrelswordCombo = self.BorrelswordComboStarted and \
            Duel.Player == 0 and Duel.Phase == DuelPhase.Main1 and \
            Bot.HasInMonstersZone(CardId.Linkuriboh) and \
            Bot.HasInExtra(CardId.BorrelswordDragon)
        if borrelswordCombo:
            return True

        if self.Card.IsCode(CardId.GlowUpBulb) and \
                not Bot.HasInDeck([CardId.EffectVeiler, CardId.GhostOgre, CardId.AshBlossom]) and \
                not Bot.HasInHand([CardId.EffectVeiler, CardId.GhostOgre, CardId.AshBlossom]):
            return False

        topologicCombo = self.ShouldStartTopologicCombo()
        if topologicCombo:
            self.TopologicComboStarted = True
            return True

        borrelswordCombo = self.ShouldStartBorrelswordCombo(False)
        if borrelswordCombo:
            self.BorrelswordComboStarted = True
            return True

        return Bot.GetMonsterCount() > 0 and not any(card.HasSetcode(0x115) for card in Bot.ExtraDeck)

    def CrystronHalqifibraxSummon(self):
        Bot, Duel = self.Bot, self.Duel
        if Duel.Player != 0 or Duel.Phase != DuelPhase.Main1:
            return False

        if self.BorrelswordComboStarted and Bot.HasInMonstersZone(CardId.Linkuriboh):
            tuner = next((card for card in Bot.GetMonsters()
                          if card.IsTuner() and card.IsFaceup() and not card.IsCode(CardId.Hayate)), None)
            linkuriboh = next((card for card in Bot.GetMonsters() if card.IsCode(CardId.Linkuriboh)), None)
            if tuner is None or linkuriboh is None:
                return False
            self.AI.SelectMaterials([tuner, linkuriboh])
            return True

        if self.BorrelswordComboStarted or \
                (self.TopologicComboStarted and self.HasTopologicComboPayoff()):
            tuner = next((card for card in Bot.GetMonsters() if card.IsTuner() and card.IsFaceup()), None)
            rest = sorted((card for card in Bot.GetMonsters() if card != tuner and card.IsFaceup()),
                          key=self.GetLinkMaterialValue)
            material = rest[0] if rest else None
            if tuner is None or material is None:
                return False
            self.AI.SelectMaterials([tuner, material])
            return True

        comboMaterials = sorted((card for card in Bot.GetMonsters() if card.IsFaceup()),
                                key=lambda card: card.Attack)
        self.AI.SelectMaterials(comboMaterials)
        return True

    def CrystronHalqifibraxEffect(self):
        if self.DefaultCheckWhetherCardIsNegated(self.Card):
            return False
        self.AI.SelectCard(CardId.GlowUpBulb, CardId.EffectVeiler, CardId.GhostOgre, CardId.AshBlossom)
        return True

    def LinkuribohEffect(self):
        Bot, Duel = self.Bot, self.Duel
        if self.DefaultCheckWhetherCardIsNegated(self.Card):
            return False
        if self.Card.Location != CardLocation.Grave:
            return Duel.Player == 1 and Bot.BattlingMonster is not None
        if self.IsTopologicComboLinkSummonReady():
            return False
        if Duel.Player != 0 or Duel.Phase != DuelPhase.Main1 or \
                not Bot.HasInMonstersZone(CardId.CrystronHalqifibrax):
            return False

        tribute = next((card for card in Bot.GetMonsters()
                        if card.Level == 1 and card.IsTuner() and card.IsFaceup() and
                        not card.IsCode(CardId.Linkuriboh)), None)
        if tribute is None:
            return False
        self.AI.SelectCard(tribute)
        return True

    def GlowUpBulbEffect(self):
        Bot, Duel = self.Bot, self.Duel
        summonForBorrelsword = Duel.Player == 0 and Duel.Phase == DuelPhase.Main1 and \
            not self.BorrelswordPositionEffectUsed and \
            sum(1 for card in Bot.MonsterZone + self.Enemy.MonsterZone
                if card is not None and card.IsAttack() and not card.HasType(CardType.Link)) == 0 and \
            Bot.HasInMonstersZone(CardId.BorrelswordDragon, True)
        summon = summonForBorrelsword or \
            Bot.HasInMonstersZone(CardId.KnightmareUnicorn) or \
            (Bot.HasInMonstersZone(CardId.CrystronHalqifibrax) and
             Bot.HasInMonstersZone(CardId.Linkuriboh))
        if summon:
            self.GlowUpBulbEffectUsed = True
            self.AI.SelectPosition(CardPosition.FaceUpAttack if summonForBorrelsword else CardPosition.FaceUpDefence)
            return True
        return False

    def BorrelswordDragonSummon(self):
        Bot, Enemy = self.Bot, self.Enemy
        if self.Util.IsTurn1OrMain2():
            return False

        committedCombo = self.BorrelswordComboStarted
        canFinishDirectly = Enemy.GetMonsterCount() == 0 and Enemy.LifePoints <= 3000
        worthwhileBattle = sum(1 for card in Enemy.GetMonsters() if self.IsBorrelswordPositionTarget(card)) >= 3 or \
            any(self.IsBorrelswordPositionTarget(card) for card in Bot.GetMonsters()) or \
            self.CanPrepareBorrelswordTargetWithSharkCannon()
        if not committedCombo and not canFinishDirectly and not worthwhileBattle:
            return False

        halqifibrax = next((card for card in Bot.GetMonsters() if card.IsCode(CardId.CrystronHalqifibrax)), None)
        linkuriboh = next((card for card in Bot.GetMonsters() if card.IsCode(CardId.Linkuriboh)), None)
        bulb = next((card for card in Bot.GetMonsters() if card.IsCode(CardId.GlowUpBulb)), None)
        if halqifibrax is not None and linkuriboh is not None and bulb is not None:
            comboMaterials = [halqifibrax, linkuriboh, bulb]
            if GetBotAvailZonesFromExtraDeck(self.Util, comboMaterials) > 0:
                self.AI.SelectMaterials(comboMaterials)
                return True

        ordered = sorted((card for card in Bot.GetMonsters() if self.IsBorrelswordPositionTarget(card)),
                         key=lambda card: (0 if card in self.ControlledEnemyCards else 1, card.Attack))
        positionTarget = ordered[0] if ordered else None
        materials = None if positionTarget is None else \
            self.GetLinkMaterials(4, 3, 4, True, False, positionTarget)
        if materials is None:
            materials = self.GetLinkMaterials(4, 3, 4, True, False)
        if materials is None:
            return False
        self.AI.SelectMaterials(materials)
        return True

    def BorrelswordDragonEffect(self):
        Bot, Duel, Util = self.Bot, self.Duel, self.Util
        if self.ActivateDescription == -1 or \
                self.ActivateDescription == Util.GetStringId(CardId.BorrelswordDragon, 1):
            self.BorrelswordAttackEffectUsed = True
            return True

        if self.ActivateDescription != Util.GetStringId(CardId.BorrelswordDragon, 0):
            return False

        target = None
        if Duel.Player == 0 and DuelPhase.Main1 < Duel.Phase < DuelPhase.Main2:
            target = next((card for card in Bot.GetMonsters()
                           if card.IsCode(CardId.Raye) and card.IsAttack() and card.Attacked), None)
            if target is None:
                target = next((card for card in Bot.GetMonsters()
                               if card.IsAttack() and card.Attacked and not card.HasType(CardType.Link)), None)
            if target is None and self.Card.Attacked:
                ordered = sorted((card for card in self.Enemy.GetMonsters() if self.IsBorrelswordPositionTarget(card)),
                                 key=lambda card: card.Attack)
                target = ordered[0] if ordered else None
        elif Duel.Player == 1:
            ordered = sorted((card for card in self.Enemy.GetMonsters() if self.IsBorrelswordPositionTarget(card)),
                             key=lambda card: -card.Attack)
            target = ordered[0] if ordered else None

        if target is None:
            return False
        self.BorrelswordPositionEffectUsed = True
        self.AI.SelectCard(target)
        return True

    def KnightmarePhoenixSummon(self):
        if self.IsTopologicComboLinkSummonReady():
            return False
        if self.Util.GetProblematicEnemySpell() is None:
            return False
        return self.SelectKnightmareLinkMaterials(False)

    def KnightmarePhoenixEffect(self):
        if self.DefaultCheckWhetherCardIsNegated(self.Card):
            return False
        target = self.Util.GetProblematicEnemySpell()
        if target is None or self.IsCurrentChainHandled(target) or len(self.Bot.Hand) == 0:
            return False
        self.MarkCurrentChainHandled(target)
        self.SelectDiscard()
        self.AI.SelectNextCard(target)
        return True

    def KnightmareCerberusSummon(self):
        if self.IsTopologicComboLinkSummonReady():
            return False
        if self.GetProblematicKnightmareCerberusTarget() is None:
            return False
        return self.SelectKnightmareLinkMaterials(False)

    def KnightmareCerberusEffect(self):
        if self.DefaultCheckWhetherCardIsNegated(self.Card):
            return False
        target = self.GetProblematicKnightmareCerberusTarget()
        if target is None or len(self.Bot.Hand) == 0:
            return False
        self.MarkCurrentChainHandled(target)
        self.SelectDiscard()
        self.AI.SelectNextCard(target)
        return True

    def KnightmarePhoenixUnlockSummon(self):
        if not self.ShouldUnlockMainMonsterZones():
            return False
        if self.Util.GetProblematicEnemySpell() is None and \
                self.GetProblematicKnightmareCerberusTarget() is not None:
            return False
        return self.SelectKnightmareLinkMaterials(True)

    def KnightmareCerberusUnlockSummon(self):
        return self.ShouldUnlockMainMonsterZones() and self.SelectKnightmareLinkMaterials(True)

    def ShouldUnlockMainMonsterZones(self):
        Bot, Duel = self.Bot, self.Duel
        if Duel.Player != 0 or len(Duel.CurrentChain) > 0 or \
                Duel.Phase != DuelPhase.Main1 and Duel.Phase != DuelPhase.Main2 or \
                Bot.GetMonsterCount() > 2 or self.EmptyMainMonsterZone():
            return False

        return self.HasUsefulBlockedSkyStrikerSpell() or \
            (any(self.IsDisposableMonster(card) for card in Bot.GetMonsters()) and self.Enemy.GetMonsterCount() > 0)

    def SelectKnightmareLinkMaterials(self, requireExtraMonsterZone):
        if requireExtraMonsterZone:
            materials = sorted((card for card in self.Bot.GetMonsters()
                                if card.IsFaceup() and not card.IsCode(CardId.BorrelswordDragon)),
                               key=self.GetLinkMaterialValue)
            if len(materials) != 2 or len({card.Id for card in materials}) != 2 or \
                    not CanMakeLinkRating(materials, 2):
                return False
        else:
            materials = self.GetLinkMaterials(2, 2, 2, False, True)
        if materials is None:
            return False
        available = GetBotAvailZonesFromExtraDeck(self.Util, materials)
        if requireExtraMonsterZone and not IsNewRule2020(self.Duel) and \
                (available & Zones.ExtraMonsterZones) == 0:
            return False
        self.AI.SelectMaterials(materials)
        if requireExtraMonsterZone:
            self.AI.SelectPlace(Zones.ExtraMonsterZones)
        return True

    def GetProblematicKnightmareCerberusTarget(self):
        targets = [card for card in self.Enemy.GetMonstersInMainZone()
                   if card.IsSpecialSummoned and not card.IsShouldNotBeTarget() and
                   not card.IsShouldNotBeMonsterTarget() and not self.IsCurrentChainHandled(card)]
        problematic = self.Util.GetProblematicEnemyMonster(0, True)
        if problematic is not None and problematic in targets:
            return problematic
        return None

    def IsTopologicComboLinkSummonReady(self):
        Bot = self.Bot
        if not self.TopologicComboStarted or not self.HasTopologicComboPayoff():
            return False
        halqifibrax = next((card for card in Bot.GetMonsters() if card.IsCode(CardId.CrystronHalqifibrax)), None)
        canSummonUnicorn = halqifibrax is not None and \
            any(card != halqifibrax and card.IsTuner() and card.IsFaceup() for card in Bot.GetMonsters()) and \
            Bot.HasInExtra(CardId.KnightmareUnicorn)
        canSummonTopologic = Bot.HasInMonstersZone(CardId.KnightmareUnicorn) and \
            Bot.HasInMonstersZone(CardId.GlowUpBulb) and \
            Bot.HasInExtra(CardId.TopologicBomberDragon)
        return canSummonUnicorn or canSummonTopologic

    def KnightmareUnicornSummon(self):
        Bot = self.Bot
        halqifibrax = next((card for card in Bot.GetMonsters() if card.IsCode(CardId.CrystronHalqifibrax)), None)
        tuner = next((card for card in Bot.GetMonsters()
                      if card != halqifibrax and card.IsTuner() and card.IsFaceup()), None)
        if halqifibrax is not None and tuner is not None:
            comboMaterials = [halqifibrax, tuner]
            if GetBotAvailZonesFromExtraDeck(self.Util, comboMaterials) != 0:
                self.AI.SelectMaterials(comboMaterials)
                return True

        if self.Util.GetProblematicEnemyCard(0, True) is None:
            return False
        materials = self.GetLinkMaterials(3, 2, 3, False, True)
        if materials is None:
            return False
        self.AI.SelectMaterials(materials)
        return True

    def KnightmareUnicornEffect(self):
        if self.DefaultCheckWhetherCardIsNegated(self.Card):
            return False
        if self.TopologicComboStarted and self.HasTopologicComboPayoff() and len(self.Bot.Hand) < 2:
            return False

        target = self.Util.GetProblematicEnemyCard(0, True)
        if target is None:
            target = self.Util.GetBestEnemyCard(False, True)
        if target is None or self.IsCurrentChainHandled(target) or \
                self.BorrelswordComboStarted and self.Enemy.GetMonsterCount() == 1:
            return False
        self.MarkCurrentChainHandled(target)
        self.SelectDiscard()
        self.AI.SelectNextCard(target)
        return True

    def TopologicBomberDragonSummon(self):
        Bot = self.Bot
        if self.TopologicComboStarted and self.HasTopologicComboPayoff():
            unicorn = next((card for card in Bot.GetMonsters() if card.IsCode(CardId.KnightmareUnicorn)), None)
            bulb = next((card for card in Bot.GetMonsters() if card.IsCode(CardId.GlowUpBulb)), None)
            if unicorn is not None and bulb is not None:
                comboMaterials = [unicorn, bulb]
                if GetBotAvailZonesFromExtraDeck(self.Util, comboMaterials) != 0:
                    self.AI.SelectMaterials(comboMaterials)
                    return True

        if Bot.HasInMonstersZone(CardId.Shizuku) or \
                Bot.HasInExtra(CardId.Shizuku) and any(card.IsCode(CardId.Raye, CardId.Kagari, CardId.Hayate)
                                                       for card in Bot.GetMonsters()):
            return False
        materials = self.GetLinkMaterials(4, 2, 4, True, False)
        if materials is None:
            return False
        self.AI.SelectMaterials(materials)
        return True

    def ShizukuSummon(self):
        if self.ShizukuSummoned or not self.Util.IsTurn1OrMain2():
            return False
        self.ShizukuSummoned = True
        return True

    def ShizukuFirstEndPhaseEffect(self):
        Bot, Duel = self.Bot, self.Duel
        if Duel.Player != 0 or Duel.Phase != DuelPhase.End or \
                self.DefaultCheckWhetherCardIsNegated(self.Card) or \
                not Bot.HasInSpellZone(CardId.Multirole, True, True) or \
                Bot.HasInGraveyard(CardId.WidowAnchor) or not Bot.HasInDeck(CardId.WidowAnchor) or \
                Bot.GetSpellCountWithoutField() >= 5:
            return False
        self.AI.SelectCard(CardId.WidowAnchor)
        return True

    def WidowAnchorEndPhaseEffect(self):
        Bot, Duel = self.Bot, self.Duel
        if Duel.Player != 0 or Duel.Phase != DuelPhase.End or \
                self.Card.Location != CardLocation.Hand or \
                not Bot.HasInSpellZone(CardId.Multirole, True, True) or \
                Bot.HasInGraveyard(CardId.WidowAnchor) or \
                Bot.GetSpellCountWithoutField() >= 5:
            return False
        self.AI.SelectCard(CardId.Shizuku)
        return True

    def ShizukuEffect(self):
        if self.DefaultCheckWhetherCardIsNegated(self.Card):
            return False
        self.AI.SelectCard(self.GetSkyStrikerSearchPriority(True))
        return True

    # --- helpers -----------------------------------------------------------------------------------------
    def GetSkyStrikerSearchPriority(self, includeEngage):
        Bot, Util = self.Bot, self.Util
        result = []
        if includeEngage:
            result.append(CardId.Engage)
        if not Bot.HasInHandOrInSpellZone(CardId.HornetDrones):
            result.append(CardId.HornetDrones)
        if Util.GetProblematicEnemyMonster() is not None:
            result.append(CardId.WidowAnchor)
        if self.EmptyMainMonsterZone() and Util.GetProblematicEnemyMonster() is not None:
            result.append(CardId.Afterburners)
        if self.EmptyMainMonsterZone() and any(card.IsFacedown() and not self.IsCurrentChainHandled(card)
                                               for card in self.Enemy.GetSpells()):
            result.append(CardId.JammingWaves)
        if not Bot.HasInHand(CardId.Raye) and not Bot.HasInMonstersZone(CardId.Raye) and \
                not Bot.HasInGraveyard(CardId.Raye):
            result.append(CardId.Raye)
        if not Bot.HasInHandOrInSpellZone(CardId.Multirole):
            result.append(CardId.Multirole)
        if not Bot.HasInHandOrInSpellZone(CardId.WidowAnchor):
            result.append(CardId.WidowAnchor)
        result.extend([
            CardId.HornetDrones,
            CardId.WidowAnchor,
            CardId.SharkCannon,
            CardId.Afterburners,
            CardId.JammingWaves,
            CardId.AreaZero,
            CardId.Multirole,
            CardId.Raye,
        ])
        return [id_ for id_ in dict.fromkeys(result) if Bot.HasInDeck(id_)]

    def GetEnemyMonsterTarget(self, problematicOnly):
        candidates = [card for card in self.Enemy.GetMonsters()
                      if card.IsFaceup() and not card.IsShouldNotBeTarget() and
                      not card.IsShouldNotBeSpellTrapTarget() and not self.IsCurrentChainHandled(card) and
                      (card != self.WidowAnchorTarget or not card.IsDisabled())]

        target = GetFloodgate(candidates)
        if target is None:
            target = GetDangerousMonster(candidates)
        if target is None:
            target = GetInvincibleMonster(candidates)
        if target is None:
            target = GetShouldBeDisabledBeforeItUseEffectMonster(candidates)
        if target is not None:
            return target

        if problematicOnly:
            bestBotAttack = self.Util.GetBestAttack(self.Bot)
            ordered = sorted((card for card in candidates
                              if card.IsAttack() and card.GetDefensePower() >= bestBotAttack),
                             key=lambda card: -card.GetDefensePower())
            return ordered[0] if ordered else None

        return GetHighestAttackMonster(candidates)

    def IsCurrentChainHandled(self, card):
        return card is not None and card in self.CurrentChainHandledCards

    def MarkCurrentChainHandled(self, card):
        if card is not None and card not in self.CurrentChainHandledCards:
            self.CurrentChainHandledCards.append(card)

    def HasUsefulBlockedSkyStrikerSpell(self):
        Bot = self.Bot
        if self.EmptyMainMonsterZone():
            return False
        problematicMonster = self.GetEnemyMonsterTarget(True)
        return Bot.HasInHandOrInSpellZone(CardId.Engage) or \
            (Bot.HasInHandOrInSpellZone(CardId.Afterburners) and problematicMonster is not None) or \
            (Bot.HasInHandOrInSpellZone(CardId.JammingWaves) and
             any(card.IsFacedown() and not self.IsCurrentChainHandled(card) for card in self.Enemy.GetSpells())) or \
            (Bot.HasInHandOrInSpellZone(CardId.WidowAnchor) and problematicMonster is not None and
             not problematicMonster.IsDisabled() and not problematicMonster.HasType(CardType.Normal))

    def IsDisposableMonster(self, card):
        if card is None:
            return False
        if card in self.ControlledEnemyCards or \
                card.IsCode(CardId.Token, CardId.GlowUpBulb, CardId.Linkuriboh, CardId.AshBlossom,
                            CardId.GhostOgre, CardId.EffectVeiler, CardId.MaxxC):
            return True
        return not card.IsCode(CardId.Raye, CardId.Kagari, CardId.Hayate, CardId.Shizuku,
                               CardId.CrystronHalqifibrax, CardId.BorrelswordDragon,
                               CardId.TopologicBomberDragon, CardId.KnightmareUnicorn)

    def SelectDiscard(self):
        Bot = self.Bot
        priorities = [
            CardId.MetalfoesFusion,
            CardId.GlowUpBulb,
        ]
        if not Bot.HasInGraveyard(CardId.Raye):
            priorities.append(CardId.Raye)
        priorities.extend([
            CardId.ReinforcementOfTheArmy,
            CardId.FoolishBurialGoods,
            CardId.UpstartGoblin,
            CardId.HerculesBase,
        ])
        if self.HasTopologicComboPayoff() and \
                (self.TopologicComboStarted or self.ShouldStartTopologicCombo()) and \
                Bot.HasInHand(CardId.HornetDrones):
            ordered = sorted((card for card in Bot.Hand
                              if card != self.Card and not card.IsCode(CardId.HornetDrones)),
                             key=lambda card: priorities.index(card.Id) if card.Id in priorities else 2 ** 31 - 1)
            discard = ordered[0] if ordered else None
            if discard is not None:
                self.AI.SelectCard(discard)
                return
        priorities.append(CardId.HornetDrones)
        self.AI.SelectCard(priorities)

    def OrderCardsById(self, cards, ids, uniqueNames):
        result = []
        addedIds = set()
        for id_ in ids:
            card = next((candidate for candidate in cards
                         if candidate.IsCode(id_) and (not uniqueNames or candidate.Id not in addedIds)), None)
            if card is not None:
                result.append(card)
                addedIds.add(card.Id)
        for card in cards:
            if card not in result and (not uniqueNames or card.Id not in addedIds):
                result.append(card)
                addedIds.add(card.Id)
        return result

    def GetLinkMaterials(self, linkRating, minCount, maxCount, effectOnly, uniqueNames, preservedCard=None):
        candidates = sorted((card for card in self.Bot.GetMonsters()
                             if card.IsFaceup() and (not effectOnly or card.HasType(CardType.Effect)) and
                             card != preservedCard and not card.IsCode(CardId.BorrelswordDragon)),
                            key=self.GetLinkMaterialValue)

        best = None
        bestScore = 2 ** 31 - 1
        subsetCount = 1 << len(candidates)
        for mask in range(1, subsetCount):
            selected = [candidates[i] for i in range(len(candidates)) if (mask & (1 << i)) != 0]
            if len(selected) < minCount or len(selected) > maxCount:
                continue
            if uniqueNames and len({card.Id for card in selected}) != len(selected):
                continue
            if not CanMakeLinkRating(selected, linkRating) or \
                    GetBotAvailZonesFromExtraDeck(self.Util, selected) == 0:
                continue

            score = sum(self.GetLinkMaterialValue(card) for card in selected)
            if score < bestScore:
                best = selected
                bestScore = score
        return best

    def GetLinkMaterialValue(self, card):
        if card in self.ControlledEnemyCards or card.Controller == 1 or \
                card.IsCode(CardId.Token, CardId.GlowUpBulb):
            return 0
        if card.IsCode(CardId.Linkuriboh):
            return 100
        if card.IsCode(CardId.AshBlossom, CardId.GhostOgre, CardId.EffectVeiler):
            return 200
        if card.IsCode(CardId.Kagari, CardId.Hayate, CardId.Shizuku):
            return 1500 + card.LinkCount * 100
        return max(300, card.Attack) + card.LinkCount * 100

    def SetHornetDrones(self):
        return self.Util.IsTurn1OrMain2() and \
            (self.SetWhenHandIsFull() or self.Bot.HasInMonstersZone(CardId.TopologicBomberDragon, True))

    def SetWhenHandIsFull(self):
        return self.Bot.GetSpellCountWithoutField() < 4 and len(self.Bot.Hand) > 6

    def EmptyMainMonsterZone(self):
        return len(self.Bot.GetMonstersInMainZone()) == 0

    def GetSpellCountInGrave(self):
        return len(self.Bot.GetGraveyardSpells())

    def HaveThreeSpellsInGrave(self):
        return self.GetSpellCountInGrave() >= 3
