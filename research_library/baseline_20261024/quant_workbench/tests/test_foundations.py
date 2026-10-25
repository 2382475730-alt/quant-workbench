import numpy as np
import pandas as pd
import pytest
from quant_workbench.signals import (
    historical_members,
    momentum_scores,
    portfolio_target,
    stock_signals,
)

from quant_workbench.data import write_json


def test_reject_outside_write():
    with pytest.raises(ValueError, match="outside"):
        write_json("../must_not_write.json", {})


def test_future_does_not_change_past_stock_signals():
    index = pd.bdate_range("2018-01-01", periods=400)
    prices = pd.Series(np.linspace(10, 30, 400), index=index)
    original = stock_signals(prices)
    prices.iloc[300:] *= 100
    changed = stock_signals(prices)
    pd.testing.assert_frame_equal(original.iloc[:300], changed.iloc[:300])


def test_momentum_excludes_recent_period():
    prices = pd.DataFrame({"a": np.arange(1, 301, dtype=float)})
    scores = momentum_scores(prices)
    assert scores.iloc[-1, 0] == pytest.approx(279 / 48 - 1)
    prices.iloc[-21:, 0] *= 10
    assert momentum_scores(prices).iloc[-1, 0] == scores.iloc[-1, 0]


def test_historical_members_excludes_current_month():
    members = pd.DataFrame({"trade_date": ["20200131", "20200228", "20200331"], "con_code": ["old", "new", "future"]})
    assert historical_members(members, "2020-02-28") == ["old"]
    assert historical_members(members, "2020-03-31") == ["new"]
    assert historical_members(members, "2020-01-15") == []


def test_weights_and_missing_scores():
    target = portfolio_target(pd.Series({"a": 1, "b": np.nan, "c": 2, "d": np.inf}), ["a", "b", "c", "d"])
    assert target == {"c": 0.1, "a": 0.1}
    assert sum(target.values()) <= 1


def test_zero_volatility_is_not_infinite_position():
    result = stock_signals(pd.Series([10.0] * 300))
    assert result.trend_risk.eq(0).all()
    assert result.trend.between(0, 1).all()
