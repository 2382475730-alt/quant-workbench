"""Pre-registered, resumable, immutable-result local research runner."""
from __future__ import annotations

import argparse
import json
import time
import traceback
from dataclasses import asdict
from datetime import UTC, datetime

import numpy as np
import pandas as pd

from ..data import ROOT
from ..enhancement_data import table
from ..metrics import metrics, returns_from_nav
from ..research import fingerprints
from ..validation import index_reference
from .allocator import Budget, Costs
from .data import BASE, DATA, digest, dump, load, validate
from .engine import simulate

PHASES = {"development": ["2017-01-03", "2021-12-31"], "validation": ["2022-01-04", "2024-12-31"],
          "review": ["2025-01-02", "2026-10-23"]}
STRATEGIES = ["single", "fixed", "risk", "band"]
SCENARIOS = ["base", "double_cost", "delay_2", "miss_fourth", "partial", "staged"]


def registry():
    runs = []

    def add(phase, strategy, scenario="base", initial=100000, annual_fee=0, monthly_contribution=0):
        row = {"phase": phase, "strategy": strategy, "scenario": scenario, "initial": initial,
                   "annual_fee": annual_fee, "monthly_contribution": monthly_contribution}
        row["id"] = f"{phase}_{strategy}_{scenario}_{initial}_fee{annual_fee}_flow{monthly_contribution}"
        runs.append(row)

    for phase in PHASES:
        for strategy in STRATEGIES:
            for scenario in SCENARIOS:
                add(phase, strategy, scenario)
            for capital in [50000, 200000, 500000]:
                add(phase, strategy, initial=capital)
            for fee in [300, 600, 1200]:
                add(phase, strategy, annual_fee=fee)
        add(phase, "legacy")
    for strategy in STRATEGIES:
        add("review", strategy, monthly_contribution=1000)
    assert len(runs) == 151 and len({x["id"] for x in runs}) == 151
    return {"version": "small_capital_v1", "phases": PHASES, "budget": asdict(Budget()), "costs": asdict(Costs()),
            "evidence": "retrospective_all_history_seen", "runs": runs}


def hashes():
    paths = list((ROOT / "src/quant_workbench/small_capital_v1").glob("*.py"))
    # Presentation and agent wrappers can be developed without changing the engine seal.
    paths = [p for p in paths if p.stem in {"__init__", "data", "allocator", "engine", "runner"}]
    paths += [ROOT / "research/small_capital_v1/protocol.md", ROOT / "research/small_capital_v1/revisions.md",
              ROOT / "config/small_capital_v1.json"]
    paths += [p for p in DATA.glob("*") if p.is_file()]
    paths += list((ROOT / "data/enhancement_v1").glob("*.parquet"))
    paths += [ROOT / f"src/quant_workbench/{x}.py" for x in ["enhancement_optimizer_r4", "enhancement_engine_r3", "enhancement_data"]]
    paths += [ROOT / "config/enhancement_v1r4.json"]
    result = fingerprints()
    result.update({str(p.relative_to(ROOT)): digest(p) for p in paths})
    return result


def freeze():
    if (BASE / "freeze.json").exists():
        return check_freeze()
    path = ROOT / "config/small_capital_v1.json"
    if not path.exists():
        dump(path, registry())
    elif json.loads(path.read_text(encoding="utf-8")) != registry():
        raise ValueError("Registration and implementation differ")
    validate(load())
    record = {"created_at": datetime.now(UTC).isoformat(), "hashes": hashes(), "registered_runs": 151,
              "config": registry(), "forward_days": 0}
    dump(BASE / "freeze.json", record)
    return record


def check_freeze():
    record = json.loads((BASE / "freeze.json").read_text(encoding="utf-8"))
    if record["hashes"] != hashes():
        changed = [k for k in set(record["hashes"]) | set(hashes()) if record["hashes"].get(k) != hashes().get(k)]
        raise ValueError(f"Frozen inputs changed: {changed}")
    return record


