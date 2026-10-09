"""Fit the position evaluation from game outcomes (THEORY §5.1).

Each logged position is a turn-end feature vector for the player who just finished the turn, labeled
with that player's game result (1 win, 0 loss, 0.5 draw). A logistic regression gives P(win) from the
features; its weights replace the designed evaluation in wsl/game.py.

Win/loss alone is a thin signal (AUDIT.md item 3: a fit on 180 mirror games valued held hand traps
below zero), so the fit is anchored to the designed weights: L2 pulls toward them, not toward zero,
and a held hand trap must stay worth more than the same card on the field. Only positions from the
current pilot version are used, and validation holds out whole matchups.
"""
import json
from pathlib import Path

import numpy as np

from .api import DATA_DIR

POSITIONS = DATA_DIR / "games" / "positions.jsonl"
WEIGHTS = DATA_DIR / "games" / "eval_weights.json"


# Designed weights (wsl/game.py DEFAULT_WEIGHTS) and the pilot version positions must come from.
PRIOR = {"lp_diff_k": 1.0, "own_tagged": 1.0, "opp_tagged": -1.0, "own_hand": 0.3, "opp_hand": -0.3,
         "own_field": 0.3, "opp_field": -0.3, "own_hand_traps": 1.0, "own_protected": 0.4, "own_threat": 0.4}
CONFIG = "v3-belief"
HAND_TRAP_MARGIN = 0.5  # held hand trap (own_hand + own_hand_traps) >= card on field (own_field) + margin


def load_positions(path: Path = POSITIONS, config: str = CONFIG):
    rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    rows = [r for r in rows if r.get("config") == config]
    if not rows:
        raise SystemExit(f"no positions logged by pilot version {config} yet")
    names = sorted({k for r in rows for k in r["features"]})
    X = np.array([[r["features"].get(n, 0.0) for n in names] for r in rows], dtype=float)
    y = np.array([r["won"] for r in rows], dtype=float)
    games = np.array([hash((tuple(r["decks"]), r["game"])) for r in rows])
    matchups = np.array([hash(tuple(sorted(r["decks"]))) for r in rows])
    return names, X, y, games, matchups


def fit_logistic(X, y, l2=1.0, iters=50, w0=None, names=None):
    """Newton's method on the log loss with L2 toward w0 (bias unregularized), projected onto the
    hand-trap constraint after each step."""
    w0 = np.zeros(X.shape[1]) if w0 is None else w0
    w = w0.copy()
    reg = np.full(X.shape[1], l2)
    reg[0] = 0.0
    for _ in range(iters):
        p = 1 / (1 + np.exp(-X @ w))
        grad = X.T @ (p - y) + reg * (w - w0)
        hess = (X * (p * (1 - p))[:, None]).T @ X + np.diag(reg)
        w -= np.linalg.solve(hess, grad)
        if names is not None:
            w = _project(w, names)
    return w


def _project(w, names):
    idx = {n: i for i, n in enumerate(names)}
    if {"own_hand_traps", "own_hand", "own_field"} <= set(idx):
        floor = w[idx["own_field"]] - w[idx["own_hand"]] + HAND_TRAP_MARGIN
        w[idx["own_hand_traps"]] = max(w[idx["own_hand_traps"]], floor)
    return w


def log_loss(X, y, w):
    p = np.clip(1 / (1 + np.exp(-X @ w)), 1e-6, 1 - 1e-6)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def fit(l2: float = 1.0, holdout: float = 0.25, seed: int = 0) -> dict:
    names, X, y, games, matchups = load_positions()
    if "bias" in names:  # bias first so it stays unregularized
        order = [names.index("bias")] + [i for i, n in enumerate(names) if n != "bias"]
        names, X = [names[i] for i in order], X[:, order]
    w0 = np.array([PRIOR.get(n, 0.0) for n in names])
    # Hold out whole matchups: the evaluation must generalize to pairings it wasn't fitted on.
    rng = np.random.default_rng(seed)
    unique = np.unique(matchups)
    test_m = set(rng.choice(unique, size=max(1, int(len(unique) * holdout)), replace=False))
    test = np.array([m in test_m for m in matchups])
    w = fit_logistic(X[~test], y[~test], l2, w0=w0, names=names)
    base = np.zeros_like(w)
    base[0] = np.log(max(y[~test].mean(), 1e-3) / max(1 - y[~test].mean(), 1e-3))
    prior_only = w0.copy()
    prior_only[0] = base[0]
    report = {
        "positions": int(len(y)), "games": int(len(np.unique(games))), "matchups": int(len(unique)),
        "test_log_loss": log_loss(X[test], y[test], w),
        "test_log_loss_designed": log_loss(X[test], y[test], prior_only),
        "test_log_loss_base_rate": log_loss(X[test], y[test], base),
        "test_accuracy": float(np.mean(((X[test] @ w) > 0) == (y[test] > 0.5))),
    }
    w_all = fit_logistic(X, y, l2, w0=w0, names=names)  # final weights use every game
    out = {"weights": dict(zip(names, map(float, w_all))), "report": report, "l2": l2, "config": CONFIG}
    WEIGHTS.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out
