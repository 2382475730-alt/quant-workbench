"""Read isolated enhancement inputs; preserve all original research inputs."""
from __future__ import annotations

import json
from datetime import timedelta

import numpy as np
import pandas as pd

from .data import ROOT, write_json
from .engine import Action
from .research import load_panels

BASE = ROOT / "data/enhancement_v1"
OUT = ROOT / "artifacts/enhancement_v1"
ETF = "510300.SH"


def config():
    return json.loads((ROOT / "config/enhancement_v1.json").read_text(encoding="utf-8"))


def table(name):
    return pd.read_parquet(BASE / f"{name}.parquet")


def dated(frame):
    if frame.trade_date.duplicated().any():
        raise ValueError("Duplicate trading dates")
    return frame.set_index(pd.to_datetime(frame.trade_date)).sort_index()


def dividend_events(frame):
    implemented = frame.loc[frame.div_proc.eq("实施")].copy()
    fields = ["record_date", "ex_date", "pay_date", "div_cash"]
    implemented = implemented[fields].drop_duplicates()
    if implemented.ex_date.duplicated().any():
        raise ValueError("Conflicting fund dividends for the same ex-date")
    if implemented[fields].isna().any().any():
        raise ValueError("Incomplete ETF corporate action")
    return implemented.sort_values("ex_date")


def industry_at(history, date):
    value = pd.Timestamp(date).strftime("%Y%m%d")
    # Strictly prior effective date; interval end excluded, conflicts remain unknown.
    valid = history.loc[history.in_date.lt(value) & (history.out_date.isna() | history.out_date.gt(value))]
    pairs = valid[["ts_code", "l1_code"]].drop_duplicates()
    conflicts = pairs.ts_code.duplicated(keep=False)
    mapping = dict(zip(pairs.loc[~conflicts, "ts_code"], pairs.loc[~conflicts, "l1_code"]))
    mapping.update({c: "UNKNOWN" for c in pairs.loc[conflicts, "ts_code"]})
    return mapping


def benchmark_weights(members, date):
    cutoff = (pd.Timestamp(date).to_pydatetime().replace(day=1) - timedelta(days=1)).strftime("%Y%m%d")
    known = members.loc[members.trade_date.astype(str).le(cutoff)]
    if known.empty:
        raise ValueError("No prior-month index weights")
    latest = known.trade_date.max()
    rows = known.loc[known.trade_date.eq(latest)]
    weights = rows.set_index("con_code").weight.astype(float)
    if weights.index.duplicated().any() or (weights <= 0).any() or not 99 < weights.sum() < 101:
        raise ValueError("Invalid index weight snapshot")
    return weights / weights.sum(), str(latest)


def load():
    panels, actions = load_panels()
    dates = panels["close"].index
    daily, adj, _limits = [dated(table(x)).reindex(dates) for x in ["etf_daily", "etf_adj", "etf_limits"]]
    for key in ["open", "high", "low", "close", "pre_close"]:
        panels[key][ETF] = daily[key]
    panels["volume"][ETF] = daily.vol * 100
    panels["amount"][ETF] = daily.amount * 1000
    panels["adj_factor"][ETF] = adj.adj_factor
    panels["adjusted_close"][ETF] = daily.close * adj.adj_factor
    # Provider ETF limits have gaps and cent-rounded history. Model a deliberately
    # narrower band from the ex-dividend reference close; retain raw limits for audit.
    for key, multiple, buffer in [("up_limit", 1.1, -.006), ("down_limit", .9, .006)]:
        derived = np.floor(daily.pre_close * multiple * 1000 + .50000001) / 1000 + buffer
        panels[key][ETF] = derived
    divs = dividend_events(table("etf_div"))
    actions += [Action(code=ETF, record_date=r.record_date, ex_date=r.ex_date,
                       pay_date=r.pay_date, cash_per_share=float(r.div_cash)) for r in divs.itertuples()]
    # Engine expects identical panel columns. Non-execution valuation fields can be missing.
    for key, frame in panels.items():
        if ETF not in frame:
            panels[key][ETF] = np.nan
    return panels, actions


