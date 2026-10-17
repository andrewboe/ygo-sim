"""WindBot's GameAI (IceYGO/windbot Game/GameAI.cs, MIT; see THIRD_PARTY_NOTICES.md) and the driver that runs an
executor at one ygo-sim decision.

GameAI is the layer between the duel and an executor: it walks the executor's rows in WindBot's order to pick
an action (OnSelectIdleCmd, OnSelectBattleCmd, OnSelectChain...), keeps the AI.Select* queues the rows fill
(m_selector is a stack: the last SelectCard answers the next prompt), asks the executor's On* overrides first
at every prompt and falls back like WindBot. Executors call it as self.AI.

decide() turns WindBot's answer into prior offsets over the env's options: the action WindBot would take gets
PICK; at action prompts every other option whose first matching row passes gets ALSO, options whose rows all
fail get REJECT. GameAI's last-resort fallbacks ("select the first cards", "pass", "end the turn") are arbitrary,
so where WindBot would only fall back the search decides (YGOSIM_EXECUTOR_FALLBACKS=1 makes them picks for deck
executors, Executor.DECK_EXECUTOR).

Messages between decisions (MSG_MOVE, CHAINING, CHAIN_SOLVED, NEW_PHASE...) come from the env's event ring and
are replayed through the executor's callbacks before each decision, against a mirror of the chain state at
that point; the board in those callbacks is the current one (the env doesn't keep past boards).
"""
import copy
import os

import numpy as np

import windbot as wb
from windbot import CardLocation, CardPosition, CardType, ExecutorType, HintMsg, Zones

MSG_NEW_TURN, MSG_NEW_PHASE, MSG_MOVE, MSG_POS_CHANGE = 40, 41, 50, 53
MSG_SUMMONING, MSG_SUMMONED, MSG_SPSUMMONING, MSG_SPSUMMONED, MSG_FLIPSUMMONING, MSG_FLIPSUMMONED = 60, 61, 62, 63, 64, 65
MSG_CHAINING, MSG_CHAIN_SOLVING, MSG_CHAIN_SOLVED, MSG_CHAIN_END, MSG_CHAIN_NEGATED, MSG_CHAIN_DISABLED = 70, 72, 73, 74, 75, 76
MSG_BECOME_TARGET = 83


class BattlePhaseAction:
    class BattleAction:
        Attack, Activate, ToMainPhaseTwo, ToEndPhase = range(4)

    def __init__(self, action, card=None, target=None):
        self.Action, self.Card, self.Target = action, card, target


class MainPhaseAction:
    class MainAction:
        Summon, SpSummon, Repos, SetMonster, SetSpell, Activate, ToBattlePhase, ToEndPhase = range(8)

    def __init__(self, action, card=None, desc=-1):
        self.Action, self.Card, self.Desc = action, card, desc


