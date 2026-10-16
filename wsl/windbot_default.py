"""WindBot's DefaultExecutor, ported for the card handlers (docs/windbot_plan.md, phase 2).

From IceYGO/windbot Game/AI/DefaultExecutor.cs (MIT, see THIRD_PARTY_NOTICES.md): the shared Default*
conditions deck executors use for staples, the on-targeted / negation / search checks, and the battle rules
(attack target choice, OnPreBattleBetween, OnSelectPosition). Names follow the C# so ports read side by side.

Kept for the field-deck pool; left out: Kaiju, Vaylantz, Diabellze, Chicken Game, Dimensional Barrier, Honest,
Timelords (no pool cards use them). Approximations, because the env doesn't expose them: cards are never
"disabled", Infinite Impermanence's column lock isn't tracked, Crossout Designator's declared name isn't known,
and the Called by the Grave / Mistaken Arrest / Dimension Shifter counters only see this rollout's turns.

GenericExecutor is the executor for decks WindBot has none for: the pool's hand traps and staples with their
Default* rules, the usual WindBot rows for repositioning and Spell/Trap sets.
"""
import json
import os

from windbot import (AIRecorder, Card, CardAttribute, CardLocation, CardPosition, CardType, DuelPhase, Executor,
                     ExecutorType, GetFloodgate, GetHighestAttackMonster, GetShouldBeDisabledBeforeItUseEffectMonster)

_LISTS = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "windbot_lists.json")))["lists"]


class _Ids:
    """DefaultExecutor's _CardId / _Setcode; names WindBot doesn't define read as 0 (match nothing)."""

    def __init__(self, table):
        self.__dict__.update(table)

    def __getattr__(self, name):
        return 0


_CardId = _Ids(_LISTS["DefaultCardId"])
_Setcode = _Ids(_LISTS["DefaultSetcode"])


