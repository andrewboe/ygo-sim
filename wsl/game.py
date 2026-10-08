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

Responder (non-turn player): co-evolved within each turn's search. At response windows it samples
from its own learned policy (starting from the heuristic's pick: the highest-tagged live response
right after an activation or summon), adapted toward the rollouts worst for the turn player. Its
own optional triggers: yes; forced choices: first option.

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
from goldfish import (CHAIN, KIND_END, KIND_PASS, KIND_PHASE, MAX_OPTIONS, PRIOR, REPLAY, adapt,  # noqa: E402
                      load, sample, set_opening)
from card_tags import all_tags  # noqa: E402

INFO_KEYS = ("num_options", "option_kinds_", "option_hash_", "option_card_", "option_act_", "to_play",
             "turn", "turn_player", "msg", "lp_", "field_codes_", "hand_codes_")
WIN = 100.0
MAX_TURN_STEPS = 400   # decisions within one searched turn
YESNO = (12, 13)       # MSG_SELECT_EFFECTYN, MSG_SELECT_YESNO
IDLE = 11              # MSG_SELECT_IDLECMD
# Pilot/engine version, logged with every result; stage2.py and review.py only use matching games.
# v1 (unlogged): committed rollout transcripts. v2: each player plays its own learned policy.
CONFIG = "v2-policy-commit"


@dataclass
class TurnRollout:
    trace: list = field(default_factory=list)       # turn player's searched decisions
    resp_trace: list = field(default_factory=list)  # responder's decisions at response windows
    actions: list = field(default_factory=list)  # full history incl. the forced prefix
    score: float = float("-inf")
    ended: bool = False                           # game over during this turn
    winner: int = -1


FEATURES = ("bias", "lp_diff_k", "own_tagged", "opp_tagged", "own_field", "opp_field",
            "own_hand", "opp_hand", "own_hand_traps", "went_first")
# Hand-picked starting weights (THEORY §5.1); replaced by eval_weights.json once fitted from outcomes.
DEFAULT_WEIGHTS = {"lp_diff_k": 1.0, "own_tagged": 1.0, "opp_tagged": -1.0, "own_hand": 0.3,
                   "own_hand_traps": 1.0}
WEIGHTS_FILE = "/mnt/c/Users/andre/Desktop/ygo-sim/data/games/eval_weights.json"


def features(info, i, p, tags) -> dict:
    """Position features for player p (end of p's turn)."""
    lp = info["lp_"][i]
    f = {"bias": 1.0, "lp_diff_k": (int(lp[p]) - int(lp[1 - p])) / 1000.0, "went_first": float(p == 0)}
    for side, name in ((p, "own"), (1 - p, "opp")):
        codes = [int(c) for c in info["field_codes_"][i][side] if c]
        f[f"{name}_field"] = float(len(codes))
        f[f"{name}_tagged"] = sum(tags.get(abs(c), {}).get("set" if c < 0 else "field", 0.0) for c in codes)
        f[f"{name}_hand"] = float(sum(1 for c in info["hand_codes_"][i][side] if c))
    f["own_hand_traps"] = sum(tags.get(int(c), {}).get("hand", 0.0) for c in info["hand_codes_"][i][p] if c)
    return f


def load_weights() -> dict:
    """Fitted weights if they were fitted from games of this pilot version, else the designed ones."""
    import json
    if os.path.exists(WEIGHTS_FILE):
        fitted = json.load(open(WEIGHTS_FILE))
        if fitted.get("config") == CONFIG:
            return fitted["weights"]
    return DEFAULT_WEIGHTS


# Card hints (as in MTG Forge, where each card script tells the AI how to use it): monster hand traps
# are held, not set or normal summoned as bodies, unless nothing else is worth doing.
HINT_PENALTY = -3.0
_HAND_TRAP_MONSTERS = None


def hint_priors(cards, acts, n, tags, id_to_code) -> np.ndarray:
    global _HAND_TRAP_MONSTERS
    if _HAND_TRAP_MONSTERS is None:
        import sqlite3
        db = sqlite3.connect(os.path.expanduser("~/ygo/run/cards.cdb"))
        _HAND_TRAP_MONSTERS = {c for c, t in db.execute("select id, type from datas")
                               if t & 0x1 and tags.get(c, {}).get("hand", 0) > 0}
    out = np.zeros(n)
    for o in range(n):
        cid = int(cards[o])
        code = id_to_code[cid] if 0 < cid < len(id_to_code) else 0
        if code in _HAND_TRAP_MONSTERS and chr(int(acts[o])) in "ms":  # set / normal summon
            out[o] = HINT_PENALTY
    return out


