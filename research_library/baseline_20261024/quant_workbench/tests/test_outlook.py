import numpy as np
import pandas as pd
import pytest
from quant_workbench.outlook import portfolio_scenarios, sizing_preview


def test_small_capital_and_expensive_minimum_lot_remain_cash():
    r = sizing_preview({"688001.SH": .5, "000001.SZ": .5}, {"688001.SH": 300, "000001.SZ": 10}, 1000)
    assert r["cash_after_estimated_costs"] == 1000
    assert all(x["illustrative_shares"] == 0 for x in r["rows"])
    r = sizing_preview({"000001.SZ": 1}, {"000001.SZ": 10}, 10000)
    assert r["cash_after_estimated_costs"] >= 0
    assert r["rows"][0]["illustrative_shares"] == 900
    assert r["cash_after_estimated_costs"] + sum(x["estimated_outlay"] for x in r["rows"]) == pytest.approx(10000)


def test_joint_scenario_does_not_fill_missing_returns_and_preserves_cash():
    dates = pd.bdate_range("2020-01-01", periods=300)
    returns = pd.DataFrame({"A": np.zeros(300), "B": np.zeros(300)}, index=dates)
    returns.iloc[:50, 1] = np.nan
    assert portfolio_scenarios(returns, {"A": .5, "B": .5})["status"] == "insufficient_joint_history"
    result = portfolio_scenarios(returns[["A"]], {"A": .4}, horizons=(20,), simulations=100)
    assert result["horizons"]["20"]["joint_historical_block_bootstrap"]["terminal_median"] == 0
    assert result["horizons"]["20"]["specified_all_equities_minus20pct_jump"]["terminal_median"] == pytest.approx(-.08)