def validate():
    panels, _ = load()
    dates = panels["close"].index
    findings, profiles = [], {}
    critical = []
    for name in ["benchmark", "etf_daily", "etf_adj", "etf_limits"]:
        frame = dated(table(name))
        missing = dates.difference(frame.index)
        profiles[name] = {"rows": len(frame), "first": str(frame.index.min().date()), "last": str(frame.index.max().date()),
                          "missing_calendar_dates": len(missing), "duplicate_dates": 0}
        if len(missing) and name != "etf_limits":
            critical.append(f"{name}: {len(missing)} calendar gaps")
    benchmark = dated(table("benchmark"))
    if not benchmark.ts_code.eq("H00300.CSI").all() or not benchmark.close.gt(0).all():
        critical.append("Incorrect benchmark code or nonpositive levels")
    previous_error = float((benchmark.pre_close.iloc[1:] - benchmark.close.shift().iloc[1:]).abs().max())
    if previous_error > .001:
        critical.append("Benchmark previous close mismatch")
    divs = dividend_events(table("etf_div"))
    factors = panels["adj_factor"][ETF]
    daily = dated(table("etf_daily"))
    changes = factors.pct_change(fill_method=None)
    checks = []
    for r in divs.itertuples():
        date = pd.Timestamp(r.ex_date)
        if date not in dates:
            continue
        previous = panels["close"][ETF].shift().loc[date]
        expected = previous / (previous - r.div_cash) - 1
        error = abs(changes.loc[date] - expected)
        checks.append({"date": r.ex_date, "cash": r.div_cash, "factor_change": float(changes.loc[date]),
                       "expected_change": float(expected), "absolute_error": float(error)})
        if error > .0005:
            critical.append(f"ETF factor/dividend mismatch {r.ex_date}")
    ex_dates = pd.to_datetime(divs.ex_date)
    unexplained = changes.loc[changes.abs().gt(.0001) & ~changes.index.isin(ex_dates)]
    if len(unexplained):
        critical.append(f"ETF unexplained factor changes {len(unexplained)}")
    if daily[["open", "close"]].isna().any().any():
        critical.append("Missing ETF trading prices")
    history = table("industry_history")
    members = pd.read_parquet(ROOT / "data/normalized/membership.parquet")
    coverage = []
    monthly = pd.Series(dates, index=dates).groupby(dates.to_period("M")).last()
    for date in monthly.iloc[1:]:
        weights, source_date = benchmark_weights(members, date)
        industries = industry_at(history, date)
        unknown = [c for c in weights.index if industries.get(c, "UNKNOWN") == "UNKNOWN"]
        coverage.append({"date": str(date.date()), "weight_date": source_date,
                         "unknown_count": len(unknown), "unknown_weight": float(weights.reindex(unknown).sum())})
    findings.append({"severity": "high", "issue": "Historical classification and index publication vintages are not fully recovered",
                     "impact": "Retrospective proxy only; no strictly point-in-time claim or adoption based on this run"})
    findings.append({"severity": "medium", "issue": "ETF sector look-through uses lagged index weights, not actual daily fund holdings",
                     "impact": "Industry constraints are measured against this disclosed proxy"})
    findings.append({"severity": "high", "issue": "ETF limit feed lacks early history and rounds many quotes to cents",
                     "impact": "Use explicit model band: ex-dividend pre_close +/-10%, .001 tick, .006 inward buffer; not actual exchange limit archive"})
    report = {"status": "passed_with_limitations" if not critical else "failed", "critical": critical,
              "profiles": profiles, "benchmark_previous_close_max_error": previous_error,
              "fund_dividend_input_rows": len(table("etf_div")), "fund_dividend_unique_events": len(divs),
              "fund_dividend_checks": checks, "industry_interval_rows": len(history), "industry_coverage": coverage,
              "findings": findings, "sources": "artifacts/enhancement_v1/source_receipts.json"}
    write_json("artifacts/enhancement_v1/data_quality.json", report)
    if critical:
        raise ValueError(str(critical))
    return report


if __name__ == "__main__":
    result = validate()
    print(json.dumps({k: result[k] for k in ["status", "profiles", "fund_dividend_unique_events"]}))
