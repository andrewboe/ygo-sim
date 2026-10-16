"""Chaos Ritual executor, ported from IceYGO/windbot Game/AI/Decks/ChaosRitualExecutor.cs (MIT, see THIRD_PARTY_NOTICES.md).

Approximations: the env limits in docs/windbot_porting.md (IsDisabled always False, Enemy.BattlingMonster None and
Bot.UnderAttack False, so CanReceiveDamage only sees the opponent's Battle Phase and damage text on the latest
chain link). Cards kept across decisions (the pending release,
Mind Shuffle return, Light and Darkness return, reserved target and Spell Shattering Sword sets) are snapshots of
the decision that stored them; FindMovedCard matches the release and Mind Shuffle return cards in OnMove by id,
previous controller and previous location instead of object identity. C# HashSet<ClientCard> / HashSet<int> are
sets; overloads (SelectGriffohAsFullRitualMaterial, CanUseSpellShatteringSwordSpellDestroy) dispatch on arity.

Module-level helper: FindMovedCard (the ClientCard identity stand-in above)."""
from windbot import *
from windbot_default import DefaultExecutor, _CardId, _Setcode
from windbot_gameai import BattlePhaseAction


class CardId:
    TheWorldsGreatestGallantThief = 24203749
    BlackSkullDragonTheArchfiendDragonOfUnity = 97818130
    BlackChaos = 98684220
    FydraulisHarmonia = 70088809
    SkullArchfiendOfChaos = 24088928
    FallenOfTheWhiteDragon = 73819701
    IncredibleEcclesiaTheVirtuous = 55273560
    CelticMystic = 50073633
    MulcharmyPurulia = 84192580
    AshBlossomJoyousSpring = 14558127
    MaxxC = 23434538
    Griffoh = 97462632
    DrollLockBird = 94145021
    BlackLusterSoldierSoldierOfLightAndDarkness = 70405001
    MagicianOfDarkChaosBlackChaos = 44001993
    SpatialTrunade = 2729965
    RaggedRecordsOfRites = 24461358
    CrimsonCall = 99398682
    LightAndDarknessRitual = 33599853
    TheFallenTheVirtuous = 30271097
    SpellShatteringSword = 77456448
    MindShuffle = 24749710
    BlackRoseDragon = 73580471
    HarpiesFeatherDuster = 18144506
    Raigeki = 12580477
    LightningStorm = 14532163

    AlbaLenatusTheAbyssDragon = 3410461
    TitanikladTheAshDragon = 41373230
    AlbionTheBrandedDragon = 87746184
    RedNovaDragonBurningSoul = 65541655
    PsychicEndPunisher = 60465049
    ChaosAngel = 22850702
    FiendsmithsRequiem = 2463794
    TheCrimsonKing = 67809530
    RedDragonArchfiend = 70902743
    EnigmasterPackbit = 72444406
    EcclesiaAndTheDarkDragon = 78397661
    StardustDragonVictimSanctuary = 76636978
    WindPegasusIgnister = 98506199
    GoldenCloudBeastMalong = 93125329
    HeraldOfTheArcLight = 79606837


