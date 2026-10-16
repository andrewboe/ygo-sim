"""Mitsurugi executor for ygo-sim's mitsurugi__tcg, written for ygo-sim in WindBot's executor style (there is no
WindBot Mitsurugi executor). Sources: Konami's Mitsurugi strategy guide (the Habakiri line: Habakiri reveal ->
Saji -> Mitsurugi Ritual tributing Aramasa + Kusanagi from the Deck -> Futsu -> Mirror -> Murakumo, ending on the
three Ritual Monsters and a set Prayers / Great Purification), the card text, and lines found by goldfish search
on this list (Pre-Preparation of Rites -> Mirror + a Ritual Monster, Ragged Records, End of the World Ruler
applying Mitsurugi Ritual, Prayers tributing a Reptile for both effects, Haggard Lizardose / W:P Fancy Ball with
the spent Level 4s).

Plan: get Ritual Monsters onto the field through their own tributes (each Ritual Monster tributed searches a
"Mitsurugi" card and Special Summons itself back), spend Level 4s from the Deck as Ritual tributes (each tribute
searches), keep Murakumo on the field, and set Prayers / Great Purification: on the opponent's turn either
tributes Murakumo, which comes back and destroys their monsters.
"""
from windbot import *
from windbot_default import DefaultExecutor, _CardId
from windbot_gameai import BattlePhaseAction


class CardId:
    Habakiri = 13332685
    Murakumo = 19899073
    Futsu = 55397172
    Saji = 18176525
    Aramasa = 40543231
    Kusanagi = 82782870
    Wousu = 76948970
    MitsurugiRitual = 81560239
    Mirror = 49721684
    Prayers = 45171524
    GreatPurification = 17954937
    PrePreparation = 13048472
    RaggedRecords = 24461358
    EndOfTheWorldRuler = 3739500
    DominusImpulse = 40366667
    HaggardLizardose = 9763474
    FancyBall = 4993187
    AshBlossom = 14558127
    MulcharmyPurulia = 84192580
    MulcharmyFuwalos = 42141493
    DrollLockBird = 94145021
    CalledByTheGrave = 24224830


RITUALS = (CardId.Murakumo, CardId.Futsu, CardId.Habakiri)
LEVEL4 = (CardId.Saji, CardId.Aramasa, CardId.Kusanagi)
REPTILE = CardRace.Reptile


def S(card, n):
    return card * 16 + n


# effect descriptions (WindBot's GetStringId)
HABAKIRI_REVEAL, HABAKIRI_TRIBUTED = S(CardId.Habakiri, 0), S(CardId.Habakiri, 1)
MURAKUMO_DESTROY, MURAKUMO_QUICK, MURAKUMO_TRIBUTED = S(CardId.Murakumo, 0), S(CardId.Murakumo, 1), S(CardId.Murakumo, 2)
FUTSU_REVIVE, FUTSU_TRIBUTED = S(CardId.Futsu, 0), S(CardId.Futsu, 1)
RITUAL_FROM_DECK, RITUAL_FROM_HAND = S(CardId.MitsurugiRitual, 1), S(CardId.MitsurugiRitual, 2)
RULER_APPLY, RULER_DESTROY = S(CardId.EndOfTheWorldRuler, 0), S(CardId.EndOfTheWorldRuler, 1)
PRAYERS_TRIBUTE, PRAYERS_ADD, PRAYERS_SUMMON, PRAYERS_BOTH, PRAYERS_SUMMON_ASK = (S(CardId.Prayers, k) for k in (1, 2, 3, 4, 5))
PURIFICATION_NEGATE, PURIFICATION_REVIVE = S(CardId.GreatPurification, 0), S(CardId.GreatPurification, 1)
SELF_SUMMON_ASK = (S(CardId.Habakiri, 2), S(CardId.Murakumo, 5), S(CardId.Futsu, 2))
TRIBUTED_EFFECT = {CardId.Murakumo: MURAKUMO_TRIBUTED, CardId.Habakiri: HABAKIRI_TRIBUTED, CardId.Futsu: FUTSU_TRIBUTED,
                   CardId.Saji: S(CardId.Saji, 0), CardId.Aramasa: S(CardId.Aramasa, 0), CardId.Kusanagi: S(CardId.Kusanagi, 0)}


