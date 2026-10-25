"""Causal, constrained ETF-core allocation. No performance-based parameter search."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
from scipy.optimize import Bounds, LinearConstraint, milp, minimize

from .data import ROOT
from .enhancement_data import ETF, benchmark_weights, dated, industry_at, table
from .signals import momentum_scores

CASH = "CASH"


def shrunk_covariance(values, shrinkage=.1):
    values = np.asarray(values, dtype=float)
    if values.ndim != 2 or len(values) < 2 or not np.isfinite(values).all():
        raise ValueError("Invalid risk observations")
    sample = np.atleast_2d(np.cov(values, rowvar=False, ddof=1)) * 252
    return (1 - shrinkage) * sample + shrinkage * np.diag(np.diag(sample))


def within_sector(values, sectors):
    frame = pd.DataFrame({"value": values, "sector": sectors}).dropna()
    groups = frame.groupby("sector").value
    count = groups.transform("count")
    return (groups.rank(method="average") - (count + 1) / 2) * 2 / (count - 1).clip(lower=1)


def solve_allocation(signal, old, industry_matrix, industry_target, covariance, active_covariance,
                     benchmark_volatility, upper, settings, initial=False):
    """Variables are asset weights (including cash) and absolute trade auxiliaries."""
    signal, old, upper = (np.asarray(a, dtype=float) for a in [signal, old, upper])
    n = len(old)
    # ETF first, cash last. Initial seed is ETF core; later seed is the real ledger.
    seed = np.zeros(n)
    seed[0], seed[-1] = 1-settings["cash_weight"], settings["cash_weight"]
    if not initial:
        seed = old.copy()
    x0 = np.r_[seed, np.abs(seed-old)]
    lower = np.zeros(2*n)
    highs = np.r_[upper, np.ones(n)*2]
    lower[0] = settings["etf_min"]
    lower[n-1] = highs[n-1] = settings["cash_weight"]
    identity = np.eye(n)
    abs_matrix = np.block([[-identity, identity], [identity, identity]])
    constraints = [LinearConstraint(abs_matrix, np.r_[-old, old], np.inf),
                   LinearConstraint(np.r_[np.ones(n), np.zeros(n)][None, :], 1, 1),
                   LinearConstraint(np.c_[industry_matrix, np.zeros_like(industry_matrix)],
                                    industry_target-settings["industry_band"], industry_target+settings["industry_band"])]
    if not initial:
        constraints.append(LinearConstraint(np.r_[np.zeros(n), np.ones(n)][None, :], 0,
                                            2*settings["one_way_turnover_cap"]))
    te2 = settings["tracking_error_cap"]**2
    vol2 = (benchmark_volatility*settings["volatility_multiple"])**2
    for matrix, cap in [(active_covariance, te2), (covariance, vol2)]:
        constraints.append({"type": "ineq", "fun": lambda x, m=matrix, c=cap: 1 - (x[:n] @ m @ x[:n])/c,
                            "jac": lambda x, m=matrix, c=cap: np.r_[-2*m@x[:n]/c, np.zeros(n)]})

    def objective(x):
        return (-settings["signal_scale"]*signal@x[:n] + settings["active_variance_penalty"]*x[:n]@active_covariance@x[:n]
                + settings["two_way_trade_penalty"]*x[n:].sum())

    def derivative(x):
        return np.r_[-settings["signal_scale"]*signal + 2*settings["active_variance_penalty"]*active_covariance@x[:n],
                     np.ones(n)*settings["two_way_trade_penalty"]]

    result = minimize(lambda x: 100*objective(x), x0, jac=lambda x: 100*derivative(x), method="SLSQP", bounds=Bounds(lower, highs), constraints=constraints,
                      options={"ftol": 1e-10, "maxiter": 1000})
    weights = result.x[:n]
    audit = allocation_diagnostics(weights, old, industry_matrix, industry_target, covariance, active_covariance, benchmark_volatility)
    violations = []
    tolerance = 2e-6
    if abs(weights.sum()-1) > tolerance or (weights < -tolerance).any() or (weights-upper > tolerance).any():
        violations.append("weights")
    if weights[0] < settings["etf_min"]-tolerance or abs(weights[-1]-settings["cash_weight"]) > tolerance:
        violations.append("core_or_cash")
    for key, cap in [("industry_max_deviation", settings["industry_band"]), ("predicted_te", settings["tracking_error_cap"]),
                     ("predicted_vol", benchmark_volatility*settings["volatility_multiple"])]:
        if audit[key] > cap+tolerance:
            violations.append(key)
    if not initial and audit["one_way_turnover"] > settings["one_way_turnover_cap"]+tolerance:
        violations.append("turnover")
    audit.update({"solver_success": bool(result.success), "solver_message": str(result.message), "violations": violations,
                  "iterations": int(result.nit), "initial_turnover_exempt": initial})
    return (weights if result.success and not violations else None), audit


def allocation_diagnostics(weights, old, industries, sector_target, cov, active_cov, benchmark_vol):
    return {"industry_max_deviation": float(np.max(np.abs(industries@weights-sector_target))),
            "predicted_te": float(np.sqrt(max(0, weights@active_cov@weights))),
            "predicted_vol": float(np.sqrt(max(0, weights@cov@weights))), "benchmark_vol": float(benchmark_vol),
            "one_way_turnover": float(np.abs(weights-old).sum()/2)}


class Inputs:
    def __init__(self, panels, settings):
        self.panels, self.settings = panels, settings
        self.members = pd.read_parquet(ROOT / "data/normalized/membership.parquet")
        self.history = table("industry_history")
        self.benchmark = dated(table("benchmark")).close.reindex(panels["close"].index)
        self.benchmark_returns = self.benchmark.pct_change(fill_method=None)
        self.returns = panels["adjusted_close"].ffill().pct_change(fill_method=None)
        self.momentum = momentum_scores(panels["adjusted_close"])
        self.volatility = self.returns.rolling(60, min_periods=60).std()*np.sqrt(252)
        self.liquidity = panels["amount"].rolling(20, min_periods=15).mean()
        self.names = {}
        for path in (ROOT / "data/normalized/namechange").glob("*.parquet"):
            self.names[path.stem] = pd.read_parquet(path)
        quality = json.loads((ROOT / "artifacts/data_quality.json").read_text(encoding="utf-8"))
        self.issues = [i for i in quality["issues"] if i["severity"] in {"critical", "high"}]
        self.cache = {}

    def context(self, date):
        if date in self.cache:
            return self.cache[date]
        weights, source_date = benchmark_weights(self.members, date)
        sectors = industry_at(self.history, date)
        sector_weights = weights.groupby(pd.Series({c: sectors.get(c, "UNKNOWN") for c in weights.index})).sum()
        self.cache[date] = (weights, source_date, sectors, sector_weights)
        return self.cache[date]

    def eligible(self, date, equity):
        weights, _, sectors, _ = self.context(date)
        stamp = date.strftime("%Y%m%d")
        minimum = self.panels["close"].loc[date] * pd.Series({c: 200 if c.startswith("688") else 100 for c in self.panels["close"].columns})
        qualified = []
        excluded = {}
        for code in weights.index:
            reason = None
            if code not in self.panels["close"] or not np.isfinite(self.panels["close"].at[date, code]):
                reason = "no_quote"
            elif sectors.get(code, "UNKNOWN") == "UNKNOWN":
                reason = "unknown_industry"
            elif not self.liquidity.at[date, code] >= 10_000_000:
                reason = "liquidity"
            elif not np.isfinite(self.momentum.at[date, code]) or not np.isfinite(self.volatility.at[date, code]):
                reason = "insufficient_signal_history"
            elif minimum[code] > equity*self.settings["stock_cap"]:
                reason = "minimum_lot_exceeds_cap"
            names = self.names.get(code)
            if reason is None and names is not None and len(names):
                known = names.loc[names.start_date.le(stamp) & (names.end_date.isna() | names.end_date.ge(stamp))]
                if len(known) and known.name.str.contains("ST|退", regex=True).any():
                    reason = "risk_warning_name"
            # Only known past events crossing the signal/risk window; no future blacklist.
            start = self.panels["close"].index[max(0, self.panels["close"].index.get_loc(date)-252)]
            for issue in self.issues:
                if issue["code"] == code and any(start <= pd.Timestamp(d) <= date for d in (issue.get("dates") or [issue.get("date", issue.get("ex_date"))]) if d):
                    reason = "unresolved_past_event"
            if reason:
                excluded[code] = reason
            else:
                qualified.append(code)
        return qualified, excluded


class StartupBudget:
    """The initial turnover exemption ends after the first actual investment."""
    def __init__(self):
        self.ever_invested = False

    def exempt(self, actual):
        self.ever_invested |= any(weight > 1e-9 for weight in actual.values())
        return not self.ever_invested


class DecisionMaker:
    def __init__(self, inputs, strategy):
        self.inputs, self.strategy, self.settings = inputs, strategy, inputs.settings
        self.audit = []
        self.startup = StartupBudget()
        self.last_share_target = None

    def __call__(self, date, actual, cash_weight, equity, initial=False):
        s, data = self.settings, self.inputs
        initial = self.startup.exempt(actual)
        self.last_share_target = None
        if self.strategy == "etf_reference":
            self.audit.append({"date": str(date.date()), "status": "etf_reference", "initial": initial})
            return {ETF: 1-s["cash_weight"]}
        _weights, source_date, sectors, sector_target = data.context(date)
        qualified, excluded = data.eligible(date, equity)
        sector_series = pd.Series({c: sectors[c] for c in qualified})
        signal = within_sector(data.momentum.loc[date, qualified], sector_series)
        if self.strategy == "defensive_constrained":
            signal = (signal + within_sector(-data.volatility.loc[date, qualified], sector_series))/2
        ranking = signal.sort_index().sort_values(ascending=False, kind="stable")
        # A deterministic sector seed avoids a candidate list containing only one industry.
        seeds = ranking.groupby(sector_series.reindex(ranking.index), sort=True).head(1).index.tolist()
        chosen = list(dict.fromkeys(seeds + ranking.index.tolist()))[:s["candidate_count"]]
        stocks = sorted((set(chosen) | set(actual)) - {ETF})
        codes = [ETF] + stocks + [CASH]
        returns = data.returns.loc[:date, codes[:-1]].tail(s["risk_window"]).copy()
        if len(returns) < s["risk_minimum"] or returns.count().min() < s["risk_minimum"]:
            self.audit.append({"date": str(date.date()), "status": "risk_data_unavailable_hold", "excluded": excluded})
            return None
        returns = returns.fillna(returns.mean())
        returns[CASH] = 0.0
        benchmark = data.benchmark_returns.reindex(returns.index)
        if benchmark.isna().any():
            raise ValueError("Missing benchmark risk return")
        cov = shrunk_covariance(returns.to_numpy(), s["diagonal_shrinkage"])
        active_cov = shrunk_covariance(returns.sub(benchmark, axis=0).to_numpy(), s["diagonal_shrinkage"])
        bench_vol = float(benchmark.std()*np.sqrt(252))
        groups = sorted(set(sector_target.index) | {sectors.get(c, "UNKNOWN") for c in stocks})
        matrix = np.zeros((len(groups), len(codes)))
        target_sector = sector_target.reindex(groups).fillna(0).to_numpy()
        matrix[:, 0] = target_sector
        for n, code in enumerate(stocks, 1):
            matrix[groups.index(sectors.get(code, "UNKNOWN")), n] = 1
        old = np.array([actual.get(c, cash_weight if c == CASH else 0) for c in codes])
        alpha = np.array([0 if c in {ETF, CASH} else signal.get(c, -1) for c in codes])
        # No additions to excluded/off-pool retained holdings; orderly exit remains subject to turnover budget.
        upper = np.array([1] + [s["stock_cap"] if c in chosen else min(s["stock_cap"], actual.get(c, 0)) for c in stocks] + [s["cash_weight"]])
        optimal, audit = solve_allocation(alpha, old, matrix, target_sector, cov, active_cov, bench_vol, upper, s, initial)
        continuous_audit = audit.copy()
        fallback = False
        if optimal is None and initial:
            optimal = np.zeros(len(codes))
            optimal[0], optimal[-1] = 1-s["cash_weight"], s["cash_weight"]
            fallback = True
        projected, projection = project_lots(optimal, codes, old, data.panels["close"].loc[date], equity,
                                            matrix, target_sector, cov, active_cov, bench_vol, upper, s, initial)
        optimal = projected
        audit.update(projection)
        audit["continuous_solver"] = continuous_audit
        audit["initial_etf_fallback"] = fallback
        before = allocation_diagnostics(old, old, matrix, target_sector, cov, active_cov, bench_vol)
        audit.update({"date": str(date.date()), "weight_snapshot": source_date,
                      "status": "accepted" if optimal is not None else "infeasible_or_solver_failed_hold",
                      "actual_before": before, "unknown_benchmark_weight": float(sector_target.get("UNKNOWN", 0)),
                      "equity": equity, "qualified": len(qualified), "excluded": excluded,
                      "candidates": chosen, "signal": {c: float(signal.get(c, -1)) for c in stocks},
                      "industry": {c: sectors.get(c, "UNKNOWN") for c in stocks}})
        self.audit.append(audit)
        if optimal is None:
            return None
        self.last_share_target = projection.get("reference_shares")
        return {c: float(max(0, w)) for c, w in zip(codes[:-1], optimal[:-1]) if w > 1e-9}


def project_lots(optimal, codes, old, prices, equity, matrix, target_sector, cov, active_cov, bench_vol, upper, settings, initial):
    """Integer nearest-target projection, with validated convex-risk outer cuts.

    This is feasibility engineering at the current date, never a return search.
    Fixed interior buffers reserve space for fees and price movement but do not
    guarantee continuous compliance after fills or subsequent market drift.
    """
    if optimal is None:
        return None, {"projection_status": "no_continuous_solution"}
    n = len(codes)
    units = np.array([200 if c.startswith("688") else 100 for c in codes[:-1]])
    quotes = prices.reindex(codes[:-1]).to_numpy(float)
    valid = np.isfinite(quotes) & (quotes > 0)
    scales = np.r_[np.where(valid, units*quotes/equity, 1), 1.0]
    transform = np.diag(scales)
    cap = upper.copy()
    cap[1:-1] = np.minimum(cap[1:-1], .029)
    maximum = np.r_[np.floor(cap[:-1]/scales[:-1]+1e-8), .007]
    maximum[:-1][~valid] = 0
    minimum = np.zeros(n)
    minimum[0] = np.ceil(settings["etf_min"]/scales[0]-1e-8)
    minimum[-1] = settings["cash_weight"]
    # Variables: integer asset units, cash weight, target distance, actual trades.
    bounds = Bounds(np.r_[minimum, np.zeros(2*n)], np.r_[maximum, np.ones(2*n)*2])
    rows, lows, highs = [], [], []

    def add(a, lo, hi):
        rows.append(np.atleast_2d(a))
        lows.extend(np.broadcast_to(lo, rows[-1].shape[0]))
        highs.extend(np.broadcast_to(hi, rows[-1].shape[0]))

    zero = np.zeros((n, n))
    identity = np.eye(n)
    add(np.r_[scales, np.zeros(2*n)], 1, 1)
    add(np.c_[matrix@transform, np.zeros((len(matrix), 2*n))], target_sector-.028, target_sector+.028)
    add(np.c_[transform, -identity, zero], -np.inf, optimal)
    add(np.c_[-transform, -identity, zero], -np.inf, -optimal)
    add(np.c_[transform, zero, -identity], -np.inf, old)
    add(np.c_[-transform, zero, -identity], -np.inf, -old)
    if not initial:
        add(np.r_[np.zeros(2*n), np.ones(n)], 0, 2*.14)
    risk_limits = [(active_cov, .038), (cov, bench_vol*1.08)]
    objective = np.r_[np.zeros(n), np.ones(n), np.ones(n)*.001]
    integrality = np.r_[np.ones(n-1), np.zeros(2*n+1)]
    last_message = "not_started"
    for iteration in range(12):
        solved = milp(objective, integrality=integrality, bounds=bounds,
                      constraints=LinearConstraint(np.vstack(rows), lows, highs),
                      options={"time_limit": 2.0, "mip_rel_gap": .001})
        last_message = str(solved.message)
        if solved.x is None:
            break
        x = solved.x[:n].copy()
        x[:-1] = np.rint(x[:-1])
        w = scales*x
        audit = allocation_diagnostics(w, old, matrix, target_sector, cov, active_cov, bench_vol)
        violations = []
        for risk, limit in risk_limits:
            norm = float(np.sqrt(max(0, w@risk@w)))
            if norm > limit+1e-7:
                gradient = risk@w/norm
                add(np.r_[gradient*scales, np.zeros(2*n)], -np.inf, limit)
                violations.append("risk_outer_cut")
        linear_ok = (abs(w.sum()-1) < 1e-6 and np.all(w >= -1e-8)
                     and np.all(w[:-1] <= upper[:-1]+1e-6)
                     and settings["cash_weight"]-1e-6 <= w[-1] <= .007001
                     and w[0] >= settings["etf_min"]-1e-6
                     and audit["industry_max_deviation"] <= .028001
                     and (initial or audit["one_way_turnover"] <= .140001))
        if not violations and linear_ok:
            return w, {**audit, "projection_status": "integer_passed", "integer_iterations": iteration+1,
                       "mip_message": last_message, "mip_gap": float(getattr(solved, "mip_gap", 0)),
                       "reference_shares": {c: int(q*u) for c, q, u in zip(codes[:-1], x[:-1], units)},
                       "violations": [], "cash_target": float(w[-1])}
        if not linear_ok:
            break
    return None, {"projection_status": "no_integer_feasible_target", "mip_message": last_message}

