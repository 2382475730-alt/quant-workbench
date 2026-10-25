from copy import deepcopy
import numpy as np
import pandas as pd
import pytest
from quant_workbench_app.swine_cycle_policy import available_statement,CyclePolicy
from quant_workbench_app.swine_engine import SwineModel


def test_statement_publication_day_not_period_end_controls_visibility():
    rows=[{'end_date':'20260630','ann_date':'20260825','f_ann_date':'20260826','report_type':'1'},
          {'end_date':'20260331','ann_date':'20260429','report_type':'1'},
          {'end_date':'20260630','ann_date':'20260820','report_type':'2'}]
    assert available_statement(rows,'20260825')['end_date']=='20260331'
    assert available_statement(rows,'20260826')['end_date']=='20260630'
    assert available_statement(rows,'20260428') is None


def test_future_financial_market_and_capacity_changes_do_not_change_prior_decisions():
    model=SwineModel();before=model.run('2026-06-01','cycle_hold',end='2026-07-31')
    policy=model.cycle_policy
    for raw in policy.raw.values():
        for api in ('balancesheet','cashflow','income'):
            for row in raw[api]:
                if row.get('ann_date','')>'20260731':
                    for key in ('money_cap','total_liab','total_assets','n_cashflow_act','n_income_attr_p'):
                        if row.get(key) is not None:row[key]*=10
    for frame in policy.pb.values():frame.loc['2026-08-01':,'pb']*=20
    for row in policy.capacity:
        if row['published']>'2026-07-31':row['sow_yoy']=.8
    after=model.run('2026-06-01','cycle_hold',end='2026-07-31')
    assert before['decisions']==after['decisions']
    assert before['trades']==after['trades']
    for d in before['decisions']:
        assert d['information_date']<d['decision_date']
        assert d['financial_publication']<=d['information_date'].replace('-','')
        assert d['capacity_publication']<=d['information_date']


def test_target_weights_are_capital_independent_but_execution_differs():
    model=SwineModel()
    unit=model.run('2026-06-01','cycle_hold')
    small=model.run('2026-06-01','cycle_hold',capital=10000)
    large=model.run('2026-06-01','cycle_hold',capital=10000000)
    assert unit['decisions']==small['decisions']==large['decisions']
    assert small['summary']['mean_exposure']!=pytest.approx(large['summary']['mean_exposure'])


def test_risk_freeze_exit_and_missing_values_are_distinct():
    p=CyclePolicy(['002714.SZ']);date='2026-10-22'
    bal=available_statement(p.raw['002714.SZ']['balancesheet'],'20261022')
    cf=available_statement(p.raw['002714.SZ']['cashflow'],'20261022',bal['end_date'])
    bal.update(total_liab=90.,total_assets=100.,money_cap=1.,st_borr=20.,non_cur_liab_due_1y=20.)
    cf['n_cashflow_act']=-1.
    target,notes=p.targets(date,40,[.4])
    assert target[0]==0 and '退出' in notes[0]['reason']
    bal['total_liab']=80.
    target,notes=p.targets(date,40,[.4])
    assert target[0]==.4 and '冻结' in notes[0]['reason']
    bal['money_cap']=None
    target,notes=p.targets(date,40,[.4])
    assert target[0]==.4 and '缺项' in notes[0]['reason']


@pytest.mark.parametrize('override',[{'review_sessions':0},{'planned_exposure':[.8,.4,1]},{'entry_pb_percentile':float('nan')}])
def test_invalid_protocol_is_rejected(override):
    with pytest.raises(ValueError):CyclePolicy(['002714.SZ'],override)