class GameAI:
    def __init__(self):
        self.Executor = None  # set by decide(); not copied with the state
        self.m_selector, self.m_selector_pointer = [], -1
        self.m_materialSelector, self.m_materialSelectorHint = None, 0
        self.m_position = []
        self.m_place, self.m_option, self.m_number, self.m_announce, self.m_yesno = 0, -1, -1, 0, -1
        self.m_attributes, self.m_races = [], []
        self._pendingAttacker = self._pendingAttackTarget = None
        self._attackersWithInvalidPreselectedTarget = []
        self._activatedCards = {}
        self._selectingPendulumSummon = False
        self.fallback = False  # ygo-sim: the last answer came from GameAI's last-resort default

    def __deepcopy__(self, memo):
        new = GameAI.__new__(GameAI)
        memo[id(self)] = new
        for k, v in self.__dict__.items():
            new.__dict__[k] = v if k == "Executor" else copy.deepcopy(v, memo)
        return new

    @property
    def _ex(self):
        return self.Executor

    # --- callbacks (GameAI.On*: bookkeeping, then the executor)
    def OnNewTurn(self):
        self._activatedCards.clear()
        self._ex.OnNewTurn()

    def OnNewPhase(self):
        self._pendingAttacker = self._pendingAttackTarget = None
        self._attackersWithInvalidPreselectedTarget.clear()
        self.ClearSelections()
        self._selectingPendulumSummon = False
        self._ex.OnNewPhase()

    def OnMove(self, card, pc, pl, cc, cl):
        self._ex.OnMove(card, pc, pl, cc, cl)

    def OnPosChange(self, card, pp, cp):
        self._ex.OnPosChange(card, pp, cp)

    def OnChaining(self, card, player):
        self._ex.OnChaining(player, card)

    def OnSummoning(self):
        self._ex.OnSummoning()

    def OnChainSolved(self, chainIndex):
        self._ex.OnChainSolved(chainIndex)

    def OnSpSummoned(self):
        self._ex.OnSpSummoned()

    def OnSpSummoning(self):
        self._selectingPendulumSummon = False
        self._ex.OnSpSummoning()

    def OnChainEnd(self):
        self.ClearSelections()
        self._ex.OnChainEnd()

    def ClearSelections(self):
        self.m_selector.clear()
        self.m_position.clear()
        self.m_selector_pointer = -1
        self.m_materialSelector, self.m_materialSelectorHint = None, 0
        self.m_place, self.m_option, self.m_number, self.m_announce, self.m_yesno = 0, -1, -1, 0, -1
        self.m_attributes.clear()
        self.m_races.clear()

    # --- decisions
    def OnSelectBattleCmd(self, battle):
        ex = self._ex
        self._pendingAttacker = self._pendingAttackTarget = None
        for row in ex.rows:
            t, _, func = row
            if t == ExecutorType.GoToMainPhase2 and battle.CanMainPhaseTwo and self._func(row):
                return self.ToMainPhase2()
            if t == ExecutorType.GoToEndPhase and battle.CanEndPhase and self._func(row):
                return self.ToEndPhase()
            for card, desc in zip(battle.ActivableCards, battle.ActivableDescs):
                if self.ShouldExecute(row, card, ExecutorType.Activate, desc):
                    return BattlePhaseAction(BattlePhaseAction.BattleAction.Activate, card, desc)
        attackers = [c for c in battle.AttackableCards if c not in self._attackersWithInvalidPreselectedTarget]
        attackers.sort(key=wb.CompareCardAttackPower)
        attackers.reverse()
        defenders = sorted(ex.Duel.Fields[1].GetMonsters(), key=wb.CompareDefensePower)
        defenders.reverse()
        if attackers:
            selected = ex.OnSelectAttacker(attackers, defenders)
            if selected is not None and selected in attackers:
                attackers.remove(selected)
                attackers.insert(0, selected)
            result = ex.OnBattle(attackers, defenders)
            if result is not None:
                return result
            if not defenders:
                return self.Attack(attackers[-1], None)
            for k, attacker in enumerate(attackers):
                attacker.IsLastAttacker = k == len(attackers) - 1
                result = ex.OnSelectAttackTarget(attacker, defenders)
                if result is not None:
                    return result
        if battle.CanMainPhaseTwo:
            return self.ToMainPhase2()
        if battle.CanEndPhase:
            return self.ToEndPhase()
        self.fallback = True
        return self.Attack(battle.AttackableCards[0], defenders[0] if defenders else None)

    def OnSelectCard(self, cards, min_, max_, hint, cancelable):
        ex = self._ex
        if hint == HintMsg.SpSummon and self._selectingPendulumSummon:
            result = self._validate(ex.OnSelectPendulumSummon(cards, min_, max_), cards, min_, max_, cancelable)
            if result is not None:
                return result
        if hint == HintMsg.AttackTarget and self._pendingAttacker is not None:
            if self._pendingAttackTarget is not None and self._pendingAttackTarget in cards:
                return [self._pendingAttackTarget]
            if cancelable:
                self._attackersWithInvalidPreselectedTarget.append(self._pendingAttacker)
                self._pendingAttacker = self._pendingAttackTarget = None
                return []
        result = self._validate(ex.OnSelectCard(cards, min_, max_, hint, cancelable), cards, min_, max_, cancelable)
        if result is not None:
            return result
        if hint in (HintMsg.FusionMaterial, HintMsg.SynchroMaterial, HintMsg.XyzMaterial, HintMsg.LinkMaterial):
            if self.m_materialSelector is not None:
                selector = self.m_materialSelector
            else:
                if hint == HintMsg.FusionMaterial:
                    result = ex.OnSelectFusionMaterial(cards, min_, max_)
                if hint == HintMsg.SynchroMaterial:
                    result = ex.OnSelectSynchroMaterial(cards, [], 0, min_, max_)
                if hint == HintMsg.XyzMaterial:
                    result = ex.OnSelectXyzMaterial(cards, min_, max_)
                if hint == HintMsg.LinkMaterial:
                    result = ex.OnSelectLinkMaterial(cards, min_, max_)
                result = self._validate(result, cards, min_, max_, cancelable)
                if result is not None:
                    return result
                selector = self.GetSelectedCards()
        elif self.m_materialSelector is not None and hint == self.m_materialSelectorHint:
            selector = self.m_materialSelector
        else:
            selector = self.GetSelectedCards()
        if selector is not None:
            return selector.Select(cards, min_, max_)
        self.fallback = True
        return list(cards[:min_]) if len(cards) >= min_ else []

    @staticmethod
    def _validate(selected, cards, min_, max_, cancelable):
        if selected is None:
            return None
        valid = min_ <= len(selected) <= max_ or (cancelable and not selected)
        if not valid or len(set(selected)) != len(selected) or any(c is None or c not in cards for c in selected):
            return None
        return list(selected)

    def OnSelectChain(self, cards, descs, forces, timing=-1):
        ex = self._ex
        ex.OnSelectChain(cards)
        for row in ex.rows:
            for k, card in enumerate(cards):
                if self.ShouldExecute(row, card, ExecutorType.Activate, descs[k], timing):
                    return k
        for k, forced in enumerate(forces):
            if forced:
                self.fallback = True
                return k
        self.fallback = True
        return -1

    def OnSelectEffectYn(self, card, desc):
        for row in self._ex.rows:
            if self.ShouldExecute(row, card, ExecutorType.Activate, desc):
                return True
        self.fallback = True
        return False

    def OnSelectIdleCmd(self, main):
        """MainPhaseAction for the idle command (main: wb.MainPhase)."""
        ex = self._ex
        self._selectingPendulumSummon = False
        A = MainPhaseAction.MainAction
        for row in ex.rows:
            t = row[0]
            if t == ExecutorType.GoToEndPhase and main.CanEndPhase and self._func(row):
                return MainPhaseAction(A.ToEndPhase)
            if t == ExecutorType.GoToBattlePhase and main.CanBattlePhase and self._func(row):
                return MainPhaseAction(A.ToBattlePhase)
            for card, desc in zip(main.ActivableCards, main.ActivableDescs):
                if self.ShouldExecute(row, card, ExecutorType.Activate, desc):
                    return MainPhaseAction(A.Activate, card, desc)
            for card in main.MonsterSetableCards:
                if self.ShouldExecute(row, card, ExecutorType.MonsterSet):
                    return MainPhaseAction(A.SetMonster, card)
            for card in main.ReposableCards:
                if self.ShouldExecute(row, card, ExecutorType.Repos):
                    return MainPhaseAction(A.Repos, card)
            for card in main.SpecialSummonableCards:
                if self.ShouldExecute(row, card, ExecutorType.SpSummon):
                    left, right = ex.Util.GetPZone(0, 0), ex.Util.GetPZone(0, 1)
                    self._selectingPendulumSummon = card.HasType(CardType.Pendulum) and card in (left, right)
                    return MainPhaseAction(A.SpSummon, card)
            for card in main.SummonableCards:
                if self.ShouldExecute(row, card, ExecutorType.Summon):
                    return MainPhaseAction(A.Summon, card)
                if self.ShouldExecute(row, card, ExecutorType.SummonOrSet):
                    if card in main.MonsterSetableCards and ex.OnSelectMonsterSummonOrSet(card):
                        return MainPhaseAction(A.SetMonster, card)
                    return MainPhaseAction(A.Summon, card)
            for card in main.SpellSetableCards:
                if self.ShouldExecute(row, card, ExecutorType.SpellSet):
                    return MainPhaseAction(A.SetSpell, card)
        self.fallback = True
        if main.CanBattlePhase and (ex.Duel.Fields[0].HasAttackingMonster() or not main.CanEndPhase):
            return MainPhaseAction(A.ToBattlePhase)
        return MainPhaseAction(A.ToEndPhase)

    def OnSelectOption(self, options):
        selector_selected, self.m_option = self.m_option, -1
        result = self._ex.OnSelectOption(options)
        if 0 <= result < len(options):
            return result
        if 0 <= selector_selected < len(options):
            return selector_selected
        self.fallback = True
        return 0

    def OnSelectPlace(self, cardId, count, available):
        """Zone bitmask (bit = player * 16 + (Monster Zone 0 / S&T Zone 8) + sequence)."""
        if count > 1:
            self.m_place = 0
            return self.OnSelectDisfield(cardId, count, available)
        if available & 0x7f:
            player, location, filt = 0, CardLocation.MonsterZone, available & Zones.MonsterZones
        elif available & 0x1f00:
            player, location, filt = 0, CardLocation.SpellZone, (available >> 8) & Zones.SpellZones
        elif available & 0x2000:
            player, location, filt = 0, CardLocation.FieldZone, Zones.FieldZone
        elif available & 0xc000:
            player, location, filt = 0, CardLocation.PendulumZone, (available >> 14) & Zones.PendulumZones
        elif available & 0x7f0000:
            player, location, filt = 1, CardLocation.MonsterZone, (available >> 16) & Zones.MonsterZones
        elif available & 0x1f000000:
            player, location, filt = 1, CardLocation.SpellZone, (available >> 24) & Zones.SpellZones
        elif available & 0x20000000:
            player, location, filt = 1, CardLocation.FieldZone, Zones.FieldZone
        else:
            player, location, filt = 1, CardLocation.PendulumZone, (available >> 30) & Zones.PendulumZones
        selector_selected, self.m_place = self.m_place, 0
        executor_selected = self._ex.OnSelectPlace(cardId, player, location, filt)
        if executor_selected & filt:
            filt &= executor_selected
        elif selector_selected & filt:
            filt &= selector_selected
        else:
            self.fallback = True
        sequence = 0
        if location not in (CardLocation.PendulumZone, CardLocation.FieldZone):
            for z, s in ((Zones.z2, 2), (Zones.z1, 1), (Zones.z3, 3), (Zones.z0, 0), (Zones.z4, 4), (Zones.z6, 6), (Zones.z5, 5)):
                if filt & z:
                    sequence = s
                    break
        else:
            location = CardLocation.SpellZone
            if filt & Zones.FieldZone:
                sequence = 5
            if filt & Zones.z0:
                sequence = 6
            if filt & Zones.z1:
                sequence = 7
        return 1 << (player * 16 + (0 if location == CardLocation.MonsterZone else 8) + sequence)

    def OnSelectDisfield(self, hint, count, available):
        required = max(1, count)
        executor_selected = self._ex.OnSelectDisfield(hint, count, available) & available
        mirrored = (executor_selected & ((1 << 5) | (1 << 22))) == ((1 << 5) | (1 << 22)) or \
            (executor_selected & ((1 << 6) | (1 << 21))) == ((1 << 6) | (1 << 21))
        if bin(executor_selected).count("1") == required and not mirrored:
            return executor_selected
        self.fallback = True
        zones = []
        for player in (1, 0):
            for seq in (2, 1, 3, 0, 4, 6, 5):
                if available & (1 << (player * 16 + seq)):
                    zones.append(1 << (player * 16 + seq))
            for seq in (2, 1, 3, 0, 4):
                if available & (1 << (player * 16 + 8 + seq)):
                    zones.append(1 << (player * 16 + 8 + seq))
        for player in (0, 1):
            for seq in (5, 7, 6):
                if available & (1 << (player * 16 + 8 + seq)):
                    zones.append(1 << (player * 16 + 8 + seq))
        selected, remaining = 0, required
        for zone in zones:
            if remaining == 0:
                break
            if (zone == 1 << 5 and selected & (1 << 22)) or (zone == 1 << 22 and selected & (1 << 5)) or \
                    (zone == 1 << 6 and selected & (1 << 21)) or (zone == 1 << 21 and selected & (1 << 6)):
                continue
            selected |= zone
            remaining -= 1
        return selected

    def OnSelectPosition(self, cardId, positions):
        executor_selected = self._ex.OnSelectPosition(cardId, positions)
        had_selector = bool(self.m_position)
        selector_selected = self.GetSelectedPosition()
        if executor_selected in positions:
            return executor_selected
        if selector_selected in positions:
            self.fallback = not had_selector
            return selector_selected
        self.fallback = True
        return positions[0]

    def OnSelectSum(self, cards, mandatoryCards, sum_, min_, max_, hint, exactEqual):
        ex = self._ex
        selected = ex.OnSelectSum(cards, mandatoryCards, sum_, min_, max_, hint, exactEqual)
        if self.IsValidSumSelection(selected, cards, mandatoryCards, sum_, min_, max_, exactEqual):
            return selected
        if hint in (HintMsg.Release, HintMsg.SynchroMaterial):
            if self.m_materialSelector is not None:
                selected = self.m_materialSelector.Select(cards, min_, max_)
            elif hint == HintMsg.SynchroMaterial:
                selected = ex.OnSelectSynchroMaterial(cards, mandatoryCards, sum_, min_, max_)
            else:
                selected = ex.OnSelectRitualTribute(cards, mandatoryCards, sum_, min_, max_, exactEqual)
            if self.IsValidSumSelection(selected, cards, mandatoryCards, sum_, min_, max_, exactEqual):
                return selected
        ordered = [c for c in (selected or []) if c is not None and c in cards]
        ordered = list(dict.fromkeys(ordered)) + [c for c in cards if c not in ordered]
        self.fallback = True
        return self.FindSumSelection(ordered, mandatoryCards, sum_, min_, max_, exactEqual) or []

    @staticmethod
    def _can_reach(cards, index, current, min_, max_):
        if current > max_:
            return False
        if index == len(cards):
            return min_ <= current <= max_
        c = cards[index]
        if GameAI._can_reach(cards, index + 1, current + c.OpParam1, min_, max_):
            return True
        return c.OpParam2 > 0 and c.OpParam2 != c.OpParam1 and \
            GameAI._can_reach(cards, index + 1, current + c.OpParam2, min_, max_)

    def IsValidSumSelection(self, selected, cards, mandatoryCards, sum_, min_, max_, exactEqual):
        if selected is None or len(set(selected)) != len(selected) or any(c is None or c not in cards for c in selected):
            return False
        if exactEqual and not (min_ <= len(selected) <= max_):
            return False
        all_selected = list(mandatoryCards) + list(selected)
        if exactEqual:
            return self._can_reach(all_selected, 0, 0, sum_, sum_)
        if not all_selected:
            return sum_ <= 0
        mins = [min(c.OpParam1, c.OpParam2) if c.OpParam2 > 0 else c.OpParam1 for c in all_selected]
        maxs = [max(c.OpParam1, c.OpParam2) for c in all_selected]
        return sum(maxs) >= sum_ and sum(mins) - min(mins) < sum_

    def FindSumSelection(self, cards, mandatoryCards, sum_, min_, max_, exactEqual):
        if not exactEqual:
            mins = [min(c.OpParam1, c.OpParam2) if c.OpParam2 > 0 else c.OpParam1 for c in mandatoryCards]
            min_sum, max_sum = sum(mins), sum(max(c.OpParam1, c.OpParam2) for c in mandatoryCards)
            smallest = min(mins) if mins else 2 ** 31 - 1
            remaining = [0] * (len(cards) + 1)
            for k in range(len(cards) - 1, -1, -1):
                remaining[k] = remaining[k + 1] + max(cards[k].OpParam1, cards[k].OpParam2)
            result = []
            ok = self._greater(cards, remaining, sum_, 0, min_sum, max_sum, smallest, len(mandatoryCards), result)
            return result if ok else None
        sums = {0}
        for c in mandatoryCards:
            nxt = set()
            for cur in sums:
                if cur + c.OpParam1 <= sum_:
                    nxt.add(cur + c.OpParam1)
                if c.OpParam2 > 0 and c.OpParam2 != c.OpParam1 and cur + c.OpParam2 <= sum_:
                    nxt.add(cur + c.OpParam2)
            sums = nxt
        targets = {sum_ - v for v in sums}
        top = max(targets) if targets else -1
        for count in range(min_, min(max_, len(cards)) + 1):
            result = []
            if self._by_sum(cards, targets, top, 0, count, 0, result, set()):
                return result
        return None

    def _by_sum(self, cards, targets, top, index, remaining, current, result, failed):
        if remaining == 0:
            return current in targets
        if current > top or len(cards) - index < remaining:
            return False
        state = (index, remaining, current)
        if state in failed:
            return False
        c = cards[index]
        result.append(c)
        if c.OpParam2 > 0 and c.OpParam2 != c.OpParam1 and \
                self._by_sum(cards, targets, top, index + 1, remaining - 1, current + c.OpParam2, result, failed):
            return True
        if self._by_sum(cards, targets, top, index + 1, remaining - 1, current + c.OpParam1, result, failed):
            return True
        result.pop()
        if self._by_sum(cards, targets, top, index + 1, remaining, current, result, failed):
            return True
        failed.add(state)
        return False

    def _greater(self, cards, remaining, sum_, index, min_sum, max_sum, smallest, count, result):
        if count > 0 and max_sum >= sum_ and min_sum - smallest < sum_:
            return True
        if count > 0 and min_sum - smallest >= sum_:
            return False
        if index >= len(cards) or max_sum + remaining[index] < sum_:
            return False
        c = cards[index]
        m = min(c.OpParam1, c.OpParam2) if c.OpParam2 > 0 else c.OpParam1
        result.append(c)
        if self._greater(cards, remaining, sum_, index + 1, min_sum + m, max_sum + max(c.OpParam1, c.OpParam2),
                         min(smallest, m), count + 1, result):
            return True
        result.pop()
        return self._greater(cards, remaining, sum_, index + 1, min_sum, max_sum, smallest, count, result)

    def OnSelectTribute(self, cards, min_, max_, hint, cancelable):
        selected = self._ex.OnSelectTribute(cards, min_, max_, hint, cancelable)
        valid_cancel = selected is not None and cancelable and not selected
        valid = selected is not None and len(set(selected)) == len(selected) and all(c in cards for c in selected) \
            and self.IsValidTributeSelection(selected, min_, max_)
        if valid_cancel or valid:
            return selected
        self.fallback = True
        return self.FindTributeSelection(sorted(cards, key=wb.CompareCardAttack), min_, max_) or []

    def IsValidTributeSelection(self, selected, min_, max_):
        return selected is not None and all(c is not None for c in selected) and self._can_reach(selected, 0, 0, min_, max_)

    def FindTributeSelection(self, cards, min_, max_, preferMaximumCount=False):
        targets = set(range(min_, max_ + 1))
        top = min(max_, len(cards))
        for offset in range(top + 1):
            count = top - offset if preferMaximumCount else offset
            result = []
            if self._by_sum(cards, targets, max_, 0, count, 0, result, set()):
                return result
        return None

    def OnSelectYesNo(self, desc):
        selected, self.m_yesno = self.m_yesno, -1
        if selected != -1:
            return selected > 0
        self.fallback = type(self._ex).OnSelectYesNo is wb.Executor.OnSelectYesNo  # the base's "yes" is a default
        return self._ex.OnSelectYesNo(desc)

    def OnSelectBattleReplay(self):
        return self._ex.OnSelectBattleReplay()

    # --- the AI.Select* queues executors fill
    def SelectCard(self, *args):
        self.m_selector_pointer = len(self.m_selector)
        self.m_selector.append(wb.CardSelector(_what(args)))

    def SelectNextCard(self, *args):
        if self.m_selector_pointer == -1:
            self.m_selector_pointer = 0
        self.m_selector.insert(self.m_selector_pointer, wb.CardSelector(_what(args)))

    SelectThirdCard = SelectNextCard

    def SelectMaterials(self, what, hint=0):
        self.m_materialSelector = wb.CardSelector(_what((what,)))
        self.m_materialSelectorHint = hint

    def CleanSelectMaterials(self):
        self.m_materialSelector, self.m_materialSelectorHint = None, 0

    def HaveSelectedCards(self):
        return bool(self.m_selector) or self.m_materialSelector is not None

    def HaveSelectedPosition(self):
        return bool(self.m_position)

    def GetSelectedCards(self):
        return self.m_selector.pop() if self.m_selector else None

    def GetSelectedPosition(self):
        return self.m_position.pop(0) if self.m_position else CardPosition.FaceUpAttack

    def SelectPosition(self, pos):
        self.m_position.append(pos)

    def SelectPlace(self, zones):
        self.m_place = zones

    def SelectOption(self, opt):
        self.m_option = opt

    def SelectNumber(self, number):
        self.m_number = number

    def SelectAttribute(self, attribute):
        self.m_attributes = [attribute]

    def SelectAttributes(self, attributes):
        self.m_attributes = list(attributes)

    def SelectRace(self, race):
        self.m_races = [race]

    def SelectRaces(self, races):
        self.m_races = list(races)

    def SelectAnnounceID(self, id_):
        self.m_announce = id_

    def SelectYesNo(self, opt):
        self.m_yesno = 1 if opt else 0

    def Attack(self, attacker, defender):
        self._pendingAttacker, self._pendingAttackTarget = attacker, defender
        return BattlePhaseAction(BattlePhaseAction.BattleAction.Attack, attacker, defender)

    @staticmethod
    def ToEndPhase():
        return BattlePhaseAction(BattlePhaseAction.BattleAction.ToEndPhase)

    @staticmethod
    def ToMainPhase2():
        return BattlePhaseAction(BattlePhaseAction.BattleAction.ToMainPhaseTwo)

    # --- rows
    def _func(self, row):
        t, _, func = row
        return func is None or bool(func())

    def ShouldExecute(self, row, card, type_, desc=-1, timing=-1):
        ex = self._ex
        ex.SetCard(type_, card, desc, timing)
        if card is not None and card.Id != 0 and type_ == ExecutorType.Activate:
            if self._activatedCards.get(card.Id, 0) >= 9:
                return False
            if not ex.OnPreActivate(card):
                return False
        t, cid, func = row
        result = card is not None and t == type_ and (cid is None or card.IsOriginalCode(cid)) and \
            (func is None or bool(func()))
        if card is not None and card.Id != 0 and type_ == ExecutorType.Activate and result:
            self._activatedCards[card.Id] = self._activatedCards.get(card.Id, 0) + (3 if card.IsDisabled() else 1)
        return result


