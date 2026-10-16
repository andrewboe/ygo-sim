"""Branded executor for ygo-sim's branded__tcg, written for ygo-sim in WindBot's executor style from the deck's
current lines (WindBot's Albaz executor plays an older Branded Despia list; this list is the 2026 Dogmatika /
"White Dragon" Branded build with Super Polymerization and The Fallen & The Virtuous).

Sources: YGOPRODeck deck primers "Branded April 2026", "Branded post Burst Protocol" and "Branded Synchro June
2026" (Fallen of the White Dragon as the 1-card starter: send an Albaz Fusion from the Extra Deck -> Special
Summon it -> Incredible Ecclesia from the Deck -> Ecclesia and the Dark Dragon -> Guiding Quem or Blazing
Cartesia; Branded Fusion / Branded Opening lock you into Fusions, so Synchro first; Albion the Branded Dragon or
Titaniklad as the White Dragon cost for their End Phase effects), the card text (cards.cdb), and the lines
goldfish search found on this list (goldfish_lines.py): Incredible Ecclesia Normal Summon -> tribute it for White
Dragon from the Deck -> White Dragon revives Ecclesia -> Ecclesia and the Dark Dragon; Branded Opening -> Aluber
-> Branded Retribution; Branded Fusion -> Rindbrumm with Springans Kitt, Kitt reviving White Dragon, White Dragon
summoning Dogmatika Ecclesia, which searches The Fallen & The Virtuous; Blazing Cartesia fusing spent bodies into
Despian Quaeritis / Mixousia; The Dragon that Devours the Dogma sent from the Extra Deck as a cost so its End
Phase effect adds Tri-Brigade Mercourier; Albion the Shrouded Dragon cycling (send an Albaz from the Deck, draw).

Plan (turn 1): White Dragon / Incredible Ecclesia into Ecclesia and the Dark Dragon (before anything that locks
the Extra Deck to Fusions), Ecclesia and the Dark Dragon pulling White Dragon / Cartesia / Quem; Aluber (Normal
Summon or Branded Opening) searching Branded Retribution, else Branded Fusion; Branded Fusion -> Rindbrumm (Albaz
+ Kitt from the Deck) when there is no Synchro line; Cartesia fusing spent bodies (not herself, not hand traps)
into Mirrorjade / Rindbrumm / Quaeritis; Extra Deck costs in the order Dogma Dragon (End Phase: Mercourier),
Albion the Branded Dragon (End Phase: Set Retribution / The Fallen & The Virtuous), Titaniklad (End Phase: White
Dragon); Dogmatika Ecclesia / Nadir Servant searches only once the Extra Deck summons are done; then Set Branded
Retribution, Super Polymerization and The Fallen & The Virtuous. Opponent's turn: hand traps (Default*), Branded
Retribution / Rindbrumm / Mercourier on their activations, Incredible Ecclesia / Ecclesia and the Dark Dragon
bringing Fallen of Albaz to fuse their monster, Super Polymerization and The Fallen & The Virtuous on their
board, Mirrorjade's banish.

Approximations: the env limits in docs/windbot_porting.md. Once-per-turn effects are tracked by the effect
description resolved this turn (OnChainSolved); Extra Deck locks are left to the engine (it doesn't offer what a
lock forbids), the rows only order the steps so no lock comes early.
"""
from windbot import *
from windbot_default import DefaultExecutor, _CardId


class CardId:
    NadirServant = 1984618
    BrandedRetribution = 17751597
    TriBrigadeMercourier = 19096726
    SpringansKitt = 19304410
    CalledByTheGrave = 24224830
    AlbionTheShroudedDragon = 25451383
    BrandedInHighSpirits = 29948294
    FallenAndVirtuous = 30271097
    BrandedOpening = 36637374
    MulcharmyFuwalos = 42141493
    BrandedFusion = 44362883
    GuidingQuem = 45883110
    SuperPolymerization = 48130397
    IncredibleEcclesia = 55273560
    DogmatikaEcclesia = 60303688
    Aluber = 62962630
    FallenOfAlbaz = 68468459
    WhiteDragon = 73819701
    GoldSarcophagus = 75500286
    MulcharmyPurulia = 84192580
    DrollLockBird = 94145021
    BlazingCartesia = 95515789
    # Extra Deck
    Granguignol = 24915933
    HyperinvokedAeon = 33166263
    Titaniklad = 41373230
    Mirrorjade = 44146295
    Rindbrumm = 51409648
    LubellionSearing = 70534340
    DespianQuaeritis = 72272462
    ThreeChampions = 74405783
    DogmaDragon = 76666602
    EcclesiaDarkDragon = 78397661
    Mixousia = 80843006
    AlbionBranded = 87746184
    Secreterion = 89851827


C = CardId
ALBAZ_NAMED = (C.FallenOfAlbaz, C.WhiteDragon, C.AlbionTheShroudedDragon)
HAND_TRAPS = (C.MulcharmyFuwalos, C.MulcharmyPurulia, C.DrollLockBird, C.TriBrigadeMercourier, C.CalledByTheGrave)
SET_CARDS = (C.BrandedRetribution, C.SuperPolymerization, C.FallenAndVirtuous)
# monsters whose quick effect is the board's interruption: never spend them as material on our own turn
KEEP_ON_FIELD = (C.BlazingCartesia, C.IncredibleEcclesia, C.EcclesiaDarkDragon, C.Mirrorjade, C.Rindbrumm,
                 C.DespianQuaeritis, C.Mixousia)


def S(card, n):
    return card * 16 + n


