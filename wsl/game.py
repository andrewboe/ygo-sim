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
from ygoenv.edopro.edopro_ygoenv import stage_hidden  # noqa: E402
from belief import LOC_HAND, REDEAL  # noqa: E402
from goldfish import (CHAIN, KIND_ACTION, KIND_END, KIND_PASS, KIND_PHASE, MAX_OPTIONS, PRIOR, REPLAY, adapt,  # noqa: E402
                      load, sample, set_opening)
from card_tags import all_tags  # noqa: E402

INFO_KEYS = ("num_options", "option_kinds_", "option_hash_", "option_card_", "option_act_", "to_play",
             "turn", "turn_player", "msg", "lp_", "field_codes_", "hand_codes_", "public_codes_", "board_")
WIN = 100.0
MAX_TURN_STEPS = 400   # decisions within one searched turn
YESNO = (12, 13)       # MSG_SELECT_EFFECTYN, MSG_SELECT_YESNO
IDLE = 11              # MSG_SELECT_IDLECMD
# Pilot/engine version, logged with every result; stage2.py and review.py only use matching games.
# v1 (unlogged): committed rollout transcripts. v2: each player plays its own learned policy.
CONFIG = "v3-belief"  # v3: hidden information re-dealt from a belief in every search rollout
HIDDEN_INFO = True


@dataclass
class TurnRollout:
    trace: list = field(default_factory=list)       # turn player's searched decisions
    resp_trace: list = field(default_factory=list)  # responder's decisions at response windows
    actions: list = field(default_factory=list)  # full history incl. the forced prefix
    score: float = float("-inf")
    ended: bool = False                           # game over during this turn
    winner: int = -1
    unseen_at: int | None = None                  # greedy play stopped here: a choice search never saw
    window_at: int | None = None                  # greedy play stopped here: a hand-trap timing window
    window_options: list = field(default_factory=list)
    window_cards: list = field(default_factory=list)  # passcode per window option (0 = pass)
    off_plan: bool = False                         # greedy play left the search's best line


FEATURES = ("bias", "lp_diff_k", "own_tagged", "opp_tagged", "own_field", "opp_field",
            "own_hand", "opp_hand", "own_hand_traps", "went_first")
# Hand-picked starting weights (THEORY §5.1); replaced by eval_weights.json once fitted from outcomes.
# A card is a card: hand and field cards both count 0.3 (field monsters are attackers, materials and
# blockers; without it, Evenly Matched banishing two attackers scored as worthless), plus tagged
# interruption value on top.
DEFAULT_WEIGHTS = {"lp_diff_k": 1.0, "own_tagged": 1.0, "opp_tagged": -1.0, "own_hand": 0.3, "opp_hand": -0.3,
                   "own_field": 0.3, "opp_field": -0.3, "own_hand_traps": 1.0}
WEIGHTS_FILE = "/mnt/c/Users/andre/Desktop/ygo-sim/data/games/eval_weights.json"


def features(info, i, p, tags) -> dict:
    """Position features for player p (end of p's turn)."""
    lp = info["lp_"][i]
    f = {"bias": 1.0, "lp_diff_k": (int(lp[p]) - int(lp[1 - p])) / 1000.0, "went_first": float(p == 0)}
    # Interruption values count once per card name: nearly every interruption is once per turn by name
    # (three Elfnote Lucina still give one bounce; two Ash still one negate), and counting copies made
    # piles of duplicate bodies outscore real end boards. Card counts still count every copy.
    for side, name in ((p, "own"), (1 - p, "opp")):
        codes = [int(c) for c in info["field_codes_"][i][side] if c]
        f[f"{name}_field"] = float(len(codes))
        best = {}
        for c in codes:
            best[abs(c)] = max(best.get(abs(c), 0.0), tags.get(abs(c), {}).get("set" if c < 0 else "field", 0.0))
        f[f"{name}_tagged"] = sum(best.values())
        f[f"{name}_hand"] = float(sum(1 for c in info["hand_codes_"][i][side] if c))
    # Hand traps that need an empty field (Mulcharmys, Evenly Matched / Impermanence from the hand) are
    # dead while you control a card: summoning Blazing Cartesia while holding Evenly Matched wasted it.
    own_cards = sum(1 for c in info["field_codes_"][i][p] if c)
    f["own_hand_traps"] = sum(tags.get(c, {}).get("hand", 0.0) for c in {int(c) for c in info["hand_codes_"][i][p] if c}
                              if not (own_cards and c in needs_empty_field()))
    return f


