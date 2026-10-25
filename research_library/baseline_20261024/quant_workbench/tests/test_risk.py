import numpy as np
import pytest
from quant_workbench.risk import block_paths, gbm_paths, summarize_paths


def test_gbm_ito_mean_and_variance_against_analytic():
    mu, sigma, days, n = 0.05, 0.2, 60, 50000
    terminal = gbm_paths(mu, sigma, days, simulations=n)[:, -1]
    t = days / 252
    expectation = np.exp(mu * t)
    variance = np.exp(2 * mu * t) * (np.exp(sigma ** 2 * t) - 1)
    assert abs(terminal.mean() - expectation) < 4 * np.sqrt(variance / n)
    assert terminal.var() == pytest.approx(variance, rel=0.04)


def test_empirical_cross_asset_pairing():
    r = np.random.default_rng(3).normal(0, 0.01, 300)
    result = block_paths(np.column_stack([r, r]), 60, simulations=100)
    np.testing.assert_array_equal(result[:, :, 0], result[:, :, 1])
    np.testing.assert_array_equal(result, block_paths(np.column_stack([r, r]), 60, simulations=100))


def test_drawdown_includes_initial_wealth():
    r = summarize_paths(np.array([[1, .8, .9], [1, .5, .6]]))
    assert r["terminal_loss_fraction"] == 1
    assert r["mean_worst_5pct_return"] == pytest.approx(-.4)
    assert r["drawdown_p05"] < -.45
