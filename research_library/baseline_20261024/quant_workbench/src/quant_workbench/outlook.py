"""As-of research allocations and conditional risks; no broker connection."""
from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd

from .company import NAMES
from .data import ROOT, write_json
from .engine import Costs, quantity
from .prepare import load_table
from .research import config, load_panels, portfolio_decisions
from .risk import block_paths, stock_scenarios, summarize_paths
from .signals import stock_signals


def sizing_preview(weights, prices, capital=1_000_000, reserve=.01):
    """Illustrative new cash account at known closes; not future executable orders."""
    if capital <= 0 or not 0 <= reserve < 1 or sum(weights.values()) > 1 + 1e-9:
        raise ValueError("Invalid allocation budget")
    costs = Costs()
    remaining = float(capital)
    rows = []
    for code, weight in sorted(weights.items()):
        price = prices.get(code)
        if weight < 0 or not np.isfinite(weight) or price is None or not np.isfinite(price) or price <= 0:
            raise ValueError("Invalid allocation input")
        execution = price * (1 + costs.slippage)
        shares = quantity(code, min(capital * (1 - reserve) * weight, remaining) / execution)
        fee = costs.fee(shares * execution, False, "20261023") if shares else 0
        while shares and shares * execution + fee > remaining:
            shares = quantity(code, shares - (1 if code.startswith("688") else 100))
            fee = costs.fee(shares * execution, False, "20261023") if shares else 0
        outlay = shares * execution + fee
        remaining -= outlay
        rows.append({"code": code, "model_weight": float(weight), "reference_close": float(price),
                     "illustrative_shares": shares, "estimated_fee": fee, "estimated_outlay": outlay,
                     "marked_value": shares * price, "portfolio_weight": shares * price / capital})
    return {"capital": capital, "cash_after_estimated_costs": remaining, "reserve_assumption": reserve, "rows": rows,
            "scope": "New cash account illustration using known closing prices plus assumed slippage; existing holdings, next open, limits and availability must be rechecked."}


