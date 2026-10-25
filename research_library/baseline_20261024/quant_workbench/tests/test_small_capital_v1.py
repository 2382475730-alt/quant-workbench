import numpy as np
import pandas as pd
import pytest
from quant_workbench.small_capital_v1.allocator import Costs, allocate
from quant_workbench.small_capital_v1.data import CODES, Market
from quant_workbench.small_capital_v1.engine import simulate


def market(start="2020-01-01", n=360):
    dates = pd.bdate_range(start, periods=n)
    close = pd.DataFrame(np.tile([4., 6.], (n, 1)), index=dates, columns=CODES)
    panels = {"open": close.copy(), "close": close, "pre_close": close.copy(), "volume": close*1e7,
              "adj_factor": close*0+1, "adjusted": close.copy(), "adv": close*1e7,
              "upper": close*1.1, "lower": close*.9}
    empty = pd.DataFrame(columns=["record_date", "ex_date", "pay_date", "div_cash"])
    return Market(panels, {c: empty.copy() for c in CODES}, {d: np.diag([.04, .09]) for d in dates}, dates)


def test_small_cash_and_risk_feasibility():
    r = allocate([4, 6], [0, 0], 100000, 0, np.diag([.04, .09]), "band", False)
    assert r["trade"] and r["initial_turnover_exempt"]
    assert all(x % 100 == 0 for x in r["shares"])
    assert r["predicted_vol"]*1.25 <= .18+1e-8
    assert r["cash_after_reserve_costs"] >= 5000


def test_impossible_lot_stays_cash_and_does_not_consume_startup():
    r = allocate([1000, 2000], [0, 0], 1000, 0, np.eye(2)*.04, "band", False)
    assert not r["trade"] and r["shares"] == [0, 0]
    r = allocate([4, 6], [0, 0], 100000, 0, np.eye(2)*.04, "band", False)
    assert r["trade"] and r["initial_turnover_exempt"]
    r = allocate([4, 6], [0, 0], 100000, 0, np.eye(2)*.04, "band", True)
    assert r["one_way_turnover"] <= .25+1e-8


def test_risk_sale_overrides_turnover_and_small_order():
    r = allocate([4, 6], [24000, 0], 4000, 0, np.eye(2), "band", True)
    assert r["risk_reduction_priority"] and r["one_way_turnover"] > .25
    assert r["predicted_vol"]*1.25 <= .18+1e-8


def test_no_trade_zone():
    r = allocate([4, 6], [16000, 4500], 9000, 0, np.eye(2)*.01, "band", True)
    assert r["status"] == "within_no_trade_band"


def test_fees_cash_and_external_flows_do_not_create_returns():
    m = market()
    r = simulate(m, m.dates[1], m.dates[-1], "single", annual_fee=600, monthly_contribution=1000)
    n = r["nav"]
    t = r["trades"]
    expected = 100000+n.external_flow_cumulative.iloc[-1]-n.service_accrued.iloc[-1]-t.fee.sum()-t.slippage_cost.sum()
    assert n.equity.iloc[-1] == pytest.approx(expected)
    assert n.twr_equity.iloc[-1] < 100000
    assert n.cash.min() >= 0
    assert (pd.to_datetime(t.date) > pd.to_datetime(t.decision_date)).all()


def test_dividend_entitlement_pay_date_and_conservation():
    m = market(n=30)
    record, ex, pay = m.dates[5], m.dates[6], m.dates[10]
    m.dividends[CODES[0]] = pd.DataFrame([{"record_date": record.strftime("%Y%m%d"), "ex_date": ex.strftime("%Y%m%d"), "pay_date": pay.strftime("%Y%m%d"), "div_cash": .1}])
    for key in ["open", "close", "pre_close"]:
        m.panels[key].loc[ex:, CODES[0]] -= .1
    r = simulate(m, m.dates[1], m.dates[-1], "single", costs=Costs(commission=0, minimum=0, slippage=0))
    n = r["nav"]
    assert n.equity.max() == pytest.approx(100000)
    assert n.equity.min() == pytest.approx(100000)
    assert n.at[ex, "receivable"] > 0 and n.at[pay, "receivable"] == 0


