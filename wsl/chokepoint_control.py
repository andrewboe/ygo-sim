"""Control for the chokepoint map: replaying to a window and *passing* must recover ~the goldfish board.
Also prints what happens on the best interruption line, so a big drop can be checked by eye."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from goldfish import KIND_PASS, load, make_pool, search_opening  # noqa: E402
from card_tags import all_tags  # noqa: E402
from chokepoint import card_names, state_after  # noqa: E402

deck, opponent, opening = sys.argv[1], sys.argv[2], int(sys.argv[3])
names = load(deck)
ids = card_names(names)
tags = all_tags()
k = 32
envs = make_pool(deck, k, 1000, opponent=f"_p2__{opponent}")
base, _ = search_opening(envs, k, opening, 15, 1.0, tags, None)
show = lambda r: [("(set) " if c < 0 else "") + names.get(abs(c), str(c)) for c in r.board if c]
print(f"goldfish {base.score:.2f}, {len(base.actions)} actions, windows at {[w.step for w in base.windows]}")
print(f"  board {show(base)}")
for w in base.windows:
    prefix = base.actions[:w.step]
    info = state_after(envs, k, opening, prefix)
    n = int(info["num_options"])
    pass_opt = next(o for o in range(n) if info["option_kinds_"][o] == KIND_PASS)
    replay, _ = search_opening(envs, k, opening, 8, 1.0, tags, None, prefix, [pass_opt], rng_salt=7)
    print(f"window step {w.step} (after {ids.get(w.p1_card)}): pass -> {replay.score:.2f}")
    for option, card, _ in w.options:
        hit, _ = search_opening(envs, k, opening, 8, 1.0, tags, None, prefix, [option], rng_salt=9)
        print(f"  {ids.get(card)} -> {hit.score:.2f} in {len(hit.actions) - w.step} more actions; board {show(hit)}")
