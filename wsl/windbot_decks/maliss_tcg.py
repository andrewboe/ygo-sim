"""Maliss executor for ygo-sim's maliss__tcg (the post-Blazing Dominion TCG list: Maliss engine + Ignisters,
Dominus traps and hand traps, no White Binder / Splash Mage / Link Decoder / Apollousa), written for ygo-sim in
WindBot's executor style from the deck's current lines. The WindBot Maliss port (windbot_decks/maliss.py) plays a
different, Master Duel list; a few of its ideas (Pawn self-summons always taken, Red Ransom searching Underground,
Allied as the finisher) carry over, its rows don't.

Sources: Master Duel Meta's Maliss deck breakdown and Maliss guides (Dormouse banishing March Hare, which adds
itself back; Pawns re-summoning themselves from banishment; Red Ransom -> Underground; Wicckid banishing Cyberse
from the GY for Backup @Ignister; Allied Code Talker reviving the 2300-ATK Queens), YGOProDeck's "Maliss post
BLZD" TCG lists (this deck's 40/15), Konami's YCS Columbus coverage (Dominus Spark in Maliss), the card text
(cards.cdb) and lines found by goldfish search on this list (goldfish_lines.py: Underground / Gold Sarcophagus /
Allure banishing a Pawn to summon it, White Rabbit setting a Maliss Trap, TB-11 turning a banished Pawn into two
bodies, S:P Little Knight / W:P Fancy Ball from two spent Pawns).

Plan (turn 1): every Pawn that gets banished Special Summons itself (Dormouse, White Rabbit, Chessy Cat) or
fetches a banished Maliss monster (March Hare), so the deck's starters are all ways to banish a Pawn: Normal
Summon Dormouse (banish March Hare -> it adds itself, or White Rabbit -> it sets TB-11), Underground /
Terraforming, Gold Sarcophagus, Allure of Darkness, Chessy Cat banishing a Maliss card from the hand, March Hare
banishing one from the hand or GY, Bystials banishing a Pawn from the GY. White Rabbit sets TB-11 first (activated
the turn it is Set: banish a face-up Maliss, Special Summon a Pawn from the Deck), MTP-07 when TB-11 is gone.
Bodies climb into Red Ransom (searches Underground or Mirror; banished later it comes back and banishes a Pawn
from the Deck) and Cyberse Wicckid (only when something can still land in its zones: it banishes a Queen or Pawn
from the GY, which comes back, and searches Backup @Ignister, whose search fetches Dormouse / a Pawn to discard for
March Hare). Once the engine is spent, the bodies go into the best end board a small planner finds (_plan: Link
materials, Master Rule 2020 zones from the real link markers, Allied's revive ending the summons): typically
Allied Code Talker reviving Red Ransom, or Firewall Dragon + S:P Little Knight, W:P Fancy Ball, Hearts Crypter.
Hand traps stay in hand (Dominus Spark / Impulse, Imperm, Ash, Fuwalos, Belle are never Set, Normal Summoned or
discarded while anything else can go); MTP-07 and Mirror are Set for the opponent's turn (MTP-07 is used on our
turn only to fetch Dormouse for an unused Normal Summon).

Opponent's turn: hand traps through the Default* helpers, Dominus Impulse on a Special Summon effect, Dominus
Spark / Mirror / Imperm on a monster, Hearts Crypter / S:P Little Knight / Allied / Firewall quick effects, set
MTP-07 / TB-11 (banish a Maliss monster you control -> a body or a banish; TB-11 brings Hearts Crypter from the
Extra Deck when the opponent controls 3+ cards).

Approximations: link markers aren't in the env, so linked zones are computed from cards.cdb (a Link Monster's
DEF holds its markers; _linked / LinkedMask, module-level helpers). Once-per-turn effects are tracked by the
effects that resolved this turn (OnChainSolved), as in mitsurugi.py; the env gives the Pawns' / Queens' banished
effects another card's description (-1), so EffectKey tells effects apart by the card's location. cards.cdb's
Maliss set code is 0x1b9 (the WindBot port's C# constant is 0x1bf, which matches nothing here).
"""
from functools import lru_cache

from windbot import *
from windbot_default import DefaultExecutor, _CardId
from windbot_gameai import BattlePhaseAction


class CardId:
    Dormouse = 32061192
    WhiteRabbit = 69272449
    ChessyCat = 96676583
    MarchHare = 20938824
    TB11 = 57111661
    MTP07 = 94722358
    Mirror = 93453053
    Underground = 68337209
    RedRansom = 68059897
    HeartsCrypter = 21848500
    BackupIgnister = 30118811
    WizardIgnister = 3723262
    Terraforming = 73628505
    GoldSarcophagus = 75500286
    AllureOfDarkness = 1475311
    DominusSpark = 6325660
    DominusImpulse = 40366667
    InfiniteImpermanence = 10045474
    AshBlossom = 14558127
    MulcharmyFuwalos = 42141493
    GhostBelle = 73642296
    BystialDruiswurm = 6637331
    BystialMagnamhut = 33854624
    FancyBall = 4993187
    FirewallDragon = 5043010
    HaggardLizardose = 9763474
    Linguriboh = 24842059
    CharmerQuartet = 27519978
    SPLittleKnight = 29301450
    AlliedCodeTalker = 39138610
    CyberseWicckid = 52698008
    Almiraj = 60303245
    Masquerena = 65741786
    AccesscodeTalker = 86066372
    LinkSpider = 98978921


PAWNS = (CardId.Dormouse, CardId.WhiteRabbit, CardId.ChessyCat, CardId.MarchHare)
SELF_SUMMON_PAWNS = (CardId.Dormouse, CardId.WhiteRabbit, CardId.ChessyCat)
QUEENS = (CardId.RedRansom, CardId.HeartsCrypter)
MALISS_TRAPS = (CardId.TB11, CardId.MTP07)
HAND_TRAPS = (CardId.DominusSpark, CardId.DominusImpulse, CardId.InfiniteImpermanence, CardId.AshBlossom,
              CardId.MulcharmyFuwalos, CardId.GhostBelle)
BYSTIALS = (CardId.BystialDruiswurm, CardId.BystialMagnamhut)
SETCODE_MALISS = 0x1b9  # cards.cdb's Maliss set code


def S(card, n):
    return card * 16 + n


DORMOUSE_BANISH, DORMOUSE_SS = S(CardId.Dormouse, 0), S(CardId.Dormouse, 1)
RABBIT_SET, RABBIT_SS = S(CardId.WhiteRabbit, 0), S(CardId.WhiteRabbit, 1)
CHESSY_BANISH, CHESSY_SS, CHESSY_DRAW = S(CardId.ChessyCat, 0), S(CardId.ChessyCat, 1), S(CardId.ChessyCat, 2)
HARE_SS, HARE_ADD = S(CardId.MarchHare, 0), S(CardId.MarchHare, 1)
SELF_SS = {CardId.Dormouse: DORMOUSE_SS, CardId.WhiteRabbit: RABBIT_SS, CardId.ChessyCat: CHESSY_SS}
MAIN_EFFECT = {CardId.Dormouse: DORMOUSE_BANISH, CardId.WhiteRabbit: RABBIT_SET, CardId.ChessyCat: CHESSY_BANISH,
               CardId.MarchHare: HARE_SS}
