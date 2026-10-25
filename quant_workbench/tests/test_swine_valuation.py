from decimal import Decimal
import math
import pytest
from quant_workbench_app.swine_valuation import recovery_value,funding_stress,supply_change,profit_requirement

def test_clean_surplus_zero_growth_equilibrium():
    for payout in (0,.3,1):
        r=recovery_value(10,10,.1,(.1,.1,.1),.1,payout)
        assert r['conditional_value']==pytest.approx(10)
        assert r['required_terminal_roe']==pytest.approx(.1)
        assert r['identity_error']==pytest.approx(0,abs=1e-12)

def test_recovery_value_independent_decimal_cashflow():
    b=Decimal('12');ke=Decimal('.12');pv=Decimal(0)
    for year,roe in enumerate([Decimal('-.2'),Decimal('.05'),Decimal('.15')],1):
        profit=b*roe;div=max(profit,Decimal(0))*Decimal('.4')
        b=b+profit-div;pv+=div/(1+ke)**year
    expected=pv+b*Decimal('.18')/ke/(1+ke)**3
    r=recovery_value(12,25,.12,(-.2,.05,.15),.18,.4)
    assert r['conditional_value']==pytest.approx(float(expected))
    assert recovery_value(12,25,.12,(-.2,.05,.15),r['required_terminal_roe'],.4)['conditional_value']==pytest.approx(25)

def test_waiting_with_losses_requires_higher_terminal_profitability():
    immediate=recovery_value(10,20,.1,(),.15)
    delayed=recovery_value(10,20,.1,(-.1,0,0),.15)
    assert delayed['required_terminal_roe']>immediate['required_terminal_roe']
    assert delayed['conditional_value']<immediate['conditional_value']

def test_funding_refinancing_and_spending_are_separate():
    r=funding_stress(100,120,-12,18,months=6,refinancing=.5,burn_factor=1,horizon=12)
    assert r['monthly_burn']==5
    assert r['ending_cash_before_new_funds']==-20
    assert r['new_funding_required']==20
    assert funding_stress(100,120,-12,18,refinancing=1)['new_funding_required']==0

def test_supply_efficiency_can_offset_sow_contraction():
    assert supply_change(-.107,.05,.02)==pytest.approx(.893*1.05*1.02-1)
    assert supply_change(-.107,.15,.02)>0


def test_operating_profit_requirement_units_and_volume_sensitivity():
    r=profit_requirement(30,1e9,2e9,15,12,0,0)
    assert r['required_company_profit']==2e9
    assert r['required_spread']==1 and r['required_selling_price']==13
    larger=profit_requirement(30,1e9,2e9,15,12,.25,0)
    assert larger['required_spread']==pytest.approx(.8)
    with pytest.raises(ValueError):profit_requirement(30,1e9,2e9,0,12)

@pytest.mark.parametrize('value',[math.nan,math.inf,-1])
def test_invalid_required_returns_rejected(value):
    with pytest.raises(ValueError):recovery_value(10,20,value)
