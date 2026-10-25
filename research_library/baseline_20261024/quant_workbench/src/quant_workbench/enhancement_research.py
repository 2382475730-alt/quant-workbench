"""Versioned experiment runner with sealed inputs and fully retained failures."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime

import numpy as np
import pandas as pd

from .data import ROOT, write_json
from .enhancement_data import BASE, ETF, OUT, config, load, table, validate
from .enhancement_engine import Costs, simulate
from .enhancement_optimizer import DecisionMaker, Inputs
from .metrics import compare, metrics, returns_from_nav
from .research import decision_dates, fingerprints
from .validation import holding_quality, index_reference


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def input_hashes():
    result = fingerprints()
    paths = [ROOT / f"src/quant_workbench/{name}.py" for name in
             ["enhancement_data", "enhancement_optimizer", "enhancement_engine", "enhancement_research"]]
    paths += [ROOT / "config/enhancement_v1.json", ROOT / "research/enhancement_v1_protocol.md"]
    paths += list(BASE.glob("*.parquet"))
    # Historical warning names are an actual input, so include them in this version's seal.
    paths += list((ROOT / "data/normalized/namechange").glob("*.parquet"))
    paths += [OUT / "source_receipts.json"]
    result.update({str(p.relative_to(ROOT)): digest(p) for p in paths})
    return result


def freeze():
    path = OUT / "freeze.json"
    if path.exists():
        check_freeze()
        return json.loads(path.read_text(encoding="utf-8"))
    validate()
    record = {"created_at": datetime.now(UTC).isoformat(), "hashes": input_hashes(),
              "research_status": "All historical periods previously seen; not a new holdout",
              "registered_runs": 27, "config": config()}
    write_json("artifacts/enhancement_v1/freeze.json", record)
    return record


def check_freeze():
    path = OUT / "freeze.json"
    if not path.exists():
        raise RuntimeError("Freeze protocol and audited inputs before running")
    saved = json.loads(path.read_text(encoding="utf-8"))
    current = input_hashes()
    changed = [k for k in set(saved["hashes"]) | set(current) if saved["hashes"].get(k) != current.get(k)]
    if changed:
        raise RuntimeError(f"Frozen inputs changed: {changed}")
    return saved


def active_metrics(nav, benchmark, initial=1e6):
    a, b = returns_from_nav(nav, initial), returns_from_nav(benchmark, initial)
    difference = a-b
    te = float(difference.std()*np.sqrt(252))
    comp = compare(nav, benchmark, initial)
    # Bonferroni across six new active strategy/period comparisons. Exploratory only.
    values = difference.to_numpy()
    block, count = 20, 4000
    rng = np.random.default_rng(20261024)
    starts = rng.integers(0, len(values)-block+1, (count, (len(values)+block-1)//block))
    idx = (starts[:, :, None]+np.arange(block)).reshape(count, -1)[:, :len(values)]
    means = values[idx].mean(axis=1)*252
    bounds = np.quantile(means, [.05/(2*6), 1-.05/(2*6)])
    return {**comp, "tracking_error": te,
            "information_ratio": float(difference.mean()*252/te) if te > 1e-10 else None,
            "geometric_relative_return": float(nav.equity.iloc[-1]/benchmark.equity.iloc[-1]-1),
            "annualized_return_difference": float((nav.equity.iloc[-1]/initial)**(252/len(nav))-(benchmark.equity.iloc[-1]/initial)**(252/len(nav))),
            "familywise_lower": float(bounds[0]), "familywise_upper": float(bounds[1]),
            "interval_scope": "20-day blocks, Bonferroni six new base active strategy-period comparisons; does not remove prior research selection",
            "rolling_63d_te_max": float((difference.rolling(63, min_periods=63).std()*np.sqrt(252)).max())}


def actual_constraints(result, inputs, decisions):
    records = []
    positions = result["positions"]
    by_date = {d: f for d, f in positions.groupby("date")} if len(positions) else {}
    for date, nav in result["nav"].iterrows():
        _, _, sectors, target = inputs.context(date)
        held = by_date.get(date, pd.DataFrame(columns=["code", "weight"]))
        weight = held.set_index("code").weight
        exposure = target * weight.get(ETF, 0)
        for code, w in weight.items():
            if code != ETF:
                sector = sectors.get(code, "UNKNOWN")
                exposure.loc[sector] = exposure.get(sector, 0)+w
        difference = exposure.subtract(target, fill_value=0)
        stocks = weight.drop(ETF, errors="ignore")
        records.append({"date": str(date.date()), "industry_max_deviation": float(difference.abs().max()),
                        "direct_stock_max": float(stocks.max()) if len(stocks) else 0,
                        "etf_weight": float(weight.get(ETF, 0)), "cash_weight": float((nav.cash+nav.receivable)/nav.equity),
                        "unknown_industry_exposure": float(exposure.get("UNKNOWN", 0))})
    daily = pd.DataFrame(records)
    turnover = []
    trades = result["trades"]
    decision_equities = {x["date"]: x.get("equity") for x in decisions}
    if len(trades):
        for date, group in trades.groupby("decision_date"):
            nav_before = result["nav"].loc[result["nav"].index <= pd.Timestamp(date)]
            equity = decision_equities.get(date) or (float(nav_before.equity.iloc[-1]) if len(nav_before) else inputs.settings["initial_cash"])
            buys = group.loc[group.shares.gt(0), "notional"].sum()
            sells = group.loc[group.shares.lt(0), "notional"].sum()
            turnover.append({"decision_date": date, "one_way_executed": float(max(buys, sells)/equity),
                             "initial_exempt": pd.Timestamp(date) < result["nav"].index[0]})
    summary = {"industry_violation_days": int(daily.industry_max_deviation.gt(inputs.settings["industry_band"]+2e-6).sum()),
               "max_actual_industry_deviation": float(daily.industry_max_deviation.max()),
               "direct_stock_cap_violation_days": int(daily.direct_stock_max.gt(inputs.settings["stock_cap"]+2e-6).sum()),
               "core_floor_violation_days": int(daily.etf_weight.lt(inputs.settings["etf_min"]-2e-6).sum()),
               "executed_turnover_violations": sum(x["one_way_executed"] > inputs.settings["one_way_turnover_cap"]+2e-6 for x in turnover if not x["initial_exempt"]),
               "max_monthly_one_way_excluding_initial": max((x["one_way_executed"] for x in turnover if not x["initial_exempt"]), default=0),
               "scope": "Daily industry/direct-stock/core checks include initial execution lag. Estimated TE/vol checked at decisions; realized TE reported separately. No claim of continuous hard enforcement."}
    return daily, turnover, summary


def run(phase):
    seal = check_freeze()
    settings = seal["config"]
    start, end = settings["phases"][phase]
    panels, actions = load()
    inputs = Inputs(panels, settings)
    quality = json.loads((ROOT / "artifacts/data_quality.json").read_text(encoding="utf-8"))
    dates = decision_dates(panels["close"].index, start, end)
    folder = OUT / "runs" / phase
    folder.mkdir(parents=True, exist_ok=True)
    summaries = []
    for strategy in settings["strategies"]:
        for scenario in settings["scenarios"]:
            experiment = f"{strategy}_{scenario}"
            path = folder / experiment
            if (path / "result.json").exists():
                summaries.append(json.loads((path / "result.json").read_text(encoding="utf-8")))
                continue
            if path.exists():
                raise RuntimeError(f"Incomplete existing run: {path}; inspect instead of overwriting")
            path.mkdir()
            maker = DecisionMaker(inputs, strategy)
            print(json.dumps({"phase": phase, "experiment": experiment, "stage": "running"}), flush=True)
            result = simulate(panels, {}, actions, initial_cash=settings["initial_cash"],
                              costs=Costs(multiplier=2 if scenario == "double_cost" else 1),
                              start=start, end=end, execution_delay=2 if scenario == "extra_delay" else 1,
                              decision_factory=maker, rebalance_dates=dates, etf_codes={ETF})
            for key in ["nav", "trades", "events", "positions"]:
                result[key].to_parquet(path / f"{key}.parquet")
            for key, value in [("decisions", result["decisions"]), ("optimization_audit", maker.audit)]:
                (path / f"{key}.json").write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
            benchmark = index_reference(table("benchmark"), result["nav"].index, settings["initial_cash"])
            benchmark.to_parquet(path / "benchmark.parquet")
            audit, turnover, constraints = actual_constraints(result, inputs, maker.audit)
            audit.to_parquet(path / "actual_constraints.parquet", index=False)
            (path / "executed_turnover.json").write_text(json.dumps(turnover, indent=2), encoding="utf-8")
            accounting = holding_quality(result, quality)
            row = {"id": experiment, "phase": phase, "strategy": strategy, "scenario": scenario,
                   **metrics(result["nav"], result["trades"], settings["initial_cash"]),
                   "vs_total_return_index": active_metrics(result["nav"], benchmark, settings["initial_cash"]),
                   "actual_constraints": constraints, "holding_quality": accounting,
                   "solver_failed_or_held": sum(x["status"] not in {"accepted", "etf_reference"} for x in maker.audit),
                   "decision_count": len(maker.audit), "accepted_target_count": len(result["decisions"]),
                   "research_status": settings["evidence_status"],
                   "data_gate_passed": not bool(accounting["unresolved_events_held"])}
            row["annual"] = []
            a, b = returns_from_nav(result["nav"]), returns_from_nav(benchmark)
            for year in sorted(a.index.year.unique()):
                row["annual"].append({"year": int(year), "strategy_return": float((1+a.loc[a.index.year == year]).prod()-1),
                                      "index_return": float((1+b.loc[b.index.year == year]).prod()-1)})
            (path / "result.json").write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")
            # A receipt detects accidental changes on resume; never silently regenerate a completed run.
            manifest = {p.name: digest(p) for p in path.iterdir() if p.is_file()}
            (path / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            summaries.append(row)
            print(json.dumps({"phase": phase, "experiment": experiment, "stage": "complete",
                              "return": row["total_return"], "failed_decisions": row["solver_failed_or_held"]}), flush=True)
    write_json(f"artifacts/enhancement_v1/runs/{phase}/summary.json", {"complete": len(summaries) == 9, "results": summaries,
               "freeze_sha256": digest(OUT / "freeze.json"), "start": start, "end": end})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["freeze", "verify", "development", "validation", "review"])
    args = parser.parse_args()
    if args.command == "freeze":
        print(json.dumps({"frozen_inputs": len(freeze()["hashes"])}))
    elif args.command == "verify":
        print(json.dumps({"verified_inputs": len(check_freeze()["hashes"])}))
    else:
        run(args.command)