_NEEDS_EMPTY = None


def needs_empty_field() -> set:
    """Cards usable from the hand only while their controller controls no cards (by card text)."""
    global _NEEDS_EMPTY
    if _NEEDS_EMPTY is None:
        import re
        import sqlite3
        db = sqlite3.connect(os.path.expanduser("~/ygo/run/cards.cdb"))
        pat = re.compile(r"if you control no cards", re.I)
        _NEEDS_EMPTY = {c for c, d in db.execute("select id, desc from texts") if d and pat.search(d)}
    return _NEEDS_EMPTY


def load_weights() -> dict:
    """Fitted weights if they were fitted from games of this pilot version, else the designed ones."""
    import json
    if os.path.exists(WEIGHTS_FILE):
        fitted = json.load(open(WEIGHTS_FILE))
        if fitted.get("config") == CONFIG:
            return fitted["weights"]
    return DEFAULT_WEIGHTS


# Card hints (as in MTG Forge, where each card script tells the AI how to use it). They shape the
# rollout policy's defaults, so search explores sensible lines first; search can still overrule them.
#  - monster hand traps are held, not set or normal summoned as bodies (IDLE)
#  - on your own turn, hand traps in chain windows default to "hold" (an unhinted prior activates them
#    ~90% of the time per window, so no rollout ever kept them: Mulcharmys burned on turn 1)
HINT_PENALTY = -5.0      # below the end-turn prior (-3): when nothing else is known, end rather than set it
OWN_TURN_TRAP_HINT = -2.5  # below the pass prior (-1)
_HAND_TRAP_MONSTERS = None


def hint_priors(cards, acts, n, tags, id_to_code, msg) -> np.ndarray:
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
        if msg == IDLE and code in _HAND_TRAP_MONSTERS and chr(int(acts[o])) in "ms":  # set / normal summon
            out[o] = HINT_PENALTY
        elif msg == CHAIN and tags.get(code, {}).get("hand", 0) > 0 and chr(int(acts[o])) == "h":  # from hand
            out[o] = OWN_TURN_TRAP_HINT
    return out


EVAL_WEIGHTS = load_weights()


def evaluate(info, i, p, tags, id_to_code) -> float:
    """Logit of P(p wins) under the fitted weights (or the hand-picked defaults)."""
    return score_features(features(info, i, p, tags))


def score_features(f: dict) -> float:
    return sum(EVAL_WEIGHTS.get(k, 0.0) * v for k, v in f.items())


# Board probe (THEORY §3, as in stage 1): at the end of the searcher's turn in a rollout, the opponent's
# first two hand cards become Card Trooper and Upstart Goblin (belief re-deal machinery); the opponent
# normal summons the Trooper, activates its effect (monster-effect negates) and activates the Goblin, and every response the engine offers the searcher is
# a live interruption. Static tags can't see placement, conditions or effects already used (Elfnote
# Lucina in the center zone can't swap; a once-per-turn effect spent on your own turn is gone).
PROBE_EVAL = True
_PROBE = None


def probe_cards(id_to_code) -> tuple[int, int, int, int]:
    """(filler code-list id, spell code-list id, filler passcode, spell passcode)."""
    global _PROBE
    if _PROBE is None:
        import sqlite3
        db = sqlite3.connect(os.path.expanduser("~/ygo/run/cards.cdb"))
        code = dict((n, c) for c, n in db.execute(
            "select id, name from texts where name in ('Card Trooper', 'Upstart Goblin')"))
        index = {c: i for i, c in enumerate(id_to_code) if c}
        f, s = code["Card Trooper"], code["Upstart Goblin"]
        _PROBE = (index[f], index[s], f, s)
    return _PROBE


