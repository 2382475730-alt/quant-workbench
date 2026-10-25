import numpy as np
import pandas as pd
import pytest
from quant_workbench.engine import simulate as original_simulate
from quant_workbench.enhancement_audit import startup_turnover_audit
from quant_workbench.enhancement_data import config, dividend_events, industry_at
from quant_workbench.enhancement_engine import simulate
from quant_workbench.enhancement_engine_r3 import simulate as simulate_r3
from quant_workbench.enhancement_optimizer import shrunk_covariance, solve_allocation, within_sector
from quant_workbench.enhancement_optimizer_r2 import project_lots
from quant_workbench.enhancement_optimizer_r2 import solve_allocation as solve_r2
from quant_workbench.enhancement_optimizer_r3 import project_lots as project_r3
from quant_workbench.enhancement_optimizer_r4 import StartupBudget


def market(code="000001.SZ"):
    dates = pd.bdate_range("2023-01-02", periods=40)
    return {k: pd.DataFrame({code: np.full(40, v)}, index=dates)
            for k, v in {"open": 4.123, "close": 4.123, "volume": 1e8, "up_limit": 4.5, "down_limit": 3.7}.items()}


def test_old_stock_execution_identical_in_fork():
    panels = market()
    dates = panels["close"].index
    decisions = {dates[11]: {"000001.SZ": .8}, dates[20]: {}, dates[25]: {"000001.SZ": .4}}
    a, b = original_simulate(panels, decisions), simulate(panels, decisions)
    for name in a:
        pd.testing.assert_frame_equal(a[name], b[name])


def test_etf_ticks_and_sell_fee_do_not_include_stock_tax():
    panels = market("510300.SH")
    dates = panels["close"].index
    result = simulate(panels, {dates[11]: {"510300.SH": .8}, dates[20]: {}}, etf_codes={"510300.SH"})
    trades = result["trades"]
    assert trades.iloc[0].price == pytest.approx(4.127)
    sell = trades.loc[trades.shares.lt(0)].iloc[0]
    assert sell.fee == pytest.approx(max(5, sell.notional * .0003))


def test_feedback_uses_actual_holdings_and_next_day_execution():
    panels = market()
    dates = panels["close"].index
    observations = []

    def decision(date, actual, cash, equity, initial):
        observations.append((date, actual.copy(), cash, initial))
        return {"000001.SZ": .5} if initial else {}

    result = simulate(panels, {}, start=dates[12], decision_factory=decision, rebalance_dates=[dates[20]])
    assert observations[0][0] == dates[11] and observations[0][1] == {}
    assert observations[1][1]["000001.SZ"] > .49
    assert result["trades"].iloc[0].date == dates[12].strftime("%Y%m%d")
    assert result["trades"].iloc[-1].date == dates[21].strftime("%Y%m%d")
    modified = {k: v.copy() for k, v in panels.items()}
    for value in modified.values():
        value.iloc[25:] *= 1.1
    other = simulate(modified, {}, start=dates[12], decision_factory=decision, rebalance_dates=[dates[20]])
    pd.testing.assert_frame_equal(result["nav"].loc[:dates[24]], other["nav"].loc[:dates[24]])


def test_sector_intervals_do_not_backfill_future_or_resolve_conflicts():
    history = pd.DataFrame([
        {"ts_code": "A", "l1_code": "old", "in_date": "20100101", "out_date": "20230101"},
        {"ts_code": "A", "l1_code": "new", "in_date": "20230101", "out_date": None},
        {"ts_code": "B", "l1_code": "one", "in_date": "20100101", "out_date": None},
        {"ts_code": "B", "l1_code": "two", "in_date": "20100101", "out_date": None}])
    assert industry_at(history, "2022-12-30") == {"A": "old", "B": "UNKNOWN"}
    assert "A" not in industry_at(history, "2023-01-01")
    assert industry_at(history, "2023-01-02")["A"] == "new"


def test_dividend_duplicate_and_conflicting_entitlement():
    row = {"div_proc": "实施", "record_date": "20230101", "ex_date": "20230102", "pay_date": "20230105", "div_cash": .1}
    assert len(dividend_events(pd.DataFrame([row, row]))) == 1
    with pytest.raises(ValueError, match="Conflicting"):
        dividend_events(pd.DataFrame([row, row | {"div_cash": .2}]))


def test_sector_rank_not_implicit_sector_return_bet():
    scores = within_sector(pd.Series({"a": 100, "b": 200, "c": -10, "d": 0, "e": 999}),
                           pd.Series({"a": "x", "b": "x", "c": "y", "d": "y", "e": "z"}))
    assert scores.to_dict() == {"a": -1, "b": 1, "c": -1, "d": 1, "e": 0}


def test_covariance_psd_and_perfect_tracking():
    rng = np.random.default_rng(17)
    b = rng.normal(0, .01, 252)
    values = np.c_[b, b + rng.normal(0, .02, 252), np.zeros(252)]
    cov = shrunk_covariance(values)
    active = shrunk_covariance(values - b[:, None])
    assert np.linalg.eigvalsh(cov).min() >= -1e-12
    assert np.linalg.eigvalsh(active).min() >= -1e-12
    assert active[0, 0] == pytest.approx(0)


