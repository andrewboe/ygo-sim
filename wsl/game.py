"""Stage B (THEORY §8): a full single game with search pilots on both sides.

Each turn, the turn player searches its turn with NRPA, replaying the game so far exactly (every
env deals the same duel and replays the same history), while the other player responds with a
heuristic responder. The best line found is appended to the history, and play continues until
someone wins or the turn cap, where the LP leader wins (a stand-in for time, THEORY §6).

Position evaluation at the end of the searcher's turn (for player p, until fitted from outcomes,
THEORY §5.1):
  game won/lost: +/-100
  + (LP_p - LP_opp) / 1000
  + tagged interruptions on p's field - tagged interruptions on the opponent's field
  + hand traps p holds + 0.3 per card in p's hand

Responder (non-turn player): at a chain window right after the turn player activates or summons,
use the highest-tagged live response; say yes to its own optional triggers; otherwise pass.

Run from ~/ygo/run:  python game.py DECK_FIRST DECK_SECOND [--games N] [--max-turns T]
"""
import argparse
import os
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np

sys.path.insert(0, os.path.expanduser("~/ygo/ygo-agent/ygoenv"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ygoenv  # noqa: E402
from goldfish import (CHAIN, KIND_END, KIND_PASS, KIND_PHASE, MAX_OPTIONS, PRIOR, adapt, load,  # noqa: E402
                      sample, set_opening)
from card_tags import all_tags  # noqa: E402

INFO_KEYS = ("num_options", "option_kinds_", "option_hash_", "option_card_", "option_act_", "to_play",
             "turn", "turn_player", "msg", "lp_", "field_codes_", "hand_codes_")
WIN = 100.0
MAX_TURN_STEPS = 400   # decisions within one searched turn
YESNO = (12, 13)       # MSG_SELECT_EFFECTYN, MSG_SELECT_YESNO


@dataclass
class TurnRollout:
    trace: list = field(default_factory=list)
    actions: list = field(default_factory=list)  # full history incl. the forced prefix
    score: float = float("-inf")
    ended: bool = False                           # game over during this turn
    winner: int = -1


def evaluate(info, i, p, tags, id_to_code) -> float:
    lp = info["lp_"][i]
    total = (int(lp[p]) - int(lp[1 - p])) / 1000.0
    for side, sign in ((p, 1.0), (1 - p, -1.0)):
        for c in info["field_codes_"][i][side]:
            if c:
                t = tags.get(abs(int(c)), {})
                total += sign * (t.get("set", 0.0) if c < 0 else t.get("field", 0.0))
    hand = [int(c) for c in info["hand_codes_"][i][p] if c]
    return total + sum(tags.get(c, {}).get("hand", 0.0) for c in hand) + 0.3 * len(hand)


def respond(info, i, n, kinds, tags, id_to_code, last_turn_act) -> int:
    """Heuristic for the non-turn player."""
    passes = np.flatnonzero(kinds == KIND_PASS)
    acting = [o for o in range(n) if kinds[o] != KIND_PASS]
    msg = int(info["msg"][i])
    if msg == CHAIN and acting and last_turn_act in (ord("v"), ord("s"), ord("c")):
        def value(o):
            cid = int(info["option_card_"][i][o])
            code = id_to_code[cid] if cid < len(id_to_code) else 0
            t = tags.get(code, {})
            return max(t.get("field", 0.0), t.get("set", 0.0), t.get("hand", 0.0))
        best = max(acting, key=value)
        if value(best) > 0:
            return best
    if msg in YESNO and acting:  # own optional triggers (floaters etc.): yes
        return acting[0]
    if msg != CHAIN and not len(passes):
        return 0  # forced choice (targets, positions): first option
    return int(passes[0]) if len(passes) else 0


def search_turn(envs, k, history, player, turn, gens, alpha, tags, id_to_code, rng) -> TurnRollout:
    weights = defaultdict(float)
    best = TurnRollout()
    for _ in range(gens):
        batch = turn_batch(envs, k, history, player, turn, weights, tags, id_to_code, rng)
        top = max(batch, key=lambda r: r.score)
        if top.score > best.score:
            best = top
        adapt(weights, best, alpha)
    return best


def turn_batch(envs, k, history, player, turn, weights, tags, id_to_code, rng) -> list[TurnRollout]:
    """K rollouts: replay `history`, then `player` plays turn `turn` by softmax policy."""
    _, info = envs.reset()
    info = {key: info[key].copy() for key in INFO_KEYS}
    out = [TurnRollout() for _ in range(k)]
    active = np.ones(k, dtype=bool)
    last_turn_act = np.zeros(k, dtype=int)
    last_actor = np.zeros(k, dtype=int)  # env reward is relative to whoever made the last move
    for _ in range(len(history) + MAX_TURN_STEPS):
        if not active.any():
            break
        acts = np.zeros(k, dtype=np.int32)
        for i in np.flatnonzero(active):
            n = int(info["num_options"][i])
            kinds = info["option_kinds_"][i][:n]
            t = len(out[i].actions)
            if t < len(history):
                acts[i] = history[t]
            elif int(info["to_play"][i]) == player:
                hashes = info["option_hash_"][i][:n].tolist()
                priors = np.array([PRIOR[int(x)] for x in kinds])
                acts[i], _ = sample(hashes, priors, weights, rng)
                out[i].trace.append((hashes, priors, int(acts[i])))
                last_turn_act[i] = int(info["option_act_"][i][acts[i]])
            else:
                acts[i] = respond(info, i, n, kinds, tags, id_to_code, last_turn_act[i])
            last_actor[i] = int(info["to_play"][i])
            out[i].actions.append(int(acts[i]))
        _, rew, term, trunc, step = envs.step(acts)
        for j, i in enumerate(step["env_id"]):
            if not active[i]:
                continue
            for key in INFO_KEYS:
                info[key][i] = step[key][j]
            if len(out[i].actions) <= len(history):
                continue
            if term[j] or trunc[j]:
                active[i] = False
                out[i].ended = True
                lp = step["lp_"][j]
                out[i].winner = 0 if lp[1] <= 0 < lp[0] else 1 if lp[0] <= 0 < lp[1] else -1
                if out[i].winner == -1 and rew[j] != 0:  # deck-out etc.: from the last mover's reward
                    out[i].winner = int(last_actor[i]) if rew[j] > 0 else 1 - int(last_actor[i])
                out[i].score = WIN if out[i].winner == player else 0.0 if out[i].winner == -1 else -WIN
            elif int(step["turn"][j]) > turn:
                active[i] = False
                out[i].score = evaluate(info, i, player, tags, id_to_code)
    return out


def current_state(envs, k, history):
    """Replay history; return (turn, turn player, decision player) at the next decision."""
    _, info = envs.reset()
    for a in history:
        _, _, _, _, info = envs.step(np.full(k, a, dtype=np.int32))
    return int(info["turn"][0]), int(info["turn_player"][0]), info


def play_game(envs, k, game_seed, max_turns, gens, alpha, tags, id_to_code, names=None, log=None) -> dict:
    set_opening(game_seed)
    rng = np.random.default_rng(game_seed)
    history, lp = [], (8000, 8000)
    show = lambda codes: [("(set) " if c < 0 else "") + names.get(abs(int(c)), str(c)) for c in codes if c]
    for _ in range(max_turns):
        turn, tp, info = current_state(envs, k, history)
        lp = tuple(int(x) for x in info["lp_"][0])
        if log and history:
            log(f"    after turn {turn - 1}: LP {lp}; P0 field {show(info['field_codes_'][0][0])}; "
                f"P1 field {show(info['field_codes_'][0][1])}")
        if turn > max_turns:
            break
        best = search_turn(envs, k, history, tp, turn, gens, alpha, tags, id_to_code, rng)
        history = best.actions
        if best.ended:
            if log:
                log(f"    turn {turn}: player {tp} ends the game (winner {best.winner})")
            return {"winner": best.winner, "turns": turn, "by": "game"}
    # Turn cap: LP leader wins, equal LP draws (stand-in for the end-of-match procedure).
    winner = 0 if lp[0] > lp[1] else 1 if lp[1] > lp[0] else -1
    return {"winner": winner, "turns": max_turns, "by": "turn cap", "lp": lp}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("first", help="deck going first (player 0)")
    ap.add_argument("second", help="deck going second (player 1)")
    ap.add_argument("--games", type=int, default=4)
    ap.add_argument("--max-turns", type=int, default=8)
    ap.add_argument("--rollouts", type=int, default=32)
    ap.add_argument("--generations", type=int, default=10)
    ap.add_argument("--alpha", type=float, default=1.0)
    ap.add_argument("--seed", type=int, default=5000)
    ap.add_argument("--verbose", action="store_true", help="log LP and boards after every turn")
    args = ap.parse_args()

    names = load(args.first)
    load(args.second)
    tags = all_tags()
    id_to_code = [0] + [int(l) for l in open(os.path.expanduser("~/ygo/run/code_list.txt")) if l.strip()]
    envs = ygoenv.make(task_id="EDOPro-v0", env_type="gymnasium", num_envs=args.rollouts,
                       num_threads=args.rollouts, seed=0, deck1=args.first, deck2=args.second, player=-1,
                       max_options=MAX_OPTIONS, n_history_actions=16, play_mode="self", lite=True,
                       duel_seed=args.seed)
    results, t0 = [], time.time()
    for g in range(args.games):
        r = play_game(envs, args.rollouts, g, args.max_turns, args.generations, args.alpha, tags, id_to_code,
                      names, (lambda s: print(s, flush=True)) if args.verbose else None)
        results.append(r)
        who = {0: f"first ({args.first})", 1: f"second ({args.second})", -1: "draw"}[r["winner"]]
        print(f"game {g}: {who} wins, turn {r['turns']} by {r['by']} "
              f"{r.get('lp', '')} [{time.time() - t0:.0f}s]", flush=True)
    w = np.array([r["winner"] for r in results])
    print(f"\n{args.first} (first) vs {args.second} (second): {args.games} games in {time.time() - t0:.0f}s")
    print(f"  first wins {np.mean(w == 0):.0%}, second wins {np.mean(w == 1):.0%}, draws {np.mean(w == -1):.0%}")


if __name__ == "__main__":
    main()