def probe_step(info, i, n, kinds, st, opp, probe) -> int:
    """One decision of the probe turn: the opponent summons the filler, activates the spell, ends;
    the searcher passes everything and its offered responses after each probe action are recorded."""
    acts_ = info["option_act_"][i][:n]
    cards = info["option_card_"][i][:n]
    passes = np.flatnonzero(kinds == KIND_PASS)
    if int(info["to_play"][i]) == opp:
        if int(info["msg"][i]) == IDLE:
            st["armed"] = False
            for key, act, card in (("summoned", ord("s"), probe[0]), ("effected", ord("v"), probe[0]),
                                   ("activated", ord("v"), probe[1])):
                if not st[key]:
                    st[key] = True
                    hit = np.flatnonzero((acts_ == act) & (cards == card))
                    if len(hit):
                        st["armed"] = True
                        return int(hit[0])
            st["finished"] = True
            ends, phases = np.flatnonzero(kinds == KIND_END), np.flatnonzero(kinds == KIND_PHASE)
            return int(ends[0]) if len(ends) else int(phases[0]) if len(phases) else 0
        return int(passes[0]) if len(passes) else 0
    if int(info["msg"][i]) == CHAIN and st["armed"]:
        st["offered"].update(int(c) for o, c in enumerate(cards) if kinds[o] != KIND_PASS and c)
    return int(passes[0]) if len(passes) else 0


def start_probe(probing, i, info, player, tags, id_to_code) -> None:
    """Snapshot the searcher's position and stage the opponent's probe hand (applied by a re-deal)."""
    opp = 1 - player
    pr = probe_cards(id_to_code)
    probing[i] = {"features": features(info, i, player, tags), "redeal": True,
                  "board": np.array(info["field_codes_"][i][player]).copy(),
                  "hand": np.array(info["hand_codes_"][i][player]).copy(),
                  "summoned": False, "effected": False, "activated": False, "armed": False, "finished": False,
                  "offered": set()}
    stage_hidden(int(i), [opp, LOC_HAND, 0, pr[2], opp, LOC_HAND, 1, pr[3]])


def live_value(board, hand, offered, tags, id_to_code) -> float:
    """Live interruptions on the searcher's board: cards offered a response during the probe, once per
    name, worth their tag (at least 0.5). Hand copies answering (Ash) count as hand traps instead."""
    in_hand = {int(c) for c in hand if c}
    on_field = {abs(int(c)): int(c) < 0 for c in board if c}
    total = 0.0
    for code in {id_to_code[c] for c in offered if 0 < c < len(id_to_code)}:
        if code in on_field and code not in in_hand:
            t = tags.get(code, {})
            total += max(0.5, t.get("set" if on_field[code] else "field", 0.0))
    return total


_DRAW_TRAPS = None


def draw_traps() -> set:
    """Draw-on-summon hand traps (Mulcharmys, Maxx "C"): passcodes whose text draws each time the
    opponent summons. Real players activate them in the opponent's Standby Phase, before any summon:
    a summon already made doesn't draw."""
    global _DRAW_TRAPS
    if _DRAW_TRAPS is None:
        import re
        import sqlite3
        db = sqlite3.connect(os.path.expanduser("~/ygo/run/cards.cdb"))
        pat = re.compile(r"each time your opponent [^.]*summons[^.]*draw", re.I)
        _DRAW_TRAPS = {c for c, d in db.execute("select id, desc from texts") if d and pat.search(d)}
    return _DRAW_TRAPS


def respond(info, i, n, kinds, tags, id_to_code, last_turn_act) -> int:
    """Heuristic for the non-turn player."""
    passes = np.flatnonzero(kinds == KIND_PASS)
    acting = [o for o in range(n) if kinds[o] != KIND_PASS]
    msg = int(info["msg"][i])
    if msg == CHAIN and acting and last_turn_act == 0:  # before the turn player has done anything
        code = lambda o: id_to_code[int(info["option_card_"][i][o])] if int(info["option_card_"][i][o]) < len(id_to_code) else 0
        early = [o for o in acting if code(o) in draw_traps()]
        if early:
            return early[0]
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


def search_turn(envs, k, history, player, turn, gens, alpha, tags, id_to_code, rng) -> tuple[dict, dict, tuple]:
    """Co-evolved search of one turn. The turn player's policy adapts toward its best rollout so far
    (NRPA); the responder's policy adapts toward each batch's worst rollout for the turn player, so
    the turn player can't win by exploiting a fixed responder rule (e.g. baiting out a negate)."""
    weights, resp_weights = defaultdict(float), defaultdict(float)
    best = TurnRollout()
    batch = []
    for _ in range(gens):
        batch = turn_batch(envs, k, history, player, turn, weights, tags, id_to_code, rng, resp_weights,
                           belief=BELIEF, decider=player)
        top = max(batch, key=lambda r: r.score)
        if top.score > best.score:
            best = top
        adapt(weights, best, alpha)
        worst = min(batch, key=lambda r: r.score)
        adapt(resp_weights, TurnRollout(trace=worst.resp_trace), alpha)
    # Return both learned policies and the turn player's moves in its best line (not the rollout's
    # transcript: that would also commit the responder's sampled, possibly self-destructive actions,
    # AUDIT.md item 1). The real turn follows those moves while they stay available (play_turn).
    plan = tuple(h[c] for h, _, c in best.trace)
    return weights, resp_weights, plan


