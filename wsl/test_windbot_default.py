"""WindBot layer checks on hand-built boards: GameAI's choices with DefaultExecutor / GenericExecutor.
Run in WSL (needs ~/ygo/run/cards.cdb)."""
from windbot import (BattlePhase, Card, CardLocation, CardPosition, ChainInfo, DuelView, ExecutorType, HintMsg,
                     MainPhase, Util)
from windbot_default import ASH, CALLED_BY_THE_GRAVE, EXCITON, POT_OF_DESIRES, STARDUST, GenericExecutor
from windbot_gameai import BattlePhaseAction, MainPhaseAction

M = CardLocation.MonsterZone
B = BattlePhaseAction.BattleAction


def monster(id_, seq, ctl, atk, dfn, pos=CardPosition.FaceUpAttack):
    return Card(id_, M, seq, ctl, pos, atk, dfn, 4)


def executor(bot=(), enemy=(), chain=(), player=0, turn=2):
    ex = GenericExecutor()
    ex.Duel = DuelView()
    ex.Bot, ex.Enemy = ex.Duel.Fields
    for f, cards in ((ex.Bot, bot), (ex.Enemy, enemy)):
        for c in cards:
            f.MonsterZone[c.Sequence] = c
    ex.Duel.Player, ex.Duel.Turn = player, turn
    ex.Duel.CurrentChain = list(chain)
    ex.Duel.CurrentChainInfo = [ChainInfo(c) for c in chain]
    ex.Duel.LastChainPlayer = chain[-1].Controller if chain else -1
    ex.Util = Util(ex.Bot, ex.Enemy, ex.Duel)
    ex.AI.Executor = ex
    return ex


def battle(ex, attackers):
    b = BattlePhase()
    b.AttackableCards = list(attackers)
    for c in attackers:
        c.CanDirectAttack = not ex.Enemy.GetMonsters()
    b.CanMainPhaseTwo = b.CanEndPhase = True
    return ex.AI.OnSelectBattleCmd(b)


def test_battle_direct_attack_weakest_first():
    strong, weak = monster(STARDUST, 0, 0, 2500, 2000), monster(EXCITON, 1, 0, 1900, 0)
    ex = executor([strong, weak])
    r = battle(ex, [strong, weak])
    assert r.Action == B.Attack and r.Card == weak and r.Target is None


def test_battle_attacks_what_it_beats_and_queues_target():
    strong, weak = monster(STARDUST, 0, 0, 2500, 2000), monster(EXCITON, 1, 0, 1900, 0)
    defender = monster(EXCITON, 0, 1, 2000, 0)
    ex = executor([strong, weak], [defender])
    r = battle(ex, [strong, weak])
    assert r.Action == B.Attack and r.Card == strong and r.Target == defender
    assert ex.AI.OnSelectCard([defender], 1, 1, HintMsg.AttackTarget, False) == [defender]


def test_battle_defense_position_uses_def():
    weak = monster(EXCITON, 1, 0, 1900, 0)
    wall = monster(STARDUST, 0, 1, 2500, 1500, CardPosition.FaceUpDefence)  # 1500 DEF in Defense Position
    ex = executor([weak], [wall])
    r = battle(ex, [weak])
    assert r.Action == B.Attack and r.Target == wall


def test_battle_no_good_attack_goes_to_main2():
    weak = monster(EXCITON, 1, 0, 1900, 0)
    ex = executor([weak], [monster(STARDUST, 0, 1, 2500, 2000)])
    assert battle(ex, [weak]).Action == B.ToMainPhaseTwo


def test_battle_trade_only_as_last_attacker():
    a, b = monster(EXCITON, 0, 0, 1900, 0), monster(EXCITON, 1, 0, 1900, 0)
    defender = monster(EXCITON, 0, 1, 1900, 0)
    ex = executor([a, b], [defender])
    r = battle(ex, [a, b])
    assert r.Target == defender and r.Card.IsLastAttacker


def test_zero_atk_defense():
    ex = executor()
    up = [CardPosition.FaceUpAttack, CardPosition.FaceUpDefence]
    assert ex.AI.OnSelectPosition(ASH, up) == CardPosition.FaceUpDefence
    assert ex.AI.OnSelectPosition(STARDUST, up) == CardPosition.FaceUpAttack and ex.AI.fallback
    ex.AI.SelectPosition(CardPosition.FaceUpAttack)
    assert ex.AI.OnSelectPosition(ASH, up) == CardPosition.FaceUpAttack  # a queued position wins


