"""Independent swine research inputs. No dependency on deleted pork studies."""
import json
import math
from pathlib import Path

import pandas as pd

from .paths import PROJECT

CONFIG = json.loads((PROJECT / 'config/swine_research.json').read_text(encoding='utf-8'))
ROOT = PROJECT / CONFIG['research_root']
UNIVERSE = json.loads((PROJECT / 'config/swine_universe.json').read_text(encoding='utf-8'))
AS_OF = CONFIG['as_of'].replace('-', '')


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def dump(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')


def finite(value):
    return float(value) if value is not None and math.isfinite(float(value)) else None


def latest_statement(rows, period=None):
    valid = [r for r in rows if r.get('ann_date') and r['ann_date'] <= AS_OF
             and (not r.get('f_ann_date') or r['f_ann_date'] <= AS_OF)
             and (not r.get('report_type') or str(r['report_type']) == '1')
             and (period is None or r.get('end_date') == period)]
    return max(valid, key=lambda r: (r['end_date'], r.get('f_ann_date') or r['ann_date'], str(r.get('update_flag', '')))) if valid else {}


def company_record(code):
    raw = read(ROOT / 'data' / f'{code}.json')
    income = latest_statement(raw['income'])
    period = income.get('end_date')
    balance = latest_statement(raw['balancesheet'], period)
    cashflow = latest_statement(raw['cashflow'], period)
    history_path=ROOT/'data/history'/f'{code}.json'
    history=read(history_path) if history_path.exists() else raw
    # A different pre-acquisition business is not the same pig-cycle valuation sample.
    comparable_start='20210101' if code=='603477.SH' else '20160101'
    prices = sorted({r['trade_date']:r for r in history['daily_basic']
                     if comparable_start <= r['trade_date'] <= AS_OF}.values(), key=lambda r: r['trade_date'])
    quote = prices[-1] if prices else {}
    pb_values = [r['pb'] for r in prices if r.get('pb') is not None and r['pb'] > 0]
    pb = quote.get('pb')
    group = next((g for g in ('core', 'watch', 'excluded') if code in UNIVERSE[g]), 'unclassified')
    debt_fields = ('st_borr', 'lt_borr', 'bond_payable', 'non_cur_liab_due_1y')
    debt = sum(balance.get(k) or 0 for k in debt_fields) if balance else None
    assets, liabilities = balance.get('total_assets'), balance.get('total_liab')
    parent_equity = balance.get('total_hldr_eqy_exc_min_int')
    return {'code': code, 'name': raw['name'], 'group': group, 'reason': UNIVERSE.get(group, {}).get(code, ''),
            'period': period, 'ann_date': income.get('f_ann_date') or income.get('ann_date'),
            'revenue': finite(income.get('revenue')), 'net_profit': finite(income.get('n_income_attr_p')),
            'operating_cashflow': finite(cashflow.get('n_cashflow_act')),
            'capex_cash': finite(cashflow.get('c_pay_acq_const_fiolta')),
            'cash': finite(balance.get('money_cap')), 'debt_proxy': finite(debt),
            'parent_equity': finite(parent_equity), 'total_assets': finite(assets),
            'debt_ratio': liabilities/assets if assets and liabilities is not None else None,
            'close': finite(quote.get('close')), 'quote_date': quote.get('trade_date'),
            'market_cap': (quote['total_mv'] * 10000) if quote.get('total_mv') else None,
            'pb': finite(pb), 'pe_ttm': finite(quote.get('pe_ttm')),
            'pb_percentile': sum(v <= pb for v in pb_values)/len(pb_values) if pb and pb_values else None,
            'pb_start': prices[0]['trade_date'] if prices else None, 'pb_count': len(pb_values),
            'business': raw['fina_mainbz'], 'source_path': str(ROOT / 'data' / f'{code}.json'),
            'history_scope': '巨星2020年重组，采用2021年后样本' if code=='603477.SH' else '2016年起或上市后可得样本；股本与业务结构变化仍影响可比性',
            'annual_history': annual_history(history, comparable_start)}


def annual_history(raw, start='20160101'):
    periods=sorted({r['end_date'] for r in raw['income'] if r['end_date'].endswith('1231') and r['end_date']>=start})
    output=[]
    for period in periods:
        income=latest_statement(raw['income'],period)
        cash=latest_statement(raw['cashflow'],period)
        balance=latest_statement(raw['balancesheet'],period)
        if not income:
            continue
        output.append({'year':period[:4],'revenue':finite(income.get('revenue')),
                       'net_profit':finite(income.get('n_income_attr_p')),
                       'operating_cashflow':finite(cash.get('n_cashflow_act')),
                       'parent_equity':finite(balance.get('total_hldr_eqy_exc_min_int')),
                       'ann_date':income.get('f_ann_date') or income.get('ann_date')})
    return output


def all_companies():
    codes = [code for group in ('core', 'watch', 'excluded') for code in UNIVERSE[group]]
    return [company_record(c) for c in codes if (ROOT / 'data' / f'{c}.json').exists()]


def load_market(codes=None):
    codes = codes or UNIVERSE['research_basket']
    calendar = read(ROOT / 'data/calendar.json')
    dates = pd.DatetimeIndex(sorted(pd.Timestamp(r['cal_date']) for r in calendar if r['is_open'] == 1))
    panels = {k: pd.DataFrame(index=dates) for k in ('open', 'close', 'raw_open', 'raw_close', 'volume', 'upper', 'lower', 'factor')}
    issues = []
    for code in codes:
        raw = read(ROOT / 'data' / f'{code}.json')
        daily = pd.DataFrame(raw['daily'])
        factor = pd.DataFrame(raw['adj_factor'])
        limit = pd.DataFrame(raw['stk_limit'])
        for frame in (daily, factor, limit):
            if frame.trade_date.duplicated().any():
                raise ValueError(f'{code} duplicate dates')
            frame.index = pd.to_datetime(frame.trade_date)
        daily, factor, limit = (f.reindex(dates) for f in (daily, factor, limit))
        for field in ('open', 'close'):
            panels['raw_'+field][code] = daily[field]
            panels[field][code] = daily[field] * factor.adj_factor
        panels['factor'][code] = factor.adj_factor
        panels['volume'][code] = daily.vol * 100
        panels['upper'][code] = limit.up_limit
        panels['lower'][code] = limit.down_limit
        missing = daily.close.isna() | factor.adj_factor.isna()
        if missing.any():
            issues.append({'code': code, 'missing': [str(d.date()) for d in dates[missing]]})
        for field in ('open', 'close'):
            if not daily[field].dropna().gt(0).all():
                raise ValueError(f'{code} nonpositive {field}')
        if not factor.adj_factor.dropna().gt(0).all():
            raise ValueError(f'{code} nonpositive adjustment')
    return panels, issues


def source_documents(code):
    path = ROOT / 'sources/documents/receipts.json'
    return [r for r in read(path) if r['code'] == code[:6] and r.get('path')] if path.exists() else []
