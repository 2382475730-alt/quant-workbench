"""Validated task adapter reusing the existing deterministic tool-layer pattern."""
from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict
from datetime import UTC, datetime

import numpy as np
import pandas as pd

from ..data import ROOT
from ..enhancement_data import benchmark_weights, industry_at, table
from ..quant_agent import verify_log
from .allocator import Budget, Costs, allocate
from .data import BASE, CODES, DATA, NAMES, load
from .runner import check_freeze, status, verify

TASK_KEYS = {"version", "capital", "cash", "holdings", "ever_invested", "allowed_assets", "strategy",
             "annual_fee", "cost_multiplier", "risk_budget", "asof", "permissions"}


def example_task(capital=100000):
    return {"version": "small_capital_v1", "capital": capital, "cash": capital, "holdings": {},
            "ever_invested": False, "allowed_assets": CODES, "strategy": "band", "annual_fee": 0,
            "cost_multiplier": 1, "risk_budget": asdict(Budget()), "asof": "2026-10-23",
            "permissions": "ordinary_cash_account_assumed_unverified"}


def number(value):
    return type(value) in {float, int} and math.isfinite(value)


def lookthrough(weights, date):
    members = pd.read_parquet(ROOT / "data/normalized/membership.parquet")
    w300, d300 = benchmark_weights(members, date)
    w500, d500 = benchmark_weights(pd.read_parquet(DATA / "current_500_weights.parquet"), date)
    sectors = industry_at(table("industry_history"), date)
    combined = w300*weights[0]
    combined = combined.add(w500*weights[1], fill_value=0)
    by_sector = combined.groupby(pd.Series({c: sectors.get(c, "UNKNOWN") for c in combined.index})).sum()
    names = table("industry_codes").set_index("index_code").industry_name.to_dict()
    overlap = w300.index.intersection(w500.index)
    return {"scope": "lagged index proxy, not actual fund holdings", "snapshot_dates": [d300, d500],
            "overlap_codes": overlap.tolist(), "overlap_count": len(overlap),
            "overlap_weight_proxy": float(sum(min(w300[c]*weights[0], w500[c]*weights[1]) for c in overlap)),
            "company_max_weight": float(combined.max()), "company_hhi": float((combined**2).sum()),
            "industry_max_weight": float(by_sector.max()), "unknown_industry_weight": float(by_sector.get("UNKNOWN", 0)),
            "industries": [{"code": c, "name": names.get(c, "未分类"), "weight": float(v)} for c, v in by_sector.sort_values(ascending=False).items()],
            "companies": [{"code": c, "weight": float(v)} for c, v in combined.sort_values(ascending=False).items()],
            "factor_warning": "two funds share China equity, liquidity and macroeconomic factors; zero name overlap is not zero correlation"}