def verify_run(path):
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    for name, expected in manifest.items():
        if digest(path / name) != expected:
            raise ValueError(f"Changed output {path.name}/{name}")
    nav = pd.read_parquet(path / "nav.parquet")
    positions = pd.read_parquet(path / "positions.parquet")
    trades = pd.read_parquet(path / "trades.parquet")
    values = positions.assign(value=positions.shares*positions.mark).groupby("date").value.sum() if len(positions) else pd.Series(dtype=float)
    balance = values.reindex(nav.index).fillna(0)+nav.cash+nav.receivable-nav.get("payable", 0)
    if not np.allclose(balance, nav.equity, atol=.000001, rtol=1e-11) or nav.cash.lt(-1e-7).any():
        raise ValueError("Wealth balance mismatch")
    if len(trades) and not (pd.to_datetime(trades.date) > pd.to_datetime(trades.decision_date)).all():
        raise ValueError("Execution before available signal")
    result = json.loads((path / "result.json").read_text(encoding="utf-8"))
    if result["strategy"] != "legacy":
        cash_ledger = pd.read_parquet(path / "cash_ledger.parquet")
        movements = cash_ledger.loc[cash_ledger.type.isin(["external_contribution", "dividend_paid", "service_fee_paid"])]
        daily_cash = movements.groupby("date").amount.sum()
        daily_cash.index = pd.to_datetime(daily_cash.index)
        trade_cash = (trades.assign(movement=-trades.shares*trades.price-trades.fee).groupby("date").movement.sum()
                      if len(trades) else pd.Series(dtype=float))
        trade_cash.index = pd.to_datetime(trade_cash.index)
        rebuilt = result["initial"]+(daily_cash.reindex(nav.index).fillna(0)+trade_cash.reindex(nav.index).fillna(0)).cumsum()
        if not np.allclose(rebuilt, nav.cash, atol=.000001, rtol=1e-11):
            raise ValueError("Cash flow reconciliation failed")
        daily_returns = nav.equity/(nav.equity.shift().fillna(result["initial"])+nav.external_flow)-1
        if not np.allclose((1+daily_returns).cumprod()*result["initial"], nav.twr_equity):
            raise ValueError("TWR flow reconciliation failed")
    return len(manifest)


def save_result(path, result, spec):
    for name, frame in result.items():
        if isinstance(frame, pd.DataFrame):
            frame.to_parquet(path / f"{name}.parquet")
        else:
            dump(path / f"{name}.json", frame)
    nav = result["nav"]
    initial = spec["initial"]
    evaluated = nav.copy()
    if "twr_equity" in nav:
        evaluated["equity"] = nav.twr_equity
    row = spec | metrics(evaluated, result["trades"], initial)
    benchmark = index_reference(table("benchmark"), nav.index, initial)
    benchmark.to_parquet(path / "benchmark.parquet")
    a, z = returns_from_nav(evaluated, initial), returns_from_nav(benchmark, initial)
    row.update({"status": "complete", "ending_equity": float(nav.equity.iloc[-1]),
                "benchmark_return": float(benchmark.equity.iloc[-1]/initial-1),
                "tracking_error_hs300": float((a-z).std()*np.sqrt(252)),
                "cash_average": float((nav.cash/nav.equity).mean()),
                "cash_opportunity_proxy": float(((nav.cash/nav.equity).shift().fillna(1)*z).sum()),
                "risk_breach_days": int(nav.risk_breach.sum()) if "risk_breach" in nav else None,
                "exposure_breach_days": int(nav.exposure_breach.sum()) if "exposure_breach" in nav else None,
                "service_fees": float(nav.service_accrued.iloc[-1]) if "service_accrued" in nav else 0.,
                "service_unpaid": float(nav.payable.iloc[-1]) if "payable" in nav else 0.,
                "external_contributions": float(nav.external_flow_cumulative.iloc[-1]) if "external_flow_cumulative" in nav else 0.,
                "net_investment_profit": float(nav.equity.iloc[-1]-initial-nav.get("external_flow_cumulative", pd.Series([0.])).iloc[-1]),
                "orders": len(result.get("orders", [])), "execution_events": len(result["events"]),
                "failed_or_held_decisions": sum(x["status"] in {"no_integer_feasible_target_hold", "cash_reserve_infeasible_hold", "insufficient_risk_history", "infeasible_or_solver_failed_hold"} for x in result["audit"]),
                "no_trade_decisions": sum(x["status"] in {"within_no_trade_band", "integer_hold", "buy_hold"} for x in result["audit"]),
                "risk_priority_overrides": sum(x["status"] == "risk_reduction_override" for x in result["audit"]),
                "annual": [{"year": int(y), "return": float((1+a.loc[a.index.year == y]).prod()-1),
                            "index_return": float((1+z.loc[z.index.year == y]).prod()-1)} for y in sorted(a.index.year.unique())],
                "evidence": "retrospective; no forward evidence"})
    dump(path / "result.json", row)
    dump(path / "manifest.json", {p.name: digest(p) for p in path.iterdir() if p.is_file() and p.name != "manifest.json"})
    verify_run(path)
    return row


