"""Read-only reuse of sealed market inputs, separate new ETF data."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..data import ROOT
from ..enhancement_data import dated, dividend_events, table

BASE = ROOT / "artifacts/small_capital_v1"
DATA = ROOT / "data/small_capital_v1"
CODES = ["510300.SH", "510500.SH"]
NAMES = {"510300.SH": "华泰柏瑞沪深300ETF", "510500.SH": "南方中证500ETF"}


def dump(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass
class Market:
    panels: dict
    dividends: dict
    covariance: dict
    dates: pd.DatetimeIndex


def load():
    daily = [dated(table("etf_daily")), dated(pd.read_parquet(DATA / "daily.parquet"))]
    factors = [dated(table("etf_adj")), dated(pd.read_parquet(DATA / "adj.parquet"))]
    dates = pd.read_parquet(ROOT / "data/panels/close.parquet").index
    # Research begins 2017; 2016 supplies a full 252-session risk warmup.
    # Raw 2015 suspended/split history is retained but never needed or filled.
    dates = dates[dates >= "2016-01-01"]
    panels = {}
    for field in ["open", "close", "pre_close", "vol"]:
        panels[field] = pd.DataFrame({c: f[field].reindex(dates) for c, f in zip(CODES, daily)})
    panels["volume"] = panels.pop("vol") * 100
    panels["adj_factor"] = pd.DataFrame({c: f.adj_factor.reindex(dates) for c, f in zip(CODES, factors)})
    panels["adjusted"] = panels["close"] * panels["adj_factor"]
    panels["adv"] = panels["volume"].rolling(20, min_periods=10).mean().shift(1)
    for field, factor, buffer in [("upper", 1.1, -.006), ("lower", .9, .006)]:
        panels[field] = np.floor(panels["pre_close"] * factor * 1000 + .50000001) / 1000 + buffer
    dividends = {c: dividend_events(f) for c, f in zip(CODES, [table("etf_div"), pd.read_parquet(DATA / "div.parquet")])}
    returns = panels["adjusted"].pct_change(fill_method=None)
    covariance = {}
    for i, date in enumerate(dates):
        window = returns.iloc[max(0, i-251):i+1].dropna()
        if len(window) >= 126:
            sample = window.cov().to_numpy() * 252
            covariance[date] = .9 * sample + .1 * np.diag(np.diag(sample))
    return Market(panels, dividends, covariance, dates)


def validate(market):
    findings, checks = [], []
    for c in CODES:
        for field in ["open", "close", "pre_close", "adj_factor"]:
            values = market.panels[field][c]
            if values.isna().any() or not values.gt(0).all():
                findings.append(f"{c} {field}: missing/nonpositive")
        events = market.dividends[c]
        factors = market.panels["adj_factor"][c].pct_change(fill_method=None)
        for row in events.itertuples():
            day = pd.Timestamp(row.ex_date)
            if day not in market.dates:
                continue
            previous = market.panels["close"][c].shift().loc[day]
            expected = previous / (previous-row.div_cash)-1
            error = abs(factors.loc[day]-expected)
            checks.append({"code": c, "date": row.ex_date, "dividend_per_share": row.div_cash, "factor_error": error})
            if error > .0005:
                findings.append(f"{c} factor/dividend mismatch {day}")
        known_dates = list(pd.to_datetime(events.ex_date))
        if c == "510500.SH":
            known_dates.append(pd.Timestamp("2022-08-29"))
            error = abs(factors.loc["2022-08-29"]-(1.14539-1))
            checks.append({"code": c, "date": "20220829", "split_ratio": 1.14539, "factor_error": error})
            if error > .0005:
                findings.append("Split factor mismatch")
        unexplained = factors.loc[factors.abs().gt(.0001) & ~factors.index.isin(known_dates)]
        if len(unexplained):
            findings.append(f"{c}: unexplained factor changes")
    result = {"status": "passed_with_disclosed_limitations" if not findings else "failed", "critical": findings,
              "dates": [str(market.dates[0].date()), str(market.dates[-1].date())], "rows": len(market.dates),
              "dividend_checks": checks, "limits": "modeled +/-10%, tick .001 and inward .006 buffer",
              "survivorship": "two currently selected long-lived ETFs; not a historical fund-selection test",
              "commercial_license": "not verified; local personal research only"}
    dump(BASE / "data_audit.json", result)
    if findings:
        raise ValueError(str(findings))
    return result