TB11_SS = S(CardId.TB11, 0)
MTP07_ADD, MTP07_BANISH_ASK = S(CardId.MTP07, 0), S(CardId.MTP07, 2)
MIRROR_NEGATE, MIRROR_SEARCH = S(CardId.Mirror, 0), S(CardId.Mirror, 1)
UNDERGROUND_ASK = S(CardId.Underground, 1)
RANSOM_SEARCH, RANSOM_SS, RANSOM_BANISH_ASK = S(CardId.RedRansom, 0), S(CardId.RedRansom, 1), S(CardId.RedRansom, 2)
CRYPTER_BANISH, CRYPTER_SS = S(CardId.HeartsCrypter, 0), S(CardId.HeartsCrypter, 1)
WICCKID_SEARCH = S(CardId.CyberseWicckid, 0)
BACKUP_SS, BACKUP_SEARCH = S(CardId.BackupIgnister, 0), S(CardId.BackupIgnister, 1)
WIZARD_SS = S(CardId.WizardIgnister, 0)
ALLIED_REVIVE, ALLIED_NEGATE = S(CardId.AlliedCodeTalker, 0), S(CardId.AlliedCodeTalker, 1)
FIREWALL_BOUNCE = S(CardId.FirewallDragon, 0)
SPLK_QUICK = S(CardId.SPLittleKnight, 1)
FANCY_LINK = S(CardId.FancyBall, 1)


_BY_LOCATION = {
    # card: {location of the activation: effect}; the env's descriptions for these effects are often another
    # card's string (-1 here), so the effect is told apart by where the card activates it
    CardId.Dormouse: {CardLocation.MonsterZone: DORMOUSE_BANISH, CardLocation.Removed: DORMOUSE_SS},
    CardId.WhiteRabbit: {CardLocation.MonsterZone: RABBIT_SET, CardLocation.Removed: RABBIT_SS},
    CardId.ChessyCat: {CardLocation.MonsterZone: CHESSY_BANISH, CardLocation.Removed: CHESSY_SS},
    CardId.MarchHare: {CardLocation.Hand: HARE_SS, CardLocation.Removed: HARE_ADD},
    CardId.RedRansom: {CardLocation.MonsterZone: RANSOM_SEARCH, CardLocation.Removed: RANSOM_SS},
    CardId.HeartsCrypter: {CardLocation.MonsterZone: CRYPTER_BANISH, CardLocation.Removed: CRYPTER_SS},
    CardId.Mirror: {CardLocation.Hand: MIRROR_NEGATE, CardLocation.SpellZone: MIRROR_NEGATE,
                    CardLocation.Removed: MIRROR_SEARCH},
    CardId.BackupIgnister: {CardLocation.Hand: BACKUP_SS, CardLocation.MonsterZone: BACKUP_SEARCH},
    CardId.WizardIgnister: {CardLocation.Hand: WIZARD_SS, CardLocation.MonsterZone: S(CardId.WizardIgnister, 1),
                            CardLocation.Grave: S(CardId.WizardIgnister, 1)},
    CardId.BystialDruiswurm: {CardLocation.Hand: S(CardId.BystialDruiswurm, 0), CardLocation.Grave: S(CardId.BystialDruiswurm, 1)},
    CardId.BystialMagnamhut: {CardLocation.Hand: S(CardId.BystialMagnamhut, 0),
                              CardLocation.MonsterZone: S(CardId.BystialMagnamhut, 1)},
    CardId.TB11: {CardLocation.SpellZone: TB11_SS},
    CardId.MTP07: {CardLocation.SpellZone: MTP07_ADD},
}


_BANISHED = {CardId.Dormouse: DORMOUSE_SS, CardId.WhiteRabbit: RABBIT_SS, CardId.ChessyCat: CHESSY_SS,
             CardId.MarchHare: HARE_ADD, CardId.RedRansom: RANSOM_SS, CardId.HeartsCrypter: CRYPTER_SS,
             CardId.Mirror: MIRROR_SEARCH}


def EffectKey(card_id, location, desc):
    """Which effect of the card this is: the effect description where the env gives the card's own string,
    else (Maliss Pawns / Queens, Ignisters, Bystials) the effect the card has in that location. The banished
    effects of Pawns / Queens come with another card's string (-1); the option may name a copy of the card in
    the hand or GY then, so -1 off the field means the banished effect."""
    if desc > 0 and desc // 16 == card_id:
        return desc
    if desc == -1 and card_id in _BANISHED and location != CardLocation.MonsterZone:
        return _BANISHED[card_id]
    by_loc = _BY_LOCATION.get(card_id)
    if by_loc is not None and location in by_loc:
        return by_loc[location]
    return desc


# --- end-board planner: which Links to make from the bodies left once the engine is spent ------------------
# On-field value of a Link for the opponent's turn (interruptions; Linguriboh only stops Traps, Red Ransom /
# Accesscode / Wicckid are bodies).
VALUE = {CardId.AlliedCodeTalker: 1.0, CardId.HeartsCrypter: 0.75, CardId.FirewallDragon: 0.75,
         CardId.SPLittleKnight: 0.75, CardId.FancyBall: 0.75, CardId.Masquerena: 0.5, CardId.CharmerQuartet: 0.5,
         CardId.Linguriboh: 0.25, CardId.RedRansom: 0.2, CardId.AccesscodeTalker: 0.2, CardId.CyberseWicckid: 0.1}
# Link: (rating, min materials, max materials, material filter, needs a Maliss)
LINKS = {
    CardId.HeartsCrypter: (3, 3, 3, None, True),
    CardId.AlliedCodeTalker: (5, 3, 5, "effect", False),
    CardId.FirewallDragon: (4, 2, 4, None, False),
    CardId.SPLittleKnight: (2, 2, 2, "effect", False),
    CardId.FancyBall: (3, 2, 3, "effect", False),
    CardId.Masquerena: (2, 2, 2, "nonlink", False),
    CardId.CharmerQuartet: (4, 2, 4, None, False),
    CardId.RedRansom: (3, 2, 3, None, True),
    CardId.Linguriboh: (1, 1, 1, "lv4cyberse", False),
}
REVIVED_BY_ALLIED = (CardId.RedRansom, CardId.AccesscodeTalker)  # 2300-ATK Cyberse Allied brings back


def _linked(seq, markers):
    """Own Monster Zones (bit = sequence, 5/6 = Extra Monster Zones) a Link Monster in zone `seq` points to.
    The env doesn't expose link markers; cards.cdb keeps them in a Link Monster's DEF."""
    mask = 0
    if seq < 5:
        if markers & CardLinkMarker.Left and seq > 0:
            mask |= 1 << (seq - 1)
        if markers & CardLinkMarker.Right and seq < 4:
            mask |= 1 << (seq + 1)
        if markers & CardLinkMarker.TopLeft and seq in (2, 4):
            mask |= 1 << (5 if seq == 2 else 6)
        if markers & CardLinkMarker.Top and seq in (1, 3):
            mask |= 1 << (5 if seq == 1 else 6)
        if markers & CardLinkMarker.TopRight and seq in (0, 2):
            mask |= 1 << (5 if seq == 0 else 6)
    else:
        base = 0 if seq == 5 else 2
        if markers & CardLinkMarker.BottomLeft:
            mask |= 1 << base
        if markers & CardLinkMarker.Bottom:
            mask |= 1 << (base + 1)
        if markers & CardLinkMarker.BottomRight:
            mask |= 1 << (base + 2)
    return mask


