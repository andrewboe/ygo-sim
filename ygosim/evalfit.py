"""Fit the position evaluation from game outcomes (THEORY §5.1).

Each logged position is a turn-end feature vector for the player who just finished the turn, labeled
with that player's game result (1 win, 0 loss, 0.5 draw). A logistic regression with L2 gives P(win)
from the features. Its weights replace the hand-picked evaluation in wsl/game.py, and games played with
them produce better data for the next fit.
"""
import json
from pathlib import Path

import numpy as np

from .api import DATA_DIR

POSITIONS = DATA_DIR / "games" / "positions.jsonl"
WEIGHTS = DATA_DIR / "games" / "eval_weights.json"


def load_positions(path: Path = POSITIONS):
    rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    names = sorted({k for r in rows for k in r["features"]})
    X = np.array([[r["features"].get(n, 0.0) for n in names] for r in rows], dtype=float)
    y = np.array([r["won"] for r in rows], dtype=float)
    games = np.array([hash((tuple(r["decks"]), r["game"])) for r in rows])
    return names, X, y, games


def fit_logistic(X, y, l2=1.0, iters=50):
    """Newton's method on the L2-regularized log loss (bias column unregularized)."""
    w = np.zeros(X.shape[1])
    reg = np.full(X.shape[1], l2)
    reg[0] = 0.0
    for _ in range(iters):
        p = 1 / (1 + np.exp(-X @ w))
        grad = X.T @ (p - y) + reg * w
        hess = (X * (p * (1 - p))[:, None]).T @ X + np.diag(reg)
        w -= np.linalg.solve(hess, grad)
    return w


def log_loss(X, y, w):
    p = np.clip(1 / (1 + np.exp(-X @ w)), 1e-6, 1 - 1e-6)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def fit(l2: float = 1.0, holdout: float = 0.25, seed: int = 0) -> dict:
    names, X, y, games = load_positions()
    if "bias" in names:  # bias first so it stays unregularized
        order = [names.index("bias")] + [i for i, n in enumerate(names) if n != "bias"]
        names, X = [names[i] for i in order], X[:, order]
    rng = np.random.default_rng(seed)
    unique = np.unique(games)
    test_games = set(rng.choice(unique, size=max(1, int(len(unique) * holdout)), replace=False))
    test = np.array([g in test_games for g in games])
    w = fit_logistic(X[~test], y[~test], l2)
    base = np.zeros_like(w)
    base[0] = np.log(max(y[~test].mean(), 1e-3) / max(1 - y[~test].mean(), 1e-3))
    report = {
        "positions": int(len(y)), "games": int(len(unique)),
        "test_log_loss": log_loss(X[test], y[test], w),
        "test_log_loss_base_rate": log_loss(X[test], y[test], base),
        "test_accuracy": float(np.mean(((X[test] @ w) > 0) == (y[test] > 0.5))),
    }
    w_all = fit_logistic(X, y, l2)  # final weights use every game
    out = {"weights": dict(zip(names, map(float, w_all))), "report": report, "l2": l2}
    WEIGHTS.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out
