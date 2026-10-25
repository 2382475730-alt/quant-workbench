"""Append-only forward observation of a frozen illustrative cash allocation.

This is not an order router or a continuation of the historical backtest.
Corporate-action changes stop valuation until a separate reviewed ledger exists.
"""
from __future__ import annotations

import argparse
import hashlib
import json

import numpy as np
import pandas as pd

from .data import ROOT, write_json


def initialize():
    path = ROOT / "artifacts/paper/seed.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    source = ROOT / "artifacts/outlook/portfolio.json"
    outlook = json.loads(source.read_text(encoding="utf-8"))
    account = outlook["illustrative_cash_account"]
    factors = pd.read_parquet(ROOT / "data/panels/adj_factor.parquet")
    date = pd.Timestamp(outlook["asof"])
    holdings = [{"code": r["code"], "shares": r["illustrative_shares"],
                 "close": r["reference_close"], "adj_factor": float(factors.at[date, r["code"]])}
                for r in account["rows"] if r["illustrative_shares"] > 0]
    seed = {"asof": outlook["asof"], "cash": account["cash_after_estimated_costs"],
            "capital_before_assumed_cost": account["capital"], "holdings": holdings,
            "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "status": "illustrative_initial_allocation_only",
            "boundary": "Assumed initial sizing, no actual fills. Forward fixed-share valuation only; no automatic rebalance or live orders. Factor changes and missing quotes block valuation. Unchanged factors do not prove absence of pending actions."}
    write_json("artifacts/paper/seed.json", seed)
    pd.DataFrame([{"date": outlook["asof"], **{k: r[k] for k in ["code", "close", "adj_factor"]}}
                  for r in holdings]).to_csv(path.parent / "quote_template.csv", index=False, encoding="utf-8-sig")
    write_json("artifacts/paper/status.json", {"forward_observations": 0, "last_date": seed["asof"],
                                              "message": "尚无前向观察。模板是初始日行情，不能当成未来业绩。"})
    return seed


def value_observation(seed, quotes, latest_date):
    required = {"date", "code", "close", "adj_factor"}
    if not required.issubset(quotes.columns) or quotes.code.duplicated().any():
        raise ValueError("Required columns or unique codes failed")
    if quotes.date.nunique() != 1:
        raise ValueError("Exactly one observation date required")
    date = pd.Timestamp(str(quotes.date.iloc[0]))
    if date <= pd.Timestamp(latest_date) or date.normalize() > pd.Timestamp.now(tz="Asia/Shanghai").tz_localize(None).normalize():
        raise ValueError("Observation must be later than the ledger and not in the future")
    expected = {r["code"] for r in seed["holdings"]}
    if set(quotes.code) != expected:
        raise ValueError("Every held security must have exactly one quote; no stale-price imputation")
    table = quotes.set_index("code")
    values = table[["close", "adj_factor"]].to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values <= 0).any():
        raise ValueError("Invalid quote or factor")
    equity = seed["cash"]
    for holding in seed["holdings"]:
        row = table.loc[holding["code"]]
        if not np.isclose(row.adj_factor, holding["adj_factor"], rtol=1e-10, atol=1e-10):
            raise ValueError(f"Corporate action/factor revision needs review: {holding['code']}")
        equity += holding["shares"] * row.close
    initial = seed["cash"] + sum(r["shares"] * r["close"] for r in seed["holdings"])
    return {"date": str(date.date()), "equity": float(equity), "mark_return_since_seed": float(equity / initial - 1),
            "scope": "Fixed illustrative shares and cash; not realized performance or a validated strategy."}


def observe(path, event_reviewed=False):
    if not event_reviewed:
        raise ValueError("Review all held securities for corporate actions and stale/suspended quotes, then pass --events-reviewed")
    seed = initialize()
    directory = ROOT / "artifacts/paper/observations"
    history = sorted(directory.glob("*.json")) if directory.exists() else []
    last = history[-1].stem if history else seed["asof"]
    raw = path.read_bytes()
    quotes = pd.read_csv(path, dtype={"date": str, "code": str})
    result = value_observation(seed, quotes, last)
    result.update({"input_sha256": hashlib.sha256(raw).hexdigest(), "manual_event_review_attested": True})
    destination = directory / f"{result['date']}.json"
    if destination.exists():
        raise ValueError("Observation already exists; no overwrite")
    write_json(str(destination.relative_to(ROOT)), result)
    (directory / f"{result['date']}.csv").write_bytes(raw)
    write_json("artifacts/paper/status.json", {"forward_observations": len(history) + 1, "last_date": result["date"], **result})
    return result


if __name__ == "__main__":
    from pathlib import Path

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["init", "observe"])
    parser.add_argument("--quotes", type=Path)
    parser.add_argument("--events-reviewed", action="store_true")
    args = parser.parse_args()
    if args.command == "init":
        initialize()
        print("Illustrative seed saved; no forward performance yet.")
    elif not args.quotes:
        parser.error("observe requires --quotes")
    else:
        print(json.dumps(observe(args.quotes, args.events_reviewed), ensure_ascii=False))
