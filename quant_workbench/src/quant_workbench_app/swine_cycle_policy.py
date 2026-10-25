"""Announcement-aware cross-cycle allocation rules with decision evidence."""
import numpy as np
import pandas as pd
from .paths import PROJECT
from .swine_data import ROOT,read

def available_statement(rows,date,period=None):
    valid=[r for r in rows if r.get('ann_date') and r['ann_date']<=date
           and (not r.get('f_ann_date') or r['f_ann_date']<=date)
           and str(r.get('report_type') or '1')=='1' and (period is None or r.get('end_date')==period)]
    return max(valid,key=lambda r:(r['end_date'],r.get('f_ann_date') or r['ann_date'],str(r.get('update_flag','')))) if valid else None

class CyclePolicy:
    def __init__(self,codes,overrides=None):
        self.codes=codes
        self.config={**read(PROJECT/'config/swine_cycle_policy.json'),**(overrides or {})}
        c=self.config
        if not isinstance(c['review_sessions'],int) or c['review_sessions']<1:
            raise ValueError('复核间隔必须为正整数交易日')
        if len(c['planned_exposure'])!=3 or any(not np.isfinite(v) or not 0<=v<=1 for v in c['planned_exposure']) or sorted(c['planned_exposure'])!=c['planned_exposure']:
            raise ValueError('三阶段目标必须在0至1之间并递增')
        for key in ('entry_pb_percentile','add_pb_percentile','harvest_pb_percentile','funding_watch_debt_ratio','funding_watch_cash_coverage','funding_exit_debt_ratio','funding_exit_cash_coverage'):
            if not np.isfinite(c[key]) or not 0<=c[key]<=1:raise ValueError('策略比例参数须在0至1之间')
        if not 0<c['pb_lookback_years']<=10 or not isinstance(c['minimum_pb_observations'],int) or c['minimum_pb_observations']<1:
            raise ValueError('历史窗口参数无效')
        self.raw={c:read(ROOT/'data'/f'{c}.json') for c in codes}
        self.pb={}
        for c in codes:
            p=ROOT/'data/history'/f'{c}.json'
            source=read(p) if p.exists() else self.raw[c]
            f=pd.DataFrame(source['daily_basic']).drop_duplicates('trade_date').sort_values('trade_date')
            f.index=pd.to_datetime(f.trade_date)
            self.pb[c]=f
        self.capacity=read(PROJECT/'runtime/research/swine_deep_20261025/model/results.json')['capacity']

    def targets(self,previous_date,offset,previous_targets):
        date=pd.Timestamp(previous_date);stamp=date.strftime('%Y%m%d')
        known=[r for r in self.capacity if r['published']<=date.strftime('%Y-%m-%d')]
        latest=known[-1] if known else None
        contraction=bool(latest and latest['sow_yoy']<0)
        planned=self.config['planned_exposure'][min(offset//self.config['review_sessions'],2)]/len(self.codes)
        anchor=self.config['planned_exposure'][0]/len(self.codes)
        result=[];decisions=[]
        for j,code in enumerate(self.codes):
            raw=self.raw[code];balance=available_statement(raw['balancesheet'],stamp)
            previous=float(previous_targets[j]);target=previous;reason='保留已有目标，不新增'
            record={'code':code,'information_date':date.strftime('%Y-%m-%d'),'previous_target':previous,
                    'capacity_publication':latest['published'] if latest else None,'sow_yoy':latest['sow_yoy'] if latest else None}
            if balance is None:
                target=previous;reason='缺少当时已披露财报，停止新增'
            else:
                period=balance['end_date'];cashflow=available_statement(raw['cashflow'],stamp,period);income=available_statement(raw['income'],stamp,period)
                debt=balance.get('total_liab');assets=balance.get('total_assets');cash=balance.get('money_cap')
                short=balance.get('st_borr');current=balance.get('non_cur_liab_due_1y')
                if None in (debt,assets,cash,short,current) or assets<=0 or cashflow is None or income is None:
                    reason='关键资金或同期财报缺项，停止新增'
                else:
                    denominator=short+current
                    coverage=cash/denominator if denominator>0 else float('inf')
                    ratio=debt/assets;ocf=cashflow.get('n_cashflow_act');profit=income.get('n_income_attr_p')
                    f=self.pb[code].loc[date-pd.DateOffset(years=self.config['pb_lookback_years']):date]
                    f=f[f.pb.notna() & (f.pb>0)]
                    percentile=float((f.pb<=f.iloc[-1].pb).mean()) if len(f)>=self.config['minimum_pb_observations'] else None
                    record.update(period=period,financial_publication=max(x.get('f_ann_date') or x['ann_date'] for x in [balance,cashflow,income]),
                                  debt_ratio=ratio,cash_coverage=coverage if np.isfinite(coverage) else None,operating_cashflow=ocf,net_profit=profit,
                                  pb_percentile=percentile,pb_observations=len(f),pb_observation_date=f.iloc[-1].trade_date if len(f) else None)
                    if len(f) and (date-f.index[-1]).days>7:
                        reason='估值观察已过期，停止新增'
                    elif ocf is None or profit is None or percentile is None:
                        reason='利润、现金流或估值窗口不足，停止新增'
                    elif ratio>=self.config['funding_exit_debt_ratio'] and coverage<self.config['funding_exit_cash_coverage'] and ocf<0:
                        target=0.;reason='高杠杆、低现金覆盖且经营净流出同时成立，退出研究目标'
                    elif previous>0 and profit>0 and percentile>=self.config['harvest_pb_percentile']:
                        target=previous*.5;reason='报告期转为盈利且PB高分位，分次兑现'
                    elif ratio>=self.config['funding_watch_debt_ratio'] or coverage<self.config['funding_watch_cash_coverage']:
                        reason='融资依赖偏高，保留已有目标并冻结新增'
                    elif contraction and percentile<=self.config['add_pb_percentile']:
                        target=max(previous,planned);reason='产能收缩且PB低于加仓门槛，向阶段目标再平衡'
                    elif previous==0 and contraction and percentile<=self.config['entry_pb_percentile']:
                        target=anchor;reason='产能收缩、估值未高企，建立观察仓'
            permission='rebalance' if any(w in reason for w in ('退出研究目标','分次兑现','向阶段目标再平衡','建立观察仓')) else 'hold'
            result.append(target);decisions.append({**record,'target':target,'reason':reason,'execution_permission':permission})
        return np.asarray(result),decisions