EVAL_WEIGHTS = load_weights()


def evaluate(info, i, p, tags, id_to_code) -> float:
    """Logit of P(p wins) under the fitted weights (or the hand-picked defaults)."""
    f = features(info, i, p, tags)
    return sum(EVAL_WEIGHTS.get(k, 0.0) * v for k, v in f.items())


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


def search_turn(envs, k, history, player, turn, gens, alpha, tags, id_to_code, rng) -> tuple[dict, dict]:
    """Co-evolved search of one turn. The turn player's policy adapts toward its best rollout so far
    (NRPA); the responder's policy adapts toward each batch's worst rollout for the turn player, so
    the turn player can't win by exploiting a fixed responder rule (e.g. baiting out a negate)."""
    weights, resp_weights = defaultdict(float), defaultdict(float)
    best = TurnRollout()
    batch = []
    for _ in range(gens):
        batch = turn_batch(envs, k, history, player, turn, weights, tags, id_to_code, rng, resp_weights)
        top = max(batch, key=lambda r: r.score)
        if top.score > best.score:
            best = top
        adapt(weights, best, alpha)
        worst = min(batch, key=lambda r: r.score)
        adapt(resp_weights, TurnRollout(trace=worst.resp_trace), alpha)
    # Return both learned policies, not a rollout: the real game is then played decision by decision,
    # each player by its own policy (play_turn). Committing a rollout's transcript would also commit
    # the responder's sampled, possibly self-destructive actions from whichever rollout went best for
    # the turn player (AUDIT.md item 1).
    return weights, resp_weights


def turn_batch(envs, k, history, player, turn, weights, tags, id_to_code, rng, resp_weights=None,
               greedy=False) -> list[TurnRollout]:
    """K rollouts: replay `history`, then `player` plays turn `turn` by softmax policy (greedy: each
    player takes its policy's most likely choice, no exploration)."""
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
            if t < len(history):  # replay flag on all but the last forced move (see goldfish.REPLAY)
                acts[i] = history[t] + (REPLAY if t < len(history) - 1 else 0)
            elif int(info["to_play"][i]) == player:
                hashes = info["option_hash_"][i][:n].tolist()
                priors = np.array([PRIOR[int(x)] for x in kinds])
                if int(info["msg"][i]) == IDLE:
                    priors = priors + hint_priors(info["option_card_"][i][:n], info["option_act_"][i][:n], n,
                                                  tags, id_to_code)
                if greedy:
                    acts[i] = int(np.argmax(np.array([weights[h] for h in hashes]) + priors))
                else:
                    acts[i], _ = sample(hashes, priors, weights, rng)
                out[i].trace.append((hashes, priors, int(acts[i])))
                last_turn_act[i] = int(info["option_act_"][i][acts[i]])
            elif resp_weights is not None and int(info["msg"][i]) == CHAIN and \
                    (kinds == KIND_PASS).any() and (kinds != KIND_PASS).any():
                # Response window: the responder's learned policy, starting from the heuristic's
                # preference (respond with tagged interruptions after activations/summons).
                hashes = info["option_hash_"][i][:n].tolist()
                pref = respond(info, i, n, kinds, tags, id_to_code, last_turn_act[i])
                priors = np.where(np.arange(n) == pref, 1.0, 0.0)
                if greedy:
                    acts[i] = int(np.argmax(np.array([resp_weights[h] for h in hashes]) + priors))
                else:
                    acts[i], _ = sample(hashes, priors, resp_weights, rng)
                out[i].resp_trace.append((hashes, priors, int(acts[i])))
            else:
                acts[i] = respond(info, i, n, kinds, tags, id_to_code, last_turn_act[i])
            last_actor[i] = int(info["to_play"][i])
            out[i].actions.append(int(acts[i]) % REPLAY)
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
    for t, a in enumerate(history):
        flag = REPLAY if t < len(history) - 1 else 0
        _, _, _, _, info = envs.step(np.full(k, a + flag, dtype=np.int32))
    return int(info["turn"][0]), int(info["turn_player"][0]), info