class MitsurugiExecutor(DefaultExecutor):
    DECK_EXECUTOR = True

    def __init__(self):
        super().__init__()
        A, SS, NS, SET = ExecutorType.Activate, ExecutorType.SpSummon, ExecutorType.Summon, ExecutorType.SpellSet
        # hand traps and the opponent's turn
        self.AddExecutor(A, CardId.AshBlossom, self.DefaultAshBlossomAndJoyousSpring)
        self.AddExecutor(A, CardId.MulcharmyPurulia, self.DefaultMaxxC)
        self.AddExecutor(A, CardId.MulcharmyFuwalos, self.DefaultMaxxC)
        self.AddExecutor(A, CardId.DrollLockBird, self.DrollActivate)
        self.AddExecutor(A, CardId.CalledByTheGrave, self.DefaultCalledByTheGrave)
        self.AddExecutor(A, CardId.Murakumo, self.MurakumoActivate)
        self.AddExecutor(A, CardId.GreatPurification, self.GreatPurificationActivate)
        self.AddExecutor(A, CardId.DominusImpulse, self.DominusImpulseActivate)
        self.AddExecutor(A, CardId.Futsu, self.FutsuActivate)
        self.AddExecutor(A, CardId.FancyBall, self.FancyBallActivate)
        # tributed / summoned triggers
        self.AddExecutor(A, CardId.Habakiri, self.TributedTrigger)
        self.AddExecutor(A, CardId.Saji, self.SearchTrigger)
        self.AddExecutor(A, CardId.Aramasa, self.SearchTrigger)
        self.AddExecutor(A, CardId.Kusanagi, self.KusanagiActivate)
        # main phase combo
        self.AddExecutor(A, CardId.Habakiri, self.HabakiriReveal)
        self.AddExecutor(A, CardId.PrePreparation, self.PrePreparationActivate)
        self.AddExecutor(A, CardId.RaggedRecords, self.RaggedRecordsActivate)
        self.AddExecutor(A, CardId.EndOfTheWorldRuler, self.RulerActivate)
        self.AddExecutor(A, CardId.MitsurugiRitual, self.MitsurugiRitualActivate)
        self.AddExecutor(A, CardId.Mirror, self.MirrorActivate)
        self.AddExecutor(NS, CardId.Saji, self.SajiSummon)
        self.AddExecutor(NS, CardId.Aramasa, self.AramasaSummon)
        self.AddExecutor(A, CardId.Prayers, self.PrayersActivate)
        self.AddExecutor(NS, CardId.Kusanagi, self.KusanagiSummon)
        self.AddExecutor(SS, CardId.HaggardLizardose, self.LizardoseSummon)
        self.AddExecutor(A, CardId.HaggardLizardose, self.LizardoseActivate)
        self.AddExecutor(SS, CardId.FancyBall, self.FancyBallSummon)
        # backrow, positions
        self.AddExecutor(SET, CardId.Prayers, self.SetPrayers)
        self.AddExecutor(SET, CardId.GreatPurification, self.SetOnce)
        self.AddExecutor(SET, CardId.DominusImpulse, self.SetOnce)
        self.AddExecutor(ExecutorType.Repos, self.DefaultMonsterRepos)
        self.usedEffects = set()        # own effect descriptions resolved this turn
        self.habakiriRevealUsed = False  # once per Duel

    # --- bookkeeping ------------------------------------------------------------------------------------
    def OnNewTurn(self):
        self.usedEffects.clear()
        super().OnNewTurn()

    def OnChainSolved(self, chainIndex):
        chain = self.Duel.GetCurrentSolvingChainInfo()
        if chain is not None and chain.ActivatePlayer == 0:
            self.usedEffects.add(chain.ActivateDescription)
            if chain.ActivateDescription == HABAKIRI_REVEAL:
                self.habakiriRevealUsed = True
        super().OnChainSolved(chainIndex)

    def Used(self, desc):
        return desc in self.usedEffects

    # --- board helpers ----------------------------------------------------------------------------------
    def Reptiles(self, cards):
        return [c for c in cards if c is not None and c.HasRace(REPTILE) and c.IsFaceup()]

    def ReptileLevels(self, include_hand=True):
        cards = self.Reptiles(self.Bot.GetMonsters()) + ([c for c in self.Bot.Hand if c.HasRace(REPTILE)] if include_hand else [])
        return sum(c.Level for c in cards)

    def RitualInHand(self):
        return [c for c in self.Bot.Hand if c.IsCode(*RITUALS)]

    def Level4InDeck(self):
        return sum(1 for c in self.Bot.Deck if c.IsCode(*LEVEL4))

    def TributeRank(self, card):
        """Lower is better to tribute: a Ritual Monster or Level 4 whose tributed effect is still unused."""
        order = (CardId.Murakumo, CardId.Habakiri, CardId.Futsu, CardId.Saji, CardId.Aramasa, CardId.Kusanagi, CardId.Wousu)
        base = next((k for k, cid in enumerate(order) if card.IsCode(cid)), 20)
        desc = TRIBUTED_EFFECT.get(card.Id)
        if desc is not None and self.Used(desc):
            base += 10
        if card.Location == CardLocation.Hand and card.IsCode(*RITUALS):
            base += 5  # keep Ritual Monsters in hand as Ritual Summon targets
        return base

    def ChooseRitualTarget(self, cards):
        """Which Ritual Monster to Ritual Summon / revive."""
        def rank(c):
            if c.IsCode(CardId.Murakumo):
                return 0 if self.Enemy.GetMonsterCount() > 0 or not self.Bot.HasInMonstersZone(CardId.Murakumo) else 2
            if c.IsCode(CardId.Futsu):
                return 1 if not self.Bot.HasInMonstersZone(CardId.Futsu) else 3
            if c.IsCode(CardId.Habakiri):
                return 2
            return 9
        return sorted(cards, key=rank)

    def MonsterSearchOrder(self):
        """Aramasa / Prayers search: what the combo needs next."""
        order = []
        if not self.Bot.HasInHand(CardId.Murakumo) and not self.Bot.HasInMonstersZone(CardId.Murakumo):
            order.append(CardId.Murakumo)
        if not self.habakiriRevealUsed and not self.Bot.HasInHand(CardId.Habakiri):
            order.append(CardId.Habakiri)
        if not self.Bot.HasInHand(CardId.Saji) and not self.Used(S(CardId.Saji, 0)):
            order.append(CardId.Saji)
        order += [CardId.Futsu, CardId.Kusanagi, CardId.Aramasa, CardId.Murakumo, CardId.Habakiri, CardId.Wousu]
        return order

    def SpellSearchOrder(self):
        """Saji / tributed-Ritual search for a Spell/Trap."""
        order = []
        has_ritual_spell = self.Bot.HasInHand([CardId.MitsurugiRitual, CardId.Mirror])
        if not has_ritual_spell and (self.RitualInHand() or self.ReptileLevels() >= 8):
            order.append(CardId.MitsurugiRitual)
        if not self.Bot.HasInHandOrInSpellZone(CardId.Prayers):
            order.append(CardId.Prayers)
        if not self.Bot.HasInHandOrInSpellZone(CardId.GreatPurification):
            order.append(CardId.GreatPurification)
        if not self.Bot.HasInHand(CardId.Mirror) and self.Bot.GetGraveyardMonsters():
            order.append(CardId.Mirror)
        order += [CardId.MitsurugiRitual, CardId.Prayers, CardId.Mirror]
        return order

    def CardSearchOrder(self):
        """Tributed Ritual Monster: add any "Mitsurugi" card."""
        order = []
        if any(c.IsCode(*RITUALS) for c in self.Bot.Graveyard) and not self.Bot.HasInHand(CardId.Mirror):
            order.append(CardId.Mirror)
        if not self.Bot.HasInHand(CardId.Murakumo) and not self.Bot.HasInMonstersZone(CardId.Murakumo):
            order.append(CardId.Murakumo)
        return order + self.SpellSearchOrder() + self.MonsterSearchOrder()

    def Pick(self, cards, ids, min_, max_):
        picked = []
        for id_ in ids:
            for c in cards:
                if c.IsCode(id_) and c not in picked:
                    picked.append(c)
                    break
        return self.Util.CheckSelectCount(picked, cards, min_, max_) if picked else None

    # --- opponent's turn --------------------------------------------------------------------------------
    def DrollActivate(self):
        return self.Duel.Player == 1

    def MurakumoActivate(self):
        if self.ActivateDescription == MURAKUMO_DESTROY:
            return self.Enemy.GetMonsterCount() > 0
        if self.ActivateDescription == MURAKUMO_QUICK:
            return self.Duel.LastChainPlayer == 1
        return True  # tributed: search, then come back

    def LevelFiveReptiles(self):
        return [c for c in self.Reptiles(self.Bot.GetMonsters()) if c.Level >= 5]

    def GreatPurificationActivate(self):
        if self.ActivateDescription == PURIFICATION_REVIVE:
            return any(c.IsCode(CardId.Murakumo, CardId.Futsu) for c in self.Bot.Graveyard) and \
                len(self.Bot.GetMonsters()) >= 1
        if self.Duel.LastChainPlayer != 1 or not self.LevelFiveReptiles():
            return False
        last = self.Util.GetLastChainCard()
        return last is not None and not self.DefaultCheckWhetherCardIsNegated(self.Card)

    def DominusImpulseActivate(self):
        return self.Duel.LastChainPlayer == 1  # only offered against an effect that Special Summons

    def FutsuActivate(self):
        if self.ActivateDescription == FUTSU_REVIVE:
            return any(c.HasRace(REPTILE) for c in self.Bot.Graveyard)
        return True

    def FancyBallActivate(self):
        return self.Duel.LastChainPlayer == 1

    def PrayersActivate(self):
        reptiles = self.Reptiles(self.Bot.GetMonsters()) + [c for c in self.Bot.Hand if c.HasRace(REPTILE)]
        if self.Duel.Player == 1:  # opponent's turn: tribute Murakumo, it returns and destroys their monsters
            return self.Bot.HasInMonstersZone(CardId.Murakumo) and not self.Used(MURAKUMO_TRIBUTED) and \
                self.Enemy.GetMonsterCount() > 0 and self.Duel.LastChainPlayer != 0
        if self.Card.Location == CardLocation.SpellZone:
            return False  # a set Prayers waits for the opponent's turn
        # own turn: a starter when nothing better is in hand
        other_starter = (not self.habakiriRevealUsed and self.Bot.HasInHand(CardId.Habakiri)) or \
            self.Bot.HasInHand([CardId.PrePreparation, CardId.RaggedRecords, CardId.MitsurugiRitual])
        return bool(reptiles) and not other_starter

    # --- triggers ---------------------------------------------------------------------------------------
    def TributedTrigger(self):
        return self.ActivateDescription != HABAKIRI_REVEAL

    def SearchTrigger(self):
        return True

    def KusanagiActivate(self):
        return any(c.HasSetcode(0x1c5) or c.IsCode(CardId.MitsurugiRitual, CardId.Prayers, CardId.Mirror, *LEVEL4, *RITUALS)
                   for c in self.Bot.Graveyard + self.Bot.Banished)

    # --- main phase -------------------------------------------------------------------------------------
    def HabakiriReveal(self):
        if self.ActivateDescription != HABAKIRI_REVEAL or self.Card.Location != CardLocation.Hand:
            return False
        return self.Level4InDeck() > 0

    def PrePreparationActivate(self):
        return self.Bot.HasInDeck(CardId.Mirror, CardId.MitsurugiRitual)

    def RaggedRecordsActivate(self):
        return self.Card.Location == CardLocation.Hand and self.Bot.HasInDeck(*RITUALS)

    def RulerActivate(self):
        if self.ActivateDescription == RULER_DESTROY:
            return False  # destroys our own board too
        return self.Bot.LifePoints > 4000 and self.Bot.HasInDeck(CardId.MitsurugiRitual) and \
            (bool(self.RitualInHand()) and self.Level4InDeck() >= 2 or self.ReptileLevels() >= 8)

    def MitsurugiRitualActivate(self):
        return (bool(self.RitualInHand()) and self.Level4InDeck() >= 1) or self.ReptileLevels() >= 8

    def MirrorActivate(self):
        if self.Card.Location == CardLocation.Grave:
            return False
        targets = [c for c in self.Bot.Graveyard + self.Bot.Hand if c.IsCode(*RITUALS)]
        return bool(targets) and self.ReptileLevels() >= 8

    def SajiSummon(self):
        return not self.Used(S(CardId.Saji, 0))

    def AramasaSummon(self):
        return not self.Used(S(CardId.Aramasa, 0))

    def KusanagiSummon(self):
        return not self.Used(S(CardId.Kusanagi, 0)) and self.KusanagiActivate()

    def SpentBodies(self):
        """Level 4s whose effects are spent: Link material."""
        return [c for c in self.Bot.GetMonsters() if c.IsFaceup() and c.IsCode(*LEVEL4)]

    def LizardoseSummon(self):
        return len(self.SpentBodies()) >= 2 or (len(self.SpentBodies()) >= 1 and
                                                 any(c.IsCode(CardId.Wousu) for c in self.Bot.GetMonsters()))

    def LizardoseActivate(self):
        return any(c.HasRace(REPTILE) and c.Attack <= 2000 for c in self.Bot.Graveyard)

    def FancyBallSummon(self):
        bodies = [c for c in self.Bot.GetMonsters() if c.IsFaceup() and not c.IsCode(*RITUALS) and c.HasType(CardType.Effect)]
        return len(bodies) >= 2 and self.Util.IsTurn1OrMain2()

    def SetPrayers(self):
        return not self.Bot.HasInSpellZone(CardId.Prayers)

    def SetOnce(self):
        return not self.Bot.HasInSpellZone(self.Card.Id)

    # --- prompts ----------------------------------------------------------------------------------------
    def OnSelectOption(self, options):
        def index(desc):
            return options.index(desc) if desc in options else -1
        if RITUAL_FROM_HAND in options or RITUAL_FROM_DECK in options:
            from_hand = bool(self.RitualInHand()) and self.Level4InDeck() >= 2
            k = index(RITUAL_FROM_HAND) if from_hand else index(RITUAL_FROM_DECK)
            return k if k >= 0 else max(index(RITUAL_FROM_HAND), index(RITUAL_FROM_DECK))
        if PRAYERS_BOTH in options:
            return index(PRAYERS_BOTH)
        if PRAYERS_ADD in options:
            return index(PRAYERS_ADD)
        return super().OnSelectOption(options)

    def OnSelectYesNo(self, desc):
        if desc == PRAYERS_TRIBUTE:
            return bool(self.Reptiles(self.Bot.GetMonsters()) or [c for c in self.Bot.Hand if c.HasRace(REPTILE)])
        if desc in SELF_SUMMON_ASK or desc == PRAYERS_SUMMON_ASK:
            return True
        return super().OnSelectYesNo(desc)

    def OnSelectSum(self, cards, mandatoryCards, sum_, min_, max_, hint, exactEqual):
        ordered = sorted(cards, key=self.TributeRank)
        return self.AI.FindSumSelection(ordered, mandatoryCards, sum_, min_, max_, exactEqual)

    def OnSelectTribute(self, cards, min_, max_, hint, cancelable):
        return self.AI.FindTributeSelection(sorted(cards, key=self.TributeRank), min_, max_)

    def OnSelectCard(self, cards, min_, max_, hint, cancelable):
        if self.AI.HaveSelectedCards():
            return None
        solving = self.Duel.GetCurrentSolvingChainInfo()
        activating = self.Duel.GetCurrentChainCard()
        source = solving.ActivateId if solving is not None else (activating.Id if activating is not None else 0)
        desc = solving.ActivateDescription if solving is not None else -1
        if hint in (HintMsg.Release, HintMsg.Tribute):
            return self.Util.CheckSelectCount(sorted(cards, key=self.TributeRank), cards, min_, max_)
        if hint == HintMsg.LinkMaterial:
            rank = lambda c: (c.IsCode(*RITUALS), not c.IsCode(*LEVEL4), c.Attack)
            return self.Util.CheckSelectCount(sorted(cards, key=rank), cards, min_, max_)
        if source == CardId.Habakiri and desc == HABAKIRI_REVEAL:
            if hint == HintMsg.SpSummon:
                first = CardId.Saji if not self.Bot.HasInHand([CardId.MitsurugiRitual, CardId.Mirror]) else CardId.Aramasa
                return self.Pick(cards, [first, CardId.Saji, CardId.Aramasa, CardId.Kusanagi], min_, max_)
            return self.Util.CheckSelectCount(sorted(cards, key=self.TributeRank), cards, min_, max_)
        if source == CardId.Saji:
            return self.Pick(cards, self.SpellSearchOrder(), min_, max_)
        if source == CardId.Aramasa:
            return self.Pick(cards, self.MonsterSearchOrder(), min_, max_)
        if source == CardId.Kusanagi:
            return self.Pick(cards, [CardId.MitsurugiRitual, CardId.Prayers, CardId.Mirror, CardId.Saji, CardId.Aramasa,
                                     CardId.Murakumo, CardId.Habakiri, CardId.Futsu], min_, max_)
        if source in RITUALS and hint == HintMsg.AddToHand:
            return self.Pick(cards, self.CardSearchOrder(), min_, max_)
        if source == CardId.Prayers:
            if hint == HintMsg.AddToHand:
                return self.Pick(cards, self.MonsterSearchOrder(), min_, max_)
            if hint == HintMsg.SpSummon:
                return self.Util.CheckSelectCount(self.ChooseRitualTarget(cards) + sorted(cards, key=self.TributeRank),
                                                  cards, min_, max_)
        if source in (CardId.Futsu, CardId.GreatPurification) and hint == HintMsg.SpSummon:
            return self.Util.CheckSelectCount(self.ChooseRitualTarget(cards), cards, min_, max_)
        if source in (CardId.MitsurugiRitual, CardId.Mirror, CardId.EndOfTheWorldRuler) and \
                hint in (HintMsg.SpSummon, HintMsg.Select) and all(c.IsCode(*RITUALS) for c in cards if c.IsMonster()):
            return self.Util.CheckSelectCount(self.ChooseRitualTarget(cards), cards, min_, max_)
        if source == CardId.EndOfTheWorldRuler and hint == HintMsg.Remove:
            return self.Pick(cards, [CardId.MitsurugiRitual, CardId.Mirror], min_, max_)
        if source in (CardId.PrePreparation, CardId.RaggedRecords):
            if all(c.IsSpell() for c in cards):
                first = CardId.Mirror if self.Bot.HasInDeck(CardId.Mirror) else CardId.MitsurugiRitual
                return self.Pick(cards, [first, CardId.MitsurugiRitual, CardId.Mirror], min_, max_)
            order = ([CardId.Habakiri] if not self.habakiriRevealUsed else []) + [CardId.Murakumo, CardId.Futsu, CardId.Habakiri]
            return self.Pick(cards, order, min_, max_)
        if source == CardId.HaggardLizardose and hint == HintMsg.Remove:
            rank = lambda c: (c.Location != CardLocation.Grave, not c.HasRace(REPTILE), not c.IsCode(*LEVEL4))
            return self.Util.CheckSelectCount(sorted(cards, key=rank), cards, min_, max_)
        return super().OnSelectCard(cards, min_, max_, hint, cancelable)