def _body(card):
    """(id, link rating, effect, Maliss, Cyberse Lv<=4 non-Link, zone, link markers)."""
    rating = card.LinkCount if card.HasType(CardType.Link) else 0
    return (card.Id, rating, card.HasType(CardType.Effect), card.HasSetcode(SETCODE_MALISS),
            card.HasRace(CardRace.Cyberse) and not rating and 0 < card.Level <= 4, card.Sequence,
            card.BaseDefense if rating else 0)


def _link_zones(rest):
    """Zones a Link from the Extra Deck can go to with these monsters left on the field (Master Rule 2020: an
    Extra Monster Zone if we have none there, or a free zone one of our Links points to)."""
    occupied = {b[5] for b in rest}
    zones = [] if occupied & {5, 6} else [5, 6]
    pointed = 0
    for b in rest:
        if b[1]:
            pointed |= _linked(b[5], b[6])
    zones += [z for z in (0, 1, 2, 3, 4, 5, 6) if pointed & (1 << z) and z not in occupied and z not in zones]
    return zones


def _rating_ok(mats, rating):
    totals = {0}
    for m in mats:
        totals = {t + 1 for t in totals} | ({t + m[1] for t in totals} if m[1] > 1 else set())
    return rating in totals


def _materials_ok(link, mats):
    rating, lo, hi, kind, maliss = LINKS[link]
    if not lo <= len(mats) <= hi:
        return False
    if kind == "effect" and not all(m[2] for m in mats):
        return False
    if kind == "nonlink" and any(m[1] for m in mats):
        return False
    if kind == "lv4cyberse" and not all(m[4] for m in mats):
        return False
    if maliss and not any(m[3] for m in mats):
        return False
    if link == CardId.HeartsCrypter:
        return True  # exactly 3 materials, each counting 1
    return _rating_ok(mats, rating)


def _board_value(bodies):
    return sum(VALUE.get(i, 0.0) for i in {b[0] for b in bodies})


def _new_link(link, zone):
    data = NamedCard.Get(link)
    return (link, LINKS[link][0], True, link in (CardId.HeartsCrypter, CardId.RedRansom), False, zone,
            data.Defense if data else 0)


@lru_cache(maxsize=50000)
def _plan(bodies, extra, depth=4):
    """Best (end-board value, first Link, its materials, its zone) from these bodies (_body tuples) with these
    Extra Deck Links, Link Summoning up to `depth` more times."""
    best = (_board_value(bodies), 0, (), -1)
    if depth == 0:
        return best
    from itertools import combinations
    for link in dict.fromkeys(extra):
        if link not in LINKS:
            continue
        lo, hi = LINKS[link][1], LINKS[link][2]
        left = list(extra)
        left.remove(link)
        left = tuple(left)
        for k in range(lo, min(hi, len(bodies)) + 1):
            for idx in combinations(range(len(bodies)), k):
                mats = tuple(bodies[i] for i in idx)
                if not _materials_ok(link, mats):
                    continue
                rest = [b for i, b in enumerate(bodies) if i not in idx]
                for zone in _link_zones(rest):
                    after = rest + [_new_link(link, zone)]
                    more = depth - 1
                    if link == CardId.AlliedCodeTalker:  # revives a 2300-ATK Cyberse material to a zone it points to
                        revived = next((m for m in mats if m[0] in REVIVED_BY_ALLIED), None)
                        free = [z for z in range(5) if _linked(zone, after[-1][6]) & (1 << z) and
                                z not in {b[5] for b in after}]
                        if revived is not None and free:
                            after.append(revived[:5] + (free[0],) + revived[6:])
                            more = 0  # and no more Special Summons this turn
                    value = _plan(tuple(sorted(after, key=lambda b: b[5])), left, more)[0]
                    if value > best[0] + 1e-9:
                        best = (value, link, mats, zone)
    return best


def LinkedMask(card):
    """Own Monster Zones a face-up Link Monster on the field points to (bit = sequence)."""
    if card is None or not card.HasType(CardType.Link) or not card.IsFaceup() or card.Location != CardLocation.MonsterZone:
        return 0
    return _linked(card.Sequence, card.BaseDefense)


