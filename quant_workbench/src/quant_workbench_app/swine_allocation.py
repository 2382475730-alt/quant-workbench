"""Current evidence tiers and conditional weights, independent of capital or replay."""
from calendar import monthrange
from datetime import date
import math
from .swine_valuation import recovery_value


def tier_allocation(profiles,costs,policy,budget=None,terminal_roe=None,required_return=None):
    budget=policy['budget'] if budget is None else budget
    terminal_roe=policy['terminal_roe'] if terminal_roe is None else terminal_roe
    required_return=policy['required_return'] if required_return is None else required_return
    if not all(math.isfinite(x) for x in (budget,terminal_roe,required_return)) or not 0<=budget<=1 or not 0<=terminal_roe<=1:
        raise ValueError('总额度须在0—100%，终态ROE须在0—100%，且参数须有限')
    observed=date.fromisoformat(policy['as_of']);rows=[]
    for p in profiles:
        c=next((c for c in costs if c['code']==p['code']),None)
        reasons=[];cost_band='未核实';fresh=False
        if c:
            period=c['period'];year=int(period[:4]);month=6 if period.endswith('H1') else int(period[5:7])
            elapsed=(observed-date(year,month,monthrange(year,month)[1])).days
            fresh=0<=elapsed<=policy['max_cost_age_days']
            cost_band='低成本证据' if c['value']<=policy['cost_low'] else ('中档成本证据' if c['value']<=policy['cost_middle'] else '成本改善待兑现')
            reasons.append(f"成本{period} {c['value']}元/kg，{c['definition']}；距期间末{elapsed}天。")
            if not fresh:cost_band+='／待更新'
        else:reasons.append('缺少核实的完全成本，不赋予有利档位。')
        cash=p['cash_short_coverage'];debt=p['debt_ratio'];ocf=p['operating_cashflow']
        burn=max(0,p['capex_cash']-ocf)/6
        runway=p['cash_available_proxy']/burn if burn else None
        strong_flow=runway is None or runway>=policy['cash_runway_strong_months']
        ordinary_flow=runway is None or runway>=policy['cash_runway_ordinary_months']
        if cash is None or cash<policy['cash_hard_floor'] or (debt>=policy['debt_stress'] and ocf<0):
            cash_band='融资约束优先';hard=True
        elif cash>=policy['cash_strong'] and debt<=policy['debt_strong_max'] and strong_flow:
            cash_band='相对较强';hard=False
        elif cash>=policy['cash_ordinary'] and ordinary_flow:
            cash_band='依赖续作';hard=False
        else:cash_band='缓冲偏薄';hard=False
        reasons.append(f"统一H1可用现金/短期义务{cash:.1%}，资产负债率{debt:.1%}。" if cash is not None else '现金覆盖缺失。')
        reasons.append(f"H1经营现金减购建支出的流出不变时，现金可覆盖{runway:.1f}个月，尚未扣还债；含可削减的扩张支出，是压力口径。" if runway is not None else 'H1经营现金覆盖购建支出，不向未来外推净流入；仍须考虑还债。')
        if hard or not c or not fresh:tier='D'
        elif cash_band=='相对较强' and c['value']<=policy['cost_low']:tier='A'
        elif cash_band!='缓冲偏薄' and c['value']<=policy['cost_middle']:tier='B'
        else:tier='C'
        value=recovery_value(p['latest_bps'],p['price'],required_return,policy['interim_roes'],terminal_roe,policy['payout'])
        coverage=value['conditional_value']/p['price'];release=0
        for threshold,factor in policy['valuation_release']:
            if coverage>=threshold:release=factor;break
        valuation_band='有条件余量' if release==1 else ('接近条件价值' if release==.5 else ('恢复依赖较高' if release==.25 else '当前假设不足'))
        reasons.append(f"终态ROE{terminal_roe:.1%}、要求回报{required_return:.1%}下，条件价值/现价{coverage:.2f}倍，释放候选额度{release:.0%}；不是估计概率。")
        if hard:reasons.append('先核实融资与每股权益变化，当前新增额度为零。')
        rows.append({'code':p['code'],'name':p['name'],'tier':tier,'cost_band':cost_band,'cash_band':cash_band,
                     'valuation_band':valuation_band,'value_coverage':coverage,'conditional_value':value['conditional_value'],
                     'cash_hard_gate':hard,'cash_runway_months':runway,'cost_fresh':fresh,'units':policy['tier_units'][tier],
                     'company_cap':policy['tier_caps'][tier],'release':release,'reasons':reasons})
    total=sum(r['units'] for r in rows)
    for r in rows:
        r['candidate_weight']=min(r['company_cap'],budget*r['units']/total) if total else 0
        r['target_weight']=r['candidate_weight']*r['release']
    target=sum(r['target_weight'] for r in rows)
    return {'as_of':policy['as_of'],'budget':budget,'terminal_roe':terminal_roe,'required_return':required_return,
            'interim_roes':policy['interim_roes'],'rows':rows,'target_exposure':target,'target_cash':1-target,
            'unreleased_budget':budget-target,'scope':policy['meaning'],
            'rule':'A/B/C/D候选单位3/2/1/0，单公司上限30%/20%/10%/0；条件价/现价达1.25/1/.75时释放100%/50%/25%，否则0。'}


def allocation_sensitivity(profiles,costs,policy,budget=None):
    result=[]
    for ke in (.08,.10,.12):
        for roe in (.20,.25,.35,.45):
            p=tier_allocation(profiles,costs,policy,budget,roe,ke)
            result.append({'required_return':ke,'terminal_roe':roe,'target_cash':p['target_cash'],
                           'weights':{r['code']:r['target_weight'] for r in p['rows']}})
    return result