def _what(args):
    """SelectCard's overloads: a Card, a list of Cards, an id, ids (list or several args) or a CardLocation."""
    if len(args) == 1:
        a = args[0]
        return list(a) if isinstance(a, (list, tuple, set)) else a
    return list(args)


# --- driver: one decision of one env --------------------------------------------------------------------

PICK, ALSO, REJECT = 2.5, 0.5, -2.5
# GameAI's last-resort defaults (first cards, Attack Position, centre zone, pass, end turn) as picks for deck
# executors. Off by default: in full games they steered play toward arbitrary choices (2026-10-16 audit).
FALLBACKS = os.environ.get("YGOSIM_EXECUTOR_FALLBACKS", "0") != "0"


class _Mirror:
    """The chain state WindBot's Duel had while the messages since the last decision arrived."""

    def __init__(self):
        self.CurrentChain, self.CurrentChainInfo, self.NegatedChainIndexList = [], [], []
        self.ChainTargets, self.LastChainTargets, self.ChainTargetOnly = [], [], []
        self.LastSummonedCards, self.SummoningCards = [], []
        self.SolvingChainIndex, self.LastChainPlayer, self.LastChainLocation, self.LastSummonPlayer = 0, -1, 0, -1
        self.summon_open = False

    FIELDS = ("CurrentChain", "CurrentChainInfo", "NegatedChainIndexList", "ChainTargets", "LastChainTargets",
              "ChainTargetOnly", "LastSummonedCards", "SummoningCards", "SolvingChainIndex", "LastChainPlayer",
              "LastChainLocation", "LastSummonPlayer")


