"""Imitation dataset for the neural pilot (THEORY §5, training stage 1).

Search logs store action sequences, not network inputs. This replays each logged line through the env
with full observations (lite=False) and records, at every decision we want the pilot to imitate:
  cards_, global_, actions_, h_actions_   ygoenv observation tensors
  num_options, action                     legal option count and the searched choice
  player, value                           who decided, and the line's outcome for that player

Sources:
  data/search/*.jsonl   chokepoint/robust logs: P1's chosen turn-1 line (value = its board), and each
                        interruption trial's reply (P2's interruption decision and P1's continuation,
                        value = the board after it; P2's value is its negative)

Output: data/train/<source>.npz shards. Replays are exact (deterministic duel seed + opening).

Run from ~/ygo/run:  python dataset.py [--max-lines N]
"""
import argparse
import glob
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.expanduser("~/ygo/ygo-agent/ygoenv"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ygoenv  # noqa: E402
from goldfish import MAX_OPTIONS, RUN, load, set_opening  # noqa: E402

SEARCH = "/mnt/c/Users/andre/Desktop/ygo-sim/data/search"
TRAIN = "/mnt/c/Users/andre/Desktop/ygo-sim/data/train"
OBS_KEYS = ("cards_", "global_", "actions_", "h_actions_")


_ENVS = {}  # never destroyed: tearing down an envpool and creating another crashes ygoenv


def make_env(deck: str, opponent: str, seed: int):
    key = (deck, opponent, seed)
    if key not in _ENVS:
        _ENVS[key] = _new_env(deck, opponent, seed)
    return _ENVS[key]


def _new_env(deck: str, opponent: str, seed: int):
    return ygoenv.make(task_id="EDOPro-v0", env_type="gymnasium", num_envs=1, num_threads=1, seed=0,
                       deck1=deck, deck2=opponent, player=-1, max_options=MAX_OPTIONS,
                       n_history_actions=16, play_mode="self", lite=False, duel_seed=seed,
                       shuffle2=not opponent.startswith("_p2__"))


def replay(env, opening: int, actions: list[int], imitate: dict[int, float], start: int = 0) -> list[dict]:
    """Replay `actions`; from step `start` on, record decisions by players in `imitate`
    ({player: value target for that player})."""
    set_opening(opening)
    obs, info = env.reset()
    out = []
    for t, a in enumerate(actions):
        p = int(info["to_play"][0])
        n = int(info["num_options"][0])
        if a >= n:
            raise ValueError(f"replay diverged at step {t}: action {a} >= {n} options")
        if t >= start and p in imitate and n > 1:  # forced moves teach nothing
            out.append({**{k: obs[k][0].copy() for k in OBS_KEYS}, "num_options": n, "action": a,
                        "player": p, "value": imitate[p]})
        obs, _, term, trunc, info = env.step(np.array([a], dtype=np.int32))
        if term[0] or trunc[0]:
            break
    return out


def examples_from_search(path: str, max_lines: int | None) -> list[dict]:
    rows = [json.loads(l) for l in open(path)][:max_lines]
    out = []
    for r in rows:
        env = make_env(r["deck"], f"_p2__{r['opponent']}", r["seed"])
        group = hash((r["deck"], r["seed"], r["hand"])) & 0x7FFFFFFF  # one opening; split train/val by it
        ex = replay(env, r["hand"], r["actions"], {0: r["line"]})  # P1's chosen line, valued by its board
        for t in r["trials"]:  # each interruption: P2's choice and P1's continuation
            ex += replay(env, r["hand"], t["reply"], {0: t["score"], 1: -t["score"]}, start=t["prefix_len"])
        out += [{**e, "group": group} for e in ex]
    return out


def save(examples: list[dict], name: str) -> str:
    os.makedirs(TRAIN, exist_ok=True)
    arrays = {k: np.stack([e[k] for e in examples]) for k in OBS_KEYS}
    for k in ("num_options", "action", "player", "value", "group"):
        arrays[k] = np.array([e[k] for e in examples])
    path = f"{TRAIN}/{name}.npz"
    np.savez_compressed(path, **arrays)
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-lines", type=int, default=None, help="per source file (for testing)")
    args = ap.parse_args()
    files = sorted(glob.glob(f"{SEARCH}/*.jsonl"))
    decks = {json.loads(open(f).readline())["deck"] for f in files}
    for d in decks:
        load(d)
    total = 0
    for f in files:
        name = os.path.basename(f)[:-6]
        try:
            ex = examples_from_search(f, args.max_lines)
        except ValueError as e:
            print(f"{name}: skipped ({e})", flush=True)
            continue
        if ex:
            path = save(ex, name)
            total += len(ex)
            shapes = {k: ex[0][k].shape for k in OBS_KEYS}
            print(f"{name}: {len(ex)} examples -> {path} {shapes}", flush=True)
    print(f"total {total} examples")


if __name__ == "__main__":
    main()
