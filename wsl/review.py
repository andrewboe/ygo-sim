"""Game review: replay logged games turn by turn and flag likely misplays.

Replays a game from data/games/results.jsonl exactly (same deal, same action history) and writes a
readable log: both hands at the start of each turn (the reviewer sees everything), every decision
with the card it used, chains and hand-trap responses, LP changes, and end-of-turn boards. Then runs
heuristic checks:
  - missed lethal: the opponent had no monsters and our face-up monsters' base ATK covered their LP,
    but the game went on (base ATK only: boosts and attack restrictions are not modeled)
  - passive interruption: the non-turn player passed live windows while holding a tagged interruption
  - idle turn: the turn player took no actions despite holding cards
  - early end: the turn player ended a main phase with summons or activations still available
Flags are prompts for a human look, not verdicts.

Run in WSL:  python review.py --sample 12      (stage 2 games: finalists, upsets, OTKs, turn caps)
             python review.py --game FIRST SECOND GAME
Output: data/review/<first>__<second>__<game>.txt and data/review/summary.jsonl
"""
import argparse
import json
import os
import random
import sqlite3
import sys

import numpy as np

sys.path.insert(0, os.path.expanduser("~/ygo/ygo-agent/ygoenv"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ygoenv  # noqa: E402
from card_tags import all_tags  # noqa: E402
from goldfish import KIND_ACTION, KIND_END, KIND_PASS, KIND_PHASE, MAX_OPTIONS, RUN, load, set_opening  # noqa: E402

DATA = "/mnt/c/Users/andre/Desktop/ygo-sim/data"
OUT = f"{DATA}/review"
MSG = {10: "battle", 11: "main", 12: "effect yes/no", 13: "yes/no", 14: "option", 15: "select card", 16: "chain",
       18: "zone", 19: "position", 20: "tribute", 22: "counter", 23: "select sum", 24: "zone", 25: "sort",
       26: "select card", 140: "declare type", 141: "declare attribute", 142: "declare card", 143: "declare number"}
ACT = {"s": "normal summons", "c": "special summons", "r": "repositions", "m": "sets monster", "t": "sets",
       "v": "activates", "a": "attacks with", "b": "to battle phase", "e": "ends phase", "n": "passes"}
TYPE_MONSTER = 0x1


def card_db():
    db = sqlite3.connect(f"{RUN}/cards.cdb")
    return {i: (t, a) for i, t, a in db.execute("select id, type, atk from datas")}


def replay(rec, names, tags, id_to_code, db):
    """Step through rec['history']; return (log lines, flags)."""
    envs = ygoenv.make(task_id="EDOPro-v0", env_type="gymnasium", num_envs=1, num_threads=1, seed=0,
                       deck1=rec["first"], deck2=rec["second"], player=-1, max_options=MAX_OPTIONS,
                       n_history_actions=16, play_mode="self", lite=True, duel_seed=rec["seed"])
    set_opening(rec["game"])
    _, info = envs.reset()
    nm = lambda code: names.get(abs(int(code)), str(code))
    code_of = lambda cid: id_to_code[cid] if 0 < cid < len(id_to_code) else 0
    deck = {0: rec["first"].removeprefix("cand__"), 1: rec["second"].removeprefix("cand__")}
    lines = [f"{deck[0]} (P0, first) vs {deck[1]} (P1, second) | game {rec['game']} seed {rec['seed']} | "
             f"result: {'draw' if rec['winner'] == -1 else 'P%d wins' % rec['winner']} by {rec['by']}, "
             f"turn {rec['turns']}", ""]
    flags = []
    turn, actions_this_turn, passive = None, 0, {}
    lethal_checked, lethal_watch = None, None
    lp = [8000, 8000]
    for t, a in enumerate(rec["history"]):
        cur_turn, tp, me = int(info["turn"][0]), int(info["turn_player"][0]), int(info["to_play"][0])
        if cur_turn != turn:
            if turn is not None:
                end_of_turn(lines, flags, info, turn, prev_tp, actions_this_turn, passive, nm, tags, db, lp)
                if lethal_watch and lethal_watch[0] == turn and lp[1 - lethal_watch[1]] > 0:
                    flags.append({"turn": turn, "player": lethal_watch[1], "check": "missed lethal",
                                  "detail": f"entered battle with base ATK {lethal_watch[2]} vs "
                                            f"{lethal_watch[3]} LP and no opposing monsters"})
            turn, prev_tp, actions_this_turn, passive = cur_turn, tp, 0, {}
            hands = [[nm(c) for c in info["hand_codes_"][0][p] if c] for p in (0, 1)]
            lines.append(f"=== Turn {turn}: P{tp} ({deck[tp]}) | LP {lp[0]} / {lp[1]}")
            lines.append(f"    P{tp} hand: {', '.join(hands[tp]) or '-'}")
            lines.append(f"    P{1 - tp} hand: {', '.join(hands[1 - tp]) or '-'}")
        n = int(info["num_options"][0])
        kinds = info["option_kinds_"][0][:n]
        acts = info["option_act_"][0][:n]
        cards = info["option_card_"][0][:n]
        msg = int(info["msg"][0])
        a = int(a)
        kind = int(kinds[a]) if a < n else KIND_PASS
        letter = chr(int(acts[a])) if a < n and acts[a] else ""
        card = nm(code_of(int(cards[a]))) if a < n and cards[a] else ""
        if me == tp and kind == KIND_ACTION:
            actions_this_turn += 1
        if msg == 11 and kind == KIND_ACTION and letter in ("m", "s") and                 tags.get(code_of(int(cards[a])), {}).get("hand", 0) > 0 and                 db.get(code_of(int(cards[a])), (0, 0))[0] & TYPE_MONSTER:  # setting a hand-trap trap is normal
            flags.append({"turn": cur_turn, "player": me, "check": "hand trap played as a monster", "detail": card})
        if msg == 10 and me == tp and lethal_checked != cur_turn:  # first battle decision of the turn
            lethal_checked = cur_turn
            opp = 1 - tp
            opp_monsters = [c for c in info["field_codes_"][0][opp] if c and db.get(abs(int(c)), (0, 0))[0] & TYPE_MONSTER]
            atk = sum(max(db.get(int(c), (0, 0))[1], 0) for c in info["field_codes_"][0][tp]
                      if c > 0 and db.get(int(c), (0, 0))[0] & TYPE_MONSTER)
            if not opp_monsters and atk >= lp[opp]:
                lethal_watch = (cur_turn, tp, atk, lp[opp])
        if me != tp and msg == 16:  # the non-turn player's chain window
            live = [nm(code_of(int(cards[o]))) for o in range(n)
                    if kinds[o] != KIND_PASS and tags.get(code_of(int(cards[o])), {})]
            if live and kind == KIND_PASS:
                for c in live:
                    passive[c] = passive.get(c, 0) + 1
        if msg == 11 and me == tp and kind == KIND_END:
            left = sorted({chr(int(acts[o])) for o in range(n) if kinds[o] == KIND_ACTION and chr(int(acts[o])) in "scv"})
            if left:
                avail = [f"{ACT.get(chr(int(acts[o])), chr(int(acts[o])))} {nm(code_of(int(cards[o])))}"
                         for o in range(n) if kinds[o] == KIND_ACTION and chr(int(acts[o])) in "scv"][:4]
                lines.append(f"      (ended main phase with options left: {'; '.join(avail)})")
                if turn > 1 or actions_this_turn == 0:
                    flags.append({"turn": turn, "player": tp, "check": "early end", "detail": avail})
        if kind != KIND_PASS or msg not in (16, 12, 13):
            who = f"P{me}"
            what = ACT.get(letter, letter) if msg in (10, 11) else MSG.get(msg, f"msg {msg}")
            if kind == KIND_PASS:
                what = "passes"
            elif kind == KIND_END:
                what = "ends phase"
            lines.append(f"    {who:3} {what}{(' ' + card) if card else ''}"
                         f"{'  [response]' if me != tp and kind == KIND_ACTION else ''}")
        _, _, term, trunc, info = envs.step(np.array([a], dtype=np.int32))
        new_lp = [int(x) for x in info["lp_"][0]]
        if new_lp != lp:
            lines.append(f"        LP {lp[0]}/{lp[1]} -> {new_lp[0]}/{new_lp[1]}")
            lp = new_lp
        if term[0] or trunc[0]:
            lines.append(f"=== Game over: LP {lp[0]} / {lp[1]}")
            break
    else:
        end_of_turn(lines, flags, info, turn, prev_tp, actions_this_turn, passive, nm, tags, db, lp)
    return lines, flags


def end_of_turn(lines, flags, info, turn, tp, n_actions, passive, nm, tags, db, lp):
    fields = [[("(set) " if c < 0 else "") + nm(c) for c in info["field_codes_"][0][p] if c] for p in (0, 1)]
    lines.append(f"    end of turn {turn}: P0 field [{', '.join(fields[0])}] | P1 field [{', '.join(fields[1])}]")
    lines.append("")
    hand = [c for c in info["hand_codes_"][0][tp] if c]
    if n_actions == 0 and hand:
        flags.append({"turn": turn, "player": tp, "check": "idle turn", "detail": f"{len(hand)} cards in hand"})
    for c, k in passive.items():
        flags.append({"turn": turn, "player": 1 - tp, "check": "passive interruption",
                      "detail": f"passed {k} live window(s) holding {c}"})


def sample_games(n: int) -> list[dict]:
    """Stage 2 games: half involving finalists, plus upsets, fast wins and turn caps."""
    results = [json.loads(l) for l in open(f"{DATA}/games/results.jsonl")]
    games = [r for r in results if r["game"] >= 10_000 and r.get("history")]
    fin = set(json.load(open(f"{DATA}/screen/stage2_finalists.json"))["finalists"])
    rng = random.Random(0)
    pick = lambda pool, k: rng.sample(pool, min(k, len(pool)))
    finalist_games = [r for r in games if r["first"] in fin or r["second"] in fin]
    losses = [r for r in finalist_games if r["winner"] != -1
              and ((r["first"] in fin and r["winner"] == 1) or (r["second"] in fin and r["winner"] == 0))]
    fast = [r for r in games if r["by"] == "game" and r["turns"] <= 2]
    capped = [r for r in games if r["by"] == "turn cap"]
    chosen = pick(finalist_games, n // 2) + pick(losses, n // 6 or 1) + pick(fast, n // 6 or 1) + pick(capped, n // 6 or 1)
    uniq = {(r["first"], r["second"], r["game"]): r for r in chosen}
    return list(uniq.values())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=0)
    ap.add_argument("--game", nargs=3, metavar=("FIRST", "SECOND", "GAME"))
    ap.add_argument("--list", action="store_true", help="print the sample (one game per line) and exit")
    args = ap.parse_args()
    if args.list:  # env pools can't be torn down safely: review_sample.sh runs one process per game
        for r in sample_games(args.sample or 12):
            print(r["first"], r["second"], r["game"])
        return
    if args.game:
        f, s, g = args.game
        recs = [r for r in (json.loads(l) for l in open(f"{DATA}/games/results.jsonl"))
                if r["first"] == f and r["second"] == s and r["game"] == int(g)][-1:]
    else:
        recs = sample_games(args.sample or 12)
    tags = all_tags()
    id_to_code = [0] + [int(l) for l in open(os.path.expanduser("~/ygo/run/code_list.txt")) if l.strip()]
    os.makedirs(OUT, exist_ok=True)
    summary = []
    for rec in recs:
        names = load(rec["first"])
        load(rec["second"])
        db = card_db()
        lines, flags = replay(rec, names, tags, id_to_code, db)
        name = f"{rec['first']}__{rec['second']}__{rec['game']}"
        open(f"{OUT}/{name}.txt", "w").write("\n".join(lines) + "\n\nFLAGS:\n" +
                                             "\n".join(f"  turn {x['turn']} P{x['player']}: {x['check']}: {x['detail']}"
                                                       for x in flags) + "\n")
        summary.append({"game": name, "winner": rec["winner"], "by": rec["by"], "turns": rec["turns"], "flags": flags})
        print(f"{name}: {rec['by']} turn {rec['turns']}, {len(flags)} flags", flush=True)
    with open(f"{OUT}/summary.jsonl", "a") as f:
        for row in summary:
            f.write(json.dumps(row) + "\n")


if __name__ == "__main__":
    main()
