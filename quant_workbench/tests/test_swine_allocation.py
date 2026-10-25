from copy import deepcopy
import pytest
from quant_workbench_app.paths import PROJECT
from quant_workbench_app.swine_data import read
from quant_workbench_app.swine_allocation import tier_allocation

DATA=read(PROJECT/'runtime/research/swine_deep_20261025/model/results.json')
POLICY=read(PROJECT/'config/swine_allocation.json')

def run(**kwargs):return tier_allocation(DATA['profiles'],DATA['costs'],POLICY,**kwargs)

def test_current_tiers_keep_unknown_and_funding_gate_unallocated():
    plan=run();rows={r['code']:r for r in plan['rows']}
    assert rows['002124.SZ']['cash_hard_gate']
    assert rows['002124.SZ']['target_weight']==0
    assert rows['600975.SH']['cost_band']=='未核实' and rows['600975.SH']['target_weight']==0
    assert rows['605296.SH']['cash_band']=='缓冲偏薄'
    assert rows['002714.SZ']['tier']=='B'
    assert plan['target_exposure']<plan['budget']
    assert sum(r['target_weight'] for r in plan['rows'])+plan['target_cash']==pytest.approx(1)
    assert all(r['target_weight']<=r['candidate_weight']<=r['company_cap'] for r in plan['rows'])

def test_valuation_conditions_release_without_changing_quality_candidate_weights():
    base=run(terminal_roe=.2);higher=run(terminal_roe=.4)
    for a,b in zip(base['rows'],higher['rows']):
        assert a['tier']==b['tier'] and a['candidate_weight']==b['candidate_weight']
        assert a['target_weight']<=b['target_weight']
    assert base['target_exposure']<higher['target_exposure']

def test_stale_cost_and_no_candidates_leave_cash():
    policy=deepcopy(POLICY);policy['as_of']='2027-06-01'
    result=tier_allocation(DATA['profiles'],DATA['costs'],policy)
    assert result['target_cash']==1 and all(r['tier']=='D' for r in result['rows'])
    assert run(budget=0)['target_cash']==1


def test_high_cash_ratio_cannot_mask_capex_burn():
    profiles=deepcopy(DATA['profiles']);p=profiles[0]
    p.update(cash_short_coverage=.8,debt_ratio=.5,cash_available_proxy=100,operating_cashflow=-600,capex_cash=600)
    result=tier_allocation(profiles,DATA['costs'],POLICY)['rows'][0]
    assert result['cash_band']=='缓冲偏薄' and result['tier']=='C'

@pytest.mark.parametrize('kwargs',[{'budget':1.1},{'terminal_roe':float('nan')},{'required_return':0}])
def test_bad_allocation_inputs_cannot_produce_weights(kwargs):
    with pytest.raises(ValueError):run(**kwargs)