class ChaosRitualExecutor(DefaultExecutor):
    DECK_EXECUTOR = True

    def __init__(self):
        super().__init__()
        self._selectingGallantThiefTributes = False
        self._ownMonsterReleasedToGraveThisTurn = False
        self._mindShufflePriorityOverrideApplied = False
        self._pendingMindShuffleSummonId = 0
        self._pendingMindShuffleReturnCards = set()
        self._performedRitualSummonThisTurn = False
        self._pendingReleaseCards = set()
        self._enemyMaxxCResolved = False
        self._ritualSummonCountThisTurn = 0
        self._celticMysticDrawTriggerPending = False
        self._preserveCelticMysticDrawTriggerAtChainEnd = False
        self._selectingLightAndDarknessRitualMaterials = False
        self._selectingBlackChaosSpecialSummonReturn = False
        self._pendingSpellShatteringSwordMonsterTarget = None
        self._pendingSpellShatteringSwordSpellDestroy = False
        self._pendingFydraulisSynchroToGraveId = 0
        self._pendingFydraulisDestructionTarget = None
        self._pendingLightAndDarknessReturnCards = set()
        self._reservedOpponentTargets = set()
        self._pendingDeckSearchIds = set()
        self._pendingBlackChaosSupportSearch = False
        self._mindShuffleFieldCount = 0
        self._activatedFirstEffectCardIdsThisTurn = set()
        self._mindShuffleSummonOrder = [
            CardId.MagicianOfDarkChaosBlackChaos,
            CardId.BlackSkullDragonTheArchfiendDragonOfUnity,
            CardId.BlackLusterSoldierSoldierOfLightAndDarkness,
            CardId.BlackChaos,
        ]
        self._mindShuffleReturnOrder = [
            CardId.FydraulisHarmonia,
            CardId.BlackSkullDragonTheArchfiendDragonOfUnity,
            CardId.BlackLusterSoldierSoldierOfLightAndDarkness,
            CardId.MagicianOfDarkChaosBlackChaos,
            CardId.BlackChaos,
        ]

        A, S, SS = ExecutorType.Activate, ExecutorType.Summon, ExecutorType.SpSummon
        self.AddExecutor(S, CardId.TheWorldsGreatestGallantThief, self.GallantThiefSummon)
        self.AddExecutor(S, CardId.CelticMystic, self.CelticMysticSummon)
        self.AddExecutor(SS, CardId.AlbaLenatusTheAbyssDragon, self.AlbaLenatusSpecialSummon)
        self.AddExecutor(A, CardId.SpatialTrunade, self.SpatialTrunadeActivate)
        self.AddExecutor(SS, CardId.ChaosAngel, self.PriorityExtraDeckSpecialSummon)
        self.AddExecutor(SS, CardId.RedNovaDragonBurningSoul, self.PriorityExtraDeckSpecialSummon)
        self.AddExecutor(SS, CardId.StardustDragonVictimSanctuary, self.StardustDragonSpecialSummon)
        self.AddExecutor(A, CardId.StardustDragonVictimSanctuary, self.StardustDragonActivate)
        self.AddExecutor(A, CardId.TitanikladTheAshDragon, self.TitanikladActivate)
        self.AddExecutor(A, CardId.AlbionTheBrandedDragon, self.AlbionActivate)
        self.AddExecutor(A, CardId.RedNovaDragonBurningSoul, self.RedNovaDragonActivate)
        self.AddExecutor(A, CardId.PsychicEndPunisher, self.PsychicEndPunisherActivate)
        self.AddExecutor(A, CardId.ChaosAngel, self.ChaosAngelActivate)
        self.AddExecutor(SS, CardId.TheCrimsonKing, self.CrimsonKingSpecialSummon)
        self.AddExecutor(A, CardId.TheCrimsonKing, self.CrimsonKingActivate)
        self.AddExecutor(A, CardId.EnigmasterPackbit, self.EnigmasterPackbitActivate)
        self.AddExecutor(A, CardId.EcclesiaAndTheDarkDragon, self.EcclesiaAndTheDarkDragonActivate)
        self.AddExecutor(A, CardId.WindPegasusIgnister, self.WindPegasusIgnisterActivate)
        self.AddExecutor(A, CardId.GoldenCloudBeastMalong, self.GoldenCloudBeastMalongActivate)
        self.AddExecutor(A, CardId.HeraldOfTheArcLight, self.HeraldOfTheArcLightActivate)
        self.AddExecutor(SS, CardId.IncredibleEcclesiaTheVirtuous, self.EcclesiaSpecialSummon)

        self.AddExecutor(A, CardId.MaxxC, self.MaxxCActivate)
        self.AddExecutor(A, CardId.MulcharmyPurulia, self.PuruliaActivate)
        self.AddExecutor(A, CardId.AshBlossomJoyousSpring, self.AshBlossomActivate)
        self.AddExecutor(A, CardId.DrollLockBird, self.DrollLockBirdActivate)
        self.AddExecutor(A, CardId.TheWorldsGreatestGallantThief, self.GallantThiefActivate)

        self.AddExecutor(A, CardId.FydraulisHarmonia, self.FydraulisHarmoniaActivate)
        self.AddExecutor(A, CardId.BlackSkullDragonTheArchfiendDragonOfUnity, self.BlackSkullDragonFieldActivate)
        self.AddExecutor(SS, CardId.PsychicEndPunisher, self.PsychicEndPunisherSpecialSummon)
        self.AddExecutor(A, CardId.CelticMystic, self.CelticMysticSearchActivate)
        self.AddExecutor(A, CardId.BlackChaos, self.BlackChaosHandActivate)
        self.AddExecutor(A, CardId.Griffoh, self.GriffohActivate)
        self.AddExecutor(A, CardId.BlackChaos, self.BlackChaosFieldActivate)
        self.AddExecutor(A, CardId.BlackLusterSoldierSoldierOfLightAndDarkness, self.BlackLusterSoldierActivate)

        self.AddExecutor(A, CardId.IncredibleEcclesiaTheVirtuous, self.EcclesiaActivate)
        self.AddExecutor(A, CardId.FallenOfTheWhiteDragon, self.FallenOfTheWhiteDragonActivate)
        self.AddExecutor(A, CardId.LightAndDarknessRitual, self.LightAndDarknessRitualGraveActivate)
        self.AddExecutor(A, CardId.MagicianOfDarkChaosBlackChaos, self.MagicianOfDarkChaosActivate)
        self.AddExecutor(A, CardId.TheFallenTheVirtuous, self.TheFallenTheVirtuousActivate)
        self.AddExecutor(A, CardId.SpellShatteringSword, self.SpellShatteringSwordActivate)
        self.AddExecutor(A, CardId.BlackSkullDragonTheArchfiendDragonOfUnity, self.BlackSkullDragonHandActivate)
        self.AddExecutor(SS, CardId.BlackChaos, self.BlackChaosSpecialSummon)
        self.AddExecutor(A, CardId.RaggedRecordsOfRites, self.RaggedRecordsOfRitesActivate)
        self.AddExecutor(A, CardId.MindShuffle, self.MindShuffleActivate)
        self.AddExecutor(A, CardId.CrimsonCall, self.CrimsonCallActivate)
        self.AddExecutor(A, CardId.LightAndDarknessRitual, self.LightAndDarknessRitualActivate)

        self.AddExecutor(A, CardId.SkullArchfiendOfChaos, self.SkullArchfiendOfChaosActivate)
        self.AddExecutor(A, CardId.CelticMystic, self.CelticMysticRitualSpecialSummonActivate)

        self.AddExecutor(ExecutorType.SpellSet, self.ChaosSpellSet)
        self.AddExecutor(ExecutorType.Repos, self.DefaultMonsterRepos)

    def OnSelectHand(self):
        return True

    def OnSelectYesNo(self, desc):
        return super().OnSelectYesNo(desc)

    def OnNewTurn(self):
        self._selectingGallantThiefTributes = False
        self._ownMonsterReleasedToGraveThisTurn = False
        self._mindShufflePriorityOverrideApplied = False
        self._pendingMindShuffleSummonId = 0
        self._pendingMindShuffleReturnCards.clear()
        self._performedRitualSummonThisTurn = False
        self._enemyMaxxCResolved = False
        self._ritualSummonCountThisTurn = 0
        self._celticMysticDrawTriggerPending = False
        self._preserveCelticMysticDrawTriggerAtChainEnd = False
        self._selectingLightAndDarknessRitualMaterials = False
        self._selectingBlackChaosSpecialSummonReturn = False
        self._pendingSpellShatteringSwordMonsterTarget = None
        self._pendingSpellShatteringSwordSpellDestroy = False
        self._pendingFydraulisSynchroToGraveId = 0
        self._pendingFydraulisDestructionTarget = None
        self._pendingReleaseCards.clear()
        self._pendingLightAndDarknessReturnCards.clear()
        self._reservedOpponentTargets.clear()
        self._pendingDeckSearchIds.clear()
        self._pendingBlackChaosSupportSearch = False
        self._mindShuffleFieldCount = 0
        self._activatedFirstEffectCardIdsThisTurn.clear()
        self.ResetMindShuffleSummonOrder()
        self.ResetMindShuffleReturnOrder()
        self._mindShuffleFieldCount = sum(1 for c in self.Bot.SpellZone if c is not None and c.IsCode(CardId.MindShuffle))
        super().OnNewTurn()

    def OnSelectAttacker(self, attackers, defenders):
        blackLusterSoldier = next((c for c in attackers if c is not None and
                                   c.IsCode(CardId.BlackLusterSoldierSoldierOfLightAndDarkness)), None)
        if blackLusterSoldier is not None:
            return blackLusterSoldier
        return super().OnSelectAttacker(attackers, defenders)

    def OnBattle(self, attackers, defenders):
        if len(defenders) == 0:
            blackLusterSoldier = next((c for c in attackers if c is not None and
                                       c.IsCode(CardId.BlackLusterSoldierSoldierOfLightAndDarkness)), None)
            if blackLusterSoldier is not None and blackLusterSoldier.CanDirectAttack:
                return self.AI.Attack(blackLusterSoldier, None)
        return super().OnBattle(attackers, defenders)

    def OnSelectAttackTarget(self, attacker, defenders):
        if attacker is not None and attacker.IsCode(CardId.BlackLusterSoldierSoldierOfLightAndDarkness):
            for defender in defenders:
                attacker.RealPower = attacker.GetAttackPower()
                defender.RealPower = defender.GetDefensePower()
                if not self.OnPreBattleBetween(attacker, defender):
                    continue
                if attacker.RealPower > defender.RealPower or \
                        attacker.RealPower == defender.RealPower and defender.IsAttack():
                    return self.AI.Attack(attacker, defender)
            if attacker.CanDirectAttack:
                return self.AI.Attack(attacker, None)
            return None
        return super().OnSelectAttackTarget(attacker, defenders)

    def OnChaining(self, player, card):
        if player == 0 and card is not None and card.IsCode(CardId.CelticMystic) and \
                self._celticMysticDrawTriggerPending:
            self._activatedFirstEffectCardIdsThisTurn.add(card.Id)
            self._celticMysticDrawTriggerPending = False
            self._preserveCelticMysticDrawTriggerAtChainEnd = False
        if player == 0 and card is not None and card.Id != 0 and not self.IsMultiEffectCard(card):
            self._activatedFirstEffectCardIdsThisTurn.add(card.Id)
        super().OnChaining(player, card)

    def OnChainSolved(self, chainIndex):
        currentChain = self.Duel.GetCurrentSolvingChainInfo()
        if currentChain is not None and currentChain.ActivatePlayer == 0 and self.IsFirstEffect(currentChain):
            self._activatedFirstEffectCardIdsThisTurn.add(currentChain.ActivateId)
        if currentChain is not None and not self.Duel.IsCurrentSolvingChainNegated():
            if currentChain.ActivatePlayer == 1 and currentChain.IsActivateCode(CardId.MaxxC):
                self._enemyMaxxCResolved = True
        super().OnChainSolved(chainIndex)

    def OnChainEnd(self):
        if self._preserveCelticMysticDrawTriggerAtChainEnd:
            self._preserveCelticMysticDrawTriggerAtChainEnd = False
        else:
            self._celticMysticDrawTriggerPending = False
        self._selectingLightAndDarknessRitualMaterials = False
        self._pendingSpellShatteringSwordMonsterTarget = None
        self._pendingSpellShatteringSwordSpellDestroy = False
        self._pendingFydraulisSynchroToGraveId = 0
        self._pendingFydraulisDestructionTarget = None
        self._reservedOpponentTargets.clear()
        self._pendingDeckSearchIds.clear()
        self._pendingBlackChaosSupportSearch = False
        self._pendingLightAndDarknessReturnCards.clear()
        super().OnChainEnd()

    def OnMove(self, card, previousControler, previousLocation, currentControler, currentLocation):
        if card is not None and currentControler == 0 and (currentLocation & CardLocation.Grave) != 0:
            tracked = FindMovedCard(self._pendingReleaseCards, card, previousControler, previousLocation)
            if tracked is not None:
                self._ownMonsterReleasedToGraveThisTurn = True
                self._pendingReleaseCards.discard(tracked)

        if card is not None and card.IsCode(CardId.MindShuffle) and currentControler == 0:
            wasInSpellZone = (previousLocation & CardLocation.SpellZone) != 0
            isInSpellZone = (currentLocation & CardLocation.SpellZone) != 0
            if not wasInSpellZone and isInSpellZone:
                self._mindShuffleFieldCount += 1
            elif wasInSpellZone and not isInSpellZone and self._mindShuffleFieldCount > 0:
                self._mindShuffleFieldCount -= 1

        if card is not None and self._pendingMindShuffleSummonId != 0 and \
                card.IsCode(self._pendingMindShuffleSummonId) and currentControler == 0 and \
                (currentLocation & CardLocation.MonsterZone) != 0:
            self.MoveMindShuffleSummonToEnd(card.Id)
            self._pendingMindShuffleSummonId = 0

        tracked = FindMovedCard(self._pendingMindShuffleReturnCards, card, previousControler, previousLocation)
        if card is not None and tracked is not None and currentControler == 0 and \
                (previousLocation & CardLocation.MonsterZone) != 0 and (currentLocation & CardLocation.Hand) != 0:
            self.MoveMindShuffleReturnToEnd(card.Id)
            self._pendingMindShuffleReturnCards.discard(tracked)

        if card is not None and card.IsCode(CardId.CelticMystic) and \
                (previousLocation & CardLocation.MonsterZone) != 0 and (currentLocation & CardLocation.MonsterZone) == 0:
            self._celticMysticDrawTriggerPending = False
            self._preserveCelticMysticDrawTriggerAtChainEnd = False

        super().OnMove(card, previousControler, previousLocation, currentControler, currentLocation)

    def OnSummoning(self):
        celticMystic = next((c for c in self.Duel.SummoningCards if c is not None and c.Controller == 0 and
                             c.IsCode(CardId.CelticMystic)), None)
        self._celticMysticDrawTriggerPending = celticMystic is not None and \
            any(c is not None and c != celticMystic and self.IsRitualRelatedCard(c) for c in self.Bot.Hand)
        self._preserveCelticMysticDrawTriggerAtChainEnd = False
        super().OnSummoning()

    def OnNewPhase(self):
        self._celticMysticDrawTriggerPending = False
        self._preserveCelticMysticDrawTriggerAtChainEnd = False
        self._selectingBlackChaosSpecialSummonReturn = False
        super().OnNewPhase()

    def OnSpSummoned(self):
        solvingChain = self.Duel.GetCurrentSolvingChainInfo()
        if solvingChain is not None and solvingChain.IsActivateCode(CardId.LightAndDarknessRitual) and \
                any(c is not None and c.Controller == 0 and self.IsRitualMonster(c) for c in self.Duel.LastSummonedCards):
            self._performedRitualSummonThisTurn = True
            self._ritualSummonCountThisTurn += 1

        self._selectingLightAndDarknessRitualMaterials = False

        if any(c is not None and c.Controller == 0 and c.IsCode(CardId.CelticMystic) for c in self.Duel.LastSummonedCards):
            self._celticMysticDrawTriggerPending = any(self.IsRitualRelatedCard(c) for c in self.Bot.Hand)
            self._preserveCelticMysticDrawTriggerAtChainEnd = \
                self._celticMysticDrawTriggerPending and len(self.Duel.CurrentChain) > 0

        super().OnSpSummoned()

    def OnSelectTribute(self, cards, min_, max_, hint, cancelable):
        griffohSelection = self.SelectGriffohAsFullRitualMaterial(cards, min_, max_)
        if griffohSelection is not None:
            self.TrackReleaseSelection(griffohSelection)
            return griffohSelection

        if any(self.IsGraveCard(c) for c in cards):
            ritualSelected = self.SelectGraveyardRitualTribute(cards, min_, max_)
            if ritualSelected is None:
                ordered = sorted((c for c in cards if self.IsAllowedRitualMaterial(c)),
                                 key=self.GetRitualTributePriority)
                ritualSelected = self.AI.FindTributeSelection(ordered, min_, max_)
            if ritualSelected is not None:
                self.TrackReleaseSelection(ritualSelected)
                return ritualSelected

        if not self._selectingGallantThiefTributes:
            return None

        self._selectingGallantThiefTributes = False
        enemyTributes = sorted((c for c in cards if c is not None and c.Controller == 1),
                               key=self.GetGallantThiefTributePriority, reverse=True)
        ownTributes = sorted((c for c in cards if c is not None and c.Controller == 0),
                             key=self.GetGallantThiefTributePriority)

        selected = []
        selected.extend(enemyTributes[:max_])
        if len(selected) < min_:
            selected.extend(ownTributes[:max(0, max_ - len(selected))])

        if len(selected) < min_:
            if cancelable:
                return []
            return None

        result = selected[:min(max_, len(selected))]
        self.TrackReleaseSelection(result)
        return result

    def OnSelectRitualTribute(self, cards, mandatoryCards, sum_, min_, max_, exactEqual):
        griffohSelection = self.SelectGriffohAsFullRitualMaterial(cards, mandatoryCards, sum_, min_, max_)
        if griffohSelection is not None:
            self.TrackReleaseSelection(griffohSelection)
            return griffohSelection

        selected = self.SelectGraveyardRitualSumSelection(cards, mandatoryCards, sum_, min_, max_, exactEqual)
        if selected is None:
            ordered = sorted((c for c in cards if self.IsAllowedRitualMaterial(c)), key=self.GetRitualMaterialPriority)
            selected = self.AI.FindSumSelection(ordered, mandatoryCards, sum_, min_, max_, exactEqual)
        self.TrackReleaseSelection(selected)
        return selected

    def OnSelectSum(self, cards, mandatoryCards, sum_, min_, max_, hint, exactEqual):
        hasGraveMaterial = (cards is not None and any(self.IsGraveCard(c) for c in cards)) or \
            (mandatoryCards is not None and any(self.IsGraveCard(c) for c in mandatoryCards))
        if hint == HintMsg.Release or hasGraveMaterial:
            griffohSelection = self.SelectGriffohAsFullRitualMaterial(cards, mandatoryCards, sum_, min_, max_)
            if griffohSelection is not None:
                self.TrackReleaseSelection(griffohSelection)
                return griffohSelection

            selected = self.SelectGraveyardRitualSumSelection(cards, mandatoryCards, sum_, min_, max_, exactEqual)
            if selected is None:
                ordered = sorted((c for c in cards if self.IsAllowedRitualMaterial(c)), key=self.GetRitualMaterialPriority)
                selected = self.AI.FindSumSelection(ordered, mandatoryCards, sum_, min_, max_, exactEqual)
            self.TrackReleaseSelection(selected)
            return selected

        return None

    def OnSelectPlace(self, cardId, player, location, available):
        if player == 0 and location == CardLocation.MonsterZone and self.IsExtraDeckMonster(cardId):
            if (available & Zones.z5) != 0:
                return Zones.z5
            if (available & Zones.z6) != 0:
                return Zones.z6
        return super().OnSelectPlace(cardId, player, location, available)

    def OnSelectCard(self, cards, min_, max_, hint, cancelable):
        chain = self.Duel.GetCurrentSolvingChainInfo()
        if chain is None:
            chain = self.GetCurrentActivationChainInfo()
        solvingCard = self.Duel.GetCurrentSolvingChainCard()

        if chain is None and hint == HintMsg.ToDeck and self._selectingBlackChaosSpecialSummonReturn:
            blackChaosReturn = self.SelectBlackChaosSpecialSummonReturn(cards, min_, max_)
            self._selectingBlackChaosSpecialSummonReturn = False
            if blackChaosReturn is not None:
                return blackChaosReturn

        if chain is None and solvingCard is not None and solvingCard.Controller == 0 and \
                solvingCard.IsCode(CardId.EcclesiaAndTheDarkDragon) and \
                (hint == HintMsg.Target or hint == HintMsg.ToDeck):
            ecclesiaTarget = self.SelectEcclesiaAndTheDarkDragonTarget(cards, min_, max_)
            if ecclesiaTarget is not None:
                return ecclesiaTarget

        selectingLightAndDarknessRitualMaterials = hint == HintMsg.Release and (
            self._selectingLightAndDarknessRitualMaterials or
            chain is not None and chain.ActivatePlayer == 0 and chain.IsActivateCode(CardId.LightAndDarknessRitual) or
            any(self.IsGraveCard(c) for c in cards))
        if selectingLightAndDarknessRitualMaterials:
            self._selectingLightAndDarknessRitualMaterials = True

            if min_ == 0:
                return []

            griffoh = self.SelectGriffohAsFullRitualMaterial(cards, min_, max_)
            if griffoh is not None:
                self.TrackReleaseSelection(griffoh)
                return griffoh

            graveMaterials = sorted((c for c in cards if self.IsPreferredGraveRitualMaterial(c)),
                                    key=self.GetRitualTributePriority)
            if len(graveMaterials) >= min_:
                selectedGrave = self.Util.CheckSelectCount(graveMaterials, cards, min_, max_)
                if selectedGrave is not None:
                    self.TrackReleaseSelection(selectedGrave)
                    return selectedGrave

        selected = None
        if chain is not None and chain.ActivatePlayer == 0:
            selected = self.SelectResolutionCard(chain, cards, min_, max_, hint)

        if selected is None and hint == HintMsg.ToGrave:
            current = self.Duel.GetCurrentChainCard()
            if current is not None and current.Controller == 0 and \
                    current.IsCode(CardId.FallenOfTheWhiteDragon, CardId.TheFallenTheVirtuous):
                selected = self.SelectFallenExtraDeckCost(cards, min_, max_)

        if selected is None:
            selected = super().OnSelectCard(cards, min_, max_, hint, cancelable)

        if chain is not None and chain.ActivatePlayer == 0 and self.IsDeckSearchSelectionHint(hint):
            self.ReservePendingDeckSearch(selected)

        if selected is not None and chain is not None and chain.ActivatePlayer == 0 and \
                chain.IsActivateCode(CardId.LightAndDarknessRitual) and chain.HasLocation(CardLocation.Grave) and \
                hint == HintMsg.AddToHand:
            for card in selected:
                if card is not None and card.IsCode(CardId.SkullArchfiendOfChaos):
                    self._pendingLightAndDarknessReturnCards.add(card)

        if self.IsOpponentTargetSelectionHint(hint) and self.IsValidTargetSelection(selected, cards, min_, max_):
            self.ReserveOpponentTargets(selected)

        if hint == HintMsg.Release:
            self.TrackReleaseSelection(selected)
        return selected

    def OnSelectOption(self, options):
        solvingChain = self.Duel.GetCurrentSolvingChainInfo()
        if solvingChain is not None and solvingChain.IsActivateCode(CardId.AlbionTheBrandedDragon):
            selected = options.index(1153) if 1153 in options else -1
            if selected >= 0:
                return selected
            selected = options.index(1190) if 1190 in options else -1
            if selected >= 0:
                return selected

        selected = self.GetOptionIndex(options, CardId.TheFallenTheVirtuous, 1)
        if selected >= 0 and self.GetOptionIndex(options, CardId.TheFallenTheVirtuous, 2) >= 0:
            return selected

        selected = self.GetOptionIndex(options, CardId.Griffoh, 2)
        if selected >= 0 and self.CanSetGriffohSupportCard():
            return selected
        selected = self.GetOptionIndex(options, CardId.Griffoh, 1)
        if selected >= 0 and self.CanReceiveDamage():
            return selected

        selected = self.GetOptionIndex(options, CardId.SpellShatteringSword, 1)
        if selected >= 0 and self.CanUseSpellShatteringSwordSpellDestroy():
            self._pendingSpellShatteringSwordMonsterTarget = None
            return selected
        selected = self.GetOptionIndex(options, CardId.SpellShatteringSword, 2)
        if selected >= 0 and self.CanUseSpellShatteringSwordMonsterNegate():
            return selected

        return super().OnSelectOption(options)

    def GallantThiefSummon(self):
        if not self.CanSummonGallantThief(self.Card):
            return False
        self._selectingGallantThiefTributes = True
        return True

    def CanSummonGallantThief(self, gallantThief):
        if gallantThief is None or not gallantThief.IsCode(CardId.TheWorldsGreatestGallantThief) or \
                gallantThief not in self.Bot.Hand or \
                self.Bot.GetMonsterCount() != 0 or self.Enemy.GetMonsterCount() == 0:
            return False
        hasOwnFallback = any(c is not None and c.IsMonster() and c != gallantThief for c in self.Bot.Hand)
        return self.Enemy.GetMonsterCount() >= 2 or hasOwnFallback

    def ShouldWaitForGallantThief(self):
        gallantThief = next((c for c in self.Bot.Hand if c is not None and
                             c.IsCode(CardId.TheWorldsGreatestGallantThief)), None)
        return self.Duel.Player == 0 and \
            (self.Duel.Phase == DuelPhase.Draw or self.Duel.Phase == DuelPhase.Standby) and \
            self.CanSummonGallantThief(gallantThief)

    def MaxxCActivate(self):
        return not self.ShouldWaitForGallantThief() and self.DefaultMaxxC()

    def PuruliaActivate(self):
        return not self.ShouldWaitForGallantThief() and self.DefaultMaxxC()

    def AshBlossomActivate(self):
        return not self.ShouldWaitForGallantThief() and self.DefaultAshBlossomAndJoyousSpring()

    def GallantThiefActivate(self):
        if self.Card.Location != CardLocation.MonsterZone:
            return False

        chainCard = self.GetCurrentOpponentChainCard()
        canNegateRemoteEffect = chainCard is not None and \
            (chainCard.Location == CardLocation.Hand or chainCard.Location == CardLocation.Grave or
             chainCard.Location == CardLocation.Removed)
        canChangeBattlePositions = self.Duel.Phase >= DuelPhase.BattleStart and \
            self.Duel.Phase < DuelPhase.Main2 and any(c.IsAttack() for c in self.Enemy.GetMonsters())

        if self.IsDescription(CardId.TheWorldsGreatestGallantThief, 1):
            return canNegateRemoteEffect
        if self.IsDescription(CardId.TheWorldsGreatestGallantThief, 2):
            return canChangeBattlePositions
        if self.ActivateDescription == -1:
            return canNegateRemoteEffect or canChangeBattlePositions
        return False

    def FydraulisHarmoniaActivate(self):
        if self.ShouldWaitForGallantThief() or self.Card.Location != CardLocation.Hand or \
                self.DefaultCheckWhetherCardIsNegated(self.Card):
            return False

        latest = self.GetLatestChainInfo()
        if not self.IsOpponentMonsterEffectChain(latest):
            return False

        source = self.GetChainSourceCard(latest)
        if source is not None and source.IsDisabled():
            return False

        synchros = [c for c in self.Bot.ExtraDeck if c is not None and c.HasType(CardType.Synchro)]
        if len(synchros) >= 5:
            if self._pendingFydraulisDestructionTarget is not None and \
                    self._pendingFydraulisDestructionTarget in self.Enemy.GetMonsters():
                return True

            target = next((c for c in self.GetOrderedFydraulisTargets(self.Enemy.GetMonsters())
                           if not self.IsOpponentTargetReserved(c)), None)
            if target is None:
                return False

            self._pendingFydraulisDestructionTarget = target
            self._reservedOpponentTargets.add(target)
            return True

        if len(synchros) >= 3:
            return self.GetPreferredFydraulisSynchroToGraveId(synchros) != 0
        return len(synchros) > 0 and self.Bot.GetMonsterCount() == 0 and self.Enemy.GetMonsterCount() > 0

    def GriffohActivate(self):
        if self.ShouldWaitForGallantThief() or self.Card.Location != CardLocation.Hand or \
                self.DefaultCheckWhetherCardIsNegated(self.Card):
            return False
        return not self.ShouldDelayForHigherPriorityHandStarter(CardId.Griffoh) and \
            (self.CanSetGriffohSupportCard() or self.CanReceiveDamage())

    def BlackChaosHandActivate(self):
        if self.ShouldWaitForGallantThief() or self.Card.Location != CardLocation.Hand or \
                self.DefaultCheckWhetherCardIsNegated(self.Card):
            return False
        if self.HasMindShuffleOnField():
            return False
        accept = not self.ShouldSummonCelticMysticFirst() and \
            not self.ShouldDelayForHigherPriorityHandStarter(CardId.BlackChaos) and \
            self.CanSearchBlackChaosSupportCard()
        if accept:
            self._pendingBlackChaosSupportSearch = True
        return accept

    def BlackSkullDragonFieldActivate(self):
        return not self.ShouldWaitForGallantThief() and self.Card.Location == CardLocation.MonsterZone and \
            not self.DefaultCheckWhetherCardIsNegated(self.Card)

    def BlackSkullDragonHandActivate(self):
        if self.ShouldWaitForGallantThief() or self.Card.Location != CardLocation.Hand or \
                self.DefaultCheckWhetherCardIsNegated(self.Card):
            return False
        return not self.HasHigherPriorityLightAndDarknessRitualCandidate() and \
            self.CanUseBlackSkullDragonHandSpecialSummon()

    def BlackChaosFieldActivate(self):
        if self.ShouldWaitForGallantThief() or self.Card.Location != CardLocation.MonsterZone or \
                self.DefaultCheckWhetherCardIsNegated(self.Card):
            return False
        return self.Duel.Phase < DuelPhase.End and self.Enemy.GetSpellCount() + self.Enemy.GetMonsterCount() >= 2

    def BlackChaosSpecialSummon(self):
        if self.HasHigherPriorityLightAndDarknessRitualCandidate():
            return False
        accept = not self.ShouldWaitForGallantThief() and not self.ShouldSummonCelticMysticFirst() and \
            (self.Card.Location != CardLocation.Hand or
             not self.ShouldDelayForHigherPriorityHandStarter(CardId.BlackChaos))
        if accept:
            self._selectingBlackChaosSpecialSummonReturn = True
        return accept

    def CelticMysticSummon(self):
        return not self.ShouldWaitForGallantThief() and not self.DefaultCheckWhetherCardIsNegated(self.Card) and \
            (any(c is not None and c != self.Card and self.IsRitualRelatedCard(c) for c in self.Bot.Hand) or
             any(self.IsRitualMonster(c) for c in self.Bot.Hand))

    def BlackLusterSoldierActivate(self):
        if self.ShouldWaitForGallantThief() or self.Card.Location != CardLocation.MonsterZone or \
                self.DefaultCheckWhetherCardIsNegated(self.Card):
            return False

        if self.IsDescription(CardId.BlackLusterSoldierSoldierOfLightAndDarkness, 0):
            return self.HasFreshOpponentTarget(self.Enemy.GetMonsters() + self.Enemy.GetSpells())

        if self.IsDescription(CardId.BlackLusterSoldierSoldierOfLightAndDarkness, 1):
            return True

        if self.ActivateDescription == -1:
            if self.Duel.Phase >= DuelPhase.BattleStart and self.Duel.Phase < DuelPhase.Main2:
                return True
            return self.HasFreshOpponentTarget(self.Enemy.GetMonsters() + self.Enemy.GetSpells())

        return False

    def CanActivateCelticMystic(self):
        if self.ShouldWaitForGallantThief() or self.Card.Location != CardLocation.MonsterZone or \
                self.DefaultCheckWhetherCardIsNegated(self.Card):
            return False
        return True

    def CelticMysticSearchActivate(self):
        if not self.CanActivateCelticMystic():
            return False
        if self.IsDescription(CardId.CelticMystic, 0):
            return any(self.IsRitualRelatedCard(c) for c in self.Bot.Hand)
        if self.IsDescription(CardId.CelticMystic, 1):
            return False
        return self.ActivateDescription == -1 and self._celticMysticDrawTriggerPending and \
            any(self.IsRitualRelatedCard(c) for c in self.Bot.Hand)

    def CelticMysticRitualSpecialSummonActivate(self):
        if not self.CanActivateCelticMystic():
            return False

        if len(self.Duel.CurrentChain) == 0 and \
                any(c is not None and c.IsCode(CardId.BlackChaos) for c in self.Duel.MainPhase.SpecialSummonableCards):
            return False

        if self.HasHigherPriorityLightAndDarknessRitualCandidate():
            return False

        if len(self.Duel.CurrentChain) == 0 and \
                any(c is not None and c.IsCode(CardId.LightAndDarknessRitual) and c.Location == CardLocation.Grave
                    for c in self.Duel.MainPhase.ActivableCards):
            return False

        if self.IsDescription(CardId.CelticMystic, 0):
            return False

        if self.IsDescription(CardId.CelticMystic, 1):
            return any(self.IsRitualMonster(c) for c in self.Bot.Hand)

        return self.ActivateDescription == -1 and not self._celticMysticDrawTriggerPending and \
            any(self.IsRitualMonster(c) for c in self.Bot.Hand)

    def RaggedRecordsOfRitesActivate(self):
        if self.ShouldWaitForGallantThief() or self.DefaultCheckWhetherCardIsNegated(self.Card):
            return False

        if self.Card.Location == CardLocation.Grave:
            return not any(c is not None and c.IsFaceup() and not c.HasType(CardType.Ritual)
                           for c in self.Bot.GetMonsters())

        return self.HasRitualMonsterSearchTarget() and \
            (self.Card.Location == CardLocation.Hand or self.Card.Location == CardLocation.SpellZone)

    def MindShuffleActivate(self):
        if self.ShouldWaitForGallantThief() or self.DefaultCheckWhetherCardIsNegated(self.Card) or \
                self.Card.Location != CardLocation.SpellZone:
            return False

        if self.IsDescription(CardId.MindShuffle, 0):
            return self.HasRitualMonsterSearchTarget()

        if self.IsDescription(CardId.MindShuffle, 1):
            return self.HasLatestOpponentChain() and self.CanUseMindShuffleSummon() and \
                self.HasMindShuffleBreakthroughReason()

        if self.HasLatestOpponentChain() and self.CanUseMindShuffleSummon() and self.HasMindShuffleBreakthroughReason():
            return True
        return self.HasRitualMonsterSearchTarget()

    def CrimsonCallActivate(self):
        if self.ShouldWaitForGallantThief() or self.DefaultCheckWhetherCardIsNegated(self.Card):
            return False

        if self.Card.Location == CardLocation.Grave:
            return self.Duel.Phase >= DuelPhase.BattleStart and self.Bot.HasInMonstersZone(CardId.RedDragonArchfiend)

        return self.Card.Location == CardLocation.Hand or self.Card.Location == CardLocation.SpellZone

    def LightAndDarknessRitualGraveActivate(self):
        return self.Card is not None and self.Card.Location == CardLocation.Grave and \
            self.LightAndDarknessRitualActivate()

    def LightAndDarknessRitualActivate(self):
        if self.ShouldWaitForGallantThief():
            return False

        if self.Card.Location == CardLocation.Grave:
            return True

        if self.DefaultCheckWhetherCardIsNegated(self.Card):
            return False

        if self.Card.Location != CardLocation.Hand and self.Card.Location != CardLocation.SpellZone:
            return False

        if self.Duel.Turn == 1 and self._ritualSummonCountThisTurn >= 1:
            return False

        return True

    def FallenOfTheWhiteDragonActivate(self):
        if self.ShouldWaitForGallantThief() or self.ShouldSuppressWhiteDragonRouteAfterMaxxC():
            return False

        if self.Card.Location == CardLocation.Hand:
            return not self.DefaultCheckWhetherCardIsNegated(self.Card) and \
                not self.ShouldDelayForHigherPriorityHandStarter(CardId.FallenOfTheWhiteDragon) and \
                self.Bot.HasInExtra([CardId.AlbionTheBrandedDragon, CardId.EcclesiaAndTheDarkDragon,
                                     CardId.TitanikladTheAshDragon, CardId.AlbaLenatusTheAbyssDragon])

        if self.Card.Location == CardLocation.MonsterZone:
            return not self.DefaultCheckWhetherCardIsNegated(self.Card)

        return False

    def EcclesiaSpecialSummon(self):
        return not self.ShouldWaitForGallantThief() and self.Card.Location == CardLocation.Hand and \
            not self.ShouldSuppressWhiteDragonRouteAfterMaxxC() and \
            self.Enemy.GetMonsterCount() > self.Bot.GetMonsterCount() and \
            self.Duel.Phase < DuelPhase.End and \
            not self.DefaultCheckWhetherCardIsNegated(self.Card) and \
            not self.ShouldDelayForHigherPriorityHandStarter(CardId.IncredibleEcclesiaTheVirtuous)

    def AlbaLenatusSpecialSummon(self):
        if self.ShouldWaitForGallantThief():
            return False

        whiteDragon = next((c for c in self.Bot.GetMonsters() if c is not None and
                            c.IsCode(CardId.FallenOfTheWhiteDragon)), None)
        if whiteDragon is None:
            return False

        enemyDragons = [c for c in self.Enemy.GetMonsters() if c is not None and c.IsFaceup() and
                        c.HasRace(CardRace.Dragon)]
        if len(enemyDragons) == 0:
            return False

        materials = [whiteDragon]
        materials.extend(enemyDragons)
        self.AI.SelectMaterials(materials)
        return True

    def PriorityExtraDeckSpecialSummon(self):
        return not self.ShouldWaitForGallantThief()

    def StardustDragonSpecialSummon(self):
        return not self.ShouldWaitForGallantThief() and \
            (self.HasChaosRitualStarterInHand() or self.HasMindShuffleOnField() or
             not self.Bot.HasInDeck(CardId.CrimsonCall))

    def StardustDragonActivate(self):
        return not self.ShouldWaitForGallantThief() and not self.DefaultCheckWhetherCardIsNegated(self.Card)

    def TitanikladActivate(self):
        return not self.ShouldWaitForGallantThief() and self.Card.Location == CardLocation.Grave and \
            self.Duel.Phase == DuelPhase.End and not self.DefaultCheckWhetherCardIsNegated(self.Card) and \
            self.Bot.HasInDeck(CardId.FallenOfTheWhiteDragon)

    def AlbionActivate(self):
        return not self.ShouldWaitForGallantThief() and self.Card.Location == CardLocation.Grave and \
            self.Duel.Phase == DuelPhase.End and not self.DefaultCheckWhetherCardIsNegated(self.Card)

    def RedNovaDragonActivate(self):
        return not self.ShouldWaitForGallantThief() and self.Card.Location == CardLocation.MonsterZone and \
            not self.DefaultCheckWhetherCardIsNegated(self.Card)

    def PsychicEndPunisherActivate(self):
        if self.ShouldWaitForGallantThief() or self.Card.Location != CardLocation.MonsterZone or \
                self.DefaultCheckWhetherCardIsNegated(self.Card):
            return False
        return True

    def PsychicEndPunisherSpecialSummon(self):
        return not self.ShouldWaitForGallantThief()

    def ChaosAngelActivate(self):
        return not self.ShouldWaitForGallantThief() and self.Card.Location == CardLocation.MonsterZone and \
            not self.DefaultCheckWhetherCardIsNegated(self.Card) and \
            self.HasFreshOpponentTarget(self.Enemy.GetMonsters() + self.Enemy.GetSpells())

    def CrimsonKingActivate(self):
        return not self.ShouldWaitForGallantThief() and self.Card.Location == CardLocation.MonsterZone and \
            not self.DefaultCheckWhetherCardIsNegated(self.Card)

    def EnigmasterPackbitActivate(self):
        return not self.ShouldWaitForGallantThief() and self.Card.Location == CardLocation.Grave and \
            not self.DefaultCheckWhetherCardIsNegated(self.Card) and \
            self.HasFreshOpponentTarget([c for c in self.Enemy.GetMonsters() if c is not None and c.IsFaceup()])

    def EcclesiaAndTheDarkDragonActivate(self):
        return not self.ShouldWaitForGallantThief() and self.Card.Location == CardLocation.Grave and \
            not self.DefaultCheckWhetherCardIsNegated(self.Card) and \
            self.HasFreshOpponentTarget(self.Enemy.GetMonsters() + self.Enemy.GetSpells())

    def WindPegasusIgnisterActivate(self):
        if self.ShouldWaitForGallantThief() or self.DefaultCheckWhetherCardIsNegated(self.Card):
            return False
        return self.Card.Location == CardLocation.Grave and \
            self.HasFreshOpponentTarget(self.Enemy.GetMonsters() + self.Enemy.GetSpells())

    def GoldenCloudBeastMalongActivate(self):
        return not self.ShouldWaitForGallantThief() and self.Card.Location == CardLocation.Grave and \
            not self.DefaultCheckWhetherCardIsNegated(self.Card) and \
            self.HasFreshOpponentTarget(self.Enemy.GetMonsters() + self.Enemy.GetSpells())

    def HeraldOfTheArcLightActivate(self):
        return not self.ShouldWaitForGallantThief() and self.Card.Location == CardLocation.Grave and \
            not self.DefaultCheckWhetherCardIsNegated(self.Card)

    def CrimsonKingSpecialSummon(self):
        return not self.ShouldWaitForGallantThief() and not self.HasMindShuffleOnField() and \
            self.Bot.HasInDeck(CardId.CrimsonCall) and not self.HasChaosRitualStarterInHand()

    def HasChaosRitualStarterInHand(self):
        return any(self.IsHandStarterAvailable(i) for i in self.GetHandStarterOrder())

    def GetHandStarterOrder(self):
        return [
            CardId.RaggedRecordsOfRites,
            CardId.IncredibleEcclesiaTheVirtuous,
            CardId.FallenOfTheWhiteDragon,
            CardId.BlackChaos,
            CardId.Griffoh,
        ]

    def ShouldDelayForHigherPriorityHandStarter(self, cardId):
        if len(self.Duel.CurrentChain) != 0:
            return False

        order = self.GetHandStarterOrder()
        currentIndex = order.index(cardId) if cardId in order else -1
        if currentIndex < 0:
            return False

        for i in range(currentIndex):
            if self.IsHandStarterAvailable(order[i]):
                return True
        return False

    def ShouldSuppressWhiteDragonRouteAfterMaxxC(self):
        if self.Duel.Player != 0 or not self._enemyMaxxCResolved:
            return False
        return any(c is not None and c.IsCode(CardId.BlackChaos, CardId.RaggedRecordsOfRites, CardId.Griffoh,
                                              CardId.CelticMystic) for c in self.Bot.Hand)

    def ShouldSummonCelticMysticFirst(self):
        return len(self.Duel.CurrentChain) == 0 and \
            any(c is not None and c.IsCode(CardId.CelticMystic) and not self.DefaultCheckWhetherCardIsNegated(c) and
                (any(handCard is not None and handCard != c and self.IsRitualRelatedCard(handCard)
                     for handCard in self.Bot.Hand) or
                 any(self.IsRitualMonster(h) for h in self.Bot.Hand))
                for c in self.Duel.MainPhase.SummonableCards)

    def IsHandStarterAvailable(self, cardId):
        card = next((c for c in self.Bot.Hand if c is not None and c.IsCode(cardId)), None)
        if card is None or self.DefaultCheckWhetherCardIsNegated(card):
            return False

        if cardId == CardId.RaggedRecordsOfRites:
            return self.HasRitualMonsterSearchTarget()

        if cardId == CardId.IncredibleEcclesiaTheVirtuous:
            return self.Enemy.GetMonsterCount() > self.Bot.GetMonsterCount() and self.Duel.Phase < DuelPhase.End

        if cardId == CardId.FallenOfTheWhiteDragon:
            return self.HasFallenExtraDeckCost()

        if cardId == CardId.Griffoh:
            return self.CanSetGriffohSupportCard() or self.CanReceiveDamage()

        if cardId == CardId.BlackChaos:
            return self.CanSearchBlackChaosSupportCard()

        return False

    def EcclesiaActivate(self):
        if self.ShouldWaitForGallantThief() or self.DefaultCheckWhetherCardIsNegated(self.Card):
            return False

        if self.Card.Location == CardLocation.MonsterZone:
            if self.ShouldSuppressWhiteDragonRouteAfterMaxxC():
                return False
            return not self.Bot.HasInMonstersZone(CardId.FallenOfTheWhiteDragon)

        if self.Card.Location == CardLocation.Grave:
            return self.Duel.Phase == DuelPhase.End

        return False

    def SkullArchfiendOfChaosActivate(self):
        if self.ShouldWaitForGallantThief() or self.DefaultCheckWhetherCardIsNegated(self.Card):
            return False

        if self.Card.Location == CardLocation.Hand:
            return False

        if self.Card.Location == CardLocation.Grave:
            if self.IsDescription(CardId.SkullArchfiendOfChaos, 1) or self.ActivateDescription == -1:
                return True

            if not self.IsDescription(CardId.SkullArchfiendOfChaos, 0):
                return False

            if self.IsSkullArchfiendReturnPending(self.Card):
                return False

            recycleCandidates = self.GetRitualRecycleCandidates()
            return len(recycleCandidates) >= 4 and any(self.IsRitualRelatedCard(c) for c in recycleCandidates)

        return False

    def MagicianOfDarkChaosActivate(self):
        if self.ShouldWaitForGallantThief() or self.Card.Location != CardLocation.MonsterZone or \
                self.DefaultCheckWhetherCardIsNegated(self.Card):
            return False

        if self.IsDescription(CardId.MagicianOfDarkChaosBlackChaos, 1):
            return self.HasFreshOpponentTarget(self.Enemy.GetMonsters() + self.Enemy.GetSpells())

        if self.IsDescription(CardId.MagicianOfDarkChaosBlackChaos, 0) or self.ActivateDescription == -1:
            return any(c.IsSpell() for c in self.Bot.Graveyard)

        return False

    def TheFallenTheVirtuousActivate(self):
        if self.ShouldWaitForGallantThief() or self.DefaultCheckWhetherCardIsNegated(self.Card) or \
                not self.HasFallenExtraDeckCost():
            return False
        return self.HasFreshOpponentTarget(self.GetOrderedFallenTargets(self.Enemy.GetMonsters() + self.Enemy.GetSpells()))

    def SpellShatteringSwordActivate(self):
        if self.ShouldWaitForGallantThief() or self.DefaultCheckWhetherCardIsNegated(self.Card):
            return False

        if self.Card.Location == CardLocation.Grave or self.Card.Location == CardLocation.Removed:
            return self.IsDescription(CardId.SpellShatteringSword, 3) or self.ActivateDescription == -1

        if len(self.Duel.CurrentChain) == 0:
            return False

        latest = self.GetLatestChainInfo()
        if latest is None or latest.ActivatePlayer != 1:
            return False

        self._pendingSpellShatteringSwordSpellDestroy = self.CanUseSpellShatteringSwordSpellDestroy(latest)
        self._pendingSpellShatteringSwordMonsterTarget = self.GetSpellShatteringSwordMonsterTarget(latest)
        canClearSpells = self._pendingSpellShatteringSwordSpellDestroy
        canDisableMonster = self._pendingSpellShatteringSwordMonsterTarget is not None
        return canClearSpells or canDisableMonster

    def CanUseSpellShatteringSwordSpellDestroy(self, *args):
        if args:  # CanUseSpellShatteringSwordSpellDestroy(ChainInfo chain)
            chain = args[0]
            if chain is None or chain.ActivatePlayer != 1 or not chain.HasLocation(CardLocation.SpellZone):
                return False
            isSpell = (chain.ActivateType & CardType.Spell) != 0
            isContinuousOrField = (chain.ActivateType & (CardType.Continuous | CardType.Field)) != 0
            return isSpell and isContinuousOrField and self.HasFreshOpponentTarget(self.Enemy.GetSpells())

        if self._pendingSpellShatteringSwordSpellDestroy:
            return True
        return self.CanUseSpellShatteringSwordSpellDestroy(self.GetLatestChainInfo())

    def CanUseSpellShatteringSwordMonsterNegate(self):
        t = self._pendingSpellShatteringSwordMonsterTarget
        if t is not None and t.Controller == 1 and t.IsOnField() and t.IsFaceup():
            return True
        self._pendingSpellShatteringSwordMonsterTarget = self.GetSpellShatteringSwordMonsterTarget(self.GetLatestChainInfo())
        return self._pendingSpellShatteringSwordMonsterTarget is not None

    def GetSpellShatteringSwordMonsterTarget(self, chain):
        if not any(c.IsCode(CardId.LightAndDarknessRitual) for c in self.Bot.Hand + self.Bot.Graveyard):
            return None
        source = self.GetChainSourceCard(chain)
        if source is None or source.IsDisabled() or not self.HasFreshOpponentTarget([source]):
            return None
        return source

    def SpatialTrunadeActivate(self):
        if self.ShouldWaitForGallantThief() or self.DefaultCheckWhetherCardIsNegated(self.Card):
            return False
        return self.CanUseSpatialTrunadeOnEnemyField()

    def DrollLockBirdActivate(self):
        if self.ShouldWaitForGallantThief() or self.DefaultCheckWhetherCardIsNegated(self.Card) or \
                self.Duel.Player != 1 or self.Duel.LastChainPlayer != 1:
            return False
        return True

    def ChaosSpellSet(self):
        if not (self.Card.IsTrap() or self.Card.HasType(CardType.QuickPlay) or self.DefaultSpellMustSetFirst()):
            return False

        reservedZones = 1
        albionMaySetFallen = self.Bot.HasInGraveyard(CardId.AlbionTheBrandedDragon) and \
            self.Bot.HasInDeck(CardId.TheFallenTheVirtuous)
        handEngineMaySetSupport = self.Bot.HasInHand(CardId.Griffoh) and self.CanSetGriffohSupportCard() or \
            self.Bot.HasInHand(CardId.BlackChaos) and self.CanSearchBlackChaosSupportCard()
        if albionMaySetFallen or handEngineMaySetSupport:
            reservedZones = 2

        return self.Bot.GetSpellCountWithoutField() < 5 - reservedZones

    def SelectResolutionCard(self, chain, cards, min_, max_, hint):
        if chain.IsActivateCode(CardId.RaggedRecordsOfRites):
            if hint == HintMsg.Confirm:
                return self.SelectPreferredIds(cards, min_, max_, CardId.LightAndDarknessRitual)
            if hint == HintMsg.AddToHand:
                selected = self.SelectRaggedRecordsSearchCard(cards, min_, max_)
                if selected is not None:
                    self._activatedFirstEffectCardIdsThisTurn.add(CardId.RaggedRecordsOfRites)
                return selected

        if chain.IsActivateCode(CardId.CelticMystic) and hint == HintMsg.Discard:
            return self.SelectCelticMysticDiscardCards(cards, min_, max_)

        if chain.IsActivateCode(CardId.MindShuffle):
            if hint == HintMsg.AddToHand:
                return self.SelectMindShuffleSearchCard(cards, min_, max_)
            if hint == HintMsg.SpSummon:
                return self.SelectMindShuffleSummonMonster(cards, min_, max_)
            if hint == HintMsg.Discard:
                return self.SelectMindShuffleDiscardCards(cards, min_, max_)
            if hint == HintMsg.ReturnToHand:
                returnCandidates = [c for c in cards if self.IsMindShuffleReturnCandidate(c)]
                magicianTargeted = any(c.IsCode(CardId.MagicianOfDarkChaosBlackChaos) and
                                       self.IsOpponentTargetedByCurrentChain(c) for c in returnCandidates)
                if self.IsMindShuffleProtectionThreat() and not magicianTargeted:
                    returnCandidates = [c for c in returnCandidates if not c.IsCode(CardId.MagicianOfDarkChaosBlackChaos)]
                returnCandidates = sorted(returnCandidates, key=lambda c: (
                    -int(self.IsOpponentTargetedByCurrentChain(c)), -int(self.WasCardActivatedThisTurn(c)),
                    self.GetMindShuffleReturnPriority(c)))
                selected = self.SelectCount(returnCandidates, cards, min_, max_, 1)
                self._pendingMindShuffleReturnCards.clear()
                if selected is not None:
                    for selectedCard in selected:
                        if selectedCard is not None:
                            self._pendingMindShuffleReturnCards.add(selectedCard)
                return selected

        if chain.IsActivateCode(CardId.CrimsonCall) and hint == HintMsg.AddToHand:
            return self.SelectPreferredIds(cards, min_, max_, CardId.Griffoh)

        if chain.IsActivateCode(CardId.LightAndDarknessRitual) and hint == HintMsg.SpSummon:
            return self.SelectRitualMonster(cards, min_, max_)

        if chain.IsActivateCode(CardId.LightAndDarknessRitual) and hint == HintMsg.AddToHand:
            return self.SelectLightAndDarknessGraveCard(cards, min_, max_)

        if chain.IsActivateCode(CardId.TitanikladTheAshDragon):
            if hint == HintMsg.AddToHand or hint == HintMsg.SpSummon:
                return self.SelectPreferredIds(cards, min_, max_, CardId.FallenOfTheWhiteDragon)

        if chain.IsActivateCode(CardId.AlbionTheBrandedDragon) and (hint == HintMsg.AddToHand or hint == HintMsg.Set):
            fallen = self.SelectPreferredIds(cards, min_, max_, CardId.TheFallenTheVirtuous)
            if fallen is not None:
                return fallen
            branded = self.SelectCount([c for c in cards if c is not None and c.HasSetcode(0x15d)], cards, min_, max_, 1)
            if branded is not None:
                return branded

        if chain.IsActivateCode(CardId.RedNovaDragonBurningSoul) and hint == HintMsg.AddToHand:
            return self.SelectPreferredIds(cards, min_, max_, CardId.LightAndDarknessRitual, CardId.RaggedRecordsOfRites,
                                           CardId.MindShuffle, CardId.CrimsonCall)

        if chain.IsActivateCode(CardId.TheCrimsonKing) and hint == HintMsg.AddToHand:
            return self.SelectPreferredIds(cards, min_, max_, CardId.CrimsonCall, CardId.RedDragonArchfiend,
                                           CardId.TheCrimsonKing)

        if chain.IsActivateCode(CardId.HeraldOfTheArcLight) and hint == HintMsg.AddToHand:
            ritualMonster = self.SelectRitualMonster(cards, min_, max_)
            if ritualMonster is not None:
                return ritualMonster
            return self.SelectPreferredIds(cards, min_, max_, CardId.LightAndDarknessRitual)

        if chain.IsActivateCode(CardId.ChaosAngel) and (hint == HintMsg.Target or hint == HintMsg.Remove):
            return self.SelectEffectTarget(cards, min_, max_, False)

        if chain.IsActivateCode(CardId.PsychicEndPunisher) and (hint == HintMsg.Target or hint == HintMsg.Remove):
            ownMonsters = sorted((c for c in cards if c is not None and c.Controller == 0 and c.IsMonster()),
                                 key=lambda c: c.Attack)
            if len(ownMonsters) > 0:
                return self.SelectCount(ownMonsters, cards, min_, max_, 1)
            return self.SelectEffectTarget(cards, min_, max_, False)

        if chain.IsActivateCode(CardId.EnigmasterPackbit) and hint == HintMsg.Target:
            return self.SelectEffectTarget([c for c in cards if c is not None and c.Controller == 1 and c.IsMonster() and
                                            c.IsFaceup()], min_, max_, False)

        if chain.IsActivateCode(CardId.EcclesiaAndTheDarkDragon) and (hint == HintMsg.Target or hint == HintMsg.ToDeck):
            return self.SelectEcclesiaAndTheDarkDragonTarget(cards, min_, max_)

        if (chain.IsActivateCode(CardId.WindPegasusIgnister) or chain.IsActivateCode(CardId.GoldenCloudBeastMalong)) and \
                hint == HintMsg.Target:
            return self.SelectEffectTarget(cards, min_, max_, False)

        if chain.IsActivateCode(CardId.FydraulisHarmonia) and hint == HintMsg.Confirm:
            candidates = [c for c in cards if c is not None and c.HasType(CardType.Synchro)]
            self._pendingFydraulisSynchroToGraveId = self.GetPreferredFydraulisSynchroToGraveId(candidates)

            synchros = []
            if self._pendingFydraulisSynchroToGraveId != 0:
                payload = next((c for c in candidates if c.IsCode(self._pendingFydraulisSynchroToGraveId)), None)
                if payload is not None:
                    synchros.append(payload)
            synchros.extend(sorted((c for c in candidates if c not in synchros), key=lambda c: c.Attack))
            synchros = synchros[:min(5, max_)]
            if len(synchros) >= min_:
                return self.Util.CheckSelectCount(synchros, cards, min_, max_)

        if chain.IsActivateCode(CardId.FydraulisHarmonia) and hint == HintMsg.ToGrave:
            return self.SelectFydraulisSynchroToGrave(cards, min_, max_)

        if chain.IsActivateCode(CardId.FydraulisHarmonia) and (hint == HintMsg.Destroy or hint == HintMsg.Target):
            ordered = self.GetOrderedFydraulisTargets([c for c in cards if c.Controller == 1 and c.IsMonster()])
            fallback = sorted((c for c in cards if c is not None and c.Controller == 1 and c.IsMonster() and
                               c not in ordered),
                              key=lambda c: (-self.GetFydraulisTargetPriority(c), -c.GetDefensePower()))
            candidates = []
            if self._pendingFydraulisDestructionTarget is not None and self._pendingFydraulisDestructionTarget in cards:
                candidates.append(self._pendingFydraulisDestructionTarget)
            candidates.extend(c for c in ordered + fallback
                              if c != self._pendingFydraulisDestructionTarget and not self.IsOpponentTargetReserved(c))
            return self.SelectCount(candidates, cards, min_, max_, 1)

        if chain.IsActivateCode(CardId.Griffoh) and hint == HintMsg.Set:
            return self.SelectGriffohSetCard(cards, min_, max_)

        if chain.IsActivateCode(CardId.BlackSkullDragonTheArchfiendDragonOfUnity) and hint == HintMsg.Discard:
            return self.SelectBlackSkullDragonDiscardCard(cards, min_, max_)

        if chain.IsActivateCode(CardId.FallenOfTheWhiteDragon):
            if hint == HintMsg.ToGrave:
                return self.SelectFallenExtraDeckCost(cards, min_, max_)
            if hint == HintMsg.SpSummon:
                return self.SelectPreferredIds(cards, min_, max_, CardId.IncredibleEcclesiaTheVirtuous)

        if chain.IsActivateCode(CardId.BlackSkullDragonTheArchfiendDragonOfUnity) and hint == HintMsg.Set:
            return self.SelectBlackSkullDragonSupportCard(cards, min_, max_)

        if chain.IsActivateCode(CardId.BlackChaos) and \
                (hint == HintMsg.Set or hint == HintMsg.ToField or hint == HintMsg.AddToHand):
            selected = self.SelectPreferredIds(cards, min_, max_, CardId.MindShuffle)
            self._pendingBlackChaosSupportSearch = False
            if selected is not None:
                self.ReservePendingDeckSearch(selected)
            return selected

        if chain.IsActivateCode(CardId.SkullArchfiendOfChaos):
            if hint == HintMsg.ToGrave:
                return self.SelectPreferredIds(cards, min_, max_, CardId.LightAndDarknessRitual)
            if hint == HintMsg.AddToHand:
                return self.SelectRitualMonster(cards, min_, max_)
            if hint == HintMsg.ToDeck:
                return self.SelectSkullArchfiendRecycleCards(cards, min_, max_)

        if chain.IsActivateCode(CardId.MagicianOfDarkChaosBlackChaos) and hint == HintMsg.AddToHand:
            return self.SelectPreferredIds(cards, min_, max_, CardId.TheFallenTheVirtuous, CardId.SpatialTrunade,
                                           CardId.CrimsonCall, CardId.RaggedRecordsOfRites,
                                           CardId.SpellShatteringSword, CardId.LightAndDarknessRitual)

        if chain.IsActivateCode(CardId.MagicianOfDarkChaosBlackChaos) and (hint == HintMsg.Remove or hint == HintMsg.Target):
            return self.SelectEffectTarget(cards, min_, max_, False)

        if chain.IsActivateCode(CardId.BlackLusterSoldierSoldierOfLightAndDarkness) and \
                (hint == HintMsg.Remove or hint == HintMsg.Target):
            problematic = self.Util.GetProblematicEnemyCard(0, True)
            if problematic is not None and problematic in cards:
                return self.SelectNonOverlappingTarget(cards, min_, max_, [problematic])
            return self.SelectNonOverlappingTarget(
                cards, min_, max_, sorted((c for c in cards if c.Controller == 1),
                                          key=lambda c: (-int(c.IsFaceup()), -c.GetDefensePower())))

        if chain.IsActivateCode(CardId.TheFallenTheVirtuous):
            if hint == HintMsg.ToGrave:
                return self.SelectFallenExtraDeckCost(cards, min_, max_)
            if hint == HintMsg.Destroy or hint == HintMsg.Target:
                ordered = self.GetOrderedFallenTargets([c for c in cards if c.Controller == 1])
                fallback = sorted((c for c in cards if c is not None and c.Controller == 1 and c.IsFaceup() and
                                   c not in ordered),
                                  key=lambda c: (-self.GetFallenTargetPriority(c), -max(c.Attack, c.Defense)))
                return self.SelectNonOverlappingTarget(cards, min_, max_, ordered + fallback)

        if chain.IsActivateCode(CardId.SpellShatteringSword):
            if hint == HintMsg.Confirm:
                return self.SelectPreferredIds(cards, min_, max_, CardId.LightAndDarknessRitual)
            if hint == HintMsg.Target or hint == HintMsg.Disable:
                return self.SelectSpellShatteringSwordMonsterTarget(cards, min_, max_)
            if hint == HintMsg.Destroy:
                return self.SelectEffectTarget(cards, min_, max_, False, False)

        if chain.IsActivateCode(CardId.SpatialTrunade) and hint == HintMsg.ReturnToHand:
            enemyCards = sorted((c for c in cards if c.Controller == 1 and not self.IsOpponentTargetReserved(c)),
                                key=lambda c: (-self.GetSpatialTrunadePriority(c), -c.GetDefensePower()))
            if len(enemyCards) > 0:
                return self.SelectCount(enemyCards, cards, min_, max_, min(2, max_))

        return None

    def SelectRitualMonster(self, cards, min_, max_):
        ordered = sorted((c for c in cards if self.IsRitualMonster(c)), key=self.GetRitualMonsterPriority)
        return self.SelectCount(ordered, cards, min_, max_, 1)

    def SelectLightAndDarknessGraveCard(self, cards, min_, max_):
        return self.SelectPreferredIds(cards, min_, max_,
                                       CardId.BlackSkullDragonTheArchfiendDragonOfUnity,
                                       CardId.CelticMystic,
                                       CardId.SkullArchfiendOfChaos,
                                       CardId.MagicianOfDarkChaosBlackChaos,
                                       CardId.BlackLusterSoldierSoldierOfLightAndDarkness,
                                       CardId.LightAndDarknessRitual)

    def SelectMindShuffleSummonMonster(self, cards, min_, max_):
        returnTarget = self.GetMindShuffleReturnTarget()
        allowUsedTargets = returnTarget is not None and self.IsOpponentTargetedByCurrentChain(returnTarget)
        summonOrder = self.GetMindShuffleSummonOrderForCurrentChain()
        ordered = []
        for id_ in summonOrder:
            ordered.extend([c for c in cards if c is not None and c.Location == CardLocation.Hand and c.IsCode(id_) and
                            (allowUsedTargets or not self.WasCardActivatedThisTurn(c)) and
                            (returnTarget is None or not c.IsCode(returnTarget.Id)) and c not in ordered])
        ordered.extend([c for c in cards if c is not None and c.Location == CardLocation.Hand and c.IsMonster() and
                        (allowUsedTargets or not self.WasCardActivatedThisTurn(c)) and
                        (returnTarget is None or not c.IsCode(returnTarget.Id)) and c not in ordered])

        selected = self.SelectCount(ordered, cards, min_, max_, 1)
        if selected is not None and len(selected) > 0:
            self._pendingMindShuffleSummonId = selected[0].Id
        return selected

    def GetSpatialTrunadePriority(self, card):
        if card is None or card.Controller != 1:
            return -1
        problematic = self.Util.GetProblematicEnemyCard(0, False)
        if card == problematic:
            return 300
        if card.IsExtraCard():
            return 200
        if card.IsFacedown():
            return 100
        return 0

    def SelectFydraulisSynchroToGrave(self, cards, min_, max_):
        preferredId = self._pendingFydraulisSynchroToGraveId
        if preferredId == 0 or not any(c is not None and c.IsCode(preferredId) for c in cards):
            preferredId = self.GetPreferredFydraulisSynchroToGraveId(cards)

        self._pendingFydraulisSynchroToGraveId = 0
        if preferredId != 0:
            selected = self.SelectPreferredIds(cards, min_, max_, preferredId)
            if selected is not None:
                return selected
        return self.SelectCount(sorted((c for c in cards if c is not None and c.HasType(CardType.Synchro)),
                                       key=lambda c: c.Attack), cards, min_, max_, 1)

    def GetPreferredFydraulisSynchroToGraveId(self, available):
        candidates = [c for c in available if c is not None and c.HasType(CardType.Synchro)]
        preferredIds = []
        enemyMonsterCount = self.Enemy.GetMonsterCount()
        if enemyMonsterCount >= 2 and (self.HasDuplicateCardInHand() or not self.CanActivatePurulia()):
            preferredIds.append(CardId.EnigmasterPackbit)
        if enemyMonsterCount >= 2:
            preferredIds.append(CardId.GoldenCloudBeastMalong)
        if self._ownMonsterReleasedToGraveThisTurn:
            preferredIds.append(CardId.StardustDragonVictimSanctuary)
        if not any(self.IsRitualMonster(c) for c in self.Bot.Hand):
            preferredIds.append(CardId.HeraldOfTheArcLight)
        if enemyMonsterCount == 1:
            preferredIds.append(CardId.WindPegasusIgnister)

        return next((id_ for id_ in preferredIds if any(c.IsCode(id_) for c in candidates)), 0)

    def SelectSkullArchfiendRecycleCards(self, cards, min_, max_):
        candidates = self.LimitSkullArchfiendRitualCopies([c for c in cards if self.IsSkullArchfiendRecycleCandidate(c)])
        if len(candidates) < min_:
            return None

        ordered = sorted(candidates, key=lambda c: (self.GetSkullArchfiendRecycleLocationPriority(c),
                                                    self.GetSkullArchfiendRecycleCardPriority(c),
                                                    -int(self.IsDuplicateInGrave(c, cards))))

        ritualRelated = next((c for c in ordered if self.IsRitualRelatedCard(c)), None)
        if ritualRelated is None:
            return None
        ordered.remove(ritualRelated)
        ordered.insert(0, ritualRelated)
        desired = min(max_, max(min_, 3))
        return self.SelectCount(ordered, cards, min_, max_, desired)

    def GetSkullArchfiendRecycleLocationPriority(self, card):
        if card is not None and card.IsCode(CardId.MindShuffle) and card.Location == CardLocation.Removed:
            return 0
        if card is not None and card.IsCode(CardId.MindShuffle) and card.Location == CardLocation.Grave:
            return 1
        if card is not None and card.Location == CardLocation.Removed:
            return 2
        return 3

    def GetSkullArchfiendRecycleCardPriority(self, card):
        if card is None:
            return 99
        if card.IsCode(CardId.BlackChaos):
            return 0
        if card.IsCode(CardId.BlackSkullDragonTheArchfiendDragonOfUnity):
            return 1
        if card.IsCode(CardId.TheFallenTheVirtuous):
            return 2
        if card.IsCode(CardId.MaxxC):
            return 3
        if card.IsCode(CardId.FallenOfTheWhiteDragon):
            return 4
        if card.IsCode(CardId.Griffoh):
            return 5
        if card.IsCode(CardId.CelticMystic):
            return 6
        if card.IsCode(CardId.AshBlossomJoyousSpring):
            return 7
        if card.IsCode(CardId.SkullArchfiendOfChaos):
            return 8
        return 9

    def IsOwnGraveyardRitualMonster(self, card):
        return card is not None and card.Controller == 0 and card.Location == CardLocation.Grave and \
            self.HasKnownCardType(card, CardType.Monster) and self.HasKnownCardType(card, CardType.Ritual)

    def IsDuplicateInGrave(self, card, cards):
        return card is not None and card.Id != 0 and \
            sum(1 for c in cards if c is not None and c.Location == CardLocation.Grave and c.Id == card.Id) > 1

    def SelectGriffohSetCard(self, cards, min_, max_):
        if not self.HasPendingBlackChaosSupportSearch() and not self.HasMindShuffleOnField() and \
                self.Bot.HasInDeck(CardId.MindShuffle):
            mindShuffle = self.SelectCount([c for c in cards if c is not None and c.IsCode(CardId.MindShuffle) and
                                            not self.IsPendingDeckSearch(c)], cards, min_, max_, 1)
            if mindShuffle is not None:
                self.ReservePendingDeckSearch(mindShuffle)
                return mindShuffle

        if self.HasPendingBlackChaosSupportSearch():
            alternatives = [CardId.SpellShatteringSword]
            for id_ in alternatives:
                if self.IsSearchTargetUnavailable(id_):
                    continue
                selected = self.SelectPreferredIds(cards, min_, max_, id_)
                if selected is not None:
                    self.ReservePendingDeckSearch(selected)
                    return selected
            return None

        return self.SelectCommonRitualSupportCard(cards, min_, max_)

    def HasPendingBlackChaosSupportSearch(self):
        return self._pendingBlackChaosSupportSearch

    def SelectBlackSkullDragonSupportCard(self, cards, min_, max_):
        if self.ShouldPrioritizeLightAndDarknessRitual():
            ritual = self.SelectPreferredIdPreferGrave(cards, min_, max_, CardId.LightAndDarknessRitual)
            if ritual is not None:
                return ritual

        preferredIds = [CardId.MindShuffle, CardId.SpellShatteringSword, CardId.LightAndDarknessRitual]
        for id_ in preferredIds:
            if self.IsSearchTargetUnavailable(id_):
                continue
            selected = self.SelectPreferredIdPreferGrave(cards, min_, max_, id_)
            if selected is not None:
                return selected

        return None

    def SelectRaggedRecordsSearchCard(self, cards, min_, max_):
        preferredIds = [CardId.Griffoh, CardId.BlackChaos, CardId.CelticMystic,
                        CardId.BlackSkullDragonTheArchfiendDragonOfUnity]

        def rank(c):
            unused = not self.WasCardActivatedThisTurn(c)
            missingFromHand = not self.Bot.HasInHand(c.Id)
            if unused and missingFromHand:
                return 0
            if unused:
                return 1
            if missingFromHand:
                return 2
            return 3

        ordered = sorted((c for c in cards if c is not None and c.Id in preferredIds and not self.IsPendingDeckSearch(c)),
                         key=lambda c: (rank(c), preferredIds.index(c.Id)))
        if len(ordered) > 0:
            return self.Util.CheckSelectCount(ordered, cards, min_, max_)

        return self.SelectRitualMonster(cards, min_, max_)

    def SelectMindShuffleSearchCard(self, cards, min_, max_):
        if not self.ShouldUseMindShuffleFallback():
            skull = self.SelectHandMissingIds(cards, min_, max_, CardId.SkullArchfiendOfChaos)
            if skull is not None:
                return skull

        fallback = self.SelectHandMissingIds(cards, min_, max_,
                                             CardId.BlackSkullDragonTheArchfiendDragonOfUnity,
                                             CardId.MagicianOfDarkChaosBlackChaos,
                                             CardId.BlackLusterSoldierSoldierOfLightAndDarkness,
                                             CardId.BlackChaos, CardId.CelticMystic, CardId.Griffoh)
        if fallback is not None:
            return fallback

        return self.SelectRitualMonster(cards, min_, max_)

    def SelectBlackSkullDragonDiscardCard(self, cards, min_, max_):
        ordered = []
        ordered.extend(c for c in cards if c is not None and c.IsCode(CardId.LightAndDarknessRitual))
        ordered.extend([c for c in cards if self.IsDuplicateSpellInHand(c) and c not in ordered])
        ordered.extend([c for c in cards if c is not None and c.IsCode(CardId.SpatialTrunade) and
                        not self.CanUseSpatialTrunadeOnEnemyField() and c not in ordered])
        ordered.extend([c for c in cards if self.IsBlackSkullDiscardSpell(c) and self.WasCardActivatedThisTurn(c) and
                        c not in ordered])

        if len(ordered) == 0:
            return None
        return self.Util.CheckSelectCount(ordered, cards, min_, max_)

    def SelectMindShuffleDiscardCards(self, cards, min_, max_):
        ordered = []
        if not self.ShouldUseMindShuffleFallback():
            ordered.extend(c for c in cards if c is not None and c.IsCode(CardId.SkullArchfiendOfChaos))
            ordered.extend([c for c in self.GetOrderedDiscardCards(cards) if c not in ordered])
        else:
            ordered.extend(c for c in cards if c is not None and c.IsCode(CardId.MulcharmyPurulia))
            ordered.extend([c for c in cards if self.IsDuplicateInSelection(c, cards) and c not in ordered])
            ordered.extend([c for c in cards if c is not None and c.IsCode(CardId.TheWorldsGreatestGallantThief) and
                            c not in ordered])
            ordered.extend([c for c in self.GetOrderedDiscardCards(cards) if c not in ordered])

        if len(ordered) == 0:
            return None
        return self.Util.CheckSelectCount(ordered, cards, min_, max_)

    def SelectCelticMysticDiscardCards(self, cards, min_, max_):
        ordered = []
        ordered.extend(c for c in cards if c is not None and c.IsCode(
            CardId.MulcharmyPurulia, CardId.SkullArchfiendOfChaos, CardId.TheWorldsGreatestGallantThief))
        ordered.extend([c for c in cards if self.IsDuplicateInSelection(c, cards) and c not in ordered])
        ordered.extend([c for c in cards if self.WasCardActivatedThisTurn(c) and c not in ordered])
        ordered.extend(sorted((c for c in cards if c not in ordered), key=self.GetDiscardPriority))

        if len(ordered) == 0:
            return None
        return self.Util.CheckSelectCount(ordered, cards, min_, max_)

    def SelectCommonRitualSupportCard(self, cards, min_, max_):
        preferredIds = [CardId.MindShuffle, CardId.SpellShatteringSword]
        for id_ in preferredIds:
            if self.IsSearchTargetUnavailable(id_):
                continue
            selected = self.SelectPreferredIds(cards, min_, max_, id_)
            if selected is not None:
                self.ReservePendingDeckSearch(selected)
                return selected
        return None

    def SelectHandMissingIds(self, cards, min_, max_, *ids):
        ordered = []
        for id_ in ids:
            if self.Bot.HasInHand(id_):
                continue
            ordered.extend([c for c in cards if c is not None and c.IsCode(id_) and not self.IsPendingDeckSearch(c) and
                            c not in ordered])

        if len(ordered) == 0:
            return None
        return self.Util.CheckSelectCount(ordered, cards, min_, max_)

    def GetOrderedDiscardCards(self, cards):
        return sorted(cards, key=lambda c: (0 if self.IsDuplicateInSelection(c, cards) else 1,
                                            0 if self.WasCardActivatedThisTurn(c) else 1,
                                            self.GetDiscardPriority(c)))

    def SelectEffectTarget(self, cards, min_, max_, allowOwnFallback, targeted=True):
        problematic = self.Util.GetProblematicEnemyCard(0, True)
        enemyCards = sorted((c for c in cards if c is not None and c.Controller == 1),
                            key=lambda c: (-self.GetGeneralRemovalPriority(c, problematic, targeted),
                                           -max(c.Attack, c.Defense)))
        if len(enemyCards) > 0:
            enemySelection = self.SelectNonOverlappingTarget(cards, min_, max_, enemyCards)
            if enemySelection is not None:
                return enemySelection

        if not allowOwnFallback:
            return None

        return self.SelectCount(sorted((c for c in cards if c is not None and c.Controller == 0),
                                       key=lambda c: c.GetDefensePower()), cards, min_, max_, 1)

    def GetGeneralRemovalPriority(self, card, problematic, targeted):
        if card is None or card.Controller != 1:
            return -1

        priority = 1200 if card == problematic else 0
        if card.IsMonster():
            if card.IsFloodgate():
                priority = max(priority, 1100)
            elif card.IsMonsterDangerous():
                priority = max(priority, 1050)
            elif card.IsMonsterShouldBeDisabledBeforeItUseEffect():
                priority = max(priority, 1000)
            elif self.IsValuableFallenExtraDeckMonster(card):
                priority = max(priority, 850)
            elif card.IsFaceup():
                priority = max(priority, 500)

            if card.IsDisabled():
                priority -= 300
            if targeted and self.CanLikelyEscapeFallenTarget(card):
                priority -= 450
            return priority

        if card.IsFloodgate():
            priority = max(priority, 1100)
        elif card.IsFacedown():
            priority = max(priority, 800)
        elif card.HasType(CardType.Field):
            priority = max(priority, 750)
        elif card.HasType(CardType.Continuous):
            priority = max(priority, 700)
        else:
            priority = max(priority, 400)
        return priority

    def SelectEcclesiaAndTheDarkDragonTarget(self, cards, min_, max_):
        enemyCards = [c for c in cards if c is not None and c.Controller == 1 and c.IsOnField()]
        if len(enemyCards) == 0:
            return None

        problematic = self.Util.GetProblematicEnemyCard(0, True)
        ordered = sorted(enemyCards, key=lambda c: (self.GetEcclesiaTargetPriority(c), -c.GetDefensePower()))

        if problematic is not None and problematic in ordered:
            ordered.remove(problematic)
            ordered.insert(0, problematic)

        return self.SelectNonOverlappingTarget(cards, min_, max_, ordered)

    def GetEcclesiaTargetPriority(self, card):
        if card is None:
            return 99
        if card.IsFloodgate() or card.IsMonsterDangerous() or card.IsMonsterInvincible() or \
                card.IsMonsterShouldBeDisabledBeforeItUseEffect():
            return 0
        if (card.IsSpell() or card.IsTrap()) and card.IsFacedown():
            return 1
        if card.IsMonster():
            return 2
        if card.IsSpell() or card.IsTrap():
            return 3
        return 4

    def SelectPreferredIds(self, cards, min_, max_, *ids):
        ordered = []
        for id_ in ids:
            ordered.extend([c for c in cards if c is not None and c.IsCode(id_) and not self.IsPendingDeckSearch(c) and
                            c not in ordered])
        if len(ordered) == 0:
            return None
        return self.Util.CheckSelectCount(ordered, cards, min_, max_)

    def SelectPreferredIdPreferGrave(self, cards, min_, max_, id_):
        ordered = sorted((c for c in cards if c is not None and c.IsCode(id_) and not self.IsPendingDeckSearch(c)),
                         key=lambda c: 0 if self.IsGraveCard(c) else 1)
        if len(ordered) == 0:
            return None
        return self.Util.CheckSelectCount(ordered, cards, min_, max_)

    def SelectFallenExtraDeckCost(self, cards, min_, max_):
        return self.SelectPreferredIds(cards, min_, max_,
                                       CardId.AlbionTheBrandedDragon,
                                       CardId.EcclesiaAndTheDarkDragon,
                                       CardId.TitanikladTheAshDragon,
                                       CardId.AlbaLenatusTheAbyssDragon)

    def SelectBlackChaosSpecialSummonReturn(self, cards, min_, max_):
        graveCards = [c for c in cards if c is not None and self.IsGraveCard(c)]
        handCards = [c for c in cards if c is not None and (c.Location & CardLocation.Hand) != 0]

        ordered = graveCards + handCards
        if len(ordered) < min_:
            return None
        return self.Util.CheckSelectCount(ordered, cards, min_, max_)

    def SelectNonOverlappingTarget(self, cards, min_, max_, preferred):
        legal = list(dict.fromkeys(c for c in preferred if c is not None and c in cards))
        if len(legal) == 0:
            return None
        unused = [c for c in legal if not self.IsOpponentTargetReserved(c)]
        if len(unused) < min_:
            return None
        return self.SelectCount(unused, cards, min_, max_, 1)

    def SelectCount(self, preferred, cards, min_, max_, desired):
        ordered = list(dict.fromkeys(c for c in preferred if c is not None and c in cards))[:max(0, min(max_, desired))]
        if len(ordered) < min_:
            return None
        return self.Util.CheckSelectCount(ordered, cards, min_, max_)

    def IsOpponentTargetSelectionHint(self, hint):
        return hint == HintMsg.Target or hint == HintMsg.Destroy or hint == HintMsg.Remove or \
            hint == HintMsg.ReturnToHand or hint == HintMsg.Disable

    def IsValidTargetSelection(self, selected, cards, min_, max_):
        return selected is not None and min_ <= len(selected) <= max_ and \
            len(set(selected)) == len(selected) and all(c is not None and c in cards for c in selected)

    def ReserveOpponentTargets(self, selected):
        for card in selected:
            if card is not None and card.Controller == 1:
                self._reservedOpponentTargets.add(card)

    def IsOpponentTargetReserved(self, card):
        if card is None:
            return False
        if card in self._reservedOpponentTargets:
            return True
        return self.Duel.CurrentChainInfo is not None and \
            any(chain is not None and chain.ActivatePlayer == 0 and chain.Targets is not None and card in chain.Targets
                for chain in self.Duel.CurrentChainInfo)

    def HasRitualMonsterSearchTarget(self):
        return self.Bot.HasInDeck(CardId.BlackLusterSoldierSoldierOfLightAndDarkness) or \
            self.Bot.HasInDeck(CardId.MagicianOfDarkChaosBlackChaos) or \
            self.Bot.HasInDeck(CardId.SkullArchfiendOfChaos) or \
            self.Bot.HasInDeck(CardId.BlackSkullDragonTheArchfiendDragonOfUnity) or \
            self.Bot.HasInDeck(CardId.BlackChaos) or \
            self.Bot.HasInDeck(CardId.CelticMystic) or \
            self.Bot.HasInDeck(CardId.Griffoh)

    def GetRitualRecycleCandidates(self):
        return self.LimitSkullArchfiendRitualCopies(
            [c for c in self.Bot.Graveyard + self.Bot.Banished + self.Enemy.Graveyard + self.Enemy.Banished
             if self.IsSkullArchfiendRecycleCandidate(c)])

    def LimitSkullArchfiendRitualCopies(self, source):
        candidates = [c for c in source if c is not None]
        ritual = next((c for c in candidates if c.IsCode(CardId.LightAndDarknessRitual)), None)
        if ritual is None:
            return candidates
        return [c for c in candidates if not c.IsCode(CardId.LightAndDarknessRitual) or c == ritual]

    def IsSkullArchfiendRecycleCandidate(self, card):
        if card is None or card.Id == 0 or card.IsCode(CardId.SkullArchfiendOfChaos) or \
                self.IsOwnGraveyardRitualMonster(card):
            return False
        if card.IsCode(CardId.LightAndDarknessRitual) and \
                sum(1 for c in self.Bot.Graveyard if c is not None and c.IsCode(CardId.LightAndDarknessRitual)) < 2:
            return False
        return True

    def IsSkullArchfiendReturnPending(self, card):
        if card is None:
            return False
        if card in self._pendingLightAndDarknessReturnCards:
            return True
        return any(chain is not None and chain.ActivatePlayer == 0 and
                   chain.IsActivateCode(CardId.LightAndDarknessRitual) and chain.HasLocation(CardLocation.Grave)
                   for chain in self.Duel.CurrentChainInfo)

    def CanUseMindShuffleSummon(self):
        returnTarget = self.GetMindShuffleReturnTarget()
        summonTarget = self.GetMindShuffleSummonTarget()
        if returnTarget is None or summonTarget is None:
            return False

        if not self.IsOpponentTargetedByCurrentChain(returnTarget) and \
                not self.HasFreshMindShuffleSummonCandidate(returnTarget):
            return False

        if self.IsMindShuffleTargetedByOpponentChain() and \
                returnTarget.IsCode(CardId.MagicianOfDarkChaosBlackChaos) and \
                not self.HasNonMagicianMindShuffleReturnCandidate():
            return False

        return not summonTarget.IsCode(returnTarget.Id)

    def HasMindShuffleBreakthroughReason(self):
        if self.IsMindShuffleProtectionThreat():
            return True
        if self.Enemy.GetMonsterCount() > 0:
            return True
        if any(c.IsFacedown() or c.HasType(CardType.Continuous) for c in self.Enemy.GetSpells()):
            return True
        return any(c.Level >= 7 and self.Util.IsChainTarget(c) for c in self.Bot.GetMonsters())

    def HasLatestOpponentChain(self):
        latest = self.Duel.GetCurrentChainCard()
        return latest is not None and latest.Controller == 1

    def IsMindShuffleTargetedByOpponentChain(self):
        return any(c is not None and c.IsCode(CardId.MindShuffle) and c.IsFaceup() and
                   self.IsOpponentTargetedByCurrentChain(c) for c in self.Bot.GetSpells())

    def IsMindShuffleProtectionThreat(self):
        return self.IsMindShuffleTargetedByOpponentChain() or self.IsOpponentNonTargetingMassDestructionChain()

    def IsOpponentNonTargetingMassDestructionChain(self):
        chain = self.GetLatestOpponentChainInfo()
        if chain is None or chain.ActivatePlayer != 1 or (chain.Targets is not None and len(chain.Targets) > 0):
            return False
        return chain.IsActivateCode(CardId.BlackRoseDragon, CardId.HarpiesFeatherDuster, CardId.Raigeki,
                                    CardId.LightningStorm)

    def GetMindShuffleSummonTarget(self):
        returnTarget = self.GetMindShuffleReturnTarget()
        for id_ in self.GetMindShuffleSummonOrderForCurrentChain():
            target = next((c for c in self.Bot.Hand if c is not None and c.IsCode(id_) and
                           not self.WasCardActivatedThisTurn(c) and
                           (returnTarget is None or not c.IsCode(returnTarget.Id))), None)
            if target is not None:
                return target

        if returnTarget is not None and self.IsOpponentTargetedByCurrentChain(returnTarget):
            for id_ in self.GetMindShuffleSummonOrderForCurrentChain():
                target = next((c for c in self.Bot.Hand if c is not None and c.IsCode(id_) and c.IsMonster() and
                               (returnTarget is None or not c.IsCode(returnTarget.Id))), None)
                if target is not None:
                    return target
        return None

    def GetMindShuffleSummonOrderForCurrentChain(self):
        self.EnsureMindShufflePriorityOverride()
        order = list(self._mindShuffleSummonOrder)
        if self.IsMindShuffleProtectionThreat():
            if CardId.MagicianOfDarkChaosBlackChaos in order:
                order.remove(CardId.MagicianOfDarkChaosBlackChaos)
            order.insert(0, CardId.MagicianOfDarkChaosBlackChaos)
        return order

    def HasNonMagicianMindShuffleReturnCandidate(self):
        return any(self.IsMindShuffleReturnCandidate(c) and not c.IsCode(CardId.MagicianOfDarkChaosBlackChaos)
                   for c in self.Bot.GetMonsters())

    def GetMindShuffleReturnTarget(self):
        candidates = [c for c in self.Bot.GetMonsters() if self.IsMindShuffleReturnCandidate(c)]

        magicianTargeted = any(c.IsCode(CardId.MagicianOfDarkChaosBlackChaos) and
                               self.IsOpponentTargetedByCurrentChain(c) for c in candidates)

        if self.IsMindShuffleProtectionThreat() and not magicianTargeted:
            candidates = [c for c in candidates if not c.IsCode(CardId.MagicianOfDarkChaosBlackChaos)]
            if len(candidates) == 0:
                return None

        selected = next(iter(sorted(candidates, key=lambda c: (
            -int(self.IsOpponentTargetedByCurrentChain(c)), -int(self.WasCardActivatedThisTurn(c)),
            self.GetMindShuffleReturnPriority(c)))), None)

        if selected is not None and selected.IsCode(CardId.MagicianOfDarkChaosBlackChaos) and \
                not self.IsOpponentTargetedByCurrentChain(selected) and \
                not any(not c.IsCode(CardId.MagicianOfDarkChaosBlackChaos) for c in candidates) and \
                self.HaveUsedMindShuffleHandTargets():
            return None

        return selected

    def HaveUsedMindShuffleHandTargets(self):
        return any(c is not None and c.IsCode(CardId.BlackLusterSoldierSoldierOfLightAndDarkness) for c in self.Bot.Hand) and \
            any(c is not None and c.IsCode(CardId.BlackSkullDragonTheArchfiendDragonOfUnity) for c in self.Bot.Hand) and \
            CardId.BlackLusterSoldierSoldierOfLightAndDarkness in self._activatedFirstEffectCardIdsThisTurn and \
            CardId.BlackSkullDragonTheArchfiendDragonOfUnity in self._activatedFirstEffectCardIdsThisTurn

    def HasFreshMindShuffleSummonCandidate(self, returnTarget):
        return any(c is not None and c.IsMonster() and
                   c.IsCode(CardId.MagicianOfDarkChaosBlackChaos, CardId.BlackSkullDragonTheArchfiendDragonOfUnity,
                            CardId.BlackLusterSoldierSoldierOfLightAndDarkness, CardId.BlackChaos) and
                   not self.WasCardActivatedThisTurn(c) and
                   (returnTarget is None or not c.IsCode(returnTarget.Id)) for c in self.Bot.Hand)

    def IsOpponentTargetedByCurrentChain(self, card):
        if card is None or card.Controller != 0 or self.Duel.CurrentChainInfo is None:
            return False
        if any(chain is not None and chain.ActivatePlayer == 1 and chain.Targets is not None and card in chain.Targets
               for chain in self.Duel.CurrentChainInfo):
            return True
        return any(chain is not None and chain.ActivatePlayer == 1 for chain in self.Duel.CurrentChainInfo) and \
            (card in self.Duel.ChainTargets or card in self.Duel.LastChainTargets)

    def IsMindShuffleReturnCandidate(self, card):
        if card is None or card.Controller != 0 or not card.IsFaceup():
            return False
        return card.IsCode(CardId.FydraulisHarmonia, CardId.BlackSkullDragonTheArchfiendDragonOfUnity,
                           CardId.BlackLusterSoldierSoldierOfLightAndDarkness, CardId.MagicianOfDarkChaosBlackChaos,
                           CardId.BlackChaos)

    def GetMindShuffleReturnPriority(self, card):
        if card is None:
            return 99
        priority = self._mindShuffleReturnOrder.index(card.Id) if card.Id in self._mindShuffleReturnOrder else -1
        return priority if priority >= 0 else 99

    def EnsureMindShufflePriorityOverride(self):
        if self._mindShufflePriorityOverrideApplied or self.Duel.Player != 0 or self.Duel.Turn == 1 or \
                not any(c.IsCode(CardId.LightAndDarknessRitual) for c in self.Bot.Graveyard):
            return
        if CardId.BlackChaos in self._mindShuffleSummonOrder:
            self._mindShuffleSummonOrder.remove(CardId.BlackChaos)
        self._mindShuffleSummonOrder.insert(0, CardId.BlackChaos)
        self._mindShufflePriorityOverrideApplied = True

    def ResetMindShuffleSummonOrder(self):
        self._mindShuffleSummonOrder.clear()
        self._mindShuffleSummonOrder.append(CardId.MagicianOfDarkChaosBlackChaos)
        self._mindShuffleSummonOrder.append(CardId.BlackSkullDragonTheArchfiendDragonOfUnity)
        self._mindShuffleSummonOrder.append(CardId.BlackLusterSoldierSoldierOfLightAndDarkness)
        self._mindShuffleSummonOrder.append(CardId.BlackChaos)

    def MoveMindShuffleSummonToEnd(self, cardId):
        if cardId not in self._mindShuffleSummonOrder:
            return
        self._mindShuffleSummonOrder.remove(cardId)
        self._mindShuffleSummonOrder.append(cardId)

    def ResetMindShuffleReturnOrder(self):
        self._mindShuffleReturnOrder.clear()
        self._mindShuffleReturnOrder.append(CardId.FydraulisHarmonia)
        self._mindShuffleReturnOrder.append(CardId.BlackSkullDragonTheArchfiendDragonOfUnity)
        self._mindShuffleReturnOrder.append(CardId.BlackLusterSoldierSoldierOfLightAndDarkness)
        self._mindShuffleReturnOrder.append(CardId.MagicianOfDarkChaosBlackChaos)
        self._mindShuffleReturnOrder.append(CardId.BlackChaos)

    def MoveMindShuffleReturnToEnd(self, cardId):
        if cardId not in self._mindShuffleReturnOrder:
            return
        self._mindShuffleReturnOrder.remove(cardId)
        self._mindShuffleReturnOrder.append(cardId)

    def HasDuplicateCardInHand(self):
        ids = [c.Id for c in self.Bot.Hand if c is not None and c.Id != 0]
        return any(ids.count(i) > 1 for i in set(ids))

    def CanActivatePurulia(self):
        return self.Bot.HasInHand(CardId.MulcharmyPurulia) and self.Bot.GetFieldCount() == 0 and \
            CardId.MulcharmyPurulia not in self._activatedFirstEffectCardIdsThisTurn

    def CanSearchBlackChaosSupportCard(self):
        return not self.HasMindShuffleOnField() and \
            (self.Bot.HasInDeck(CardId.MindShuffle) or self.Bot.HasInGraveyard(CardId.MindShuffle)) and \
            CardId.MindShuffle not in self._pendingDeckSearchIds

    def IsSearchTargetUnavailable(self, cardId):
        return (cardId == CardId.MindShuffle and self.HasMindShuffleOnField()) or \
            self.HasCardInHandOrField(cardId) or cardId in self._pendingDeckSearchIds

    def HasMindShuffleOnField(self):
        return self.Bot.HasInSpellZone(CardId.MindShuffle) or self._mindShuffleFieldCount > 0

    def IsDeckSearchSelectionHint(self, hint):
        return hint == HintMsg.AddToHand or hint == HintMsg.Set or hint == HintMsg.ToField or hint == HintMsg.SpSummon

    def IsPendingDeckSearch(self, card):
        return card is not None and card.Id != 0 and (card.Location & CardLocation.Deck) != 0 and \
            card.Id in self._pendingDeckSearchIds

    def ReservePendingDeckSearch(self, selected):
        if selected is None:
            return
        for card in selected:
            if card is not None and card.Id != 0 and (card.Location & CardLocation.Deck) != 0:
                self._pendingDeckSearchIds.add(card.Id)

    def ShouldPrioritizeLightAndDarknessRitual(self):
        return self.Duel.Player == 0 and any(self.IsRitualMonster(c) for c in self.Bot.Hand) and \
            not self._performedRitualSummonThisTurn and \
            not self.Bot.HasInHandOrInSpellZone(CardId.LightAndDarknessRitual)

    def HasHigherPriorityLightAndDarknessRitualCandidate(self):
        if len(self.Duel.CurrentChain) != 0 or self.Duel.MainPhase is None:
            return False
        return any(c is not None and c.IsCode(CardId.LightAndDarknessRitual) and
                   (c.Location & (CardLocation.Hand | CardLocation.SpellZone)) != 0
                   for c in self.Duel.MainPhase.ActivableCards)

    def HasFreeSpellTrapZone(self):
        return self.Bot.GetSpellCountWithoutField() < 5

    def CanSetGriffohSupportCard(self):
        if not self.HasFreeSpellTrapZone():
            return False

        if self.HasPendingBlackChaosSupportSearch():
            return self.Bot.HasInDeck(CardId.SpellShatteringSword) and \
                not self.IsSearchTargetUnavailable(CardId.SpellShatteringSword)

        return (self.Bot.HasInDeck(CardId.MindShuffle) and not self.HasMindShuffleOnField() and
                CardId.MindShuffle not in self._pendingDeckSearchIds) or \
            (self.Bot.HasInDeck(CardId.SpellShatteringSword) and
             not self.IsSearchTargetUnavailable(CardId.SpellShatteringSword))

    def CanReceiveDamage(self):
        if self.Bot.UnderAttack or self.Enemy.BattlingMonster is not None:
            return True

        if self.Duel.Player == 1 and self.Duel.Phase >= DuelPhase.BattleStart and \
                self.Duel.Phase <= DuelPhase.Battle and \
                any(c is not None and c.IsAttack() and not c.IsDisabled() for c in self.Enemy.GetMonsters()):
            return True

        latest = self.GetLatestChainInfo()
        if latest is not None and latest.ActivatePlayer == 1 and self.HasDamageText(NamedCard.Get(latest.ActivateId)):
            return True

        latestCard = self.GetCurrentOpponentChainCard()
        return latestCard is not None and self.HasDamageText(latestCard.Data)

    def HasDamageText(self, card):
        description = card.Description if card is not None else None
        if card is None or not description:
            return False
        return "傷害" in description or "伤害" in description or "damage" in description.lower()

    def HasCardInHandOrField(self, cardId):
        return any(c is not None and c.IsCode(cardId) for c in self.Bot.Hand) or \
            any(c is not None and c.IsCode(cardId) for c in self.Bot.GetSpells()) or \
            any(c is not None and c.IsCode(cardId) for c in self.Bot.GetMonsters())

    def CanUseBlackSkullDragonHandSpecialSummon(self):
        return any(c is not None and c.IsCode(CardId.LightAndDarknessRitual) for c in self.Bot.Hand) or \
            any(self.IsDuplicateSpellInHand(c) for c in self.Bot.Hand) or \
            (any(c is not None and c.IsCode(CardId.SpatialTrunade) for c in self.Bot.Hand) and
             not self.CanUseSpatialTrunadeOnEnemyField()) or \
            any(self.IsBlackSkullDiscardSpell(c) and self.WasCardActivatedThisTurn(c) for c in self.Bot.Hand)

    def CanUseSpatialTrunadeOnEnemyField(self):
        enemyCards = [c for c in self.Enemy.GetMonsters() + self.Enemy.GetSpells()
                      if c is not None and not self.IsOpponentTargetReserved(c)]
        if len(enemyCards) == 0:
            return False

        problematic = self.Util.GetProblematicEnemyCard(0, False)
        return len(enemyCards) >= 2 or problematic is not None and problematic in enemyCards or \
            any(c.IsExtraCard() or c.IsFacedown() or c.IsFaceup() and c.IsFloodgate() for c in enemyCards)

    def IsDuplicateSpellInHand(self, card):
        return self.IsBlackSkullDiscardSpell(card) and \
            sum(1 for c in self.Bot.Hand if c is not None and c.IsCode(card.Id)) > 1

    def IsBlackSkullDiscardSpell(self, card):
        return card is not None and card.Id != 0 and card.IsSpell() and \
            (card.HasType(CardType.QuickPlay) or card.IsCode(CardId.LightAndDarknessRitual))

    def ShouldUseMindShuffleFallback(self):
        return not self.Bot.HasInDeck(CardId.LightAndDarknessRitual) or not self.Bot.HasInDeck(CardId.SkullArchfiendOfChaos)

    def TrackReleaseSelection(self, selected):
        if selected is None:
            return
        for card in selected:
            if card is not None and card.Controller == 0 and card.IsMonster() and not self.IsGraveMonster(card):
                self._pendingReleaseCards.add(card)

    def HasFallenExtraDeckCost(self):
        return self.Bot.HasInExtra(CardId.AlbionTheBrandedDragon) or \
            self.Bot.HasInExtra(CardId.EcclesiaAndTheDarkDragon) or \
            self.Bot.HasInExtra(CardId.TitanikladTheAshDragon) or \
            self.Bot.HasInExtra(CardId.AlbaLenatusTheAbyssDragon)

    def GetOrderedFallenTargets(self, source):
        return sorted(dict.fromkeys(c for c in source if self.IsWorthwhileFallenTarget(c)),
                      key=lambda c: (-self.GetFallenTargetPriority(c), -max(c.Attack, c.Defense)))

    def GetFallenTargetPriority(self, card):
        if card is None or card.Controller != 1 or not card.IsFaceup():
            return -1

        if not card.IsMonster():
            if card.IsFloodgate():
                return 1000
            if card.HasType(CardType.Field):
                return 850
            if card.HasType(CardType.Continuous):
                return 800
            return 0

        priority = self.GetDestructionMonsterPriority(card)
        if self.CanLikelyEscapeFallenTarget(card):
            priority -= 450
        return priority

    def GetOrderedFydraulisTargets(self, source):
        return sorted(dict.fromkeys(c for c in source if self.IsWorthwhileDestructionMonster(c)),
                      key=lambda c: (-self.GetFydraulisTargetPriority(c), -max(c.Attack, c.Defense)))

    def GetFydraulisTargetPriority(self, card):
        if card is None or card.Controller != 1 or not card.IsMonster():
            return -1
        return self.GetDestructionMonsterPriority(card)

    def GetDestructionMonsterPriority(self, card):
        if card is None or not card.IsMonster():
            return -1

        if card.IsFloodgate():
            priority = 1000
        elif card.IsMonsterDangerous():
            priority = 950
        elif card.IsMonsterShouldBeDisabledBeforeItUseEffect():
            priority = 900
        elif self.IsValuableFallenExtraDeckMonster(card):
            priority = 750
        elif self.MeetsFallenMonsterStatThreshold(card):
            priority = 500
        else:
            priority = 0

        if card.IsDisabled():
            priority -= 350
        return priority

    def IsWorthwhileFallenTarget(self, card):
        if card is None or card.Controller != 1 or not card.IsFaceup():
            return False
        if card.IsMonster():
            return self.IsWorthwhileDestructionMonster(card)
        return card.HasType(CardType.Field | CardType.Continuous)

    def IsWorthwhileDestructionMonster(self, card):
        return card is not None and card.Controller == 1 and card.IsMonster() and card.IsFaceup() and \
            (self.IsValuableFallenExtraDeckMonster(card) or card.IsFloodgate() or card.IsMonsterDangerous() or
             card.IsMonsterShouldBeDisabledBeforeItUseEffect() or self.MeetsFallenMonsterStatThreshold(card))

    def MeetsFallenMonsterStatThreshold(self, card):
        return card is not None and card.Attack + card.Defense >= 2700 and (card.Attack >= 1800 or card.Defense >= 2100)

    def CanLikelyEscapeFallenTarget(self, card):
        return card is not None and card.IsCode(CardId.FiendsmithsRequiem) and not card.IsDisabled()

    def IsValuableFallenExtraDeckMonster(self, card):
        return card is not None and card.IsMonster() and card.IsExtraCard() and \
            (not card.HasType(CardType.Link) or card.LinkCount >= 2)

    def IsRitualMonster(self, card):
        return card is not None and card.IsCode(CardId.MagicianOfDarkChaosBlackChaos,
                                                CardId.BlackLusterSoldierSoldierOfLightAndDarkness)

    def IsRitualRelatedCard(self, card):
        return card is not None and card.IsCode(
            CardId.SkullArchfiendOfChaos,
            CardId.MindShuffle,
            CardId.LightAndDarknessRitual,
            CardId.MagicianOfDarkChaosBlackChaos,
            CardId.CelticMystic,
            CardId.BlackLusterSoldierSoldierOfLightAndDarkness,
            CardId.SpellShatteringSword,
            CardId.Griffoh,
            CardId.BlackSkullDragonTheArchfiendDragonOfUnity,
            CardId.BlackChaos)

    def GetRitualMonsterPriority(self, card):
        if card.IsCode(CardId.MagicianOfDarkChaosBlackChaos):
            return 0
        if card.IsCode(CardId.BlackLusterSoldierSoldierOfLightAndDarkness):
            return 1
        return 2

    def GetRitualMaterialPriority(self, card):
        if self.IsGraveCard(card):
            if self.HasKnownCardType(card, CardType.Fusion):
                return 30
            if card.IsCode(CardId.Griffoh):
                return 0
            if card.IsCode(CardId.BlackChaos):
                return 1
            return 2

        if card.IsCode(CardId.Griffoh):
            return 10
        if card.IsCode(CardId.BlackChaos):
            return 11
        if card.IsCode(CardId.CelticMystic):
            return 20
        if card.IsCode(CardId.FallenOfTheWhiteDragon):
            return 21
        if card.IsCode(CardId.AshBlossomJoyousSpring, CardId.MaxxC, CardId.DrollLockBird, CardId.MulcharmyPurulia):
            return 23
        if card.IsCode(CardId.BlackLusterSoldierSoldierOfLightAndDarkness):
            return 30
        return 25

    def GetRitualTributePriority(self, card):
        if self.IsGraveCard(card):
            if self.HasKnownCardType(card, CardType.Fusion):
                return 30
            if card.IsCode(CardId.Griffoh):
                return 0
            if card.IsCode(CardId.BlackChaos):
                return 1
            return 2

        if card.IsCode(CardId.Griffoh):
            return 10
        if card.IsCode(CardId.BlackChaos):
            return 11
        if card.IsCode(CardId.CelticMystic):
            return 20
        if card.IsCode(CardId.FallenOfTheWhiteDragon):
            return 21
        if card.IsCode(CardId.AshBlossomJoyousSpring, CardId.MaxxC, CardId.DrollLockBird, CardId.MulcharmyPurulia):
            return 23
        return 25

    def IsGraveMonster(self, card):
        return card is not None and self.HasKnownCardType(card, CardType.Monster) and \
            (card.Location & CardLocation.Grave) != 0

    def HasKnownCardType(self, card, type_):
        return card is not None and (card.HasType(type_) or card.Data is not None and card.Data.HasType(type_))

    def IsGraveCard(self, card):
        return card is not None and (card.Location & CardLocation.Grave) != 0

    def IsAllowedRitualMaterial(self, card):
        return card is not None and not card.IsCode(CardId.SkullArchfiendOfChaos)

    def IsPreferredGraveRitualMaterial(self, card):
        return self.IsAllowedRitualMaterial(card) and self.IsGraveCard(card) and \
            not self.HasKnownCardType(card, CardType.Fusion)

    def CanUseOnlyGraveyardMaterials(self, mandatoryCards):
        return mandatoryCards is None or all(self.IsGraveCard(c) for c in mandatoryCards)

    def SelectGraveyardRitualSumSelection(self, cards, mandatoryCards, sum_, min_, max_, exactEqual):
        if not self.CanUseOnlyGraveyardMaterials(mandatoryCards):
            return None
        graveCards = sorted((c for c in cards if self.IsPreferredGraveRitualMaterial(c)), key=self.GetRitualMaterialPriority)
        if len(graveCards) == 0:
            return None
        return self.AI.FindSumSelection(graveCards, mandatoryCards, sum_, min_, max_, exactEqual)

    def SelectGraveyardRitualTribute(self, cards, min_, max_):
        graveCards = sorted((c for c in cards if self.IsPreferredGraveRitualMaterial(c)), key=self.GetRitualTributePriority)
        if len(graveCards) == 0:
            return None
        return self.AI.FindTributeSelection(graveCards, min_, max_)

    def SelectGriffohAsFullRitualMaterial(self, cards, *args):
        if len(args) == 2:  # (cards, min, max)
            griffoh = next((c for c in cards if c is not None and c.IsCode(CardId.Griffoh) and self.IsGraveCard(c)), None)
            if griffoh is None:
                return None
            griffoh.OpParam1 = 1
            griffoh.OpParam2 = 8
            return [griffoh]

        mandatoryCards, sum_, min_, max_ = args  # (cards, mandatoryCards, sum, min, max)
        if min_ > 1 or max_ < 1:
            return None
        if sum_ != 0 and sum_ != 1 and sum_ != 8:
            return None

        mandatoryGriffoh = None if mandatoryCards is None else \
            next((c for c in mandatoryCards if c is not None and c.IsCode(CardId.Griffoh) and self.IsGraveCard(c)), None)
        if mandatoryGriffoh is not None:
            mandatoryGriffoh.OpParam1 = 1
            mandatoryGriffoh.OpParam2 = 8
            return []

        if mandatoryCards is not None and len(mandatoryCards) > 0:
            return None

        griffoh = next((c for c in cards if c is not None and c.IsCode(CardId.Griffoh) and self.IsGraveCard(c)), None)
        if griffoh is None:
            return None
        griffoh.OpParam1 = 1
        griffoh.OpParam2 = 8
        return [griffoh]

    def IsExtraDeckMonster(self, cardId):
        card = NamedCard.Get(cardId)
        return card is not None and card.IsExtraCard()

    def GetDiscardPriority(self, card):
        if card.IsCode(CardId.SpatialTrunade):
            return 0
        if card.IsCode(CardId.TheFallenTheVirtuous, CardId.SpellShatteringSword, CardId.CrimsonCall):
            return 1
        if card.IsCode(CardId.RaggedRecordsOfRites, CardId.MindShuffle):
            return 2
        if card.IsCode(CardId.LightAndDarknessRitual) and \
                sum(1 for c in self.Bot.Hand if c.IsCode(CardId.LightAndDarknessRitual)) > 1:
            return 3
        if card.IsCode(CardId.FallenOfTheWhiteDragon, CardId.CelticMystic, CardId.Griffoh):
            return 5
        if card.IsCode(CardId.BlackChaos, CardId.BlackLusterSoldierSoldierOfLightAndDarkness):
            return 20
        return 10

    def WasCardActivatedThisTurn(self, card):
        return card is not None and card.Id != 0 and card.Id in self._activatedFirstEffectCardIdsThisTurn

    _MULTI_EFFECT = (
        CardId.TheWorldsGreatestGallantThief,
        CardId.BlackSkullDragonTheArchfiendDragonOfUnity,
        CardId.BlackChaos,
        CardId.CelticMystic,
        CardId.RaggedRecordsOfRites,
        CardId.MindShuffle,
        CardId.CrimsonCall,
        CardId.LightAndDarknessRitual,
        CardId.FallenOfTheWhiteDragon,
        CardId.IncredibleEcclesiaTheVirtuous,
        CardId.SkullArchfiendOfChaos,
        CardId.MagicianOfDarkChaosBlackChaos,
        CardId.TheFallenTheVirtuous,
        CardId.SpellShatteringSword,
        CardId.BlackLusterSoldierSoldierOfLightAndDarkness,
        CardId.FydraulisHarmonia,
    )

    def IsMultiEffectCard(self, card):
        return card is not None and card.IsCode(*self._MULTI_EFFECT)

    def IsFirstEffect(self, chain):
        if chain is None:
            return False
        if not chain.IsActivateCode(*self._MULTI_EFFECT):
            return True
        offset = 1 if chain.IsActivateCode(CardId.TheWorldsGreatestGallantThief) else 0
        return chain.ActivateDescription == self.Util.GetStringId(chain.ActivateId, offset)

    def IsDuplicateInSelection(self, card, cards):
        return card is not None and card.Id != 0 and sum(1 for c in cards if c is not None and c.Id == card.Id) > 1

    def GetGallantThiefTributePriority(self, card):
        if card.Controller == 1:
            problematic = self.Util.GetProblematicEnemyMonster(0, True)
            if card == problematic:
                return 100
            return 80 if card.IsFacedown() else card.Attack

        if card.IsCode(CardId.CelticMystic, CardId.FallenOfTheWhiteDragon, CardId.Griffoh):
            return 1
        return 0

    def IsDescription(self, cardId, offset):
        return self.ActivateDescription == self.Util.GetStringId(cardId, offset)

    def GetOptionIndex(self, options, cardId, offset):
        id_ = self.Util.GetStringId(cardId, offset)
        return options.index(id_) if id_ in options else -1

    def IsOpponentMonsterEffectChain(self, chain):
        return chain is not None and chain.ActivatePlayer == 1 and (chain.ActivateType & CardType.Monster) != 0 and \
            chain.HasLocation(CardLocation.MonsterZone)

    def GetChainSourceCard(self, chain):
        if not self.IsOpponentMonsterEffectChain(chain):
            return None

        source = next((c for c in self.Enemy.GetMonsters() if c is not None and c.Location == chain.ActivateLocation and
                       c.Sequence == chain.ActivateSequence and c.IsFaceup()), None)
        if source is not None:
            return source

        return next((c for c in self.Enemy.GetMonsters() if c is not None and c == chain.RelatedCard and c.IsFaceup()), None)

    def GetLatestOpponentChainInfo(self):
        if self.Duel.CurrentChainInfo is None:
            return None
        for chain in reversed(self.Duel.CurrentChainInfo):
            if chain is not None and chain.ActivatePlayer == 1:
                return chain
        return None

    def FindMatchingCard(self, cards, source):
        if source is None:
            return None
        exact = next((c for c in cards if c == source), None)
        if exact is not None:
            return exact
        return next((c for c in cards if c is not None and c.Controller == source.Controller and
                     c.Location == source.Location and c.Sequence == source.Sequence), None)

    def SelectSpellShatteringSwordMonsterTarget(self, cards, min_, max_):
        target = self.FindMatchingCard(cards, self._pendingSpellShatteringSwordMonsterTarget)
        if target is None or target.Controller != 1 or not target.IsOnField() or not target.IsMonster() or \
                not target.IsFaceup():
            return None
        self._pendingSpellShatteringSwordMonsterTarget = None
        return self.SelectCount([target], cards, min_, max_, 1)

    def GetLatestChainInfo(self):
        if self.Duel.CurrentChainInfo is None or len(self.Duel.CurrentChainInfo) == 0:
            return None
        return self.Duel.CurrentChainInfo[-1]

    def HasFreshOpponentTarget(self, candidates):
        return candidates is not None and \
            any(c is not None and c.Controller == 1 and not self.IsOpponentTargetReserved(c) for c in candidates)

    def GetCurrentActivationChainInfo(self):
        current = self.Duel.GetCurrentChainCard()
        if current is None:
            return None
        for chain in reversed(self.Duel.CurrentChainInfo):
            if chain is None or chain.ActivatePlayer != 0:
                continue
            if chain.RelatedCard == current or (chain.ActivateId == current.Id and
                                                chain.ActivateController == current.Controller and
                                                chain.ActivateSequence == current.Sequence):
                return chain
        return None

    def GetCurrentOpponentChainCard(self):
        current = self.Duel.GetCurrentChainCard()
        if current is not None and current.Controller == 1:
            return current
        last = self.Util.GetLastChainCard()
        return last if last is not None and last.Controller == 1 else None
