"""Maliss executor, ported from IceYGO/windbot Game/AI/Decks/MalissExecutor.cs (MIT, see THIRD_PARTY_NOTICES.md).

Approximations: the env limits in docs/windbot_porting.md (IsDisabled always False, link markers 0 so every
GetLinkedZones / linked-zone mask is 0, EquipCards empty, Attacked False). GetBotAvailZonesFromExtraDeck assumes
Master Rule 2020 (Duel.IsNewRule2020, which the shim's Duel lacks), so it returns the main Monster Zones. Cards
kept across decisions (escapeTargetList, currentNegateCardList, currentDestroyCardList, enemyPlaceThisTurn...) are
snapshots compared by (Id, Controller, Location, Sequence). The executor's own dimensionShifterCount hides
DefaultExecutor's private field in C#; here it is name-mangled (self.__dimensionShifterCount) so the two stay apart.
ActLittleKnight's opponent-turn branch dereferences a possibly null monster in C# (NullReferenceException); here a
missing attack-position monster leaves selfMonster None. C# comparers (CompareUsableAttack) go through cmp_to_key;
List.Sort (unstable in C#) is Python's stable sort.

Module-level helpers (WindBot members the shim lacks): CardLinkMarker, ShuffleListInPlace (AIUtil),
GetBotAvailZonesFromExtraDeck (AIUtil), ChainInfo_HasType / ChainInfo_IsSpell (ChainInfo.HasType / IsSpell)."""
from functools import cmp_to_key

from windbot import *
from windbot_default import DefaultExecutor, _CardId, _Setcode
from windbot_gameai import BattlePhaseAction


class CardId:
    DominusImpulse = 40366667
    TERRAFORMING = 73628505
    GoldSarcophagus = 75500286

    BackupIgnister = 30118811
    WizardIgnister = 3723262

    MalissP_Dormouse = 32061192
    MalissP_WhiteRabbit = 69272449
    MalissP_ChessyCat = 96676583
    MalissP_MarchHare = 20938824
    MalissC_GWC06 = 20726052
    MalissC_MTP07 = 94722358
    MalissQ_RedRansom = 68059897
    MalissQ_WhiteBinder = 95454996
    MalissQ_HeartsCrypter = 21848500
    MalissInTheMirror = 93453053
    MalissInUnderground = 68337209

    Linguriboh = 24842059
    LinkDecoder = 30342076
    SP_LITTLE_KNIGHT = 29301450
    SALAMANGREAT_ALMIRAJ = 60303245
    SplashMage = 59859086
    CyberseWicckid = 52698008
    TranscodeTalker = 46947713
    AlliedCodeTalkerIgnister = 39138610
    FirewallDragon = 5043010
    LinkSpider = 98978921
    HaggardLizardose = 9763474
    AccesscodeTalker = 86066372
    Apollousa = 4280258

    Lancea = 34267821
    Fuwalos = 42141493
    NaturalExterio = 99916754
    NaturalBeast = 33198837
    ImperialOrder = 61740673
    SwordsmanLV7 = 37267041
    RoyalDecree = 51452091
    Number41BagooskatheTerriblyTiredTapir = 90590303
    InspectorBoarder = 15397015
    SkillDrain = 82732705
    DivineArsenalAAZEUS_SkyThunder = 90448279
    DimensionShifter = 91800273
    MacroCosmos = 30241314
    DimensionalFissure = 81674782
    BanisheroftheRadiance = 94853057
    BanisheroftheLight = 61528025
    KashtiraAriseHeart = 48626373
    GhostMournerMoonlitChill = 52038441
    NibiruThePrimalBeing = 27204311
    AmeNoMurakumoNoMitsurugi = 19899073


def _max_by(cards, key):
    """LINQ OrderByDescending(key).FirstOrDefault(): the first card with the largest key."""
    return max(cards, key=key, default=None)


def _min_by(cards, key):
    """LINQ OrderBy(key).FirstOrDefault()."""
    return min(cards, key=key, default=None)


