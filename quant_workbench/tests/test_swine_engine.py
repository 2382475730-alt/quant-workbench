import math

import numpy as np
import pandas as pd
import pytest

from quant_workbench_app.swine_engine import Costs, SwineModel, capital_plan, dividend_events


def synthetic_model():
    m = SwineModel.__new__(SwineModel)
    m.codes = ['A', 'B']
    m.dates = pd.bdate_range('2026-01-01', '2026-07-31')
    m.entry_dates = m.dates[m.dates >= '2026-06-01']
    shape = (len(m.dates), 2)
    m.a = {'raw_open': np.full(shape, 10.), 'raw_close': np.full(shape, 10.),
           'volume': np.full(shape, 1e7), 'upper': np.full(shape, 11.), 'lower': np.full(shape, 9.)}
    m.vol = np.full(len(m.dates), .2)
    m.trend = np.full(len(m.dates), True)
    m.adv = np.full(shape, 1e7)
    m.events = {0: [], 1: []}
    return m


FREE = Costs(commission=0, minimum=0, transfer=0, sell_levy=0, slippage=0, dividend_reserve=0)


def test_unit_and_integer_same_under_divisible_free_execution():
    m = synthetic_model()
    unit = m.run('2026-06-01', 'hold80', costs=FREE)
    actual = m.run('2026-06-01', 'hold80', capital=100000, costs=FREE)
    assert unit['summary']['return'] == pytest.approx(0)
    assert actual['summary']['return'] == pytest.approx(0)
    assert actual['nav'][0]['cash'] == pytest.approx(20000)
    assert all(r['shares'] % 100 == 0 for r in actual['positions'])


def test_drawdown_includes_initial_cash_and_costs():
    m = synthetic_model()
    result = m.run('2026-06-01', 'hold80', end='2026-06-01')
    assert result['summary']['return'] < 0
    assert result['summary']['max_drawdown'] == pytest.approx(result['summary']['return'])


def test_dividend_entitlement_not_given_to_ex_date_buyer():
    m = synthetic_model()
    m.events[0] = [{'record_date': '20260602', 'ex_date': '20260603', 'pay_date': '20260604', 'cash_div_tax': 1, 'stk_div': 0}]
    i = m.dates.get_loc('2026-06-03')
    m.a['raw_open'][i:,0] = 9
    m.a['raw_close'][i:,0] = 9
    a = m.run('2026-06-01', 'hold80', costs=FREE)
    b = m.run('2026-06-03', 'hold80', costs=FREE)
    assert [e['type'] for e in a['events']] == ['dividend_accrued','dividend_paid']
    assert a['summary']['return'] == pytest.approx(0)
    assert not b['events']
    nav = {r['date']: r for r in a['nav']}
    assert nav['2026-06-03']['receivable'] > 0
    assert nav['2026-06-04']['receivable'] == pytest.approx(0)


def test_duplicate_dividend_deduplication_and_conflict_rejection():
    row = {'ts_code': 'A', 'div_proc': '实施', 'record_date': '20260602', 'ex_date': '20260603',
           'pay_date': '20260604', 'cash_div_tax': 1, 'stk_div': 0, 'div_listdate': None}
    assert len(dividend_events([row,row])) == 1
    with pytest.raises(ValueError, match='Conflicting'):
        dividend_events([row,{**row, 'cash_div_tax': 2}])


def test_blocked_limit_is_not_filled_and_cash_remains():
    m = synthetic_model()
    m.a['upper'][:] = 10
    result = m.run('2026-06-01', 'hold80', costs=FREE)
    assert not result['trades']
    assert result['summary']['ending_cash'] == 1
    assert result['summary']['blocked_orders'] == 2


def test_small_account_omission_is_explicit_and_never_leveraged():
    plan = capital_plan(1000, {'A': 35, 'B': 12}, {'A': .4, 'B': .4})
    assert set(plan['omitted_names']) == {'A', 'B'}
    assert plan['cash'] == 1000
    assert plan['minimum_capital_for_one_lot_each']>1000
    with pytest.raises(ValueError):
        capital_plan(math.nan, {'A': 1}, {'A': .8})


def test_capital_capacity_days_and_residual_cash_are_explicit():
    p=capital_plan(1000000,{'A':10},{'A':.8},costs=FREE,volumes={'A':100000})
    assert p['rows'][0]['shares']==1000
    assert p['capacity_days_proxy']==80
    assert p['capacity_limited_names']==['A']
    assert p['implementation_cash_gap']==pytest.approx(.79)


def test_invalid_cost_and_missing_capacity_cannot_create_trades():
    m=synthetic_model()
    with pytest.raises(ValueError):
        m.run('2026-06-01',costs=Costs(dividend_reserve=1.1))
    with pytest.raises(ValueError):
        capital_plan(10000,{'A':10},{'A':.8},volumes={'A':math.nan})
    m.adv[:]=math.nan
    assert not m.run('2026-06-01',capital=10000)['trades']


def test_future_close_cannot_change_existing_orders():
    m = synthetic_model()
    original = m.run('2026-06-01', 'hold80')
    m.a['raw_close'][m.dates.get_loc('2026-07-01'):] *= 3
    changed = m.run('2026-06-01', 'hold80')
    assert original['trades'] == changed['trades']


def test_fundamental_freeze_does_not_buy_to_restore_weight_after_price_decline():
    m=synthetic_model()
    class Policy:
        config={'review_sessions':20}
        def targets(self,date,offset,previous):
            return np.array([.4,.4]),[{'execution_permission':'rebalance' if offset==0 else 'hold'} for _ in range(2)]
    m.cycle_policy=Policy()
    i=m.dates.get_loc('2026-06-15');m.a['raw_open'][i:,0]=5.;m.a['raw_close'][i:,0]=5.
    run=m.run('2026-06-01','cycle_hold',costs=FREE)
    assert len(run['trades'])==2
    assert all(t['date']=='2026-06-01' for t in run['trades'])


def test_real_risk_signals_and_orders_ignore_future_market_changes(monkeypatch):
    from quant_workbench_app import swine_engine
    original=SwineModel()
    start, cut='2026-06-01','2026-08-01'
    before=original.run(start,'risk80')
    altered={key:frame.copy() for key,frame in original.market.items()}
    for key in ('open','close','raw_open','raw_close','upper','lower'):
        altered[key].loc[cut:]*=1.25
    monkeypatch.setattr(swine_engine,'load_market',lambda codes:(altered,[]))
    changed=SwineModel().run(start,'risk80')
    assert [t for t in before['trades'] if t['date']<cut]==[t for t in changed['trades'] if t['date']<cut]


@pytest.mark.parametrize('capital', [1000, 10000, 100000, 1000000, 10000000])
def test_cash_fees_positions_reconcile_for_capital_scales(capital):
    m = synthetic_model()
    run = m.run('2026-06-01', 'staged80', capital=capital)
    assert run['summary']['ending_cash'] >= 0
    for row in run['nav']:
        assert row['equity'] == pytest.approx(row['cash']+row['market_value']+row['receivable'])
    assert capital-sum(t['gross']+t['fees'] for t in run['trades']) == pytest.approx(run['summary']['ending_cash'])