# effect descriptions (WindBot's GetStringId)
WD_SELF, WD_ECCLESIA = S(C.WhiteDragon, 0), S(C.WhiteDragon, 1)
IE_QUICK = S(C.IncredibleEcclesia, 1)  # the script's string for the Tribute quick effect (its End Phase add has none)
CARTESIA_SS, CARTESIA_FUSION, CARTESIA_ADD = (S(C.BlazingCartesia, k) for k in range(3))
QUEM_SEND, QUEM_REVIVE = S(C.GuidingQuem, 0), S(C.GuidingQuem, 1)
ALUBER_SEARCH, ALUBER_NEGATE = S(C.Aluber, 0), S(C.Aluber, 1)
KITT_SELF, KITT_REVIVE = S(C.SpringansKitt, 0), S(C.SpringansKitt, 1)
MERC_NEGATE, MERC_SEARCH = S(C.TriBrigadeMercourier, 0), S(C.TriBrigadeMercourier, 1)
HS_ACT, HS_ADD, HS_APPLY = (S(C.BrandedInHighSpirits, k) for k in range(3))
FV_DESTROY, FV_REVIVE = S(C.FallenAndVirtuous, 1), S(C.FallenAndVirtuous, 2)
OPENING_ACT, OPENING_SS, OPENING_BANISH = S(C.BrandedOpening, 0), S(C.BrandedOpening, 1), S(C.BrandedOpening, 3)
DE_SS, DE_SEARCH = S(C.DogmatikaEcclesia, 0), S(C.DogmatikaEcclesia, 1)
EDD_SUMMON, EDD_SHUFFLE = S(C.EcclesiaDarkDragon, 0), S(C.EcclesiaDarkDragon, 1)
GRAN_SEND, GRAN_FLOAT = S(C.Granguignol, 0), S(C.Granguignol, 1)
TITAN_EP, TITAN_SS = S(C.Titaniklad, 0), S(C.Titaniklad, 3)
ALBION_FUSION, ALBION_EP, ALBION_SET = S(C.AlbionBranded, 0), S(C.AlbionBranded, 1), S(C.AlbionBranded, 3)
MJ_BANISH = S(C.Mirrorjade, 0)
RIND_NEGATE, RIND_REVIVE, RIND_BOUNCE = (S(C.Rindbrumm, k) for k in range(3))
QUAER_ATK, QUAER_FLOAT, QUAER_SS = S(C.DespianQuaeritis, 0), S(C.DespianQuaeritis, 1), S(C.DespianQuaeritis, 3)
CHAMP_ADD, CHAMP_NEGATE, CHAMP_DESTROY = (S(C.ThreeChampions, k) for k in range(3))
DOGMA_SHUFFLE, DOGMA_EP = S(C.DogmaDragon, 0), S(C.DogmaDragon, 1)
MIX_ATTR, MIX_FUSION, MIX_GY = (S(C.Mixousia, k) for k in range(3))
AEON_BANISH, AEON_ATTR, AEON_ED = (S(C.HyperinvokedAeon, k) for k in range(3))
RET_NEGATE, RET_ADD = S(C.BrandedRetribution, 0), S(C.BrandedRetribution, 1)
ALWAYS_YES = (HS_APPLY, OPENING_BANISH, AEON_ED, CHAMP_DESTROY)


