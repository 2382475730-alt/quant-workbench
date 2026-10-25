"""Read saved ledgers for display without recalculating or changing strategies."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from .data import ROOT

REASONS = {"no_trading_quote": "无可交易报价", "unknown_price_limits": "涨跌停价格未知",
           "opening_at_limit": "开盘触及方向涨跌停", "insufficient_prior_liquidity": "历史成交量不足",
           "slippage_outside_limit": "模拟成交价越过涨跌停", "cash_lot_or_capacity": "现金/交易单位/容量限制"}
EVENTS = {"unfilled": "未成交", "expired_order": "订单过期", "superseded_order": "被新指令替换",
          "no_price_target": "目标缺报价", "corporate_action": "分红/股本变动", "share_exchange": "换股",
          "pending_at_end": "期末待执行"}


def load_ledger(phase, experiment):
    # Values come from known local summaries, never an arbitrary filesystem path.
    root = ROOT / "artifacts/research"
    folder = (root / phase / experiment).resolve()
    if not folder.is_relative_to(root.resolve()):
        raise ValueError("Ledger path outside research")
    frames = {name: pd.read_parquet(folder / f"{name}.parquet") for name in ["nav", "positions", "trades", "events"]}
    frames["decisions"] = json.loads((folder / "decisions.json").read_text(encoding="utf-8"))
    return frames


def snapshot(ledger, asof, names=None, prices=None):
    date = pd.Timestamp(asof)
    nav = ledger["nav"]
    if date not in nav.index:
        raise ValueError("Choose an actual ledger valuation date")
    account = nav.loc[date]
    known = [d for d in ledger["decisions"] if pd.Timestamp(d["date"]) <= date]
    decision = max(known, key=lambda d: pd.Timestamp(d["date"])) if known else None
    target = decision["weights"] if decision else {}
    positions = ledger["positions"]
    held = positions.loc[pd.to_datetime(positions.date).eq(date)].set_index("code") if len(positions) else pd.DataFrame()
    rows = []
    for code in sorted(set(held.index) | set(target)):
        actual = held.loc[code] if code in held.index else None
        shares = int(actual.shares) if actual is not None else 0
        mark = float(actual.mark) if actual is not None else (float(prices.get(code, np.nan)) if prices is not None else np.nan)
        value = shares * mark if shares else 0.0
        weight = value / float(account.equity)
        target_weight = float(target.get(code, 0)) if decision else None
        stale = int(actual.stale_trading_days) if actual is not None else 0
        status = "持有" if shares else "目标内未持有"
        if shares and decision and code not in target:
            status = "目标外残留持仓"
        if stale:
            status += f" / {stale}日无报价"
        rows.append({"code": code, "name": (names or {}).get(code, code), "shares": shares,
                     "mark": mark if np.isfinite(mark) else None, "market_value": value,
                     "actual_weight": weight, "target_weight": target_weight,
                     "gap_pp": (weight - target_weight) * 100 if target_weight is not None else None,
                     "status": status})
    rows.sort(key=lambda r: (-r["market_value"], r["code"]))
    market_value = sum(r["market_value"] for r in rows)
    if not np.isclose(market_value + account.cash + account.receivable, account.equity, atol=.01, rtol=1e-10):
        raise ValueError("Holdings + cash + receivables do not reconcile to ledger equity")
    trades = ledger["trades"]
    events = ledger["events"]
    for name, frame in [("trades", trades), ("events", events)]:
        if len(frame):
            dates = pd.to_datetime(frame.date.astype(str))
            filtered = frame.loc[dates.le(date)].copy()
            filtered["date"] = dates.loc[filtered.index].dt.strftime("%Y-%m-%d")
            filtered = filtered.sort_values("date", kind="stable")
        else:
            filtered = frame.copy()
        if name == "trades":
            trades = filtered
        else:
            events = filtered
    return {"asof": str(date.date()), "decision_date": decision["date"] if decision else None,
            "equity": float(account.equity), "cash": float(account.cash), "receivable": float(account.receivable),
            "market_value": market_value, "stock_weight": market_value / account.equity,
            "cash_weight": float(account.cash / account.equity), "held_count": sum(r["shares"] > 0 for r in rows),
            "target_count": len(target), "rows": rows, "trades": trades, "events": events}


def export_snapshot(view, phase, experiment):
    folder = ROOT / "artifacts/holding_views" / phase / experiment / view["asof"]
    folder.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(view["rows"]).to_csv(folder / "holdings.csv", index=False, encoding="utf-8-sig")
    for key in ["trades", "events"]:
        view[key].to_csv(folder / f"{key}.csv", index=False, encoding="utf-8-sig")
    metadata = {k: v for k, v in view.items() if k not in {"rows", "trades", "events"}}
    metadata.update({"phase": phase, "experiment": experiment,
                     "boundary": "Saved simulated ledger, not broker holdings. Target gap is descriptive, not an immediate order. Prices may be stale; securities availability is not inferred."})
    (folder / "account.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return folder