@pytest.mark.parametrize("solver", [solve_allocation, solve_r2])
def test_optimizer_obeys_caps_industry_turnover_and_risk(solver):
    settings = config()
    rng = np.random.default_rng(19)
    b = rng.normal(0, .01, 252)
    values = np.c_[b, b+rng.normal(0, .02, 252), b+rng.normal(0, .02, 252), np.zeros(252)]
    cov = shrunk_covariance(values)
    active = shrunk_covariance(values-b[:, None])
    old = np.array([.995, 0, 0, .005])
    matrix = np.array([[.5, 1, 0, 0], [.5, 0, 1, 0]])
    w, audit = solver([0, 1, .5, 0], old, matrix, np.array([.5, .5]), cov, active,
                                b.std(ddof=1)*np.sqrt(252), [1, .03, .03, .005], settings)
    assert w is not None and not audit["violations"]
    assert 0 < w[1] <= .030002 and w[0] >= .5
    assert np.abs(w-old).sum()/2 <= .150002
    assert audit["predicted_te"] <= .040002
    settings = settings | {"one_way_turnover_cap": .001}
    w, audit = solver([0, 1, .5, 0], old, matrix, np.array([.5, .5]), cov, active,
                                b.std(ddof=1)*np.sqrt(252), [1, .03, .03, .005], settings)
    assert w is not None and audit["one_way_turnover"] <= .001002


@pytest.mark.parametrize("solver", [solve_allocation, solve_r2])
def test_infeasibility_is_not_silently_relaxed(solver):
    s = config() | {"one_way_turnover_cap": .001}
    w, audit = solver([0, 1, 0], [0, 1, 0], np.array([[1, 1, 0]]), np.array([1]),
                                np.diag([.02, .04, 0]), np.diag([0, .04, .02]), .15, [1, .03, .005], s)
    assert w is None and (not audit["solver_success"] or audit["violations"])


def test_lot_projection_checks_constraints_and_sends_residual_to_etf():
    s = config()
    matrix = np.array([[.5, 1, 0], [.5, 0, 0]])
    w, audit = project_lots(np.array([.965, .03, .005]), ["510300.SH", "000001.SZ", "CASH"],
                            np.array([.995, 0, .005]), pd.Series({"000001.SZ": 135}), 1e6,
                            matrix, np.array([.5, .5]), np.diag([.02, .04, 0]), np.diag([0, .04, .02]),
                            .15, np.array([1, .03, .005]), s, False)
    assert w is not None and audit["reference_shares"]["000001.SZ"] == 200
    assert w[1] == pytest.approx(.027) and w[0] == pytest.approx(.968)
    assert audit["industry_max_deviation"] <= .03


def test_integer_projection_respects_turnover_risk_and_cash():
    matrix = np.array([[.5, 1, 0], [.5, 0, 0]])
    w, audit = project_r3(np.array([.965, .03, .005]), ["510300.SH", "000001.SZ", "CASH"],
                          np.array([.995, 0, .005]), pd.Series({"510300.SH": 4.3, "000001.SZ": 135}), 1e6,
                          matrix, np.array([.5, .5]), np.diag([.02, .04, 0]), np.diag([0, 4, .02]),
                          .15, np.array([1, .03, .005]), config(), False)
    assert w is not None and audit["projection_status"] == "integer_passed"
    assert .005-1e-7 <= w[-1] <= .007+1e-7
    assert w.sum() == pytest.approx(1)
    assert audit["one_way_turnover"] <= .140001 and audit["predicted_te"] <= .038001
    assert audit["reference_shares"]["000001.SZ"] % 100 == 0
    assert audit["reference_shares"]["510300.SH"] % 100 == 0


def test_share_instructions_are_not_rerounded_at_next_open():
    panels = market()
    dates = panels["close"].index
    class Maker:
        def __init__(self):
            self.last_share_target = {"000001.SZ": 100}
        def __call__(self, *args):
            return {"000001.SZ": 100*4.123/1e6}
    panels["open"].loc[dates[12]] = 4.2
    result = simulate_r3(panels, {}, start=dates[12], decision_factory=Maker())
    assert result["trades"].iloc[0].shares == 100
    assert result["trades"].iloc[0].date == dates[12].strftime("%Y%m%d")
    original = simulate(panels, {}, start=dates[12], decision_factory=Maker())
    assert original["trades"].empty


def test_r3_fork_preserves_static_weight_execution():
    panels = market()
    date = panels["close"].index[12]
    old, new = simulate(panels, {date: {"000001.SZ": .5}}), simulate_r3(panels, {date: {"000001.SZ": .5}})
    for key in ["nav", "trades", "positions", "events"]:
        pd.testing.assert_frame_equal(old[key], new[key])


def test_startup_exemption_waits_for_actual_fill_and_never_reopens():
    state = StartupBudget()
    assert state.exempt({})
    assert state.exempt({})  # Failed optimization/unfilled first order is not an investment.
    assert not state.exempt({"510300.SH": .01})
    assert not state.exempt({})  # Liquidation must not reset the turnover exemption.


def test_executed_turnover_audit_uses_first_actual_fill_after_failed_start():
    trades = pd.DataFrame([{"date": "20230201", "shares": 100}, {"date": "20230301", "shares": -100}, {"date": "20230403", "shares": 100}])
    records = [{"decision_date": d, "one_way_executed": .9, "initial_exempt": False}
               for d in ["2023-01-31", "2023-02-28", "2023-03-31"]]
    audit = startup_turnover_audit(trades, records)
    assert audit["changed_exemption_flags"] == 1
    assert audit["executed_turnover_violations"] == 2
