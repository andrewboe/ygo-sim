import numpy as np

from ygosim.evalfit import fit_logistic, log_loss


def test_recovers_known_weights():
    rng = np.random.default_rng(0)
    X = np.column_stack([np.ones(4000), rng.normal(size=(4000, 2))])
    true_w = np.array([0.5, 2.0, -1.0])
    y = (rng.random(4000) < 1 / (1 + np.exp(-X @ true_w))).astype(float)
    w = fit_logistic(X, y, l2=0.1)
    assert np.allclose(w, true_w, atol=0.2)
    assert log_loss(X, y, w) < log_loss(X, y, np.zeros(3))
