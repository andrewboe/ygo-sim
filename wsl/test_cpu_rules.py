"""Checks the Master Duel CPU battle rules in board.py on hand-built boards (no engine needed).
Run from ~/ygo/run: python test_cpu_rules.py"""
import numpy as np

import board

A, D, SET = 0x1, 0x4, 0x8


def m(atk, dfn=0, pos=A, code=1):
    return code, atk, dfn, pos


def test_battle_damage():
    assert board.battle_damage([m(3000), m(1500)], []) == 4500
    assert board.battle_damage([m(3000), m(1500)], [m(2000)]) == 1000 + 1500   # 3000 beats the 2000 attacker
    assert board.battle_damage([m(3000), m(1500)], [m(0, 2500, D)]) == 1500     # 3000 clears the wall, no damage
    assert board.battle_damage([m(1500)], [m(0, 2500, D)]) == 0                 # wall holds: no direct attacks
    assert board.battle_damage([m(2000, pos=D)], []) == 0                       # Defense Position can't attack
    assert board.battle_damage([m(2000, pos=D)], [], next_turn=True) == 2000    # ...but may switch next turn
    assert board.battle_damage([m(1800)], [m(0, 0, SET)]) == 0                  # a set monster eats the attack
    assert board.battle_damage([m(0)], []) == 0


def prompt(code_id, turn=3, opp=(), own=(), lp=8000):
    """Fake info for a position prompt: P0 to play, options "1" (face-up ATK) and "3" (face-up DEF)."""
    stats, codes, counts = np.zeros((2, 7, 3), int), np.zeros((2, 13), int), np.zeros((2, 7), int)
    for p, mons in ((0, own), (1, opp)):
        for s, (c, a, d, pos) in enumerate(mons):
            stats[p, s], codes[p, s] = (a, d, pos), c
        counts[p, 0] = len(mons)
    return {"to_play": [0], "option_card_": [[code_id, code_id]], "option_act_": [[ord("1"), ord("3")]],
            "turn": [turn], "lp_": [[lp, 8000]], "field_stats_": [stats], "field_codes_": [codes], "board_": [counts]}


def test_position_choice():
    board._CARD_STATS = {11: (1800, 1000), 12: (500, 2000), 13: (0, 1500), 14: (1200, 2600), 15: (1000, 1200)}
    ids = [0, 11, 12, 13, 14, 15, 99]
    pos = lambda info: "ATK" if board.position_choice(info, 0, 2, ids) == 0 else "DEF"
    assert pos(prompt(1)) == "ATK"                                   # 1800, nothing to fear
    assert pos(prompt(1, opp=[m(2500, code=99)])) == "DEF"           # 2500 beats 1800
    assert pos(prompt(1, opp=[m(1800, code=99)])) == "ATK"           # a tie
    assert pos(prompt(3)) == "DEF"                                   # 0 ATK
    assert pos(prompt(2, turn=1)) == "DEF"                           # turn 1, DEF >= ATK
    assert pos(prompt(1, turn=1)) == "ATK"                           # turn 1, ATK > DEF
    assert pos(prompt(4, opp=[m(1500, code=99)])) == "DEF"           # 2600 clears 1500 by 500 and ATK by 1000
    assert pos(prompt(5, opp=[m(900, code=99)])) == "ATK"            # ATK beats the threat
    assert pos(prompt(1, opp=[m(2000, code=99)], lp=150)) == "DEF"   # 200 more damage than LP allows
    board._CARD_STATS = None


if __name__ == "__main__":
    test_battle_damage()
    test_position_choice()
    print("cpu rules ok")