def play_game(envs, k, game_seed, max_turns, gens, alpha, tags, id_to_code, names=None, log=None) -> dict:
    set_opening(game_seed)
    rng = np.random.default_rng(game_seed)
    history, lp = [], (8000, 8000)
    positions = []  # (player who just finished a turn, features) for outcome fitting
    show = lambda codes: [("(set) " if c < 0 else "") + names.get(abs(int(c)), str(c)) for c in codes if c]
    last_tp = None
    for _ in range(max_turns):
        turn, tp, info = current_state(envs, k, history)
        lp = tuple(int(x) for x in info["lp_"][0])
        if last_tp is not None:
            positions.append((last_tp, features(info, 0, last_tp, tags)))
        last_tp = tp
        if log and history:
            log(f"    after turn {turn - 1}: LP {lp}; P0 field {show(info['field_codes_'][0][0])}; "
                f"P1 field {show(info['field_codes_'][0][1])}")
        if turn > max_turns:
            break
        weights, resp_weights = search_turn(envs, k, history, tp, turn, gens, alpha, tags, id_to_code, rng)
        # The real turn: both players play their learned policies greedily, decision by decision.
        best = turn_batch(envs, k, history, tp, turn, weights, tags, id_to_code, rng, resp_weights,
                          greedy=True)[0]
        history = best.actions
        if best.ended:
            if log:
                log(f"    turn {turn}: player {tp} ends the game (winner {best.winner})")
            return {"winner": best.winner, "turns": turn, "by": "game", "positions": positions,
                    "history": history}
    # Position after the last searched turn (used by short screens, e.g. 2-turn going-second tests).
    turn, tp, info = current_state(envs, k, history)
    lp = tuple(int(x) for x in info["lp_"][0])
    if last_tp is not None:
        positions.append((last_tp, features(info, 0, last_tp, tags)))
    # Turn cap: LP leader wins, equal LP draws (stand-in for the end-of-match procedure).
    winner = 0 if lp[0] > lp[1] else 1 if lp[1] > lp[0] else -1
    return {"winner": winner, "turns": max_turns, "by": "turn cap", "lp": lp, "positions": positions,
            "history": history}


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
    ap.add_argument("--first-game", type=int, default=0, help="game index to start from (game seed offset)")
    args = ap.parse_args()

    names = load(args.first)
    load(args.second)
    tags = all_tags()
    id_to_code = [0] + [int(l) for l in open(os.path.expanduser("~/ygo/run/code_list.txt")) if l.strip()]
    envs = ygoenv.make(task_id="EDOPro-v0", env_type="gymnasium", num_envs=args.rollouts,
                       num_threads=args.rollouts, seed=0, deck1=args.first, deck2=args.second, player=-1,
                       max_options=MAX_OPTIONS, n_history_actions=16, play_mode="self", lite=True,
                       duel_seed=args.seed)
    import json
    os.makedirs(os.path.dirname(WEIGHTS_FILE), exist_ok=True)
    pos_log = open(os.path.join(os.path.dirname(WEIGHTS_FILE), "positions.jsonl"), "a")
    result_log = open(os.path.join(os.path.dirname(WEIGHTS_FILE), "results.jsonl"), "a")
    fitted = EVAL_WEIGHTS is not DEFAULT_WEIGHTS
    weights_tag = json.load(open(WEIGHTS_FILE))["report"] if fitted else None
    print(f"eval weights: {'fitted' if fitted else 'designed defaults'}", flush=True)
    results, t0 = [], time.time()
    for g in range(args.first_game, args.first_game + args.games):
        r = play_game(envs, args.rollouts, g, args.max_turns, args.generations, args.alpha, tags, id_to_code,
                      names, (lambda s: print(s, flush=True)) if args.verbose else None)
        results.append(r)
        for p, f in r.pop("positions"):  # label each turn-end position with that player's result
            won = 0.5 if r["winner"] == -1 else float(r["winner"] == p)
            pos_log.write(json.dumps({"config": CONFIG, "decks": [args.first, args.second], "game": g, "player": p,
                                      "features": f, "won": won}) + "\n")
        pos_log.flush()
        result_log.write(json.dumps({"config": CONFIG, "first": args.first, "second": args.second, "game": g,
                                     "seed": args.seed,
                                     "winner": r["winner"], "turns": r["turns"], "by": r["by"],
                                     "eval": "fitted" if weights_tag else "default",
                                     "eval_positions": weights_tag["positions"] if weights_tag else 0,
                                     "history": r.get("history", [])}) + "\n")  # exact replay -> dataset.py
        result_log.flush()
        who = {0: f"first ({args.first})", 1: f"second ({args.second})", -1: "draw"}[r["winner"]]
        print(f"game {g}: {who} wins, turn {r['turns']} by {r['by']} "
              f"{r.get('lp', '')} [{time.time() - t0:.0f}s]", flush=True)
    w = np.array([r["winner"] for r in results])
    print(f"\n{args.first} (first) vs {args.second} (second): {args.games} games in {time.time() - t0:.0f}s")
    print(f"  first wins {np.mean(w == 0):.0%}, second wins {np.mean(w == 1):.0%}, draws {np.mean(w == -1):.0%}")


if __name__ == "__main__":
    main()