class MalissExecutor(DefaultExecutor):
    DECK_EXECUTOR = True

    SetcodeMaliss = 0x1b9
    SetcodeTimeLord = 0x4a
    SetcodePhantom = 0xdb
    SetcodeOrcust = 0x11b
    SetcodeHorus = 0x19d
    SetcodeDarkWorld = 0x6
    SetcodeSkyStriker = 0x115

    MZ0 = 1 << 0
    MZ1 = 1 << 1
    MZ2 = 1 << 2
    MZ3 = 1 << 3
    MZ4 = 1 << 4
    EMZ_L = 1 << 5
    EMZ_R = 1 << 6
    EMZ_ALL = EMZ_L | EMZ_R

    EMZ_LEFT = 5
    EMZ_RIGHT = 6
    PreferCenterMainSeq = [2, 1, 3, 0, 4]

    def __init__(self):
        super().__init__()
        self.notToNegateIdList = [58699500, 20343502, 19403423]
        self.notToDestroySpellTrap = [50005218, 6767771]
        self.targetNegateIdList = [
            _CardId.EffectVeiler, _CardId.InfiniteImpermanence, CardId.GhostMournerMoonlitChill, _CardId.BreakthroughSkill,
            74003290, 67037924, 9753964, 66192538, 23204029, 73445448, 35103106, 30286474, 45002991, 5795980, 38511382,
            53742162, 30430448,
        ]

        # Maliss Flags
        self.usedNormalSummon = False
        self.ssDormouse = False
        self.ssWhiteRabbit = False
        self.ssChessyCat = False
        self.ssMarchHare = False
        self.ActiveMarchHare = False
        self.ssRRThisTurn = False
        self.ssWBThisTurn = False
        self.ssHCThisTurn = False
        self.enemyActivateLancea = False
        self.enemyActivateFuwalos = False
        self.ActiveUnderground = False
        self.blockWicckid = False
        self.mtp07SetThisTurn = False
        self.gwc06SetThisTurn = False
        self.splashNegatedThisTurn = False
        self.Allied_End = False
        self.goldstart = False
        self.undergroundstart = False
        self.nsplan = False
        self.nsBackupplan = False
        self.NSDorMouse = False

        self.myTurnCount = 0
        self.avoidLinkedZones = False

        # Step Flag
        self.step1Done = False
        self.step2Done = False
        self.lastRevivedIdBySplash = 0
        self.madeIt3 = False
        self.resultSuccessFlag = False
        self._didSplashToRR = False
        self._didRRtoWicckid = False
        self._didSummonToWicckidArrow = False
        self._preferWicckidArrows = False
        self._rrSelfSSPlacing = False

        self._oppJustActivatedPersistentSpell = False
        self._oppJustSummoned = False
        self._oppJustSet = False
        self._prefWindowTTL = 0

        self._enemyMonsterCountSnap = 0
        self._enemyFacedownSTSnap = 0

        # Default code
        self.enemyActivateMaxxC = False
        self.__dimensionShifterCount = 0
        self.infiniteImpermanenceList = []
        self.currentNegateCardList = []
        self.currentDestroyCardList = []
        self.sendToGYThisTurn = []
        self.activatedCardIdList = []
        self.enemyPlaceThisTurn = []
        self.escapeTargetList = []
        self.summonThisTurn = []

        A, S, SS = ExecutorType.Activate, ExecutorType.Summon, ExecutorType.SpSummon
        # Must Set First
        self.AddExecutor(ExecutorType.SpellSet, CardId.MalissC_GWC06, self.SpellSetCheck)
        self.AddExecutor(ExecutorType.SpellSet, CardId.MalissC_MTP07, self.SpellSetCheck)

        self.AddExecutor(A, CardId.AccesscodeTalker, self.Accesscode_OnSummon_AtkUp)
        self.AddExecutor(A, CardId.AccesscodeTalker, self.Accesscode_Destroy_Ignition)

        # Generic counters
        self.AddExecutor(A, _CardId.MaxxC, self.MaxxCActivate)
        self.AddExecutor(A, _CardId.AshBlossom, self.AshBlossomActivate)
        self.AddExecutor(A, _CardId.CalledByTheGrave, self.CalledbytheGraveActivate)
        self.AddExecutor(A, _CardId.CrossoutDesignator, self.CrossoutDesignatorActivate)
        self.AddExecutor(A, _CardId.InfiniteImpermanence, self.InfiniteImpermanenceActivate)
        self.AddExecutor(A, CardId.Apollousa, self.DontSelfNG)
        self.AddExecutor(A, CardId.DominusImpulse, self.DontSelfNG)
        self.AddExecutor(A, CardId.AlliedCodeTalkerIgnister, self.Allied_NegateBanish)
        self.AddExecutor(A, CardId.FirewallDragon, self.FirewallBounce_OnOppSummon)
        self.AddExecutor(A, CardId.MalissC_MTP07, self.MTP07_OppTurn_RemoveEnemyOnly)
        self.AddExecutor(A, CardId.MalissQ_HeartsCrypter, self.HC_Quick_ReturnBanished_AndBanishField)
        self.AddExecutor(A, CardId.MalissC_GWC06, self.GWC06_OppTurn_ReviveWB_HC)
        self.AddExecutor(A, CardId.SP_LITTLE_KNIGHT, self.ActLittleKnight)

        self.AddExecutor(A, CardId.MalissQ_RedRansom, self.RR_SS_FromBanished)
        self.AddExecutor(A, CardId.MalissQ_HeartsCrypter, self.HC_OnBanished_SpecialSummon)
        self.AddExecutor(A, CardId.MalissInTheMirror, self.Mirror_Banish)

        # Plan#1: start with Dormouse
        self.AddExecutor(S, CardId.MalissP_Dormouse, self.Step1_Dormouse_NormalSummon)
        self.AddExecutor(S, CardId.MalissP_WhiteRabbit, self.Step1_WhiteRabbit_NormalSummon)
        self.AddExecutor(S, CardId.MalissP_ChessyCat, self.TwoCC_NormalSummon)
        self.AddExecutor(S, CardId.MalissP_ChessyCat, self.Emergency_NormalCat)
        self.AddExecutor(S, CardId.MalissP_MarchHare, self.NSMH)
        self.AddExecutor(S, CardId.BackupIgnister, self.NSBackup)
        self.AddExecutor(A, CardId.MalissP_Dormouse, self.Dormouse_SS_FromBanished)
        self.AddExecutor(A, CardId.MalissP_Dormouse, self.Dormouse_ForMH)
        self.AddExecutor(A, CardId.MalissP_Dormouse, self.Dormouse_Banish_Anytime)
        self.AddExecutor(A, CardId.MalissP_WhiteRabbit, self.Step1_WhiteRabbit_SS_FromBanished)
        self.AddExecutor(A, CardId.MalissP_WhiteRabbit, self.Step1_WhiteRabbit_SetTrapOnSummon)
        self.AddExecutor(A, CardId.MalissP_MarchHare, self.Step1_MH_FromHand)
        self.AddExecutor(A, CardId.MalissP_MarchHare, self.returnFromBanish)
        self.AddExecutor(SS, CardId.Linguriboh, self.LinguribohMHLine)
        self.AddExecutor(SS, CardId.LinkDecoder, self.Step1_SSLinkDecoder)
        self.AddExecutor(SS, CardId.MalissQ_RedRansom, self.Step2N_LinkSummon_RedRansom)
        self.AddExecutor(SS, CardId.MalissQ_RedRansom, self.Step2_LinkSummon_RedRansom)
        self.AddExecutor(A, CardId.MalissQ_RedRansom, self.Step2_RedRansom_Search)
        self.AddExecutor(A, CardId.MalissP_ChessyCat, self.AnyDraw)
        self.AddExecutor(SS, CardId.Apollousa, self.Link_Apo)
        self.AddExecutor(SS, CardId.CyberseWicckid, self.Step2N_RRtoWicckid)
        self.AddExecutor(SS, CardId.LinkDecoder, self.Step_SummonLinkDecoderToWicckid)
        self.AddExecutor(A, CardId.CyberseWicckid, self.Wicckid_SearchTuner)
        self.AddExecutor(SS, CardId.SplashMage, self.Step_SplashToWB)
        self.AddExecutor(A, CardId.SplashMage, self.Step2N_SplashMage_ReviveP)
        self.AddExecutor(A, CardId.BackupIgnister, self.Flow3_BackupIgnister_AfterMakeIt3)
        self.AddExecutor(A, CardId.BackupIgnister, self.OneBody_Backup_SearchWizard)
        self.AddExecutor(SS, CardId.MalissQ_WhiteBinder, self.Step2N_LinkSummon_WB)
        self.AddExecutor(A, CardId.MalissQ_WhiteBinder, self.WB_OnSummon_BanishGY)
        self.AddExecutor(A, CardId.MalissC_GWC06, self.GWC06_MyTurn_Extend)
        self.AddExecutor(A, CardId.MalissQ_WhiteBinder, self.WB_SetMalissTrap)

        # STEP2: 2 bodies -> Splash Mage -> revive P -> Red Ransom -> search
        self.AddExecutor(A, CardId.WizardIgnister, self.Step2_Fallback_Wizard_AfterSplashNegated)
        self.AddExecutor(A, CardId.BackupIgnister, self.Step2_Fallback_Backup_AfterSplashNegated)

        self.AddExecutor(A, CardId.WizardIgnister, self.Flow3_WizardIgnister_AfterMakeIt3)
        self.AddExecutor(A, CardId.MalissQ_WhiteBinder, self.WB_OnBanished_SelfSS)
        self.AddExecutor(A, CardId.MalissP_MarchHare, self.ssFromHandMH)
        self.AddExecutor(SS, CardId.MalissQ_HeartsCrypter, self.Step_LinkSummon_HeartsCrypter)
        self.AddExecutor(SS, CardId.AlliedCodeTalkerIgnister, self.Flow3_Link_Allied)
        self.AddExecutor(A, CardId.AlliedCodeTalkerIgnister, self.Allied_OnSummonTrigger)

        # Plan#2 White Rabbit
        self.AddExecutor(A, CardId.MalissC_MTP07, self.MTP07_ForMH)
        self.AddExecutor(SS, CardId.FirewallDragon, self.Flow3_Link_Firewall)
        self.AddExecutor(SS, CardId.MalissQ_WhiteBinder, self.Step_WicckidPlusOneToWB)
        self.AddExecutor(A, CardId.MalissP_ChessyCat, self.ChessyCat_SS_FromBanished)

        self.AddExecutor(SS, CardId.CyberseWicckid, self.Step_RRtoWicckid)
        self.AddExecutor(A, CardId.MalissInUnderground, self.Flow3_UnderGround_Available_SSAnyPawn)
        self.AddExecutor(A, CardId.LinkDecoder, self.LinkDecoder_ReviveFromGY)

        # Fallback Lancea
        self.AddExecutor(SS, CardId.TranscodeTalker, self.SummonTranscode)
        self.AddExecutor(A, CardId.TranscodeTalker, self.Transcode_ReviveLink3OrLower)

        # Emergency Start
        self.AddExecutor(A, CardId.TERRAFORMING, self.Terra_GrabUnderground)
        self.AddExecutor(A, CardId.GoldSarcophagus, self.GoldSarc_StartPiece)
        self.AddExecutor(A, CardId.MalissInUnderground, self.Underground_ActivateStarter)

        self.AddExecutor(SS, CardId.SplashMage, self.Step_SplashToRR)
        self.AddExecutor(A, CardId.SplashMage, self.Step2_SplashMage_ReviveP)

        # Fallback: Try to Start
        self.AddExecutor(SS, CardId.LinkSpider)
        self.AddExecutor(S, _CardId.AshBlossom, self.Emergency_NS)
        self.AddExecutor(S, _CardId.MaxxC, self.Emergency_NS)
        self.AddExecutor(SS, CardId.Linguriboh, self.OneBody_Link1_Linguriboh)
        self.AddExecutor(SS, CardId.SALAMANGREAT_ALMIRAJ, self.OneBody_Link1_Almiraj)
        self.AddExecutor(A, CardId.BackupIgnister, self.OneBody_Backup_SS)
        self.AddExecutor(A, CardId.BackupIgnister, self.OneBody_Backup_SearchWizard)
        self.AddExecutor(A, CardId.WizardIgnister, self.OneBody_Wizard_SS)

        # Finisher
        self.AddExecutor(SS, CardId.AccesscodeTalker, self.Flow3_Link_Accesscode)

        # Turn3 or More
        self.AddExecutor(SS, CardId.Linguriboh, self.T3Allow)
        self.AddExecutor(SS, CardId.SALAMANGREAT_ALMIRAJ, self.T3Allow)
        self.AddExecutor(SS, CardId.TranscodeTalker, self.EmerTranscode)
        self.AddExecutor(SS, CardId.AlliedCodeTalkerIgnister, self.Emer_Allied)
        self.AddExecutor(SS, CardId.AlliedCodeTalkerIgnister, self.Emer_Allied2)

        # Fallback: S:P Little Knight
        self.AddExecutor(SS, CardId.SP_LITTLE_KNIGHT, self.SummonLittleKnightFast)
        self.AddExecutor(SS, CardId.SP_LITTLE_KNIGHT, self.SPEmer)

        self.AddExecutor(ExecutorType.SpellSet, self.SpellSetCheck)
        self.AddExecutor(ExecutorType.Repos, self.MonsterRepos)

    @staticmethod
    def LowestBit(m):
        return m & -m

    # ==================== Default code ====================
    def OnSelectHand(self):
        return True

    def MonsterRepos(self):
        selfAttack = self.Card.Attack + 1
        if selfAttack <= 1:
            return not self.Card.IsDefense()
        bestAttack = 0
        for card in self.Bot.GetMonsters():
            attack = card.Attack
            if attack >= bestAttack:
                bestAttack = attack
        enemyBetter = self.Util.IsAllEnemyBetterThanValue(bestAttack, True)
        if self.Card.IsAttack() and enemyBetter:
            return True
        if self.Card.IsDefense() and not enemyBetter:
            return True
        return False

    def CheckAtAdvantage(self):
        if self.GetProblematicEnemyMonster() is None and any(card.IsFaceup() for card in self.Bot.GetMonsters()):
            return True
        return False

    def CheckInDanger(self):
        if DuelPhase.Main1 < self.Duel.Phase < DuelPhase.Main2:
            totalAtk = 0
            for m in self.Enemy.GetMonsters():
                if m.IsAttack() and not m.Attacked:
                    totalAtk += m.Attack
            if totalAtk >= self.Bot.LifePoints:
                return True
        return False

    def GetMyLinkedMMZMask(self):
        mask = 0
        for m in self.Bot.GetMonsters():
            if m is None or not m.IsFaceup() or not m.HasType(CardType.Link):
                continue
            mask |= m.GetLinkedZones()
        mask &= 0x1F
        return mask

    def IsPawnId(self, id_):
        return id_ in (CardId.MalissP_Dormouse, CardId.MalissP_WhiteRabbit, CardId.MalissP_ChessyCat,
                       CardId.MalissP_MarchHare)

    def GetQueenLinkedMMZMask(self):
        mask = 0
        for m in self.Bot.GetMonsters():
            if m is None or not m.IsFaceup():
                continue
            if m.IsCode(CardId.MalissQ_RedRansom) or m.IsCode(CardId.MalissQ_WhiteBinder) or \
                    m.IsCode(CardId.MalissQ_HeartsCrypter):
                mask |= m.GetLinkedZones()
        mask &= 0x1F
        return mask

    def LinkValOf(self, c):
        return max(1, c.LinkCount) if c.HasType(CardType.Link) else 1

    def IsOneVal(self, c):
        return not c.HasType(CardType.Link) or max(1, c.LinkCount) == 1

    def IsMaliss(self, c):
        return c.HasSetcode(0x1b9)

    def ScoreForBanishedMaliss(self, c):
        if c.IsCode(CardId.MalissInTheMirror):
            return 100
        if c.IsCode(CardId.MalissC_MTP07):
            return 95
        if c.IsCode(CardId.MalissC_GWC06):
            return 90
        if c.IsCode(CardId.MalissInUnderground):
            return 85
        if c.IsCode(CardId.MalissP_MarchHare):
            return 80
        if c.IsCode(CardId.MalissP_ChessyCat):
            return 75
        if c.IsCode(CardId.MalissP_WhiteRabbit):
            return 70
        if c.IsCode(CardId.MalissP_Dormouse):
            return 65
        return 50

    def OnSelectPlace(self, cardId, player, location, available):
        if player == 0 and location == CardLocation.MonsterZone:
            MAIN_MASK = Zones.z0 | Zones.z1 | Zones.z2 | Zones.z3 | Zones.z4
            emzMask = available & ~MAIN_MASK
            mainMask = available & MAIN_MASK
            solvingChain = self.Duel.GetCurrentSolvingChainInfo()
            if solvingChain is not None and solvingChain.ActivatePlayer == 0 and \
                    solvingChain.IsActivateCode(CardId.TranscodeTalker):
                # Transcode's revival is restricted to its arrows, even when reviving Wicckid.
                choices = self.GetLinkedMaskFor(solvingChain.RelatedCard) & mainMask
                return self.LowestBit(choices if choices != 0 else available)
            wicckid = self.GetWicckid()
            if self._preferWicckidArrows and not self._didSummonToWicckidArrow and \
                    cardId != CardId.CyberseWicckid and cardId != CardId.TranscodeTalker and wicckid is not None:
                choices = self.GetLinkedMaskFor(wicckid) & mainMask
                if choices != 0:
                    # Leave the straight-down zone free for a later Transcode revival.
                    diagonal = choices & ~(self.MZ1 if wicckid.Sequence == 5 else self.MZ3)
                    return self.LowestBit(diagonal if diagonal != 0 else choices)
            if self.IsPawnId(cardId):
                queenMask = self.GetQueenLinkedMMZMask()
                queenChoices = queenMask & available & MAIN_MASK
                if queenChoices != 0:
                    return self.FirstBitFromOrder(queenChoices, [Zones.z2, Zones.z1, Zones.z3, Zones.z0, Zones.z4])
            if cardId == CardId.AlliedCodeTalkerIgnister:
                fw = GetFirstMatchingCard(self.Bot.MonsterZone, lambda m: m is not None and m.IsCode(CardId.FirewallDragon))
                emzAvail = available & self.EMZ_ALL
                if fw is not None and fw.IsFaceup():
                    firewallCenter = fw.Controller == 0 and fw.Location == CardLocation.MonsterZone and fw.Sequence == 2
                    linkedAll = fw.GetLinkedZones()
                    linkedChoices = linkedAll & available
                    linkedEmzChoices = linkedChoices & self.EMZ_ALL
                    if linkedEmzChoices != 0:
                        if firewallCenter and (linkedEmzChoices & self.EMZ_L) != 0 and (linkedEmzChoices & self.EMZ_R) != 0:
                            leftFree = int((available & Zones.z0) != 0) + int((available & Zones.z1) != 0)
                            rightFree = int((available & Zones.z3) != 0) + int((available & Zones.z4) != 0)
                            if leftFree > rightFree:
                                pick = self.EMZ_L
                            elif rightFree > leftFree:
                                pick = self.EMZ_R
                            else:
                                pick = self.FirstBitFromOrder(linkedEmzChoices, [self.EMZ_L, self.EMZ_R])
                        else:
                            pick = self.FirstBitFromOrder(linkedEmzChoices, [self.EMZ_L, self.EMZ_R])
                        return pick
                    if emzAvail != 0:
                        if firewallCenter and (emzAvail & self.EMZ_L) != 0 and (emzAvail & self.EMZ_R) != 0:
                            leftFree = int((available & Zones.z0) != 0) + int((available & Zones.z1) != 0)
                            rightFree = int((available & Zones.z3) != 0) + int((available & Zones.z4) != 0)
                            if leftFree > rightFree:
                                pick = self.EMZ_L
                            elif rightFree > leftFree:
                                pick = self.EMZ_R
                            else:
                                pick = self.FirstBitFromOrder(emzAvail, [self.EMZ_L, self.EMZ_R])
                        else:
                            pick = self.FirstBitFromOrder(emzAvail, [self.EMZ_L, self.EMZ_R])
                        return pick
                    if linkedChoices != 0:
                        return self.FirstBitFromOrder(linkedChoices, [Zones.z2, Zones.z1, Zones.z3, Zones.z0, Zones.z4])
                emzOnly = available & self.EMZ_ALL
                if emzOnly != 0:
                    return self.FirstBitFromOrder(emzOnly, [self.EMZ_L, self.EMZ_R])
                return self.PreferSafeSummonZones(available)
            if cardId == CardId.CyberseWicckid:
                picked = self.ChooseWicckidEmz(available)
                if picked != 0:
                    return picked
                return self.LowestBit(available)
            if cardId == CardId.TranscodeTalker:
                best = 0
                bestScore = -2 ** 31
                for seq in range(7):
                    bit = 1 << seq
                    if (available & bit) == 0:
                        continue
                    linkedMainSeq = 1 if seq == 5 else 3 if seq == 6 else seq + 1
                    freeArrow = linkedMainSeq < 5 and self.Bot.MonsterZone[linkedMainSeq] is None
                    score = (10 if freeArrow else 0) + (1 if seq >= 5 else 0)
                    linkedMonster = self.Bot.MonsterZone[linkedMainSeq] if linkedMainSeq < 5 else None
                    if linkedMonster is not None and linkedMonster.IsFaceup() and linkedMonster.HasType(CardType.Link) and \
                            linkedMonster.HasLinkMarker(CardLinkMarker.Top if seq >= 5 else CardLinkMarker.Left):
                        score += 5
                    if score > bestScore:
                        best = bit
                        bestScore = score
                return best
            if cardId == CardId.MalissQ_RedRansom and self._rrSelfSSPlacing:
                prefer = Zones.z1 | Zones.z3
                wmask = self.GetLinkedMaskFor(self.GetWicckid())
                choices = (available & prefer) & ~wmask
                if choices != 0:
                    pick = self.FirstBitFromOrder(choices, [Zones.z1, Zones.z3])
                    self._rrSelfSSPlacing = False
                    return pick
            if cardId == CardId.LinkDecoder:
                trans = GetFirstMatchingCard(self.Bot.MonsterZone, lambda m: m is not None and m.IsCode(CardId.TranscodeTalker))
                tmask = self.GetLinkedMaskFor(trans) & 0x1F
                safe = (available & 0x1F) & ~tmask
                if safe != 0:
                    return self.FirstBitFromOrder(safe, [Zones.z2, Zones.z1, Zones.z3, Zones.z0, Zones.z4])
            if cardId == CardId.FirewallDragon:
                trans = GetFirstMatchingCard(self.Bot.MonsterZone, lambda m: m is not None and m.IsCode(CardId.TranscodeTalker))
                underTrans = 0
                if trans is not None:
                    tmask = self.GetLinkedMaskFor(trans) & 0x1F
                    if (tmask & Zones.z1) != 0:
                        underTrans |= Zones.z1
                    if (tmask & Zones.z3) != 0:
                        underTrans |= Zones.z3
                choices = available & underTrans
                if choices != 0:
                    return self.FirstBitFromOrder(choices, [Zones.z1, Zones.z3])
            if cardId in (CardId.TranscodeTalker, CardId.AccesscodeTalker, CardId.AlliedCodeTalkerIgnister,
                          CardId.MalissQ_WhiteBinder, CardId.MalissQ_HeartsCrypter):
                return self.PreferSafeSummonZones(available)
            linked = (self.GetMyLinkedMMZMask() & available) & 0x1F
            unlinked = (available & 0x1F) & ~linked
            if self.avoidLinkedZones and unlinked != 0:
                choose = self.LowestBit(unlinked)
            elif linked != 0:
                choose = self.LowestBit(linked)
            else:
                choose = self.LowestBit(available & 0x1F)
            return choose
        return super().OnSelectPlace(cardId, player, location, available)

    def OnSelectPosition(self, cardId, positions):
        cardData = NamedCard.Get(cardId)
        if cardData is not None:
            if self.Duel.Turn == 1 or self.Duel.Phase >= DuelPhase.Main2:
                turnDefense = False
                if cardData.Attack <= cardData.Defense:
                    turnDefense = True
                if turnDefense:
                    return CardPosition.FaceUpDefence
            if self.Duel.Player == 1:
                if cardData.Defense >= cardData.Attack or self.Util.IsOneEnemyBetterThanValue(cardData.Attack, True):
                    return CardPosition.FaceUpDefence
            cardAttack = cardData.Attack
            bestBotAttack = max(self.Util.GetBestAttack(self.Bot), cardAttack)
            if self.Util.IsAllEnemyBetterThanValue(bestBotAttack, True):
                return CardPosition.FaceUpDefence
        return super().OnSelectPosition(cardId, positions)

    def AshBlossomActivate(self):
        if self.CheckWhetherNegated(True) or not self.CheckLastChainShouldNegated():
            return False
        if self.Duel.LastChainPlayer == 1 and self.Util.GetLastChainCard().IsCode(_CardId.MaxxC):
            if self.CheckAtAdvantage() and self.Duel.Turn > 1:
                return False
        return self.DefaultAshBlossomAndJoyousSpring()

    def MaxxCActivate(self):
        if self.CheckWhetherNegated(True) or self.Duel.LastChainPlayer == 0:
            return False
        return self.DefaultMaxxC()

    def InfiniteImpermanenceActivate(self):
        if self.CheckWhetherNegated():
            return False
        for m in self.Enemy.GetMonsters():
            if m.IsMonsterShouldBeDisabledBeforeItUseEffect() and not m.IsDisabled() and self.Duel.LastChainPlayer != 0:
                if self.Card.Location == CardLocation.SpellZone:
                    for i in range(5):
                        if self.Bot.SpellZone[i] == self.Card:
                            self.infiniteImpermanenceList.append(i)
                            break
                if self.Card.Location == CardLocation.Hand:
                    self.SelectSTPlace(self.Card, True)
                self.AI.SelectCard(m)
                return True

        LastChainCard = self.Util.GetLastChainCard()

        if self.Card.Location == CardLocation.SpellZone:
            this_seq = -1
            that_seq = -1
            for i in range(5):
                if self.Bot.SpellZone[i] == self.Card:
                    this_seq = i
                if LastChainCard is not None and LastChainCard.Controller == 1 and \
                        LastChainCard.Location == CardLocation.SpellZone and self.Enemy.SpellZone[i] == LastChainCard:
                    that_seq = i
                elif self.Duel.Player == 0 and self.Util.GetProblematicEnemySpell() is not None and \
                        self.Enemy.SpellZone[i] is not None and self.Enemy.SpellZone[i].IsFloodgate():
                    that_seq = i
            if (this_seq * that_seq >= 0 and this_seq + that_seq == 4) or self.Util.IsChainTarget(self.Card) or \
                    (LastChainCard is not None and LastChainCard.Controller == 1 and
                     LastChainCard.IsCode(_CardId.HarpiesFeatherDuster)):
                target = self.GetProblematicEnemyMonster(canBeTarget=True)
                self.AI.SelectCard(target)
                self.infiniteImpermanenceList.append(this_seq)
                return True
        if LastChainCard is None or LastChainCard.Controller != 1 or LastChainCard.Location != CardLocation.MonsterZone \
                or LastChainCard.IsDisabled() or LastChainCard.IsShouldNotBeTarget() or \
                LastChainCard.IsShouldNotBeSpellTrapTarget():
            return False

        if self.Card.Location == CardLocation.SpellZone:
            for i in range(5):
                if self.Bot.SpellZone[i] == self.Card:
                    self.infiniteImpermanenceList.append(i)
                    break
        if self.Card.Location == CardLocation.Hand:
            self.SelectSTPlace(self.Card, True)
        if LastChainCard is not None:
            self.AI.SelectCard(LastChainCard)
        else:
            enemyMonsters = sorted(self.Enemy.GetMonsters(), key=CompareCardAttack)
            enemyMonsters.reverse()
            for card in enemyMonsters:
                if card.IsFaceup() and not card.IsShouldNotBeTarget() and not card.IsShouldNotBeSpellTrapTarget():
                    self.AI.SelectCard(card)
                    return True
        return True

    def CrossoutDesignatorActivate(self):
        if self.CheckWhetherNegated() or not self.CheckLastChainShouldNegated():
            return False
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
                if not self.Card.Location == CardLocation.SpellZone:
                    self.SelectSTPlace(None, True)
                self.AI.SelectAnnounceID(code)
                self.currentNegateCardList.extend(c for c in self.Enemy.MonsterZone
                                                  if c is not None and c.IsFaceup() and c.IsCode(code))
                return True
        return False

    def CalledbytheGraveActivate(self):
        if self.CheckWhetherNegated() or not self.CheckLastChainShouldNegated():
            return False
        if self.Duel.LastChainPlayer == 1:
            if self.Util.GetLastChainCard().IsMonster():
                code = self.Util.GetLastChainCard().GetOriginCode()
                if code == 0:
                    return False
                if self.DefaultCheckWhetherCardIdIsNegated(code):
                    return False
                if self.Util.GetLastChainCard().IsCode(_CardId.MaxxC) and self.CheckAtAdvantage() and self.Duel.Turn > 1:
                    return False
                graveTarget = GetFirstMatchingCard(self.Enemy.Graveyard,
                                                   lambda card: card.IsMonster() and card.GetOriginCode() == code)
                if graveTarget is not None:
                    if not self.Card.Location == CardLocation.SpellZone:
                        self.SelectSTPlace(None, True)
                    self.AI.SelectCard(graveTarget)
                    self.currentDestroyCardList.append(graveTarget)
                    return True

            for graveCard in self.Enemy.Graveyard:
                if graveCard in self.Duel.ChainTargets and graveCard.IsMonster():
                    if not self.Card.Location == CardLocation.SpellZone:
                        self.SelectSTPlace(None, True)
                    self.AI.SelectCard(graveCard)
                    self.currentDestroyCardList.append(graveCard)
                    return True

            if self.Card in self.Duel.ChainTargets:
                enemyMonsters = GetMatchingCards(self.Enemy.Graveyard, lambda card: card.IsMonster())
                if len(enemyMonsters) > 0:
                    enemyMonsters.sort(key=CompareCardAttack)
                    enemyMonsters.reverse()
                    code = enemyMonsters[0].Id
                    self.AI.SelectCard(code)
                    self.currentDestroyCardList.append(enemyMonsters[0])
                    return True

        if self.Duel.LastChainPlayer == 1:
            return False
        targets = self.GetDangerousCardinEnemyGrave(True)
        if len(targets) > 0:
            code = targets[0].Id
            if not self.Card.Location == CardLocation.SpellZone:
                self.SelectSTPlace(None, True)
            self.AI.SelectCard(code)
            self.currentDestroyCardList.append(targets[0])
            return True
        return False

    def SpellSetCheck(self):
        if self.Duel.Phase == DuelPhase.Main1 and self.Bot.HasAttackingMonster() and self.Duel.Turn > 1:
            return False
        onlyOneSetList = []
        if self.Card.Id in onlyOneSetList and self.Bot.HasInSpellZone(self.Card.Id):
            return False

        if self.Card.IsTrap() or self.Card.HasType(CardType.QuickPlay):
            avoid_list = []
            setFornfiniteImpermanence = 0
            for i in range(5):
                if self.Enemy.SpellZone[i] is not None and self.Enemy.SpellZone[i].IsFaceup() and \
                        self.Bot.SpellZone[4 - i] is None:
                    avoid_list.append(4 - i)
                    setFornfiniteImpermanence += 1 << (4 - i)
            if self.Bot.HasInHand(_CardId.InfiniteImpermanence):
                if self.Card.IsCode(_CardId.InfiniteImpermanence):
                    self.AI.SelectPlace(setFornfiniteImpermanence)
                    return True
                else:
                    self.SelectSTPlace(self.Card, False, avoid_list)
                    return True
            else:
                self.SelectSTPlace()
            if self.Card.IsCode(CardId.MalissC_MTP07):
                self.mtp07SetThisTurn = True
            if self.Card.IsCode(CardId.MalissC_GWC06):
                self.gwc06SetThisTurn = True
            return True
        return False

    def GetDangerousCardinEnemyGrave(self, onlyMonster=False):
        result = GetMatchingCards(self.Enemy.Graveyard, lambda card: (not onlyMonster or card.IsMonster()) and (
            card.HasSetcode(self.SetcodeOrcust) or card.HasSetcode(self.SetcodePhantom) or
            card.HasSetcode(self.SetcodeHorus) or card.HasSetcode(self.SetcodeDarkWorld) or
            card.HasSetcode(self.SetcodeSkyStriker)))
        dangerMonsterIdList = [99937011, 63542003, 9411399, 28954097, 30680659, 32731036]
        result.extend(GetMatchingCards(self.Enemy.Graveyard, lambda card: card.Id in dangerMonsterIdList))
        return result

    def CheckWhetherNegated(self, disablecheck=True, toFieldCheck=False, type_=0):
        isMonster = type_ == 0 and self.Card.IsMonster()
        isMonster |= (type_ & CardType.Monster) != 0
        isSpellOrTrap = type_ == 0 and (self.Card.IsSpell() or self.Card.IsTrap())
        isSpellOrTrap |= (type_ & CardType.Spell) != 0 or (type_ & CardType.Trap) != 0
        isCounter = (type_ & CardType.Counter) != 0
        if isSpellOrTrap and toFieldCheck and self.CheckSpellWillBeNegate(isCounter):
            return True
        if self.DefaultCheckWhetherCardIsNegated(self.Card):
            return True
        if isMonster and (toFieldCheck or self.Card.Location == CardLocation.MonsterZone):
            if (toFieldCheck and (type_ & CardType.Link) == 0) or self.Card.IsDefense():
                if self.DefaultCheckWhetherNumber41IsActive():
                    return True
            if self.Enemy.HasInSpellZone(CardId.SkillDrain, True):
                return True
        if disablecheck:
            return (self.Card.Location == CardLocation.MonsterZone or self.Card.Location == CardLocation.SpellZone) and \
                self.Card.IsDisabled() and self.Card.IsFaceup()
        return False

    def SelectSTPlace(self, card=None, avoidImpermanence=False, avoidList=None):
        if card is None:
            card = self.Card
        list_ = []
        for seq in range(5):
            if self.Bot.SpellZone[seq] is None:
                if card is not None and card.Location == CardLocation.Hand and avoidImpermanence and \
                        seq in self.infiniteImpermanenceList:
                    continue
                if avoidList is not None and seq in avoidList:
                    continue
                list_.append(seq)
        ShuffleListInPlace(list_)
        if avoidImpermanence and any(c.IsFaceup() and not c.IsDisabled() for c in self.Bot.GetMonsters()):
            for seq in list_:
                enemySpell = self.Enemy.SpellZone[4 - seq]
                if enemySpell is not None and enemySpell.IsFacedown():
                    continue
                self.AI.SelectPlace(1 << seq)
                return
        for seq in list_:
            self.AI.SelectPlace(1 << seq)
            return
        self.AI.SelectPlace(0)

    def CheckSpellWillBeNegate(self, isCounter=False, target=None):
        if target is None:
            target = self.Card
        if target.Location != CardLocation.SpellZone and target.Location != CardLocation.Hand:
            return False
        if self.Enemy.HasInMonstersZone(CardId.NaturalExterio, True) and not isCounter:
            return True
        if target.IsSpell():
            if self.Enemy.HasInMonstersZone(CardId.NaturalBeast, True):
                return True
            if self.Enemy.HasInSpellZone(CardId.ImperialOrder, True) or self.Bot.HasInSpellZone(CardId.ImperialOrder, True):
                return True
            if self.Enemy.HasInMonstersZone(CardId.SwordsmanLV7, True) or self.Bot.HasInMonstersZone(CardId.SwordsmanLV7, True):
                return True
        if target.IsTrap() and (self.Enemy.HasInSpellZone(CardId.RoyalDecree, True) or
                                self.Bot.HasInSpellZone(CardId.RoyalDecree, True)):
            return True
        if target.Location == CardLocation.SpellZone and (target.IsSpell() or target.IsTrap()):
            selfSeq = -1
            for i in range(5):
                if self.Bot.SpellZone[i] == self.Card:
                    selfSeq = i
            if selfSeq in self.infiniteImpermanenceList:
                return True
        return False

    def CheckLastChainShouldNegated(self):
        lastcard = self.Util.GetLastChainCard()
        if lastcard is None or lastcard.Controller != 1:
            return False
        if lastcard.IsMonster() and lastcard.HasSetcode(self.SetcodeTimeLord) and self.Duel.Phase == DuelPhase.Standby:
            return False
        if lastcard.Id in self.notToNegateIdList:
            return False
        if self.DefaultCheckWhetherCardIsNegated(lastcard):
            return False
        if self.Duel.Turn == 1 and lastcard.IsCode(_CardId.MaxxC):
            return False
        return True

    def GetProblematicEnemyMonster(self, attack=0, canBeTarget=False, ignoreCurrentDestroy=False, selfType=0):
        floodagateCard = _max_by([c for c in self.Enemy.GetMonsters()
                                  if c is not None and c.Data is not None and
                                  (ignoreCurrentDestroy or c not in self.currentDestroyCardList) and
                                  c.IsFloodgate() and c.IsFaceup() and
                                  self.CheckCanBeTargeted(c, canBeTarget, selfType) and self.CheckShouldNotIgnore(c)],
                                 key=lambda card: card.Attack)
        if floodagateCard is not None:
            return floodagateCard

        dangerCard = _max_by([c for c in self.Enemy.MonsterZone
                              if c is not None and c.Data is not None and
                              (ignoreCurrentDestroy or c not in self.currentDestroyCardList) and
                              c.IsMonsterDangerous() and c.IsFaceup() and
                              self.CheckCanBeTargeted(c, canBeTarget, selfType) and self.CheckShouldNotIgnore(c)],
                             key=lambda card: card.Attack)
        if dangerCard is not None:
            return dangerCard

        invincibleCard = _max_by([c for c in self.Enemy.MonsterZone
                                  if c is not None and c.Data is not None and
                                  (ignoreCurrentDestroy or c not in self.currentDestroyCardList) and
                                  c.IsMonsterInvincible() and c.IsFaceup() and
                                  self.CheckCanBeTargeted(c, canBeTarget, selfType) and self.CheckShouldNotIgnore(c)],
                                 key=lambda card: card.Attack)
        if invincibleCard is not None:
            return invincibleCard

        equippedCard = _max_by([c for c in self.Enemy.MonsterZone
                                if c is not None and c.Data is not None and
                                (ignoreCurrentDestroy or c not in self.currentDestroyCardList) and
                                len(c.EquipCards) > 0 and self.CheckCanBeTargeted(c, canBeTarget, selfType) and
                                self.CheckShouldNotIgnore(c)],
                               key=lambda card: card.Attack)
        if equippedCard is not None:
            return equippedCard

        enemyExtraMonster = _max_by([c for c in self.Enemy.MonsterZone
                                     if c is not None and (ignoreCurrentDestroy or c not in self.currentDestroyCardList) and
                                     (c.HasType(CardType.Fusion | CardType.Ritual | CardType.Synchro | CardType.Xyz) or
                                      (c.HasType(CardType.Link) and c.LinkCount >= 2)) and
                                     self.CheckCanBeTargeted(c, canBeTarget, selfType) and self.CheckShouldNotIgnore(c)],
                                    key=lambda card: card.Attack)
        if enemyExtraMonster is not None:
            return enemyExtraMonster

        if attack >= 0:
            if attack == 0:
                attack = self.Util.GetBestAttack(self.Bot)
            betterCard = _max_by([card for card in self.Enemy.MonsterZone
                                  if card is not None and card.GetDefensePower() >= attack and
                                  card.GetDefensePower() > 0 and card.IsAttack() and
                                  self.CheckCanBeTargeted(card, canBeTarget, selfType) and
                                  (ignoreCurrentDestroy or card not in self.currentDestroyCardList)],
                                 key=lambda card: card.Attack)
            if betterCard is not None:
                return betterCard
        return None

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

    def CheckShouldNotIgnore(self, cards, ignore=False):
        return not ignore or (cards not in self.currentDestroyCardList and cards not in self.currentNegateCardList)

    def GetProblematicEnemyCardList(self, canBeTarget=False, ignoreSpells=False, selfType=0):
        resultList = []

        floodagateList = sorted((c for c in self.Enemy.MonsterZone
                                 if c is not None and c.Data is not None and c not in self.currentDestroyCardList and
                                 c.IsFloodgate() and c.IsFaceup() and self.CheckCanBeTargeted(c, canBeTarget, selfType)),
                                key=lambda card: -card.Attack)
        if len(floodagateList) > 0:
            resultList.extend(floodagateList)

        problemEnemySpellList = [c for c in self.Enemy.SpellZone
                                 if c is not None and c.Data is not None and c not in resultList and
                                 c not in self.currentDestroyCardList and c.IsFloodgate() and c.IsFaceup() and
                                 self.CheckCanBeTargeted(c, canBeTarget, selfType)]
        if len(problemEnemySpellList) > 0:
            resultList.extend(self.Util.ShuffleList(problemEnemySpellList))

        dangerList = sorted((c for c in self.Enemy.MonsterZone
                             if c is not None and c.Data is not None and c not in resultList and
                             c not in self.currentDestroyCardList and c.IsMonsterDangerous() and c.IsFaceup() and
                             self.CheckCanBeTargeted(c, canBeTarget, selfType)),
                            key=lambda card: -card.Attack)
        if len(dangerList) > 0 and (self.Duel.Player == 0 or DuelPhase.Main1 < self.Duel.Phase < DuelPhase.Main2):
            resultList.extend(dangerList)

        invincibleList = sorted((c for c in self.Enemy.MonsterZone
                                 if c is not None and c.Data is not None and c not in resultList and
                                 c not in self.currentDestroyCardList and c.IsMonsterInvincible() and c.IsFaceup() and
                                 self.CheckCanBeTargeted(c, canBeTarget, selfType)),
                                key=lambda card: -card.Attack)
        if len(invincibleList) > 0:
            resultList.extend(invincibleList)

        enemyMonsters = sorted((c for c in self.Enemy.GetMonsters() if c not in self.currentDestroyCardList),
                               key=lambda card: -card.Attack)
        if len(enemyMonsters) > 0:
            for target in enemyMonsters:
                if (target.HasType(CardType.Fusion | CardType.Ritual | CardType.Synchro | CardType.Xyz) or
                        (target.HasType(CardType.Link) and target.LinkCount >= 2)) and \
                        target not in resultList and self.CheckCanBeTargeted(target, canBeTarget, selfType):
                    resultList.append(target)

        spells = [c for c in self.Enemy.GetSpells()
                  if c.IsFaceup() and c not in self.currentDestroyCardList and
                  c.HasType(CardType.Equip | CardType.Pendulum | CardType.Field | CardType.Continuous) and
                  self.CheckCanBeTargeted(c, canBeTarget, selfType) and c.Id not in self.notToDestroySpellTrap]
        if len(spells) > 0 and not ignoreSpells:
            resultList.extend(self.Util.ShuffleList(spells))

        return resultList

    def GetNormalEnemyTargetList(self, canBeTarget=True, ignoreCurrentDestroy=False, selfType=0):
        targetList = self.GetProblematicEnemyCardList(canBeTarget, selfType=selfType)
        enemyMonster = [card for card in self.Enemy.GetMonsters()
                        if card.IsFaceup() and card not in targetList and
                        (not ignoreCurrentDestroy or card not in self.currentDestroyCardList)]
        enemyMonster.sort(key=CompareCardAttack)
        enemyMonster.reverse()
        targetList.extend(enemyMonster)
        targetList.extend(self.Util.ShuffleList([card for card in self.Enemy.GetSpells()
                                                 if (not ignoreCurrentDestroy or card not in self.currentDestroyCardList)
                                                 and card in self.enemyPlaceThisTurn]))
        targetList.extend(self.Util.ShuffleList([card for card in self.Enemy.GetSpells()
                                                 if (not ignoreCurrentDestroy or card not in self.currentDestroyCardList)
                                                 and card not in self.enemyPlaceThisTurn]))
        targetList.extend(self.Util.ShuffleList([card for card in self.Enemy.GetMonsters()
                                                 if card.IsFacedown() and
                                                 (not ignoreCurrentDestroy or card not in self.currentDestroyCardList)]))
        return targetList

    def GetMonsterListForTargetNegate(self, canBeTarget=False, selfType=0):
        resultList = []
        if self.CheckWhetherNegated():
            return resultList

        target = next((card for card in self.Enemy.MonsterZone
                       if card is not None and card.Data is not None and
                       card.IsMonsterShouldBeDisabledBeforeItUseEffect() and card.IsFaceup() and
                       not card.IsShouldNotBeTarget() and self.CheckCanBeTargeted(card, canBeTarget, selfType) and
                       card not in self.currentNegateCardList), None)
        if target is not None:
            resultList.append(target)

        for chainingCard in self.Duel.CurrentChain:
            if chainingCard.Location == CardLocation.MonsterZone and chainingCard.Controller == 1 and \
                    not chainingCard.IsDisabled() and self.CheckCanBeTargeted(chainingCard, canBeTarget, selfType) and \
                    chainingCard not in self.currentNegateCardList:
                resultList.append(chainingCard)
        return resultList

    def GetBestEnemyMonster(self, onlyFaceup=False, canBeTarget=False):
        card = self.GetProblematicEnemyMonster(0, canBeTarget)
        if card is not None:
            return card
        card = GetHighestAttackMonster(self.Enemy.MonsterZone, canBeTarget)
        if card is not None:
            return card
        monsters = [c for c in self.Enemy.GetMonsters() if not canBeTarget or not c.IsShouldNotBeTarget()]
        if len(monsters) > 0 and not onlyFaceup:
            return self.Util.ShuffleList(monsters)[0]
        return None

    def GetBestEnemySpell(self, onlyFaceup=False, canBeTarget=False):
        problemEnemySpellList = [c for c in self.Enemy.SpellZone
                                 if c is not None and c.Data is not None and c.IsFloodgate() and c.IsFaceup() and
                                 (not canBeTarget or not c.IsShouldNotBeTarget())]
        if len(problemEnemySpellList) > 0:
            return self.Util.ShuffleList(problemEnemySpellList)[0]

        spells = [card for card in self.Enemy.GetSpells() if not (card.IsFaceup() and card.IsCode(_CardId.EvenlyMatched))]
        faceUpList = [ecard for ecard in spells
                      if ecard.IsFaceup() and (ecard.HasType(CardType.Continuous) or ecard.HasType(CardType.Field) or
                                               ecard.HasType(CardType.Pendulum))]
        if len(faceUpList) > 0:
            return self.Util.ShuffleList(faceUpList)[0]
        if len(spells) > 0 and not onlyFaceup:
            return self.Util.ShuffleList(spells)[0]
        return None

    def GetBestEnemyCard(self, onlyFaceup=False, canBeTarget=False, checkGrave=False):
        card = self.GetBestEnemyMonster(onlyFaceup, canBeTarget)
        if card is not None:
            return card
        card = self.GetBestEnemySpell(onlyFaceup, canBeTarget)
        if card is not None:
            return card
        if checkGrave and len(self.Enemy.Graveyard) > 0:
            graveMonsterList = GetMatchingCards(self.Enemy.Graveyard, lambda c: c.IsMonster())
            if len(graveMonsterList) > 0:
                graveMonsterList.sort(key=CompareCardAttack)
                graveMonsterList.reverse()
                return graveMonsterList[0]
            return self.Util.ShuffleList(list(self.Enemy.Graveyard))[0]
        return None

    def LinkVal(self, c):
        return max(1, c.LinkCount) if (c is not None and c.HasType(CardType.Link)) else 1

    def IsInEMZ(self, c):
        mz = self.Bot.MonsterZone
        return (len(mz) > 5 and mz[5] == c) or (len(mz) > 6 and mz[6] == c)

    def HasFreeEMZ(self):
        mz = self.Bot.MonsterZone
        slot5Free = len(mz) > 5 and mz[5] is None
        slot6Free = len(mz) > 6 and mz[6] is None
        return slot5Free or slot6Free

    # ==================== work space #1 ====================
    def OnSpSummoned(self):
        wicckid = self.GetWicckid()
        if self._preferWicckidArrows and wicckid is not None and wicckid not in self.Duel.LastSummonedCards and \
                any(c is not None and c.Controller == 0 and c.Location == CardLocation.MonsterZone and
                    (self.GetLinkedMaskFor(wicckid) & (1 << c.Sequence)) != 0 for c in self.Duel.LastSummonedCards):
            self._didSummonToWicckidArrow = True
            self._preferWicckidArrows = False
        super().OnSpSummoned()

    def OnChainSolved(self, chainIndex):
        currentChain = self.Duel.GetCurrentSolvingChainInfo()
        if currentChain is not None and not self.Duel.IsCurrentSolvingChainNegated() and currentChain.ActivatePlayer == 1:
            if currentChain.IsActivateCode(CardId.Lancea):
                self.enemyActivateLancea = True
            if currentChain.IsActivateCode(_CardId.MaxxC):
                self.enemyActivateMaxxC = True
            if currentChain.IsActivateCode(CardId.Fuwalos):
                self.enemyActivateFuwalos = True
            if currentChain.IsActivateCode(_CardId.InfiniteImpermanence):
                for i in range(5):
                    if self.Enemy.SpellZone[i] == currentChain.RelatedCard:
                        self.infiniteImpermanenceList.append(4 - i)
                        break
            if currentChain.IsSpell() and (currentChain.HasType(CardType.Field) or
                                                    currentChain.HasType(CardType.Continuous) or
                                                    currentChain.HasType(CardType.Equip)):
                self._oppJustActivatedPersistentSpell = True
            self._prefWindowTTL = max(self._prefWindowTTL, 2)
        if currentChain is not None and currentChain.ActivatePlayer == 0 and currentChain.IsActivateCode(CardId.SplashMage):
            if self.Duel.IsCurrentSolvingChainNegated():
                self.splashNegatedThisTurn = True
        super().OnChainSolved(chainIndex)

    def OnChainEnd(self):
        self.escapeTargetList.clear()
        self.currentNegateCardList.clear()
        self.currentDestroyCardList.clear()
        self._oppJustActivatedPersistentSpell = False
        curMon = self.Enemy.GetMonsterCount()
        if curMon > self._enemyMonsterCountSnap:
            self._oppJustSummoned = True
        self._enemyMonsterCountSnap = curMon
        curFD = sum(1 for c in self.Enemy.SpellZone if c is not None and c.IsFacedown())
        if curFD > self._enemyFacedownSTSnap:
            self._oppJustSet = True
        self._enemyFacedownSTSnap = curFD
        for idx in range(len(self.enemyPlaceThisTurn) - 1, -1, -1):
            checkTarget = self.enemyPlaceThisTurn[idx]
            if checkTarget is None or (checkTarget.Location != CardLocation.SpellZone and
                                       checkTarget.Location != CardLocation.MonsterZone):
                del self.enemyPlaceThisTurn[idx]
        super().OnChainEnd()

    def OnNewTurn(self):
        if self.Duel.Player == 0:
            self.myTurnCount += 1
        self.enemyActivateLancea = False
        self.enemyActivateFuwalos = False
        self.enemyActivateMaxxC = False
        if self.__dimensionShifterCount > 0:
            self.__dimensionShifterCount -= 1
        self.infiniteImpermanenceList.clear()
        self.currentNegateCardList.clear()
        self.currentDestroyCardList.clear()
        self.sendToGYThisTurn.clear()
        self.activatedCardIdList.clear()
        self.enemyPlaceThisTurn.clear()
        self.summonThisTurn.clear()

        # reset Maliss flags
        self.usedNormalSummon = False
        self.ssChessyCat = False
        self.ssDormouse = False
        self.ssMarchHare = False
        self.ssWhiteRabbit = False
        self.ActiveMarchHare = False
        self.ActiveUnderground = False
        self.step1Done = False
        self.step2Done = False
        self.lastRevivedIdBySplash = 0
        self.mtp07SetThisTurn = False
        self.gwc06SetThisTurn = False
        self.splashNegatedThisTurn = False
        self.ssRRThisTurn = False
        self.ssWBThisTurn = False
        self.ssHCThisTurn = False
        self._didSplashToRR = self._didRRtoWicckid = self._didSummonToWicckidArrow = False
        self._preferWicckidArrows = False
        self._rrSelfSSPlacing = False
        self._oppJustActivatedPersistentSpell = False
        self._oppJustSummoned = False
        self._oppJustSet = False
        self._enemyMonsterCountSnap = self.Enemy.GetMonsterCount()
        self._enemyFacedownSTSnap = sum(1 for c in self.Enemy.SpellZone if c is not None and c.IsFacedown())
        self._prefWindowTTL = 0
        self.Allied_End = False
        self.nsplan = False
        self.nsBackupplan = False
        self.NSDorMouse = False
        super().OnNewTurn()

    def OnSelectYesNo(self, desc):
        if desc == self.Util.GetStringId(CardId.AmeNoMurakumoNoMitsurugi, 3):
            shouldDiscard = len(self.Bot.Hand) >= 2
            return shouldDiscard
        if desc == self.Util.GetStringId(CardId.MalissQ_WhiteBinder, 0):
            anyGY = len(self.Bot.Graveyard) > 0 or len(self.Enemy.Graveyard) > 0
            return anyGY
        return super().OnSelectYesNo(desc)

    def DontSelfNG(self):
        return self.Duel.LastChainPlayer != 0

    def OnSelectCard(self, cards, min_, max_, hint, cancelable):
        solving = self.Duel.GetCurrentSolvingChainInfo()
        if solving is not None and solving.ActivatePlayer == 1 and solving.IsActivateCode(CardId.AmeNoMurakumoNoMitsurugi) \
                and cards is not None and len(cards) > 0 and (hint == HintMsg.Discard or hint == HintMsg.ToGrave) and \
                all(c is not None and c.Controller == 0 and c.Location == CardLocation.Hand for c in cards):
            discardOrder = sorted(cards, key=self.ScoreMalissMurakumoDiscard)
            return self.Util.CheckSelectCount(discardOrder, cards, min_, max_)
        if cards is not None and len(cards) > 0 and solving is not None:
            if solving.IsActivateCode(CardId.MalissQ_RedRansom):
                searchPool = [c for c in cards if c is not None and
                              (c.IsCode(CardId.MalissInUnderground) or c.IsCode(CardId.MalissInTheMirror))]
                if len(searchPool) > 0:
                    shouldUG = self.ShouldSearchUnderground()
                    chooseId = 0
                    if shouldUG and any(c.IsCode(CardId.MalissInUnderground) for c in searchPool):
                        chooseId = CardId.MalissInUnderground
                    elif any(c.IsCode(CardId.MalissInTheMirror) for c in searchPool):
                        chooseId = CardId.MalissInTheMirror
                    if chooseId != 0:
                        pick = next(c for c in searchPool if c.IsCode(chooseId))
                        return [pick]
            if hint == HintMsg.Set and solving.IsActivateCode(CardId.MalissQ_WhiteBinder):
                pick = next((c for c in cards if c.Id == CardId.MalissC_GWC06 and c.Location == CardLocation.Deck), None)
                if pick is None:
                    pick = next((c for c in cards if c.Id == CardId.MalissC_GWC06), None)
                if pick is None:
                    pick = next((c for c in cards if c.Id == CardId.MalissC_MTP07), None)
                if pick is not None:
                    if pick.Id == CardId.MalissC_GWC06:
                        self.gwc06SetThisTurn = True
                    elif pick.Id == CardId.MalissC_MTP07:
                        self.mtp07SetThisTurn = True
                    return [pick]
        return super().OnSelectCard(cards, min_, max_, hint, cancelable)

    # ==================== work space #2 ====================
    def GetMMZCount(self):
        return sum(1 for c in self.Bot.MonsterZone[:5] if c is not None)

    def HasFreeMMZ(self):
        return self.GetMMZCount() < 5

    def HaveTwoBodies(self):
        return self.Bot.GetMonsterCount() >= 2

    def ShouldFastEndToSPLK(self):
        return self.enemyActivateMaxxC or self.enemyActivateFuwalos

    def Step1Complete(self):
        return self.Bot.HasInMonstersZone(CardId.MalissP_Dormouse) and self.Bot.HasInMonstersZone(CardId.MalissP_WhiteRabbit)

    def CanStartStep1(self):
        if self.enemyActivateLancea or self.ShouldFastEndToSPLK():
            return False
        if self.HaveTwoBodies():
            return False
        if not self.HasFreeMMZ():
            return False
        haveStarterInHand = self.Bot.HasInHand(CardId.MalissP_Dormouse) or \
            self.Bot.HasInHand(CardId.MalissP_WhiteRabbit) or \
            self.Bot.HasInHand(CardId.GoldSarcophagus) or \
            self.Bot.HasInHand(CardId.TERRAFORMING) or \
            self.Bot.HasInHand(CardId.MalissInUnderground)
        return haveStarterInHand

    def CanContinueStep1(self):
        if self.enemyActivateLancea:
            return False
        return not self.HaveTwoBodies() and self.HasFreeMMZ()

    def PickMalissTrapToSet(self):
        if self.Duel.Player == 0 and self.Bot.HasInMonstersZone(CardId.MalissP_Dormouse) and \
                self.Bot.HasInMonstersZone(CardId.MalissP_WhiteRabbit):
            pref = CardId.MalissC_GWC06
        elif self.Duel.Player == 0 and (self.Bot.HasInMonstersZoneOrInGraveyard(CardId.MalissQ_RedRansom) or
                                        self.Bot.HasInBanished(CardId.MalissQ_RedRansom)):
            pref = CardId.MalissC_GWC06
        elif self.Duel.Player == 0 and self.Bot.HasInHand(CardId.MalissP_MarchHare) and not self.ActiveMarchHare and \
                not self.ssWhiteRabbit:
            pref = CardId.MalissC_GWC06
        elif self.Duel.Player == 0 and self.nsBackupplan:
            pref = CardId.MalissC_GWC06
        elif self.Duel.Player == 1:
            pref = CardId.MalissC_MTP07
        else:
            pref = CardId.MalissC_MTP07
        if self.Bot.HasInDeck(pref):
            return pref
        return 0

    def ActLittleKnight(self):
        if self.ActivateDescription == -1 or self.ActivateDescription == self.Util.GetStringId(CardId.SP_LITTLE_KNIGHT, 0):
            problemCardList = self.GetProblematicEnemyCardList(True, selfType=CardType.Monster)
            problemCardList.extend(self.GetDangerousCardinEnemyGrave(False))
            problemCardList.extend(self.GetNormalEnemyTargetList(True, True, CardType.Monster))
            problemCardList.extend(sorted((card for card in self.Enemy.Graveyard if card.HasType(CardType.Monster)),
                                          key=lambda card: -card.Attack))
            problemCardList.extend(card for card in self.Enemy.Graveyard if not card.HasType(CardType.Monster))
            if len(problemCardList) > 0:
                self.AI.SelectCard(problemCardList)
                self.activatedCardIdList.append(self.Card.Id)
                return True
        elif self.ActivateDescription == self.Util.GetStringId(CardId.SP_LITTLE_KNIGHT, 1):
            selfMonster = None
            for target in self.Bot.GetMonsters():
                if target in self.Duel.ChainTargets and target not in self.escapeTargetList:
                    selfMonster = target
                    break
            if selfMonster is None:
                if self.Duel.Player == 1:
                    selfMonster = _min_by([card for card in self.Bot.GetMonsters() if card.IsAttack()],
                                          key=lambda card: card.Attack)
                    # C# dereferences selfMonster here even when it is null
                    if selfMonster is not None and not self.Util.IsOneEnemyBetterThanValue(selfMonster.Attack, True):
                        selfMonster = None
            if selfMonster is not None:
                nextMonster = None
                selfTargetList = [card for card in self.Bot.GetMonsters() if card != selfMonster]
                if self.Enemy.GetMonsterCount() == 0 and len(selfTargetList) > 0:
                    selfTargetList.sort(key=cmp_to_key(self.CompareUsableAttack))
                    nextMonster = selfTargetList[0]
                    self.escapeTargetList.append(nextMonster)
                if self.Enemy.GetMonsterCount() > 0:
                    nextMonster = self.GetBestEnemyMonster(True, True)
                    self.currentDestroyCardList.append(nextMonster)
                if nextMonster is not None:
                    self.AI.SelectCard(selfMonster)
                    self.AI.SelectNextCard(nextMonster)
                    self.escapeTargetList.append(selfMonster)
                    self.activatedCardIdList.append(self.Card.Id + 1)
                    return True
        return False

    def CompareUsableAttack(self, cardA, cardB):
        if cardA is None and cardB is None:
            return 0
        if cardA is None:
            return -1
        if cardB is None:
            return 1
        powerA = 0 if (cardA.IsDefense() and cardA in self.summonThisTurn) else cardA.Attack
        powerB = 0 if (cardB.IsDefense() and cardB in self.summonThisTurn) else cardB.Attack
        if powerA < powerB:
            return -1
        if powerA == powerB:
            return (cardA.Level > cardB.Level) - (cardA.Level < cardB.Level)  # CardContainer.CompareCardLevel
        return 1

    def Step1_Dormouse_NormalSummon(self):
        if not self.CanStartStep1():
            return False
        if self.usedNormalSummon:
            return False
        self.usedNormalSummon = True
        self.NSDorMouse = True
        return True

    def Dormouse_ForMH(self):
        if self.DefaultCheckWhetherCardIdIsNegated(self.Card.Id):
            return False
        if not self.CanContinueStep1():
            return False
        if self.Card.Location != CardLocation.MonsterZone:
            return False
        if self.DefaultCheckWhetherCardIsNegated(self.Card):
            return False
        if self.goldstart or self.undergroundstart:
            pick = CardId.MalissP_WhiteRabbit if self.Bot.HasInDeck(CardId.MalissP_WhiteRabbit) else CardId.MalissP_ChessyCat
        else:
            pick = CardId.MalissP_MarchHare if self.Bot.HasInDeck(CardId.MalissP_MarchHare) \
                else CardId.MalissP_WhiteRabbit if self.Bot.HasInDeck(CardId.MalissP_WhiteRabbit) \
                else CardId.MalissP_ChessyCat
        if pick == 0:
            return False
        self.AI.SelectCard(pick)
        return True

    def Step1_WhiteRabbit_SS_FromBanished(self):
        if self.DefaultCheckWhetherCardIdIsNegated(self.Card.Id):
            return False
        if self.enemyActivateLancea:
            return False
        if self.Card.Id != CardId.MalissP_WhiteRabbit:
            return False
        if self.Card.Location != CardLocation.Removed:
            return False
        if self.Bot.LifePoints <= 300:
            return False
        self.ssWhiteRabbit = True
        return True

    def Step1_WhiteRabbit_SetTrapOnSummon(self):
        if self.DefaultCheckWhetherCardIdIsNegated(self.Card.Id):
            return False
        if self.Card.Id != CardId.MalissP_WhiteRabbit:
            return False
        if self.Card.Location != CardLocation.MonsterZone:
            return False
        if self.DefaultCheckWhetherCardIsNegated(self.Card):
            return False
        trapToSet = self.PickMalissTrapToSet()
        if trapToSet == 0:
            return False
        if trapToSet == CardId.MalissC_GWC06:
            self.gwc06SetThisTurn = True
        if trapToSet == CardId.MalissC_MTP07:
            self.mtp07SetThisTurn = True
        self.AI.SelectCard(trapToSet)
        self.SelectSafeSTZoneAwayFromImperm()
        if self.Step1Complete():
            self.step1Done = True
        return True

    def Step1_WhiteRabbit_NormalSummon(self):
        if not self.CanStartStep1():
            return False
        if self.Bot.HasInHand(CardId.MalissP_Dormouse):
            return False
        if self.usedNormalSummon:
            return False
        self.usedNormalSummon = True
        return True

    def Dormouse_SS_FromBanished(self):
        if self.DefaultCheckWhetherCardIdIsNegated(self.Card.Id):
            return False
        if self.Card.Id != CardId.MalissP_Dormouse:
            return False
        if self.Card.Location != CardLocation.Removed:
            return False
        if self.enemyActivateLancea:
            return False
        if self.Bot.LifePoints <= 300:
            return False
        self.ssDormouse = True
        return True

    def ChessyCat_SS_FromBanished(self):
        if self.DefaultCheckWhetherCardIdIsNegated(self.Card.Id):
            return False
        if self.Card.Id != CardId.MalissP_ChessyCat:
            return False
        if self.Card.Location != CardLocation.Removed:
            return False
        if self.enemyActivateLancea:
            return False
        if self.Bot.LifePoints <= 300:
            return False
        self.ssChessyCat = True
        return True

    def SummonLittleKnightFast(self):
        if not (self.Bot.HasInMonstersZone(CardId.LinkSpider) or self.Bot.HasInMonstersZone(CardId.Linguriboh)):
            return False
        if not self.HaveTwoBodies():
            return False
        mats = sorted((c for c in self.Bot.GetMonsters() if c is not None and c.IsFaceup() and c.HasType(CardType.Effect)),
                      key=lambda c: c.Attack)[:2]
        if len(mats) < 2:
            return False
        self.AI.SelectMaterials(mats)
        self.step1Done = True
        return True

    def SPEmer(self):
        if self.Bot.HasInMonstersZone(CardId.FirewallDragon) or \
                self.Bot.HasInMonstersZone(CardId.AlliedCodeTalkerIgnister) or \
                self.Bot.HasInMonstersZone(CardId.Apollousa) or \
                self.Bot.HasInMonstersZone(CardId.AccesscodeTalker):
            return False
        if not self.HaveTwoBodies():
            return False
        mats = self.PickLinkMatsMinCount(
            targetLink=2,
            isEligible=lambda m: m.HasType(CardType.Effect),
            minCount=2,
            maxCount=2,
            avoidIds=[CardId.Apollousa, CardId.AlliedCodeTalkerIgnister, CardId.AccesscodeTalker])
        if len(mats) != 2:
            return False
        self.AI.SelectMaterials(mats)
        return True

    def GoldSarc_StartPiece(self):
        if self.CheckSpellWillBeNegate():
            return False
        if self.enemyActivateLancea:
            return False
        if self.Bot.HasInHand(CardId.MalissP_Dormouse) or self.Bot.HasInHand(CardId.MalissP_WhiteRabbit):
            return False
        if not self.Bot.HasInMonstersZone(CardId.MalissP_Dormouse) and self.Bot.HasInDeck(CardId.MalissP_Dormouse) and \
                not self.ssDormouse:
            pick = CardId.MalissP_Dormouse
        elif not self.Bot.HasInMonstersZone(CardId.MalissP_WhiteRabbit) and self.Bot.HasInDeck(CardId.MalissP_WhiteRabbit) \
                and not self.ssWhiteRabbit:
            pick = CardId.MalissP_WhiteRabbit
        elif self.madeIt3 and not self.ssChessyCat:
            pick = CardId.MalissP_ChessyCat
        else:
            return False
        if pick == 0:
            return False
        self.AI.SelectCard(pick)
        if self.Card.Location == CardLocation.Hand:
            self.SelectSTPlace(self.Card, True)
        self.goldstart = True
        return True

    def ExistsForUnderground(self, id_):
        return self.Bot.HasInDeck(id_) or self.Bot.HasInHand(id_) or self.Bot.HasInGraveyard(id_)

    def Underground_ActivateStarter(self):
        if self.enemyActivateLancea:
            return False
        if self.Bot.GetMonsterCount() != 0:
            return False
        if self.step1Done:
            return False
        pick = 0
        if self.ExistsForUnderground(CardId.MalissP_Dormouse):
            pick = CardId.MalissP_Dormouse
        elif self.ExistsForUnderground(CardId.MalissP_WhiteRabbit):
            pick = CardId.MalissP_WhiteRabbit
        elif self.ExistsForUnderground(CardId.MalissP_ChessyCat):
            pick = CardId.MalissP_ChessyCat
        if pick == 0:
            return False
        self.AI.SelectYesNo(True)
        self.AI.SelectCard(pick)
        self.ActiveUnderground = True
        self.undergroundstart = True
        return True

    def Terra_GrabUnderground(self):
        if self.DefaultCheckWhetherCardIdIsNegated(self.Card.Id):
            return False
        if self.CheckSpellWillBeNegate():
            return False
        if self.ActiveUnderground:
            return False
        if self.Bot.HasInHand(CardId.MalissInUnderground) or self.Bot.HasInSpellZone(CardId.MalissInUnderground):
            return False
        self.AI.SelectCard(CardId.MalissInUnderground)
        if self.Card.Location == CardLocation.Hand:
            self.SelectSTPlace(self.Card, True)
        return True

    def HaveBackupOrWizardInHand(self):
        return self.Bot.HasInHand(CardId.BackupIgnister) or self.Bot.HasInHand(CardId.WizardIgnister)

    def HaveMHInHand(self):
        return self.Bot.HasInHand(CardId.MalissP_MarchHare)

    def IsMalissBody(self, c):
        return c is not None and c.IsFaceup() and c.HasSetcode(self.SetcodeMaliss) and \
            c.IsCode(CardId.MalissP_Dormouse, CardId.MalissP_WhiteRabbit, CardId.MalissP_ChessyCat, CardId.MalissP_MarchHare)

    def Emergency_NormalCat(self):
        if self.Bot.GetMonsterCount() != 0:
            return False
        if self.usedNormalSummon:
            return False
        if self.Bot.HasInHand(CardId.MalissP_Dormouse) or self.Bot.HasInHand(CardId.MalissP_WhiteRabbit) or \
                self.Bot.HasInHand(CardId.MalissInUnderground) or self.Bot.HasInHand(CardId.TERRAFORMING) or \
                self.Bot.HasInHand(CardId.GoldSarcophagus):
            return False
        if not self.HaveMHInHand():
            return False
        self.usedNormalSummon = True
        return True

    def OneBody_Link1_Linguriboh(self):
        if not self.HaveBackupOrWizardInHand():
            return False
        if self.Bot.HasInMonstersZone(CardId.Linguriboh):
            return False
        if self.Bot.GetMonsterCount() != 1:
            return False
        return True

    def OneBody_Link1_Almiraj(self):
        if not self.HaveBackupOrWizardInHand():
            return False
        if self.Bot.HasInMonstersZone(CardId.SALAMANGREAT_ALMIRAJ):
            return False
        if self.Bot.GetMonsterCount() != 1:
            return False
        return True

    def OneBody_Backup_SS(self):
        if self.DefaultCheckWhetherCardIdIsNegated(self.Card.Id):
            return False
        haveLinkAnchor = self.Bot.HasInMonstersZone(CardId.Linguriboh) or self.Bot.HasInMonstersZone(CardId.SplashMage)
        if not haveLinkAnchor:
            return False
        if self.Card.Location != CardLocation.Hand:
            return False
        self.avoidLinkedZones = True
        return True

    def OneBody_Backup_SearchWizard(self):
        if self.DefaultCheckWhetherCardIdIsNegated(self.Card.Id):
            return False
        if not self.Card.IsCode(CardId.BackupIgnister):
            return False
        if len(self.Bot.Hand) == 0:
            return False
        haveWizard = self.Bot.HasInHand(CardId.WizardIgnister)

        if haveWizard and self.Bot.HasInDeck(CardId.MalissP_MarchHare) and len(self.Bot.Hand) > 0:
            searchId = CardId.MalissP_MarchHare
        elif self.Bot.HasInDeck(CardId.MalissP_Dormouse) and self.nsplan and \
                self.Bot.HasInMonstersZone(CardId.SALAMANGREAT_ALMIRAJ):
            searchId = CardId.MalissP_Dormouse
        elif self.Bot.HasInDeck(CardId.MalissP_WhiteRabbit) and self.nsBackupplan:
            searchId = CardId.MalissP_WhiteRabbit
        elif not haveWizard and self.Bot.HasInDeck(CardId.WizardIgnister) and len(self.Bot.Hand) > 0:
            searchId = CardId.WizardIgnister
        elif self.Bot.HasInDeck(CardId.MalissP_WhiteRabbit):
            searchId = CardId.MalissP_WhiteRabbit
        else:
            return False

        self.AI.SelectCard(searchId)

        hand = [h for h in self.Bot.Hand if h is not None]
        candidates = [h for h in hand if h.Id != CardId.WizardIgnister]
        discards = []
        if searchId == CardId.MalissP_Dormouse:
            discards.extend(c for c in candidates if c.Id == CardId.MalissP_Dormouse)

        def OthersExcludingTarget():
            if searchId == CardId.MalissP_MarchHare:
                return [c for c in candidates if c.Id != CardId.MalissP_MarchHare]
            return candidates

        othersExcludingTarget = list(OthersExcludingTarget())
        groups = {}
        for c in othersExcludingTarget:  # GroupBy: groups in first-appearance order
            groups.setdefault(c.Id, []).append(c)
        dupGroups = [(k, g) for k, g in groups.items() if len(g) >= 2]

        for _, g in dupGroups:
            discards.extend(g)

        lowValueSinglesOrder = [CardId.NibiruThePrimalBeing, CardId.Lancea, CardId.TERRAFORMING, CardId.GoldSarcophagus]
        for id_ in lowValueSinglesOrder:
            discards.extend(c for c in othersExcludingTarget if c.Id == id_ and all(k != id_ for k, _ in dupGroups))

        already = set(discards)
        discards.extend(c for c in othersExcludingTarget if c not in already)

        discards = list(dict.fromkeys(c for c in discards if c is not None))

        if searchId == CardId.MalissP_Dormouse:
            self.AI.SelectNextCard(searchId)
        if searchId == CardId.MalissP_WhiteRabbit:
            self.AI.SelectNextCard(searchId)
        elif discards is not None:
            self.AI.SelectNextCard(discards)
        else:
            return False

        self.avoidLinkedZones = True
        if self.Bot.HasInMonstersZone(CardId.Linguriboh):
            self.blockWicckid = True
        return True

    def OneBody_Wizard_SS(self):
        if self.DefaultCheckWhetherCardIdIsNegated(self.Card.Id):
            return False
        if not self.Bot.HasInMonstersZone(CardId.Linguriboh) and not self.Bot.HasInMonstersZone(CardId.SALAMANGREAT_ALMIRAJ):
            return False
        if self.Card.Location != CardLocation.Hand:
            return False
        revive = self.PickGYCybersePriority()
        if revive is None:
            return False
        self.avoidLinkedZones = True
        self.blockWicckid = True
        self.AI.SelectCard(revive)
        return True

    def PickGYCybersePriority(self):
        m = self.PickGYMalissPriority()
        if m is not None:
            return m
        list_ = GetMatchingCards(self.Bot.Graveyard, lambda c: c is not None and c.IsMonster() and
                                 c.HasRace(CardRace.Cyberse) and c.Level <= 4)
        return list_[0] if list_ else None

    def PickGYMalissPriority(self):
        pref = [CardId.MalissP_Dormouse, CardId.MalissP_WhiteRabbit, CardId.MalissP_ChessyCat, CardId.MalissP_MarchHare]
        for id_ in pref:
            c = GetFirstMatchingCard(self.Bot.Graveyard, lambda g: g.IsCode(id_) and g.IsMonster())
            if c is not None:
                return c
        return None

    def TwoCC_NormalSummon(self):
        if self.usedNormalSummon:
            return False
        if self.Bot.GetMonsterCount() != 0:
            return False
        haveOtherStarter = self.Bot.HasInHand(CardId.MalissP_Dormouse) or \
            self.Bot.HasInHand(CardId.MalissP_WhiteRabbit) or \
            self.Bot.HasInHand(CardId.GoldSarcophagus) or \
            self.Bot.HasInHand(CardId.MalissInUnderground)
        if haveOtherStarter:
            return False
        if len(GetMatchingCards(self.Bot.Hand, lambda c: c is not None and c.IsCode(CardId.MalissP_ChessyCat))) >= 2:
            self.usedNormalSummon = True
            return True
        return False

    def IsMalissCost(self, card):
        if card is None:
            return False
        if card.IsCode(CardId.MalissP_ChessyCat):
            return True
        if card.IsCode(CardId.MalissP_WhiteRabbit) and self.NSDorMouse and not self.ssWhiteRabbit:
            return True
        if card.IsCode(CardId.MalissP_WhiteRabbit) and self.ssWhiteRabbit:
            return True
        if card.IsCode(CardId.MalissP_Dormouse) and self.ssDormouse:
            return True
        if card.IsCode(CardId.MalissP_MarchHare) and self.ActiveMarchHare:
            return True
        return False

    def IsMalissCost2(self, card):
        if card is None:
            return False
        return card.IsCode(CardId.MalissP_ChessyCat) or card.IsCode(CardId.MalissP_WhiteRabbit) or \
            card.IsCode(CardId.MalissP_MarchHare) or card.IsCode(CardId.MalissInUnderground)

    def AnyDraw(self):
        if self.DefaultCheckWhetherCardIdIsNegated(self.Card.Id):
            return False
        if self.Card.Id != CardId.MalissP_ChessyCat:
            return False
        if self.Card.Location != CardLocation.MonsterZone:
            return False
        if self.CheckWhetherNegated():
            return False
        target = next((c for c in self.Bot.Hand if c is not None and c.IsCode(CardId.MalissInTheMirror)), None)
        if target is None:
            target = next((c for c in self.Bot.Hand if self.IsMalissCost(c)), None)
        if target is None:
            groups = {}
            for c in self.Bot.Hand:
                if self.IsMalissCost2(c):
                    groups.setdefault(c.Id, []).append(c)
            malissDupGroup = next((g for g in groups.values() if len(g) >= 2), None)
            if malissDupGroup is not None:
                target = malissDupGroup[0]
        if target is None:
            return False
        self.AI.SelectCard(target)
        return True

    def PickTB11CostCandidateId(self):
        field = [c for c in self.Bot.GetMonsters() if c is not None and c.IsFaceup() and c.HasSetcode(self.SetcodeMaliss)]
        field = [c for c in field if
                 not (c.IsCode(CardId.MalissP_WhiteRabbit) and self.ssWhiteRabbit) and
                 not (c.IsCode(CardId.MalissP_ChessyCat) and self.ssChessyCat) and
                 not (c.IsCode(CardId.MalissP_MarchHare) and self.ssMarchHare) and
                 not (c.IsCode(CardId.MalissP_Dormouse) and self.ssDormouse) and
                 not (c.IsCode(CardId.MalissQ_RedRansom) and self.ssRRThisTurn) and
                 not (c.IsCode(CardId.MalissQ_WhiteBinder) and self.ssWBThisTurn) and
                 not (c.IsCode(CardId.MalissQ_HeartsCrypter) and self.ssHCThisTurn)]
        pref = [CardId.MalissP_WhiteRabbit, CardId.MalissP_ChessyCat, CardId.MalissP_MarchHare, CardId.MalissP_Dormouse,
                CardId.MalissQ_RedRansom, CardId.MalissQ_WhiteBinder, CardId.MalissQ_HeartsCrypter]
        for id_ in pref:
            if any(c.IsCode(id_) for c in field):
                return id_
        return 0

    def PickPFromGYForSplash(self):
        if self.enemyActivateLancea:
            pref2 = [CardId.MalissP_Dormouse, CardId.MalissP_WhiteRabbit, CardId.MalissP_ChessyCat, CardId.MalissP_MarchHare,
                     CardId.BackupIgnister, CardId.WizardIgnister]
            for id_ in pref2:
                if self.Bot.HasInGraveyard(id_):
                    return id_
        pref = [CardId.MalissP_Dormouse, CardId.MalissP_WhiteRabbit, CardId.MalissP_ChessyCat, CardId.MalissP_MarchHare]
        for id_ in pref:
            if self.Bot.HasInGraveyard(id_):
                return id_
        return 0

    def HaveUndergroundOnHandOrField(self):
        return self.Bot.HasInHand(CardId.MalissInUnderground) or self.Bot.HasInSpellZone(CardId.MalissInUnderground)

    def ShouldSearchUnderground(self):
        if self.ActiveUnderground:
            return False
        if self.HaveUndergroundOnHandOrField():
            return False
        return self.Bot.HasInDeck(CardId.MalissInUnderground)

    def Step2_RedRansom_Search(self):
        if self.DefaultCheckWhetherCardIdIsNegated(self.Card.Id):
            return False
        chooseId = 0
        shouldUG = self.ShouldSearchUnderground()
        if shouldUG:
            chooseId = CardId.MalissInUnderground
        elif self.Bot.HasInDeck(CardId.MalissInTheMirror):
            chooseId = CardId.MalissInTheMirror
        if chooseId == 0:
            return False
        # the searched card is picked in OnSelectCard
        self.step2Done = True
        self.avoidLinkedZones = False
        return True

    def PickMaterialsForRedRansom(self):
        splash = next((c for c in self.Bot.MonsterZone if c is not None and c.IsFaceup() and c.IsCode(CardId.SplashMage)), None)
        if splash is None:
            return []
        revived = None
        if self.lastRevivedIdBySplash != 0:
            revived = next((c for c in self.Bot.MonsterZone if c is not None and c.IsFaceup() and
                            c.IsCode(self.lastRevivedIdBySplash)), None)
        if revived is None:
            revived = next((c for c in self.Bot.MonsterZone if c is not None and c.IsFaceup() and c.HasSetcode(0x1b9) and
                            c != splash and not c.HasType(CardType.Link)), None)
        if revived is None:
            return []
        return [splash, revived]

    def Step2_SplashMage_ReviveP(self):
        if self.DefaultCheckWhetherCardIdIsNegated(self.Card.Id):
            return False
        if self.step2Done:
            return False
        if not self.Bot.HasInMonstersZone(CardId.SplashMage):
            return False
        pick = self.PickPFromGYForSplash()
        if pick == 0:
            return False
        self.AI.SelectCard(pick)
        self.lastRevivedIdBySplash = pick
        return True

    def Step2N_SplashMage_ReviveP(self):
        if self.DefaultCheckWhetherCardIdIsNegated(self.Card.Id):
            return False
        if not self.Bot.HasInMonstersZone(CardId.SplashMage):
            return False
        pick = self.PickPFromGYForSplash()
        if pick == 0:
            return False
        self.AI.SelectCard(pick)
        self.lastRevivedIdBySplash = pick
        return True

    def Step2_LinkSummon_RedRansom(self):
        if self.step2Done:
            return False
        mats = self.PickMaterialsForRedRansom()
        if len(mats) != 2:
            return False
        if GetBotAvailZonesFromExtraDeck(self.Util, mats) == 0:
            return False
        self.AI.SelectMaterials(mats)
        self.madeIt3 = True
        return True

    def Step2N_LinkSummon_WB(self):
        mats = self.PickMaterialsForRedRansom()
        if len(mats) != 2:
            return False
        if GetBotAvailZonesFromExtraDeck(self.Util, mats) == 0:
            return False
        self.AI.SelectMaterials(mats)
        return True

    def Step2N_LinkSummon_RedRansom(self):
        if not self.Bot.HasInMonstersZone(CardId.MalissP_MarchHare) or self.Bot.GetMonsterCount() < 3:
            return False
        self.madeIt3 = True
        return True

    def Step2_Fallback_Wizard_AfterSplashNegated(self):
        if self.DefaultCheckWhetherCardIdIsNegated(self.Card.Id):
            return False
        if not self.splashNegatedThisTurn:
            return False
        if self.Card.Location != CardLocation.Hand:
            return False
        revive = self.PickGYMalissPriority()
        if revive is None:
            return False
        self.avoidLinkedZones = True
        self.blockWicckid = True
        self.AI.SelectCard(revive)
        return True

    def Step2_Fallback_Backup_AfterSplashNegated(self):
        if self.DefaultCheckWhetherCardIdIsNegated(self.Card.Id):
            return False
        if not self.splashNegatedThisTurn:
            return False
        if self.Card.Location != CardLocation.Hand:
            return False
        if self.GetMMZCount() >= 5:
            return False
        want = CardId.WizardIgnister if not self.Bot.HasInHand(CardId.WizardIgnister) and \
            self.Bot.HasInDeck(CardId.WizardIgnister) else \
            (CardId.MalissP_MarchHare if self.Bot.HasInDeck(CardId.MalissP_MarchHare) else 0)
        if want == 0:
            return False
        self.AI.SelectCard(want)
        discard = next((h for h in self.Bot.Hand if h is not None and h.Id != CardId.WizardIgnister and h != self.Card), None)
        if discard is not None:
            self.AI.SelectNextCard(discard)
        self.avoidLinkedZones = True
        self.blockWicckid = True
        return True

    # ==================== FLOW 3: Core -> Results (UG / Mirror / TP11 -> Make it 3!! -> Finishers) ====================
    def HaveUG(self):
        return self.Bot.HasInHand(CardId.MalissInUnderground) or self.Bot.HasInSpellZone(CardId.MalissInUnderground)

    def HasSelfSSAvailable(self, id_):
        if id_ == CardId.MalissP_Dormouse:
            return not self.ssDormouse
        if id_ == CardId.MalissP_WhiteRabbit:
            return not self.ssWhiteRabbit
        if id_ == CardId.MalissP_ChessyCat:
            return not self.ssChessyCat
        if id_ == CardId.MalissP_MarchHare:
            return not self.ActiveMarchHare
        return True

    def PickUG_DHG_DormouseFirst(self):
        pref = [CardId.MalissP_Dormouse, CardId.MalissP_WhiteRabbit, CardId.MalissP_ChessyCat, CardId.MalissP_MarchHare]
        for id_ in pref:
            if not self.HasSelfSSAvailable(id_):
                continue
            if self.ExistsForUnderground(id_):
                return id_
        return 0

    def Flow3_UnderGround_Available_SSAnyPawn(self):
        if not self.step2Done:
            return False
        if not self.HaveUG():
            return False
        if self.Card.Id != CardId.MalissInUnderground:
            return False
        if self.resultSuccessFlag:
            return False
        if self.GetMMZCount() >= 5:
            self.AI.SelectYesNo(False)
            return True
        if self.enemyActivateLancea:
            self.AI.SelectYesNo(False)
            return True
        if self.Bot.HasInDeck(CardId.MalissInTheMirror) and self.nsplan:
            pick = CardId.MalissInTheMirror
        elif self.Bot.HasInDeck(CardId.MalissInTheMirror) and self.NSDorMouse:
            pick = CardId.MalissInTheMirror
        else:
            pick = self.PickUG_DHG_DormouseFirst()
        if pick == 0:
            self.AI.SelectYesNo(False)
            return True
        self.AI.SelectYesNo(True)
        self.AI.SelectCard(pick)
        self.resultSuccessFlag = True
        return True

    def Mirror_Banish(self):
        if self.DescIs(CardId.MalissInTheMirror, 1):
            gy = self.PickMirrorGYTargetForSearch()
            if gy is None:
                return False
            self.AI.SelectCard(gy)
            wants = self.Mirror_SearchOrderForType(False, gy.IsMonster())
            self.AI.SelectNextCard(wants)
            return True

        if self.CheckSpellWillBeNegate():
            return False
        if self.CheckWhetherNegated():
            return False
        cost = self.PickMirrorCostCandidate()
        if cost is None:
            return False
        for m in self.Enemy.GetMonsters():
            if m.IsMonsterShouldBeDisabledBeforeItUseEffect() and not m.IsDisabled() and self.Duel.LastChainPlayer != 0:
                if self.Card.Location == CardLocation.Hand:
                    self.SelectSTPlace(self.Card, True)
                self.AI.SelectCard(m)
                self.AI.SelectNextCard(cost)
                return True
        LastChainCard = self.Util.GetLastChainCard()
        if LastChainCard is None or LastChainCard.Controller != 1 or LastChainCard.Location != CardLocation.MonsterZone \
                or LastChainCard.IsDisabled() or LastChainCard.IsShouldNotBeTarget() or \
                LastChainCard.IsShouldNotBeSpellTrapTarget():
            return False
        if self.Card.Location == CardLocation.Hand:
            self.SelectSTPlace(self.Card, True)
        if LastChainCard is not None:
            self.AI.SelectCard(LastChainCard)
        else:
            enemyMonsters = sorted(self.Enemy.GetMonsters(), key=CompareCardAttack)
            enemyMonsters.reverse()
            for card in enemyMonsters:
                if card.IsFaceup() and not card.IsShouldNotBeTarget() and not card.IsShouldNotBeSpellTrapTarget():
                    self.AI.SelectCard(card)
        self.AI.SelectNextCard(cost)
        return True

    def Flow3_Link_Accesscode(self):
        if self.Bot.HasInExtra(CardId.AlliedCodeTalkerIgnister):
            return False
        if self.BlockAccesscodeOnT1():
            return False
        avoid = [CardId.AlliedCodeTalkerIgnister, CardId.FirewallDragon]
        mats = self.PickLinkMatsMinCount(
            targetLink=4,
            isEligible=lambda m: m.HasType(CardType.Effect),
            minCount=2,
            maxCount=4,
            avoidIds=avoid)
        if len(mats) < 2:
            return False
        self.AI.SelectMaterials(mats)
        return True

    def Flow3_BackupIgnister_AfterMakeIt3(self):
        if self.DefaultCheckWhetherCardIdIsNegated(self.Card.Id):
            return False
        if not self.madeIt3:
            return False
        if self.Card.Location != CardLocation.Hand:
            return False
        self.avoidLinkedZones = True
        return True

    def Flow3_WizardIgnister_AfterMakeIt3(self):
        if self.DefaultCheckWhetherCardIdIsNegated(self.Card.Id):
            return False
        if not self.madeIt3:
            return False
        if self.Card.Location != CardLocation.Hand:
            return False
        revive = self.PickGYMalissPriority()
        if revive is None:
            return False
        self.avoidLinkedZones = True
        self.AI.SelectCard(revive)
        return True

    def RR_SS_FromBanished(self):
        if self.DefaultCheckWhetherCardIdIsNegated(self.Card.Id):
            return False
        if self.Card.Id != CardId.MalissQ_RedRansom:
            return False
        if self.Card.Location != CardLocation.Removed:
            return False
        if self.GetMMZCount() >= 5:
            return False
        if self.Bot.LifePoints <= 900:
            return False
        pickId = 0
        pawnOrder = [CardId.MalissP_ChessyCat, CardId.MalissP_MarchHare, CardId.MalissP_WhiteRabbit, CardId.MalissP_Dormouse]
        for id_ in pawnOrder:
            if self.Bot.HasInDeck(id_) and self.PawnSelfSS_AvailableId(id_):
                pickId = id_
                break
        canBanish = pickId != 0
        self.AI.SelectYesNo(canBanish)
        if canBanish:
            self.AI.SelectCard(pickId)
        self._rrSelfSSPlacing = True
        self.ssRRThisTurn = True
        return True

    def Wicckid_SearchTuner(self):
        if self.DefaultCheckWhetherCardIdIsNegated(self.Card.Id):
            return False
        if not self.Bot.HasInDeck(CardId.BackupIgnister):
            return False
        cost = self.PickGYCyberseForWicckidCost_Safe()
        if cost is None:
            return False
        self.AI.SelectCard(cost)
        self.AI.SelectNextCard(CardId.BackupIgnister)
        self.avoidLinkedZones = False
        return True

    def LinkDecoder_ReviveFromGY(self):
        if self.DefaultCheckWhetherCardIdIsNegated(self.Card.Id):
            return False
        if self.Card.Location != CardLocation.Grave:
            return False
        if self.Allied_End:
            return False
        return True

    def Transcode_ReviveLink3OrLower(self):
        if self.DefaultCheckWhetherCardIdIsNegated(self.Card.Id):
            return False
        if self.Card.Location != CardLocation.MonsterZone:
            return False
        prefer = GetFirstMatchingCard(self.Bot.Graveyard, lambda c: c.IsCode(CardId.CyberseWicckid)) or \
            GetFirstMatchingCard(self.Bot.Graveyard, lambda c: c.IsCode(CardId.SplashMage)) or \
            GetFirstMatchingCard(self.Bot.Graveyard, lambda c: c.IsCode(CardId.MalissQ_RedRansom)) or \
            GetFirstMatchingCard(self.Bot.Graveyard, lambda c: c.IsCode(CardId.MalissQ_WhiteBinder)) or \
            _max_by(GetMatchingCards(self.Bot.Graveyard, lambda c: c.IsMonster() and c.HasType(CardType.Link) and
                                     c.LinkCount <= 3 and not c.IsCode(CardId.TranscodeTalker)),
                    key=lambda c: c.Attack)
        if prefer is None:
            return False
        self.AI.SelectCard(prefer)
        self.avoidLinkedZones = False
        return True

    def Allied_NegateBanish(self):
        if self.DefaultCheckWhetherCardIdIsNegated(self.Card.Id):
            return False
        if self.CheckWhetherNegated(True) or not self.CheckLastChainShouldNegated():
            return False
        allied = GetFirstMatchingCard(self.Bot.MonsterZone, lambda m: m is not None and m.IsCode(CardId.AlliedCodeTalkerIgnister))
        if allied is None or allied.IsDisabled():
            return False
        haveAnyLink = any(m is not None and m.HasType(CardType.Link) and not m.IsCode(CardId.AlliedCodeTalkerIgnister)
                          for m in self.Bot.GetMonsters())
        if not haveAnyLink:
            return False
        cheapLinks = [CardId.CyberseWicckid, CardId.MalissQ_WhiteBinder, CardId.TranscodeTalker, CardId.MalissQ_RedRansom]
        self.AI.SelectCard(list(cheapLinks))
        return True

    def GetWicckid(self):
        return GetFirstMatchingFaceupCard(self.Bot.MonsterZone, lambda c: c is not None and c.IsCode(CardId.CyberseWicckid))

    def GetLinkedMaskFor(self, link):
        if link is None or not link.IsFaceup() or not link.HasType(CardType.Link):
            return 0
        return link.GetLinkedZones() & 0x1F

    def PawnSelfSS_AvailableId(self, id_):
        if id_ == CardId.MalissP_Dormouse:
            return not self.ssDormouse
        if id_ == CardId.MalissP_WhiteRabbit:
            return not self.ssWhiteRabbit
        if id_ == CardId.MalissP_ChessyCat:
            return not self.ssChessyCat
        if id_ == CardId.MalissP_MarchHare:
            return not self.ActiveMarchHare
        return False

    def QueenSelfSS_AvailableId(self, id_):
        if id_ == CardId.MalissQ_HeartsCrypter:
            return not self.ssHCThisTurn
        if id_ == CardId.MalissQ_WhiteBinder:
            return not self.ssWBThisTurn
        if id_ == CardId.MalissQ_RedRansom:
            return not self.ssRRThisTurn
        return False

    def Dormouse_Banish_Anytime(self):
        if self.DefaultCheckWhetherCardIdIsNegated(self.Card.Id):
            return False
        if self.Card.Id != CardId.MalissP_Dormouse:
            return False
        if self.Card.Location != CardLocation.MonsterZone:
            return False
        if self.DefaultCheckWhetherCardIsNegated(self.Card):
            return False
        if self.enemyActivateLancea:
            return False
        if not self.HasFreeMMZ():
            return False
        pick = 0
        if self.Bot.HasInDeck(CardId.MalissP_WhiteRabbit) and self.PawnSelfSS_AvailableId(CardId.MalissP_WhiteRabbit):
            pick = CardId.MalissP_WhiteRabbit
        elif self.Bot.HasInDeck(CardId.MalissP_ChessyCat) and self.PawnSelfSS_AvailableId(CardId.MalissP_ChessyCat):
            pick = CardId.MalissP_ChessyCat
        if pick == 0:
            return False
        self.AI.SelectCard(pick)
        return True

    def IsCyberse(self, c):
        return c is not None and c.HasType(CardType.Monster) and c.HasRace(CardRace.Cyberse)

    def RR_HOPT_Spent_ThisTurn(self):
        return self.ssRRThisTurn

    def RR_CanStillSS_ThisTurn(self):
        if self.RR_HOPT_Spent_ThisTurn():
            return False
        return True

    def Score_WicckidCost(self, c):
        if c is None:
            return -2 ** 31
        if c.IsCode(CardId.MalissQ_RedRansom) and self.RR_HOPT_Spent_ThisTurn():
            return -999
        if c.IsCode(CardId.MalissQ_RedRansom) and self.RR_CanStillSS_ThisTurn():
            return 1000
        if c.IsCode(CardId.Linguriboh) or c.IsCode(CardId.SALAMANGREAT_ALMIRAJ):
            return 120
        if c.IsCode(CardId.MalissP_Dormouse) and self.ssDormouse:
            return 90
        if c.IsCode(CardId.MalissP_WhiteRabbit) and self.ssWhiteRabbit:
            return 70
        if c.IsCode(CardId.MalissP_ChessyCat) and self.ssChessyCat:
            return 60
        if c.IsCode(CardId.MalissP_MarchHare) and self.ssMarchHare:
            return 60
        if c.IsCode(CardId.BackupIgnister):
            return 20
        if c.IsCode(CardId.WizardIgnister):
            return 20
        return 30

    def PickGYCyberseForWicckidCost_Safe(self):
        gy = [c for c in (self.Bot.Graveyard or []) if self.IsCyberse(c)]
        if len(gy) == 0:
            return None
        best = None
        bestScore = -2 ** 31
        for c in gy:
            sc = self.Score_WicckidCost(c)
            if sc > bestScore:
                best = c
                bestScore = sc
        return best

    def BlockAccesscodeOnT1(self):
        blocked = self.Duel.Player == 0 and self.Duel.Turn == 1
        return blocked

    def Allied_OnSummonTrigger(self):
        if self.DefaultCheckWhetherCardIdIsNegated(self.Card.Id):
            return False
        me = GetFirstMatchingCard(self.Bot.MonsterZone, lambda m: m is not None and m.IsCode(CardId.AlliedCodeTalkerIgnister))
        if me is None:
            return False
        has2300 = any(c is not None and c.IsMonster() and c.HasRace(CardRace.Cyberse) and c.Attack == 2300
                      for c in self.Bot.Graveyard)
        if not has2300:
            return False
        prefer = [CardId.MalissQ_RedRansom, CardId.MalissQ_WhiteBinder, CardId.TranscodeTalker]
        self.AI.SelectCard(list(prefer))
        return True

    def ShouldSummonTranscode(self):
        haveSplashGY = self.Bot.HasInGraveyard(CardId.SplashMage)
        haveRR = self.Bot.HasInMonstersZone(CardId.MalissQ_RedRansom)
        haveL1 = self.Bot.HasInMonstersZone(CardId.LinkDecoder) or self.Bot.HasInGraveyard(CardId.LinkDecoder)
        return haveSplashGY and (haveRR or haveL1)

    def Step_SplashToRR(self):
        if self._didSplashToRR:
            return False
        if self.Bot.HasInMonstersZone(CardId.LinkDecoder):
            return False
        if not self.Bot.HasInExtra(CardId.MalissQ_RedRansom):
            return False
        mats = self.PickLinkMatsMinCount(
            targetLink=2,
            isEligible=lambda m: m.HasType(CardType.Effect),
            minCount=2,
            maxCount=2,
            avoidIds=[CardId.CyberseWicckid])
        if len(mats) == 0:
            return False
        self.AI.SelectMaterials(mats)
        self._didSplashToRR = True
        return True

    def Step_SplashToWB(self):
        if self._didSplashToRR:
            return False
        if not self.Bot.HasInExtra(CardId.MalissQ_WhiteBinder):
            return False
        mats = self.PickLinkMatsMinCount(
            targetLink=2,
            isEligible=lambda m: m.HasType(CardType.Effect),
            minCount=2,
            maxCount=2,
            avoidIds=[CardId.CyberseWicckid])
        if len(mats) == 0:
            return False
        self.AI.SelectMaterials(mats)
        self._didSplashToRR = True
        return True

    def Step_RRtoWicckid(self):
        if self.enemyActivateLancea:
            return False
        if self.blockWicckid:
            return True
        if not self._didSplashToRR or self._didRRtoWicckid:
            return False
        if not self.Bot.HasInExtra(CardId.CyberseWicckid):
            return False
        rr = GetFirstMatchingCard(self.Bot.MonsterZone, lambda m: m is not None and m.IsCode(CardId.MalissQ_RedRansom))
        if rr is None:
            return False
        emzOccupant = next((m for m in self.Bot.GetMonsters() if m is not None and m != rr and self.IsInEMZ(m)), None)
        buddy = emzOccupant if emzOccupant is not None else \
            next((m for m in self.Bot.MonsterZone if m is not None and m != rr), None)
        if buddy is None:
            return False
        emzWillBeFree = self.HasFreeEMZ() or self.IsInEMZ(rr) or self.IsInEMZ(buddy)
        if not emzWillBeFree:
            return False
        self.AI.SelectCard(CardId.CyberseWicckid)
        self.AI.SelectMaterials([rr, buddy])
        self._preferWicckidArrows = True
        self._didRRtoWicckid = True
        return True

    def Step2N_RRtoWicckid(self):
        if self.enemyActivateLancea:
            return False
        if self.blockWicckid:
            return False
        rr = GetFirstMatchingCard(self.Bot.MonsterZone, lambda m: m is not None and m.IsCode(CardId.MalissQ_RedRansom))
        if rr is None:
            return False
        emzOccupant = next((m for m in self.Bot.GetMonsters() if m is not None and m != rr and self.IsInEMZ(m)), None)
        buddy = emzOccupant if emzOccupant is not None else \
            next((m for m in self.Bot.MonsterZone if m is not None and m != rr), None)
        if buddy is None:
            return False
        emzWillBeFree = self.HasFreeEMZ() or self.IsInEMZ(rr) or self.IsInEMZ(buddy)
        if not emzWillBeFree:
            return False
        self.AI.SelectCard(CardId.CyberseWicckid)
        self.AI.SelectMaterials([rr, buddy])
        self._preferWicckidArrows = True
        self._didRRtoWicckid = True
        return True

    def Step_SummonLinkDecoderToWicckid(self):
        if not self._didRRtoWicckid or self._didSummonToWicckidArrow:
            return False
        wic = self.GetWicckid()
        if wic is None:
            return False
        material = next((m for m in self.Bot.GetMonsters()
                         if m is not None and m != wic and m.IsFaceup() and m.HasRace(CardRace.Cyberse) and m.Level <= 4
                         and not m.HasType(CardType.Link | CardType.Xyz)
                         and any((self.GetLinkedMaskFor(wic) & (1 << seq)) != 0 and
                                 (self.Bot.MonsterZone[seq] is None or self.Bot.MonsterZone[seq] == m)
                                 for seq in range(5))), None)
        if material is None:
            return False
        self.AI.SelectMaterials([material])
        self._preferWicckidArrows = True
        self.avoidLinkedZones = False
        return True

    def Step1_SSLinkDecoder(self):
        if (self.Bot.HasInMonstersZone(CardId.MalissP_Dormouse) or
                self.Bot.HasInMonstersZone(CardId.MalissP_WhiteRabbit) or
                self.Bot.HasInMonstersZone(CardId.MalissP_ChessyCat) or
                self.Bot.HasInMonstersZone(CardId.BackupIgnister)) and self.Bot.GetMonsterCount() == 1 and \
                self.Bot.HasInHand(CardId.MalissP_MarchHare):
            return True
        return False

    def IsMalissMonster(self, c):
        return c is not None and c.IsMonster() and c.HasSetcode(0x1b9)

    def CanMakeLinkNWithFlexibleTwo(self, a, b, target):
        a1, aL = 1, (max(1, a.LinkCount) if (a is not None and a.HasType(CardType.Link)) else 1)
        b1, bL = 1, (max(1, b.LinkCount) if (b is not None and b.HasType(CardType.Link)) else 1)
        return (a1 + b1 == target) or (a1 + bL == target) or (aL + b1 == target) or (aL + bL == target)

    def Step_WicckidPlusOneToWB(self):
        WB_LINK = 3
        if not self.Bot.HasInExtra(CardId.MalissQ_WhiteBinder):
            return False
        wic = self.GetWicckid()
        if wic is not None:
            partners = [m for m in self.Bot.GetMonsters()
                        if m is not None and m.IsFaceup() and m != wic and m.HasType(CardType.Effect)]

            def okPair(p):
                return (self.IsMalissMonster(p) or self.IsMalissMonster(wic)) and \
                    self.CanMakeLinkNWithFlexibleTwo(wic, p, WB_LINK)

            p2 = next((p for p in partners if not p.IsCode(CardId.MalissQ_RedRansom) and okPair(p)), None)
            if p2 is None:
                p2 = next((p for p in partners if p.IsCode(CardId.MalissQ_RedRansom) and okPair(p)), None)
            if p2 is not None:
                self.AI.SelectMaterials([wic, p2])
                return True
        mats = self.PickLinkMatsMinCount(
            targetLink=WB_LINK,
            isEligible=lambda m: m.HasType(CardType.Effect),
            minCount=2,
            maxCount=3,
            avoidIds=[CardId.Apollousa, CardId.FirewallDragon, CardId.AlliedCodeTalkerIgnister],
            requireMaliss=True)
        if len(mats) == 0:
            return False
        self.AI.SelectMaterials(mats)
        return True

    def ssFromHandMH(self):
        if self.DefaultCheckWhetherCardIdIsNegated(self.Card.Id):
            return False
        if self.Card.Location != CardLocation.Hand:
            return False
        if self.GetMMZCount() > 3:
            return False
        if self.enemyActivateLancea:
            return False
        if self.Duel.Player == 0:
            gy = GetMatchingCards(self.Bot.Graveyard, lambda c: c is not None and c.HasSetcode(0x1b9) and c != self.Card)

            def pickP1(src):
                pref = [CardId.MalissQ_WhiteBinder, CardId.MalissQ_HeartsCrypter, CardId.MalissQ_RedRansom]
                for id_ in pref:
                    c = next((x for x in src if x.HasType(CardType.Monster) and x.Id == id_ and
                              self.QueenSelfSS_AvailableId(x.Id)), None)
                    if c is not None:
                        return c
                return next((x for x in src if x.HasType(CardType.Monster) and self.QueenSelfSS_AvailableId(x.Id)), None)

            pick = pickP1(gy)
            if pick is None:
                return False
            self.AI.SelectCard(pick)
            self.ssMarchHare = True
            return self.DontSelfNG()
        else:
            if self.Bot.HasInGraveyard(CardId.MalissQ_WhiteBinder) and not self.ssWBThisTurn:
                Target = GetFirstMatchingCard(self.Bot.Graveyard, lambda c: c is not None and c.IsCode(CardId.MalissQ_WhiteBinder))
                if Target is None:
                    return False
                self.AI.SelectCard(Target)
            elif self.Bot.HasInGraveyard(CardId.MalissQ_HeartsCrypter) and not self.ssHCThisTurn:
                Target = GetFirstMatchingCard(self.Bot.Graveyard, lambda c: c is not None and c.IsCode(CardId.MalissQ_HeartsCrypter))
                if Target is None:
                    return False
                self.AI.SelectCard(Target)
            elif self.Bot.HasInGraveyard(CardId.MalissQ_RedRansom) and not self.ssRRThisTurn:
                Target = GetFirstMatchingCard(self.Bot.Graveyard, lambda c: c is not None and c.IsCode(CardId.MalissQ_RedRansom))
                if Target is None:
                    return False
                self.AI.SelectCard(Target)
            else:
                return False
            self.ssMarchHare = True
            return self.DontSelfNG()

    def Step1_MH_FromHand(self):
        if self.DefaultCheckWhetherCardIdIsNegated(self.Card.Id):
            return False
        if self.Card.Location != CardLocation.Hand:
            return False
        if self.Bot.GetMonsterCount() > 1:
            return False
        if self.enemyActivateLancea:
            return False
        for anchor, gyId in ((CardId.MalissP_WhiteRabbit, CardId.MalissC_MTP07),
                             (CardId.LinkDecoder, CardId.MalissP_Dormouse),
                             (CardId.LinkDecoder, CardId.MalissP_WhiteRabbit),
                             (CardId.LinkDecoder, CardId.MalissP_ChessyCat),
                             (CardId.Linguriboh, CardId.MalissP_MarchHare)):
            if self.Bot.HasInMonstersZone(anchor) and self.Bot.HasInGraveyard(gyId):
                target = GetFirstMatchingCard(self.Bot.Graveyard, lambda c: c is not None and c.IsCode(gyId))
                if target is None:
                    return False
                self.AI.SelectCard(target)
                self.ssMarchHare = True
                return self.DontSelfNG()
        return False

    def returnFromBanish(self):
        if self.Bot.LifePoints <= 300:
            return False
        if self.DefaultCheckWhetherCardIdIsNegated(self.Card.Id):
            return False
        if self.Card.Location != CardLocation.Removed:
            return False
        mh = GetFirstMatchingCard(self.Bot.Banished, lambda c: c.IsFaceup() and c.IsCode(CardId.MalissP_MarchHare))
        if mh is None:
            return False
        self.AI.SelectCard(mh)
        self.ActiveMarchHare = True
        return True

    def WB_OnSummon_BanishGY(self):
        if self.DefaultCheckWhetherCardIdIsNegated(self.Card.Id):
            return False
        if self.Card.Location != CardLocation.MonsterZone:
            return False
        MAX_PICKS = 3
        picks = []
        gyFirst = lambda f: GetFirstMatchingCard(self.Bot.Graveyard, f)
        if self.Duel.Player == 0:
            freeMMZ = max(0, 5 - self.GetMMZCount())
            myPawnCount = len(GetMatchingCards(self.Bot.Graveyard, lambda g: self.IsMalissPawn(g)))
            canUseOwnPawn = myPawnCount > 1

            if not self.ActiveMarchHare and canUseOwnPawn:
                mh = gyFirst(lambda g: g.IsCode(CardId.MalissP_MarchHare))
                if mh is not None:
                    picks.append(mh)
            if freeMMZ > 0 and not self.ssRRThisTurn and not self.Allied_End:
                rr = gyFirst(lambda g: g.IsCode(CardId.MalissQ_RedRansom))
                if rr is not None and rr not in picks and not self.ShouldSkipBanishing(rr):
                    picks.append(rr)
                    freeMMZ -= 1
            if freeMMZ > 0 and not self.ssHCThisTurn and not self.Allied_End:
                hc = gyFirst(lambda g: g.IsCode(CardId.MalissQ_HeartsCrypter))
                if hc is not None and hc not in picks and not self.ShouldSkipBanishing(hc):
                    picks.append(hc)
                    freeMMZ -= 1
            if freeMMZ > 0 and not self.ssWhiteRabbit and not self.Allied_End and canUseOwnPawn:
                wr = gyFirst(lambda g: g.IsCode(CardId.MalissP_WhiteRabbit))
                if wr is not None and wr not in picks and not self.ShouldSkipBanishing(wr):
                    picks.append(wr)
                    freeMMZ -= 1
            if freeMMZ > 0 and not self.ssDormouse and not self.Allied_End and canUseOwnPawn:
                dm = gyFirst(lambda g: g.IsCode(CardId.MalissP_Dormouse))
                if dm is not None and dm not in picks and not self.ShouldSkipBanishing(dm):
                    picks.append(dm)
                    freeMMZ -= 1
            if freeMMZ > 0 and not self.ssChessyCat and not self.Allied_End and canUseOwnPawn:
                cc = gyFirst(lambda g: g.IsCode(CardId.MalissP_ChessyCat))
                if cc is not None and cc not in picks and not self.ShouldSkipBanishing(cc):
                    picks.append(cc)
                    freeMMZ -= 1
            if freeMMZ >= 0 and canUseOwnPawn:
                target = gyFirst(lambda g: g.IsCode(CardId.MalissP_ChessyCat) or g.IsCode(CardId.MalissP_Dormouse))
                picks.append(target)

            picks = list(dict.fromkeys(c for c in picks if c is not None))[:MAX_PICKS]

            threats = self.PickEnemyGYThreats(MAX_PICKS - len(picks))
            for t in threats:
                if len(picks) >= MAX_PICKS:
                    break
                if t not in picks:
                    picks.append(t)
        else:
            freeMMZ = max(0, 5 - self.GetMMZCount())
            if not self.Bot.HasInSpellZone(CardId.MalissC_MTP07) and freeMMZ > 0 and not self.ssWhiteRabbit:
                wr = gyFirst(lambda g: g.IsCode(CardId.MalissP_WhiteRabbit))
                if wr is not None:
                    picks.append(wr)
                    freeMMZ -= 1
            if len(picks) > 0 and not self.Bot.HasInHand(CardId.MalissP_MarchHare) and not self.ActiveMarchHare:
                mh = gyFirst(lambda g: g.IsCode(CardId.MalissP_MarchHare))
                if mh is not None:
                    picks.append(mh)
            if freeMMZ > 0 and not self.ssRRThisTurn:
                rr = gyFirst(lambda g: g.IsCode(CardId.MalissQ_RedRansom))
                if rr is not None and rr not in picks and not self.ShouldSkipBanishing(rr):
                    picks.append(rr)
                    freeMMZ -= 1
            if freeMMZ > 0 and not self.ssHCThisTurn:
                hc = gyFirst(lambda g: g.IsCode(CardId.MalissQ_HeartsCrypter))
                if hc is not None and hc not in picks and not self.ShouldSkipBanishing(hc):
                    picks.append(hc)
                    freeMMZ -= 1
            threats = self.PickEnemyGYThreats(MAX_PICKS - len(picks))
            for t in threats:
                if len(picks) >= MAX_PICKS:
                    break
                if t not in picks:
                    picks.append(t)

        if len(picks) == 0:
            return False
        if len(picks) > MAX_PICKS:
            picks = picks[:MAX_PICKS]
        if len(picks) < MAX_PICKS:
            more = self.PickEnemyGYThreats(MAX_PICKS - len(picks))
            for t in more:
                if t not in picks:
                    picks.append(t)
        self.AI.SelectCard(picks)
        return True

    def IsMalissPawn(self, c):
        return c is not None and (c.IsCode(CardId.MalissP_ChessyCat) or c.IsCode(CardId.MalissP_WhiteRabbit) or
                                  c.IsCode(CardId.MalissP_Dormouse) or c.IsCode(CardId.MalissP_MarchHare))

    def PickEnemyGYThreats(self, need):
        result = []
        if need <= 0:
            return result
        danger = self.GetDangerousCardinEnemyGrave(False)
        for c in danger:
            if len(result) >= need:
                break
            if c not in result:
                result.append(c)
        if len(result) < need:
            i = len(self.Enemy.Graveyard) - 1
            while i >= 0 and len(result) < need:
                c = self.Enemy.Graveyard[i]
                i -= 1
                if c is None:
                    continue
                if c not in result:
                    result.append(c)
        if len(result) < need:
            for c in self.Enemy.Graveyard:
                if len(result) >= need:
                    break
                if c not in result:
                    result.append(c)
        return result

    def WB_OnBanished_SelfSS(self):
        if self.DefaultCheckWhetherCardIdIsNegated(self.Card.Id):
            return False
        if self.Card.Location != CardLocation.Removed:
            return False
        if self.GetMMZCount() >= 5:
            return False
        if self.Bot.LifePoints <= 900:
            return False
        self.AI.SelectYesNo(True)
        self.ssWBThisTurn = True
        return True

    def PickMalissTrapForWB(self):
        if self.Bot.HasInDeck(CardId.MalissC_GWC06) or self.Bot.HasInGraveyard(CardId.MalissC_GWC06):
            return CardId.MalissC_GWC06
        if self.Bot.HasInDeck(CardId.MalissC_MTP07) or self.Bot.HasInGraveyard(CardId.MalissC_MTP07):
            return CardId.MalissC_MTP07
        return 0

    def WB_SetMalissTrap(self):
        if self.DefaultCheckWhetherCardIdIsNegated(self.Card.Id):
            return False
        if self.ActivateDescription != self.Util.GetStringId(CardId.MalissQ_WhiteBinder, 1):
            return False
        if self.Card.Location != CardLocation.MonsterZone:
            return False
        self.SelectSafeSTZoneAwayFromImperm()
        return True

    def PickLinkMatsMinCount(self, targetLink, isEligible, minCount, maxCount, avoidIds=None, requireMaliss=False):
        all_ = [m for m in self.Bot.GetMonsters() if m is not None and m.IsFaceup() and isEligible(m)]
        if len(all_) < minCount:
            return []
        avoid = set(avoidIds or [])

        def OrderForFirst(src):
            return sorted(src, key=lambda m: (-self.LinkValOf(m), 1 if m.Id in avoid else 0, m.Attack))

        def OrderForLater(src):
            return sorted(src, key=lambda m: (0 if self.IsOneVal(m) else 1,
                                              (0 if max(1, m.LinkCount) == 1 else 1) if m.HasType(CardType.Link) else -1,
                                              self.LinkValOf(m), 1 if m.Id in avoid else 0, m.Attack))

        poolPreferred = [m for m in all_ if m.Id not in avoid]
        poolFallback = list(all_)

        def TryPick(pool):
            chosen = []

            def Dfs(avail, sum_):
                if sum_ > targetLink or len(chosen) > maxCount:
                    return False
                if len(chosen) >= minCount and sum_ == targetLink:
                    if requireMaliss and not any(self.IsMalissBody(c) for c in chosen):
                        return False
                    if GetBotAvailZonesFromExtraDeck(self.Util, chosen) == 0:
                        return False
                    return True
                need = max(0, minCount - len(chosen))
                if sum_ + need > targetLink:
                    return False
                ordered = OrderForFirst(avail) if len(chosen) == 0 else OrderForLater(avail)
                for i in range(len(ordered)):
                    m = ordered[i]
                    nextAvail = [x for idx, x in enumerate(ordered) if idx != i]
                    lv = self.LinkValOf(m)
                    if len(chosen) == 0:
                        values = [lv, 1] if lv > 1 else [1]
                    else:
                        values = [1, lv] if lv > 1 else [1]
                    for v in dict.fromkeys(values):
                        newSum = sum_ + v
                        if newSum > targetLink:
                            continue
                        remMin = max(0, minCount - (len(chosen) + 1))
                        if newSum + remMin > targetLink:
                            continue
                        chosen.append(m)
                        if Dfs(nextAvail, newSum):
                            return True
                        chosen.pop()
                return False

            if Dfs(OrderForFirst(pool), 0):
                return chosen
            return None

        pick = TryPick(poolPreferred)
        if pick is not None and len(pick) > 0:
            return pick
        pick = TryPick(poolFallback)
        return pick if pick is not None else []

    def Link_Apo(self):
        if not (self.Bot.HasInMonstersZone(CardId.MalissQ_RedRansom) and self.Bot.HasInMonstersZone(CardId.LinkDecoder)):
            return False
        mats = self.PickLinkMatsMinCount(
            targetLink=4,
            isEligible=lambda m: m.HasType(CardType.Monster),
            minCount=2,
            maxCount=2,
            avoidIds=[CardId.TranscodeTalker, CardId.AlliedCodeTalkerIgnister, CardId.AccesscodeTalker])
        if len(mats) == 0:
            return False
        self.AI.SelectMaterials(mats)
        self.blockWicckid = True
        return True

    def Flow3_Link_Firewall(self):
        if self.Bot.HasInMonstersZone(CardId.MalissQ_HeartsCrypter) and self.Bot.HasInMonstersZone(CardId.LinkDecoder) and \
                self.Bot.HasInMonstersZone(CardId.CyberseWicckid):
            mats = self.PickLinkMatsMinCount(
                targetLink=4,
                isEligible=lambda m: m.HasType(CardType.Monster),
                minCount=2,
                maxCount=2,
                avoidIds=[CardId.CyberseWicckid, CardId.Apollousa, CardId.TranscodeTalker, CardId.AlliedCodeTalkerIgnister,
                          CardId.AccesscodeTalker])
            if len(mats) == 0:
                return False
            self.AI.SelectMaterials(mats)
            return True
        return False

    def Step_LinkSummon_HeartsCrypter(self):
        if self.Bot.HasInMonstersZone(CardId.MalissQ_WhiteBinder) and self.Bot.HasInMonstersZone(CardId.MalissQ_RedRansom) and \
                self.Bot.HasInMonstersZone(CardId.Apollousa) and self.Bot.GetMonsterCount() < 5:
            return False
        cand = [c for c in self.Bot.GetMonsters() if c is not None and c.IsFaceup() and c.HasType(CardType.Effect)]
        if len(cand) < 3:
            return False
        avoid = {CardId.CyberseWicckid, CardId.Apollousa, CardId.AlliedCodeTalkerIgnister, CardId.AccesscodeTalker,
                 CardId.FirewallDragon, CardId.TranscodeTalker}
        ordered = sorted(cand, key=lambda m: (2 if m.Id in avoid else 0, 1 if m.HasType(CardType.Link) else 0, m.Attack))
        mats = ordered[:3]
        if not any(self.IsMaliss(c) for c in mats):
            maliss = next((c for c in ordered if self.IsMaliss(c)), None)
            if maliss is None:
                return False
            mats[2] = maliss
        if GetBotAvailZonesFromExtraDeck(self.Util, mats) == 0:
            return False
        self.AI.SelectMaterials(mats)
        return True

    def HC_Quick_ReturnBanished_AndBanishField(self):
        if self.DefaultCheckWhetherCardIdIsNegated(self.Card.Id):
            return False
        if self.ActivateDescription != self.Util.GetStringId(CardId.MalissQ_HeartsCrypter, 0):
            return False
        if self.Card.Location != CardLocation.MonsterZone:
            return False
        if self.CheckWhetherNegated():
            return False
        self.RefreshNoChainWindows()
        banishedMaliss = self.GetBanishedMaliss()
        if len(banishedMaliss) == 0:
            return False
        haveReturn = len(banishedMaliss) > 0
        mustNow = len(self.GetProblematicEnemyCardList(canBeTarget=True,
                                                       selfType=CardType.Monster | CardType.Spell | CardType.Trap)) > 0
        if self.Duel.Player == 0:
            if not haveReturn and not mustNow:
                return False
        else:
            if not mustNow and not self.IsPreferredRemovalTiming():
                return False
        if not haveReturn:
            return False
        ret = self.PickBanishedMalissForHC(banishedMaliss)
        if ret is None:
            return False
        fieldTargets = self.GetProblematicEnemyCardList(True, selfType=CardType.Monster | CardType.Spell | CardType.Trap)
        if len(fieldTargets) == 0:
            any_ = self.GetBestEnemyCard(False, True)
            if any_ is not None:
                fieldTargets.append(any_)
        if len(fieldTargets) == 0:
            return False
        self.AI.SelectCard(ret)
        self.AI.SelectNextCard(fieldTargets)
        self.ConsumePreferredWindow()
        return self.DontSelfNG()

    def GetBanishedMaliss(self):
        return GetMatchingCards(self.Bot.Banished, lambda c: c is not None and c.IsFaceup() and c.HasSetcode(0x1b9))

    def PickBanishedMalissForHC(self, cand):
        cand = [c for c in cand if not c.IsCode(CardId.MalissQ_WhiteBinder) and not c.IsCode(CardId.MalissQ_RedRansom)]
        if len(cand) == 0:
            return None
        return _max_by(cand, key=self.ScoreForBanishedMaliss)

    def HC_OnBanished_SpecialSummon(self):
        if self.DefaultCheckWhetherCardIdIsNegated(self.Card.Id):
            return False
        if self.Card.Location != CardLocation.Removed:
            return False
        if self.GetMMZCount() >= 5:
            return False
        if self.Bot.LifePoints <= 900:
            return False
        self.AI.SelectYesNo(True)
        self.ssHCThisTurn = True
        return True

    def HasMalissLinkFaceup(self):
        return any(c is not None and c.IsFaceup() and c.HasSetcode(0x1b9) and c.HasType(CardType.Link)
                   for c in self.Bot.GetMonsters())

    def CanReachAlliedNow(self):
        mats = self.PickLinkMatsMinCount(
            targetLink=5,
            isEligible=lambda m: m.HasType(CardType.Effect),
            minCount=3,
            maxCount=5,
            avoidIds=[CardId.Apollousa, CardId.FirewallDragon, CardId.AccesscodeTalker])
        return len(mats) > 0

    def Flow3_Link_Allied(self):
        if not (self.Bot.HasInMonstersZoneOrInGraveyard(CardId.MalissQ_RedRansom) and
                self.Bot.HasInMonstersZoneOrInGraveyard(CardId.MalissQ_WhiteBinder)):
            return False
        mats = self.PickLinkMatsMinCount(
            targetLink=5,
            isEligible=lambda m: m.HasType(CardType.Effect),
            minCount=3,
            maxCount=5,
            avoidIds=[CardId.Apollousa, CardId.FirewallDragon, CardId.AccesscodeTalker])
        if len(mats) == 0:
            return False
        self.AI.SelectMaterials(mats)
        self.Allied_End = True
        return True

    def Emer_Allied(self):
        if not self.enemyActivateLancea:
            return False
        if not (self.Bot.HasInMonstersZone(CardId.TranscodeTalker) and self.Bot.HasInMonstersZone(CardId.SplashMage)):
            return False
        mats = self.PickLinkMatsMinCount(
            targetLink=5,
            isEligible=lambda m: m.HasType(CardType.Effect),
            minCount=3,
            maxCount=3)
        if len(mats) == 0:
            return False
        self.AI.SelectMaterials(mats)
        self.Allied_End = True
        return True

    def Emer_Allied2(self):
        myMonsters = [m for m in self.Bot.GetMonsters() if m is not None]
        if len(myMonsters) != 3:
            return False
        link3List = [m for m in myMonsters if m.HasType(CardType.Link) and m.LinkCount == 3]
        if len(link3List) != 1:
            return False
        haveKeyInGY = self.Bot.HasInGraveyard(CardId.MalissQ_RedRansom) or \
            self.Bot.HasInGraveyard(CardId.MalissQ_WhiteBinder) or \
            self.Bot.HasInGraveyard(CardId.TranscodeTalker)
        if not haveKeyInGY:
            return False
        mats = self.PickLinkMatsMinCount(
            targetLink=5,
            isEligible=lambda m: m.HasType(CardType.Effect),
            minCount=3,
            maxCount=3)
        if len(mats) == 0:
            return False
        self.AI.SelectMaterials(mats)
        self.Allied_End = True
        return True

    def FindGWC06TargetByOrder(self, *ids):
        for id_ in ids:
            gy = GetFirstMatchingCard(self.Bot.Graveyard, lambda c: c is not None and c.IsCode(id_))
            if gy is not None:
                return gy
            ban = GetFirstMatchingCard(self.Bot.Banished, lambda c: c is not None and c.IsCode(id_) and c.IsFaceup())
            if ban is not None:
                return ban
        return None

    def PickGWC06CostCandidateId(self):
        if self.Bot.HasInMonstersZone(CardId.MalissQ_WhiteBinder) and not self.ssWBThisTurn:
            return CardId.MalissQ_WhiteBinder
        if self.Bot.HasInMonstersZone(CardId.MalissQ_RedRansom) and not self.ssRRThisTurn:
            return CardId.MalissQ_RedRansom
        card = self.PickTB11CostCandidateId()
        if card != 0:
            return card
        return 0

    def PickGWC06TargetExtend(self):
        if self.Duel.Turn > 2:
            return self.FindGWC06TargetByOrder(CardId.MalissQ_HeartsCrypter, CardId.MalissQ_RedRansom,
                                               CardId.MalissQ_WhiteBinder)
        return self.FindGWC06TargetByOrder(CardId.MalissQ_WhiteBinder, CardId.MalissQ_RedRansom,
                                           CardId.MalissQ_HeartsCrypter, CardId.MalissP_WhiteRabbit,
                                           CardId.MalissP_Dormouse, CardId.MalissP_ChessyCat, CardId.MalissP_MarchHare)

    def GWC06_MyTurn_Extend(self):
        if self.DefaultCheckWhetherCardIdIsNegated(self.Card.Id):
            return False
        if self.Duel.Player == 0 and self.GetMMZCount() >= 4 and self.Bot.HasInMonstersZone(CardId.FirewallDragon) and \
                (self.Bot.HasInMonstersZoneOrInGraveyard(CardId.MalissQ_RedRansom) or
                 self.Bot.HasInMonstersZoneOrInGraveyard(CardId.MalissQ_WhiteBinder) or
                 self.Bot.HasInMonstersZoneOrInGraveyard(CardId.MalissQ_HeartsCrypter)):
            return False
        if self.Duel.Player != 0:
            return False
        if not (self.Duel.Phase == DuelPhase.Main1 or self.Duel.Phase == DuelPhase.Main2):
            return False
        if self.CheckSpellWillBeNegate():
            return False
        if self.GetMMZCount() >= 5:
            return False
        if not self.Bot.HasInMonstersZone(CardId.MalissQ_WhiteBinder) and \
                not (self.Bot.HasInMonstersZone(CardId.MalissQ_RedRansom) and self.Bot.GetMonsterCount() == 1):
            return False
        target = self.PickGWC06TargetExtend()
        if target is None:
            return False
        if self.gwc06SetThisTurn:
            costId = self.PickGWC06CostCandidateId()
            if costId == 0:
                return False
            self.AI.SelectCard(costId)
            self.AI.SelectNextCard(target)
            return self.DontSelfNG()
        self.AI.SelectCard(target)
        return self.DontSelfNG()

    def GWC06_OppTurn_ReviveWB_HC(self):
        if self.Duel.Player != 1:
            return False
        if not self.Bot.HasInSpellZone(CardId.MalissC_GWC06):
            return False
        if self.CheckSpellWillBeNegate():
            return False
        if self.GetMMZCount() >= 5:
            return False
        target = self.FindGWC06TargetByOrder(CardId.MalissQ_WhiteBinder, CardId.MalissQ_HeartsCrypter)
        if target is None:
            return False
        if self.gwc06SetThisTurn:
            costId = self.PickGWC06CostCandidateId()
            if costId == 0:
                return False
            self.AI.SelectCard(costId)
            self.AI.SelectNextCard(target)
            return self.DontSelfNG()
        self.AI.SelectCard(target)
        return self.DontSelfNG()

    @staticmethod
    def FirstBit(mask):
        for i in range(32):
            b = 1 << i
            if (mask & b) != 0:
                return b
        return 0

    @staticmethod
    def FirstBitFromOrder(mask, order):
        for b in order:
            if (mask & b) != 0:
                return b
        return MalissExecutor.FirstBit(mask)

    def PreferSafeSummonZones(self, available):
        MAIN_MASK = Zones.z0 | Zones.z1 | Zones.z2 | Zones.z3 | Zones.z4
        emzMask = available & ~MAIN_MASK
        if emzMask != 0:
            return self.FirstBit(emzMask)
        enemyPointed = self.Enemy.GetLinkedZones()
        safeMain = (available & MAIN_MASK) & ~enemyPointed
        if safeMain != 0:
            return self.FirstBitFromOrder(safeMain, [Zones.z2, Zones.z1, Zones.z3, Zones.z0, Zones.z4])
        return self.FirstBit(available)

    def PickMTP07CostCandidateId(self):
        return self.PickTB11CostCandidateId()

    def PickMTP07EnemyRemovalTarget(self):
        list_ = self.GetProblematicEnemyCardList(canBeTarget=True, ignoreSpells=False, selfType=CardType.Trap)
        if len(list_) > 0:
            return list_[0]
        m = self.GetBestEnemyMonster(onlyFaceup=False, canBeTarget=True)
        if m is not None:
            return m
        s = self.GetBestEnemySpell(onlyFaceup=False, canBeTarget=True)
        if s is not None:
            return s
        return next((c for c in self.Enemy.GetMonsters() if c is not None), None) or \
            next((c for c in self.Enemy.GetSpells() if c is not None), None)

    def MTP07_ForMH(self):
        if not (self.Bot.GetMonsterCount() == 1 and self.Bot.HasInMonstersZone(CardId.MalissP_WhiteRabbit)):
            return False
        if self.CheckSpellWillBeNegate():
            return False
        if self.CheckWhetherNegated():
            return False
        searchId = self.PickMTP07SearchId()
        if searchId == 0:
            return False
        if self.mtp07SetThisTurn:
            costId = self.PickMTP07CostCandidateId()
            if costId == 0:
                return False
            self.AI.SelectCard(costId)
        self.AI.SelectNextCard(searchId)
        return self.DontSelfNG()

    def MTP07_OppTurn_RemoveEnemyOnly(self):
        if self.Duel.Player != 1:
            return False
        if not self.HasMalissLinkFaceup():
            return False
        if self.CheckSpellWillBeNegate():
            return False
        if self.CheckWhetherNegated():
            return False
        urgent = self.GetProblematicEnemyCardList(canBeTarget=True, ignoreSpells=False, selfType=CardType.Trap)
        if len(urgent) == 0 and not self.IsPreferredRemovalTiming():
            return False
        preBattle = self.Duel.Phase == DuelPhase.Main1 and self.Enemy.GetMonsterCount() > 0
        if len(urgent) == 0 and not (self.IsPreferredRemovalTiming() or preBattle):
            return False
        searchId = self.PickMTP07SearchId()
        if searchId == 0:
            return False
        if len(urgent) > 0:
            target = urgent[0]
        elif preBattle:
            target = _max_by([c for c in self.Enemy.MonsterZone if c is not None and c.IsFaceup()], key=lambda c: c.Attack)
        else:
            target = self.PickMTP07EnemyRemovalTarget()
        if target is None:
            return False
        if self.mtp07SetThisTurn:
            costId = self.PickMTP07CostCandidateId()
            if costId == 0:
                return False
            self.AI.SelectCard(costId)
            self.AI.SelectNextCard(searchId)
            self.AI.SelectNextCard(target)
            self.ConsumePreferredWindow()
            return self.DontSelfNG()
        self.AI.SelectCard(searchId)
        self.AI.SelectNextCard(target)
        self.ConsumePreferredWindow()
        return self.DontSelfNG()

    def Emergency_NS(self):
        if self.usedNormalSummon:
            return False
        if self.Bot.GetMonsterCount() != 0:
            return False
        if self.Bot.HasInHand(CardId.MalissP_Dormouse) or self.Bot.HasInHand(CardId.MalissP_WhiteRabbit) or \
                self.Bot.HasInHand(CardId.MalissP_ChessyCat) or \
                self.Bot.HasInHand(CardId.GoldSarcophagus) or self.Bot.HasInHand(CardId.MalissInUnderground):
            return False
        if not self.Bot.HasInHand(CardId.BackupIgnister):
            return False
        self.usedNormalSummon = True
        self.nsplan = True
        return True

    def IsWicInEMZ(self, wic):
        return wic is not None and wic.Location == CardLocation.MonsterZone and \
            (wic.Sequence == self.EMZ_LEFT or wic.Sequence == self.EMZ_RIGHT)

    def GetWicDownSeq(self, wic):
        if not self.IsWicInEMZ(wic):
            return
        if wic.Sequence == self.EMZ_LEFT:
            yield 1
            yield 2
        if wic.Sequence == self.EMZ_RIGHT:
            yield 3
            yield 4

    def IsUnderWic(self, wic, m):
        if wic is None or m is None:
            return False
        if m.Controller != wic.Controller:
            return False
        if m.Location != CardLocation.MonsterZone:
            return False
        if m.Sequence < 0 or m.Sequence > 4:
            return False
        return m.Sequence in self.GetWicDownSeq(wic)

    def PickUnderlingForTranscode(self, wic, pool):
        if not self.IsWicInEMZ(wic):
            return None
        underlings = [x for x in pool
                      if x is not None and x != wic and x.IsFaceup() and x.Location == CardLocation.MonsterZone and
                      x.Controller == wic.Controller and 0 <= x.Sequence <= 4 and self.IsUnderWic(wic, x) and
                      (x.HasType(CardType.Link) or x.HasType(CardType.Effect)) and not x.HasType(CardType.Token)]
        if len(underlings) == 0:
            return None
        preferLD = next((x for x in underlings if x.IsCode(CardId.LinkDecoder)), None)
        if preferLD is not None:
            return preferLD
        return next(iter(sorted(underlings, key=lambda x: (-(2 if x.HasType(CardType.Link) else 1), -x.Attack))), None)

    def SummonTranscode(self):
        if not self.enemyActivateLancea:
            return False
        wic = next((x for x in self.Bot.GetMonsters() if x is not None and x.IsFaceup() and
                    x.IsCode(CardId.CyberseWicckid)), None)
        if not self.IsWicInEMZ(wic):
            return False
        under = self.PickUnderlingForTranscode(wic, self.Bot.GetMonsters())
        if under is None:
            return False
        self.AI.SelectMaterials([wic, under])
        return True

    def ChooseWicckidEmz(self, available):
        emzAvail = available & self.EMZ_ALL
        if emzAvail == 0:
            return 0
        best = 0
        bestScore = -2 ** 31
        for emz in (self.EMZ_L, self.EMZ_R):
            if (emzAvail & emz) == 0:
                continue
            score = 0
            downSeq = 1 if emz == self.EMZ_L else 3
            if self.Bot.MonsterZone[downSeq] is None:
                score += 10
            if self.Bot.MonsterZone[downSeq + 1] is None:
                score += 10
            if score > bestScore:
                bestScore = score
                best = emz
        if best == 0:
            best = self.EMZ_L if (emzAvail & self.EMZ_L) != 0 else self.EMZ_R
        return best

    def IsPreferredRemovalTiming(self):
        if self.Duel.Player != 1:
            return False
        if self._prefWindowTTL > 0:
            return True
        if self._oppJustActivatedPersistentSpell or self._oppJustSummoned or self._oppJustSet:
            return True
        return False

    def ConsumePreferredWindow(self):
        self._prefWindowTTL = 0
        self._oppJustActivatedPersistentSpell = False
        self._oppJustSummoned = False
        self._oppJustSet = False

    def RefreshNoChainWindows(self):
        oppMain = self.Duel.Player == 1 and (self.Duel.Phase == DuelPhase.Main1 or self.Duel.Phase == DuelPhase.Main2)
        curMon = self.Enemy.GetMonsterCount()
        if curMon > self._enemyMonsterCountSnap:
            self._oppJustSummoned = True
            if oppMain:
                self._prefWindowTTL = max(self._prefWindowTTL, 2)
        self._enemyMonsterCountSnap = curMon
        curFD = sum(1 for c in self.Enemy.SpellZone if c is not None and c.IsFacedown())
        if curFD > self._enemyFacedownSTSnap:
            self._oppJustSet = True
            if oppMain:
                self._prefWindowTTL = max(self._prefWindowTTL, 2)
        self._enemyFacedownSTSnap = curFD
        if oppMain:
            if self._prefWindowTTL > 0:
                self._prefWindowTTL -= 1
            if self._prefWindowTTL == 0:
                self._oppJustActivatedPersistentSpell = False
                self._oppJustSummoned = False
                self._oppJustSet = False
        else:
            self._prefWindowTTL = 0
            self._oppJustActivatedPersistentSpell = False
            self._oppJustSummoned = False
            self._oppJustSet = False

    def FirewallBounce_OnOppSummon(self):
        if self.DefaultCheckWhetherCardIdIsNegated(self.Card.Id):
            return False
        if self.ActivateDescription != self.Util.GetStringId(CardId.FirewallDragon, 0):
            return False
        if self.Duel.LastSummonPlayer != 1:
            return False
        picks = []
        negateList = self.GetMonsterListForTargetNegate()
        if negateList is not None:
            for c in negateList:
                if c is None:
                    continue
                if c.Controller != 1:
                    continue
                if not c.IsMonster():
                    continue
                if not c.IsFaceup():
                    continue
                if c not in picks:
                    picks.append(c)
        for m in sorted(self.Enemy.GetMonsters(), key=lambda x: -x.Attack):
            if m is None:
                continue
            if not m.IsMonster():
                continue
            if not m.IsFaceup():
                continue
            if m not in picks:
                picks.append(m)
        if len(picks) == 0:
            return False
        self.AI.SelectCard(picks)
        return True

    def Accesscode_OnSummon_AtkUp(self):
        list_ = []
        prefer = [CardId.MalissQ_HeartsCrypter, CardId.MalissQ_WhiteBinder, CardId.MalissQ_RedRansom, CardId.TranscodeTalker]
        for id_ in prefer:
            hit = GetFirstMatchingCard(self.Bot.Graveyard, lambda c: c is not None and c.IsCode(id_))
            if hit is not None:
                list_.append(hit)
        self.AI.SelectCard(list_)
        return True

    def Accesscode_Destroy_Ignition(self):
        if self.ActivateDescription != self.Util.GetStringId(CardId.AccesscodeTalker, 1):
            return False
        if self.Enemy.GetFieldCount() == 0:
            return False
        costPool = [c for c in (self.Bot.GetGraveyardMonsters() or []) if c.HasType(CardType.Link)] + \
            [c for c in (self.Bot.GetMonsters() or []) if c.HasType(CardType.Link) and c != self.Card]
        costList = sorted(costPool, key=lambda c: (c.Location != CardLocation.Grave, c.LinkCount, c.Attack))
        if len(costList) == 0:
            return False
        targets = []
        targets.extend(s for s in self.Enemy.GetSpells() if s is not None and s.IsFacedown())
        targets.extend(s for s in self.Enemy.GetSpells() if s is not None and not s.IsFacedown())
        targets.extend(sorted(self.Enemy.GetMonsters(), key=lambda m: -m.Attack))
        if len(targets) == 0:
            return False
        self.AI.SelectCard(costList)
        self.AI.SelectNextCard(targets)
        return True

    def AlreadySSFromBanishThisTurn(self, c):
        if c is None:
            return False
        if c.Controller != 0:
            return False
        if c.IsCode(CardId.MalissP_Dormouse):
            return self.ssDormouse
        if c.IsCode(CardId.MalissP_WhiteRabbit):
            return self.ssWhiteRabbit
        if c.IsCode(CardId.MalissP_ChessyCat):
            return self.ssChessyCat
        if c.IsCode(CardId.MalissQ_RedRansom):
            return self.ssRRThisTurn
        if c.IsCode(CardId.MalissQ_HeartsCrypter):
            return self.ssHCThisTurn
        if c.IsCode(CardId.MalissQ_WhiteBinder):
            return self.ssWBThisTurn
        return False

    def ShouldSkipBanishing(self, c):
        if c is None:
            return True
        if c.Controller != 0:
            return False
        if self.AlreadySSFromBanishThisTurn(c):
            return True
        if c.IsCode(CardId.MalissP_MarchHare) and self.ActiveMarchHare:
            return True
        return False

    def DescIs(self, cardId, *idx):
        if self.ActivateDescription == -1:
            return True
        for i in idx:
            if self.ActivateDescription == self.Util.GetStringId(cardId, i):
                return True
        return False

    def PickMirrorCostCandidate(self):
        handPref = [CardId.MalissP_WhiteRabbit, CardId.MalissP_ChessyCat, CardId.MalissP_Dormouse, CardId.MalissP_MarchHare]
        for id_ in handPref:
            h = GetFirstMatchingCard(self.Bot.Hand, lambda c: c is not None and c.IsCode(id_))
            if h is not None:
                return h
        fieldP = _min_by([c for c in self.Bot.GetMonsters()
                          if c is not None and c.HasSetcode(0x1b9) and not c.HasType(CardType.Link)],
                         key=lambda c: c.Attack)
        if fieldP is not None:
            return fieldP
        avoid = [CardId.MalissQ_HeartsCrypter, CardId.MalissQ_WhiteBinder, CardId.MalissQ_RedRansom]
        weakLink = _min_by([c for c in self.Bot.GetMonsters()
                            if c is not None and c.HasSetcode(0x1b9) and c.HasType(CardType.Link) and c.Id not in avoid],
                           key=lambda c: c.Attack)
        return weakLink

    def Mirror_SearchOrderForType(self, isTrap, isMon):
        if isTrap:
            return [CardId.MalissC_GWC06, CardId.MalissC_MTP07]
        if isMon:
            if not self.Bot.HasInHand(CardId.MalissP_WhiteRabbit) and self.NSDorMouse:
                return [CardId.MalissP_WhiteRabbit, CardId.MalissP_MarchHare, CardId.MalissP_Dormouse, CardId.MalissP_ChessyCat]
            else:
                return [CardId.MalissP_MarchHare, CardId.MalissP_Dormouse, CardId.MalissP_WhiteRabbit, CardId.MalissP_ChessyCat]
        return [CardId.MalissP_MarchHare, CardId.MalissP_Dormouse, CardId.MalissP_WhiteRabbit, CardId.MalissP_ChessyCat]

    def PickMirrorGYTargetForSearch(self):
        if self.NSDorMouse and not self.ssRRThisTurn:
            rr = GetFirstMatchingCard(self.Bot.Graveyard, lambda c: c is not None and c.IsCode(CardId.MalissQ_RedRansom))
            if rr is not None:
                return rr
        monPref = [CardId.MalissP_MarchHare, CardId.MalissP_Dormouse, CardId.MalissP_WhiteRabbit, CardId.MalissP_ChessyCat]
        for id_ in monPref:
            m = GetFirstMatchingCard(self.Bot.Graveyard, lambda c: c is not None and c.IsCode(id_))
            if m is not None and self.Bot.HasInDeck(id_):
                return m
        return None

    def PickMTP07SearchId(self):
        if self.Bot.HasInDeck(CardId.MalissP_MarchHare):
            return CardId.MalissP_MarchHare
        pawnPref = [CardId.MalissP_Dormouse, CardId.MalissP_WhiteRabbit, CardId.MalissP_ChessyCat]
        for id_ in pawnPref:
            if self.Bot.HasInDeck(id_):
                return id_
        return 0

    def SelectSafeSTZoneAwayFromImperm(self):
        safeCols = [seq for seq in range(5)
                    if self.Bot.SpellZone[seq] is None and seq not in self.infiniteImpermanenceList]
        if len(safeCols) == 0:
            safeCols = [seq for seq in range(5) if self.Bot.SpellZone[seq] is None]
        mask = 0
        for seq in safeCols:
            mask |= 1 << seq
        self.AI.SelectPlace(mask)

    def T3Allow(self):
        if self.Duel.Player != 0:
            return False
        if self.myTurnCount < 2:
            return False
        if not self.HaveBackupOrWizardInHand() or not self.Bot.HasInHand(CardId.MalissP_MarchHare):
            return False
        return True

    def NSBackup(self):
        if self.Bot.GetMonsterCount() != 0:
            return False
        if self.usedNormalSummon:
            return False
        if self.Bot.HasInHand(CardId.MalissP_Dormouse) or self.Bot.HasInHand(CardId.MalissP_WhiteRabbit) or \
                self.Bot.HasInHand(CardId.MalissP_ChessyCat) or self.Bot.HasInHand(CardId.MalissInUnderground) or \
                self.Bot.HasInHand(CardId.TERRAFORMING) or self.Bot.HasInHand(CardId.GoldSarcophagus):
            return False
        self.nsBackupplan = True
        return True

    def NSMH(self):
        mhCount = len(GetMatchingCards(self.Bot.Hand, lambda c: c is not None and c.IsCode(CardId.MalissP_MarchHare)))
        if mhCount < 2:
            return False
        if self.Bot.GetMonsterCount() != 0:
            return False
        if self.usedNormalSummon:
            return False
        if self.Bot.HasInHand(CardId.MalissP_Dormouse) or self.Bot.HasInHand(CardId.MalissP_WhiteRabbit) or \
                self.Bot.HasInHand(CardId.MalissP_ChessyCat) or self.Bot.HasInHand(CardId.MalissInUnderground) or \
                self.Bot.HasInHand(CardId.TERRAFORMING) or self.Bot.HasInHand(CardId.GoldSarcophagus):
            return False
        return True

    def LinguribohMHLine(self):
        if not (self.Bot.HasInHand(CardId.MalissP_MarchHare) and self.Bot.HasInMonstersZone(CardId.MalissP_MarchHare)):
            return False
        if self.Bot.GetMonsterCount() != 1:
            return False
        return True

    def EmerTranscode(self):
        if not self.enemyActivateLancea:
            return False
        if self.Bot.GetMonsterCount() < 3:
            return False
        mats = self.PickLinkMatsMinCount(
            targetLink=3,
            isEligible=lambda m: m.HasType(CardType.Effect),
            minCount=2,
            maxCount=2)
        if len(mats) == 0:
            return False
        self.AI.SelectMaterials(mats)
        return True

    def ScoreMalissMurakumoDiscard(self, card):
        if card is None:
            return 2 ** 31 - 1
        score = 1000
        copiesInHand = sum(1 for c in self.Bot.Hand if c is not None and c.IsCode(card.Id))
        if copiesInHand > 1:
            score -= 600
        undergroundActive = any(c is not None and c.IsFaceup() and c.IsCode(CardId.MalissInUnderground)
                                for c in self.Bot.SpellZone)
        if card.IsCode(CardId.TERRAFORMING) and (undergroundActive or not self.Bot.HasInDeck(CardId.MalissInUnderground)):
            score -= 500
        if card.IsCode(CardId.MalissInUnderground) and undergroundActive:
            score -= 400
        if card.IsCode(CardId.MalissP_Dormouse, CardId.MalissP_WhiteRabbit, CardId.GoldSarcophagus):
            score += 500
        return score
