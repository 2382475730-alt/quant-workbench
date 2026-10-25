"""Derived, inspectable presentation artifacts; never edits sealed experiments."""
from __future__ import annotations

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from .data import ROOT, write_json
from .enhancement_audit import load_result
from .enhancement_data import ETF, benchmark_weights, industry_at, table
from .enhancement_research_r4 import active_metrics
from .holding_view import snapshot
from .metrics import metrics
from .validation import index_reference

REPORT = ROOT / "reports/enhancement_v1"
NAMES = {"etf_reference": "ETF对照", "momentum_constrained": "约束动量主方案", "defensive_constrained": "防御备选"}
PHASE_NAMES = {"development": "2017—2021回溯", "validation": "2022—2024回溯", "review": "2025—2026回溯"}
VERSIONS = ["enhancement_v1", "enhancement_v1r2", "enhancement_v1r3", "enhancement_v1r4"]


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def comparison_row(name, nav, benchmark, result=None, key=None):
    result = result or metrics(nav)
    m = active_metrics(nav, benchmark)
    return {"name": name, "key": key, **{k: result[k] for k in ["total_return", "cagr", "max_drawdown", "volatility", "average_exposure", "fees", "slippage", "annual_two_way_turnover"]},
            "annual_excess": m["annualized_return_difference"], "relative_return": m["geometric_relative_return"],
            "tracking_error": m["tracking_error"], "information_ratio": m["information_ratio"], "beta": m["beta"],
            "familywise_lower": m["familywise_lower"], "familywise_upper": m["familywise_upper"]}


def frozen_reference_audit(path, members, history):
    """Industry deviation measured against the last accepted decision's reference."""
    decisions = read(path / "decisions.json")
    positions = pd.read_parquet(path / "positions.parquet")
    if not decisions or positions.empty:
        return {"days": 0, "violation_days": 0, "max_deviation": None, "scope": "No accepted targets; not a pass"}
    decision_dates = pd.DatetimeIndex([x["date"] for x in decisions])
    cache, observations = {}, []
    for date, group in positions.groupby("date"):
        n = decision_dates.searchsorted(date, side="left")-1
        if n < 0:
            continue
        reference_date = decision_dates[n]
        if reference_date not in cache:
            weights, _ = benchmark_weights(members, reference_date)
            sectors = industry_at(history, reference_date)
            target = weights.groupby(pd.Series({c: sectors.get(c, "UNKNOWN") for c in weights.index})).sum()
            cache[reference_date] = sectors, target
        sectors, target = cache[reference_date]
        actual = target * group.set_index("code").weight.get(ETF, 0)
        for row in group.itertuples():
            if row.code != ETF:
                sector = sectors.get(row.code, "UNKNOWN")
                actual.loc[sector] = actual.get(sector, 0)+row.weight
        observations.append(float(actual.subtract(target, fill_value=0).abs().max()))
    return {"days": len(observations), "violation_days": int(sum(x > .030002 for x in observations)),
            "max_deviation": max(observations, default=None), "scope": "Last accepted decision reference; delayed fills and drift retained"}


