"""Discrete, long-only cash/share ledger with delayed orders and corporate actions.

Prices and limits are raw. Signals supplied to the engine are end-of-day decisions.
Cash dividends are gross of investor-specific dividend income tax (disclosed).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Costs:
    commission: float = 0.0003
    minimum: float = 5.0
    slippage: float = 0.001
    participation: float = 0.01
    multiplier: float = 1.0

    def fee(self, value, sell, date):
        stamp = (0.0005 if date >= "20230828" else 0.001) if sell else 0.0
        transfer = 0.00001 if date >= "20220429" else 0.00002
        return (max(self.minimum, self.commission * value) + (stamp + transfer) * value) * self.multiplier


@dataclass(frozen=True)
class Action:
    code: str
    record_date: str
    ex_date: str
    cash_per_share: float = 0.0
    stock_ratio: float = 0.0
    pay_date: str = ""
    list_date: str = ""
    uncertain_entitlement: bool = False
    # A shareholder-to-shareholder transfer grants shares without splitting
    # the company's per-share mark. None means the ordinary stock split ratio.
    mark_stock_ratio: float | None = None
    exchange_to: str = ""
    exchange_ratio: float = 0.0


def quantity(code, desired, sell=False, holding=0):
    desired = max(0, int(desired))
    if sell and desired >= holding:
        return int(holding)
    if code.startswith("688"):
        return desired if desired >= 200 else 0
    return desired // 100 * 100


def simulate(panels: dict[str, pd.DataFrame], decisions: dict, actions=(),
             initial_cash=1_000_000.0, costs=None, start=None, end=None,
             execution_delay=1, order_life=5):
    if execution_delay < 1:
        raise ValueError("Execution must be after decision")
    if initial_cash <= 0:
        raise ValueError("Initial cash must be positive")
    costs = costs or Costs()
    dates = panels["close"].index
    codes = panels["close"].columns.tolist()
    code_index = {c: i for i, c in enumerate(codes)}
    arrays = {k: v.reindex(index=dates, columns=codes).to_numpy(dtype=float) for k, v in panels.items()}
    # Capacity is based entirely on earlier volume, never today's final volume.
    adv = panels["volume"].rolling(20, min_periods=10).mean().shift(1).to_numpy(dtype=float)
    scheduled = {}
    for key, weights in decisions.items():
        values = list(weights.values())
        if any(not math.isfinite(v) or v < 0 for v in values) or sum(values) > 1 + 1e-9:
            raise ValueError("Invalid long-only weights")
        if any(code not in code_index for code in weights):
            raise ValueError("Unknown asset in target")
        pos = dates.get_indexer([pd.Timestamp(key)])[0]
        if pos < 0:
            raise ValueError("Decision not on trading calendar")
        if pos + execution_delay < len(dates):
            scheduled[pos + execution_delay] = (str(pd.Timestamp(key).date()), weights)
    start = pd.Timestamp(start) if start else dates[0]
    end = pd.Timestamp(end) if end else dates[-1]
    holdings = np.zeros(len(codes), dtype=np.int64)
    marks = np.full(len(codes), np.nan)
    quote_age = np.zeros(len(codes), dtype=np.int64)
    cash = float(initial_cash)
    claims, locked, entitlements, orders = [], [], {}, {}
    by_record, by_ex = {}, {}
    for aid, action in enumerate(actions):
        if action.code not in code_index:
            continue
        if action.cash_per_share < 0 or action.stock_ratio < 0 or (action.mark_stock_ratio is not None and action.mark_stock_ratio < 0):
            raise ValueError("Negative corporate action")
        if action.record_date >= action.ex_date:
            raise ValueError("Record date must precede ex date")
        if action.exchange_to and (action.exchange_ratio <= 0 or action.cash_per_share or action.stock_ratio or not action.list_date):
            raise ValueError("Invalid share exchange")
        by_record.setdefault(action.record_date, []).append((aid, action))
        by_ex.setdefault(action.ex_date, []).append((aid, action))
    nav, trades, events, positions = [], [], [], []
    cumulative_fees = cumulative_slippage = 0.0
    for day, timestamp in enumerate(dates):
        if timestamp < start or timestamp > end:
            continue
        date = timestamp.strftime("%Y%m%d")
        opening = arrays["open"][day]
        closing = arrays["close"][day]
        mark_adjustments = {}
        for aid, action in by_ex.get(date, []):
            entitled = entitlements.pop(aid, 0)
            if not entitled:
                continue
            if action.uncertain_entitlement:
                raise ValueError(f"Unresolved shareholder-specific entitlement: {action.code} {date}")
            j = code_index[action.code]
            if action.exchange_to:
                if action.exchange_to not in code_index:
                    raise ValueError(f"Missing share-exchange destination prices: {action.exchange_to}")
                if holdings[j] != entitled or any(k == j for _, k, _ in locked):
                    raise ValueError("Share exchange requires the fully retained record-date holding")
                destination = code_index[action.exchange_to]
                converted = math.floor(entitled * action.exchange_ratio + 1e-8)
                fraction = entitled * action.exchange_ratio - converted
                holdings[j] = 0
                holdings[destination] += converted
                locked.append((action.list_date, destination, converted))
                # New securities with no prior quote carry the old account
                # value as a disclosed stale reference until a quote arrives.
                if not np.isfinite(marks[destination]):
                    marks[destination] = marks[j] / action.exchange_ratio
                    quote_age[destination] = quote_age[j]
                for order_code in [j, destination]:
                    if order_code in orders:
                        orders.pop(order_code)
                        events.append({"date": date, "code": codes[order_code], "type": "order_cancelled_for_share_exchange"})
                events.append({"date": date, "code": action.code, "type": "share_exchange",
                               "destination": action.exchange_to, "old_shares": entitled,
                               "new_shares": converted, "fractional_shares_not_assumed": fraction,
                               "available_date": action.list_date})
                continue
            correction = mark_adjustments.setdefault(j, [0.0, 0.0])
            correction[0] += action.cash_per_share
            correction[1] += action.stock_ratio if action.mark_stock_ratio is None else action.mark_stock_ratio
            if action.cash_per_share:
                if not action.pay_date:
                    raise ValueError(f"Missing dividend pay date: {action.code} {date}")
                claims.append((action.pay_date, entitled * action.cash_per_share))
            bonus = math.floor(entitled * action.stock_ratio + 1e-8)
            if bonus:
                if not action.list_date:
                    raise ValueError(f"Missing bonus listing date: {action.code} {date}")
                holdings[j] += bonus
                locked.append((action.list_date, j, bonus))
            events.append({"date": date, "code": action.code, "type": "corporate_action",
                           "entitled": entitled, "gross_dividend": entitled * action.cash_per_share,
                           "bonus_shares": bonus})
        for j, (dividend, bonus_ratio) in mark_adjustments.items():
            # A suspended stock has no new quote. Adjust the carried mark for
            # distributions so adding claims/shares cannot manufacture wealth.
            if np.isfinite(marks[j]):
                marks[j] = (marks[j] - dividend) / (1 + bonus_ratio)
                if marks[j] < 0:
                    raise ValueError("Distribution exceeds carried valuation")
            if j in orders and bonus_ratio:
                orders[j][0] = int(orders[j][0] * (1 + bonus_ratio))
        cash += sum(value for due, value in claims if due <= date)
        claims = [(due, value) for due, value in claims if due > date]
        locked = [(due, j, shares) for due, j, shares in locked if due > date]
        unavailable = np.zeros(len(codes), dtype=np.int64)
        for _, j, shares in locked:
            unavailable[j] += shares
        available = holdings - unavailable
        open_marks = np.where(np.isfinite(opening), opening, marks)
        if np.any((holdings > 0) & ~np.isfinite(open_marks)):
            raise ValueError("Held asset has no valuation price")
        receivable = sum(value for _, value in claims)
        equity_open = cash + receivable + np.nansum(holdings * open_marks)
        if day in scheduled:
            decision_date, target = scheduled[day]
            if orders:
                for j, order in orders.items():
                    events.append({"date": date, "code": codes[j], "type": "superseded_order", "remaining": int(order[0])})
            orders = {}
            for j in sorted(set(np.flatnonzero(holdings)) | {code_index[c] for c in target}):
                price = open_marks[j]
                weight = target.get(codes[j], 0.0)
                if weight and not (np.isfinite(price) and price > 0):
                    events.append({"date": date, "code": codes[j], "type": "no_price_target"})
                    continue
                desired = quantity(codes[j], equity_open * weight / price) if weight else 0
                delta = desired - holdings[j]
                if delta:
                    orders[j] = [int(delta), day + order_life - 1, decision_date]
        # Sells release cash first. The code order gives reproducible allocation.
        for j in sorted(orders, key=lambda idx: (orders[idx][0] > 0, codes[idx])):
            delta, expiry, signal_date = orders[j]
            if day > expiry:
                events.append({"date": date, "code": codes[j], "type": "expired_order", "remaining": delta})
                del orders[j]
                continue
            sell = delta < 0
            price = opening[j]
            reason = None
            if not np.isfinite(price) or price <= 0:
                reason = "no_trading_quote"
            upper, lower = arrays["up_limit"][day, j], arrays["down_limit"][day, j]
            if not reason and (not np.isfinite(upper) or not np.isfinite(lower)):
                reason = "unknown_price_limits"
            if not reason and ((not sell and price >= upper - 0.005) or (sell and price <= lower + 0.005)):
                reason = "opening_at_limit"
            if not reason and (not np.isfinite(adv[day, j]) or adv[day, j] <= 0):
                reason = "insufficient_prior_liquidity"
            if reason:
                events.append({"date": date, "code": codes[j], "type": "unfilled", "reason": reason})
                continue
            fill_price = round(price * (1 - costs.slippage * costs.multiplier if sell else 1 + costs.slippage * costs.multiplier), 2)
            if fill_price < lower - 1e-8 or fill_price > upper + 1e-8:
                events.append({"date": date, "code": codes[j], "type": "unfilled", "reason": "slippage_outside_limit"})
                continue
            capacity = int(adv[day, j] * costs.participation)
            desired_fill = min(abs(delta), capacity, int(available[j]) if sell else abs(delta))
            shares = quantity(codes[j], desired_fill, sell=sell, holding=int(available[j]))
            if not sell:
                affordable = max(0, int((cash - costs.minimum * costs.multiplier) / (fill_price * (1 + (costs.commission + 0.00002) * costs.multiplier))))
                shares = min(shares, quantity(codes[j], affordable))
            if shares <= 0:
                events.append({"date": date, "code": codes[j], "type": "unfilled", "reason": "cash_lot_or_capacity"})
                continue
            notional = shares * fill_price
            fee = costs.fee(notional, sell, date)
            signed = -shares if sell else shares
            cash -= signed * fill_price + fee
            holdings[j] += signed
            if sell:
                available[j] -= shares
            cumulative_fees += fee
            slip = shares * abs(fill_price - price)
            cumulative_slippage += slip
            trades.append({"date": date, "decision_date": signal_date, "code": codes[j],
                           "shares": signed, "price": fill_price, "raw_open": price,
                           "notional": notional, "fee": fee, "slippage_cost": slip, "cash_after": cash})
            orders[j][0] -= signed
            if not orders[j][0]:
                del orders[j]
        if cash < -1e-6 or (holdings < 0).any():
            raise AssertionError("Cash/share invariant failed")
        marks = np.where(np.isfinite(closing), closing, marks)
        quote_age = np.where(np.isfinite(closing), 0, quote_age + 1)
        equity = cash + receivable + np.nansum(holdings * marks)
        stale = int(np.sum((holdings > 0) & ~np.isfinite(closing)))
        nav.append({"date": timestamp, "equity": equity, "cash": cash, "receivable": receivable,
                    "gross_exposure": (equity - cash - receivable) / equity,
                    "fees_cumulative": cumulative_fees, "slippage_cumulative": cumulative_slippage,
                    "stale_holdings": stale,
                    "stale_market_value": float(np.nansum(np.where(np.isfinite(closing), 0, holdings * marks)))})
        for j in np.flatnonzero(holdings):
            positions.append({"date": timestamp, "code": codes[j], "shares": int(holdings[j]),
                              "mark": marks[j], "weight": holdings[j] * marks[j] / equity,
                              "stale_trading_days": int(quote_age[j])})
        for aid, action in by_record.get(date, []):
            entitlements[aid] = int(holdings[code_index[action.code]])
    for j, order in orders.items():
        events.append({"date": end.strftime("%Y%m%d"), "code": codes[j], "type": "pending_at_end", "remaining": int(order[0])})
    return {"nav": pd.DataFrame(nav).set_index("date"), "trades": pd.DataFrame(trades),
            "events": pd.DataFrame(events), "positions": pd.DataFrame(positions)}
