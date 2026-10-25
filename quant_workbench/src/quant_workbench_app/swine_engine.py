"""Independent cash/position replay; unit strategies and integer execution share rules."""
from dataclasses import dataclass
import math

import numpy as np
import pandas as pd

from .swine_data import ROOT, UNIVERSE, dump, load_market, read

STRATEGIES = {'hold80': '80%等权一次建仓', 'staged80': '80%等权三批建仓',
              'risk80': '趋势减仓＋波动预算', 'hold100': '100%等权参照', 'cycle_hold':'跨周期证据分批（草案）'}


@dataclass(frozen=True)
class Costs:
    commission: float = .0003
    minimum: float = 5.0
    transfer: float = .00001
    sell_levy: float = .0005
    slippage: float = .001
    dividend_reserve: float = .2

    def validate(self):
        if any(not math.isfinite(v) or v < 0 for v in vars(self).values()):
            raise ValueError('费用参数必须为非负有限数值')
        if self.dividend_reserve > 1 or any(getattr(self,k)>=1 for k in ('commission','transfer','sell_levy','slippage')):
            raise ValueError('比例费用或分红扣留比例超出有效范围')


def dividend_events(raw, start='2026-06-01', end='2026-10-23'):
    unique = {}
    for row in raw:
        if row.get('div_proc') != '实施' or not row.get('ex_date'):
            continue
        ex = pd.Timestamp(row['ex_date'])
        if not pd.Timestamp(start) <= ex <= pd.Timestamp(end):
            continue
        key = (row['ts_code'], row['ex_date'], row.get('record_date'))
        value = {k: row.get(k) for k in ('record_date', 'ex_date', 'pay_date', 'cash_div_tax', 'stk_div', 'div_listdate')}
        if key in unique and unique[key] != value:
            raise ValueError(f'Conflicting dividend event: {key}')
        if not value['record_date'] or (value['cash_div_tax'] and not value['pay_date']):
            raise ValueError(f'Incomplete dividend event: {key}')
        if value['stk_div']:
            raise ValueError('Share distributions require explicit handling before replay')
        unique[key] = value
    return list(unique.values())