def holding_payload(path, members, history, names):
    ledger = {k: pd.read_parquet(path / f"{k}.parquet") for k in ["nav", "positions", "trades", "events"]}
    ledger["decisions"] = read(path / "decisions.json")
    date = ledger["nav"].index[-1]
    view = snapshot(ledger, date, names)
    b, source = benchmark_weights(members, date)
    sectors = industry_at(history, date)
    sector_names = dict(zip(table("industry_codes").index_code, table("industry_codes").industry_name))
    target_sector = b.groupby(pd.Series({c: sectors.get(c, "UNKNOWN") for c in b.index})).sum()
    actual = target_sector*next((r["actual_weight"] for r in view["rows"] if r["code"] == ETF), 0)
    for row in view["rows"]:
        row["industry"] = "指数ETF底仓" if row["code"] == ETF else sector_names.get(sectors.get(row["code"]), "未知")
        if row["code"] != ETF:
            sector = sectors.get(row["code"], "UNKNOWN")
            actual.loc[sector] = actual.get(sector, 0)+row["actual_weight"]
    sectors_out = []
    for sector in sorted(set(actual.index) | set(target_sector.index)):
        sectors_out.append({"industry": sector_names.get(sector, "未知"), "benchmark_weight": float(target_sector.get(sector, 0)),
                            "actual_weight": float(actual.get(sector, 0)), "gap": float(actual.get(sector, 0)-target_sector.get(sector, 0))})
    sectors_out.sort(key=lambda r: -abs(r["gap"]))
    return {k: v for k, v in view.items() if k not in {"trades", "events"}} | {"sectors": sectors_out,
            "industry_weight_date": source, "ledger_path": str(path.relative_to(ROOT)),
            "industry_boundary": "ETF穿透使用上月指数权重代理，非基金实际日持仓；行业日期按纳入/剔除区间处理"}


