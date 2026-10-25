"""Close-of-day decisions; execution must occur after their timestamps."""
from __future__ import annotations

from datetime import timedelta

import numpy as np
import pandas as pd


def stock_signals(close: pd.Series, window=200, vol_window=60, target_vol=0.15):
    if (close.dropna() <= 0).any():
        raise ValueError("Prices must be positive")
    mean = close.rolling(window, min_periods=window).mean()
    volatility = close.pct_change(fill_method=None).rolling(vol_window, min_periods=vol_window).std() * np.sqrt(252)
    trend = (close > mean).astype(float).where(mean.notna(), 0.0)
    scaled = (target_vol / volatility.where(volatility > 1e-8)).clip(upper=1).fillna(0)
    return pd.DataFrame({"trend": trend, "trend_risk": trend * scaled,
                         "volatility": volatility, "moving_average": mean})


def historical_members(membership: pd.DataFrame, decision_date):
    """Use latest snapshot from a completed prior month, not today's membership.

    This conservative lag is a proxy, not proof of original publication timing.
    """
    date = pd.Timestamp(decision_date)
    cutoff = (date.to_pydatetime().replace(day=1) - timedelta(days=1)).strftime("%Y%m%d")
    known = membership.loc[membership.trade_date.astype(str) <= cutoff]
    if known.empty:
        return []
    latest = known.trade_date.astype(str).max()
    return sorted(known.loc[known.trade_date.astype(str) == latest, "con_code"].unique())


def momentum_scores(close: pd.DataFrame, lookback=252, skip=21):
    if not 0 < skip < lookback:
        raise ValueError("Require 0 < skip < lookback")
    return close.shift(skip) / close.shift(lookback) - 1


def portfolio_target(scores: pd.Series, eligible, count=20, cap=0.10):
    if count <= 0 or not 0 < cap <= 1:
        raise ValueError("Invalid allocation constraints")
    candidates = scores.reindex(sorted(set(eligible))).dropna()
    candidates = candidates.loc[np.isfinite(candidates)]
    # Stable code-order tie breaks; never force remaining cash into excess weights.
    chosen = candidates.sort_values(ascending=False, kind="stable").head(count)
    return {str(code): min(1 / len(chosen), cap) for code in chosen.index} if len(chosen) else {}