class SwineModel:
    def __init__(self, codes=None):
        self.codes = codes or UNIVERSE['research_basket']
        self.market, issues = load_market(self.codes)
        if issues:
            raise ValueError('核心行情存在缺口，不能静默填充后回放')
        self.dates = self.market['close'].index
        self.entry_dates = self.dates[self.dates >= '2026-06-01']
        self.a = {k: f.to_numpy(dtype=float) for k, f in self.market.items()}
        returns = self.market['close'].pct_change(fill_method=None)
        basket = returns.mean(axis=1)
        self.vol = basket.rolling(60, min_periods=40).std().shift(1).to_numpy() * np.sqrt(252)
        basket_nav = (1 + basket.fillna(0)).cumprod()
        self.trend = (basket_nav.shift(1) >= basket_nav.rolling(60).mean().shift(1)).to_numpy()
        self.adv = self.market['volume'].rolling(20, min_periods=10).mean().shift(1).to_numpy()
        self.events = {}
        for j, code in enumerate(self.codes):
            raw = read(ROOT / 'data' / f'{code}.json')
            self.events[j] = dividend_events(raw['dividend'])

    def run(self, start, strategy='staged80', capital=None, end=None, costs=None, details=True, policy_overrides=None):
        if strategy not in STRATEGIES:
            raise ValueError('Unknown strategy')
        start = pd.Timestamp(start)
        end = pd.Timestamp(end) if end else self.dates[-1]
        if start not in self.entry_dates or end not in self.dates or end < start:
            raise ValueError('请选择2026年6月起的有效交易日及不早于起点的终点')
        if capital is not None and (not math.isfinite(capital) or capital <= 0):
            raise ValueError('资金必须为正的有限数值')
        costs = costs or Costs()
        costs.validate()
        initial = float(capital) if capital is not None else 1.0
        integer = capital is not None
        cash = initial
        shares = np.zeros(len(self.codes))
        receivable = 0.0
        accruals, entitlements = {}, {}
        nav, positions, trades, orders, events = [], [], [], [], []
        decisions=[]
        policy=None
        if strategy=='cycle_hold':
            from .swine_cycle_policy import CyclePolicy
            if policy_overrides:
                policy=CyclePolicy(self.codes,policy_overrides)
            else:
                if not hasattr(self,'cycle_policy'):self.cycle_policy=CyclePolicy(self.codes)
                policy=self.cycle_policy
        lo, hi = self.dates.get_loc(start), self.dates.get_loc(end)
        total_fees = 0.0
        total_slippage = 0.0
        first_fill = None
        last_target = np.zeros(len(self.codes))
        for i in range(lo, hi+1):
            day = self.dates[i]
            daystr = day.strftime('%Y-%m-%d')
            offset = i-lo
            for j, company_events in self.events.items():
                for k, event in enumerate(company_events):
                    key = (j, k)
                    if day == pd.Timestamp(event['ex_date']):
                        entitled = entitlements.get(key, 0)
                        amount = entitled * (event['cash_div_tax'] or 0) * (1-costs.dividend_reserve)
                        accruals[key] = amount
                        receivable += amount
                        if amount:
                            events.append({'date': daystr, 'code': self.codes[j], 'type': 'dividend_accrued', 'net_amount': amount})
                    if event['pay_date'] and day == pd.Timestamp(event['pay_date']):
                        amount = accruals.pop(key, 0)
                        cash += amount
                        receivable -= amount
                        if amount:
                            events.append({'date':daystr,'code':self.codes[j],'type':'dividend_paid','net_amount':amount})
            rebalance = offset == 0 or (strategy == 'staged80' and offset in (10, 20)) or (strategy == 'risk80' and offset % 20 == 0) or (strategy=='cycle_hold' and offset % policy.config['review_sessions']==0)
            if rebalance:
                exposure = 1.0 if strategy == 'hold100' else .8
                if strategy == 'staged80':
                    exposure = .4 if offset == 0 else (.6 if offset == 10 else .8)
                if strategy == 'risk80':
                    exposure = min(.8, .12/max(.01, self.vol[i])) if np.isfinite(self.vol[i]) else .4
                    if not self.trend[i]:
                        exposure = min(exposure, .4)
                equity_reference = cash + receivable + float(shares @ self.a['raw_close'][i-1])
                if strategy=='cycle_hold':
                    last_target,records=policy.targets(self.dates[i-1],offset,last_target)
                    decisions.extend({'decision_date':daystr,**r} for r in records)
                else:
                    last_target = np.full(len(self.codes), exposure/len(self.codes))
                desired = equity_reference*last_target / self.a['raw_close'][i-1]
                if integer:
                    desired = np.floor(desired/100) * 100
                if policy:
                    for j,record in enumerate(records):
                        if record['execution_permission']=='hold':desired[j]=shares[j]
                differences = desired-shares
                # Sells precede buys. Same-day purchases are never sold on this schedule.
                for j in sorted(range(len(shares)), key=lambda n: differences[n]):
                    delta = differences[j]
                    if abs(delta) < (1 if integer else 1e-12):
                        continue
                    buying = delta > 0
                    op = self.a['raw_open'][i, j]
                    blocked = not np.isfinite(self.a['volume'][i,j]) or self.a['volume'][i, j] <= 0 or not np.isfinite(op)
                    blocked = blocked or (integer and (not np.isfinite(self.adv[i,j]) or self.adv[i,j]<=0))
                    bound = self.a['upper' if buying else 'lower'][i, j]
                    blocked = blocked or not np.isfinite(bound) or (op >= bound-.005 if buying else op <= bound+.005)
                    row = {'date': daystr, 'code': self.codes[j], 'requested_shares': float(delta), 'status': 'blocked' if blocked else 'filled'}
                    if blocked:
                        orders.append(row)
                        continue
                    price = op*(1+costs.slippage if buying else 1-costs.slippage)
                    price = min(price, self.a['upper'][i,j]) if buying else max(price, self.a['lower'][i,j])
                    if integer:
                        quantity = min(abs(delta), math.floor(self.adv[i,j]*.01/100)*100)
                    else:
                        quantity = abs(delta)
                    quantity = min(quantity, shares[j]) if not buying else quantity
                    def fee(q):
                        gross = q*price
                        return max(costs.minimum if integer else 0, gross*costs.commission) + gross*(costs.transfer + (0 if buying else costs.sell_levy))
                    if buying:
                        available = max(0, cash-initial*.0)
                        if integer:
                            while quantity and quantity*price+fee(quantity) > available+1e-9:
                                quantity -= 100
                        else:
                            quantity = min(quantity, available/(price*(1+costs.commission+costs.transfer)))
                    if quantity <= (0 if integer else 1e-14):
                        row['status'] = 'cash_or_capacity'
                        orders.append(row)
                        continue
                    charges = fee(quantity)
                    signed = quantity if buying else -quantity
                    cash -= signed*price + charges
                    shares[j] += signed
                    total_fees += charges
                    slip = quantity*abs(price-op)
                    total_slippage += slip
                    first_fill = first_fill or daystr
                    row.update({'filled_shares': signed, 'status': 'filled' if abs(signed-delta)<1e-8 else 'partial'})
                    orders.append(row)
                    trades.append({'date': daystr, 'code': self.codes[j], 'shares': signed, 'price': price,
                                   'gross': signed*price, 'fees': charges, 'slippage_cost': slip, 'cash_after': cash})
            values = shares*self.a['raw_close'][i]
            equity = cash + receivable + float(values.sum())
            if cash < -max(1e-8, initial*1e-10) or (shares < -1e-8).any() or equity <= 0:
                raise AssertionError('Invalid account state')
            nav.append({'date': daystr, 'equity': equity, 'nav': equity/initial, 'cash': cash,
                        'receivable': receivable, 'market_value': float(values.sum()),
                        'exposure': float(values.sum())/equity, 'fees_cumulative': total_fees})
            if details:
                positions.extend({'date': daystr, 'code': code, 'shares': float(shares[j]),
                                  'close': self.a['raw_close'][i,j], 'market_value': float(values[j]),
                                  'weight': float(values[j])/equity, 'target_weight': float(last_target[j])}
                                 for j, code in enumerate(self.codes))
            for j, company_events in self.events.items():
                for k, event in enumerate(company_events):
                    if day == pd.Timestamp(event['record_date']):
                        entitlements[(j,k)] = float(shares[j])
        wealth = np.array([1.0] + [r['nav'] for r in nav])
        summary = {'start': start.strftime('%Y-%m-%d'), 'end': end.strftime('%Y-%m-%d'),
                   'strategy': strategy, 'mode': 'integer' if integer else 'unit', 'initial': initial,
                   'sessions': len(nav), 'return': wealth[-1]-1,
                   'max_drawdown': float(np.min(wealth/np.maximum.accumulate(wealth)-1)),
                   'ending_equity': nav[-1]['equity'], 'ending_cash': cash, 'fees': total_fees,
                   'slippage': total_slippage, 'first_fill': first_fill, 'trade_count': len(trades),
                   'blocked_orders': sum(r['status'] != 'filled' for r in orders),
                   'mean_exposure': float(np.mean([r['exposure'] for r in nav])),
                   'costs': vars(costs), 'codes': self.codes}
        if policy:summary['policy']=policy.config
        return {'summary': summary, 'nav': nav, 'positions': positions, 'trades': trades, 'orders': orders, 'events': events,'decisions':decisions}