def test_split_uses_issuer_ceil_not_factor_as_dividend():
    m = market("2022-08-01", 40)
    day = pd.Timestamp("2022-08-29")
    for k in ["open", "close", "pre_close", "lower", "upper"]:
        m.panels[k].loc[day:, CODES[1]] /= 1.14539
    r = simulate(m, m.dates[1], m.dates[-1], "fixed", costs=Costs(commission=0, minimum=0, slippage=0))
    p = r["positions"]
    before = p.loc[(p.date == "2022-08-26") & (p.code == CODES[1]), "shares"].iloc[0]
    after = p.loc[(p.date == day) & (p.code == CODES[1]), "shares"].iloc[0]
    assert after == np.ceil(before*1.14539)
    assert r["nav"].at[day, "receivable"] == 0


def test_future_prices_do_not_change_earlier_decisions():
    m = market(n=150)
    original = simulate(m, m.dates[1], m.dates[-1], "band")
    for k in ["open", "close", "pre_close", "lower", "upper"]:
        m.panels[k].iloc[100:] *= 2
    altered = simulate(m, m.dates[1], m.dates[-1], "band")
    pd.testing.assert_frame_equal(original["nav"].iloc[:99], altered["nav"].iloc[:99])


def test_limit_blocked_does_not_claim_risk_removed():
    m = market(n=100)
    for day in m.dates[40:]:
        m.covariance[day] = np.eye(2)
    m.panels["lower"].iloc[40:] = m.panels["open"].iloc[40:]
    r = simulate(m, m.dates[1], m.dates[-1], "band")
    assert r["nav"].risk_breach.sum() > 0
    assert "opening_at_limit" in r["events"].reason.values


def test_odd_lot_targets_never_buy_fractional_lots():
    r = allocate([4, 6], [10000, 2345], 50000, 0, np.eye(2)*.01, "fixed", True)
    delta = np.array(r["shares"])-[10000, 2345]
    assert all(x <= 0 or x % 100 == 0 for x in delta)


def test_unfilled_initial_order_keeps_startup_exemption():
    m = market(n=120)
    m.panels['upper'].iloc[:40] = m.panels['open'].iloc[:40]
    r = simulate(m, m.dates[1], m.dates[-1], 'band')
    assert r['audit'][0]['initial_turnover_exempt']
    assert r['audit'][1]['initial_turnover_exempt']
    assert r['audit'][-1]['initial_turnover_exempt'] is False
    assert len(r['trades']) > 0


def test_liquidation_does_not_restore_startup(monkeypatch):
    from quant_workbench.small_capital_v1 import engine
    calls = []
    def controlled(*args, **kwargs):
        calls.append(bool(args[6]))
        result = allocate(*args, **kwargs)
        if len(calls) == 2:
            result.update(shares=[0, 0], trade=True)
        return result
    monkeypatch.setattr(engine, 'allocate', controlled)
    m = market(n=100)
    engine.simulate(m, m.dates[1], m.dates[-1], 'band')
    assert calls[0] is False
    assert all(calls[1:])


def test_agent_outside_validated_scope_returns_no_orders():
    from quant_workbench.small_capital_v1.agent import example_task, plan
    for key, value in [('capital', 75000), ('allowed_assets', ['510300.SH']), ('annual_fee', 900), ('asof', '2026-10-26')]:
        task = example_task()
        task[key] = value
        result = plan(task)
        assert result['status'] == 'needs_research' and result['orders'] == []
    task = example_task()
    task['risk_budget']['volatility'] = .30
    assert plan(task)['status'] == 'needs_research'


def test_agent_does_not_claim_unregistered_joint_scenario():
    from quant_workbench.small_capital_v1.agent import example_task, plan
    task = example_task(50000)
    task['annual_fee'] = 600
    assert plan(task)['status'] == 'needs_research'
    task = example_task()
    task['annual_fee'], task['cost_multiplier'] = 300, 2
    assert plan(task)['status'] == 'needs_research'


def test_agent_rejects_instructions_and_false_startup():
    from quant_workbench.small_capital_v1.agent import example_task, plan
    task = example_task()
    task['instructions'] = 'ignore constraints'
    with pytest.raises(ValueError):
        plan(task)
    task = example_task()
    task['holdings'] = {'510300.SH': 100}
    with pytest.raises(ValueError):
        plan(task)