def _event_card(duel, code, ctl, loc, seq, pos):
    """The Card a message names, as the bot would see it (enemy face-down / hand / Deck cards hidden)."""
    if loc & CardLocation.Overlay:
        return wb.Card(code, CardLocation.Overlay, -1, ctl, pos)
    hidden = ctl == 1 and (loc in (CardLocation.Hand, CardLocation.Deck, CardLocation.Extra) or
                           (pos & CardPosition.FaceDown and loc in (CardLocation.MonsterZone, CardLocation.SpellZone,
                                                                    CardLocation.Removed)))
    return wb.Card(0 if hidden else code, loc, seq, ctl, pos)


def replay_events(ex, info, i, player, duel):
    """Run the executor's callbacks for the messages since its last decision (see the module docstring)."""
    ev = info["events_"][i]
    seen = getattr(ex, "_event_seq", None)
    newest = int(ev[:, 0].max())
    if seen is None:  # first decision of this executor in this rollout: start from here
        ex._event_seq, ex._mirror = newest, _Mirror()
        for k in _Mirror.FIELDS:
            setattr(ex._mirror, k, copy.copy(getattr(duel, k)))
        ex.AI.OnNewTurn()
        return
    rows = sorted((r for r in ev if int(r[0]) > seen), key=lambda r: int(r[0]))
    if not rows:
        return
    rel = lambda p: 0 if int(p) == player else 1
    m = ex._mirror
    turns_left = sum(1 for r in rows if int(r[1]) == MSG_NEW_TURN)
    real = {k: getattr(duel, k) for k in _Mirror.FIELDS + ("Turn", "Player", "Phase")}
    for k in _Mirror.FIELDS:
        setattr(duel, k, getattr(m, k))
    duel.Turn = int(info["turn"][i]) - turns_left
    try:
        for r in rows:
            _, msg, code, a, b, c, d, e = (int(x) for x in r)
            if msg == MSG_NEW_TURN:
                duel.Turn += 1
                duel.Player = rel(a)
                ex.AI.OnNewTurn()
            elif msg == MSG_NEW_PHASE:
                duel.Phase = a
                ex.AI.OnNewPhase()
            elif msg == MSG_CHAINING:
                card = duel.GetCard(rel(a), b, c) if b in (CardLocation.MonsterZone, CardLocation.SpellZone) else None
                if card is None or card.Id != code:
                    card = wb.Card(code, b, c, rel(a))
                ex.AI.OnChaining(card, rel(d))
                duel.LastChainLocation = b
                duel.ChainTargetOnly = []
                duel.LastSummonPlayer = -1
                duel.CurrentChain = duel.CurrentChain + [card]
                duel.CurrentChainInfo = duel.CurrentChainInfo + [wb.ChainInfo(card, rel(d), wb.activate_description(e, code))]
                duel.LastChainPlayer = rel(d)
            elif msg == MSG_CHAIN_SOLVING:
                duel.SolvingChainIndex = a
            elif msg in (MSG_CHAIN_NEGATED, MSG_CHAIN_DISABLED):
                duel.NegatedChainIndexList = duel.NegatedChainIndexList + [a]
            elif msg == MSG_CHAIN_SOLVED:
                ex.AI.OnChainSolved(a)
            elif msg == MSG_CHAIN_END:
                ex.AI.OnChainEnd()
                duel.LastChainPlayer, duel.LastChainLocation, duel.SolvingChainIndex = -1, 0, 0
                duel.CurrentChain, duel.CurrentChainInfo, duel.ChainTargets = [], [], []
                duel.LastChainTargets, duel.ChainTargetOnly, duel.NegatedChainIndexList = [], [], []
            elif msg == MSG_BECOME_TARGET:
                card = duel.GetCard(rel(a), b, c)
                if card is None or card.Id != code:
                    card = _event_card(duel, code, rel(a), b, c, CardPosition.FaceUpAttack)
                duel.LastChainTargets = duel.LastChainTargets + [card]
                duel.ChainTargets = duel.ChainTargets + [card]
                duel.ChainTargetOnly = duel.ChainTargetOnly + [card]
                if duel.CurrentChainInfo:
                    duel.CurrentChainInfo[-1].Targets.append(card)
            elif msg == MSG_MOVE:
                seq, pos = e & 0xFFFF, (e >> 16) & 0xFFFF
                card = _event_card(duel, code, rel(c), d, seq, pos)
                ex.AI.OnMove(card, rel(a), b, rel(c), d)
            elif msg == MSG_POS_CHANGE:
                card = duel.GetCard(rel(a), b, c)
                if card is None:
                    card = _event_card(duel, code, rel(a), b, c, e)
                ex.AI.OnPosChange(card, d, e)
            elif msg in (MSG_SUMMONING, MSG_SPSUMMONING, MSG_FLIPSUMMONING):
                card = duel.GetCard(rel(a), b, c) or _event_card(duel, code, rel(a), b, c, d)
                if not m.summon_open:
                    duel.LastSummonedCards, duel.SummoningCards = [], []
                    m.summon_open = True
                duel.LastSummonedCards = duel.LastSummonedCards + [card]
                duel.SummoningCards = duel.SummoningCards + [card]
                duel.LastSummonPlayer = card.Controller
                if msg == MSG_SPSUMMONING:
                    ex.AI.OnSpSummoning()
                else:
                    ex.AI.OnSummoning()
            elif msg in (MSG_SUMMONED, MSG_SPSUMMONED, MSG_FLIPSUMMONED):
                m.summon_open = False
                if msg == MSG_SPSUMMONED:
                    ex.AI.OnSpSummoned()
                duel.SummoningCards = []
    finally:
        for k in _Mirror.FIELDS:
            setattr(m, k, getattr(duel, k))
        for k, v in real.items():
            setattr(duel, k, v)
        ex._event_seq = newest