class MalissTcgExecutor(DefaultExecutor):
    DECK_EXECUTOR = True

    def __init__(self):
        super().__init__()
        A, SS, NS, SET = ExecutorType.Activate, ExecutorType.SpSummon, ExecutorType.Summon, ExecutorType.SpellSet
        # --- opponent's turn: hand traps and quick effects
        self.AddExecutor(A, CardId.AshBlossom, self.DefaultAshBlossomAndJoyousSpring)
        self.AddExecutor(A, CardId.GhostBelle, self.GhostBelleActivate)
        self.AddExecutor(A, CardId.MulcharmyFuwalos, self.DefaultMaxxC)
        self.AddExecutor(A, CardId.DominusImpulse, self.DominusImpulseActivate)
        self.AddExecutor(A, CardId.InfiniteImpermanence, self.ImpermanenceActivate)
        self.AddExecutor(A, CardId.DominusSpark, self.DominusSparkActivate)
        self.AddExecutor(A, CardId.AlliedCodeTalker, self.AlliedActivate)
        self.AddExecutor(A, CardId.HeartsCrypter, self.HeartsCrypterActivate)
        self.AddExecutor(A, CardId.SPLittleKnight, self.LittleKnightActivate)
        self.AddExecutor(A, CardId.FancyBall, self.FancyBallActivate)
        self.AddExecutor(A, CardId.FirewallDragon, self.FirewallActivate)
        self.AddExecutor(A, CardId.Masquerena, self.OpponentMainPhaseLink)
        self.AddExecutor(A, CardId.CharmerQuartet, self.CharmerActivate)
        self.AddExecutor(A, CardId.Mirror, self.MirrorActivate)
        self.AddExecutor(A, CardId.MTP07, self.MTP07Activate)
        self.AddExecutor(A, CardId.TB11, self.TB11Activate)
        # --- triggers: Pawns and Queens coming back from banishment, searches
        self.AddExecutor(A, CardId.Dormouse, self.PawnSelfSummon)
        self.AddExecutor(A, CardId.WhiteRabbit, self.PawnSelfSummon)
        self.AddExecutor(A, CardId.ChessyCat, self.PawnSelfSummon)
        self.AddExecutor(A, CardId.WhiteRabbit, self.RabbitSetTrap)
        self.AddExecutor(A, CardId.MarchHare, self.HareAdd)
        self.AddExecutor(A, CardId.RedRansom, self.RedRansomActivate)
        self.AddExecutor(A, CardId.HeartsCrypter, self.CrypterSelfSummon)
        self.AddExecutor(A, CardId.CyberseWicckid, self.WicckidActivate)
        self.AddExecutor(A, CardId.BackupIgnister, self.BackupSearch)
        self.AddExecutor(A, CardId.AlliedCodeTalker, self.AlliedRevive)
        self.AddExecutor(A, CardId.BystialMagnamhut, self.MagnamhutSearch)
        self.AddExecutor(A, CardId.BystialDruiswurm, self.DruiswurmSend)
        # --- Maliss Traps from the hand are Set first (activated the turn they are Set)
        self.AddExecutor(SET, CardId.TB11, self.SetMalissTrap)
        self.AddExecutor(SET, CardId.MTP07, self.SetMalissTrap)
        # --- starters: ways to banish a Pawn
        self.AddExecutor(NS, CardId.Dormouse, self.DormouseSummon)
        self.AddExecutor(A, CardId.Dormouse, self.DormouseBanish)
        self.AddExecutor(A, CardId.Terraforming, self.TerraformingActivate)
        self.AddExecutor(A, CardId.Underground, self.UndergroundActivate)
        self.AddExecutor(A, CardId.GoldSarcophagus, self.GoldSarcophagusActivate)
        self.AddExecutor(A, CardId.AllureOfDarkness, self.AllureActivate)
        self.AddExecutor(A, CardId.ChessyCat, self.ChessyBanish)
        self.AddExecutor(NS, CardId.WhiteRabbit, self.RabbitSummon)
        self.AddExecutor(A, CardId.MarchHare, self.HareSummon)
        self.AddExecutor(A, CardId.BackupIgnister, self.BackupSelfSummon)
        self.AddExecutor(NS, CardId.BackupIgnister, self.BackupSummon)
        self.AddExecutor(A, CardId.BystialDruiswurm, self.BystialSummon)
        self.AddExecutor(A, CardId.BystialMagnamhut, self.BystialSummon)
        self.AddExecutor(NS, CardId.ChessyCat, self.ChessySummon)
        self.AddExecutor(NS, CardId.MarchHare, self.HareNormalSummon)
        # --- Link climb
        self.AddExecutor(SS, CardId.RedRansom, self.RedRansomSummon)
        self.AddExecutor(SS, CardId.CyberseWicckid, self.WicckidSummon)
        self.AddExecutor(SS, CardId.HeartsCrypter, self.CrypterSummon)
        self.AddExecutor(A, CardId.WizardIgnister, self.WizardActivate)
        self.AddExecutor(SS, CardId.AlliedCodeTalker, self.AlliedSummon)
        self.AddExecutor(SS, CardId.FirewallDragon, self.FirewallSummon)
        self.AddExecutor(SS, CardId.SPLittleKnight, self.LittleKnightSummon)
        self.AddExecutor(SS, CardId.FancyBall, self.FancyBallSummon)
        self.AddExecutor(SS, CardId.Masquerena, self.MasquerenaSummon)
        self.AddExecutor(SS, CardId.Linguriboh, self.LingurribohSummon)
        self.AddExecutor(SS, CardId.CharmerQuartet, self.CharmerSummon)
        self.AddExecutor(SS, CardId.AccesscodeTalker, self.AccesscodeSummon)
        self.AddExecutor(SS, CardId.Almiraj, self.Never)
        self.AddExecutor(SS, CardId.LinkSpider, self.Never)
        self.AddExecutor(SS, CardId.HaggardLizardose, self.Never)
        self.AddExecutor(A, CardId.AccesscodeTalker, self.AccesscodeActivate)
        # --- backrow: Mirror / MTP-07 for the opponent's turn; hand traps stay in hand
        self.AddExecutor(SET, CardId.Mirror, self.SetMirror)
        for id_ in HAND_TRAPS:
            self.AddExecutor(SET, id_, self.Never)
        self.AddExecutor(SET, CardId.Underground, self.Never)
        for id_ in (CardId.AshBlossom, CardId.GhostBelle, CardId.MulcharmyFuwalos):
            self.AddExecutor(NS, id_, self.Never)
        self.AddExecutor(ExecutorType.MonsterSet, self.Never)
        self.AddExecutor(ExecutorType.Repos, self.DefaultMonsterRepos)
        self.usedEffects = set()   # own effect descriptions resolved this turn
        self.activatedIds = set()  # own cards activated this turn (hard once-per-turn cards)
        self.normalSummoned = False
        self.pendingLink = 0   # the Link being summoned (its materials are queued with SelectMaterials)
        self.plannedZone = -1  # and the zone the planner put it in

    # --- bookkeeping ------------------------------------------------------------------------------------
    def OnNewTurn(self):
        self.usedEffects.clear()
        self.activatedIds.clear()
        self.normalSummoned = False
        self.pendingLink, self.plannedZone = 0, -1
        super().OnNewTurn()

    def OnChainSolved(self, chainIndex):
        chain = self.Duel.GetCurrentSolvingChainInfo()
        if chain is not None and chain.ActivatePlayer == 0:
            self.usedEffects.add(EffectKey(chain.ActivateId, chain.ActivateLocation, chain.ActivateDescription))
            self.activatedIds.add(chain.ActivateId)
        super().OnChainSolved(chainIndex)

    def Used(self, desc):
        return desc in self.usedEffects

    def Key(self):
        """The effect the row is asked about (EffectKey of the current card and description)."""
        if self.Card is None:
            return self.ActivateDescription
        return EffectKey(self.Card.Id, self.Card.Location, self.ActivateDescription)

    def MyTurn(self):
        return self.Duel.Player == 0

    # --- board helpers ----------------------------------------------------------------------------------
    def IsMaliss(self, c):
        return c is not None and c.HasSetcode(SETCODE_MALISS)

    def SelfSummonReady(self, c):
        """A Pawn / Queen whose banished effect is still unused this turn (banishing it gains a body)."""
        if c.IsCode(*SELF_SUMMON_PAWNS):
            return not self.Used(SELF_SS[c.Id])
        if c.IsCode(CardId.MarchHare):
            return not self.Used(HARE_ADD)
        if c.IsCode(CardId.RedRansom):
            return not self.Used(RANSOM_SS) and self.Bot.LifePoints > 1500
        if c.IsCode(CardId.HeartsCrypter):
            return not self.Used(CRYPTER_SS) and self.Bot.LifePoints > 1500
        return False

    def BanishValue(self, c):
        """Higher = better to banish (as a cost or effect) on our own turn."""
        if c.IsCode(CardId.Dormouse):
            return 10 if not self.Used(DORMOUSE_SS) and not self.Used(DORMOUSE_BANISH) else 4 if not self.Used(DORMOUSE_SS) else 0
        if c.IsCode(CardId.WhiteRabbit):
            return 9 if not self.Used(RABBIT_SS) and not self.Used(RABBIT_SET) else 4 if not self.Used(RABBIT_SS) else 0
        if c.IsCode(CardId.RedRansom):
            return 8 if self.SelfSummonReady(c) and c.Location != CardLocation.MonsterZone else 1
        if c.IsCode(CardId.MarchHare):
            return 7 if not self.Used(HARE_ADD) and self.BanishedMalissMonsters(extra=c) else 1
        if c.IsCode(CardId.ChessyCat):
            return 6 if not self.Used(CHESSY_SS) else 0
        if c.IsCode(CardId.Mirror):
            return 5 if not self.Used(MIRROR_SEARCH) and c.Location == CardLocation.Hand else 0
        if c.IsCode(CardId.HeartsCrypter):
            return 3 if self.SelfSummonReady(c) and c.Location != CardLocation.MonsterZone else -5
        if c.IsCode(CardId.Underground):
            return 2 if self.Used(UNDERGROUND_ASK) or CardId.Underground in self.activatedIds or \
                self.Bot.HasInSpellZone(CardId.Underground) else -3
        if c.IsCode(*MALISS_TRAPS):
            return 0 if c.Location == CardLocation.Grave else -4
        return -1

    def BanishedMalissMonsters(self, extra=None):
        return [c for c in self.Bot.Banished if c.IsMonster() and self.IsMaliss(c)] + ([extra] if extra is not None else [])

    def ByBanishValue(self, cards):
        return sorted(cards, key=lambda c: -self.BanishValue(c))

    def Bodies(self):
        return [c for c in self.Bot.GetMonsters() if c.IsFaceup()]

    def MainZoneFree(self):
        return sum(1 for c in self.Bot.MonsterZone[:5] if c is None)

    def Pick(self, cards, ids, min_, max_):
        picked = []
        for id_ in ids:
            for c in cards:
                if c.IsCode(id_) and c not in picked:
                    picked.append(c)
                    break
        return self.Util.CheckSelectCount(picked, cards, min_, max_) if picked else None

    def HandValue(self, c):
        """Higher = keep in hand (discard / banish the lowest)."""
        if c.IsCode(*HAND_TRAPS):
            return 10
        if c.IsCode(*BYSTIALS):
            return 4
        if c.IsCode(CardId.Dormouse) and not self.normalSummoned:
            return 8
        if c.IsCode(CardId.MarchHare) and not self.Used(HARE_SS):
            return 5  # an outlet: banishes a Pawn from the GY to Special Summon both
        if c.IsCode(*PAWNS):
            return 1 if self.SelfSummonReady(c) or c.IsCode(CardId.MarchHare) else 2
        if c.IsCode(CardId.MTP07, CardId.TB11, CardId.Mirror):
            return 6
        return 3

    def BanishOutlet(self):
        """A way left this turn to banish a Pawn from the hand / GY (so a Pawn discarded or searched now comes back)."""
        return (self.Bot.HasInHand(CardId.MarchHare) and not self.Used(HARE_SS)) or \
            (self.Bot.HasInHand(CardId.Underground) and self.UndergroundAvailable()) or \
            any(self.Bot.HasInHand(b) for b in BYSTIALS)

    # --- searches -----------------------------------------------------------------------------------------
    def PawnSearchOrder(self):
        """Which Maliss / DARK Cyberse monster to add (Backup, MTP-07)."""
        order = []
        if not self.Used(DORMOUSE_BANISH) and not self.Bot.HasInHand(CardId.Dormouse) and \
                (not self.normalSummoned or self.BanishOutlet()):
            order.append(CardId.Dormouse)
        if not self.Used(RABBIT_SET) and not self.Bot.HasInHand(CardId.WhiteRabbit) and \
                (self.Bot.HasInDeck(CardId.TB11) or self.Bot.HasInDeck(CardId.MTP07)):
            order.append(CardId.WhiteRabbit)
        if not self.Bot.HasInHand(CardId.MarchHare) and not self.Used(HARE_SS):
            order.append(CardId.MarchHare)
        if not self.Used(CHESSY_BANISH) and not self.Bot.HasInHand(CardId.ChessyCat):
            order.append(CardId.ChessyCat)
        return order + [CardId.MarchHare, CardId.ChessyCat, CardId.WhiteRabbit, CardId.Dormouse, CardId.WizardIgnister]

    def DeckBanishOrder(self):
        """Dormouse / Underground / Red Ransom / Gold Sarcophagus: which Maliss card to banish from the Deck."""
        order = []
        hare_in_hand = self.Bot.HasInHand(CardId.MarchHare)
        if not self.Used(RABBIT_SS) and not self.Used(RABBIT_SET) and \
                (self.Bot.HasInDeck(CardId.TB11) or self.Bot.HasInDeck(CardId.MTP07)):
            order.append(CardId.WhiteRabbit)
        if not self.Used(DORMOUSE_SS) and not self.Used(DORMOUSE_BANISH):
            order.append(CardId.Dormouse)
        if not hare_in_hand and not self.Used(HARE_ADD) and not self.Used(HARE_SS):
            order.append(CardId.MarchHare)
        if not self.Used(CHESSY_SS):
            order.append(CardId.ChessyCat)
        if not self.Used(HARE_ADD):
            order.append(CardId.MarchHare)
        return order + [CardId.ChessyCat, CardId.WhiteRabbit, CardId.Dormouse, CardId.MarchHare]

    def SpellSearchOrder(self):
        """Red Ransom: a Maliss Spell."""
        if not self.Bot.HasInHand(CardId.Underground) and CardId.Underground not in self.activatedIds and \
                not self.Bot.HasInSpellZone(CardId.Underground):
            return [CardId.Underground, CardId.Mirror]
        return [CardId.Mirror, CardId.Underground]

    def TrapSetOrder(self):
        if CardId.TB11 not in self.activatedIds and self.MyTurn():
            return [CardId.TB11, CardId.MTP07]
        return [CardId.MTP07, CardId.TB11]

    # --- opponent's turn --------------------------------------------------------------------------------
    def GhostBelleActivate(self):
        return self.Duel.LastChainPlayer == 1 and self.DefaultGhostBelleAndHauntedMansion()

    def DominusImpulseActivate(self):
        return self.Duel.LastChainPlayer == 1

    def ImpermanenceActivate(self):
        if self.MyTurn() and self.Duel.LastChainPlayer != 1:
            return False
        return self.DefaultInfiniteImpermanence()

    def DominusSparkActivate(self):
        target = self.Util.GetBestEnemyMonster(True, True)
        if target is None or self.MyTurn() and self.Duel.LastChainPlayer != 1:
            return False
        self.AI.SelectCard(target)
        return True

    def AlliedActivate(self):
        if self.Duel.LastChainPlayer == 1:
            return self.Key() != ALLIED_REVIVE  # negate the opponent's card
        return self.MyTurn() and self.Key() != ALLIED_NEGATE  # Link Summoned: revive the 2300-ATK Cyberse

    def HeartsCrypterActivate(self):
        if self.Key() != CRYPTER_BANISH:
            return False
        if not self.Enemy.GetMonsters() and not self.Enemy.GetSpells():
            return False
        return self.Duel.LastChainPlayer == 1 or self.Duel.Player == 1 or self.Enemy.GetMonsterCount() > 0

    def LittleKnightActivate(self):
        if self.Key() == SPLK_QUICK:
            return self.Duel.LastChainPlayer == 1 and self.Enemy.GetMonsterCount() > 0
        target = self.Util.GetBestEnemyCard(False, True)
        if target is None:
            gy = [c for c in self.Enemy.Graveyard]
            if not gy:
                return False
            target = gy[0]
        self.AI.SelectCard(target)
        return True

    def FancyBallActivate(self):
        if self.Key() == FANCY_LINK:
            return self.Duel.Player == 1
        return self.Duel.LastChainPlayer == 1

    def FirewallActivate(self):
        if self.Key() != FIREWALL_BOUNCE:
            return True  # a monster it points to left: Special Summon a Cyberse from the hand
        return not self.MyTurn() and self.Enemy.GetMonsterCount() > 0

    def OpponentMainPhaseLink(self):
        return self.Duel.Player == 1

    def CharmerActivate(self):
        return self.Duel.Player == 1 or len(self.Bodies()) <= 2

    def MirrorActivate(self):
        if self.Key() == MIRROR_SEARCH:
            return any(self.IsMaliss(c) for c in self.Bot.Graveyard)
        if self.MyTurn() and self.Duel.LastChainPlayer != 1:
            return False
        return self.Enemy.GetMonsterCount() > 0 and any(c.IsCode(*PAWNS) for c in self.Bot.Hand + self.Bot.GetMonsters())

    def MalissCostOnField(self):
        return [c for c in self.Bot.GetMonsters() if c.IsFaceup() and self.IsMaliss(c)]

    def MTP07Activate(self):
        if not self.MalissCostOnField():
            return False
        if self.MyTurn():
            # own turn: only to fetch Dormouse for the Normal Summon, paying with a monster that comes back;
            # otherwise it stays Set for the opponent's turn
            return not self.normalSummoned and not self.Used(DORMOUSE_BANISH) and self.Bot.HasInDeck(CardId.Dormouse) \
                and any(self.SelfSummonReady(c) for c in self.MalissCostOnField())
        return self.Enemy.GetMonsterCount() + self.Enemy.GetSpellCount() > 0

    def FieldCostOrder(self, cards):
        """TB-11 / MTP-07 / Mirror cost from the field: a monster that comes back when banished first."""
        def rank(c):
            if c.IsCode(CardId.RedRansom) and self.SelfSummonReady(c):
                return 0  # comes back and banishes a Pawn from the Deck
            if c.IsCode(*SELF_SUMMON_PAWNS) and self.SelfSummonReady(c):
                return 1
            if c.IsCode(CardId.MarchHare) and self.SelfSummonReady(c):
                return 2
            if c.IsCode(*PAWNS):
                return 3
            if c.IsCode(CardId.HeartsCrypter):
                return 6 if self.SelfSummonReady(c) else 9
            return 5
        return sorted(cards, key=rank)

    def TB11Activate(self):
        cost = self.MalissCostOnField()
        if not cost:
            return False
        if not self.MyTurn():
            return self.Duel.LastChainPlayer != 0
        return self.MainZoneFree() >= 1 and any(self.Bot.HasInDeck(id_) for id_ in PAWNS)

    # --- triggers ---------------------------------------------------------------------------------------
    def PawnSelfSummon(self):
        desc = SELF_SS.get(self.Card.Id)
        if self.Key() != desc:
            return False
        return self.Bot.LifePoints > 300 and self.MainZoneFree() >= 1

    def RabbitSetTrap(self):
        return self.Key() == RABBIT_SET

    def HareAdd(self):
        return self.Key() == HARE_ADD and self.Bot.LifePoints > 300

    def RedRansomActivate(self):
        if self.Key() == RANSOM_SEARCH:
            return True
        if self.Key() == RANSOM_SS:
            return self.Bot.LifePoints > 900 and self.MainZoneFree() >= 1
        return False

    def CrypterSelfSummon(self):
        return self.Key() == CRYPTER_SS and self.Bot.LifePoints > 900

    def WicckidActivate(self):
        return any(c.HasRace(CardRace.Cyberse) and c.IsMonster() for c in self.Bot.Graveyard)

    def BackupSearch(self):
        return self.Key() == BACKUP_SEARCH

    def AlliedRevive(self):
        return self.Key() == ALLIED_REVIVE

    def MagnamhutSearch(self):
        return self.Key() != S(CardId.BystialMagnamhut, 0)

    def DruiswurmSend(self):
        if self.Key() == S(CardId.BystialDruiswurm, 0):
            return False
        return self.Enemy.GetMonsterCount() > 0

    def SetMalissTrap(self):
        return not self.Bot.HasInSpellZone(self.Card.Id)

    # --- starters ---------------------------------------------------------------------------------------
    def UndergroundAvailable(self):
        return CardId.Underground not in self.activatedIds and not self.Bot.HasInSpellZone(CardId.Underground)

    def TerraformingActivate(self):
        return self.UndergroundAvailable() and not self.Bot.HasInHand(CardId.Underground) and \
            self.Bot.HasInDeck(CardId.Underground)

    def UndergroundActivate(self):
        if self.Card.Location == CardLocation.SpellZone and self.Card.IsFaceup():
            return False
        return self.UndergroundAvailable()

    def DormouseSummon(self):
        if self.Used(DORMOUSE_BANISH):
            return False
        self.normalSummoned = True
        return True

    def DormouseBanish(self):
        return self.Key() == DORMOUSE_BANISH and self.Card.Location == CardLocation.MonsterZone

    def GoldSarcophagusActivate(self):
        return any(self.Bot.HasInDeck(id_) for id_ in PAWNS)

    def AllureActivate(self):
        dark = [c for c in self.Bot.Hand if c.IsMonster() and c.HasAttribute(CardAttribute.Dark) and c != self.Card]
        return bool(dark)

    def ChessyBanish(self):
        if self.Key() != CHESSY_BANISH or self.Card.Location != CardLocation.MonsterZone:
            return False
        return any(self.IsMaliss(c) for c in self.Bot.Hand)

    def RabbitSummon(self):
        if self.Used(RABBIT_SET) or self.Bot.HasInHand(CardId.Dormouse) and not self.Used(DORMOUSE_BANISH):
            return False
        self.normalSummoned = True
        return True

    def HareSummon(self):
        if self.Key() != HARE_SS or self.Card.Location != CardLocation.Hand:
            return False
        return any(self.IsMaliss(c) and c != self.Card and self.BanishValue(c) >= 0
                   for c in self.Bot.Hand + self.Bot.Graveyard) and self.MainZoneFree() >= 1

    def BackupSelfSummon(self):
        return self.Key() == BACKUP_SS and self.Card.Location == CardLocation.Hand and self.MainZoneFree() >= 1

    def BackupSummon(self):
        if self.Bot.HasInHand([CardId.Dormouse, CardId.WhiteRabbit]):
            return False
        self.normalSummoned = True
        return True

    def BystialSummon(self):
        if self.Key() != S(self.Card.Id, 0):
            return False
        if self.MyTurn():
            return self.MainZoneFree() >= 1
        return self.Duel.LastChainPlayer == 1

    def ChessySummon(self):
        if self.Bot.HasInHand([CardId.Dormouse, CardId.WhiteRabbit, CardId.BackupIgnister]):
            return False
        if not any(self.IsMaliss(c) and c != self.Card for c in self.Bot.Hand):
            return False
        self.normalSummoned = True
        return True

    def HareNormalSummon(self):
        if self.Bot.HasInHand([CardId.Dormouse, CardId.WhiteRabbit, CardId.BackupIgnister, CardId.ChessyCat]):
            return False
        self.normalSummoned = True
        return True

    # --- Link climb -------------------------------------------------------------------------------------
    def MaterialRank(self, c):
        """Lower = better Link Material."""
        if c.IsCode(CardId.Linguriboh, CardId.Almiraj, CardId.LinkSpider):
            return 0
        if c.IsCode(*PAWNS):
            spent = not self.SelfSummonReady(c) and (self.Used(MAIN_EFFECT.get(c.Id, -1)) or c.IsCode(CardId.ChessyCat))
            return 1 if spent else 2
        if c.IsCode(CardId.BackupIgnister, CardId.WizardIgnister):
            return 1
        if c.IsCode(*BYSTIALS):
            return 3
        if c.IsCode(CardId.CyberseWicckid):
            return 2 if self.Used(WICCKID_SEARCH) else 6
        if c.IsCode(CardId.RedRansom):
            return 4 if self.Used(RANSOM_SEARCH) else 7
        if c.IsCode(CardId.Masquerena, CardId.FancyBall, CardId.SPLittleKnight):
            return 5
        if c.IsCode(CardId.HeartsCrypter):
            return 8
        return 9

    def Keeper(self, c):
        return VALUE.get(c.Id, 0.0) >= 0.5

    def ChooseMaterials(self, link, cards):
        """First valid material set for an engine Link from these cards (best-ranked first, fewest cards)."""
        from itertools import combinations
        cards = sorted(cards, key=self.MaterialRank)
        rating, lo, hi = LINKS[link][:3] if link in LINKS else (2, 2, 2)
        for k in range(lo, min(hi, len(cards)) + 1):
            for combo in combinations(cards, k):
                bodies = tuple(_body(c) for c in combo)
                if link == CardId.CyberseWicckid:
                    ok = all(c.HasRace(CardRace.Cyberse) for c in combo) and not any(b[1] > 1 for b in bodies)
                else:
                    ok = _materials_ok(link, bodies)
                if ok:
                    return list(combo)
        return None

    def EngineLink(self, link):
        mats = self.ChooseMaterials(link, [c for c in self.Bodies() if not self.Keeper(c)])
        if mats is None:
            return False
        zones = _link_zones([_body(c) for c in self.Bodies() if c not in mats])
        if not zones:
            return False
        self.pendingLink, self.plannedZone = link, zones[0]
        self.AI.SelectMaterials(mats)
        return True

    def Plan(self):
        bodies = tuple(sorted((_body(c) for c in self.Bodies()), key=lambda b: b[5]))
        if self.Used(ALLIED_REVIVE):
            return (_board_value(bodies), 0, (), -1)  # Allied's revive: no more Special Summons this turn
        cyberse_only = self.Used(WIZARD_SS)  # Wizard @Ignister: only Cyberse monsters for the rest of the turn
        extra = tuple(sorted(c.Id for c in self.Bot.ExtraDeck if c.Id in LINKS and
                             (not cyberse_only or c.HasRace(CardRace.Cyberse))))
        return _plan(bodies, extra)

    def FinisherSummon(self):
        """The first Link of the best end board the planner finds from the bodies on the field."""
        if not self.MyTurn():
            return False
        value, link, mats, zone = self.Plan()
        if link != self.Card.Id or value <= _board_value(tuple(_body(c) for c in self.Bodies())) + 1e-9:
            return False
        chosen = [c for c in self.Bodies() if any(m[5] == c.Sequence for m in mats)]
        if len(chosen) != len(mats):
            return False
        self.pendingLink, self.plannedZone = link, zone
        self.AI.SelectMaterials(chosen)
        return True

    def RedRansomSummon(self):
        if self.Used(RANSOM_SEARCH) or self.Bot.HasInMonstersZone(CardId.RedRansom):
            return self.FinisherSummon()
        if not self.Bot.HasInDeck(CardId.Underground) and not self.Bot.HasInDeck(CardId.Mirror):
            return self.FinisherSummon()
        return self.EngineLink(CardId.RedRansom)

    def WicckidFollowUp(self):
        """Something can still be Special Summoned into Wicckid's zones after it lands."""
        if self.Bot.HasInHand(CardId.BackupIgnister) and not self.Used(BACKUP_SS):
            return True
        if self.Bot.HasInHand(CardId.MarchHare) and not self.Used(HARE_SS) and \
                any(self.IsMaliss(c) for c in self.Bot.Graveyard):
            return True
        if self.Bot.HasInHand(CardId.WizardIgnister) and not self.Used(WIZARD_SS):
            return True
        if any(self.Bot.HasInHand(b) for b in BYSTIALS):
            return True
        return any(c.IsCode(*SELF_SUMMON_PAWNS) and self.SelfSummonReady(c) for c in self.Bot.Graveyard) and \
            (self.UndergroundAvailable() and self.Bot.HasInHand(CardId.Underground))

    def WicckidSummon(self):
        if self.Used(WICCKID_SEARCH) or self.Bot.HasInMonstersZone(CardId.CyberseWicckid):
            return False
        if not self.Bot.HasInDeck(CardId.BackupIgnister) or not self.WicckidFollowUp():
            return False
        return self.EngineLink(CardId.CyberseWicckid)

    def CrypterSummon(self):
        return self.FinisherSummon()

    def WizardActivate(self):
        if self.Key() == WIZARD_SS:
            return self.MainZoneFree() >= 2 and any(c.HasRace(CardRace.Cyberse) and c.HasAttribute(CardAttribute.Dark)
                                                   for c in self.Bot.Graveyard)
        return not self.MyTurn() and self.Enemy.GetMonsterCount() > 0

    AlliedSummon = FirewallSummon = LittleKnightSummon = FancyBallSummon = MasquerenaSummon = CharmerSummon = \
        FinisherSummon

    def LingurribohSummon(self):
        """A spent Pawn into a Link-1 when that frees a Pawn to the GY for March Hare / Wicckid fodder or
        gives Backup @Ignister its Extra Deck Cyberse."""
        spent = [c for c in self.Bodies() if c.IsCode(*PAWNS) and self.MaterialRank(c) <= 2]
        if not spent or self.Bot.HasInMonstersZone(CardId.Linguriboh):
            return self.FinisherSummon()
        need_ed_cyberse = self.Bot.HasInHand(CardId.BackupIgnister) and not self.Used(BACKUP_SS) and \
            not any(c.HasType(CardType.Link) for c in self.Bodies())
        hare = self.Bot.HasInHand(CardId.MarchHare) and not self.Used(HARE_SS) and \
            not any(self.IsMaliss(c) for c in self.Bot.Graveyard + self.Bot.Hand if not c.IsCode(CardId.MarchHare))
        if need_ed_cyberse or hare:
            return self.EngineLink(CardId.Linguriboh)
        return self.FinisherSummon()

    def AccesscodeSummon(self):
        return False

    def AccesscodeActivate(self):
        return self.Enemy.GetMonsterCount() + self.Enemy.GetSpellCount() > 0

    def Never(self):
        return False

    def SetMirror(self):
        return not self.Bot.HasInSpellZone(CardId.Mirror) and \
            (not self.Bot.HasInHand(CardId.ChessyCat) or self.Used(CHESSY_BANISH))

    # --- prompts ----------------------------------------------------------------------------------------
    def OnSelectYesNo(self, desc):
        if desc == UNDERGROUND_ASK:
            return True
        if desc == RANSOM_BANISH_ASK:
            return any(self.Bot.HasInDeck(id_) for id_ in PAWNS)
        if desc == CHESSY_DRAW:
            return True
        if desc == MTP07_BANISH_ASK:
            return self.Enemy.GetMonsterCount() + self.Enemy.GetSpellCount() > 0
        if desc in SELF_SS.values() or desc in (RANSOM_SS, CRYPTER_SS):
            return self.Bot.LifePoints > 900
        return super().OnSelectYesNo(desc)

    def OnSelectOption(self, options):
        if TB11_SS in options and len(options) > 1:
            # TB-11 against 3+ opposing cards: a Maliss Link from the Extra Deck (Hearts Crypter's banish) on the
            # opponent's turn, a Pawn from the Deck (a body for Links) on ours
            k = options.index(TB11_SS)
            return k if self.MyTurn() else next(i for i in range(len(options)) if i != k)
        return super().OnSelectOption(options)

    def OnSelectPlace(self, cardId, player, location, available):
        if player != 0 or location != CardLocation.MonsterZone:
            return super().OnSelectPlace(cardId, player, location, available)
        data = NamedCard.Get(cardId)
        is_link = data is not None and data.HasType(CardType.Link)
        wicckid = next((c for c in self.Bot.GetMonsters() if c.IsCode(CardId.CyberseWicckid) and c.IsFaceup()), None)
        if not is_link and wicckid is not None and not self.Used(WICCKID_SEARCH):
            choice = LinkedMask(wicckid) & available
            if choice:
                return choice
        if is_link:
            if cardId == self.pendingLink and self.plannedZone >= 0 and available & (1 << self.plannedZone):
                return 1 << self.plannedZone  # where the planner put it
            emz = available & (Zones.z5 | Zones.z6)
            if emz and not self.Bot.GetMonstersInExtraZone():
                return Zones.z5 if emz & Zones.z5 else Zones.z6
            main = available & Zones.MainMonsterZones
            if main:
                return main
        else:
            # non-Links: avoid zones Links point to, so later Links have room
            linked = 0
            for c in self.Bot.GetMonsters():
                linked |= LinkedMask(c)
            free = available & Zones.MainMonsterZones & ~linked
            if free:
                return free
        return 0

    def OnSelectCard(self, cards, min_, max_, hint, cancelable):
        solving = self.Duel.GetCurrentSolvingChainInfo()
        activating = self.Duel.GetCurrentChainCard()
        source = solving.ActivateId if solving is not None else (activating.Id if activating is not None else 0)
        desc = EffectKey(solving.ActivateId, solving.ActivateLocation, solving.ActivateDescription) if solving is not None else -1
        mine = [c for c in cards if c.Controller == 0]
        theirs = [c for c in cards if c.Controller == 1]
        if hint == HintMsg.LinkMaterial:
            return None  # SelectMaterials from the summon row
        if hint == HintMsg.Discard:
            return self.Util.CheckSelectCount(sorted(cards, key=self.HandValue), cards, min_, max_)
        if source == CardId.Dormouse and hint == HintMsg.Remove:
            return self.Pick(cards, self.DeckBanishOrder(), min_, max_)
        if source == CardId.Underground and hint == HintMsg.Remove:
            return self.Util.CheckSelectCount(self.ByBanishValue(cards), cards, min_, max_)
        if source == CardId.GoldSarcophagus:
            return self.Pick(cards, self.DeckBanishOrder() + [CardId.Mirror], min_, max_)
        if source == CardId.WhiteRabbit:
            return self.Pick(cards, self.TrapSetOrder(), min_, max_)
        if source == CardId.MarchHare and hint == HintMsg.AddToHand or source == CardId.MarchHare and desc == HARE_ADD:
            order = []
            if not self.normalSummoned and not self.Used(DORMOUSE_BANISH):
                order.append(CardId.Dormouse)
            if not self.Used(HARE_SS):
                order.append(CardId.MarchHare)
            return self.Pick(cards, order + [CardId.WhiteRabbit, CardId.ChessyCat, CardId.Dormouse, CardId.MarchHare],
                             min_, max_)
        if source == CardId.MarchHare and hint == HintMsg.Remove:
            gy_first = sorted(cards, key=lambda c: (-self.BanishValue(c) - (3 if c.Location == CardLocation.Grave else 0)))
            return self.Util.CheckSelectCount(gy_first, cards, min_, max_)
        if source == CardId.ChessyCat and hint == HintMsg.Remove:
            return self.Util.CheckSelectCount(self.ByBanishValue(cards), cards, min_, max_)
        if source == CardId.RedRansom:
            if hint == HintMsg.AddToHand:
                return self.Pick(cards, self.SpellSearchOrder(), min_, max_)
            if hint == HintMsg.Remove:
                return self.Pick(cards, self.DeckBanishOrder(), min_, max_)
        if source == CardId.CyberseWicckid:
            if hint == HintMsg.Remove:
                return self.Util.CheckSelectCount(self.ByBanishValue(cards), cards, min_, max_)
            return self.Pick(cards, [CardId.BackupIgnister], min_, max_)
        if source == CardId.BackupIgnister and hint == HintMsg.AddToHand:
            return self.Pick(cards, self.PawnSearchOrder(), min_, max_)
        if source == CardId.MTP07:
            if hint == HintMsg.AddToHand:
                return self.Pick(cards, self.PawnSearchOrder(), min_, max_)
            if hint == HintMsg.Remove and theirs:
                return self.Util.CheckSelectCount(theirs, cards, min_, max_)
            if hint == HintMsg.Remove:
                return self.Util.CheckSelectCount(self.FieldCostOrder(mine), cards, min_, max_)
        if source == CardId.TB11:
            if hint == HintMsg.SpSummon:
                order = [CardId.HeartsCrypter, CardId.RedRansom] if not self.MyTurn() else []
                return self.Pick(cards, order + [CardId.ChessyCat, CardId.MarchHare, CardId.WhiteRabbit, CardId.Dormouse],
                                 min_, max_)
            if hint == HintMsg.Remove:
                return self.Util.CheckSelectCount(self.FieldCostOrder(mine), cards, min_, max_)
        if source == CardId.Mirror:
            if hint == HintMsg.Remove and mine:
                return self.Util.CheckSelectCount(self.ByBanishValue(mine), cards, min_, max_)
            if hint == HintMsg.AddToHand:
                return self.Pick(cards, [CardId.MTP07, CardId.TB11] + self.PawnSearchOrder() + [CardId.Underground],
                                 min_, max_)
        if source == CardId.AllureOfDarkness and hint == HintMsg.Remove:
            rank = lambda c: (-self.BanishValue(c) if c.IsCode(*PAWNS) else 0 if c.IsCode(*BYSTIALS) else 5)
            return self.Util.CheckSelectCount(sorted(cards, key=rank), cards, min_, max_)
        if source in BYSTIALS and hint == HintMsg.Remove:
            own_pawns = sorted([c for c in mine if c.IsCode(*PAWNS, *QUEENS)], key=lambda c: -self.BanishValue(c))
            return self.Util.CheckSelectCount(theirs + own_pawns, cards, min_, max_) if not self.MyTurn() else \
                self.Util.CheckSelectCount(own_pawns + theirs, cards, min_, max_)
        if source == CardId.WizardIgnister and hint == HintMsg.SpSummon:
            return self.Pick(cards, [CardId.RedRansom, CardId.HeartsCrypter, CardId.CyberseWicckid, CardId.BackupIgnister,
                                     CardId.ChessyCat, CardId.WhiteRabbit, CardId.Dormouse], min_, max_)
        if source == CardId.HeartsCrypter:
            if hint in (HintMsg.ToDeck, HintMsg.Target) and mine:
                rank = lambda c: (c.IsCode(*SELF_SUMMON_PAWNS), c.IsMonster())
                return self.Util.CheckSelectCount(sorted(mine, key=rank), cards, min_, max_)
            if theirs:
                return self.Util.CheckSelectCount(theirs, cards, min_, max_)
        if source in (CardId.FirewallDragon, CardId.DominusSpark, CardId.SPLittleKnight) and theirs:
            return self.Util.CheckSelectCount(theirs, cards, min_, max_)
        return super().OnSelectCard(cards, min_, max_, hint, cancelable)
