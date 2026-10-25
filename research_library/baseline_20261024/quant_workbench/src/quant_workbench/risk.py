"""Shreve-inspired model controls and empirical path-risk scenarios.

These are conditional model scenarios, not calibrated guarantees of future loss.
"""
from __future__ import annotations

import numpy as np


def gbm_paths(mu, sigma, days, simulations=10000, seed=20261023):
    if sigma < 0 or days < 1 or simulations < 1:
        raise ValueError("Invalid GBM parameters")
    rng = np.random.default_rng(seed)
    increments = (mu - 0.5 * sigma ** 2) / 252 + sigma / np.sqrt(252) * rng.standard_normal((simulations, days))
    return np.exp(np.column_stack([np.zeros(simulations), np.cumsum(increments, axis=1)]))


def block_paths(returns, days, simulations=10000, block=20, seed=20261023):
    """Resample contiguous historical blocks; multiple columns stay paired."""
    observed = np.asarray(returns, dtype=float)
    if observed.ndim == 1:
        observed = observed[:, None]
    observed = observed[np.isfinite(observed).all(axis=1)]
    if len(observed) < max(block * 3, 60) or (observed <= -1).any():
        raise ValueError("Insufficient or invalid empirical returns")
    rng = np.random.default_rng(seed)
    starts = rng.integers(0, len(observed) - block + 1, size=(simulations, (days + block - 1) // block))
    indices = (starts[:, :, None] + np.arange(block)).reshape(simulations, -1)[:, :days]
    sampled = observed[indices]
    values = np.cumprod(1 + sampled, axis=1)
    return np.concatenate([np.ones((simulations, 1, observed.shape[1])), values], axis=1)


def summarize_paths(paths):
    values = np.asarray(paths)
    if values.ndim != 2 or values.shape[1] < 2:
        raise ValueError("Expected one-asset or portfolio wealth paths")
    terminal = values[:, -1] / values[:, 0] - 1
    drawdown = (values / np.maximum.accumulate(values, axis=1) - 1).min(axis=1)
    fifth = np.quantile(terminal, 0.05)
    return {"terminal_p05": float(fifth), "terminal_median": float(np.median(terminal)),
            "terminal_p95": float(np.quantile(terminal, 0.95)),
            "terminal_loss_fraction": float(np.mean(terminal < 0)),
            "mean_worst_5pct_return": float(terminal[terminal <= fifth].mean()),
            "drawdown_p05": float(np.quantile(drawdown, 0.05)),
            "label": "Conditional model scenarios; not a reliable forecast probability"}


def stock_scenarios(returns, horizons=(20, 60, 120), simulations=10000):
    data = np.asarray(returns, dtype=float)
    data = data[np.isfinite(data)][-756:]
    if len(data) < 252 or np.any(data <= -1):
        raise ValueError("At least 252 valid returns required")
    log_returns = np.log1p(data)
    sigma = float(log_returns.std(ddof=1) * np.sqrt(252))
    estimated_mu = float(log_returns.mean() * 252 + 0.5 * sigma ** 2)
    results = {"history_observations": len(data), "annual_sigma": sigma,
               "historical_mu_unstable_estimate": estimated_mu, "horizons": {}}
    for days in horizons:
        empirical = block_paths(data, days, simulations=simulations)[:, :, 0]
        # Stress overlay is a specified scenario, not a fitted jump probability.
        jump = empirical.copy()
        jump[:, max(1, days // 4):] *= 0.8
        results["horizons"][str(days)] = {
            "historical_block_bootstrap": summarize_paths(empirical),
            "gbm_zero_arithmetic_drift": summarize_paths(gbm_paths(0, sigma, days, simulations)),
            "gbm_historical_drift": summarize_paths(gbm_paths(estimated_mu, sigma, days, simulations)),
            "specified_minus20pct_jump_stress": summarize_paths(jump),
        }
    return results