def turn_batch(envs, k, history, player, turn, weights, tags, id_to_code, rng, resp_weights=None,
               greedy=False, stop_unseen=False, stop_windows=False, first_actions=None, belief=None,
               decider=None, held_windows=frozenset(), plan=(), probe_now=False) -> list[TurnRollout]:
    """K rollouts: replay `history`, then `player` plays turn `turn` by softmax policy (greedy: each
    player takes its policy's most likely choice, no exploration; stop_unseen: stop at the first
    turn-player choice between 2+ actions that the search never visited, for re-planning;
    stop_windows: stop where the non-turn player can use a tagged interruption or pass;
    first_actions[i]: env i's first move after `history`, for comparing choices at one decision;
    probe_now: start the board probe right after `history` (measuring the board a history ends on);
    plan: option hashes of the turn player's moves in the search's best line; greedy play follows them
    in order while each is available, then falls back to the policy;
    belief: before `decider`'s first decision after `history`, each env re-deals what the decider
    can't see from the belief (belief.py), so search can't use hidden cards)."""
    _, info = envs.reset()
    info = {key: info[key].copy() for key in INFO_KEYS}
    out = [TurnRollout() for _ in range(k)]
    active = np.ones(k, dtype=bool)
    last_turn_act = np.zeros(k, dtype=int)
    last_actor = np.zeros(k, dtype=int)  # env reward is relative to whoever made the last move
    redealt = np.zeros(k, dtype=bool)
    plan_pos = np.zeros(k, dtype=int)
    probing = [None] * k  # per-env probe state once the searcher's turn has ended (not in greedy play)
    on_plan = np.full(k, bool(plan))
    for _ in range(len(history) + MAX_TURN_STEPS):
        if not active.any():
            break
        acts = np.zeros(k, dtype=np.int32)
        for i in np.flatnonzero(active):
            n = int(info["num_options"][i])
            kinds = info["option_kinds_"][i][:n]
            t = len(out[i].actions)
            if probe_now and probing[i] is None and t >= len(history):
                start_probe(probing, i, info, player, tags, id_to_code)
            if probing[i] is not None:  # evaluation probe: not part of the line, not recorded
                if probing[i]["redeal"]:
                    acts[i], probing[i]["redeal"] = REDEAL, False
                else:
                    acts[i] = probe_step(info, i, n, kinds, probing[i], 1 - player, probe_cards(id_to_code))
                continue
            if t < len(history):  # replay flag on all but the last forced move (see goldfish.REPLAY)
                acts[i] = history[t] + (REPLAY if t < len(history) - 1 else 0)
            elif belief is not None and not redealt[i] and int(info["to_play"][i]) == decider:
                stage_hidden(int(i), belief.sample(rng, decider, info, i))
                acts[i] = REDEAL  # same decision, hidden cards re-dealt; not part of the history
                redealt[i] = True
                continue
            elif first_actions is not None and t == len(history):
                acts[i] = first_actions[i]
            elif int(info["to_play"][i]) == player:
                hashes = info["option_hash_"][i][:n].tolist()
                priors = np.array([PRIOR[int(x)] for x in kinds])
                if int(info["msg"][i]) in (IDLE, CHAIN):
                    priors = priors + hint_priors(info["option_card_"][i][:n], info["option_act_"][i][:n], n,
                                                  tags, id_to_code, int(info["msg"][i]))
                if stop_unseen and int((kinds == 0).sum()) >= 2 and not any(weights.get(h, 0.0) for h in hashes):
                    out[i].unseen_at = len(out[i].actions)
                    active[i] = False
                    continue
                if on_plan[i] and plan_pos[i] < len(plan) and plan[plan_pos[i]] in hashes:
                    acts[i] = hashes.index(plan[plan_pos[i]])  # the best line's own move
                    plan_pos[i] += 1
                elif greedy:
                    on_plan[i] = False  # the real game left the best line: policy from here
                    out[i].off_plan = bool(plan)
                    acts[i] = int(np.argmax(np.array([weights.get(h, 0.0) for h in hashes]) + priors))
                else:
                    acts[i], _ = sample(hashes, priors, weights, rng)
                out[i].trace.append((hashes, priors, int(acts[i])))
                last_turn_act[i] = int(info["option_act_"][i][acts[i]])
            elif stop_windows and (kinds == KIND_PASS).any() and \
                    (live := live_interruptions(info, i, n, kinds, tags, id_to_code)):
                cid = lambda o: int(info["option_card_"][i][o])
                cards = [0] + [id_to_code[cid(o)] if 0 < cid(o) < len(id_to_code) else 0 for o in live]
                if tuple(sorted(cards)) in held_windows:  # already judged "hold" this turn: pass inline
                    acts[i] = int(np.flatnonzero(kinds == KIND_PASS)[0])
                    last_actor[i] = int(info["to_play"][i])
                    out[i].actions.append(int(acts[i]))
                    continue
                out[i].window_at = len(out[i].actions)
                out[i].window_options = [int(np.flatnonzero(kinds == KIND_PASS)[0])] + live
                out[i].window_cards = cards
                active[i] = False
                continue
            elif resp_weights is not None and int(info["msg"][i]) == CHAIN and \
                    (kinds == KIND_PASS).any() and (kinds != KIND_PASS).any():
                # Response window: the responder's learned policy, starting from the heuristic's
                # preference (respond with tagged interruptions after activations/summons).
                hashes = info["option_hash_"][i][:n].tolist()
                pref = respond(info, i, n, kinds, tags, id_to_code, last_turn_act[i])
                priors = np.where(np.arange(n) == pref, 1.0, 0.0)
                if greedy:
                    acts[i] = int(np.argmax(np.array([resp_weights.get(h, 0.0) for h in hashes]) + priors))
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
            st = probing[i]  # (before the history check: probe moves aren't part of the line)
            if st is not None:
                if term[j] or trunc[j] or st["finished"] or int(step["turn"][j]) > turn + 1:
                    active[i] = False
                    f = dict(st["features"])
                    f["own_tagged"] = live_value(st["board"], st["hand"], st["offered"], tags, id_to_code)
                    out[i].score = score_features(f)
                continue
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
                opp = 1 - player
                if PROBE_EVAL and not greedy and int(info["board_"][i][opp][2]) >= 2:
                    start_probe(probing, i, info, player, tags, id_to_code)
                else:
                    active[i] = False
                    out[i].score = evaluate(info, i, player, tags, id_to_code)
    return out


