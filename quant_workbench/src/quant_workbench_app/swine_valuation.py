"""Transparent conditional equity recovery and funding models; no fitted target price."""
import math

def recovery_value(book_per_share, price, required_return=.10, interim_roes=(-.10,0,.10),
                   terminal_roe=.15, payout=.3):
    values=(book_per_share,price,required_return,terminal_roe,payout,*interim_roes)
    if not all(math.isfinite(x) for x in values) or book_per_share<=0 or price<=0:
        raise ValueError('净资产、价格及参数须为有限数值，净资产和价格须为正')
    if not 0<required_return<1 or not 0<=payout<=1 or terminal_roe<0 or len(interim_roes)>10:
        raise ValueError('折现率、分红率、恢复期或终态ROE超出有效范围')
    if any(r<=-1 or r>2 for r in interim_roes):
        raise ValueError('过渡期ROE须大于-100%且不超过200%')
    book=book_per_share
    pv_dividends=0.
    path=[]
    residual_income_pv=0.
    for year,roe in enumerate(interim_roes,1):
        opening=book
        profit=opening*roe
        dividend=max(profit,0)*payout
        book=opening+profit-dividend
        discount=(1+required_return)**year
        pv_dividends+=dividend/discount
        residual_income_pv+=(profit-required_return*opening)/discount
        path.append({'year':year,'opening_book':opening,'roe':roe,'profit':profit,'dividend':dividend,
                     'closing_book':book,'pv_dividend':dividend/discount})
    discount=(1+required_return)**len(interim_roes)
    terminal_value=book*terminal_roe/required_return
    value=pv_dividends+terminal_value/discount
    required_roe=(price-pv_dividends)*required_return*discount/book
    ri_value=book_per_share+residual_income_pv+book*(terminal_roe-required_return)/required_return/discount
    return {'book_per_share':book_per_share,'price':price,'required_return':required_return,'interim_roes':list(interim_roes),
            'terminal_roe':terminal_roe,'payout':payout,'path':path,'closing_book':book,'pv_dividends':pv_dividends,
            'terminal_value':terminal_value,'conditional_value':value,'relative_to_price':value/price-1,
            'required_terminal_roe':required_roe,'residual_income_value':ri_value,'identity_error':value-ri_value,
            'terminal_pv_share':(terminal_value/discount/value) if value>0 else None,
            'method':'过渡期清洁盈余净资产滚动＋终态零增长全部盈利分配；不新增权益融资、不再增杠杆，终态再投资覆盖维持能力'}

def funding_stress(cash_available, short_obligations, operating_cashflow, capex, months=6,
                   burn_factor=1., refinancing=.5, horizon=12):
    values=(cash_available,short_obligations,operating_cashflow,capex,months,burn_factor,refinancing,horizon)
    if not all(math.isfinite(x) for x in values) or min(cash_available,short_obligations,capex,burn_factor)<0 or months<=0 or horizon<=0 or not 0<=refinancing<=1:
        raise ValueError('资金压力参数无效')
    burn=max(0,capex-operating_cashflow)/months*burn_factor
    debt_cash=short_obligations*(1-refinancing)
    ending=cash_available-burn*horizon-debt_cash
    return {'monthly_burn':burn,'cash_runway_months':cash_available/burn if burn>0 else None,
            'debt_cash_payment':debt_cash,'ending_cash_before_new_funds':ending,'new_funding_required':max(0,-ending),
            'burn_factor':burn_factor,'refinancing':refinancing,'horizon':horizon,
            'scope':'静态压力：仅经营净现金减购建长期资产；不含新增融资、额外分红利息、资产处置、现金用途改变；不是违约预测'}

def supply_change(sow_change, pigs_per_sow_change, weight_change):
    if any(not math.isfinite(x) or x<=-1 for x in (sow_change,pigs_per_sow_change,weight_change)):
        raise ValueError('供给参数无效')
    return (1+sow_change)*(1+pigs_per_sow_change)*(1+weight_change)-1


def profit_requirement(price,shares,annual_kg,normal_pe=15,cost_per_kg=12,volume_change=0,other_profit=0):
    values=(price,shares,annual_kg,normal_pe,cost_per_kg,volume_change,other_profit)
    if not all(math.isfinite(x) for x in values) or min(price,shares,annual_kg,normal_pe)<=0 or cost_per_kg<0 or volume_change<=-1:
        raise ValueError('盈利桥输入须为有限数值，价格、股本、重量及PE须为正，量变化须大于−100%')
    kg=annual_kg*(1+volume_change)
    total_profit=price*shares/normal_pe
    pig_profit=total_profit-other_profit
    spread=pig_profit/kg
    return {'price':price,'shares':shares,'normal_pe':normal_pe,'cost_per_kg':cost_per_kg,'volume_change':volume_change,
            'annual_kg_proxy':annual_kg,'scenario_kg':kg,'other_profit_assumption':other_profit,
            'required_company_profit':total_profit,'required_pig_surplus':pig_profit,'required_spread':spread,
            'required_selling_price':cost_per_kg+spread,'one_yuan_spread_impact':kg,
            'scope':'A股每股价格/假设PE隐含全公司归母利润，暂用养殖价差承担剩余要求；仅诊断条件，非合并利润预测。月报重量含内部交易，年化量非预测。'}
