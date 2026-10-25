"""Audit source tables and assemble raw-price research panels."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict

import numpy as np
import pandas as pd

from .data import ROOT, write_json
from .engine import Action
from .event_review import adjudicate, load_reviews
from .suspensions import audit as audit_suspensions


def finite(value, default=0):
    return float(value) if value is not None and pd.notna(value) else default


def date_string(value):
    return str(value) if value is not None and pd.notna(value) else ""


def load_table(api, code=None):
    path = ROOT / "data/normalized" / (f"{api}/{code}.parquet" if code else f"{api}.parquet")
    return pd.read_parquet(path) if path.exists() else pd.DataFrame()


def prepare(symbols=None, require_complete=True):
    state = json.loads((ROOT / "artifacts/collection_status.json").read_text())
    if require_complete and state["stage"] != "complete":
        raise RuntimeError("Acquisition still running; full analysis cannot silently use partial coverage")
    universe = json.loads((ROOT / "artifacts/universe_manifest.json").read_text())
    symbols = symbols or universe["symbols"]
    calendar = load_table("calendar")
    dates = pd.DatetimeIndex(pd.to_datetime(calendar.loc[calendar.is_open.eq(1), "cal_date"].sort_values()))
    fields = ["open", "high", "low", "close", "pre_close", "volume", "amount", "adj_factor", "up_limit", "down_limit", "pe_ttm", "pb", "total_mv"]
    panels = {f: pd.DataFrame(np.nan, index=dates, columns=symbols) for f in fields}
    profiles, issues, actions = [], [], []
    overrides_path = ROOT / "config/action_overrides.json"
    overrides = json.loads(overrides_path.read_text(encoding="utf-8")) if overrides_path.exists() else []
    master = load_table("stock_basic").set_index("ts_code")
    for code in symbols:
        daily = load_table("daily", code)
        if daily.empty:
            issues.append({"code": code, "severity": "critical", "type": "no_daily"})
            continue
        if daily.duplicated(["ts_code", "trade_date"]).any():
            raise ValueError(f"Duplicate daily keys {code}")
        d = daily.set_index(pd.to_datetime(daily.trade_date)).sort_index()
        invalid = ((d.high < d[["open", "close", "low"]].max(axis=1) - 1e-8) |
                   (d.low > d[["open", "close", "high"]].min(axis=1) + 1e-8) |
                   (d[["open", "high", "low", "close"]] <= 0).any(axis=1) |
                   (d.vol < 0) | (d.amount < 0))
        if invalid.any():
            issues.append({"code": code, "severity": "critical", "type": "invalid_ohlcv", "count": int(invalid.sum())})
        for field in ["open", "high", "low", "close", "pre_close"]:
            panels[field][code] = d[field].reindex(dates)
        panels["volume"][code] = (d.vol * 100).reindex(dates)  # provider unit: lots
        panels["amount"][code] = (d.amount * 1000).reindex(dates)  # provider unit: CNY thousands
        for api, wanted in [("adj_factor", ["adj_factor"]), ("stk_limit", ["up_limit", "down_limit"]),
                            ("daily_basic", ["pe_ttm", "pb", "total_mv"])]:
            frame = load_table(api, code)
            if frame.empty:
                issues.append({"code": code, "severity": "critical", "type": f"missing_{api}"})
                continue
            if frame.duplicated(["ts_code", "trade_date"]).any():
                raise ValueError(f"Duplicate {api} keys {code}")
            frame = frame.set_index(pd.to_datetime(frame.trade_date)).sort_index()
            for field in wanted:
                panels[field][code] = pd.to_numeric(frame[field], errors="coerce").reindex(dates)
        dividend = load_table("dividend", code)
        action_by_ex = {}
        stock_overrides = [o for o in overrides if o["code"] == code]
        if not dividend.empty:
            implemented = dividend.loc[dividend.div_proc.eq("实施") & dividend.ex_date.notna() &
                                       dividend.ex_date.astype(str).between("20150101", "20261023")]
            for override in stock_overrides:
                implemented = implemented.loc[implemented.ex_date != override["ex_date"]]
            economic_fields = ["end_date", "ex_date", "record_date", "pay_date", "div_listdate", "stk_div", "cash_div_tax"]
            duplicate_count = int(implemented.duplicated(economic_fields).sum())
            if duplicate_count:
                issues.append({"code": code, "severity": "low", "type": "duplicate_identical_dividend_notices", "count": duplicate_count})
                implemented = implemented.drop_duplicates(economic_fields)
            if implemented.duplicated(["ex_date", "end_date"]).any():
                merged = []
                for _, group in implemented.groupby(["ex_date", "end_date"]):
                    if any(group[field].dropna().nunique() > 1 for field in economic_fields):
                        issues.append({"code": code, "severity": "critical", "type": "conflicting_dividend",
                                       "date": str(group.iloc[0].ex_date),
                                       "records": group.where(pd.notna(group), None).to_dict("records")})
                        continue
                    row = group.iloc[0].copy()
                    for field in economic_fields:
                        known = group[field].dropna()
                        if len(known):
                            row[field] = known.iloc[0]
                    merged.append(row)
                    if len(group) > 1:
                        issues.append({"code": code, "severity": "low", "type": "complementary_dividend_notices_merged", "count": len(group)})
                implemented = pd.DataFrame(merged, columns=implemented.columns)
            for row in implemented.to_dict("records"):
                if str(row["ex_date"]) < "20150101" or str(row["ex_date"]) > "20261023":
                    continue
                action = Action(code, date_string(row.get("record_date")), str(row["ex_date"]),
                                finite(row.get("cash_div_tax")), finite(row.get("stk_div")),
                                date_string(row.get("pay_date")), date_string(row.get("div_listdate")))
                if not action.record_date or (action.cash_per_share and not action.pay_date) or (action.stock_ratio and not action.list_date):
                    issues.append({"code": code, "severity": "high", "type": "incomplete_action_dates", "ex_date": action.ex_date})
                actions.append(action)
                action_by_ex.setdefault(action.ex_date, []).append(action)
        for override in stock_overrides:
            action = Action(**{key: value for key, value in override.items() if key in Action.__dataclass_fields__})
            actions.append(action)
            action_by_ex.setdefault(action.ex_date, []).append(action)
            issues.append({"code": code, "severity": "info", "type": "primary_source_action_override",
                           "date": action.ex_date, "source": override["source"], "reason": override["reason"]})
            if action.uncertain_entitlement:
                issues.append({"code": code, "severity": "high", "type": "unresolved_shareholder_entitlement",
                               "date": action.ex_date, "source": override["source"],
                               "handling": "Engine rejects any strategy holding an entitlement; no assumed free shares."})
        factor = panels["adj_factor"][code].dropna()
        changes = factor.div(factor.shift()).dropna()
        changed = changes.loc[(changes - 1).abs() > 1e-6]
        # Check action dates even when the provider factor did NOT change (e.g. reorganization).
        check_dates = changed.index.union(pd.to_datetime(list(action_by_ex)))
        unmatched = []
        for event_date in check_dates:
            if event_date not in changes.index:
                continue
            factor_ratio = changes.loc[event_date]
            key = event_date.strftime("%Y%m%d")
            event_actions = action_by_ex.get(key, [])
            delisted = date_string(master.at[code, "delist_date"]) if code in master.index else ""
            if delisted and key >= delisted and event_date > d.index[-1] and not event_actions:
                issues.append({"code": code, "severity": "info", "type": "factor_after_delisting_without_quote",
                               "date": key, "delist_date": delisted, "last_quote": str(d.index[-1].date()),
                               "handling": "No quoted price exists, so this factor is not an input to a return or trade. Any stale holding is retained and separately stressed."})
                continue
            if not event_actions:
                absolute_change = abs(factor.loc[event_date] - factor.shift().loc[event_date])
                past = d.loc[d.index < event_date, "close"]
                unchanged_reference = (event_date in d.index and len(past) and
                                       abs(d.loc[event_date, "pre_close"] - past.iloc[-1]) < .005)
                if abs(factor_ratio - 1) <= 0.0001 or (absolute_change <= .00101 and unchanged_reference):
                    issues.append({"code": code, "severity": "low", "type": "tiny_factor_revision", "date": key, "relative_change": float(factor_ratio - 1)})
                    continue
                unmatched.append(key)
                continue
            past = d.loc[d.index < event_date, "close"]
            if past.empty:
                continue
            previous = past.iloc[-1]
            cash_div = sum(a.cash_per_share for a in event_actions)
            stock_div = sum(a.stock_ratio if a.mark_stock_ratio is None else a.mark_stock_ratio for a in event_actions)
            expected = previous * (1 + stock_div) / (previous - cash_div) if previous > cash_div else np.nan
            if not np.isfinite(expected) or abs(factor_ratio / expected - 1) > max(0.002, 0.02 / previous):
                issues.append({"code": code, "severity": "high", "type": "action_factor_mismatch", "date": key,
                               "factor_ratio": float(factor_ratio), "expected": float(expected)})
        if unmatched:
            issues.append({"code": code, "severity": "high", "type": "unexplained_factor_change", "dates": unmatched})
        matched_factor = panels["adj_factor"][code].reindex(d.index)
        profiles.append({"code": code, "rows": len(d), "first": str(d.index.min().date()),
                         "last": str(d.index.max().date()), "invalid_rows": int(invalid.sum()),
                         "missing_factor_on_quotes": int(matched_factor.isna().sum()),
                         "calendar_gaps_between_quotes": int(panels["close"][code].loc[d.index.min():d.index.max()].isna().sum()),
                         "unexplained_factor_changes": len(unmatched)})
    # Unanchored price*factor is ratio-consistent; no future terminal anchor.
    # Missing trading-day observations remain missing for signals and execution.
    panels["adjusted_close"] = panels["close"] * panels["adj_factor"]
    issues = adjudicate(issues, panels, actions, load_reviews())
    pending_path = ROOT / "config/pending_exchanges.json"
    pending = json.loads(pending_path.read_text(encoding="utf-8")) if pending_path.exists() else []
    for entry in pending:
        source = (ROOT / entry["source"]["path"]).resolve()
        if not source.is_relative_to(ROOT.resolve()) or hashlib.sha256(source.read_bytes()).hexdigest() != entry["source"]["sha256"]:
            raise ValueError("Pending-conversion source missing or changed")
    report = {"scope": "complete" if require_complete else "partial_engineering_only", "symbols": len(symbols),
              "profiles": profiles, "issues": issues,
              "pending_security_conversions": pending,
              "units": {"price": "CNY", "volume": "shares", "amount": "CNY", "total_mv": "CNY 10000"},
              "limitations": ["Monthly membership publication time is proxied by prior-month lag.",
                              "Current industry is descriptive only.", "Cash dividends are before investor-specific dividend tax.",
                              "Calendar gaps require suspension/delisting reconciliation; missing quote forbids trading.",
                              "Reviewed rights issues are not subscribed: raw-price dilution remains in NAV; factor changes are used only for price signals.",
                              "Differential distributions use ordinary-holder cash/shares; exchange reference calculations may use a different diluted amount."]}
    label = "data_quality" if require_complete else "partial_data_quality"
    if require_complete:
        suspension = audit_suspensions(panels["close"])
        report["suspensions"] = {"totals": suspension["totals"], "unexplained_count": suspension["unexplained_count"],
                                 "detail_path": "artifacts/suspension_audit.json"}
    write_json(f"artifacts/{label}.json", report)
    if require_complete:
        for name, frame in panels.items():
            path = ROOT / "data/panels" / f"{name}.parquet"
            path.parent.mkdir(parents=True, exist_ok=True)
            frame.to_parquet(path)
        write_json("data/panels/actions.json", [asdict(a) for a in actions])
    return panels, actions, report


if __name__ == "__main__":
    prepare()