MAX_REPLANS = 4
OPENING_BOOST = 3    # search budget multiplier for turns 1-2
MAX_WINDOWS = 10     # hand-trap timing comparisons per real turn
WINDOW_LOG = []      # every timing comparison of the real game (inspection; play_game --verbose prints them)
REPLAN_LOG = []      # every re-plan of the real game
WINDOW_OPTIONS = 3   # pass + the best tagged interruptions


def live_interruptions(info, i, n, kinds, tags, id_to_code) -> list[int]:
    """Options of the non-turn player that use a tagged interruption (hand trap, set or face-up
    quick effect), best first; empty if none."""
    def value(o):
        cid = int(info["option_card_"][i][o])
        code = id_to_code[cid] if 0 < cid < len(id_to_code) else 0
        t = tags.get(code, {})
        return max(t.get("field", 0.0), t.get("set", 0.0), t.get("hand", 0.0))
    acting = [o for o in range(n) if kinds[o] == KIND_ACTION and value(o) > 0]
    return sorted(acting, key=lambda o: -value(o))[:WINDOW_OPTIONS - 1]


def choose_window(envs, k, prefix, options, player, turn, weights, resp_weights, tags, id_to_code, rng) -> int:
    """Hand-trap timing for the non-turn player: play the rest of the turn out after each option
    (k envs split across options; both sides by their learned policies, with exploration) and take
    the option after which the turn player's best continuation is worst (minimax: the turn player
    re-optimizes around the interruption; means mostly measured exploration noise). Pass is
    options[0] and wins ties."""
    first = [options[i % len(options)] for i in range(k)]
    batch = turn_batch(envs, k, prefix, player, turn, weights, tags, id_to_code, rng, resp_weights,
                       first_actions=first, belief=BELIEF, decider=1 - player)
    totals = defaultdict(list)
    for i, r in enumerate(batch):
        totals[first[i]].append(r.score)
    mean = {o: float(np.max(v)) for o, v in totals.items()}  # the turn player's best response
    choice = min(options, key=lambda o: (mean.get(o, float("inf")), o != options[0]))
    WINDOW_LOG.append({"turn": turn, "len": len(prefix), "options": options, "mean": mean, "choice": choice})
    return choice