class DefaultExecutor(Executor):
    def __init__(self):
        super().__init__()
        self.AddExecutor(ExecutorType.Activate, _CardId.SantaClaws)
        self.calledbytheGraveIdCountMap = {}
        self.crossoutDesignatorIdList = []
        self.mistakenArrestAffectedCount = 0
        self.dimensionShifterCount = 0
        self.resolvedEffectIdList = []
        self.enemyResolvedEffectIdList = []
        self.infiniteImpermanenceNegatedColumns = []
        self._resolved_seen = 0

    # --- bookkeeping WindBot does in OnChainSolved / OnMove / OnNewTurn --------------------------------
    def OnNewTurn(self):
        self.infiniteImpermanenceNegatedColumns.clear()
        self.resolvedEffectIdList.clear()
        self.enemyResolvedEffectIdList.clear()
        self._resolved_seen = 0
        if self.Duel is not None and self.Duel.Turn <= 1:
            self.calledbytheGraveIdCountMap.clear()
            self.mistakenArrestAffectedCount = 0
            self.dimensionShifterCount = 0
        self.mistakenArrestAffectedCount = max(self.mistakenArrestAffectedCount - 1, 0)
        if self.dimensionShifterCount > 0:
            self.dimensionShifterCount -= 1
        for k in self.calledbytheGraveIdCountMap:
            if self.calledbytheGraveIdCountMap[k] > 0:
                self.calledbytheGraveIdCountMap[k] -= 1
        self.crossoutDesignatorIdList.clear()

    def OnUpdate(self):
        """Process chain links resolved since the last decision (card_handlers calls this every decision)."""
        for chain in self.Duel.ResolvedThisTurn[self._resolved_seen:]:
            self.OnChainSolved(chain)
        self._resolved_seen = len(self.Duel.ResolvedThisTurn)

    def OnChainSolved(self, chain):
        if chain.Negated:
            return
        if chain.IsActivateCode(_CardId.LockBird):
            self.resolvedEffectIdList.append(_CardId.LockBird)
        if chain.IsActivateCode(_CardId.DifferentDimensionGround):
            self.resolvedEffectIdList.append(_CardId.DifferentDimensionGround)
        if chain.IsActivateCode(_CardId.DimensionShifter):
            self.dimensionShifterCount = 2
        if chain.ActivatePlayer == 1:
            for id_ in (_CardId.MaxxC, _CardId.MulcharmyPurulia, _CardId.MulcharmyFuwalos, _CardId.MulcharmyNyalus):
                if id_ and chain.IsActivateCode(id_):
                    self.enemyResolvedEffectIdList.append(id_)
            if chain.IsActivateCode(_CardId.MistakenArrest):
                self.mistakenArrestAffectedCount = max(self.mistakenArrestAffectedCount, 3 if self.Duel.Player == 1 else 2)
        # OnMove: Called by the Grave banishes its target; that card's effects stay negated for two turns
        if chain.IsActivateCode(_CardId.CalledByTheGrave) and chain.Targets:
            target = chain.Targets[0]
            self.calledbytheGraveIdCountMap[target.Alias or target.Id] = 2

    # --- battle (OnSelectAttackTarget, OnPreBattleBetween, GameAI.OnSelectBattleCmd) ----------------------
    def OnSelectAttackTarget(self, attacker, defenders):
        """(attacker, defender or None for a direct attack), or None to try the next attacker."""
        for defender in defenders:
            attacker.RealPower = attacker.GetAttackPower()
            defender.RealPower = defender.GetDefensePower()
            if not self.OnPreBattleBetween(attacker, defender):
                continue
            if attacker.RealPower > defender.RealPower or \
                    (attacker.RealPower >= defender.RealPower and attacker.IsLastAttacker and defender.IsAttack()):
                return attacker, defender
        return None

    def OnPreBattleBetween(self, attacker, defender):
        if not attacker.IsMonsterHasPreventActivationEffectInBattle():
            if defender.IsMonsterInvincible() and defender.IsDefense():
                return False
            if defender.IsMonsterDangerous():
                can_ignore = (attacker.IsCode(_CardId.UltimateConductorTytanno) and defender.IsDefense() or
                              attacker.IsCode(_CardId.ElShaddollConstruct) and defender.IsSpecialSummoned or
                              attacker.IsCode(_CardId.AllyOfJusticeCatastor) and not defender.HasAttribute(CardAttribute.Dark))
                if not can_ignore:
                    return False
            if defender.IsCode(_CardId.CrystalWingSynchroDragon) and defender.IsAttack() and attacker.Level >= 5:
                defender.RealPower += attacker.Attack
            if defender.IsCode(_CardId.AllyOfJusticeCatastor) and not attacker.HasAttribute(CardAttribute.Dark):
                return False
        if not defender.IsMonsterHasPreventActivationEffectInBattle():
            if attacker.IsCode(_CardId.EaterOfMillions):
                attacker.RealPower = 9999
            if attacker.IsMonsterInvincible():
                attacker.RealPower = 9999
        enemy = self.Enemy.GetMonsters()
        # DefenderInvisbleRule entries for pool cards: Selene with an Endymion monster, Ra Sphere Mode
        if defender.IsCode(_CardId.SeleneQueenOfTheMasterMagicians) and \
                any(m.HasSetcode(_Setcode.Endymion) for m in enemy):
            return False
        if defender.IsCode(_CardId.TheWingedDragonofRaSphereMode):
            return False
        if any(m is not defender and m.IsCode(_CardId.HamonLordofStrikingThunder) and m.IsDefense() for m in enemy):
            return False
        if self.Enemy.HasInSpellZone(_CardId.ElfnotesRhapsodiaOfMadness, faceUp=True):
            center = self.Enemy.MonsterZone[2]
            if center is not None and defender is not center:
                return False
        return True

    def BattleChoice(self, attackers):
        """GameAI.OnSelectBattleCmd's attack choice: (attacker, defender-or-None) or None (leave the Battle Phase).
        `attackers`: the bot's monsters that can attack."""
        attackers = sorted(attackers, key=lambda c: c.GetAttackPower(), reverse=True)
        defenders = sorted(self.Enemy.GetMonsters(), key=lambda c: c.GetDefensePower(), reverse=True)
        if not attackers:
            return None
        if not defenders:
            direct = next((a for a in reversed(attackers) if a.GetAttackPower() > 0), None)
            return (direct, None) if direct is not None else None  # weakest attacks directly first
        for k, attacker in enumerate(attackers):
            attacker.IsLastAttacker = k == len(attackers) - 1
            result = self.OnSelectAttackTarget(attacker, defenders)
            if result is not None:
                return result
        return None

    def OnSelectPosition(self, card_id, positions):
        """0-ATK monsters go to face-up Defense Position; 0 = no opinion."""
        return CardPosition.FaceUpDefence if Card(card_id, CardLocation.Hand).Attack == 0 else 0

    def OnSelectMonsterSummonOrSet(self, card):
        """Set when this card can't beat the enemies."""
        return card.Level <= 4 and not any(m.IsFaceup() for m in self.Bot.GetMonsters()) and \
            self.Util.IsAllEnemyBetterThanValue(card.Attack, True)

    # --- removal and backrow ----------------------------------------------------------------------------
    def DefaultMysticalSpaceTyphoon(self):
        if any(c.IsCode(_CardId.MysticalSpaceTyphoon) for c in self.Duel.CurrentChain):
            return False
        spells = self.Enemy.GetSpells()
        if not spells:
            return False
        selected = GetFloodgate(self.Enemy.SpellZone)
        if selected is None:
            if self.Duel.Player == 0:
                selected = next((c for c in spells if c.IsFacedown()), None)
            if self.Duel.Player == 1:
                selected = next((c for c in spells if c.HasType(CardType.Continuous | CardType.Equip | CardType.Field)), None)
        if selected is None:
            return False
        self.AI.SelectCard(selected)
        return True

    def DefaultCosmicCyclone(self):
        if any(c.IsCode(_CardId.CosmicCyclone) for c in self.Duel.CurrentChain):
            return False
        return self.Bot.LifePoints > 1000 and self.DefaultMysticalSpaceTyphoon()

    def DefaultGalaxyCyclone(self):
        spells = self.Enemy.GetSpells()
        if not spells:
            return False
        if self.Card.Location == CardLocation.Grave:
            selected = self.Util.GetBestEnemySpell(True)
        else:
            selected = next((c for c in spells if c.IsFacedown()), None)
        if selected is None:
            return False
        self.AI.SelectCard(selected)
        return True

    def DefaultBookOfMoon(self):
        if self.Util.IsAllEnemyBetter(True):
            monster = GetHighestAttackMonster([c for c in self.Enemy.GetMonsters()
                                               if not self.IsCardAlreadyHandledInCurrentChain(c)], True)
            if monster is not None and monster.HasType(CardType.Effect) and not monster.HasType(CardType.Link) and \
                    (monster.HasType(CardType.Xyz) or monster.Level > 4):
                self.AI.SelectCard(monster)
                return True
        return False

    def DefaultCompulsoryEvacuationDevice(self):
        target = self.Util.GetProblematicEnemyMonster(0, True)
        if target is not None and not self.IsCardAlreadyHandledInCurrentChain(target):
            self.AI.SelectCard(target)
            return True
        if self.Util.IsChainTarget(self.Card):
            monster = self.Util.GetBestEnemyMonster(False, True)
            if monster is not None and not self.IsCardAlreadyHandledInCurrentChain(monster):
                self.AI.SelectCard(monster)
                return True
        return False

    def DefaultCallOfTheHaunted(self):
        if not self.Util.IsAllEnemyBetter(True):
            return False
        revivable = sorted((c for c in self.Bot.Graveyard if c.IsCanRevive()), key=lambda c: -c.Attack)
        self.AI.SelectCard(revivable[:1])
        return True

    def DefaultTorrentialTribute(self):
        if self.Util.HasChainedTrap(0) or not self.Util.IsAllEnemyBetter(True):
            return False
        return any(not self.IsCardAlreadyHandledInCurrentChain(c) for c in self.Enemy.GetMonsters())

    def DefaultHeavyStorm(self):
        return self.Bot.GetSpellCount() < self.Enemy.GetSpellCount()

    def DefaultHarpiesFeatherDusterFirst(self):
        return self.Enemy.GetSpellCount() >= 2

    def DefaultHammerShot(self):
        return self.Util.IsOneEnemyBetter(True)

    def DefaultDarkHole(self):
        return self.Util.IsOneEnemyBetter()

    DefaultRaigeki = DefaultSmashingGround = DefaultDarkHole

    # --- hand traps and negation ------------------------------------------------------------------------
    def DefaultMaxxC(self):
        if self.DefaultCheckWhetherCardIsNegated(self.Card):
            return False
        return self.Duel.Player == 1

    def DefaultAshBlossomAndJoyousSpring(self):
        if self.DefaultCheckWhetherCardIsNegated(self.Card):
            return False
        last = self.Util.GetLastChainCard()
        if last is None:
            return False
        if last.IsCode(_CardId.MacroCosmos, _CardId.UpstartGoblin, _CardId.CyberEmergency, _CardId.TheAgentOfCreationVenus):
            return False
        if last.HasSetcode(_Setcode.Danger) and last.Location == CardLocation.Hand:
            return False
        return self.Duel.LastChainPlayer == 1

    def DefaultGhostOgreAndSnowRabbit(self):
        if self.DefaultCheckWhetherCardIsNegated(self.Card):
            return False
        return self.DefaultTrap()

    def DefaultGhostBelleAndHauntedMansion(self):
        if self.DefaultCheckWhetherCardIsNegated(self.Card):
            return False
        return self.DefaultTrap()

    def DefaultEffectVeiler(self):
        if self.DefaultCheckWhetherCardIsNegated(self.Card):
            return False
        last = self.Util.GetLastChainCard()
        if last is not None and (last.IsCode(_CardId.GalaxySoldier) and len(self.Enemy.Hand) >= 3 or
                                 last.IsCode(_CardId.EffectVeiler, _CardId.InfiniteImpermanence)):
            return False
        return self.DefaultBreakthroughSkill()

    def DefaultCalledByTheGrave(self):
        targets = (_CardId.MaxxC, _CardId.LockBird, _CardId.GhostOgreAndSnowRabbit, _CardId.AshBlossom,
                   _CardId.GhostBelle, _CardId.EffectVeiler, _CardId.ArtifactLancea)
        if self.Duel.LastChainPlayer == 1:
            last = self.Util.GetLastChainCard()
            for id_ in targets:
                if last.IsCode(id_):
                    self.AI.SelectCard(id_)
                    return self.UniqueFaceupSpell()
        return False

    def DefaultInfiniteImpermanence(self):
        if self.DefaultCheckWhetherCardIsNegated(self.Card):
            return False
        last = self.Util.GetLastChainCard()
        if last is not None and (last.IsCode(_CardId.GalaxySoldier) and len(self.Enemy.Hand) >= 3 or
                                 last.IsCode(_CardId.EffectVeiler, _CardId.InfiniteImpermanence)):
            return False
        return self.DefaultDisableMonster()

    def DefaultBreakthroughSkill(self):
        if not self.DefaultUniqueTrap():
            return False
        return self.DefaultDisableMonster()

    def DefaultDisableMonster(self):
        target = self.DefaultGetDisableMonsterTarget()
        if target is None:
            return False
        self.AI.SelectCard(target)
        return True

    def DefaultGetDisableMonsterTarget(self):
        if self.Duel.Player == 1:
            target = GetShouldBeDisabledBeforeItUseEffectMonster(self.Enemy.MonsterZone)
            if target is not None:
                return target
        last = self.Util.GetLastChainCard()
        if last is not None and last.Controller == 1 and last.Location == CardLocation.MonsterZone and \
                not last.IsShouldNotBeTarget() and not last.IsShouldNotBeSpellTrapTarget():
            return last
        if self.Duel.Phase == DuelPhase.BattleStart and self.Duel.Player == 1:
            return next((c for c in self.Enemy.GetMonsters() if c.IsCode(_CardId.NumberS39UtopiaTheLightning)), None)
        return None

    def DefaultSolemnJudgment(self):
        last = self.Duel.CurrentChainInfo[-1] if self.Duel.CurrentChainInfo else None
        if last is not None and last.ActivatePlayer == 1 and \
                last.RelatedCard.IsCode(_CardId.MysticalSpaceTyphoon, _CardId.GalaxyCyclone) and \
                any(t.IsFacedown() and t.Controller == 0 for t in last.Targets):
            return False
        return not self.Util.IsChainTargetOnly(self.Card) and not (self.Duel.Player == 0 and self.Duel.LastChainPlayer == -1) \
            and not self.DefaultOnlyHorusSpSummoning() and self.DefaultTrap()

    def DefaultSolemnWarning(self):
        last = self.Util.GetLastChainCard()
        return self.Bot.LifePoints > 2000 and not (self.Duel.Player == 0 and self.Duel.LastChainPlayer == -1) \
            and not self.DefaultOnlyHorusSpSummoning() and not (last is not None and last.IsCode(_CardId.TreebornFrog)) \
            and self.DefaultTrap()

    def DefaultSolemnStrike(self):
        return self.Bot.LifePoints > 1500 and not (self.Duel.Player == 0 and self.Duel.LastChainPlayer == -1) \
            and not self.DefaultOnlyHorusSpSummoning() and self.DefaultTrap()

    def DefaultOnlyHorusSpSummoning(self):
        summoning = self.Duel.SummoningCards
        return bool(summoning) and all(c.HasSetcode(_Setcode.Horus) and c.LastLocation == CardLocation.Grave for c in summoning)

    def DefaultBottomlessTrapHole(self):
        if not self.DefaultUniqueTrap():
            return False
        return any(c.Controller == 1 and c.Attack >= 1500 and not self.IsCardAlreadyHandledInCurrentChain(c)
                   for c in self.Duel.LastSummonedCards)

    def DefaultTrap(self):
        """Chain enemy activation or summon."""
        if self.DefaultCheckWhetherCardIsNegated(self.Card):
            return False
        return (self.Duel.LastChainPlayer == -1 and self.Duel.LastSummonPlayer != 0) or self.Duel.LastChainPlayer == 1

    def DefaultUniqueTrap(self):
        if self.Util.HasChainedTrap(0):
            return False
        return self.UniqueFaceupSpell()

    def DefaultDontChainMyself(self):
        return self.Duel.LastChainPlayer != 0

    def DefaultOnBecomeTarget(self, card=None):
        card = card if card is not None else self.Card
        if card is None:
            return False
        if self.Util.IsChainTarget(card):
            return True
        destroy_all = (_CardId.EvilswarmExcitonKnight, _CardId.BlackRoseDragon, _CardId.JudgmentDragon,
                       _CardId.TopologicTrisbaena, _CardId.EvenlyMatched, _CardId.DivineArsenalAAZEUS_SkyThunder)
        if self.Util.ChainContainsCard(list(destroy_all)):
            return True
        if self.Enemy.HasInSpellZone([_CardId.HarpiesFeatherDuster, _CardId.DarkMagicAttack], faceUp=True) and \
                card.Location == CardLocation.SpellZone:
            return True
        if self.Util.ChainContainsCard([_CardId.DarkHole, _CardId.InterruptedKaijuSlumber]) and \
                card.Location == CardLocation.MonsterZone:
            return True
        if any(c.Controller == 1 and c.IsCode(_CardId.Raigeki) for c in self.Duel.CurrentChain) and \
                card.Location == CardLocation.MonsterZone:
            return True
        return False

    def IsCardAlreadyHandledInCurrentChain(self, card):
        """One of our earlier chain links already deals with this card (its target)."""
        if card is None:
            return False
        handlers = (_CardId.BookOfMoon, _CardId.CompulsoryEvacuationDevice, _CardId.EnemyController,
                    _CardId.DimensionalPrison, _CardId.RingOfDestruction, _CardId.RaigekiBreak, _CardId.KarmaCut,
                    _CardId.SakuretsuArmor, _CardId.Crackdown, _CardId.DogmatikaPunishment)
        for chain in self.Duel.CurrentChainInfo:
            if chain.ActivatePlayer != 0:
                continue
            if chain.IsCode(*handlers) and any(t.Id == card.Id and t.Controller == card.Controller for t in chain.Targets):
                return True
            if card.Controller == 1 and card.Location == CardLocation.MonsterZone and \
                    chain.IsCode(_CardId.TorrentialTribute):
                return True
            if card.Controller == 1 and card.Location == CardLocation.MonsterZone and card.IsAttack() and \
                    chain.IsCode(_CardId.DrowningMirrorForce, _CardId.BlazingMirrorForce, _CardId.StormingMirrorForce,
                                 _CardId.MirrorForce):
                return True
        return False

    # --- main phase defaults ----------------------------------------------------------------------------
    def DefaultPotOfDesires(self):
        return len(self.Bot.Deck) > 15

    def DefaultAllureofDarkness(self):
        return any(c.HasAttribute(CardAttribute.Dark) for c in self.Bot.Hand)

    def DefaultSpellSet(self):
        """Set traps (and Quick-Plays) only, keeping a zone free for other cards."""
        return (self.Card.IsTrap() or self.Card.HasType(CardType.QuickPlay) or self.DefaultSpellMustSetFirst()) and \
            self.Bot.GetSpellCountWithoutField() < 4

    def DefaultMonsterSummon(self):
        if self.Card.Level <= 4:
            return True
        if not self.UniqueFaceupMonster():
            return False
        tributes = -(-(self.Card.Level - 4) // 2)
        tributes -= sum(1 for m in self.Bot.GetMonsters() if m.GetDefensePower() < self.Card.Attack)
        return tributes <= 0

    def DefaultField(self):
        return self.Bot.SpellZone[5] is None

    def DefaultMonsterRepos(self):
        """Turn to Defense when every enemy is better; back to Attack when ours beats them."""
        card = self.Card
        if card.IsMonsterInvincible():
            return card.IsDefense()
        if card.Attack == 0:
            if card.IsFaceup() and card.IsAttack():
                return True
            if card.IsFaceup() and card.IsDefense():
                return False
        enemy_better = self.Util.IsAllEnemyBetter()
        if card.IsAttack() and enemy_better:
            return True
        if card.IsDefense() and not enemy_better and \
                (card.Attack > card.Defense or (self.Duel.Phase == DuelPhase.Main1 and card.Attack >= self.Util.GetBestPower(self.Enemy))):
            return True
        return False

    def DefaultEvilswarmExcitonKnightSummon(self):
        own = self.Bot.GetMonsterCount() + self.Bot.GetSpellCount() + self.Bot.GetHandCount()
        opp = self.Enemy.GetMonsterCount() + self.Enemy.GetSpellCount() + self.Enemy.GetHandCount()
        return own - 1 < opp and self.DefaultEvilswarmExcitonKnightEffect()

    def DefaultEvilswarmExcitonKnightEffect(self):
        own = self.Bot.GetMonsterCount() + self.Bot.GetSpellCount()
        opp = self.Enemy.GetMonsterCount() + self.Enemy.GetSpellCount()
        if own < opp:
            return True
        return sum(m.GetDefensePower() for m in self.Bot.GetMonsters()) < sum(m.GetDefensePower() for m in self.Enemy.GetMonsters())

    def DefaultStardustDragonSummon(self):
        own, opp = self.Util.GetBestAttack(self.Bot), self.Util.GetBestPower(self.Enemy)
        return (own <= opp and opp <= 2500) or self.Util.IsTurn1OrMain2()

    def DefaultStardustDragonEffect(self):
        return self.Card.Location == CardLocation.Grave or self.Duel.LastChainPlayer == 1

    # --- checks -----------------------------------------------------------------------------------------
    def UniqueFaceupSpell(self):
        return not any(c.IsCode(self.Card.Id) and c.IsFaceup() for c in self.Bot.GetSpells())

    def UniqueFaceupMonster(self):
        return not any(c.IsCode(self.Card.Id) and c.IsFaceup() for c in self.Bot.GetMonsters())

    def DefaultSpellWillBeNegated(self, card=None):
        return (self.Bot.HasInSpellZone(_CardId.ImperialOrder, faceUp=True) or self.Enemy.HasInSpellZone(_CardId.ImperialOrder, faceUp=True)) \
            and not self.Util.ChainContainsCard(_CardId.ImperialOrder) or self.DefaultCheckWhetherCardIsNegated(card or self.Card)

    def DefaultTrapWillBeNegated(self, card=None):
        return (self.Bot.HasInSpellZone(_CardId.RoyalDecreel, faceUp=True) or self.Enemy.HasInSpellZone(_CardId.RoyalDecreel, faceUp=True)) \
            and not self.Util.ChainContainsCard(_CardId.RoyalDecreel) or self.DefaultCheckWhetherCardIsNegated(card or self.Card)

    def DefaultSpellMustSetFirst(self):
        return self.Bot.HasInSpellZone(_CardId.AntiSpellFragrance, faceUp=True) or \
            self.Enemy.HasInSpellZone(_CardId.AntiSpellFragrance, faceUp=True)

    def DefaultCheckWhetherCardIsNegated(self, card):
        if card is None:
            return True
        origin = card.Alias or card.Id
        return origin in self.crossoutDesignatorIdList or self.calledbytheGraveIdCountMap.get(origin, 0) > 0

    def DefaultCheckWhetherCardIdIsNegated(self, card_id):
        return card_id in self.crossoutDesignatorIdList or self.calledbytheGraveIdCountMap.get(card_id, 0) > 0

    def GetCalledbytheGraveIdCount(self, card_id):
        return self.calledbytheGraveIdCountMap.get(card_id, 0)

    def DefaultCheckWhetherNumber41IsActive(self):
        return any(c is not None and c.IsFaceup() and c.IsCode(_CardId.Number41BagooskatheTerriblyTiredTapir) and c.IsDefense()
                   for c in self.Bot.MonsterZone + self.Enemy.MonsterZone)

    def DefaultCheckAllAvailableSpellColumnNegated(self):
        return all(self.Bot.SpellZone[k] is not None or k in self.infiniteImpermanenceNegatedColumns for k in range(5))

    def DefaultCheckWhetherSpellActivateWillBeNegated(self, card):
        if card is None:
            return False
        if card.Location == CardLocation.SpellZone:
            return card.Sequence in self.infiniteImpermanenceNegatedColumns
        return self.DefaultCheckAllAvailableSpellColumnNegated()

    def DefaultCheckWhetherBotWillBeBanished(self, card=None):
        """Subset: Macro Cosmos, the Banishers, Kashtira Arise-Heart, Dark Law, Dimensional Fissure, Dimension
        Shifter, Different Dimension Ground."""
        if self.Bot.HasInSpellZone(_CardId.ImperialIronWall, faceUp=True) or self.Enemy.HasInSpellZone(_CardId.ImperialIronWall, faceUp=True):
            return False
        if self.dimensionShifterCount > 0:
            return True
        for f in (self.Bot, self.Enemy):
            if f.HasInMonstersZone([_CardId.BanisheroftheRadiance, _CardId.BanisheroftheLight, _CardId.KashtiraAriseHeart], faceUp=True) \
                    or f.HasInSpellZone(_CardId.MacroCosmos, faceUp=True):
                return True
        if self.Enemy.HasInMonstersZone(_CardId.MaskedHERODarkLaw, faceUp=True):
            return True
        is_monster = card is None or card.IsMonster()
        if is_monster and (_CardId.DifferentDimensionGround in self.resolvedEffectIdList or
                           any(f.HasInSpellZone(_CardId.DimensionalFissure, faceUp=True) for f in (self.Bot, self.Enemy))):
            return True
        return False

    def DefaultCheckWhetherBotCanSearch(self):
        if _CardId.LockBird in self.resolvedEffectIdList or self.mistakenArrestAffectedCount > 0:
            return False
        if any(f.HasInMonstersZone(_CardId.ThunderKingRaiOh, faceUp=True) for f in (self.Bot, self.Enemy)):
            return False
        if self.Enemy.HasInMonstersZone(_CardId.ThunderDragonColossus, faceUp=True):
            return False
        if any(f.HasInSpellZone([_CardId.DeckLockdown, _CardId.Mistake], faceUp=True) for f in (self.Bot, self.Enemy)):
            return False
        if self.Enemy.HasInSpellZone(_CardId.DoomZDestruction, faceUp=True):
            return False
        return True

    def DefaultCheckWhetherBotCanDraw(self):
        return _CardId.LockBird not in self.resolvedEffectIdList

    DefaultCheckWhetherEnemyCanDraw = DefaultCheckWhetherBotCanDraw


# Pool staples WindBot deck executors activate with these Default* rules (ids from the pool's cards.cdb).
ASH, MAXX_C, VEILER, GHOST_BELLE, GHOST_OGRE = 14558127, 23434538, 97268402, 73642296, 59438930
CALLED_BY_THE_GRAVE, IMPERM, SOLEMN_JUDGMENT, SOLEMN_WARNING = 24224830, 10045474, 41420027, 84749824
MST, COSMIC_CYCLONE, POT_OF_DESIRES, ALLURE = 5318639, 8267140, 35261759, 1475311
MULCHARMY_PURULIA, MULCHARMY_FUWALOS, MULCHARMY_MEOWLS = 84192580, 42141493, 87126721
EXCITON, STARDUST = 46772449, 44508094


class GenericExecutor(DefaultExecutor):
    """For decks WindBot has no executor for: the usual staple rows deck executors add, then repositioning
    and Spell/Trap sets."""

    def __init__(self):
        super().__init__()
        a = ExecutorType.Activate
        self.AddExecutor(a, ASH, self.DefaultAshBlossomAndJoyousSpring)
        self.AddExecutor(a, MAXX_C, self.DefaultMaxxC)
        self.AddExecutor(a, MULCHARMY_PURULIA, self.DefaultMaxxC)   # same timing as Maxx "C": opponent's turn
        self.AddExecutor(a, MULCHARMY_FUWALOS, self.DefaultMaxxC)
        self.AddExecutor(a, MULCHARMY_MEOWLS, self.DefaultMaxxC)
        self.AddExecutor(a, GHOST_OGRE, self.DefaultGhostOgreAndSnowRabbit)
        self.AddExecutor(a, GHOST_BELLE, self.DefaultGhostBelleAndHauntedMansion)
        self.AddExecutor(a, VEILER, self.DefaultEffectVeiler)
        self.AddExecutor(a, IMPERM, self.DefaultInfiniteImpermanence)
        self.AddExecutor(a, CALLED_BY_THE_GRAVE, self.DefaultCalledByTheGrave)
        self.AddExecutor(a, SOLEMN_JUDGMENT, self.DefaultSolemnJudgment)
        self.AddExecutor(a, SOLEMN_WARNING, self.DefaultSolemnWarning)
        self.AddExecutor(a, MST, self.DefaultMysticalSpaceTyphoon)
        self.AddExecutor(a, COSMIC_CYCLONE, self.DefaultCosmicCyclone)
        self.AddExecutor(a, POT_OF_DESIRES, self.DefaultPotOfDesires)
        self.AddExecutor(a, ALLURE, self.DefaultAllureofDarkness)
        self.AddExecutor(ExecutorType.SpSummon, EXCITON, self.DefaultEvilswarmExcitonKnightSummon)
        self.AddExecutor(a, EXCITON, self.DefaultEvilswarmExcitonKnightEffect)
        self.AddExecutor(ExecutorType.SpSummon, STARDUST, self.DefaultStardustDragonSummon)
        self.AddExecutor(a, STARDUST, self.DefaultStardustDragonEffect)
        self.AddExecutor(ExecutorType.Repos, None, self.DefaultMonsterRepos)
        self.AddExecutor(ExecutorType.SpellSet, None, self.DefaultSpellSet)
