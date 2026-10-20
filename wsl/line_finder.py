"""Line finder: the turn-1 lines a starting hand makes, going first against a passive opponent.

The deck is stacked so the hand is exactly the requested cards (engine config shuffle1=False: the last Main Deck
lines of the .ydk are drawn first). Turn 1 is searched with goldfish's NRPA several times from independent
starts; each search's best line is replayed and written out step by step, with the end board, the hand left and
the live interruptions (goldfish's probe: a scripted opponent turn shows which of the board's effects can
still respond). Optional executor priors (a windbot_decks executor) steer the search like in game.py.

Run from ~/ygo/run:  python line_finder.py REQUEST.json OUT.json
REQUEST: {"main": [passcodes], "extra": [passcodes], "hand": [passcodes], "rollouts": 32, "generations": 15,
          "restarts": 3, "seed": 1000, "executor": "windbot_decks.mitsurugi:MitsurugiExecutor" (optional)}
OUT: {"ok": true, "hand": [...], "lines": [{"score", "steps": [...], "board": [...], "hand_left": [...],
      "live": [...]}], "elapsed_s": ...} or {"ok": false, "error": "...", "missing": [...]}
"""
import collections
import json
import os
import sqlite3
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.expanduser("~/ygo/ygo-agent/ygoenv"))
os.environ.setdefault("YGOSIM_CONTEXT", "1")  # select prompts' candidates, for describing choices
RUN = os.path.expanduser("~/ygo/run")

IDLE_ACT = {"s": "Normal Summon", "c": "Special Summon", "m": "Set (monster)", "t": "Set", "v": "Activate",
            "r": "Change position of", "b": "Enter the Battle Phase", "e": "End the turn"}
HINT = {500: "tribute", 501: "discard", 502: "destroy", 503: "banish", 504: "send to the GY", 505: "return to hand",
        506: "add to hand", 507: "return to the Deck", 509: "Special Summon", 510: "Set", 511: "Fusion Material",
        512: "Synchro Material", 513: "Xyz Material", 527: "place on the field", 531: "tribute", 533: "Link Material",
        549: "attack target", 551: "target", 573: "negate", 574: "use"}
POSITION = {"1": "face-up Attack", "2": "face-down Attack", "3": "face-up Defense", "4": "face-down Defense"}
SYSTEM = {30: "Continue this attack (replay)", 31: "Attack directly", 1152: "Special Summon", 1190: "Add to hand",
          1192: "Banish"}
LOCATION = {0x1: "Deck", 0x2: "hand", 0x4: "field", 0x8: "field", 0x10: "GY", 0x20: "banishment", 0x40: "Extra Deck"}


def coverage(codes):
    """Cards the engine can't play: not in cards.cdb, no script, or not in code_list.txt."""
    db = sqlite3.connect(f"{RUN}/cards.cdb")
    listed = {int(l) for l in open(f"{RUN}/code_list.txt") if l.strip()}
    missing = []
    for c in sorted(set(codes)):
        row = db.execute("select name from texts where id=?", (c,)).fetchone()
        script = os.path.exists(f"{RUN}/edopro_script/c{c}.lua")
        if not row or not script or c not in listed:
            missing.append({"passcode": c, "name": row[0] if row else None, "in_cdb": bool(row), "script": script,
                            "in_code_list": c in listed})
    return missing


def card_string(db, card, desc):
    """The effect string an option / yes-no prompt refers to (EDOPro desc: code << 20 | index, code cut to its
    low 12 bits): looked up on the card that is acting."""
    if desc in SYSTEM:
        return SYSTEM[desc]
    if not card or desc <= 0:
        return None
    index, code_bits = desc & 0xFFFFF, (desc >> 20) & 0xFFF
    if code_bits and (card & 0xFFF) == code_bits and index < 16:
        row = db.execute(f"select str{index + 1} from texts where id=?", (card,)).fetchone()
        return row[0] if row and row[0] else None
    return None


def main(req_path, out_path):
    t0 = time.time()
    req = json.load(open(req_path))
    main_deck, extra, hand = [int(c) for c in req["main"]], [int(c) for c in req.get("extra", [])], \
        [int(c) for c in req["hand"]]
    out = {"ok": False}
    try:
        need = collections.Counter(hand)
        have = collections.Counter(main_deck)
        short = [c for c, k in need.items() if have[c] < k]
        if short:
            raise ValueError(f"hand cards not in the Main Deck (or more copies than it has): {short}")
        if len(hand) != 5:
            raise ValueError(f"a going-first hand has 5 cards, got {len(hand)}")
        missing = coverage(main_deck + extra)
        if missing:
            out.update(error="the engine can't play some cards (missing data, script or card index)",
                       missing=missing)
            return
        rest = list(main_deck)
        for c in hand:
            rest.remove(c)
        name = f"_lines__{os.getpid()}"
        path = f"{RUN}/decks/{name}.ydk"
        # the last Main Deck lines are drawn first: put the hand last, in reverse draw order
        with open(path, "w", newline="\n") as f:
            f.write("#main\n" + "\n".join(map(str, rest + hand[::-1])) + "\n#extra\n" +
                    "\n".join(map(str, extra)) + "\n!side\n")
        try:
            out.update(search(name, req, hand))
        finally:
            os.remove(path)
    except Exception as e:  # report, don't hang the caller
        import traceback
        out.update(error=f"{type(e).__name__}: {e}", traceback=traceback.format_exc()[-2000:])
    finally:
        out["elapsed_s"] = round(time.time() - t0, 1)
        json.dump(out, open(out_path, "w"), indent=1)


