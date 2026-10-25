"""Common evaluation, uncertainty and transparent baseline comparisons."""
from __future__ import annotations

import numpy as np
import pandas as pd


def returns_from_nav(nav, initial=1_000_000.0):
    returns = nav.equity.pct_change(fill_method=None)
    returns.iloc[0] = nav.equity.iloc[0] / initial - 1
    return returns


def metrics(nav, trades=None, initial=1_000_000.0):
    returns = returns_from_nav(nav, initial)
    wealth = np.r_[initial, nav.equity.to_numpy()]
    n = len(nav)
    annual = float((wealth[-1] / initial) ** (252 / n) - 1)
    vol = float(returns.std(ddof=1) * np.sqrt(252))
    dd = wealth / np.maximum.accumulate(wealth) - 1
    sharpe = float(returns.mean() * 252 / vol) if vol > 1e-10 else None
    turnover = 0.0
    if trades is not None and not trades.empty:
        turnover = float(trades.notional.sum() / nav.equity.mean() / (n / 252))
    return {"days": n, "total_return": float(wealth[-1] / initial - 1), "cagr": annual,
            "volatility": vol, "sharpe_zero_cash_rate": sharpe,
            "max_drawdown": float(dd.min()), "annual_two_way_turnover": turnover,
            "average_exposure": float(nav.gross_exposure.mean()),
            "fees": float(nav.fees_cumulative.iloc[-1]), "slippage": float(nav.slippage_cumulative.iloc[-1]),
            "trade_count": len(trades) if trades is not None else 0,
            "stale_holding_days": int(nav.stale_holdings.gt(0).sum())}


def block_mean_interval(difference, block=20, samples=2000, seed=20261023):
    data = np.asarray(difference, dtype=float)
    data = data[np.isfinite(data)]
    if len(data) < 3 * block:
        return {"supported": False, "reason": "insufficient_length"}
    rng = np.random.default_rng(seed)
    starts = rng.integers(0, len(data) - block + 1, (samples, (len(data) + block - 1) // block))
    indices = (starts[:, :, None] + np.arange(block)).reshape(samples, -1)[:, :len(data)]
    means = data[indices].mean(axis=1) * 252
    lo, hi = np.quantile(means, [.025, .975])
    return {"supported": True, "annual_arithmetic_mean_difference": float(data.mean() * 252),
            "lower_95": float(lo), "upper_95": float(hi), "block": block,
            "note": "Pointwise block-bootstrap interval; not corrected for all strategy trials"}


def compare(nav, baseline, initial=1_000_000.0):
    joined = pd.concat([returns_from_nav(nav, initial).rename("strategy"),
                        returns_from_nav(baseline, initial).rename("benchmark")], axis=1).dropna()
    x, y = joined.benchmark.to_numpy(), joined.strategy.to_numpy()
    variance = x.var()
    beta = float(np.cov(y, x, ddof=0)[0, 1] / variance) if variance > 1e-12 else None
    result = block_mean_interval(y - x)
    result.update({"beta": beta, "annual_residual_intercept": float((y - beta * x).mean() * 252) if beta is not None else None,
                   "risk_matched_note": "Beta/intercept are descriptive, not proof of causal skill or an implementable benchmark."})
    return result
