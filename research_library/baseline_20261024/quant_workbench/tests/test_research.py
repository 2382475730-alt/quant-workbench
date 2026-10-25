import numpy as np
import pandas as pd
import pytest
from quant_workbench.metrics import block_mean_interval, metrics

from quant_workbench.research import decision_dates, portfolio_decisions, single_decisions


def test_initial_and_completed_month_decisions():
    dates = pd.bdate_range("2020-12-01", "2021-03-15")
    chosen = decision_dates(dates, "2021-01-01", "2021-03-15")
    assert chosen == list(pd.to_datetime(["2020-12-31", "2021-01-29", "2021-02-26"]))


def test_complete_pipeline_signal_future_invariance():
    dates = pd.bdate_range("2019-01-01", periods=750)
    close = pd.DataFrame({"a": np.linspace(10, 30, len(dates)), "b": np.linspace(10, 20, len(dates))}, index=dates)
    panels = {"adjusted_close": close, "amount": close * 1e8}
    members = pd.DataFrame({"trade_date": ["20181231", "20181231", "20201231"], "con_code": ["a", "b", "b"]})
    spec = {"kind": "momentum", "lookback": 252, "skip": 21, "count": 20}
    before = portfolio_decisions(panels, members, spec, "2020-01-01", "2020-12-31")
    close.loc[close.index >= "2021-01-01"] *= 10
    after = portfolio_decisions(panels, members, spec, "2020-01-01", "2020-12-31")
    assert before == after
    s = {"kind": "trend", "window": 200}
    first = single_decisions(panels, "a", s, "2020-01-01", "2020-12-31")
    close.loc[close.index >= "2021-01-01"] *= 10
    assert first == single_decisions(panels, "a", s, "2020-01-01", "2020-12-31")


def test_initial_loss_included_in_max_drawdown():
    frame = pd.DataFrame({"equity": [900., 990.], "gross_exposure": [1., 1.],
                          "fees_cumulative": [1., 2.], "slippage_cumulative": [0., 0.], "stale_holdings": [0, 0]})
    m = metrics(frame, initial=1000)
    assert m["max_drawdown"] == pytest.approx(-.1)
    assert m["total_return"] == pytest.approx(-.01)
    interval = block_mean_interval(np.full(300, .001))
    assert interval["lower_95"] == pytest.approx(.252)
