"""Imitation training (THEORY §5, stage 1): fit the pilot to the search's choices and outcomes.

Reads data/train/*.npz (wsl/dataset.py), holds out 10% of examples, and reports how often the pilot
picks the search's option on held-out decisions, against a uniform-random baseline (mean 1/options).
Checkpoints go to data/checkpoints/ with the config needed to reload them.

Run in the WSL venv:  python train_pilot.py [--epochs N] [--dim D]
"""
import argparse
import glob
import json
import os
import time

import numpy as np
import torch

from pilot import Pilot, loss_fn

TRAIN = "/mnt/c/Users/andre/Desktop/ygo-sim/data/train"
CKPT = "/mnt/c/Users/andre/Desktop/ygo-sim/data/checkpoints"
KEYS = ("cards_", "global_", "actions_", "num_options", "action", "value")


def load_all():
    parts = [np.load(p) for p in sorted(glob.glob(f"{TRAIN}/*.npz"))]
    data = {k: np.concatenate([p[k] for p in parts]) for k in KEYS}
    # Opening id per example (older shards without one: each file is its own group).
    data["group"] = np.concatenate([p["group"] if "group" in p else np.full(len(p["action"]), i)
                                    for i, p in enumerate(parts)])
    data["deck"] = np.concatenate([p["deck"] if "deck" in p else np.full(len(p["action"]), "?")
                                   for p in parts])
    return data


def batches(data, idx, bs, device, shuffle):
    if shuffle:
        idx = np.random.permutation(idx)
    for i in range(0, len(idx), bs):
        j = idx[i:i + bs]
        yield [torch.as_tensor(data[k][j], device=device) for k in KEYS]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=10)
    ap.add_argument("--dim", type=int, default=128)
    ap.add_argument("--layers", type=int, default=4)
    ap.add_argument("--batch", type=int, default=256)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--holdout-deck", help="validate only on decks with this name prefix (never trained on)")
    ap.add_argument("--resume", action="store_true", help="continue from the last completed epoch")
    args = ap.parse_args()
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    device = torch.device("cuda")

    data = load_all()
    n = len(data["action"])
    # Hold out whole openings: decisions from one opening share line prefixes, so a per-example split
    # would leak near-duplicate positions into validation.
    if args.holdout_deck:
        # Generalization test: the pilot never sees this deck in training (THEORY §5 pilot quality).
        is_val = np.array([d.startswith(args.holdout_deck) for d in data["deck"]])
        print(f"holding out every example from decks starting with {args.holdout_deck!r}: {is_val.sum()}")
    else:
        groups = np.unique(data["group"])
        val_groups = set(np.random.choice(groups, size=max(1, len(groups) // 10), replace=False))
        is_val = np.array([g in val_groups for g in data["group"]])
        print(f"{len(groups)} openings, {len(val_groups)} held out")
    val, train = np.flatnonzero(is_val), np.flatnonzero(~is_val)
    baseline = float(np.mean(1.0 / data["num_options"][val]))
    print(f"{n} examples ({len(train)} train / {len(val)} val); uniform-random accuracy {baseline:.1%}")

    model = Pilot(args.dim, args.layers).to(device)
    print(f"{sum(p.numel() for p in model.parameters()) / 1e6:.1f}M parameters")
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
    os.makedirs(CKPT, exist_ok=True)
    resume_path = f"{CKPT}/pilot_imitation.resume.pt"
    start = 0
    if args.resume and os.path.exists(resume_path):
        state = torch.load(resume_path, map_location=device)
        model.load_state_dict(state["model"])
        opt.load_state_dict(state["opt"])
        start = state["epoch"] + 1
        print(f"resumed after epoch {state['epoch']}")
    t0 = time.time()
    for epoch in range(start, args.epochs):
        model.train()
        tot, cnt = 0.0, 0
        for cards, glob_, acts, nopt, action, value in batches(data, train, args.batch, device, True):
            with torch.autocast("cuda", dtype=torch.bfloat16):
                logits, v = model(cards, glob_, acts, nopt)
            loss, _ = loss_fn(logits.float(), v.float(), action.long(), value.float())
            opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            tot += loss.item() * len(action)
            cnt += len(action)
        model.eval()
        hits, vloss = 0, 0.0
        with torch.no_grad():
            for cards, glob_, acts, nopt, action, value in batches(data, val, 1024, device, False):
                logits, v = model(cards, glob_, acts, nopt)
                hits += (logits.argmax(-1) == action).sum().item()
                vloss += torch.nn.functional.mse_loss(v, value.float(), reduction="sum").item()
        print(f"epoch {epoch}: train loss {tot / cnt:.3f}, val accuracy {hits / len(val):.1%}, "
              f"val value MSE {vloss / len(val):.2f} [{time.time() - t0:.0f}s]", flush=True)
        # Resume point every epoch (stop any time; --resume continues). Same split via --seed.
        torch.save({"model": model.state_dict(), "opt": opt.state_dict(), "epoch": epoch}, resume_path)

    path = f"{CKPT}/pilot_imitation.pt"
    torch.save({"model": model.state_dict(), "config": vars(args), "val_accuracy": hits / len(val),
                "baseline": baseline, "examples": n}, path)
    print(f"saved {path}")


if __name__ == "__main__":
    main()