def portfolio_scenarios(returns, weights, horizons=(20, 60, 120), simulations=10000):
    """Fixed initial shares, paired returns; cash earns zero, no future rebalancing."""
    ordered = returns.reindex(columns=list(weights)).tail(756)
    paired = ordered.dropna(how="any")
    if len(paired) < 252:
        return {"status": "insufficient_joint_history", "joint_observations": len(paired)}
    vector = np.array(list(weights.values()), dtype=float)
    if (vector < 0).any() or vector.sum() > 1 + 1e-9:
        raise ValueError("Invalid scenario weights")
    cash = 1 - vector.sum()
    result = {"status": "complete", "joint_observations": len(paired),
              "first_observation": str(paired.index[0].date()), "last_observation": str(paired.index[-1].date()),
              "missing_rows_removed": len(ordered) - len(paired), "weights": weights, "horizons": {}}
    centered = (1 + paired) / (1 + paired.mean()) - 1
    for days in horizons:
        paths = block_paths(paired.to_numpy(), days, simulations=simulations)
        wealth = cash + paths @ vector
        stressed = wealth.copy()
        start = max(1, days // 4)
        stressed[:, start:] = cash + .8 * (wealth[:, start:] - cash)
        centered_paths = block_paths(centered.to_numpy(), days, simulations=simulations)
        result["horizons"][str(days)] = {
            "joint_historical_block_bootstrap": summarize_paths(wealth),
            "joint_zero_sample_arithmetic_mean_bootstrap": summarize_paths(cash + centered_paths @ vector),
            "specified_all_equities_minus20pct_jump": summarize_paths(stressed)}
    result["scope"] = "Conditional adjusted-price scenarios, fixed initial shares and zero-yield cash. Historical cross-asset dependence retained; future trading, tax and new corporate actions are not simulated. Centered variant removes each asset's historical arithmetic mean to expose drift-estimation risk; it is not risk-neutral pricing."
    return result


def build():
    panels, _ = load_panels()
    settings = config()
    asof = panels["close"].index[-1]
    spec = next(s for s in settings["portfolio"] if s["role"] == "primary")
    decisions = portfolio_decisions(panels, load_table("membership"), spec, settings["phases"]["final"][0], asof)
    decision = max(decisions)
    weights = decisions[decision]
    master = load_table("stock_basic").set_index("ts_code")
    prices = panels["close"].loc[asof].to_dict()
    quoted_weights = {c: w for c, w in weights.items() if pd.notna(prices[c])}
    unavailable = sorted(set(weights) - set(quoted_weights))
    preview = sizing_preview(quoted_weights, prices, settings["initial_cash"])
    for row in preview["rows"]:
        row["name"] = str(master.at[row["code"], "name"])
        row["current_industry_descriptive_only"] = str(master.at[row["code"], "industry"])
    current_industries = {}
    for row in preview["rows"]:
        industry = row["current_industry_descriptive_only"]
        current_industries[industry] = current_industries.get(industry, 0) + row["portfolio_weight"]
    returns = panels["adjusted_close"].pct_change(fill_method=None)
    joint_weights = {r["code"]: r["portfolio_weight"] for r in preview["rows"] if r["portfolio_weight"] > 0}
    portfolio = {"asof": str(asof.date()), "strategy": spec["name"], "last_scheduled_decision": str(decision.date()),
                 "decision_weights": weights, "unquoted_symbols_not_sized": unavailable,
                 "illustrative_cash_account": preview, "current_industry_weights": current_industries,
                 "risk": portfolio_scenarios(returns, joint_weights),
                 "timing": "Weights are from the last scheduled monthly decision. This is not an unscheduled rebalance recommendation; reevaluate at the next trading month-end close."}
    write_json("artifacts/outlook/portfolio.json", portfolio)
    print("Portfolio outlook and joint risk complete", flush=True)
    stocks = []
    for code in settings["single_stock_examples"]:
        series = panels["adjusted_close"][code]
        signal = stock_signals(series.ffill()).loc[asof]
        risk = stock_scenarios(returns[code])
        # Account risk budgeting illustration, separate from the tested sleeve.
        illustrative_loss_budget, specified_jump = .01, .20
        cap = illustrative_loss_budget / specified_jump
        stock = {"code": code, "name": NAMES[code], "asof": str(asof.date()),
                 "raw_close": float(prices[code]), "trend_on": bool(signal.trend),
                 "adjusted_price_to_ma200": float(series.loc[asof] / signal.moving_average - 1),
                 "estimated_volatility_60d": float(signal.volatility),
                 "trend_risk_sleeve_weight": float(signal.trend_risk),
                 "illustrative_total_account_cap": cap,
                 "illustrative_total_account_weight": cap * float(signal.trend_risk),
                 "risk_budget": {"loss_budget_fraction": illustrative_loss_budget, "specified_one_stock_gap": specified_jump,
                                 "formula": "total account cap = loss budget / specified gap; allocated cap multiplied by tested sleeve signal",
                                 "boundary": "Chosen teaching assumptions, not optimized or personalized. A larger gap can exceed the budget; no stop-loss guarantee."},
                 "risk": risk}
        write_json(f"artifacts/outlook/{code}.json", stock)
        stocks.append({k: stock[k] for k in ["code", "name", "asof", "trend_on", "trend_risk_sleeve_weight", "illustrative_total_account_weight"]})
        print(f"Single-stock outlook and risk complete: {code}", flush=True)
    write_json("artifacts/outlook/index.json", {"asof": str(asof.date()), "stocks": stocks,
               "simulations": 10000, "seed": 20261023, "historical_block_trading_days": 20,
               "not_final_holdout_performance": True})
    paths = [ROOT / f"src/quant_workbench/{module}.py" for module in ["outlook", "risk", "signals", "engine"]]
    paths += [ROOT / "config/experiments.json", ROOT / "data/normalized/membership.parquet"]
    paths += sorted((ROOT / "data/panels").glob("*.parquet"))
    write_json("artifacts/outlook/input_fingerprints.json", {
        str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
    return portfolio, stocks


if __name__ == "__main__":
    build()