def test_ash_chains_enemy_only():
    ash = Card(ASH, CardLocation.Hand)
    ex = executor(chain=[Card(POT_OF_DESIRES, CardLocation.SpellZone, Controller=1)])
    assert ex.AI.OnSelectChain([ash], [-1], [False]) == 0
    ex = executor(chain=[Card(POT_OF_DESIRES, CardLocation.SpellZone, Controller=0)])
    assert ex.AI.OnSelectChain([ash], [-1], [False]) == -1


def test_maxx_c_on_enemy_turn():
    maxx = Card(23434538, CardLocation.Hand)
    assert executor(player=1).AI.OnSelectChain([maxx], [-1], [False]) == 0
    assert executor(player=0).AI.OnSelectChain([maxx], [-1], [False]) == -1


def test_called_by_the_grave_negates_for_two_turns():
    ex = executor(turn=3)
    cbtg = Card(CALLED_BY_THE_GRAVE, CardLocation.SpellZone, Controller=1)
    ex.Duel.CurrentChain, ex.Duel.CurrentChainInfo = [cbtg], [ChainInfo(cbtg, 1)]
    ex.Duel.SolvingChainIndex = 1
    ex.AI.OnMove(Card(ASH, CardLocation.Removed), 0, CardLocation.Grave, 0, CardLocation.Removed)
    ash = Card(ASH, CardLocation.Hand)
    assert ex.DefaultCheckWhetherCardIsNegated(ash)
    ex.AI.OnNewTurn()
    assert ex.DefaultCheckWhetherCardIsNegated(ash)
    ex.AI.OnNewTurn()
    assert not ex.DefaultCheckWhetherCardIsNegated(ash)


def test_lock_bird_resolution_and_negation():
    ex = executor()
    bird = Card(94145021, CardLocation.Hand, Controller=1)
    ex.Duel.CurrentChain, ex.Duel.CurrentChainInfo = [bird], [ChainInfo(bird, 1)]
    ex.Duel.SolvingChainIndex = 1
    ex.Duel.NegatedChainIndexList = [1]
    ex.AI.OnChainSolved(1)
    assert ex.DefaultCheckWhetherBotCanSearch()
    ex.Duel.NegatedChainIndexList = []
    ex.AI.OnChainSolved(1)
    assert not ex.DefaultCheckWhetherBotCanSearch()


def test_selector_stack_and_chain_end():
    ex = executor()
    a, b = Card(ASH, CardLocation.Hand, 0), Card(STARDUST, CardLocation.Extra, 0)
    ex.AI.SelectCard(STARDUST)
    ex.AI.SelectNextCard(ASH)  # answers the prompt after the next one
    assert ex.AI.OnSelectCard([a, b], 1, 1, HintMsg.SpSummon, False) == [b]
    assert ex.AI.OnSelectCard([a, b], 1, 1, HintMsg.AddToHand, False) == [a]
    ex.AI.SelectCard(ASH)
    ex.AI.OnChainEnd()
    ex.AI.fallback = False
    ex.AI.OnSelectCard([a, b], 1, 1, HintMsg.AddToHand, False)
    assert ex.AI.fallback


def test_idle_rows_in_order_then_battle():
    pot = Card(POT_OF_DESIRES, CardLocation.Hand, 0)
    ex = executor([monster(STARDUST, 0, 0, 2500, 2000)])
    ex.Bot.Deck = [Card(ASH, CardLocation.Deck, k) for k in range(20)]
    main = MainPhase()
    main.ActivableCards, main.ActivableDescs = [pot], [-1]
    main.CanBattlePhase = main.CanEndPhase = True
    r = ex.AI.OnSelectIdleCmd(main)
    assert r.Action == MainPhaseAction.MainAction.Activate and r.Card == pot
    ex.Bot.Deck = ex.Bot.Deck[:10]  # Pot of Desires needs more than 15 cards
    r = ex.AI.OnSelectIdleCmd(main)
    assert r.Action == MainPhaseAction.MainAction.ToBattlePhase and ex.AI.fallback


def test_default_no_executor_row():
    ex = executor()
    ex.rows = [(ExecutorType.SpellSet, POT_OF_DESIRES, lambda: False), (ExecutorType.SpellSet, None, ex._DefaultNoExecutor)]
    pot, other = Card(POT_OF_DESIRES, CardLocation.Hand), Card(CALLED_BY_THE_GRAVE, CardLocation.Hand)
    assert not ex.AI.ShouldExecute(ex.rows[1], pot, ExecutorType.SpellSet)
    assert ex.AI.ShouldExecute(ex.rows[1], other, ExecutorType.SpellSet)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("ok")
