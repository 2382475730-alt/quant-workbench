"""Connect source exceptions to actual holdings, without deleting problem stocks."""
from __future__ import annotations

import pandas as pd

from .signals import historical_members, momentum_scores


def momentum_input_quality(panels, membership, spec, decisions, quality):
    """Inspect all rankable candidates, not only stocks ultimately selected."""
    if spec["kind"] != "momentum":
        return {"unresolved_candidate_windows": [], "scope": "No price-return ranking in equal-weight baseline"}
    prices = panels["adjusted_close"]
    scores = momentum_scores(prices, spec["lookback"], spec["skip"])
    liquidity = panels["amount"].rolling(20, min_periods=15).mean()
    relevant = [i for i in quality["issues"] if i["severity"] in {"critical", "high"}
                and i["type"] in {"unexplained_factor_change", "action_factor_mismatch"}]
    affected = []
    for date, target in decisions.items():
        pos = prices.index.get_loc(date)
        if pos < spec["lookback"]:
            continue
        before, after = prices.index[pos - spec["lookback"]], prices.index[pos - spec["skip"]]
        pool = set(historical_members(membership, date))
        for issue in relevant:
            code = issue["code"]
            if code not in pool or code not in prices:
                continue
            if pd.isna(prices.at[date, code]) or pd.isna(scores.at[date, code]) or not liquidity.at[date, code] >= 10_000_000:
                continue
            for event in issue.get("dates") or [issue.get("date")]:
                if event and before < pd.Timestamp(event) <= after:
                    affected.append({"decision_date": str(date.date()), "code": code, "event": event,
                                     "issue": issue["type"], "selected": code in target})
    return {"unresolved_candidate_windows": affected,
            "scope": "Unresolved factor events crossing momentum endpoints for every liquid historical-pool candidate; does not prove source vintages."}


def holding_quality(result, quality):
    positions = result["positions"]
    nav = result["nav"]
    affected, reviewed, pending = [], [], []
    if not positions.empty:
        weights = positions.pivot(index="date", columns="code", values="weight").reindex(nav.index).fillna(0)
        for issue in quality["issues"]:
            accepted = issue.get("review", {}).get("status") == "accepted"
            if (issue["severity"] not in {"critical", "high"} and not accepted) or issue["code"] not in weights:
                continue
            events = issue.get("dates") or [issue.get("date", issue.get("ex_date"))]
            for event in events:
                if not event:
                    continue
                date = pd.Timestamp(event)
                if not nav.index[0] <= date <= nav.index[-1]:
                    continue
                previous = weights.index[weights.index < date]
                weight = float(weights.loc[previous[-1], issue["code"]]) if len(previous) else 0
                if weight > 0:
                    target = reviewed if accepted else affected
                    target.append({"code": issue["code"], "date": str(date.date()), "issue": issue["type"],
                                   "previous_close_weight": weight,
                                   **({"classification": issue["review"]["classification"],
                                       "source": issue["review"]["source"]} if accepted else {})})
        stale = positions.loc[positions.stale_trading_days.gt(20)]
        stale_max = float(stale.groupby("date").weight.sum().max()) if len(stale) else 0.0
        end_positions = positions.loc[positions.date.eq(nav.index[-1])]
        stale_end = end_positions.loc[end_positions.stale_trading_days.gt(20)]
        terminal_at_risk = float((stale_end.shares * stale_end.mark).sum())
        for item in quality.get("pending_security_conversions", []):
            retained = end_positions.loc[end_positions.code.eq(item["code"])]
            if len(retained):
                row = retained.iloc[0]
                pending.append({**item, "old_shares": int(row.shares), "stale_marked_value": float(row.shares * row.mark),
                                "expected_destination_shares_before_rounding": float(row.shares * item["exchange_ratio"]),
                                "terminal_weight": float(row.weight)})
    else:
        stale_max = terminal_at_risk = 0.0
    return {"unresolved_events_held": affected, "reviewed_events_held": reviewed, "pending_conversion_holdings": pending,
            "long_stale_max_weight": stale_max,
            "long_stale_terminal_marked_value": terminal_at_risk,
            "terminal_equity_if_long_stale_written_off": float(nav.equity.iloc[-1] - terminal_at_risk),
            "ledger_status": "needs_review" if affected or stale_max else "no_flagged_held_event",
            "limitation": "This is a holdings-impact audit, not proof that all source data or price-based signals are correct. A stale-price writeoff is a sensitivity bound, not a realized liquidation."}


def index_reference(frame, dates, initial):
    series = frame.set_index(pd.to_datetime(frame.trade_date)).sort_index().close
    prior = series.loc[series.index < dates[0]]
    if prior.empty:
        raise ValueError("Index reference needs preceding close")
    aligned = series.reindex(dates)
    if aligned.isna().any():
        raise ValueError("Index reference has missing observations")
    equity = initial * aligned / prior.iloc[-1]
    return pd.DataFrame({"equity": equity, "gross_exposure": 1.0, "fees_cumulative": 0.0,
                         "slippage_cumulative": 0.0, "stale_holdings": 0})