class BrandedExecutor(DefaultExecutor):
    DECK_EXECUTOR = True

    def __init__(self):
        super().__init__()
        A, SS, NS, SET = ExecutorType.Activate, ExecutorType.SpSummon, ExecutorType.Summon, ExecutorType.SpellSet
        # hand traps and the opponent's turn
        self.AddExecutor(A, C.MulcharmyPurulia, self.DefaultMaxxC)
        self.AddExecutor(A, C.MulcharmyFuwalos, self.DefaultMaxxC)
        self.AddExecutor(A, C.DrollLockBird, self.DrollActivate)
        self.AddExecutor(A, C.CalledByTheGrave, self.DefaultCalledByTheGrave)
        self.AddExecutor(A, C.BrandedRetribution, self.RetributionActivate)
        self.AddExecutor(A, C.Rindbrumm, self.RindbrummActivate)
        self.AddExecutor(A, C.TriBrigadeMercourier, self.MercourierActivate)
        self.AddExecutor(A, C.Mirrorjade, self.MirrorjadeActivate)
        self.AddExecutor(A, C.SuperPolymerization, self.SuperPolyActivate)
        self.AddExecutor(A, C.FallenAndVirtuous, self.FallenAndVirtuousActivate)
        self.AddExecutor(A, C.Aluber, self.AluberActivate)
        self.AddExecutor(A, C.FallenOfAlbaz, self.AlbazActivate)
        self.AddExecutor(A, C.Granguignol, self.GranguignolActivate)
        self.AddExecutor(A, C.DespianQuaeritis, self.QuaeritisActivate)
        self.AddExecutor(A, C.Mixousia, self.MixousiaActivate)
        self.AddExecutor(A, C.ThreeChampions, self.ChampionsActivate)
        self.AddExecutor(A, C.HyperinvokedAeon, self.AeonActivate)
        # summon / search triggers and End Phase effects
        self.AddExecutor(A, C.WhiteDragon, self.WhiteDragonTrigger)
        self.AddExecutor(A, C.SpringansKitt, self.KittRevive)
        self.AddExecutor(A, C.GuidingQuem, self.QuemActivate)
        self.AddExecutor(A, C.DogmatikaEcclesia, self.DogmatikaEcclesiaTrigger)
        self.AddExecutor(A, C.AlbionBranded, self.AlbionBrandedActivate)
        self.AddExecutor(A, C.LubellionSearing, self.LubellionActivate)
        self.AddExecutor(A, C.Titaniklad, self.Always)
        self.AddExecutor(A, C.DogmaDragon, self.DogmaDragonActivate)
        self.AddExecutor(A, C.BrandedInHighSpirits, self.HighSpiritsReturn)
        # main phase combo
        self.AddExecutor(A, C.AlbionTheShroudedDragon, self.AlbionShroudedCycle)
        self.AddExecutor(A, C.WhiteDragon, self.WhiteDragonSelf)
        self.AddExecutor(NS, C.IncredibleEcclesia, self.IncredibleEcclesiaSummon)
        self.AddExecutor(A, C.IncredibleEcclesia, self.IncredibleEcclesiaActivate)
        self.AddExecutor(SS, C.EcclesiaDarkDragon, self.EcclesiaDarkDragonSummon)
        self.AddExecutor(A, C.EcclesiaDarkDragon, self.EcclesiaDarkDragonActivate)
        self.AddExecutor(A, C.BrandedOpening, self.BrandedOpeningActivate)
        self.AddExecutor(A, C.BrandedInHighSpirits, self.HighSpiritsActivate)
        self.AddExecutor(NS, C.Aluber, self.AluberSummon)
        self.AddExecutor(NS, C.WhiteDragon, self.WhiteDragonSummon)
        self.AddExecutor(A, C.BrandedFusion, self.BrandedFusionActivate)
        self.AddExecutor(A, C.BlazingCartesia, self.CartesiaActivate)
        self.AddExecutor(A, C.SpringansKitt, self.KittSelf)
        self.AddExecutor(NS, C.GuidingQuem, self.QuemSummon)
        self.AddExecutor(NS, C.IncredibleEcclesia, self.LateSummon)  # a body whose quick effect fuses on their turn
        self.AddExecutor(NS, C.BlazingCartesia, self.CartesiaSummon)
        self.AddExecutor(A, C.AlbionTheShroudedDragon, self.AlbionShroudedSummon)
        self.AddExecutor(A, C.DogmatikaEcclesia, self.DogmatikaEcclesiaSelf)
        self.AddExecutor(NS, C.DogmatikaEcclesia, self.DogmatikaEcclesiaSummon)
        self.AddExecutor(A, C.NadirServant, self.NadirActivate)
        self.AddExecutor(NS, C.SpringansKitt, self.LateSummon)
        self.AddExecutor(NS, C.FallenOfAlbaz, self.LateSummon)
        self.AddExecutor(NS, self.NoOtherSummon)
        self.AddExecutor(SS, C.ThreeChampions, self.ChampionsSummon)
        self.AddExecutor(SS, C.IncredibleEcclesia, self.Always)
        self.AddExecutor(SS, self.NoOtherSpSummon)
        self.AddExecutor(A, C.FallenAndVirtuous, self.FallenAndVirtuousDump)
        self.AddExecutor(A, C.GoldSarcophagus, self.GoldSarcophagusActivate)
        # backrow, positions
        self.AddExecutor(SET, C.BrandedRetribution, self.SetBackrow)
        self.AddExecutor(SET, C.SuperPolymerization, self.SetBackrow)
        self.AddExecutor(SET, C.FallenAndVirtuous, self.SetBackrow)
        self.AddExecutor(SET, self.NoOtherSet)
        self.AddExecutor(ExecutorType.MonsterSet, self.NoMonsterSet)
        self.AddExecutor(ExecutorType.Repos, self.DefaultMonsterRepos)
        self.usedEffects = set()   # own effect descriptions resolved this turn
        self.usedCards = set()     # own cards whose (only) effect resolved this turn (Spells)
        self.sentToGY = set()      # ids of own cards sent to the GY this turn (End Phase "sent this turn" effects)
        self.normalSummoned = False
        self.albionPick = 0        # the Branded Spell/Trap Albion the Branded Dragon's End Phase effect picked

    # --- bookkeeping ------------------------------------------------------------------------------------
    def OnNewTurn(self):
        self.usedEffects.clear()
        self.usedCards.clear()
        self.sentToGY.clear()
        self.normalSummoned = False
        super().OnNewTurn()

    def OnSummoning(self):
        if self.Duel.Player == 0:
            self.normalSummoned = True
        super().OnSummoning()

    def OnChainSolved(self, chainIndex):
        chain = self.Duel.GetCurrentSolvingChainInfo()
        if chain is not None and chain.ActivatePlayer == 0:
            self.usedEffects.add(chain.ActivateDescription)
            self.usedCards.add(chain.ActivateId)
        super().OnChainSolved(chainIndex)

    def OnMove(self, card, previousControler, previousLocation, currentControler, currentLocation):
        if card is not None and currentControler == 0 and currentLocation == CardLocation.Grave:
            self.sentToGY.add(card.Id)
        super().OnMove(card, previousControler, previousLocation, currentControler, currentLocation)

    def Used(self, desc):
        return desc in self.usedEffects

    def Always(self):
        return True

    # --- board helpers ----------------------------------------------------------------------------------
    def MyTurn(self):
        return self.Duel.Player == 0

    def Field(self, *ids):
        return [c for c in self.Bot.GetMonsters() if c.IsFaceup() and (not ids or c.IsCode(*ids))]

    def InDeck(self, *ids):
        return any(c.IsCode(*ids) for c in self.Bot.Deck)

    def InExtra(self, *ids):
        return any(c.IsCode(*ids) for c in self.Bot.ExtraDeck)

    def InGrave(self, *ids):
        return any(c.IsCode(*ids) for c in self.Bot.Graveyard)

    def InHand(self, *ids):
        return any(c.IsCode(*ids) for c in self.Bot.Hand)

    def AlbazOnFieldOrGY(self):
        return bool(self.Field(*ALBAZ_NAMED)) or self.InGrave(*ALBAZ_NAMED)

    def EnemyHasMonsters(self):
        return self.Enemy.GetMonsterCount() > 0

    def EnemyFaceup(self):
        return [c for c in self.Enemy.GetMonsters() + self.Enemy.GetSpells() if c.IsFaceup()]

    def WhiteDragonTriggerReady(self):
        return not self.Used(WD_ECCLESIA)

    def EcclesiaAvailable(self):
        """Incredible Ecclesia for White Dragon's trigger (Deck, hand or GY) when it is not already on the field."""
        return not self.Field(C.IncredibleEcclesia) and \
            (self.InDeck(C.IncredibleEcclesia) or self.InGrave(C.IncredibleEcclesia) or self.InHand(C.IncredibleEcclesia))

    def BFPlanned(self):
        return self.InHand(C.BrandedFusion) and C.BrandedFusion not in self.usedCards and \
            self.InDeck(C.FallenOfAlbaz, C.WhiteDragon)

    def SynchroPlanned(self):
        """Ecclesia and the Dark Dragon is still to come: keep Fusion-only locks (Opening, Branded Fusion) for later."""
        if self.BFPlanned() or not self.InExtra(C.EcclesiaDarkDragon) or self.Field(C.EcclesiaDarkDragon) or \
                any(c.IsCode(C.EcclesiaDarkDragon) for c in self.Bot.Banished + self.Bot.Graveyard):
            return False
        if self.FusionLocked() or C.NadirServant in self.usedCards or self.Used(DE_SEARCH):
            return False
        tuner = self.Field(C.IncredibleEcclesia, C.GuidingQuem)
        non_tuner = [c for c in self.Field() if not c.IsTuner() and c.Level == 4 and not c.IsCode(*KEEP_ON_FIELD) and
                     (self.Spent(c) or c.IsCode(*ALBAZ_NAMED))]
        wd_hand = self.InHand(C.WhiteDragon) and not self.Used(WD_SELF)
        ie_coming = self.WhiteDragonTriggerReady() and self.EcclesiaAvailable()
        ie_quick = self.Field(C.IncredibleEcclesia) and not self.Used(IE_QUICK) and self.InDeck(C.WhiteDragon) and \
            self.WhiteDragonTriggerReady()
        ie_ns = self.InHand(C.IncredibleEcclesia) and self.InDeck(C.WhiteDragon) and self.WhiteDragonTriggerReady() and \
            self.CanNormalSummon()
        return bool((wd_hand and ie_coming) or (tuner and non_tuner) or ie_quick or ie_ns)

    def FusionLocked(self):
        """Branded Opening / Branded Fusion / Lubellion: only Fusion Monsters from the Extra Deck this turn."""
        return C.BrandedOpening in self.usedCards or C.BrandedFusion in self.usedCards or \
            self.Used(S(C.LubellionSearing, 0))

    def Owned(self, card_id):
        """Copies in hand plus Set / face-up in the Spell & Trap Zone."""
        return sum(1 for c in self.Bot.Hand if c.IsCode(card_id)) + \
            sum(1 for c in self.Bot.GetSpells() if c.IsCode(card_id))

    def CanNormalSummon(self):
        return self.MyTurn() and not self.normalSummoned

    def MainPhase(self):
        return self.Duel.Phase in (DuelPhase.Main1, DuelPhase.Main2)

    def EDPending(self):
        """Extra Deck summons still to come this turn (Nadir Servant / Dogmatika Ecclesia lock the Extra Deck)."""
        if self.SynchroPlanned() or self.BFPlanned():
            return True
        return bool(self.Field(C.BlazingCartesia)) and not self.Used(CARTESIA_FUSION) and self.CartesiaFusionMaterials()

    def Spent(self, card):
        """A face-up monster of ours whose job this turn is done: Fusion material."""
        if card.IsCode(*KEEP_ON_FIELD) or card.IsCode(*HAND_TRAPS):
            return False
        if card.IsCode(C.Aluber):
            return self.Used(ALUBER_SEARCH)
        if card.IsCode(C.GuidingQuem):
            return self.Used(QUEM_SEND)
        if card.IsCode(C.DogmatikaEcclesia):
            return True
        if card.IsCode(C.WhiteDragon):
            return self.Used(WD_ECCLESIA)
        return True

    def HandFodder(self, c):
        """A monster in hand with nothing better to do this turn: Cartesia's Fusion material."""
        if not c.IsMonster() or c.IsCode(*HAND_TRAPS) or c.IsCode(C.BlazingCartesia, C.WhiteDragon, C.IncredibleEcclesia):
            return False
        if c.IsCode(C.Aluber, C.GuidingQuem):
            return not self.CanNormalSummon()
        if c.IsCode(C.DogmatikaEcclesia):
            return not any(m.IsExtraCard() for m in self.Field())
        return True

    def CartesiaFusionMaterials(self):
        """Two spent bodies (or an Albaz-named one and an Extra Deck monster for Mirrorjade) Cartesia can fuse."""
        spent = [c for c in self.Field() if self.Spent(c)] + [c for c in self.Bot.Hand if self.HandFodder(c)]
        albaz = [c for c in self.Field(*ALBAZ_NAMED)] + [c for c in self.Bot.Hand if c.IsCode(C.FallenOfAlbaz)]
        extra = [c for c in self.Field() if c.IsExtraCard() and not c.IsCode(C.Mirrorjade)]
        if albaz and extra and self.InExtra(C.Mirrorjade) and not self.Field(C.Mirrorjade):
            return True
        return len(spent) >= 2

    # --- rankings ---------------------------------------------------------------------------------------
    def Pick(self, cards, ids, min_, max_):
        picked = []
        for id_ in ids:
            for c in cards:
                if c.IsCode(id_) and c not in picked:
                    picked.append(c)
                    break
        return self.Util.CheckSelectCount(picked, cards, min_, max_) if picked else None

    def Ranked(self, cards, key, min_, max_):
        return self.Util.CheckSelectCount(sorted(cards, key=key)[:max(min_, 1)], cards, min_, max_)

    def ExtraDumpRank(self, c):
        """Extra Deck monster to send to the GY as a cost: the End Phase 'sent this turn' effects first."""
        if c.IsCode(C.DogmaDragon):
            return 0 if C.DogmaDragon not in self.sentToGY and not self.Used(DOGMA_EP) else 5
        if c.IsCode(C.AlbionBranded):
            return 1 if C.AlbionBranded not in self.sentToGY and not self.Used(ALBION_EP) else 6
        if c.IsCode(C.Titaniklad):
            return 2 if not self.Used(TITAN_EP) else 7
        order = (C.LubellionSearing, C.Secreterion, C.HyperinvokedAeon, C.Granguignol, C.Mixousia, C.ThreeChampions,
                 C.DespianQuaeritis, C.Rindbrumm, C.EcclesiaDarkDragon, C.Mirrorjade)
        return 8 + next((k for k, cid in enumerate(order) if c.IsCode(cid)), 0)

    def DiscardRank(self, c):
        """Lower is better to discard: dead cards and GY-useful ones first, interruptions and starters last."""
        if c.IsCode(C.FallenOfAlbaz):
            return 0   # in the GY it enables Cartesia, Kitt / Quem revivals
        if c.IsCode(C.GoldSarcophagus):
            return 1
        if c.IsCode(C.NadirServant):
            # Nadir adds White Dragon, which Special Summons itself and an Ecclesia under Nadir's lock
            wd_line = self.InDeck(C.WhiteDragon) and not self.InHand(C.WhiteDragon) and not self.Used(WD_SELF)
            return 4 if wd_line and C.NadirServant not in self.usedCards else 1
        if c.IsCode(C.BrandedOpening):
            return 2 if sum(1 for h in self.Bot.Hand if h.IsCode(C.BrandedOpening)) > 1 or C.BrandedOpening in self.usedCards else 9
        if c.IsCode(C.BrandedInHighSpirits):
            revealable = any(h.IsMonster() and self.RevealRank(h) < 8 for h in self.Bot.Hand)
            return 3 if revealable and C.BrandedInHighSpirits not in self.usedCards else 1
        if c.IsCode(C.AlbionTheShroudedDragon, C.DogmatikaEcclesia, C.SpringansKitt):
            return 3
        if c.IsCode(C.Aluber):
            return 4 if self.Used(ALUBER_SEARCH) or not self.CanNormalSummon() else 8
        if c.IsCode(C.GuidingQuem):
            return 5
        if c.IsCode(C.WhiteDragon):
            return 4 if self.Used(WD_SELF) else 10
        if c.IsCode(C.BrandedFusion):
            return 4 if C.BrandedFusion in self.usedCards else 9
        if c.IsCode(C.BlazingCartesia, C.IncredibleEcclesia):
            return 7
        if c.IsCode(C.BrandedRetribution, C.FallenAndVirtuous, C.SuperPolymerization):
            return 11 if self.Owned(c.Id) <= 1 else 3  # a second copy adds nothing to the board
        if c.IsCode(*HAND_TRAPS):
            return 12
        return 6

    def ReviveOrder(self):
        """Albaz / Albaz-mentioning monster to Special Summon (Kitt, Quem, Ecclesia and the Dark Dragon...)."""
        order = []
        if self.WhiteDragonTriggerReady():
            order.append(C.WhiteDragon)
        if not self.Field(C.BlazingCartesia) and not self.InHand(C.BlazingCartesia):
            order.append(C.BlazingCartesia)
        if not self.Field(C.IncredibleEcclesia) and not self.InHand(C.IncredibleEcclesia):
            order.append(C.IncredibleEcclesia)
        if not self.Used(QUEM_SEND):
            order.append(C.GuidingQuem)
        return order + [C.BlazingCartesia, C.IncredibleEcclesia, C.WhiteDragon, C.GuidingQuem, C.AlbionTheShroudedDragon,
                        C.FallenOfAlbaz, C.SpringansKitt, C.DogmatikaEcclesia]

    def AlbazSearchOrder(self):
        """Fallen of Albaz or a monster that mentions it, to hand (High Spirits, Mercourier, Nadir)."""
        order = []
        if not self.InHand(C.WhiteDragon) and not self.Used(WD_SELF):
            order.append(C.WhiteDragon)
        if not self.InHand(C.IncredibleEcclesia) and self.CanNormalSummon():
            order.append(C.IncredibleEcclesia)
        if not self.InHand(C.BlazingCartesia) and not self.Field(C.BlazingCartesia):
            order.append(C.BlazingCartesia)
        return order + [C.WhiteDragon, C.IncredibleEcclesia, C.BlazingCartesia, C.GuidingQuem, C.DogmatikaEcclesia,
                        C.SpringansKitt, C.FallenOfAlbaz, C.TriBrigadeMercourier, C.AlbionTheShroudedDragon]

    def BrandedSearchOrder(self):
        """Aluber: a Branded Spell/Trap."""
        order = []
        owned_ret = self.InHand(C.BrandedRetribution) or self.Bot.HasInSpellZone(C.BrandedRetribution)
        if not owned_ret:
            order.append(C.BrandedRetribution)
        if not self.InHand(C.BrandedFusion) and C.BrandedFusion not in self.usedCards and \
                not self.Field(C.EcclesiaDarkDragon) and self.InDeck(C.FallenOfAlbaz, C.WhiteDragon) and \
                not self.SynchroPlanned():
            order.append(C.BrandedFusion)
        return order + [C.FallenAndVirtuous, C.BrandedRetribution, C.BrandedInHighSpirits, C.BrandedFusion,
                        C.BrandedOpening]

    def SetSearchOrder(self):
        """Albion the Branded Dragon's End Phase Set / Retribution's add: a Branded Spell/Trap."""
        order = []
        if not self.Bot.HasInSpellZone(C.BrandedRetribution) and not self.InHand(C.BrandedRetribution):
            order.append(C.BrandedRetribution)
        return order + [C.FallenAndVirtuous, C.BrandedRetribution, C.BrandedInHighSpirits, C.BrandedFusion, C.BrandedOpening]

    def FusionTargetOrder(self):
        """Fusion Monster to make with our own materials (Cartesia, Branded Fusion)."""
        return [C.Mirrorjade, C.Rindbrumm, C.DespianQuaeritis, C.Mixousia, C.AlbionBranded, C.LubellionSearing,
                C.Granguignol, C.DogmaDragon, C.HyperinvokedAeon, C.Titaniklad, C.Secreterion]

    def RemovalFusionOrder(self):
        """Fusion Monster to make with the opponent's monsters (Fallen of Albaz, Super Polymerization)."""
        return [C.Mirrorjade, C.DogmaDragon, C.HyperinvokedAeon, C.Rindbrumm, C.Mixousia, C.AlbionBranded,
                C.LubellionSearing, C.Titaniklad, C.DespianQuaeritis, C.Secreterion, C.Granguignol]

    def MaterialRank(self, c):
        """Our own Fusion / Synchro material: the Deck, then spent bodies and the GY, keep interruptions."""
        if c.Controller == 1:
            return -10 - c.Attack / 10000.0
        if c.Location == CardLocation.Deck:
            return 0
        if c.Location == CardLocation.Grave:
            return 1
        if c.Location == CardLocation.MonsterZone:
            if c.IsCode(*KEEP_ON_FIELD):
                return 8
            return 2 if self.Spent(c) else 5
        if c.Location == CardLocation.Hand:
            return (3 if self.HandFodder(c) else 12) + self.DiscardRank(c) / 20.0
        return 6

    # --- opponent's turn --------------------------------------------------------------------------------
    def DrollActivate(self):
        return self.Duel.Player == 1

    def RetributionActivate(self):
        if self.ActivateDescription == RET_ADD:
            return self.MyTurn() and any(c.IsSpell() or c.IsTrap() for c in self.Bot.Graveyard
                                         if c.IsCode(C.FallenAndVirtuous, C.BrandedFusion, C.BrandedOpening))
        return self.Duel.LastChainPlayer == 1

    def RindbrummActivate(self):
        if self.ActivateDescription == RIND_REVIVE:
            return self.Duel.Player == 1 and self.EnemyHasMonsters()
        return self.Duel.LastChainPlayer == 1

    def MercourierActivate(self):
        if self.ActivateDescription in (MERC_SEARCH, -1):
            return True
        return self.Duel.LastChainPlayer == 1

    def MirrorjadeActivate(self):
        if self.ActivateDescription == MJ_BANISH or self.Card.Location == CardLocation.MonsterZone:
            return self.EnemyHasMonsters() and (self.Duel.Player == 1 or self.Duel.Phase == DuelPhase.Main1)
        return True  # the End Phase destroy

    def SuperPolyActivate(self):
        return self.Duel.Player == 1 and self.EnemyHasMonsters()

    def FallenAndVirtuousActivate(self):
        if self.Duel.Player == 1:
            return bool(self.EnemyFaceup())
        return False  # our turn: Set it

    def AluberActivate(self):
        if self.ActivateDescription == ALUBER_NEGATE:
            return self.EnemyHasMonsters()
        return True  # search

    def AlbazActivate(self):
        """Fallen of Albaz's summon trigger: fuse with the opponent's monsters."""
        return self.EnemyHasMonsters()

    def GranguignolActivate(self):
        return True

    def QuaeritisActivate(self):
        if self.ActivateDescription == QUAER_ATK or (self.Card.Location == CardLocation.MonsterZone and
                                                     self.ActivateDescription != QUAER_FLOAT):
            return self.Duel.Player == 1 and any(c.Attack >= 2500 for c in self.Enemy.GetMonsters())
        return True

    def MixousiaActivate(self):
        if self.ActivateDescription == MIX_FUSION:
            return self.Duel.Player == 1 and self.EnemyHasMonsters()
        return False

    def ChampionsActivate(self):
        if self.ActivateDescription == CHAMP_NEGATE:
            return bool(self.EnemyFaceup())
        return True

    def AeonActivate(self):
        return self.ActivateDescription == AEON_BANISH

    # --- triggers ---------------------------------------------------------------------------------------
    def WhiteDragonTrigger(self):
        # -1: a trigger's yes/no prompt carries no effect string; White Dragon's only trigger is this one
        return self.ActivateDescription in (WD_ECCLESIA, -1)  # Special Summon an Ecclesia

    def KittRevive(self):
        if self.ActivateDescription not in (KITT_REVIVE, -1):
            return False
        return any(c.IsCode(*self.ReviveOrder()) for c in self.Bot.Graveyard if c.IsMonster() and not c.IsCode(C.SpringansKitt))

    def QuemActivate(self):
        return True

    def DogmatikaEcclesiaTrigger(self):
        if self.ActivateDescription not in (DE_SEARCH, -1):
            return False
        # the search locks the Extra Deck for the rest of the turn
        return not self.MyTurn() or not self.EDPending()

    def AlbionBrandedActivate(self):
        return True

    def LubellionActivate(self):
        return any(self.DiscardRank(c) <= 6 for c in self.Bot.Hand)

    def DogmaDragonActivate(self):
        if self.ActivateDescription == DOGMA_SHUFFLE or (self.ActivateDescription == -1 and
                                                         self.Duel.Phase != DuelPhase.End):
            return bool(self.Enemy.Graveyard)  # shuffle: only the opponent's cards
        return True

    def HighSpiritsReturn(self):
        return self.ActivateDescription in (HS_ADD, -1)

    # --- main phase -------------------------------------------------------------------------------------
    def AlbionShroudedCycle(self):
        """From the hand: send an Albaz from the Deck, put Albion on the bottom, draw 1."""
        return self.MyTurn() and self.Card.Location == CardLocation.Hand and \
            (self.InDeck(C.FallenOfAlbaz) or sum(1 for c in self.Bot.Deck if c.IsCode(C.WhiteDragon)) >= 2 or
             self.InDeck(C.BrandedOpening, C.BrandedInHighSpirits))

    def AlbionShroudedSummon(self):
        return self.MyTurn() and self.Card.Location == CardLocation.Grave and \
            any(self.DiscardRank(c) <= 3 for c in self.Bot.Hand)

    def WhiteDragonSelf(self):
        return self.MyTurn() and self.ActivateDescription == WD_SELF and not self.Used(WD_SELF)

    def IncredibleEcclesiaSummon(self):
        # keep the Normal Summon for Aluber when White Dragon comes another way (in hand, or High Spirits)
        wd_other = (self.InHand(C.WhiteDragon) and not self.Used(WD_SELF)) or \
            (self.InHand(C.BrandedInHighSpirits) and C.BrandedInHighSpirits not in self.usedCards and
             self.InDeck(C.WhiteDragon))
        if self.HighSpiritsReady():
            return False  # High Spirits first: reveal (discard) Ecclesia, add White Dragon, which revives it
        return self.InDeck(C.WhiteDragon) and self.WhiteDragonTriggerReady() and not self.Used(IE_QUICK) and \
            not (wd_other and self.InHand(C.Aluber) and not self.Used(ALUBER_SEARCH))

    def IncredibleEcclesiaActivate(self):
        if self.Duel.Phase == DuelPhase.End:
            return True  # End Phase: back to hand
        if self.MyTurn():
            # tribute it for White Dragon, whose trigger brings it back: Ecclesia and the Dark Dragon
            return self.InDeck(C.WhiteDragon) and self.WhiteDragonTriggerReady() and not self.Field(*ALBAZ_NAMED) \
                and self.Duel.Phase == DuelPhase.Main1
        return self.EnemyHasMonsters() and (self.InDeck(C.FallenOfAlbaz) or self.InHand(C.FallenOfAlbaz))

    def EcclesiaDarkDragonSummon(self):
        return not self.BFPlanned()

    def EcclesiaDarkDragonActivate(self):
        if self.ActivateDescription == EDD_SHUFFLE:
            return False  # its shuffle would return our own Fusion Monster
        if self.MyTurn():
            return self.Duel.Phase == DuelPhase.Main1
        return self.EnemyHasMonsters() and (self.InDeck(C.FallenOfAlbaz) or self.InGrave(C.FallenOfAlbaz, C.WhiteDragon))

    def BrandedOpeningActivate(self):
        if not self.MyTurn() or not self.MainPhase() or self.Duel.CurrentChain or self.SynchroPlanned():
            return False
        if not self.InDeck(C.Aluber, C.GuidingQuem):
            return False
        return any(c != self.Card and self.DiscardRank(c) <= 9 for c in self.Bot.Hand)

    def AluberSummon(self):
        return not self.Used(ALUBER_SEARCH)

    def BrandedFusionActivate(self):
        return self.MyTurn() and self.InDeck(C.FallenOfAlbaz, C.WhiteDragon)

    def CartesiaActivate(self):
        if self.ActivateDescription == CARTESIA_ADD or self.Duel.Phase == DuelPhase.End:
            return True  # End Phase: back to hand
        if self.ActivateDescription == CARTESIA_SS:
            return self.MyTurn()  # Special Summon itself (an Albaz on the field / in the GY)
        if not self.MyTurn():
            return self.EnemyHasMonsters() or self.Duel.LastChainPlayer == 1
        return not self.SynchroPlanned() and self.CartesiaFusionMaterials()

    def KittSelf(self):
        return self.MyTurn() and self.ActivateDescription == KITT_SELF

    def QuemSummon(self):
        return not self.Used(QUEM_SEND)

    def CartesiaSummon(self):
        return not self.AlbazOnFieldOrGY() and not self.Used(CARTESIA_SS)

    def HighSpiritsActivate(self):
        if self.ActivateDescription in (HS_ADD, -1):
            return False
        return self.HighSpiritsReady()

    def HighSpiritsReady(self):
        if not self.MyTurn() or not self.MainPhase() or self.Duel.CurrentChain or C.BrandedInHighSpirits in self.usedCards:
            return False
        if not self.InHand(C.BrandedInHighSpirits):
            return False
        return any(c.IsMonster() and self.RevealRank(c) < 8 for c in self.Bot.Hand)

    def RevealRank(self, c):
        """High Spirits: the monster to reveal and discard."""
        if c.IsCode(C.FallenOfAlbaz, C.AlbionTheShroudedDragon, C.DogmatikaEcclesia, C.SpringansKitt):
            return 0
        if c.IsCode(C.GuidingQuem):
            return 1 if not self.CanNormalSummon() or self.InHand(C.Aluber, C.IncredibleEcclesia) else 6
        if c.IsCode(C.Aluber):
            return 2 if self.Used(ALUBER_SEARCH) else 9
        if c.IsCode(C.WhiteDragon):
            return 3 if self.Used(WD_SELF) else 9
        if c.IsCode(*HAND_TRAPS):
            return 9
        return 5

    def DogmatikaEcclesiaSelf(self):
        if self.ActivateDescription != DE_SS:
            return False
        return self.MyTurn()

    def DogmatikaEcclesiaSummon(self):
        return not self.EDPending()

    def NadirActivate(self):
        return self.MyTurn() and not self.EDPending() and C.NadirServant not in self.usedCards

    def LateSummon(self):
        return True

    def GoldSarcophagusActivate(self):
        # turn 1 it is kept as discard fodder (Opening, Super Polymerization, Lubellion); later turns it banishes
        # White Dragon / a Set card for two turns on
        return self.MyTurn() and self.Duel.Turn > 1 and not self.EDPending()

    def SetBackrow(self):
        """One copy of each: a second Set copy is the same interruption, kept in hand it is a card."""
        return self.MyTurn() and not any(c.IsCode(self.Card.Id) for c in self.Bot.GetSpells())

    def WhiteDragonSummon(self):
        return self.WhiteDragonTriggerReady() and not (self.InHand(C.WhiteDragon) and not self.Used(WD_SELF) and
                                                       sum(1 for c in self.Bot.Hand if c.IsCode(C.WhiteDragon)) == 1)

    def NoOtherSummon(self):
        return False  # hand traps and spent starters stay in hand

    def ChampionsSummon(self):
        """The Three Champions of Swordsoul from a spent Tuner (Quem) and a spent non-Tuner: it adds Cartesia."""
        tuners = [c for c in self.Field(C.GuidingQuem) if self.Spent(c)]
        others = [c for c in self.Field() if self.Spent(c) and not c.IsTuner() and c.Level == 4]
        return bool(tuners) and bool(others) and not self.EDPendingNoChampions()

    def EDPendingNoChampions(self):
        return self.SynchroPlanned() or self.BFPlanned()

    def NoOtherSpSummon(self):
        return False

    def FallenAndVirtuousDump(self):
        """Our turn: send Dogma Dragon from the Extra Deck as the cost (End Phase: add Mercourier), destroying a
        spent monster of ours, when Dogma Dragon has no other way to the GY. One Set copy stays the interruption."""
        if not self.MyTurn() or self.Duel.CurrentChain or self.EDPending():
            return False
        if not self.InExtra(C.DogmaDragon) or C.DogmaDragon in self.sentToGY or self.Used(DOGMA_EP) or \
                not self.InDeck(C.TriBrigadeMercourier):
            return False
        if not any(self.Spent(c) for c in self.Field()):
            return False
        other_dump = (self.InHand(C.WhiteDragon) and not self.Used(WD_SELF)) or \
            (self.InHand(C.BrandedInHighSpirits) and C.BrandedInHighSpirits not in self.usedCards) or \
            (self.InHand(C.NadirServant) and C.NadirServant not in self.usedCards)
        return not other_dump

    def NoOtherSet(self):
        return False

    def NoMonsterSet(self):
        return False

    # --- prompts ----------------------------------------------------------------------------------------
    def OnSelectOption(self, options):
        def index(desc):
            return options.index(desc) if desc in options else -1
        if ALBION_SET in options:
            # Set a card the backrow doesn't have yet; a second copy is worth more in hand
            already = self.albionPick and any(c.IsCode(self.albionPick) for c in self.Bot.GetSpells())
            if not already or len(options) < 2:
                return index(ALBION_SET)
            return next(k for k in range(len(options)) if options[k] != ALBION_SET)
        for want in (OPENING_SS, TITAN_SS, QUAER_SS):
            if want in options:
                return index(want)
        if FV_DESTROY in options:
            return index(FV_DESTROY)
        return super().OnSelectOption(options)

    def OnSelectYesNo(self, desc):
        if desc in ALWAYS_YES:
            return True
        if desc == RIND_BOUNCE:
            return self.EnemyHasMonsters()
        return super().OnSelectYesNo(desc)

    def OnSelectSynchroMaterial(self, cards, mandatoryCards, sum_, min_, max_):
        return self.Ranked(cards, self.SynchroRank, min_, max_) if min_ <= len(cards) else None

    def SynchroRank(self, c):
        if c.IsCode(C.WhiteDragon, C.FallenOfAlbaz):
            return 0
        if c.IsCode(C.IncredibleEcclesia):
            return 1 if self.Used(IE_QUICK) else 2
        if c.IsCode(C.GuidingQuem, C.Aluber, C.DogmatikaEcclesia, C.SpringansKitt):
            return 3
        if c.IsCode(C.BlazingCartesia):
            return 9
        return 5

    def OnSelectSum(self, cards, mandatoryCards, sum_, min_, max_, hint, exactEqual):
        if hint == HintMsg.SynchroMaterial:
            ordered = sorted(cards, key=self.SynchroRank)
            return self.AI.FindSumSelection(ordered, mandatoryCards, sum_, min_, max_, exactEqual)
        return super().OnSelectSum(cards, mandatoryCards, sum_, min_, max_, hint, exactEqual)

    def OnSelectCard(self, cards, min_, max_, hint, cancelable):
        if self.AI.HaveSelectedCards():
            return None
        solving = self.Duel.GetCurrentSolvingChainInfo()
        activating = self.Duel.GetCurrentChainCard()
        source = solving.ActivateId if solving is not None else (activating.Id if activating is not None else 0)
        desc = solving.ActivateDescription if solving is not None else -1
        locs = {c.Location for c in cards}
        mine = all(c.Controller == 0 for c in cards)

        # costs and generic prompts
        if hint == HintMsg.Discard and mine:
            return self.Ranked(cards, self.DiscardRank, min_, max_)
        if hint == HintMsg.SynchroMaterial:
            return self.Ranked(cards, self.SynchroRank, min_, max_)
        if locs == {CardLocation.Extra} and hint in (HintMsg.ToGrave, HintMsg.Confirm, HintMsg.Select) and \
                source != C.BrandedFusion and hint != HintMsg.SpSummon:
            if not (source == C.Granguignol):
                return self.Ranked(cards, self.ExtraDumpRank, min_, max_)

        if source == C.WhiteDragon and hint == HintMsg.SpSummon:
            order = [C.IncredibleEcclesia] if not self.Field(C.IncredibleEcclesia) else []
            return self.Pick(cards, order + [C.DogmatikaEcclesia, C.IncredibleEcclesia], min_, max_)
        if source == C.IncredibleEcclesia and hint == HintMsg.SpSummon:
            first = [C.WhiteDragon] if self.MyTurn() and self.WhiteDragonTriggerReady() else [C.FallenOfAlbaz]
            return self.Pick(cards, first + [C.FallenOfAlbaz, C.WhiteDragon], min_, max_)
        if source == C.EcclesiaDarkDragon and hint == HintMsg.SpSummon:
            if not self.MyTurn():
                return self.Pick(cards, [C.FallenOfAlbaz, C.WhiteDragon], min_, max_)
            return self.Pick(cards, self.ReviveOrder(), min_, max_)
        if source in (C.SpringansKitt, C.GuidingQuem, C.Rindbrumm, C.FallenAndVirtuous) and hint == HintMsg.SpSummon:
            return self.Pick(cards, self.ReviveOrder(), min_, max_)
        if source == C.GuidingQuem and hint == HintMsg.ToGrave:
            return self.Pick(cards, self.QuemSendOrder(), min_, max_)
        if source == C.Aluber and hint == HintMsg.AddToHand:
            return self.Pick(cards, self.BrandedSearchOrder(), min_, max_)
        if source == C.BrandedOpening:
            if hint == HintMsg.Discard:
                return self.Ranked(cards, self.DiscardRank, min_, max_)
            first = [C.Aluber] if not self.Used(ALUBER_SEARCH) and not self.InHand(C.Aluber) else [C.GuidingQuem]
            return self.Pick(cards, first + [C.Aluber, C.GuidingQuem], min_, max_)
        if source == C.BrandedInHighSpirits:
            if hint == HintMsg.AddToHand and CardLocation.Grave not in locs:
                return self.Pick(cards, self.AlbazSearchOrder(), min_, max_)
            if locs == {CardLocation.Hand}:
                return self.Ranked(cards, self.RevealRank, min_, max_)
        if source in (C.NadirServant, C.TriBrigadeMercourier) and hint == HintMsg.AddToHand:
            return self.Pick(cards, self.AlbazSearchOrder(), min_, max_)
        if source in (C.DogmatikaEcclesia, C.ThreeChampions) and hint == HintMsg.AddToHand:
            order = [C.BlazingCartesia] if not self.InHand(C.BlazingCartesia) and not self.Field(C.BlazingCartesia) and \
                self.AlbazOnFieldOrGY() and not self.Used(CARTESIA_SS) else []
            if self.Owned(C.FallenAndVirtuous) == 0:
                order.append(C.FallenAndVirtuous)
            return self.Pick(cards, order + [C.IncredibleEcclesia, C.BlazingCartesia, C.FallenAndVirtuous, C.GuidingQuem,
                                             C.DogmatikaEcclesia, C.NadirServant], min_, max_)
        if source == C.FallenAndVirtuous and self.MyTurn() and hint in (HintMsg.Destroy, HintMsg.Target, HintMsg.Select):
            own = lambda c: (c.Controller != 0, not self.Spent(c) if c.IsMonster() else True, c.Attack)
            return self.Ranked(cards, own, min_, max_)
        if source == C.DogmaDragon and hint == HintMsg.AddToHand:
            return self.Pick(cards, [C.TriBrigadeMercourier, C.FallenAndVirtuous, C.SpringansKitt, C.BlazingCartesia,
                                     C.IncredibleEcclesia, C.GuidingQuem], min_, max_)
        if source == C.Titaniklad:
            first = [C.WhiteDragon] if self.WhiteDragonTriggerReady() and self.EcclesiaAvailable() else []
            return self.Pick(cards, first + [C.IncredibleEcclesia, C.BlazingCartesia, C.WhiteDragon, C.DogmatikaEcclesia,
                                             C.GuidingQuem, C.FallenOfAlbaz], min_, max_)
        if source == C.DespianQuaeritis and all(c.Location == CardLocation.Deck for c in cards):
            return self.Pick(cards, [C.FallenOfAlbaz, C.Aluber, C.GuidingQuem, C.WhiteDragon], min_, max_)
        if source == C.AlbionBranded and all(c.Location == CardLocation.Deck for c in cards):
            result = self.Pick(cards, self.SetSearchOrder(), min_, max_)
            self.albionPick = result[0].Id if result else 0
            return result
        if source == C.BrandedRetribution and hint == HintMsg.AddToHand:
            return self.Pick(cards, [C.FallenAndVirtuous, C.BrandedFusion, C.BrandedOpening, C.BrandedInHighSpirits], min_, max_)
        if source == C.Granguignol and hint == HintMsg.ToGrave:
            return self.Ranked(cards, lambda c: (self.ExtraDumpRank(c) if c.Location == CardLocation.Extra else
                                                 (3 if c.IsCode(C.AlbionTheShroudedDragon) else 20)), min_, max_)
        if source == C.Granguignol and hint == HintMsg.SpSummon:
            return self.Pick(cards, [C.DespianQuaeritis, C.DogmatikaEcclesia], min_, max_)
        if source == C.AlbionTheShroudedDragon:
            return self.Ranked(cards, self.AlbionShroudedRank, min_, max_)
        if source == C.GoldSarcophagus:
            first = [C.WhiteDragon] if not self.InHand(C.WhiteDragon) else []
            return self.Pick(cards, first + [C.SuperPolymerization, C.FallenAndVirtuous, C.BrandedRetribution,
                                             C.IncredibleEcclesia], min_, max_)
        if source in (C.BrandedFusion, C.BlazingCartesia) and hint == HintMsg.SpSummon and \
                all(c.Location == CardLocation.Extra for c in cards):
            order = self.FusionTargetOrder()
            if source == C.BrandedFusion and self.InDeck(C.SpringansKitt):
                order = [C.Rindbrumm, C.AlbionBranded] + order
            return self.Pick(cards, order, min_, max_)
        if source in (C.FallenOfAlbaz, C.SuperPolymerization) and hint == HintMsg.SpSummon and \
                all(c.Location == CardLocation.Extra for c in cards):
            return self.Pick(cards, self.RemovalFusionOrder(), min_, max_)
        if hint == HintMsg.FusionMaterial:
            return self.Ranked(cards, self.FusionMaterialRank(source), min_, max_)
        if source in (C.Mirrorjade, C.FallenAndVirtuous, C.Rindbrumm, C.Aluber, C.ThreeChampions,
                      C.HyperinvokedAeon) and not mine:
            return self.Ranked(cards, lambda c: (c.Controller == 0, -c.Attack), min_, max_)
        return super().OnSelectCard(cards, min_, max_, hint, cancelable)

    def FusionMaterialRank(self, source):
        def rank(c):
            if source == C.BrandedFusion:
                if c.IsCode(C.WhiteDragon, C.FallenOfAlbaz) and c.Location == CardLocation.Deck:
                    return -3 if c.IsCode(C.WhiteDragon) and self.InDeck(C.SpringansKitt) else -2
                if c.IsCode(C.SpringansKitt) and c.Location == CardLocation.Deck:
                    return -1
            if c.IsCode(C.TriBrigadeMercourier) and c.Location == CardLocation.Deck:
                return 3  # keep it for Dogma Dragon's End Phase search
            return self.MaterialRank(c)
        return rank

    def QuemSendOrder(self):
        revive_target = any(c.IsCode(C.WhiteDragon, C.BlazingCartesia, C.IncredibleEcclesia) for c in self.Bot.Graveyard)
        order = []
        if revive_target and not self.Used(KITT_REVIVE):
            order.append(C.SpringansKitt)
        if self.WhiteDragonTriggerReady():
            order.append(C.WhiteDragon)
        return order + [C.FallenOfAlbaz, C.AlbionTheShroudedDragon, C.SpringansKitt, C.BlazingCartesia,
                        C.BrandedRetribution, C.WhiteDragon]

    def AlbionShroudedRank(self, c):
        if c.Location == CardLocation.Deck:
            if c.IsCode(C.FallenOfAlbaz):
                return 0
            if c.IsCode(C.WhiteDragon):
                return 1
            if c.IsCode(C.BrandedOpening, C.BrandedInHighSpirits):
                return 2
            return 4
        return 3 + self.DiscardRank(c)