def run(minutes=120, only=None):
    sealed = check_freeze()
    deadline = time.monotonic()+minutes*60
    market = load()
    legacy_inputs = None
    results = []
    # Basic comparisons first, then fees, other stress/scales; never select by returns.
    ordered = sorted(sealed["config"]["runs"], key=lambda r: (r["initial"] != 100000, r["scenario"] != "base", r["annual_fee"] > 0, r["monthly_contribution"] > 0))
    for spec in ordered:
        if only and spec["strategy"] != only:
            continue
        path = BASE / "runs" / spec["id"]
        if (path / "manifest.json").exists():
            verify_run(path)
            results.append(json.loads((path / "result.json").read_text(encoding="utf-8")))
            continue
        if path.exists():
            print(json.dumps({"id": spec["id"], "status": "prior_failure_or_incomplete_retained"}), flush=True)
            continue
        if time.monotonic() >= deadline:
            break
        path.mkdir(parents=True)
        dump(path / "started.json", {"at": datetime.now(UTC).isoformat(), "spec": spec})
        print(json.dumps({"id": spec["id"], "stage": "running"}), flush=True)
        try:
            start, end = PHASES[spec["phase"]]
            if spec["strategy"] == "legacy":
                from ..enhancement_data import load as legacy_load
                from ..enhancement_engine_r3 import Costs as LegacyCosts
                from ..enhancement_engine_r3 import simulate as legacy_simulate
                from ..enhancement_optimizer_r4 import DecisionMaker, Inputs
                from ..enhancement_research_r4 import actual_constraints
                from ..research import decision_dates
                if legacy_inputs is None:
                    panels, actions = legacy_load()
                    settings = json.loads((ROOT / "config/enhancement_v1r4.json").read_text())
                    settings["initial_cash"] = 100000
                    legacy_inputs = Inputs(panels, settings)
                maker = DecisionMaker(legacy_inputs, "momentum_constrained")
                result = legacy_simulate(panels, {}, actions, initial_cash=100000, costs=LegacyCosts(), start=start, end=end,
                                         decision_factory=maker, rebalance_dates=decision_dates(panels["close"].index, start, end), etf_codes={"510300.SH"})
                result["audit"] = maker.audit
                actual, turnover, summary = actual_constraints(result, legacy_inputs, maker.audit)
                result["actual_constraints"] = actual
                result["constraint_summary"] = summary
                result["turnover"] = turnover
            else:
                result = simulate(market, start, end, **{k: v for k, v in spec.items() if k not in {"id", "phase"}})
            row = save_result(path, result, spec)
            results.append(row)
            print(json.dumps({"id": spec["id"], "stage": "complete", "return": row["total_return"]}), flush=True)
        except Exception as exc:  # noqa: BLE001 -- preserve every experiment failure and continue fixed registry
            dump(path / "failure.json", {"at": datetime.now(UTC).isoformat(), "error": str(exc), "traceback": traceback.format_exc(), "spec": spec})
            print(json.dumps({"id": spec["id"], "stage": "failed", "error": str(exc)}), flush=True)
    dump(BASE / "status.json", status())
    return status()


def status():
    return {"registered": 151, "completed": len(list((BASE / "runs").glob("*/manifest.json"))),
            "failed": len(list((BASE / "runs").glob("*/failure.json"))), "frozen": (BASE / "freeze.json").exists(),
            "forward_days": 0, "broker_connected": False, "stage": "research_prototype"}


def verify():
    check_freeze()
    before = json.loads((BASE / "legacy_before.json").read_text(encoding="utf-8"))
    changed = [p for p, h in before["hashes"].items() if digest(ROOT / p) != h]
    if changed:
        raise ValueError(f"Legacy changed: {changed}")
    files = sum(verify_run(p.parent) for p in (BASE / "runs").glob("*/manifest.json"))
    result = status() | {"legacy_files_unchanged": len(before["hashes"]), "run_files_verified": files, "integrity": "passed"}
    dump(BASE / "verification.json", result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["freeze", "run", "verify", "status"])
    parser.add_argument("--minutes", type=float, default=120)
    parser.add_argument("--only", choices=STRATEGIES+["legacy"])
    args = parser.parse_args()
    if not 0 < args.minutes <= 180:
        parser.error("Budget must be in (0,180]")
    if args.command == "freeze":
        result = {"inputs": len(freeze()["hashes"]), "registered": 151}
    elif args.command == "run":
        result = run(args.minutes, args.only)
    elif args.command == "verify":
        result = verify()
    else:
        result = status()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
