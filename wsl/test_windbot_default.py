"""DefaultExecutor port checks on hand-built boards (run in WSL: needs ~/ygo/run/cards.cdb)."""
from windbot import Card, CardLocation, CardPosition, ChainInfo, DuelView, Field, Util
from windbot_default import ASH, CALLED_BY_THE_GRAVE, EXCITON, POT_OF_DESIRES, STARDUST, GenericExecutor

M = CardLocation.MonsterZone


def monster(id_, seq, ctl, atk, dfn, pos=CardPosition.FaceUpAttack):
    return Card(id_, M, seq, ctl, pos, atk, dfn, 4)


def executor(bot=(), enemy=(), chain=(), player=0, turn=2):
    ex = GenericExecutor()
    ex.Bot, ex.Enemy = Field(), Field()
    for f, cards in ((ex.Bot, bot), (ex.Enemy, enemy)):
        for c in cards:
            f.MonsterZone[c.Sequence] = c
    ex.Duel = DuelView(Player=player, Turn=turn, CurrentChain=list(chain),
                       CurrentChainInfo=[ChainInfo(c) for c in chain])
    ex.Util = Util(ex.Bot, ex.Enemy, ex.Duel)
    return ex


def test_battle_direct_attack_weakest_first():
    strong, weak = monster(STARDUST, 0, 0, 2500, 2000), monster(EXCITON, 1, 0, 1900, 0)
    assert executor([strong, weak]).BattleChoice([strong, weak]) == (weak, None)


def test_battle_attacks_what_it_beats():
    strong, weak = monster(STARDUST, 0, 0, 2500, 2000), monster(EXCITON, 1, 0, 1900, 0)
    defender = monster(EXCITON, 0, 1, 2000, 0)
    ex = executor([strong, weak], [defender])
    assert ex.BattleChoice([strong, weak]) == (strong, defender)


def test_battle_no_good_attack():
    weak = monster(EXCITON, 1, 0, 1900, 0)
    ex = executor([weak], [monster(STARDUST, 0, 1, 2500, 2000)])
    assert ex.BattleChoice([weak]) is None


def test_battle_trade_only_as_last_attacker():
    a, b = monster(EXCITON, 0, 0, 1900, 0), monster(EXCITON, 1, 0, 1900, 0)
    defender = monster(EXCITON, 0, 1, 1900, 0)
    ex = executor([a, b], [defender])
    attacker, target = ex.BattleChoice([a, b])
    assert target is defender and attacker.IsLastAttacker


def test_zero_atk_defense():
    ex = executor()
    assert ex.OnSelectPosition(ASH, None) == CardPosition.FaceUpDefence
    assert ex.OnSelectPosition(STARDUST, None) == 0


def test_ash_chains_enemy_only():
    ex = executor(chain=[Card(POT_OF_DESIRES, CardLocation.SpellZone, Controller=1)])
    ex.Card = Card(ASH, CardLocation.Hand)
    assert ex.DefaultAshBlossomAndJoyousSpring()
    ex = executor(chain=[Card(POT_OF_DESIRES, CardLocation.SpellZone, Controller=0)])
    ex.Card = Card(ASH, CardLocation.Hand)
    assert not ex.DefaultAshBlossomAndJoyousSpring()


def test_maxx_c_on_enemy_turn():
    ex = executor(player=1)
    ex.Card = Card(23434538, CardLocation.Hand)
    assert ex.DefaultMaxxC()
    ex.Duel.Player = 0
    assert not ex.DefaultMaxxC()


def test_called_by_the_grave_negates_for_two_turns():
    ex = executor(turn=3)
    ex.Duel.ResolvedThisTurn = [ChainInfo(Card(CALLED_BY_THE_GRAVE, CardLocation.SpellZone, Controller=1),
                                          Card(ASH, CardLocation.Grave))]
    ex.OnUpdate()
    ex.OnUpdate()  # idempotent per decision
    ash = Card(ASH, CardLocation.Hand)
    assert ex.DefaultCheckWhetherCardIsNegated(ash)
    ex.Card = ash
    ex.Duel.CurrentChain = [Card(POT_OF_DESIRES, CardLocation.SpellZone, Controller=1)]
    assert not ex.DefaultAshBlossomAndJoyousSpring()
    ex.OnNewTurn()
    assert ex.DefaultCheckWhetherCardIsNegated(ash)
    ex.OnNewTurn()
    assert not ex.DefaultCheckWhetherCardIsNegated(ash)


def test_negated_link_ignored():
    ex = executor()
    ex.Duel.ResolvedThisTurn = [ChainInfo(Card(CALLED_BY_THE_GRAVE, CardLocation.SpellZone, Controller=1),
                                          Card(ASH, CardLocation.Grave), negated=True)]
    ex.OnUpdate()
    assert not ex.DefaultCheckWhetherCardIsNegated(Card(ASH, CardLocation.Hand))


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("ok")
