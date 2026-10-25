import numpy as np
import pandas as pd
import pytest
from quant_workbench.engine import Action, Costs, quantity, simulate


def market():
    dates = pd.bdate_range("2023-01-02", periods=30)
    return {name: pd.DataFrame({"000001.SZ": np.full(30, value)}, index=dates)
            for name, value in {"open": 10.0, "close": 10.0, "volume": 1_000_000,
                                "up_limit": 11.0, "down_limit": 9.0}.items()}


def test_next_day_and_cash_conservation():
    panels = market()
    dates = panels["close"].index
    result = simulate(panels, {dates[10]: {"000001.SZ": 1}}, initial_cash=10000, costs=Costs(multiplier=0))
    assert result["trades"].iloc[0].date == dates[11].strftime("%Y%m%d")
    assert result["nav"].equity.eq(10000).all()
    assert result["positions"].shares.eq(1000).all()
    assert result["nav"].cash.ge(0).all()


def test_missing_quote_defers_order():
    panels = market()
    dates = panels["close"].index
    panels["open"].iloc[11] = np.nan
    result = simulate(panels, {dates[10]: {"000001.SZ": 1}}, initial_cash=10000, costs=Costs(multiplier=0))
    assert result["trades"].iloc[0].date == dates[12].strftime("%Y%m%d")
    assert "no_trading_quote" in result["events"].reason.tolist()


def test_limit_does_not_assume_fill():
    panels = market()
    dates = panels["close"].index
    panels["up_limit"].iloc[11:16] = 10
    result = simulate(panels, {dates[10]: {"000001.SZ": 1}}, initial_cash=10000, costs=Costs(multiplier=0))
    assert result["trades"].empty
    assert "expired_order" in result["events"].type.tolist()


def test_dividend_receivable_preserves_wealth_and_is_not_cash_early():
    panels = market()
    dates = panels["close"].index
    panels["open"].iloc[13:] = 9
    panels["close"].iloc[13:] = 9
    action = Action("000001.SZ", dates[12].strftime("%Y%m%d"), dates[13].strftime("%Y%m%d"),
                    cash_per_share=1, pay_date=dates[15].strftime("%Y%m%d"))
    result = simulate(panels, {dates[10]: {"000001.SZ": 1}}, [action], initial_cash=10000, costs=Costs(multiplier=0))
    nav = result["nav"]
    assert nav.equity.eq(10000).all()
    assert nav.loc[dates[13], "receivable"] == 1000
    assert nav.loc[dates[13], "cash"] == 0
    assert nav.loc[dates[15], "cash"] == 1000
    assert nav.loc[dates[15], "receivable"] == 0


def test_bonus_cannot_sell_before_listing():
    panels = market()
    dates = panels["close"].index
    panels["open"].iloc[13:] = 5
    panels["close"].iloc[13:] = 5
    panels["down_limit"].iloc[13:] = 4.5
    panels["up_limit"].iloc[13:] = 5.5
    action = Action("000001.SZ", dates[12].strftime("%Y%m%d"), dates[13].strftime("%Y%m%d"),
                    stock_ratio=1, list_date=dates[15].strftime("%Y%m%d"))
    result = simulate(panels, {dates[10]: {"000001.SZ": 1}, dates[12]: {}}, [action], initial_cash=10000, costs=Costs(multiplier=0))
    assert result["nav"].equity.eq(10000).all()
    sells = result["trades"].query("shares < 0")
    assert sells.shares.tolist() == [-1000, -1000]
    assert sells.date.tolist() == [dates[13].strftime("%Y%m%d"), dates[15].strftime("%Y%m%d")]


def test_fee_regime_and_cash_reconciliation():
    costs = Costs()
    assert costs.fee(10000, True, "20230827") - costs.fee(10000, True, "20230828") == pytest.approx(5)
    panels = market()
    dates = panels["close"].index
    result = simulate(panels, {dates[10]: {"000001.SZ": 1}, dates[15]: {}}, initial_cash=10000)
    trades = result["trades"]
    cash = 10000 - (trades.shares * trades.price + trades.fee).sum()
    assert result["nav"].iloc[-1].cash == pytest.approx(cash)
    assert result["nav"].iloc[-1].equity == pytest.approx(cash)
    assert cash < 10000


