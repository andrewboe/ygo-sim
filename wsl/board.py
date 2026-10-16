"""Board reading shared by the pilot (game.py) and the card handlers (card_handlers.py).

Battle behaviour of Master Duel's CPU (duel.dll's cpu_think, read 2026-10-15), for both players:
 - lethal check: the most battle damage a side can deal through the other's Monster Zones against
   the other's LP. With lethal on board the CPU enters the Battle Phase and keeps attacking.
 - it never declares an attack with a 0-ATK monster (a debug assert in its battle think).
 - summon positions: position_choice() below, against the strongest monster that could attack it.
"""
import os

POS_FACEUP_ATTACK, POS_FACEDOWN = 0x1, 0xA
_CARD_STATS = None


def card_stats() -> dict:
    """passcode -> (ATK, DEF) printed on the card (DEF 0 for Link monsters, "?" as 0)."""
    global _CARD_STATS
    if _CARD_STATS is None:
        import sqlite3
        db = sqlite3.connect(os.path.expanduser("~/ygo/run/cards.cdb"))
        _CARD_STATS = {c: (max(a, 0), 0 if t & 0x4000000 else max(d, 0))
                       for c, a, d, t in db.execute("select id, atk, def, type from datas")}
    return _CARD_STATS


def monsters(info, i, p) -> list:
    """(passcode, ATK, DEF, position) of p's Monster Zone cards, current stats; face-down ones show ATK/DEF 0.
    field_codes_ lists Monster Zone cards first in slot order, field_stats_ is indexed by slot."""
    codes = [abs(int(c)) for c in info["field_codes_"][i][p][:int(info["board_"][i][p][0])]]
    slots = [s for s in info["field_stats_"][i][p] if int(s[2])]
    return [(c, int(s[0]), int(s[1]), int(s[2])) for c, s in zip(codes, slots)]


def battle_damage(attackers, defenders, next_turn=False) -> int:
    """Most battle damage `attackers` (monsters() list) can deal through `defenders` in one Battle Phase.
    Attackers are face-up Attack Position monsters (any face-up one next turn, when it may change position).
    Each blocker, weakest first, takes the weakest attacker that destroys it; only Attack Position blockers
    pass battle damage, and an unbeaten blocker stops every direct attack. Face-down blockers (stats hidden)
    are assumed beatable for no damage."""
    hitters = sorted(a for _, a, _, pos in attackers
                     if a > 0 and (pos & POS_FACEUP_ATTACK or (next_turn and not pos & POS_FACEDOWN)))
    blockers = sorted((a if pos & POS_FACEUP_ATTACK else d, bool(pos & POS_FACEUP_ATTACK))
                      for _, a, d, pos in defenders)
    damage = 0
    for value, attack_pos in blockers:
        k = next((j for j, x in enumerate(hitters) if x > value or (attack_pos and x == value)), None)
        if k is None:
            return damage
        x = hitters.pop(k)
        if attack_pos:
            damage += x - value
    return damage + sum(hitters)


def can_win_battle(info, i, p) -> bool:
    return battle_damage(monsters(info, i, p), monsters(info, i, 1 - p)) >= int(info["lp_"][i][1 - p])


def zero_atk_attacker(info, i, p, code) -> bool:
    """Every Attack Position copy of `code` p controls has 0 ATK (the attack option names the card, not its slot)."""
    atks = [a for c, a, _, pos in monsters(info, i, p) if c == code and pos & POS_FACEUP_ATTACK]
    return bool(atks) and max(atks) == 0


def position_choice(info, i, n, id_to_code) -> int | None:
    """Option index of the CPU's position for the monster being placed (MSG_SELECT_POSITION).
    Its rule, with T = the strongest face-up monster the opponent could attack it with (none on turn 1):
    defense for 0 ATK, on turn 1 when DEF >= ATK, or when T beats ATK by min(LP, 1000) or more;
    with DEF > ATK, defense if DEF clears T by 500 and ATK by 1000, attack if ATK >= max(T, 1700),
    defense if DEF > 1500 and no stronger monster of its own stands guard; otherwise attack unless
    T beats ATK. Stats are the printed ones: the card isn't on the field yet."""
    p = int(info["to_play"][i])
    cid = int(info["option_card_"][i][0]) if n else 0
    code = id_to_code[cid] if 0 < cid < len(id_to_code) else 0
    if not code:
        return None
    atk, dfn = card_stats().get(code, (0, 0))
    first = int(info["turn"][i]) <= 1
    threat = 0 if first else max((a for _, a, _, pos in monsters(info, i, 1 - p) if not pos & POS_FACEDOWN), default=0)
    gap = threat - atk
    if atk == 0 or (first and dfn >= atk) or gap >= min(int(info["lp_"][i][p]), 1000):
        defend = True
    elif atk < dfn and dfn >= threat + 500 and dfn > atk + 1000:
        defend = True
    elif atk < dfn and threat <= atk and atk >= 1700:
        defend = False
    elif atk < dfn and dfn > 1500 and dfn >= max((a for _, a, _, pos in monsters(info, i, p)
                                                    if not pos & POS_FACEDOWN), default=0):
        defend = True
    else:
        defend = gap > 1
    acts = [chr(int(x)) for x in info["option_act_"][i][:n]]
    for want in ("34" if defend else "12"):
        if want in acts:
            return acts.index(want)
    return None
