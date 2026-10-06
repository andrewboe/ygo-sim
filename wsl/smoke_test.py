"""Random self-play across the field decks: does the 2024 env survive the 2026 engine?
Run from ~/ygo/run (the env loads scripts from ./edopro_script)."""
import glob
import os
import sys
import time
from collections import Counter

import numpy as np

sys.path.insert(0, os.path.expanduser("~/ygo/ygo-agent/ygoenv"))
import ygoenv  # noqa: E402
from ygoenv.edopro import init_module  # noqa: E402

RUN = os.path.expanduser("~/ygo/run")
N_ENVS = int(sys.argv[1]) if len(sys.argv) > 1 else 16
N_GAMES = int(sys.argv[2]) if len(sys.argv) > 2 else 200
VERBOSE = len(sys.argv) > 3 and sys.argv[3] == "verbose"
MAX_STEPS = 20_000


def main():
    os.chdir(RUN)
    decks = {os.path.basename(p)[:-4]: p for p in glob.glob(f"{RUN}/decks/*.ydk")}
    init_module(f"{RUN}/cards.cdb", f"{RUN}/code_list.txt", decks)
    envs = ygoenv.make(task_id="EDOPro-v0", env_type="gymnasium", num_envs=N_ENVS, num_threads=N_ENVS,
                       seed=0, deck1="random", deck2="random", player=-1, max_options=24,
                       n_history_actions=16, play_mode="self", verbose=VERBOSE)
    obs, info = envs.reset()
    rng = np.random.default_rng(0)
    games, lengths, reasons, steps = 0, [], Counter(), 0
    ep_len = np.zeros(N_ENVS, dtype=int)
    t0 = time.time()
    while games < N_GAMES and steps < MAX_STEPS:
        n_opt = info["num_options"]
        actions = np.array([rng.integers(0, max(1, n)) for n in n_opt], dtype=np.int32)
        obs, reward, term, trunc, info = envs.step(actions)
        ep_len += 1
        steps += 1
        for i in np.flatnonzero(term | trunc):
            games += 1
            lengths.append(ep_len[i])
            reasons[int(info["win_reason"][i])] += 1
            ep_len[i] = 0
    dt = time.time() - t0
    print(f"{games} games, {steps * N_ENVS} env steps in {dt:.1f}s "
          f"({steps * N_ENVS / dt:,.0f} steps/s, {games / dt:.1f} games/s)")
    if lengths:
        print(f"episode length: mean {np.mean(lengths):.0f}, max {max(lengths)}; win reasons {dict(reasons)}")


if __name__ == "__main__":
    main()