def plan(task, market=None):
    if not isinstance(task, dict) or set(task) != TASK_KEYS:
        raise ValueError("Task fields must exactly match the documented schema; arbitrary instructions are not data")
    if task["version"] != "small_capital_v1" or task["strategy"] not in {"single", "fixed", "risk", "band"}:
        raise ValueError("Unknown version or strategy")
    if not all(number(task[k]) and task[k] >= 0 for k in ["capital", "cash", "annual_fee", "cost_multiplier"]):
        raise ValueError("Finite nonnegative numbers required")
    if type(task["ever_invested"]) is not bool or not isinstance(task["holdings"], dict):
        raise ValueError("Explicit persistent startup state and holdings mapping required")
    if not isinstance(task["allowed_assets"], list) or len(set(task["allowed_assets"])) != len(task["allowed_assets"]):
        raise ValueError("Unique allowed-asset list required")
    if any(c not in CODES or type(q) is not int or q < 0 for c, q in task["holdings"].items()):
        raise ValueError("Only nonnegative integer ETF shares are supported")
    if any(task["holdings"].values()) and not task["ever_invested"]:
        raise ValueError("Actual holdings require ever_invested=true")
    reasons = []
    if task["capital"] not in {50000, 100000, 200000, 500000}:
        reasons.append("capital_not_at_validated_scale")
    required_assets = {CODES[0]} if task["strategy"] == "single" else set(CODES)
    if not required_assets <= set(task["allowed_assets"]) or not set(task["allowed_assets"]) <= set(CODES):
        reasons.append("asset_set_requires_new_research")
    if task["annual_fee"] not in {0, 300, 600, 1200} or task["cost_multiplier"] not in {1, 2}:
        reasons.append("fee_contract_outside_scenarios")
    if task["capital"] != 100000 and (task["annual_fee"] != 0 or task["cost_multiplier"] != 1):
        reasons.append("scale_and_fee_combination_not_tested_jointly")
    if task["annual_fee"] != 0 and task["cost_multiplier"] != 1:
        reasons.append("service_fee_and_cost_stress_not_tested_jointly")
    if task["risk_budget"] != asdict(Budget()):
        reasons.append("risk_budget_changed_requires_new_research_no_automatic_risk_escalation")
    if task["asof"] != "2026-10-23":
        reasons.append("new_quotes_and_actions_need_separate_forward_validation")
    if task["permissions"] != "ordinary_cash_account_assumed_unverified":
        reasons.append("permission_contract_not_validated")
    if reasons:
        return {"status": "needs_research", "reasons": reasons, "orders": [], "broker_connected": False}
    check_freeze()
    m = market or load()
    date = pd.Timestamp(task["asof"])
    prices = m.panels["close"].loc[date].to_numpy()
    held = np.array([task["holdings"].get(c, 0) for c in CODES], dtype=int)
    actual_equity = task["cash"]+held@prices
    if abs(actual_equity-task["capital"]) > .01:
        raise ValueError("capital is current account wealth; cash plus securities must reconcile to it")
    if task["cash"] < task["annual_fee"]:
        return {"status": "fee_cash_shortfall", "orders": [], "required_cash": task["annual_fee"], "broker_connected": False}
    result = allocate(prices, held, task["cash"]-task["annual_fee"], 0, m.covariance[date], task["strategy"],
                      task["ever_invested"], Costs(multiplier=task["cost_multiplier"]))
    result.update({"account_type": "new_cash_trial" if not task["ever_invested"] else "existing_holding_reference_plan",
                   "research_date": task["asof"], "capital": task["capital"], "input_cash": task["cash"],
                   "annual_fee_reserved": task["annual_fee"], "permissions": task["permissions"],
                   "cash_contract": "ETF minimum commission 5 / rate .0003 / slippage .001, multiplied by scenario",
                   "broker_connected": False, "fill_status": "not_executed_reference_close_only",
                   "earliest_execution": "next real trading session after signal; refresh quote and tradability first"})
    chosen = np.array(result["shares"])
    actual_weights = chosen*prices/task["capital"]
    costs = Costs(multiplier=task["cost_multiplier"])
    delta = chosen-held
    result["rows"] = [{"code": c, "name": NAMES[c], "reason": "大盘权益底仓" if j == 0 else "中盘权益补充；与大盘仍有共同风险",
                       "reference_price": float(prices[j]), "current_shares": int(held[j]), "target_shares": int(chosen[j]),
                       "market_value": float(chosen[j]*prices[j]), "weight": float(actual_weights[j]),
                       "target_weight": float(result.get("target_weights", [0, 0])[j]), "delta": int(delta[j]),
                       "estimated_fee": float(costs.fees([abs(delta[j])*prices[j]])[0]),
                       "unbought": bool(result.get("target_weights", [0, 0])[j] > 0 and chosen[j] == 0)} for j, c in enumerate(CODES)]
    result["available_cash_reference"] = float(task["cash"]-task["annual_fee"]-delta@prices-result.get("estimated_fees", 0)-result.get("estimated_slippage", 0))
    result["lookthrough"] = lookthrough(actual_weights, date)
    result["correlation_252d"] = float(m.panels["adjusted"].pct_change().loc[:date].tail(252).corr().iloc[0, 1])
    return result


def log(action, result):
    path = BASE / "agent_events.jsonl"
    verify_log(path)
    previous = json.loads(path.read_text(encoding="utf-8").splitlines()[-1])["hash"] if path.exists() else ""
    event = {"at": datetime.now(UTC).isoformat(), "action": action, "result": result, "previous": previous}
    import hashlib
    event["hash"] = hashlib.sha256(json.dumps(event, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False)+"\n")


def dispatch(name, arguments):
    if name == "small_capital_status" and arguments == {}:
        return status()
    if name == "small_capital_verify" and arguments == {}:
        return verify()
    if name == "small_capital_plan" and isinstance(arguments, dict) and set(arguments) == {"task"}:
        result = plan(arguments["task"])
        log(name, {"status": result["status"], "task": arguments["task"]})
        return result
    raise ValueError("Unsupported small-capital tool or arguments")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("command", choices=["status", "verify", "plan", "example"])
    p.add_argument("--task")
    args = p.parse_args()
    if args.command == "example":
        result = example_task()
    elif args.command == "plan":
        if not args.task:
            p.error("--task JSON is required")
        from pathlib import Path
        result = dispatch("small_capital_plan", {"task": json.loads(Path(args.task).read_text(encoding="utf-8-sig"))})
    else:
        result = dispatch("small_capital_"+args.command, {})
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