def build():
    REPORT.mkdir(parents=True, exist_ok=True)
    members = pd.read_parquet(ROOT / "data/normalized/membership.parquet")
    history = table("industry_history")
    basic = pd.read_parquet(ROOT / "data/normalized/stock_basic.parquet")
    names = dict(zip(basic.ts_code, basic.name)) | {ETF: "沪深300ETF"}
    dashboard = {"asof": "2026-10-23", "version": "v1r4首次建仓状态修订", "evidence": "全部为已见历史的回溯探索，尚无新前向证据",
                 "benchmark": "沪深300全收益 H00300.CSI；含股息再投资，未扣投资者交易成本", "phases": {}}
    all_runs, comparisons, frozen_audits, turnover_audits = [], [], [], []
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    for phase, phase_label in PHASE_NAMES.items():
        current = ROOT / f"artifacts/enhancement_v1r4/runs/{phase}"
        summary = read(current / "summary.json")
        if not summary["complete"]:
            raise RuntimeError("Do not publish incomplete experiment coverage")
        summary["results"] = [load_result(current/r["id"]) for r in summary["results"]]
        turnover_audits += [{"phase": phase, "id": r["id"], **r["turnover_reconciliation"]} for r in summary["results"]]
        reference = pd.read_parquet(current / "etf_reference_base/nav.parquet")
        benchmark = index_reference(table("benchmark"), reference.index, 1e6)
        rows = [comparison_row("沪深300全收益指数", benchmark, benchmark, key="benchmark")]
        curves = pd.DataFrame({"benchmark": benchmark.equity/1e6})
        holdings = {}
        for strategy, strategy_label in NAMES.items():
            path = current / f"{strategy}_base"
            result = load_result(path)
            nav = pd.read_parquet(path / "nav.parquet")
            rows.append(comparison_row(strategy_label, nav, benchmark, result, strategy))
            curves[strategy] = nav.equity/1e6
            holdings[strategy] = holding_payload(path, members, history, names)
            pd.DataFrame(holdings[strategy]["rows"]).to_csv(REPORT/f"{phase}_{strategy}_holdings.csv", index=False, encoding="utf-8-sig")
            pd.DataFrame(holdings[strategy]["sectors"]).to_csv(REPORT/f"{phase}_{strategy}_industries.csv", index=False, encoding="utf-8-sig")
        old_phase = "final_repaired" if phase == "review" else phase
        old_summary = read(ROOT / f"artifacts/research/{old_phase}/summary.json")
        for strategy, label in [("momentum_252_20", "原动量20股"), ("equal_weight", "原同池等权")]:
            experiment = f"portfolio_pool_{strategy}_base"
            old = next(r for r in old_summary["results"] if r["id"] == experiment)
            nav = pd.read_parquet(ROOT / f"artifacts/research/{old_phase}/{experiment}/nav.parquet")
            rows.append(comparison_row(label, nav, benchmark, old, strategy))
            curves[strategy] = nav.equity/1e6
        for version in VERSIONS:
            folder = ROOT / f"artifacts/{version}/runs/{phase}"
            saved = read(folder / "summary.json")
            for r in saved["results"]:
                r = load_result(folder/r["id"])
                flat = {k: v for k, v in r.items() if not isinstance(v, (dict, list))}
                flat.update({"version": version, **{f"index_{k}": v for k, v in r["vs_total_return_index"].items() if isinstance(v, (int, float))}})
                flat.update({f"constraint_{k}": v for k, v in r["actual_constraints"].items() if isinstance(v, (int, float))})
                all_runs.append(flat)
            for strategy in ["momentum_constrained", "defensive_constrained"]:
                path = folder / f"{strategy}_base"
                audit = frozen_reference_audit(path, members, history)
                audit.update({"phase": phase, "version": version, "strategy": strategy})
                frozen_audits.append(audit)
                if version != "enhancement_v1r4":
                    result = read(path / "result.json")
                    nav = pd.read_parquet(path / "nav.parquet")
                    key = f"{version}_{strategy}"
                    rows.append(comparison_row(version.replace("enhancement_", "")+"存档·"+NAMES[strategy], nav, benchmark, result, key))
                    curves[key] = nav.equity/1e6
        etf_return = next(r["total_return"] for r in rows if r["key"] == "etf_reference")
        for row in rows:
            row["relative_to_etf"] = (1+row["total_return"])/(1+etf_return)-1
        details = {r["strategy"]: r for r in summary["results"] if r["scenario"] == "base"}
        phase_view = {"label": phase_label, "start": str(reference.index[0].date()), "end": str(reference.index[-1].date()),
                      "rows": rows, "holdings": holdings, "details": details,
                      "stress": summary["results"], "curves_file": str((REPORT/f"{phase}_curves.csv").relative_to(ROOT))}
        dashboard["phases"][phase] = phase_view
        curves.to_csv(REPORT/f"{phase}_curves.csv", index_label="date")
        comparisons += [{"phase": phase, **r} for r in rows]
        fig, axes = plt.subplots(2, 1, figsize=(11, 7), sharex=True, gridspec_kw={"height_ratios": [2, 1]})
        for key, label, color in [("benchmark", "沪深300全收益", "#a66b00"), ("etf_reference", "ETF对照", "#7b8493"),
                                  ("momentum_constrained", "约束动量 v1r4", "#176aa2"), ("defensive_constrained", "防御备选 v1r4", "#239480")]:
            axes[0].plot(curves.index, curves[key], label=label, color=color)
            if key != "benchmark":
                axes[1].plot(curves.index, (curves[key]/curves.benchmark-1)*100, label=label, color=color)
        axes[0].set_title(phase_label+" · 已见历史回溯，非新样本外")
        axes[0].set_ylabel("净值（初始100万元）")
        axes[1].set_ylabel("相对全收益指数 %")
        axes[1].axhline(0, color="#888", linewidth=.7)
        for ax in axes:
            ax.grid(alpha=.2)
        axes[0].legend(fontsize=9)
        fig.tight_layout()
        fig.savefig(REPORT/f"{phase}_comparison.png", dpi=160)
        plt.close(fig)
    pd.DataFrame(comparisons).to_csv(REPORT/"comparison.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(all_runs).to_csv(REPORT/"all_108_experiments.csv", index=False, encoding="utf-8-sig")
    write_json("reports/enhancement_v1/frozen_reference_audit.json", frozen_audits)
    write_json("reports/enhancement_v1/turnover_reconciliation.json", turnover_audits)
    write_json("reports/enhancement_v1/dashboard.json", dashboard)
    return dashboard


if __name__ == "__main__":
    build()
    print("Enhancement dashboard, tables and charts generated from sealed results")