def search(deck, req, hand):
    import numpy as np
    import ygoenv

    import goldfish as gf
    from card_tags import all_tags

    names = gf.load(deck)
    tags = all_tags()
    db = sqlite3.connect(f"{RUN}/cards.cdb")
    ids = [0] + [int(l) for l in open(f"{RUN}/code_list.txt") if l.strip()]
    K, G = int(req.get("rollouts", 32)), int(req.get("generations", 15))
    restarts, seed = int(req.get("restarts", 3)), int(req.get("seed", 1000))
    envs = ygoenv.make(task_id="EDOPro-v0", env_type="gymnasium", num_envs=K, num_threads=K, seed=0, deck1=deck,
                       deck2="_p2__none", player=-1, max_options=gf.MAX_OPTIONS, n_history_actions=16,
                       play_mode="self", lite=True, duel_seed=seed, shuffle1=False, shuffle2=False)
    gf.set_opening(0)
    _, info = envs.reset()
    dealt = sorted(int(c) for c in info["hand_codes_"][0][0] if c)
    if dealt != sorted(hand):
        raise RuntimeError(f"dealt hand {[names.get(c) for c in dealt]} is not the requested one")
    if req.get("executor"):
        os.environ["YGOSIM_CARD_HANDLERS"] = "1"
        import importlib

        import card_handlers as ch
        module, cls = req["executor"].split(":")
        ch.ENABLED = True
        ch.DECK_EXECUTORS[deck] = getattr(importlib.import_module(module), cls)
        ch.set_decks(deck, "_p2__none")

        class Hook:
            def reset(self, k):
                ch.reset(k)

            def offsets(self, info, i, n):
                return ch.windbot_offsets(info, i, n, ids)

            def chosen(self, i, o):
                ch.chosen(i, 0, o)
        gf.PRIOR_HOOK = Hook()
    probe = gf.make_probe(names)
    lines, seen = [], set()
    for r in range(restarts):
        best, _ = gf.search_opening(envs, K, 0, G, 1.0, tags, None, probe=probe, rng_salt=r)
        actions = tuple(best.actions[:best.turn1_len])
        if actions in seen or not actions:
            continue
        seen.add(actions)
        lines.append(describe(envs, K, actions, best, names, ids, db))
    lines.sort(key=lambda l: (-l["score"], len(l["steps"])))
    unique, boards = [], set()
    for l in lines:  # the same end board and hand by another order of steps: keep the shortest
        key = (tuple(sorted(l["board"])), tuple(sorted(l["hand_left"])))
        if key not in boards:
            boards.add(key)
            unique.append(l)
    lines = unique
    return {"ok": True, "hand": [names.get(c, str(c)) for c in hand], "lines": lines,
            "search": {"rollouts": K, "generations": G, "restarts": restarts, "executor": req.get("executor"),
                       "scoring": "live interruptions after a probe turn (card_tags), plus hand traps held"}}


def describe(envs, k, actions, best, names, ids, db):
    """Replay a line in env 0 and write out player 0's choices."""
    import numpy as np

    import goldfish as gf
    nm = lambda c: names.get(abs(int(c)), str(c))
    card_of = lambda info, o: ids[int(info["option_card_"][0][o])] if 0 < int(info["option_card_"][0][o]) < len(ids) else 0
    gf.set_opening(0)
    _, info = envs.reset()
    steps, last_card = [], 0
    for a in actions:
        n, msg, p = int(info["num_options"][0]), int(info["msg"][0]), int(info["to_play"][0])
        if p == 0 and n > 1:
            act = chr(int(info["option_act_"][0][a]))
            card = card_of(info, a)
            kind = int(info["option_kinds_"][0][a])
            text = None
            if msg == 11:
                text = f"{IDLE_ACT.get(act, act)} {nm(card)}".strip() if card else IDLE_ACT.get(act, act)
            elif msg == 16 and kind != 1:
                text = f"Activate {nm(card)}"
            elif msg == 12:
                text = f"{'Use' if kind != 1 else 'Skip'} {nm(card)}'s effect"
            elif msg == 13:
                prompt = card_string(db, last_card, int(info["prompt_desc_"][0]))
                text = f"{'Yes' if kind != 1 else 'No'}" + (f": {prompt}" if prompt else "")
            elif msg == 14:
                opts = [int(x) for x in info["prompt_options_"][0][:n]]
                text = "Choose: " + (card_string(db, last_card, opts[a]) or f"option {a + 1} of {n}")
            elif msg in (15, 20, 23, 26):
                combo = [int(x) for x in info["option_combo_"][0][a] if x]
                rows = [info["select_cards_"][0][x - 1] for x in combo]
                where = lambda r: (" (opponent's " if int(r[1]) != 0 else " (") +                     LOCATION.get(int(r[2]) & 0x7F, "?") + ")"
                chosen = ", ".join(nm(int(r[0])) + where(r) for r in rows)
                hint = HINT.get(int(info["select_"][0][0]))
                text = (f"Select to {hint}: " if hint else "Select: ") + chosen if rows else "Finish selecting"
            elif msg == 19:
                text = f"{nm(card)} in {POSITION.get(act, act)} Position" if card else None
            if text:
                steps.append(text)
            if card and msg in (11, 12, 16):
                last_card = card
        acts = np.zeros(k, np.int32)
        acts[0] = a
        _, _, term, trunc, step = envs.step(acts)
        nxt = {key: v for key, v in step.items() if isinstance(v, np.ndarray)}
        j = list(step["env_id"]).index(0)
        info = {key: v[j:j + 1] for key, v in nxt.items()}
        if term[j] or trunc[j]:
            break
    return {"score": round(float(best.score), 2), "steps": steps,
            "board": [("(set) " if int(c) < 0 else "") + nm(c) for c in best.board if c],
            "hand_left": [nm(c) for c in best.hand if c],
            "live": [nm(c) for c in best.live]}


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
