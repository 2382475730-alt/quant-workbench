"""Small-account ETF ledger: integer orders, explicit flows/fees/receivables."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .allocator import Budget, Costs, allocate, risk
from .data import CODES


def simulate(market, start, end, strategy, initial=100000, scenario="base", annual_fee=0,
             monthly_contribution=0, budget=None, costs=None):
    b = budget or Budget()
    costs = costs or Costs(multiplier=2 if scenario == "double_cost" else 1)
    dates = market.dates
    active = dates[(dates >= pd.Timestamp(start)) & (dates <= pd.Timestamp(end))]
    if not len(active) or dates.get_loc(active[0]) < 1:
        raise ValueError("Require prior signal date and nonempty period")
    if initial <= 0 or annual_fee < 0 or monthly_contribution < 0:
        raise ValueError("Invalid funding")
    arrays = {k: f.to_numpy(float) for k, f in market.panels.items()}
    held = np.zeros(2, dtype=int)
    cash, payable, fees, slippage, service_paid, service_accrued = float(initial), 0., 0., 0., 0., 0.
    cumulative_flow, twr_equity, previous_equity = 0., float(initial), float(initial)
    ever_invested = False
    orders, scheduled, claims, entitlements = {}, {}, [], {}
    by_record, by_ex = {}, {}
    for j, c in enumerate(CODES):
        for row in market.dividends[c].itertuples():
            key = (c, row.ex_date)
            by_record.setdefault(pd.Timestamp(row.record_date), []).append((key, j))
            by_ex.setdefault(pd.Timestamp(row.ex_date), []).append((key, j, float(row.div_cash), pd.Timestamp(row.pay_date)))
    nav, positions, trades, events, audit, order_log, cash_log = [], [], [], [], [], [], []
    delay = 3 if scenario == "delay_2" else 1
    next_fee = active[0]
    sequence = 0

    def decide(date, equity, receivable):
        nonlocal sequence
        sequence += 1
        i = dates.get_loc(date)
        fraction = min(1, sequence/3) if scenario == "staged" else 1
        result = allocate(arrays["close"][i], held, cash, receivable, market.covariance.get(date),
                          strategy, ever_invested and not (strategy == "single" and scenario == "staged" and sequence <= 3),
                          costs, b, fraction, payable)
        result.update({"date": str(date.date()), "sequence": sequence, "fraction": fraction})
        if scenario == "miss_fourth" and sequence % 4 == 0:
            result["status"] = "investor_missed_plan"
            result["trade"] = False
        audit.append(result)
        if result["trade"]:
            scheduled[i+delay] = (date, np.array(result["shares"], int), sequence)

    initial_signal = dates[dates.get_loc(active[0])-1]
    # Reserve known first-year service charge before constructing first plan.
    # Charge itself still occurs on first active day and remains a return expense.
    cash -= annual_fee
    if cash < 0:
        raise ValueError("Initial funding cannot cover first service charge")
    decide(initial_signal, initial-annual_fee, 0)
    cash += annual_fee
    for date in active:
        i = dates.get_loc(date)
        open_px, close_px = arrays["open"][i], arrays["close"][i]
        if not np.isfinite(close_px).all():
            raise ValueError("Missing ETF valuation: do not silently forward-fill")
        if date == pd.Timestamp("2022-08-29"):
            old = int(held[1])
            held[1] = int(np.ceil(old*1.14539-1e-10))
            cash_log.append({"date": str(date.date()), "type": "split_shares", "amount": 0.,
                             "code": CODES[1], "old_shares": old, "new_shares": int(held[1]),
                             "ratio": 1.14539, "rounding": "ceil per issuer notice"})
            if 1 in orders:
                events.append({"date": str(date.date()), "code": CODES[1], "type": "split_cancel_order"})
                orders.pop(1)
            if i in scheduled:
                scheduled.pop(i)
                events.append({"date": str(date.date()), "code": CODES[1], "type": "split_cancel_stale_target"})
        flow = 0.
        if monthly_contribution and (date == active[0] or date.month != dates[i-1].month):
            flow = float(monthly_contribution)
            cash += flow
            cumulative_flow += flow
            cash_log.append({"date": str(date.date()), "type": "external_contribution", "amount": flow})
        if date >= next_fee:
            payable += annual_fee
            service_accrued += annual_fee
            cash_log.append({"date": str(date.date()), "type": "service_fee_accrual", "amount": -annual_fee})
            next_fee = next_fee + pd.DateOffset(years=1)
        for key, j, amount, pay_date in by_ex.get(date, []):
            value = entitlements.pop(key, 0)*amount
            if value:
                claims.append((pay_date, value))
                cash_log.append({"date": str(date.date()), "type": "dividend_receivable", "amount": value, "code": CODES[j]})
        paid = sum(value for due, value in claims if due <= date)
        if paid:
            cash += paid
            cash_log.append({"date": str(date.date()), "type": "dividend_paid", "amount": paid})
        claims = [(due, value) for due, value in claims if due > date]
        receivable = sum(value for _, value in claims)
        payment = min(cash, payable)
        cash -= payment
        payable -= payment
        service_paid += payment
        if payment:
            cash_log.append({"date": str(date.date()), "type": "service_fee_paid", "amount": -payment})
        available = held.copy()  # T+1: today's purchases never join this vector.
        if i in scheduled:
            signal, target, seq = scheduled.pop(i)
            for j, order in orders.items():
                events.append({"date": str(date.date()), "code": CODES[j], "type": "superseded", "remaining": order["delta"]})
            orders = {}
            for j, delta in enumerate(target-held):
                if delta:
                    oid = f"{seq}:{CODES[j]}"
                    order = {"delta": int(delta), "expires": i+4, "signal": signal, "id": oid, "submitted": date}
                    orders[j] = order
                    order_log.append({"id": oid, "code": CODES[j], "signal_date": str(signal.date()),
                                      "order_date": str(date.date()), "requested_shares": int(delta), "reference_target": int(target[j])})
        for j in sorted(orders, key=lambda k: (orders[k]["delta"] > 0, k)):
            order = orders[j]
            if i > order["expires"]:
                events.append({"date": str(date.date()), "code": CODES[j], "type": "expired", "remaining": order["delta"], "id": order["id"]})
                del orders[j]
                continue
            sell, px = order["delta"] < 0, open_px[j]
            reason = None
            upper, lower, adv = arrays["upper"][i, j], arrays["lower"][i, j], arrays["adv"][i, j]
            if not np.isfinite([px, upper, lower, adv]).all() or px <= 0 or adv <= 0:
                reason = "no_quote_limits_or_prior_liquidity"
            elif (sell and px <= lower+.0005) or (not sell and px >= upper-.0005):
                reason = "opening_at_limit"
            elif not sell and payable > 0:
                reason = "unpaid_service_fee_no_new_risk"
            if reason:
                events.append({"date": str(date.date()), "code": CODES[j], "type": "unfilled", "reason": reason, "id": order["id"]})
                continue
            fill_price = round(px*(1+(-1 if sell else 1)*costs.slippage*costs.multiplier), 3)
            if not lower <= fill_price <= upper:
                events.append({"date": str(date.date()), "code": CODES[j], "type": "unfilled", "reason": "slippage_outside_limits", "id": order["id"]})
                continue
            desired = abs(order["delta"])
            if scenario == "partial":
                desired = desired//200*100  # once only; unfilled half explicitly cancelled below
            quantity = min(desired, int(adv*.01)//100*100)
            if sell:
                quantity = min(quantity, int(available[j]))
            else:
                affordable = max(0, int((cash-costs.minimum*costs.multiplier)/(fill_price*(1+costs.commission*costs.multiplier))))//100*100
                quantity = min(quantity, affordable)
            if quantity:
                notional = quantity*fill_price
                fee = float(costs.fees([notional])[0])
                signed = -quantity if sell else quantity
                cash -= signed*fill_price+fee
                held[j] += signed
                if sell:
                    available[j] -= quantity
                fees += fee
                slip = quantity*abs(fill_price-px)
                slippage += slip
                order["delta"] -= signed
                trades.append({"date": str(date.date()), "decision_date": str(order["signal"].date()),
                               "order_date": str(order["submitted"].date()), "code": CODES[j], "shares": signed,
                               "price": fill_price, "raw_open": px, "notional": notional, "fee": fee,
                               "slippage_cost": slip, "cash_after": cash, "id": order["id"]})
            else:
                events.append({"date": str(date.date()), "code": CODES[j], "type": "unfilled", "reason": "cash_lot_capacity", "id": order["id"]})
            if scenario == "partial" and order["delta"]:
                events.append({"date": str(date.date()), "code": CODES[j], "type": "partial_cancel", "remaining": order["delta"], "id": order["id"]})
                del orders[j]
            elif not order["delta"]:
                del orders[j]
        ever_invested |= bool((held > 0).any())
        equity = cash+held@close_px+receivable-payable
        if cash < -1e-7 or (held < 0).any() or equity <= 0:
            raise AssertionError("Ledger invariant")
        daily_return = equity/(previous_equity+flow)-1
        twr_equity *= 1+daily_return
        previous_equity = equity
        weights = held*close_px/equity
        vol = risk(weights, market.covariance[date]) if date in market.covariance else None
        nav.append({"date": date, "equity": equity, "cash": cash, "receivable": receivable, "payable": payable,
                    "gross_exposure": weights.sum(), "fees_cumulative": fees, "slippage_cumulative": slippage,
                    "service_paid": service_paid, "service_accrued": service_accrued, "external_flow": flow,
                    "external_flow_cumulative": cumulative_flow, "twr_equity": twr_equity,
                    "predicted_vol": vol, "risk_breach": bool(strategy in {"risk", "band"} and vol is not None and vol*b.estimation_multiplier > b.volatility+1e-8),
                    "exposure_breach": bool(strategy in {"risk", "band"} and weights.sum() > b.max_equity+1e-8),
                    "stale_holdings": 0, "max_fund_weight": weights.max(), "fund_hhi": (weights**2).sum()})
        for j, c in enumerate(CODES):
            if held[j]:
                positions.append({"date": date, "code": c, "shares": int(held[j]), "mark": close_px[j], "weight": weights[j]})
        for key, j in by_record.get(date, []):
            entitlements[key] = int(held[j])
        if i+1 < len(dates) and date.to_period("M") != dates[i+1].to_period("M"):
            decide(date, equity, receivable)
    for j, order in orders.items():
        events.append({"date": str(active[-1].date()), "code": CODES[j], "type": "pending_at_end", "remaining": order["delta"], "id": order["id"]})
    return {"nav": pd.DataFrame(nav).set_index("date"), "positions": pd.DataFrame(positions, columns=["date", "code", "shares", "mark", "weight"]),
            "trades": pd.DataFrame(trades, columns=["date", "decision_date", "order_date", "code", "shares", "price", "raw_open", "notional", "fee", "slippage_cost", "cash_after", "id"]),
            "events": pd.DataFrame(events), "orders": pd.DataFrame(order_log), "cash_ledger": pd.DataFrame(cash_log), "audit": audit}