def play_turn(envs, k, history, player, turn, gens, alpha, tags, id_to_code, rng) -> TurnRollout:
    """The real turn: search, then both players play their learned policies greedily, decision by
    decision. When play reaches a choice the search never visited (the real responses differed from
    every rollout), re-plan from that exact point with a smaller search and merge what it learns. At
    each window where the non-turn player could interrupt, it compares using each live interruption
    now against holding (choose_window), the hand-trap timing THEORY §2 is about."""
    weights, resp_weights, plan = search_turn(envs, k, history, player, turn, gens, alpha, tags, id_to_code, rng)
    prefix, replans, windows, held = list(history), 0, 0, set()
    done_moves = 0  # turn-player moves of the plan already played (plans restart after a re-plan)
    while True:
        if len(prefix) - len(history) > MAX_TURN_STEPS:  # runaway turn: finish it without more stops
            return turn_batch(envs, k, prefix, player, turn, weights, tags, id_to_code, rng, resp_weights,
                              greedy=True)[0]
        r = turn_batch(envs, k, prefix, player, turn, weights, tags, id_to_code, rng, resp_weights, greedy=True,
                       stop_unseen=replans < MAX_REPLANS, stop_windows=windows < MAX_WINDOWS,
                       held_windows=frozenset(held), plan=plan[done_moves:])[0]
        if r.window_at is None and r.unseen_at is None and windows >= MAX_WINDOWS:
            REPLAN_LOG.append({"turn": turn, "window_budget_exhausted": True})
        if r.unseen_at is not None:  # a choice the search never visited: re-plan from here
            replans += 1
            REPLAN_LOG.append({"turn": turn, "len": len(r.actions)})
            w2, r2, plan = search_turn(envs, k, r.actions, player, turn, max(3, gens // 2), alpha, tags,
                                       id_to_code, rng)
            weights.update(w2)
            resp_weights.update(r2)
            prefix, done_moves = r.actions, 0
        elif r.window_at is not None:  # the opponent can interrupt here: use now or hold?
            done_moves += len(r.trace)  # the turn player's moves played before this stop
            if r.off_plan:
                plan = ()
            key = tuple(sorted(r.window_cards))
            windows += 1
            choice = choose_window(envs, k, r.actions, r.window_options, player, turn, weights, resp_weights,
                                   tags, id_to_code, rng)
            WINDOW_LOG[-1]["cards"] = r.window_cards
            if choice == r.window_options[0]:
                held.add(key)
            prefix = r.actions + [choice]
        else:
            return r


def current_state(envs, k, history):
    """Replay history; return (turn, turn player, decision player) at the next decision."""
    _, info = envs.reset()
    for t, a in enumerate(history):
        flag = REPLAY if t < len(history) - 1 else 0
        _, _, _, _, info = envs.step(np.full(k, a + flag, dtype=np.int32))
    return int(info["turn"][0]), int(info["turn_player"][0]), info


# Hidden-information belief (belief.py) used by every search; None = clairvoyant search (pilot v2).
BELIEF = None


def play_game(envs, k, game_seed, max_turns, gens, alpha, tags, id_to_code, names=None, log=None) -> dict:
    global BELIEF
    if BELIEF is None and HIDDEN_INFO:
        from belief import Belief
        BELIEF = Belief()
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
        # Turns 1-2 (the going-first combo and the going-second break) are the long combo turns:
        # Elfnote reached a real end board only at 3x search; 9x found the same board.
        budget = gens * OPENING_BOOST if turn <= 2 else gens
        best = play_turn(envs, k, history, tp, turn, budget, alpha, tags, id_to_code, rng)
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
    ap.add_argument("--max-turns", type=int, default=12)  # 8 cut off 3 of 6 audit games once interruptions were used
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
        result_log.write(json.dumps({"config": CONFIG, "gens": args.generations, "rollouts": args.rollouts,
                                     "first": args.first, "second": args.second, "game": g, "seed": args.seed,
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
