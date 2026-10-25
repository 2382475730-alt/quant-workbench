"""Independent presentation audit; never rewrites a sealed ledger or result."""
from __future__ import annotations

import json

import pandas as pd


def startup_turnover_audit(trades, turnover, cap=.15):
    """First actual investment, not first date in a backtest, defines startup."""
    buys = trades.loc[trades.shares.gt(0)] if len(trades) else trades
    first_fill = pd.to_datetime(buys.date.astype(str)).min() if len(buys) else None
    records = []
    for record in turnover:
        exempt = bool(first_fill is None or pd.Timestamp(record["decision_date"]) < first_fill)
        records.append({**record, "recorded_initial_exempt": record["initial_exempt"], "initial_exempt": exempt})
    return {"records": records,
            "changed_exemption_flags": sum(r["recorded_initial_exempt"] != r["initial_exempt"] for r in records),
            "executed_turnover_violations": sum(r["one_way_executed"] > cap+2e-6 for r in records if not r["initial_exempt"]),
            "max_monthly_one_way_excluding_initial": max((r["one_way_executed"] for r in records if not r["initial_exempt"]), default=0)}


def load_result(folder):
    result = json.loads((folder/"result.json").read_text(encoding="utf-8"))
    if "enhancement_v1r4" not in folder.parts:
        return result
    turnover = json.loads((folder/"executed_turnover.json").read_text(encoding="utf-8"))
    audit = startup_turnover_audit(pd.read_parquet(folder/"trades.parquet"), turnover)
    result["turnover_reconciliation"] = audit
    result["actual_constraints"] = {**result["actual_constraints"],
                                    "recorded_executed_turnover_violations": result["actual_constraints"]["executed_turnover_violations"],
                                    "executed_turnover_violations": audit["executed_turnover_violations"],
                                    "max_monthly_one_way_excluding_initial": audit["max_monthly_one_way_excluding_initial"]}
    return result
