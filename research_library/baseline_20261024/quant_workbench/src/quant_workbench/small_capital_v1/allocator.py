"""Direct integer feasible-set allocation; no return forecasting or continuous optimizer."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Costs:
    commission: float = .0003
    minimum: float = 5.0
    slippage: float = .001
    multiplier: float = 1.0

    def fees(self, notionals):
        x = np.asarray(notionals)
        return np.where(x > 1e-8, np.maximum(self.minimum, self.commission*x)*self.multiplier, 0)


@dataclass(frozen=True)
class Budget:
    volatility: float = .18
    estimation_multiplier: float = 1.25
    max_equity: float = .95
    no_trade_band: float = .05
    min_order: float = 2000.0
    turnover: float = .25


def risk(weights, covariance):
    return float(np.sqrt(max(0, weights @ covariance @ weights)))


def allocate(prices, holdings, cash, receivable, covariance, strategy, ever_invested,
             costs=None, budget=None, fraction=1.0, payable=0.0):
    """Enumerate ALL 100-share pairs under cash cap; chunk to bound memory.

    The economic 70/30 mix is a preference, not a continuously optimized solution.
    Every integer pair is tested against costs, risk, order size, and turnover.
    Earliest code-order pair wins ties. No guarantee for next-day prices.
    """
    costs, b = costs or Costs(), budget or Budget()
    prices, held = np.asarray(prices, float), np.asarray(holdings, int)
    if len(prices) != 2 or not np.isfinite(prices).all() or (prices <= 0).any():
        raise ValueError("Two finite positive ETF reference prices required")
    if (held < 0).any() or cash < 0 or receivable < 0 or payable < 0:
        raise ValueError("Invalid cash/share state")
    equity = cash + receivable + held @ prices - payable
    if equity <= 0:
        raise ValueError("Nonpositive wealth")
    actual = held * prices / equity
    controlled = strategy in {"risk", "band"}
    if controlled and covariance is None:
        return {"status": "insufficient_risk_history", "shares": held.tolist(), "trade": False}
    mix = np.array([.7, .3])
    exposure = min(b.max_equity, b.volatility / (b.estimation_multiplier * max(risk(mix, covariance), 1e-12))) if controlled else .95
    target = np.array([.995, 0]) if strategy == "single" else mix * exposure
    target *= fraction
    estimated_before = risk(actual, covariance) if covariance is not None else None
    emergency = controlled and estimated_before * b.estimation_multiplier > b.volatility+1e-8
    base = {"target_weights": target.tolist(), "actual_weights": actual.tolist(), "equity": equity,
            "predicted_vol_before": estimated_before, "risk_reduction_priority": bool(emergency),
            "initial_turnover_exempt": not ever_invested, "scope": "reference close; not a fill"}
    if strategy == "single" and ever_invested:
        return base | {"status": "buy_hold", "shares": held.tolist(), "trade": False}
    if strategy == "band" and ever_invested and not emergency and np.max(np.abs(actual-target)) <= b.no_trade_band and payable == 0:
        return base | {"status": "within_no_trade_band", "shares": held.tolist(), "trade": False,
                       "estimated_fees": 0.0, "predicted_vol": estimated_before}
    reserve = equity * (.005 if strategy == "single" else 1-b.max_equity)
    units = prices*100
    available = cash + held @ prices - payable - reserve
    if available < 0:
        return base | {"status": "cash_reserve_infeasible_hold", "shares": held.tolist(), "trade": False}
    maxima = np.floor(available/units).astype(int)
    if strategy == "single":
        maxima[1] = 0
    # Exact 2D enumeration in chunks: no rounding after constraint validation.
    best, best_value, feasible = None, float("inf"), 0
    # Split-created odd lots may be retained, or sold in one instruction.
    n1 = np.unique(np.r_[np.arange(maxima[1]+1)*100,
                         np.arange(maxima[1]+1)*100+held[1] % 100])
    n0_all = np.unique(np.r_[np.arange(maxima[0]+1)*100,
                             np.arange(maxima[0]+1)*100+held[0] % 100])
    for offset in range(0, len(n0_all), 128):
        n0 = n0_all[offset:offset+128]
        a, z = np.meshgrid(n0, n1, indexing="ij")
        shares = np.column_stack([a.ravel(), z.ravel()])
        values = shares*prices
        weights = values/equity
        trades = np.abs((shares-held)*prices)
        fees = costs.fees(trades).sum(axis=1)
        slip = trades.sum(axis=1)*costs.slippage*costs.multiplier
        # Include half-tick adverse rounding per share as extra execution reserve.
        tick_reserve = np.abs(shares-held).sum(axis=1)*.0005
        net_equity = equity-fees-slip-tick_reserve
        weights = values/np.maximum(net_equity[:, None], 1e-12)
        remaining = cash - ((shares-held)*prices).sum(axis=1) - fees-slip-tick_reserve-payable
        valid = (remaining >= reserve-1e-8) & (net_equity > 0)
        delta = shares-held
        valid &= ((delta <= 0) | (delta % 100 == 0)).all(axis=1)
        if payable > 0:
            valid &= (shares <= held).all(axis=1)
        if controlled:
            variance = np.einsum("ij,jk,ik->i", weights, covariance, weights)
            valid &= variance <= (b.volatility/b.estimation_multiplier)**2+1e-12
            valid &= weights.sum(axis=1) <= b.max_equity+1e-10
        turnover = np.maximum(np.maximum((shares-held)*prices, 0).sum(axis=1),
                              np.maximum((held-shares)*prices, 0).sum(axis=1))/equity
        if strategy == "band" and ever_invested and not emergency:
            valid &= turnover <= b.turnover+1e-10
            valid &= ((trades == 0) | (trades >= b.min_order)).all(axis=1)
        feasible += int(valid.sum())
        # L1 target error plus a small declared fee/turnover regularizer.
        objective = np.abs(weights-target).sum(axis=1) + .001*turnover + (fees+slip)/equity*.01
        objective[~valid] = np.inf
        k = int(np.argmin(objective))
        if objective[k] < best_value:
            best_value = float(objective[k])
            best = {"shares": shares[k].tolist(), "weights": weights[k].tolist(),
                    "estimated_fees": float(fees[k]), "estimated_slippage": float(slip[k]),
                    "cash_after_reserve_costs": float(remaining[k]), "cash_reserve": reserve,
                    "one_way_turnover": float(turnover[k]), "predicted_vol": risk(weights[k], covariance) if covariance is not None else None,
                    "trade": bool(np.any(shares[k] != held))}
    if best is None:
        return base | {"status": "no_integer_feasible_target_hold", "shares": held.tolist(), "trade": False, "feasible_pairs": 0}
    return base | best | {"status": "risk_reduction_override" if emergency else "integer_feasible" if best["trade"] else "integer_hold",
                          "feasible_pairs": feasible, "objective": best_value}
