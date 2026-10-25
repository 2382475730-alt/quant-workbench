"""Check source context/signs and independently recompute displayed economic outputs."""
from decimal import Decimal
from pathlib import Path
import json,math,sys,re
from html import unescape
PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT/'src'))
from quant_workbench_app.swine_data import read,dump
ROOT=PROJECT/'runtime/research/swine_deep_20261025'
LABELS={'money_cap':'货币资金','st_borr':'短期借款','non_cur_liab_due_1y':'一年内到期的非流动负债',
        'total_liab':'负债合计','total_assets':'资产总计','total_hldr_eqy_exc_min_int':'归属于母公司',
        'total_share':'股本','n_cashflow_act':'经营活动产生的现金流量净额',
        'c_pay_acq_const_fiolta':'购建固定资产','n_income_attr_p':'归属于',
        'total_profit':'利润总额','assets_impair_loss':'资产减值'}

def main():
    failures=[];semantic=[];math_checks=[]
    for row in read(ROOT/'model/financial_checks.json')['records']:
        hits=[h for h in row['evidence'] if LABELS[row['field']] in h['context']]
        needle=f"{abs(row['value']):.2f}"
        if row['value']<0:
            hits=[h for h in hits if '-'+needle in h['context'] or '−'+needle in h['context'] or '－'+needle in h['context']]
        ok=bool(hits)
        semantic.append({'id':row['id'],'label_and_sign_consistent':ok,'evidence':hits})
        if not ok:failures.append(row['id']+' lacks matching label/sign context')
    data=read(ROOT/'model/results.json');raw=read(ROOT/'model/raw_financial_inputs.json')
    sources={s['id']:s for s in read(ROOT/'evidence/sources.json')}
    facts={f['id']:f for f in read(ROOT/'evidence/facts.json')};publications=[]
    D=lambda x:Decimal(str(x))
    for p in data['profiles']:
        balance=raw[p['code']]['half_balance']
        check={'code':p['code']}
        check['balance_equation']=abs(balance['total_assets']-balance['total_liab']-balance['total_hldr_eqy_inc_min_int'])<1
        check['restricted_cash_bridge']=abs(p['cash_gross']-p['cash_restricted']-p['cash_purpose_bound']-p['cash_available_proxy'])<.01
        v=p['valuation'];book=D(v['book_per_share']);ke=D(v['required_return']);pv=D(0)
        for t,roe in enumerate(v['interim_roes'],1):
            profit=book*D(roe);div=max(D(0),profit)*D(v['payout']);pv+=div/(1+ke)**t;book+=profit-div
        pv+=book*D(v['terminal_roe'])/ke/(1+ke)**len(v['interim_roes'])
        check['decimal_dividend_value']=math.isclose(float(pv),v['conditional_value'],rel_tol=1e-12)
        check['terminal_inverse']=math.isclose(v['pv_dividends']+float(book)*v['required_terminal_roe']/float(ke)/(1+float(ke))**len(v['interim_roes']),p['price'],rel_tol=1e-12)
        check['q2_net_profit']=math.isclose(p['earnings_bridge']['q2_net_profit'],raw[p['code']]['half_income']['n_income_attr_p']-raw[p['code']]['q1_income']['n_income_attr_p'],rel_tol=1e-12)
        for s in p['stress']:
            demand=max(D(0),(D(p['capex_cash'])-D(p['operating_cashflow']))/6)*D(s['burn_factor'])*D(s['horizon'])+D(p['short_obligations_proxy'])*(1-D(s['refinancing']))-D(p['cash_available_proxy'])
            if not math.isclose(float(max(D(0),demand)),s['new_funding_required'],abs_tol=.0001):failures.append(p['code']+' funding decimal mismatch')
        math_checks.append(check)
        failures.extend(p['code']+' '+k for k,v in check.items() if v is False)
        for key,field,period in [('half_balance','money_cap','20260630'),('q1_income','n_income_attr_p','20260331')]:
            fact=facts[f"F_{p['code'][:6]}_{period}_{field}"];source=sources[fact['source_ids'][0]];record=raw[p['code']][key]
            api=max(record.get('ann_date') or '',record.get('f_ann_date') or '')
            passed=api>=source['published_date'].replace('-','')
            publications.append({'code':p['code'],'period':period,'api_date':api,'original_date':source['published_date'],'passed':passed})
            if not passed:failures.append(p['code']+' publication date earlier than original')
    for b in data['profit_bridges']:
        profit=D(b['price'])*D(b['shares'])/D(b['normal_pe'])
        spread=(profit-D(b['other_profit_assumption']))/D(b['scenario_kg'])
        if not math.isclose(float(spread+D(b['cost_per_kg'])),b['required_selling_price'],rel_tol=1e-12):failures.append(b['code']+' profit bridge decimal mismatch')
    allocation=data['allocation']
    if abs(sum(r['target_weight'] for r in allocation['rows'])+allocation['target_cash']-1)>1e-12:failures.append('allocation sum')
    for r in allocation['rows']:
        if not 0<=r['target_weight']<=r['candidate_weight']<=r['company_cap']:failures.append(r['code']+' allocation cap')
    sources={s['id']:s for s in read(ROOT/'evidence/sources.json')}
    history=read(ROOT/'model/price_history.json');price_checks=0
    labels={'hog':'全国生猪平均价格','piglet':'全国仔猪平均价格','corn':'全国玉米(?:平均)?价格','soymeal':'全国豆粕(?:平均)?价格','feed':'育肥猪配合饲料(?:平均)?价格'}
    for row in history['rows']:
        text=re.sub(r'\s+','',unescape(re.sub('<[^>]+>',' ',(ROOT/sources[row['source']]['local_path']).read_text(encoding='utf8'))))
        for field,label in labels.items():
            values=re.findall(label+r'([\d.]+)元',text)
            if len(values)!=1 or float(values[0])!=row[field]:failures.append(row['period']+' '+field+' primary source mismatch')
            price_checks+=1
        if row['published_date']>'2026-10-25':failures.append('future price publication')
    result={'status':'passed' if not failures else 'failed','financial_context_checks':semantic,
            'independent_math_checks':math_checks,'funding_scenarios':54,'profit_bridges':3,
            'allocation_sensitivity_cases':len(data['allocation_sensitivity']),'failures':failures,
            'primary_price_checks':price_checks,'price_missing_sources':history['unresolved'],
            'publication_date_checks':publications,
            'scope':'Original amount label/sign context, balance identity, Decimal calculations, and condition consistency; not audit opinion or investment effectiveness'}
    dump(ROOT/'qa/substantive_checks.json',result)
    print(json.dumps({'status':result['status'],'financial_context_checks':len(semantic),'companies':len(math_checks),'failures':failures}))
    if failures:raise SystemExit(1)

if __name__=='__main__':main()
