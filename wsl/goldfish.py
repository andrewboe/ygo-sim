"""Goldfish: how strong a turn-1 board does a deck make, against a passive opponent?

For each opening hand, every env replays the same duel (deterministic seed). Turn 1 is searched with
NRPA (Nested Rollout Policy Adaptation): batches of rollouts sample choices from a softmax policy over
option identities (card + action, from the env's option hashes); after each batch the policy shifts
toward the best line found so far. The opponent declines everything.

A board is scored in "interruptions" (card_tags.py): tagged cards on the field (face-up/set) plus
hand traps kept in hand, with small tiebreaks for cards in hand and on the field.

Run from ~/ygo/run:  python goldfish.py DECK [--hands N] [--rollouts K] [--generations G]
                     python goldfish.py DECK --check     (determinism check)
"""
import argparse
import glob
import os
import sqlite3
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np

sys.path.insert(0, os.path.expanduser("~/ygo/ygo-agent/ygoenv"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ygoenv  # noqa: E402
from ygoenv.edopro import init_module  # noqa: E402
from ygoenv.edopro.edopro_ygoenv import set_opening  # noqa: E402
from card_tags import all_tags  # noqa: E402

RUN = os.path.expanduser("~/ygo/run")
MAX_OPTIONS = 24
KIND_ACTION, KIND_PASS, KIND_END, KIND_PHASE = 0, 1, 2, 3
PRIOR = {KIND_ACTION: 0.0, KIND_PASS: -1.0, KIND_END: -3.0, KIND_PHASE: -3.0}  # logit offsets
MAX_STEPS = 300  # per rollout; turn-1 combos are far shorter
INFO_KEYS = ("num_options", "option_kinds_", "option_hash_", "option_card_", "option_act_", "to_play", "turn", "msg",
             "board_", "field_codes_", "hand_codes_")


@dataclass
class Window:
    """A point where P2 could interrupt (THEORY §2): a P2 decision with a non-pass option."""
    step: int        # index into Rollout.actions
    msg: int         # decision type (16 = chain)
    options: list    # (option index, card id, kind) for each non-pass option
    p1_card: int     # card id of P1's most recent choice, i.e. what P2 would be responding to
    p1_decisions: int = 0  # P1 decisions so far; windows with the same count are the same game state


@dataclass
class Rollout:
    trace: list = field(default_factory=list)    # (option hashes, priors, chosen) per searched P1 decision
    actions: list = field(default_factory=list)  # every action taken, both players, for exact replay
    windows: list = field(default_factory=list)  # Window, for P2 decisions where it passed
    score: float = float("-inf")
    board: list = field(default_factory=list)  # field codes, negative = face-down
    hand: list = field(default_factory=list)
    turn1_len: int = 0  # actions[:turn1_len] is the turn-1 line; the rest is the probe turn
    live: list = field(default_factory=list)  # passcodes of P1 field cards that answered the probe


def score_board(field_codes, hand_codes, tags) -> float:
    """Interruptions on board + hand traps in hand, with tiebreaks for resources."""
    total, n_field = 0.0, 0
    for c in field_codes:
        if c:
            n_field += 1
            t = tags.get(abs(int(c)))
            if t:
                total += t["set"] if c < 0 else t["field"]
    hand = [int(c) for c in hand_codes if c]
    total += sum(tags.get(c, {}).get("hand", 0.0) for c in hand)
    return total + 0.1 * len(hand) + 0.02 * n_field


def sample(hashes, priors, weights, rng) -> tuple[int, np.ndarray]:
    logits = np.array([weights[h] for h in hashes]) + priors
    p = np.exp(logits - logits.max())
    p /= p.sum()
    return int(rng.choice(len(p), p=p)), p


@dataclass
class Probe:
    """Opponent's scripted turn 2 that reveals which of P1's interruptions are still live (THEORY §3):
    normal summon the vanilla filler, then activate the probe spell, then end the turn. Every
    response the engine offers P1 right after those actions is a live interruption."""
    filler_id: int  # code-list ids
    spell_id: int
    id_to_code: list  # code-list id -> passcode


IDLE = 11
CHAIN = 16


def probe_decision(info, i, n, kinds, state) -> int:
    """One decision during the probe turn. `state` holds per-env probe progress."""
    acts_ = info["option_act_"][i][:n]
    cards = info["option_card_"][i][:n]
    passes = np.flatnonzero(kinds == KIND_PASS)
    if int(info["to_play"][i]) == 1:
        if int(info["msg"][i]) == IDLE:
            state["armed"] = False
            for step_name, act, card in (("summoned", ord("s"), state["probe"].filler_id),
                                         ("activated", ord("v"), state["probe"].spell_id)):
                if not state[step_name]:
                    hit = np.flatnonzero((acts_ == act) & (cards == card))
                    state[step_name] = True
                    if len(hit):
                        state["armed"] = True
                        return int(hit[0])
            state["finished"] = True
            ends = np.flatnonzero(kinds == KIND_END)
            phases = np.flatnonzero(kinds == KIND_PHASE)
            return int(ends[0]) if len(ends) else int(phases[0]) if len(phases) else 0
        return int(passes[0]) if len(passes) else 0
    # P1: note every live response to the probe actions, but don't use them.
    if int(info["msg"][i]) == CHAIN and state["armed"]:
        state["offered"].update(int(c) for o, c in enumerate(cards) if kinds[o] != KIND_PASS and c)
    return int(passes[0]) if len(passes) else 0


def score_probed(board, hand, offered_ids, probe: Probe, tags) -> float:
    """Live interruptions (offered during the probe, weighted by tag value, at least 0.5) for field
    cards, plus hand traps kept in hand, with tiebreaks. Effects used up on turn 1 aren't offered."""
    hand = [int(c) for c in hand if c]
    on_field = {abs(int(c)): int(c) < 0 for c in board if c}
    total = 0.0
    for cid in offered_ids:
        code = probe.id_to_code[cid] if cid < len(probe.id_to_code) else 0
        # A copy in hand answered (e.g. Ash), not the field copy: hand traps are scored below.
        if code in on_field and code not in hand:
            t = tags.get(code, {})
            total += max(0.5, t.get("set" if on_field[code] else "field", 0.0))
    total += sum(tags.get(c, {}).get("hand", 0.0) for c in hand)
    return total + 0.1 * len(hand) + 0.02 * len(on_field)


@dataclass(frozen=True)
class P2Rule:
    """A live interruption policy for P2: use `trap` at the first window right after P1 uses `trigger`
    (any window if trigger is 0); answer an immediate follow-up (e.g. a target) with its first option."""
    trap: int     # code-list card id of the hand trap
    trigger: int  # code-list card id of the P1 card to respond to; 0 = first legal window


def rollout_batch(envs, k, weights, tags, rng, prefix=(), p2_plan=(), probe: Probe | None = None,
                  p2_rule: P2Rule | None = None, greedy: bool = False) -> list[Rollout]:
    """K rollouts of turn 1 of the current opening.

    The first len(prefix) actions are forced (both players), for exact replay to a window. After
    that, P2's next decisions follow p2_plan in order (e.g. [activate Ash] or [activate Imperm,
    target]), then P2 passes. P1 samples from the softmax policy throughout, after the prefix.
    With `probe`, the opponent's turn 2 probes P1's end board and scores live interruptions only;
    without it, the turn-1 board is scored from card tags.
    """
    _, info = envs.reset()
    info = {key: info[key].copy() for key in INFO_KEYS}
    out = [Rollout() for _ in range(k)]
    active = np.ones(k, dtype=bool)
    plan_pos = np.zeros(k, dtype=int)
    last_p1_card = np.zeros(k, dtype=int)
    p1_decisions = np.zeros(k, dtype=int)
    rule_state = np.zeros(k, dtype=int)  # 0 = rule not used yet, 1 = just used, 2 = done
    probing = [None] * k  # per-env probe state once turn 2 starts
    for _ in range(MAX_STEPS):
        if not active.any():
            break
        # Step every env: envpool's sync mode can deadlock waiting for a full batch when only a
        # subset is stepped. Finished envs get a filler action and their results are ignored.
        acts = np.zeros(k, dtype=np.int32)
        for i in np.flatnonzero(active):
            n = int(info["num_options"][i])
            kinds = info["option_kinds_"][i][:n]
            t = len(out[i].actions)
            if probing[i] is not None:
                acts[i] = probe_decision(info, i, n, kinds, probing[i])
                out[i].actions.append(int(acts[i]))
                continue
            if t < len(prefix):
                acts[i] = prefix[t]
            elif int(info["to_play"][i]) == 1:
                passes = np.flatnonzero(kinds == KIND_PASS)
                acting = [(o, int(info["option_card_"][i][o]), int(kinds[o]))
                          for o in range(n) if kinds[o] != KIND_PASS]
                rule_hit = None
                if p2_rule is not None and rule_state[i] == 0 and \
                        (p2_rule.trigger == 0 or last_p1_card[i] == p2_rule.trigger):
                    rule_hit = next((o for o, c, _ in acting if c == p2_rule.trap), None)
                if plan_pos[i] < len(p2_plan):
                    acts[i] = p2_plan[plan_pos[i]]
                    plan_pos[i] += 1
                elif rule_hit is not None:
                    acts[i] = rule_hit
                    rule_state[i] = 1  # next P2 decision may be the follow-up (e.g. a target)
                elif rule_state[i] == 1 and int(info["msg"][i]) != CHAIN and acting:
                    acts[i] = acting[0][0]
                    rule_state[i] = 2
                else:  # passive opponent: decline when possible, and log the window if it could act
                    if rule_state[i] == 1:
                        rule_state[i] = 2
                    acts[i] = passes[0] if len(passes) else 0
                    if acting and len(passes):
                        out[i].windows.append(Window(t, int(info["msg"][i]), acting, int(last_p1_card[i]),
                                                     int(p1_decisions[i])))
            else:
                hashes = info["option_hash_"][i][:n].tolist()
                priors = np.array([PRIOR[int(x)] for x in kinds])
                if greedy:  # the strategy's own line: most likely choice everywhere
                    acts[i] = int(np.argmax(np.array([weights[h] for h in hashes]) + priors))
                else:
                    acts[i], _ = sample(hashes, priors, weights, rng)
                out[i].trace.append((hashes, priors, int(acts[i])))
            if int(info["to_play"][i]) == 0:
                p1_decisions[i] += 1
                if info["option_card_"][i][acts[i]]:
                    last_p1_card[i] = int(info["option_card_"][i][acts[i]])
            out[i].actions.append(int(acts[i]))
        _, _, term, trunc, step = envs.step(acts)
        for j, i in enumerate(step["env_id"]):
            if not active[i]:
                continue
            for key in INFO_KEYS:
                info[key][i] = step[key][j]
            ended = term[j] or trunc[j]
            if probing[i] is None and (ended or step["turn"][j] >= 2):
                # End of turn 1: snapshot P1's board and hand.
                out[i].turn1_len = len(out[i].actions)
                out[i].board = step["field_codes_"][j][0].tolist()
                out[i].hand = step["hand_codes_"][j][0].tolist()
                if probe is None or ended:
                    active[i] = False
                    out[i].score = score_board(out[i].board, out[i].hand, tags)
                else:
                    probing[i] = {"probe": probe, "summoned": False, "activated": False,
                                  "armed": False, "finished": False, "offered": set()}
            elif probing[i] is not None and (ended or probing[i]["finished"] or step["turn"][j] >= 3):
                active[i] = False
                out[i].score = score_probed(out[i].board, out[i].hand, probing[i]["offered"], probe, tags)
                on_field = {abs(int(c)) for c in out[i].board if c} - {int(c) for c in out[i].hand if c}
                out[i].live = sorted({probe.id_to_code[c] for c in probing[i]["offered"]
                                      if c < len(probe.id_to_code)} & on_field)
    return out


def adapt(weights, best: Rollout, alpha: float) -> None:
    """NRPA: move the policy toward the best line's choices."""
    old = dict(weights)
    for hashes, priors, chosen in best.trace:
        logits = np.array([old.get(h, 0.0) for h in hashes]) + priors
        p = np.exp(logits - logits.max())
        p /= p.sum()
        for h, ph in zip(hashes, p):
            weights[h] -= alpha * ph
        weights[hashes[chosen]] += alpha


def search_opening(envs, k, opening, generations, alpha, tags, rng, prefix=(), p2_plan=(),
                   rng_salt=0, probe: Probe | None = None, p2_rule: P2Rule | None = None,
                   weights_out: dict | None = None) -> tuple[Rollout, float]:
    """Best turn-1 line for one opening (optionally continuing after a forced prefix and P2 plan, or
    against a live P2 rule); also returns the first (untrained) batch's best score."""
    set_opening(opening)
    rng = np.random.default_rng([opening, rng_salt])  # per-opening stream: any hand reproduces alone
    weights = defaultdict(float)
    best, first = Rollout(), None
    for _ in range(generations):
        batch = rollout_batch(envs, k, weights, tags, rng, prefix, p2_plan, probe, p2_rule)
        top = max(batch, key=lambda r: r.score)
        first = top.score if first is None else first
        if top.score > best.score:
            best = top
        adapt(weights, best, alpha)
    if weights_out is not None:
        weights_out.update(weights)
    return best, first


def make_pool(deck: str, k: int, base_seed: int, opponent: str | None = None):
    """K lockstep envs. `opponent` is a stacked P2 deck (e.g. '_p2__ash'), dealt in file order."""
    return ygoenv.make(task_id="EDOPro-v0", env_type="gymnasium", num_envs=k, num_threads=k,
                       seed=0, deck1=deck, deck2=opponent or deck, player=-1, max_options=MAX_OPTIONS,
                       n_history_actions=16, play_mode="self", lite=True, duel_seed=base_seed,
                       shuffle2=opponent is None)


def make_probe(names: dict) -> Probe:
    """Probe using the filler and spell stacked into every _p2__ deck (setup_runtime.py)."""
    codes = [int(l) for l in open(f"{RUN}/code_list.txt") if l.strip()]
    by_name = {}
    for code in codes:
        by_name.setdefault(names.get(code), code)
    index = {c: i + 1 for i, c in enumerate(codes)}  # code-list ids are 1-based lines
    id_to_code = [0] + codes
    return Probe(index[by_name["Mystical Elf"]], index[by_name["Upstart Goblin"]], id_to_code)


def load(deck=None):
    os.chdir(RUN)
    decks = {os.path.basename(p)[:-4]: p for p in glob.glob(f"{RUN}/decks/*.ydk")}
    if deck is not None and deck not in decks:
        sys.exit(f"unknown deck {deck}; have: {sorted(d for d in decks if not d.startswith('_'))}")
    init_module(f"{RUN}/cards.cdb", f"{RUN}/code_list.txt", decks)
    return dict(sqlite3.connect(f"{RUN}/cards.cdb").execute("select id, name from texts"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("deck")
    ap.add_argument("--hands", type=int, default=20)
    ap.add_argument("--rollouts", type=int, default=32)
    ap.add_argument("--generations", type=int, default=15)
    ap.add_argument("--alpha", type=float, default=1.0)
    ap.add_argument("--seed", type=int, default=1000, help="duel seed base; opening n uses seed + n")
    ap.add_argument("--first", type=int, default=0, help="index of the first opening")
    ap.add_argument("--no-probe", action="store_true",
                    help="score turn-1 boards from card tags instead of probing live interruptions")
    args = ap.parse_args()

    names = load(args.deck)
    tags = all_tags()
    rng = np.random.default_rng(0)
    probe = None if args.no_probe else make_probe(names)
    envs = make_pool(args.deck, args.rollouts, args.seed, opponent=None if args.no_probe else "_p2__none")
    # Every searched line is training data for the pilot (wsl/dataset.py reads this format).
    import json
    opponent = None if args.no_probe else "none"
    os.makedirs("/mnt/c/Users/andre/Desktop/ygo-sim/data/search", exist_ok=True)
    log = open(f"/mnt/c/Users/andre/Desktop/ygo-sim/data/search/{args.deck}__goldfish.jsonl", "a") \
        if opponent else None
    t0, scores, firsts = time.time(), [], []
    for h in range(args.first, args.first + args.hands):
        best, first = search_opening(envs, args.rollouts, h, args.generations, args.alpha, tags, rng,
                                     probe=probe)
        scores.append(best.score)
        firsts.append(first)
        if log:
            log.write(json.dumps({"deck": args.deck, "opponent": opponent, "seed": args.seed, "hand": h,
                                  "actions": best.actions[:best.turn1_len], "line": best.score,
                                  "trials": []}) + "\n")
            log.flush()
        board = [("(set) " if c < 0 else "") + names.get(abs(c), str(c)) for c in best.board if c]
        held = [names.get(c, str(c)) for c in best.hand if c and tags.get(c, {}).get("hand")]
        live = f" | live: {[names.get(c, str(c)) for c in best.live]}" if probe else ""
        print(f"hand {h:3}: {best.score:5.2f} (random: {first:5.2f}) in {len(best.trace):3} decisions | "
              f"board: {board} | hand traps held: {held}{live}", flush=True)
    dt = time.time() - t0
    s = np.array(scores)
    print(f"\n{args.deck}: {args.hands} openings, {args.rollouts}x{args.generations} rollouts each, {dt:.0f}s")
    print(f"  mean interruptions {s.mean():.2f} (random-policy best: {np.mean(firsts):.2f})")
    for t in (1, 2, 3, 4):
        print(f"  P(>= {t}) = {(s >= t).mean():.0%}")


def check_determinism(deck: str, k: int = 4):
    """Same opening + same actions must give the same board."""
    load(deck)
    set_opening(7)
    rng = np.random.default_rng(1)
    envs = make_pool(deck, k, 0)
    _, info = envs.reset()
    for _ in range(60):
        a = int(rng.integers(int(info["num_options"][0])))
        _, _, term, _, info = envs.step(np.full(k, a, dtype=np.int32))
        if term[0]:
            break
    same = all((info["field_codes_"][i] == info["field_codes_"][0]).all() and
               (info["hand_codes_"][i] == info["hand_codes_"][0]).all() for i in range(k))
    print(f"determinism ({k} envs, same opening and actions): {'OK' if same else 'MISMATCH'}")


if __name__ == "__main__":
    if "--check" in sys.argv:
        check_determinism(sys.argv[1])
    else:
        main()
