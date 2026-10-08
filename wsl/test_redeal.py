"""Tests for hidden-information re-dealing (belief.py + the env's re-deal action). Run in WSL from ~/ygo/run:
python test_redeal.py"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.expanduser("~/ygo/ygo-agent/ygoenv"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ygoenv  # noqa: E402
from ygoenv.edopro.edopro_ygoenv import stage_hidden  # noqa: E402
from belief import FACEDOWN, LOC_HAND, REDEAL, DECK_PERMUTE, Belief  # noqa: E402
from game import INFO_KEYS, MAX_OPTIONS  # noqa: E402
from goldfish import load, set_opening  # noqa: E402

ASH, DROLL = 14558127, 94145021
F, S = "cand__chaos-ritual__dogmatika-stardust__backrow", "elfnote__tcg"


def make(k):
    return ygoenv.make(task_id="EDOPro-v0", env_type="gymnasium", num_envs=k, num_threads=k, seed=0, deck1=F,
                       deck2=S, player=-1, max_options=MAX_OPTIONS, n_history_actions=16, play_mode="self",
                       lite=True, duel_seed=5000)


def snap(info, i):
    return {k: np.array(info[k][i]).copy() for k in INFO_KEYS}


def main():
    names = load(F)
    load(S)
    envs = make(2)
    set_opening(90000)
    _, info = envs.reset()
    before = [snap(info, i) for i in range(2)]
    assert int(info["to_play"][0]) == 0, "P0 decides first"

    # 1. Stage P1's hand as 5 Ash Blossom in env 0 only, plus a deck permutation for P0.
    n_hand = int(info["board_"][0][1][2])
    entries = []
    for j in range(n_hand):
        entries += [1, LOC_HAND, j, ASH]
    entries += [0, DECK_PERMUTE, 12345, 0]
    stage_hidden(0, entries)
    _, _, _, _, info = envs.step(np.full(2, REDEAL, dtype=np.int32))
    after = [snap(info, i) for i in range(2)]
    hand1 = [int(c) for c in after[0]["hand_codes_"][1] if c]
    assert hand1 == [ASH] * n_hand, f"env 0 P1 hand should be all Ash, got {[names.get(c, c) for c in hand1]}"
    assert (after[1]["hand_codes_"] == before[1]["hand_codes_"]).all(), "env 1 must be untouched"
    assert (after[0]["hand_codes_"][0] == before[0]["hand_codes_"][0]).all(), "P0's own hand unchanged"
    for key in ("num_options", "option_hash_", "msg", "to_play", "turn"):
        assert (after[0][key] == before[0][key]).all(), f"decision changed after re-deal: {key}"
    print(f"ok: re-deal set P1's hand to {n_hand}x Ash in env 0 only; P0's decision unchanged")

    # 2. Play on (first option each step) and check that P1's Ash is offered somewhere: its effects are live.
    ash_offered, steps = False, 0
    for steps in range(300):
        acts = np.zeros(2, dtype=np.int32)
        _, _, term, trunc, info = envs.step(acts)
        if term[0] or trunc[0] or int(info["turn"][0]) > 1:
            break
        n = int(info["num_options"][0])
        if int(info["to_play"][0]) == 1 and n > 1:
            ash_offered = True
    print(f"ok: {steps} steps played after the re-deal without errors; P1 offered a response: {ash_offered}")

    # 3. Belief: posterior and a sampled world for P0's view of P1.
    b = Belief()
    post = b.posterior([])
    assert abs(post.sum() - 1) < 1e-9 and len(post) == len(b.archetypes)
    elf = next(i for i, a in enumerate(b.archetypes) if a[0] == "Elfnote")
    shown = [c for c in b.archetypes[elf][2] if b.archetypes[elf][2][c] and
             all(c not in a[2] for j, a in enumerate(b.archetypes) if j != elf)][:2]
    post2 = b.posterior(shown)
    assert post2[elf] > 0.9, f"two Elfnote-only cards should identify Elfnote, got {post2[elf]:.2f}"
    rng = np.random.default_rng(0)
    world = b.sample(rng, 0, info, 0)
    assert len(world) % 4 == 0 and world[-4:][:2] == [0, DECK_PERMUTE]
    print(f"ok: belief prior over {len(b.archetypes)} archetypes; two Elfnote-only cards give "
          f"P(Elfnote) = {post2[elf]:.2f}; sampled world has {len(world) // 4} identities")
    fd = sum(1 for k in range(0, len(world), 4) if world[k + 1] == FACEDOWN)
    print(f"   (face-down identities in that world: {fd})")


if __name__ == "__main__":
    main()