def test_trade_rules_and_long_only_constraints():
    assert quantity("688001.SH", 199) == 0
    assert quantity("688001.SH", 201) == 201
    assert quantity("000001.SZ", 201) == 200
    assert quantity("000001.SZ", 57, sell=True, holding=57) == 57
    panels = market()
    with pytest.raises(ValueError, match="long-only"):
        simulate(panels, {panels["close"].index[10]: {"000001.SZ": 1.1}})
    with pytest.raises(ValueError, match="after"):
        simulate(panels, {}, execution_delay=0)


def test_future_market_changes_do_not_change_past_fills():
    panels = market()
    dates = panels["close"].index
    decisions = {dates[10]: {"000001.SZ": 1}}
    before = simulate(panels, decisions)
    for field in ["open", "close", "volume", "up_limit", "down_limit"]:
        panels[field].iloc[20:] *= 10
    after = simulate(panels, decisions)
    pd.testing.assert_frame_equal(before["nav"].iloc[:20], after["nav"].iloc[:20])
    pd.testing.assert_frame_equal(before["trades"], after["trades"])


def test_suspended_ex_date_does_not_manufacture_wealth():
    panels = market()
    dates = panels["close"].index
    for key in ["open", "close"]:
        panels[key].iloc[13:15] = np.nan
        panels[key].iloc[15:] = 4.5
    action = Action("000001.SZ", dates[12].strftime("%Y%m%d"), dates[13].strftime("%Y%m%d"),
                    cash_per_share=1, stock_ratio=1, pay_date=dates[15].strftime("%Y%m%d"),
                    list_date=dates[15].strftime("%Y%m%d"))
    result = simulate(panels, {dates[10]: {"000001.SZ": 1}}, [action], initial_cash=10000, costs=Costs(multiplier=0))
    assert result["nav"].equity.eq(10000).all()
    assert result["nav"].loc[dates[13], "stale_market_value"] == 9000
    position = result["positions"].loc[result["positions"].date.eq(dates[14])].iloc[0]
    assert position.stale_trading_days == 2


def test_unknown_entitlement_blocks_held_strategy_only():
    panels = market()
    dates = panels["close"].index
    action = Action("000001.SZ", dates[12].strftime("%Y%m%d"), dates[13].strftime("%Y%m%d"),
                    uncertain_entitlement=True)
    with pytest.raises(ValueError, match="Unresolved shareholder"):
        simulate(panels, {dates[10]: {"000001.SZ": 1}}, [action])
    result = simulate(panels, {}, [action])
    assert result["nav"].equity.eq(1_000_000).all()


def test_shareholder_transfer_then_split_uses_enlarged_record_holding():
    panels = market()
    dates = panels["close"].index
    for key in ["open", "close"]:
        panels[key].iloc[13:18] = np.nan
        panels[key].iloc[18:] = 10 / 3.5
    fmt = lambda i: dates[i].strftime("%Y%m%d")
    transfer = Action("000001.SZ", fmt(12), fmt(13), stock_ratio=.5,
                      list_date=fmt(14), mark_stock_ratio=0)
    split = Action("000001.SZ", fmt(16), fmt(17), stock_ratio=2.5, list_date=fmt(18))
    result = simulate(panels, {dates[10]: {"000001.SZ": 1}}, [transfer, split],
                      initial_cash=10000, costs=Costs(multiplier=0))
    assert result["positions"].iloc[-1].shares == 5250
    assert result["nav"].loc[dates[13]:, "equity"].to_numpy() == pytest.approx(15000)
    assert result["events"].query("type == 'corporate_action'").bonus_shares.tolist() == [500, 3750]


def test_merger_replaces_old_security_and_locks_new_shares_until_listing():
    panels = market()
    dates = panels["close"].index
    for key, frame in panels.items():
        frame["600019.SH"] = frame["000001.SZ"] * (2 if key != "volume" else 1)
    for key in ["open", "close"]:
        panels[key].loc[dates[13]:, "000001.SZ"] = np.nan
    fmt = lambda i: dates[i].strftime("%Y%m%d")
    action = Action("000001.SZ", fmt(12), fmt(13), exchange_to="600019.SH", exchange_ratio=.5, list_date=fmt(16))
    result = simulate(panels, {dates[10]: {"000001.SZ": 1}, dates[13]: {}}, [action],
                      initial_cash=10000, costs=Costs(multiplier=0))
    assert result["nav"].equity.eq(10000).all()
    sold = result["trades"].query("shares < 0")
    assert sold.code.tolist() == ["600019.SH"]
    assert sold.shares.tolist() == [-500]
    assert sold.date.tolist() == [fmt(16)]
    assert not result["positions"].query("date >= @dates[13] and code == '000001.SZ'").size