def resolve_desc(raw, code, duel):
    """WindBot's description for the env's 32-bit desc. With no card (yes/no and option prompts) the card is
    found among the codes in the duel whose low 12 bits match."""
    if code:
        return wb.activate_description(raw, code)
    d = raw & 0xFFFFFFFF
    if not d >> 20:
        return d
    for f in duel.Fields:
        for c in f.Hand + f.GetMonsters() + f.GetSpells() + f.Graveyard + f.Banished + f.Deck + f.ExtraDeck:
            if c.Id and (c.Id & 0xFFF) == d >> 20:
                return c.Id * 16 + (d & 0xFFFFF)
    return -1


def card_for(bot, code, zone):
    """The bot's Card an action option names (code from option_card_, zone = sequence + 1)."""
    for cards in (bot.Hand, bot.MonsterZone, bot.SpellZone, bot.Graveyard, bot.Banished, bot.ExtraDeck, bot.Deck):
        hit = [c for c in cards if c is not None and c.Id == code]
        if hit:
            return next((c for c in hit if zone and c.Sequence == zone - 1), hit[0])
    return wb.Card(code, CardLocation.Hand) if code else None


def _candidates(info, i, player, duel):
    """The prompt's candidate Cards (WindBot reuses the field's card objects; their ids become known)."""
    rel = lambda p: 0 if int(p) == player else 1
    cards, mandatory, out = [], [], []
    for k, row in enumerate(info["select_cards_"][i]):
        code, ctl, loc, seq, pos, param, mand = (int(x) for x in row)
        if not code and not loc:
            break
        r = rel(ctl)
        card = duel.GetCard(r, loc, seq) if not loc & CardLocation.Overlay else None
        if card is None:
            card = wb.Card(code, loc if not loc & CardLocation.Overlay else CardLocation.Overlay, seq, r, pos or CardPosition.FaceUpAttack)
        elif card.Id == 0 and (r == 0 or loc not in (CardLocation.MonsterZone, CardLocation.SpellZone)):
            card.SetId(code)
        card = copy.copy(card)
        card.SelectSeq = k
        card.OpParam1, card.OpParam2 = param & 0xFFFF, (param >> 16) & 0xFFFF
        if card.OpParam2 & 0x8000:
            card.OpParam1, card.OpParam2 = param & 0x7FFFFFFF, 0
        if card.OpParam2 > 0 and card.OpParam1 > card.OpParam2:
            card.OpParam1, card.OpParam2 = card.OpParam2, card.OpParam1
        out.append(card)
        (mandatory if mand else cards).append(card)
    return out, cards, mandatory