def capital_plan(capital, prices, weights, costs=None, volumes=None):
    costs = costs or Costs()
    costs.validate()
    if not math.isfinite(capital) or capital <= 0 or not prices or set(prices) != set(weights):
        raise ValueError('资金、价格与权重不完整')
    if any(not math.isfinite(p) or p <= 0 for p in prices.values()) or any(not math.isfinite(w) or w < 0 for w in weights.values()) or sum(weights.values()) > 1+1e-10:
        raise ValueError('价格须为正，权重须非负且合计不超过100%')
    if volumes is not None and (set(volumes)!=set(prices) or any(not math.isfinite(v) or v<0 for v in volumes.values())):
        raise ValueError('容量数据必须完整且为非负有限数值')
    cash, rows = capital, []
    minimum_capitals=[];capacity_days=[]
    for code in sorted(prices):
        price = prices[code]*(1+costs.slippage)
        budget = capital*weights[code]
        q = math.floor(budget/price/100)*100
        target_lots=q
        one_lot_fee=max(costs.minimum,100*price*costs.commission)+100*price*costs.transfer
        if weights[code]>0:minimum_capitals.append((100*price+one_lot_fee)/weights[code])
        days=None
        if volumes:
            daily_capacity=math.floor(volumes[code]*.01/100)*100
            q = min(q,daily_capacity)
            days=math.ceil(target_lots/daily_capacity) if daily_capacity else (None if target_lots else 0)
            if days is not None:capacity_days.append(days)
        def fee(qty):
            return max(costs.minimum, qty*price*costs.commission) + qty*price*costs.transfer if qty else 0
        while q and q*price+fee(q) > min(budget, cash)+1e-9:
            q -= 100
        charge = fee(q)
        cash -= q*price+charge
        rows.append({'code': code, 'reference_price': prices[code], 'execution_assumption': price,
                     'target_weight': weights[code], 'shares': q, 'value': q*prices[code], 'fees': charge,
                     'actual_weight': q*prices[code]/capital, 'weight_gap': q*prices[code]/capital-weights[code],
                     'capacity_days_proxy':days,'capacity_limited':bool(volumes and q<target_lots and daily_capacity<target_lots)})
    return {'capital': capital, 'cash': cash, 'cash_weight': cash/capital, 'rows': rows,
            'target_cash_weight':1-sum(weights.values()),'implementation_cash_gap':cash/capital-(1-sum(weights.values())),
            'minimum_capital_for_one_lot_each':max(minimum_capitals,default=0),'capacity_days_proxy':max(capacity_days,default=0),
            'capacity_limited_names':[r['code'] for r in rows if r['capacity_limited']],
            'fees': sum(r['fees'] for r in rows), 'max_weight_gap': max(abs(r['weight_gap']) for r in rows),
            'omitted_names': [r['code'] for r in rows if r['target_weight'] and not r['shares']],
            'warning': '静态比例映射，未输入既有持仓；不是当前建仓或调仓信号。容量天数假定均量及价格不变，未检查次日停牌涨跌停。'}


def export_run(result, destination, overwrite=False):
    destination.mkdir(parents=True, exist_ok=overwrite)
    dump(destination / 'summary.json', result['summary'])
    for key in ('nav', 'positions', 'trades', 'orders', 'events','decisions'):
        pd.DataFrame(result[key]).to_csv(destination / f'{key}.csv', index=False, encoding='utf-8-sig')
    dump(destination / 'methodology.json', {
        'selection': '2026-10-25当前公司池历史回放，有回看偏差；未做历史成分选股',
        'execution': '前一交易日收盘定目标，当日开盘加滑点；涨跌停/无量不成交；失败订单等下一次计划再评估',
        'unit': '单位策略允许碎股、比例佣金、不计最低佣金；用于研究，不代表可交易账户',
        'integer': '整数账户100股单位，最低佣金、前20日成交量1%容量；现金不足不加杠杆',
        'dividends': '去重后登记日持股确权，除息应收、派息现金；按20%保守扣留，不声称复现实际差别税结算',
        'end': '期末按收盘持仓估值，未强制清仓，不含清仓费用',
        'risk': '12%年化波动预算是研究参数，不是最大亏损保证；未优化或证明有效'})
