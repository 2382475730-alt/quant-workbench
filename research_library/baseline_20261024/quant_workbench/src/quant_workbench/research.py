"""Pre-registered research runs with a separate, auditable final unlock."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import UTC, datetime

import pandas as pd

from .data import ROOT, write_json
from .engine import Action, Costs, simulate
from .metrics import compare, metrics
from .prepare import load_table
from .signals import historical_members, momentum_scores, portfolio_target, stock_signals
from .validation import holding_quality, index_reference, momentum_input_quality


def config():
    return json.loads((ROOT / "config/experiments.json").read_text(encoding="utf-8"))


def fingerprints():
    # Seal calculation and input lineage. Presentation-only changes must not
    # silently invalidate an otherwise identical one-time holdout experiment.
    modules = ["data", "collect", "prepare", "suspensions", "event_review", "signals", "engine", "metrics", "validation", "research"]
    configs = ["experiments", "action_overrides", "event_reviews", "listing_suspensions", "pending_exchanges"]
    paths = ([ROOT / f"src/quant_workbench/{name}.py" for name in modules]
             + [ROOT / f"config/{name}.json" for name in configs]
             + [ROOT / "pyproject.toml", ROOT / "uv.lock", ROOT / "research/protocol.md", ROOT / "artifacts/data_quality.json",
                ROOT / "data/normalized/membership.parquet", ROOT / "data/normalized/index/000300.SH.parquet"]
             + list((ROOT / "data/panels").glob("*")))
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}


def verify_repair_scope(original, current):
    for key in ["config/experiments.json", "src/quant_workbench/signals.py", "research/protocol.md"]:
        # Windows relative paths in the original manifest contain backslashes.
        lookup = {k.replace("\\", "/"): v for k, v in original.items()}
        updated = {k.replace("\\", "/"): v for k, v in current.items()}
        if lookup.get(key) is None or lookup[key] != updated.get(key):
            raise RuntimeError(f"Post-holdout repair may not change strategy rules or protocol: {key}")


def freeze(repair=False):
    for phase in ["development", "validation"]:
        summary_path = ROOT / f"artifacts/research/{phase}/summary.json"
        if not summary_path.exists():
            raise RuntimeError(f"Missing completed {phase} run")
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        if not summary.get("complete"):
            raise RuntimeError(f"Incomplete experiment coverage in {phase}")
        started = json.loads((summary_path.parent / "started.json").read_text(encoding="utf-8"))
        if started["hashes"] != fingerprints():
            raise RuntimeError(f"Stale {phase} evidence: rerun after code/config/data changes before freeze")
        if any(r.get("holding_quality", {}).get("unresolved_events_held") for r in summary["results"]):
            raise RuntimeError(f"Unresolved corporate-action exposures in {phase}; finish source review before final unlock")
        if any(r.get("signal_quality", {}).get("unresolved_candidate_windows") for r in summary["results"]):
            raise RuntimeError(f"Unresolved candidate signal inputs in {phase}")
    filename = "repair_freeze.json" if repair else "freeze.json"
    path = ROOT / "artifacts/research" / filename
    if path.exists():
        raise RuntimeError("Already frozen; do not silently replace final protocol")
    metadata = {}
    if repair:
        original = json.loads((ROOT / "artifacts/research/freeze.json").read_text(encoding="utf-8"))
        plan = ROOT / "artifacts/research/repair_plan.json"
        if not plan.exists() or not (ROOT / "artifacts/research_initial_frozen/final/summary.json").exists():
            raise RuntimeError("Repair requires the recorded plan and archived initial final evidence")
        verify_repair_scope(original["hashes"], fingerprints())
        metadata = {"repair_plan_sha256": hashlib.sha256(plan.read_bytes()).hexdigest(),
                    "interpretation": "Accounting repair after initial holdout was viewed; not a new untouched test."}
    write_json(f"artifacts/research/{filename}", {"frozen_at": datetime.now(UTC).isoformat(), "hashes": fingerprints(), **metadata})


def load_panels():
    files = sorted((ROOT / "data/panels").glob("*.parquet"))
    if not files:
        raise RuntimeError("Run prepare after full acquisition")
    panels = {p.stem: pd.read_parquet(p) for p in files}
    actions = [Action(**x) for x in json.loads((ROOT / "data/panels/actions.json").read_text())]
    return panels, actions


def decision_dates(dates, start, end, frequency="monthly"):
    valid = dates[(dates >= pd.Timestamp(start)) & (dates <= pd.Timestamp(end))]
    if len(valid) == 0:
        return []
    first_pos = dates.get_indexer([valid[0]])[0]
    initial = dates[first_pos - 1] if first_pos > 0 else valid[0]
    period = "M" if frequency == "monthly" else "W-FRI"
    # Calendar-derived rebalance dates; the last partial period is not auto-added.
    chosen = [dates[i] for i in range(len(dates) - 1)
              if dates[i].to_period(period) != dates[i + 1].to_period(period)
              and valid[0] <= dates[i] <= valid[-1]]
    return sorted(set([initial] + chosen))


def portfolio_decisions(panels, membership, spec, start, end):
    close = panels["adjusted_close"]
    scores = momentum_scores(close, spec["lookback"], spec["skip"])
    liquidity = panels["amount"].rolling(20, min_periods=15).mean()
    decisions = {}
    for date in decision_dates(close.index, start, end):
        pool = historical_members(membership, date)
        pool = [c for c in pool if c in close.columns and pd.notna(close.at[date, c])
                and liquidity.at[date, c] >= 10_000_000]
        if spec["kind"] == "equal":
            decisions[date] = {c: min(1 / len(pool), .1) for c in pool} if pool else {}
        else:
            decisions[date] = portfolio_target(scores.loc[date], pool, count=spec["count"])
    return decisions


def single_decisions(panels, code, spec, start, end):
    close = panels["adjusted_close"][code]
    trading = close.dropna()
    signals = stock_signals(close.ffill(), window=spec["window"])
    available_dates = close.index[(close.index >= pd.Timestamp(start)) & (close.index <= pd.Timestamp(end))]
    first_pos = close.index.get_indexer([available_dates[0]])[0]
    initial = close.index[max(0, first_pos - 1)]
    if spec["kind"] == "buy_hold":
        return {initial: {code: 1.0}}
    dates = decision_dates(close.index, start, end, "weekly") if spec["kind"] == "trend_risk" else close.index[(close.index >= initial) & (close.index <= pd.Timestamp(end))]
    decisions, previous = {}, None
    for date in dates:
        if date not in trading.index:
            continue
        weight = float(signals.at[date, spec["kind"]])
        # Trend strategy trades changes; volatility sizing refreshes weekly.
        if previous is None or weight != previous:
            decisions[date] = {code: weight} if weight else {}
            previous = weight
    return decisions


def run(phase):
    settings = config()
    start, end = settings["phases"]["final" if phase == "final_repaired" else phase]
    quality = json.loads((ROOT / "artifacts/data_quality.json").read_text(encoding="utf-8"))
    if quality["scope"] != "complete" or any(i["severity"] == "critical" for i in quality["issues"]):
        raise RuntimeError("Complete data audit must pass critical checks before research")
    output = ROOT / "artifacts/research" / phase
    if phase in {"final", "final_repaired"}:
        filename = "repair_freeze.json" if phase == "final_repaired" else "freeze.json"
        frozen = json.loads((ROOT / "artifacts/research" / filename).read_text())
        if frozen["hashes"] != fingerprints():
            raise RuntimeError("Code/config changed after freeze")
        if phase == "final_repaired" and frozen["repair_plan_sha256"] != hashlib.sha256((ROOT / "artifacts/research/repair_plan.json").read_bytes()).hexdigest():
            raise RuntimeError("Repair plan changed after repair freeze")
        if (output / "started.json").exists():
            raise RuntimeError("Final already opened; reruns require documented repair, not silent overwrite")
    elif output.exists() and (output / "started.json").exists():
        history = ROOT / "artifacts/research_history" / phase / datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        history.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(output, history)
    output.mkdir(parents=True, exist_ok=True)
    write_json(f"artifacts/research/{phase}/started.json", {"time": datetime.now(UTC).isoformat(), "hashes": fingerprints()})
    panels, actions = load_panels()
    active_dates = panels["close"].index[(panels["close"].index >= pd.Timestamp(start)) & (panels["close"].index <= pd.Timestamp(end))]
    index_nav = index_reference(load_table("index/000300.SH"), active_dates, settings["initial_cash"])
    index_nav.to_parquet(output / "csi300_price_reference.parquet")
    membership = load_table("membership")
    reports, results = [], {}
    experiments = []
    for spec in settings["portfolio"]:
        decisions = portfolio_decisions(panels, membership, spec, start, end)
        experiments.append(("portfolio", "pool", spec, panels, actions, decisions))
    for code in settings["single_stock_examples"]:
        subset = {f: table[[code]] for f, table in panels.items()}
        stock_actions = [a for a in actions if a.code == code]
        for spec in settings["single_stock"]:
            decisions = single_decisions(subset, code, spec, start, end)
            experiments.append(("stock", code, spec, subset, stock_actions, decisions))
    for category, code, spec, subset, relevant_actions, decisions in experiments:
        signal_audit = momentum_input_quality(subset, membership, spec, decisions, quality) if category == "portfolio" else {
            "unresolved_candidate_windows": [], "scope": "Fixed single-stock cases have no unresolved factor events in the source audit."}
        if category == "stock" and any(i["severity"] in {"critical", "high"} and i["code"] == code for i in quality["issues"]):
            raise RuntimeError(f"Single-stock source inputs require explicit review: {code}")
        variants = [("base", Costs(), 1)]
        if spec["role"] in {"primary", "primary_risk"}:
            variants += [("double_cost", Costs(multiplier=2), 1), ("extra_delay", Costs(), 2)]
        for scenario, costs, delay in variants:
            name = f"{category}_{code}_{spec['name']}_{scenario}"
            result = simulate(subset, decisions, relevant_actions, initial_cash=settings["initial_cash"],
                              costs=costs, start=start, end=end, execution_delay=delay)
            folder = output / name
            folder.mkdir(exist_ok=True)
            for key, frame in result.items():
                frame.to_parquet(folder / f"{key}.parquet")
            decision_rows = [{"date": str(d.date()), "weights": w} for d, w in decisions.items()]
            write_json(f"artifacts/research/{phase}/{name}/decisions.json", decision_rows)
            audit = holding_quality(result, quality)
            write_json(f"artifacts/research/{phase}/{name}/holding_quality.json", audit)
            row = {"id": name, "category": category, "symbol": code, "strategy": spec["name"],
                   "role": spec["role"], "scenario": scenario,
                   "holding_quality": audit, "signal_quality": signal_audit,
                   **metrics(result["nav"], result["trades"], settings["initial_cash"])}
            baseline_id = "portfolio_pool_equal_weight_base" if category == "portfolio" else f"stock_{code}_buy_hold_base"
            if baseline_id in results and name != baseline_id:
                row["comparison"] = compare(result["nav"], results[baseline_id]["nav"], settings["initial_cash"])
            row["market_price_reference_comparison"] = compare(result["nav"], index_nav, settings["initial_cash"])
            annual = []
            for year, year_nav in result["nav"].groupby(result["nav"].index.year):
                prior = result["nav"].loc[result["nav"].index < year_nav.index[0], "equity"]
                initial = float(prior.iloc[-1]) if len(prior) else settings["initial_cash"]
                annual.append({"year": int(year), "return": float(year_nav.equity.iloc[-1] / initial - 1)})
            row["annual"] = annual
            reports.append(row)
            results[name] = {"nav": result["nav"]}
            write_json(f"artifacts/research/{phase}/progress.json", {"completed": len(reports), "last": name})
            print(f"{phase}: completed {name}", flush=True)
    write_json(f"artifacts/research/{phase}/summary.json", {"phase": phase, "start": start, "end": end,
               "initial_cash": settings["initial_cash"], "results": reports, "complete": True,
               "market_reference": {"name": "CSI300 price index", **metrics(index_nav, initial=settings["initial_cash"]),
                                    "limitation": "Price index excludes dividends and trading costs; context only, primary performance benchmark is the simulated equal-weight stock portfolio."},
               "post_holdout_accounting_repair": phase == "final_repaired",
               "limitations": ["Pointwise intervals do not adjust for multiple research trials.",
                                "Historical membership uses previous-month proxy.", "Investor dividend tax excluded."]})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["development", "validation", "final", "final_repaired", "freeze", "freeze_repair"])
    args = parser.parse_args()
    if args.phase in {"freeze", "freeze_repair"}:
        freeze(repair=args.phase == "freeze_repair")
    else:
        run(args.phase)