def decide(ex, info, i, n, id_to_code):
    """(offsets over the n options, {option: executor state if chosen}, state to keep whatever is chosen)."""
    out = np.zeros(n)
    msg = int(info["msg"][i])
    p = int(info["to_play"][i])
    bot, enemy, duel = wb.build_views(info, i, p)
    ex.Bot, ex.Enemy, ex.Duel, ex.Util = bot, enemy, duel, wb.Util(bot, enemy, duel)
    ex.AI.Executor = ex
    replay_events(ex, info, i, p, duel)
    code = lambda o: id_to_code[int(info["option_card_"][i][o])] if 0 < int(info["option_card_"][i][o]) < len(id_to_code) else 0
    acts = [chr(int(a)) for a in info["option_act_"][i][:n]]
    zones = [int(z) for z in info["option_zone_"][i][:n]]
    kinds = [int(k) for k in info["option_kinds_"][i][:n]]
    base = copy.deepcopy(ex._state())
    pending, keep = {}, None
    deck = ex.DECK_EXECUTOR and FALLBACKS

    def run(fn):
        """Run a GameAI decision on the current state; return (answer, state after, fell back)."""
        ex.AI.fallback = False
        answer = fn()
        after = copy.deepcopy(ex._state())
        fell = ex.AI.fallback
        ex.__dict__.update(copy.deepcopy(base))
        return answer, after, fell

    # WindBot's Duel.MainPhase / BattlePhase hold the last idle / battle command's actions until the next one
    duel.MainPhase = getattr(ex, "_main_phase", None) or duel.MainPhase
    duel.BattlePhase = getattr(ex, "_battle_phase", None) or duel.BattlePhase
    if msg in (wb.IDLE, wb.BATTLECMD, wb.CHAIN, wb.EFFECTYN):
        cards = [card_for(bot, code(o), zones[o]) if code(o) else None for o in range(n)]
        descs = [resolve_desc(int(info["option_desc_"][i][o]), code(o), duel) for o in range(n)]
        if msg == wb.IDLE:
            main = duel.MainPhase = ex._main_phase = wb.MainPhase()
            lists = {"s": main.SummonableCards, "c": main.SpecialSummonableCards, "r": main.ReposableCards,
                     "m": main.MonsterSetableCards, "t": main.SpellSetableCards}
            for o in range(n):
                if acts[o] in lists and cards[o] is not None:
                    lists[acts[o]].append(cards[o])
                elif acts[o] == "v" and cards[o] is not None:
                    main.ActivableCards.append(cards[o])
                    main.ActivableDescs.append(descs[o])
            main.CanBattlePhase, main.CanEndPhase = "b" in acts, "e" in acts
            answer, after, fell = run(lambda: ex.AI.OnSelectIdleCmd(main))
            A = MainPhaseAction.MainAction
            letter = {A.Summon: "s", A.SpSummon: "c", A.Repos: "r", A.SetMonster: "m", A.SetSpell: "t", A.Activate: "v",
                      A.ToBattlePhase: "b", A.ToEndPhase: "e"}[answer.Action]
            chosen = next((o for o in range(n) if acts[o] == letter and (answer.Card is None or cards[o] == answer.Card)
                           and (answer.Action != A.Activate or descs[o] == answer.Desc)), None)
        elif msg == wb.BATTLECMD:
            battle = duel.BattlePhase = ex._battle_phase = wb.BattlePhase()
            for o in range(n):
                if acts[o] == "a" and cards[o] is not None:
                    battle.AttackableCards.append(cards[o])
                elif acts[o] == "v" and cards[o] is not None:
                    battle.ActivableCards.append(cards[o])
                    battle.ActivableDescs.append(descs[o])
            for c in battle.AttackableCards:
                c.CanDirectAttack = not enemy.GetMonsters()
            battle.CanMainPhaseTwo, battle.CanEndPhase = "m" in acts, "e" in acts
            answer, after, fell = run(lambda: ex.AI.OnSelectBattleCmd(battle))
            B = BattlePhaseAction.BattleAction
            letter = {B.Attack: "a", B.Activate: "v", B.ToMainPhaseTwo: "m", B.ToEndPhase: "e"}[answer.Action]
            chosen = next((o for o in range(n) if acts[o] == letter and (answer.Card is None or cards[o] == answer.Card)), None)
        elif msg == wb.CHAIN:
            act_opts = [o for o in range(n) if kinds[o] != 1 and cards[o] is not None]
            forced = not any(kinds[o] == 1 for o in range(n))
            answer, after, fell = run(lambda: ex.AI.OnSelectChain([cards[o] for o in act_opts], [descs[o] for o in act_opts],
                                                                   [forced] * len(act_opts)))
            chosen = act_opts[answer] if answer >= 0 else next((o for o in range(n) if kinds[o] == 1), None)
        else:  # EFFECTYN
            yes = next((o for o in range(n) if kinds[o] != 1), None)
            card = cards[yes] if yes is not None else None
            desc = resolve_desc(int(info["prompt_desc_"][i]), card.Id if card else 0, duel)
            desc = -1 if desc in (0, 221) else desc
            answer, after, fell = run(lambda: ex.AI.OnSelectEffectYn(card, desc) if card is not None else False)
            chosen = yes if answer else next((o for o in range(n) if kinds[o] == 1), None)
        if chosen is not None and (not fell or deck):
            out[chosen] = PICK
            pending[chosen] = after
        # other options: their own first matching row (WindBot would take them if nothing ranked earlier)
        if msg in (wb.IDLE, wb.CHAIN, wb.BATTLECMD):
            types = {"s": (ExecutorType.Summon, ExecutorType.SummonOrSet), "c": (ExecutorType.SpSummon,),
                     "r": (ExecutorType.Repos,), "m": (ExecutorType.MonsterSet, ExecutorType.SummonOrSet),
                     "t": (ExecutorType.SpellSet,), "v": (ExecutorType.Activate,)}
            for o in range(n):
                if o == chosen or cards[o] is None:
                    continue
                kinds_o = (ExecutorType.Activate,) if msg == wb.CHAIN and kinds[o] != 1 else types.get(acts[o], ())
                matched = passed = False
                for row in ex.rows:
                    if row[0] not in kinds_o or (row[1] is not None and not cards[o].IsOriginalCode(row[1])):
                        continue
                    matched = True
                    ex.__dict__.update(copy.deepcopy(base))
                    if ex.AI.ShouldExecute(row, cards[o], row[0], descs[o]):
                        passed = True
                        pending[o] = copy.deepcopy(ex._state())
                        break
                ex.__dict__.update(copy.deepcopy(base))
                if passed:
                    out[o] = ALSO
                elif matched:
                    out[o] = REJECT
    elif msg in wb.SELECTS:
        sel = [int(x) for x in info["select_"][i]]
        hint, min_, max_, cancel, sum_, mode = sel
        allc, cards, mandatory = _candidates(info, i, p, duel)
        if msg == wb.SELECT_CARD:
            if hint == 575 and cancel:  # HINTMSG_FIELD_FIRST: WindBot cancels
                answer, after, fell = [], copy.deepcopy(base), False
            else:
                answer, after, fell = run(lambda: ex.AI.OnSelectCard(cards, min_, max_, hint, bool(cancel)))
        elif msg == wb.UNSELECT_CARD:
            finishable = bool(cancel & 1)
            answer, after, fell = run(lambda: ex.AI.OnSelectCard(cards, 0 if finishable else 1, 1, hint, bool(cancel)))
        elif msg == wb.TRIBUTE:
            for c in cards:
                c.OpParam1, c.OpParam2 = 1, c.OpParam1
            answer, after, fell = run(lambda: ex.AI.OnSelectTribute(cards, min_, max_, hint, bool(cancel)))
        else:
            answer, after, fell = run(lambda: ex.AI.OnSelectSum(cards, mandatory, sum_, min_, max_ if max_ > 0 else 99,
                                                                hint, mode == 0))
        keep = after  # the prompt used up the queued selection whatever is chosen
        if answer is not None and not fell:
            want = {allc.index(c) + 1 for c in answer if c in allc}
            mand = {allc.index(c) + 1 for c in mandatory}
            for o in range(n):
                combo = {int(x) for x in info["option_combo_"][i][o] if x} - mand
                if msg == wb.UNSELECT_CARD:
                    if (combo and combo <= want) or (not combo and not want and kinds[o] == 1):
                        out[o] = PICK
                elif combo == want or (not combo and not want and kinds[o] == 1):
                    out[o] = PICK
                elif combo and combo < want:
                    out[o] = ALSO
    elif msg == wb.POSITION:
        positions = [pos for pos, letter in wb.POSITION_LETTER.items() if letter in acts]
        answer, after, fell = run(lambda: ex.AI.OnSelectPosition(code(0), positions))
        keep = after
        if not fell or deck:
            out[:] = [PICK if a == wb.POSITION_LETTER.get(answer) else 0.0 for a in acts]
    elif msg == wb.YESNO:
        desc = resolve_desc(int(info["prompt_desc_"][i]), 0, duel)
        if desc == 30:
            answer, after, fell = run(lambda: ex.AI.OnSelectBattleReplay())
            fell = fell or not deck
        else:
            answer, after, fell = run(lambda: ex.AI.OnSelectYesNo(desc))
        keep = after
        if not fell or deck:
            out[:] = [PICK if (kinds[o] != 1) == bool(answer) else 0.0 for o in range(n)]
    elif msg == wb.SELECT_OPTION:
        options = [resolve_desc(int(d), 0, duel) for d in info["prompt_options_"][i][:n]]
        answer, after, fell = run(lambda: ex.AI.OnSelectOption(options))
        keep = after
        if (not fell or deck) and 0 <= answer < n:
            out[answer] = PICK
    elif msg in (wb.SELECT_PLACE, wb.SELECT_DISFIELD):
        sel = [int(x) for x in info["select_"][i]]
        hint, available, count = sel[0], sel[1] & 0xFFFFFFFF, sel[2]
        answer, after, fell = run(lambda: ex.AI.OnSelectPlace(hint, count, available))
        keep = after
        if not fell or deck:
            for o in range(n):
                a, z = acts[o], zones[o] - 1
                if z < 0:
                    continue
                bits = {"m": [z], "s": [8 + z], "o": [16 + z, 24 + z]}.get(a, [])
                if any(answer & (1 << b) for b in bits):
                    out[o] = PICK
    return out, pending, keep
