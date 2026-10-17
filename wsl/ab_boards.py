"""Turn-1 boards in a paired executor A/B (ab_executors.sh): replays every game and, for the executor deck
going first, takes its field and hand at the start of turn 2; reports per deck and arm the mean field size, the
tagged interruptions on the field (once per name, as the search scores them) and how often each Extra Deck
monster is on it.

Run from ~/ygo/run:  python ab_boards.py OUT_DIR"""
import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.expanduser("~/ygo/ygo-agent/ygoenv"))
import numpy as np  # noqa: E402
import ygoenv  # noqa: E402

from card_tags import all_tags  # noqa: E402
from goldfish import load, set_opening  # noqa: E402
from windbot import CardType, card_data  # noqa: E402
from windbot_decks import DECKS  # noqa: E402

EXTRA = CardType.Fusion | CardType.Synchro | CardType.Xyz | CardType.Link


_ENVS = {}  # one env per (decks, seed), kept alive: destroying envpool envs mid-run segfaults


def turn1_board(first, second, game, seed, history):
    key = (first, second, seed)
    if key not in _ENVS:
        _ENVS[key] = ygoenv.make(task_id="EDOPro-v0", env_type="gymnasium", num_envs=1, num_threads=1, seed=0,
                                 deck1=first, deck2=second, player=-1, max_options=24, n_history_actions=16,
                                 play_mode="self", lite=True, duel_seed=seed, shuffle2=True)
    envs = _ENVS[key]
    set_opening(game)
    _, info = envs.reset()
    for a in history:
        if int(info["turn"][0]) >= 2:
            break
        _, _, term, trunc, info = envs.step(np.array([a], np.int32))
        if term[0] or trunc[0]:
            return None
    return [int(c) for c in info["field_codes_"][0][0] if c]


def main(out):
    names = dict(load())
    tags = all_tags()
    rows = collections.defaultdict(lambda: {"n": 0, "field": [], "tagged": [], "extra": collections.Counter()})
    for arm in (0, 1):
        path = os.path.join(out, f"arm{arm}", "results.jsonl")
        if not os.path.exists(path):
            continue
        for line in open(path):
            r = json.loads(line)
            if r["first"] not in DECKS:
                continue
            board = turn1_board(r["first"], r["second"], r["game"], r["seed"], r["history"])
            if board is None:
                continue
            d = rows[(r["first"], arm)]
            d["n"] += 1
            d["field"].append(len(board))
            best = {}
            for c in board:
                t = tags.get(abs(c), {})
                best[abs(c)] = max(best.get(abs(c), 0.0), t.get("set" if c < 0 else "field", 0.0))
            d["tagged"].append(sum(best.values()))
            d["extra"].update({abs(c) for c in board if card_data(abs(c))[2] & EXTRA})
    for deck in sorted({k[0] for k in rows}):
        print(f"\n{deck} going first")
        for arm in (0, 1):
            d = rows.get((deck, arm))
            if not d or not d["n"]:
                continue
            top = ", ".join(f"{names.get(c, c)} {k / d['n']:.0%}" for c, k in d["extra"].most_common(8))
            print(f"  arm {arm}: {d['n']} games, field {np.mean(d['field']):.1f} cards, tagged {np.mean(d['tagged']):.2f}"
                  f" | Extra Deck monsters: {top or 'none'}")


if __name__ == "__main__":
    main(sys.argv[1])
