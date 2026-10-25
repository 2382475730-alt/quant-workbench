import pandas as pd
import pytest
from quant_workbench.holding_view import snapshot


def example():
    dates = pd.to_datetime(["2026-01-05", "2026-01-06"])
    return {"nav": pd.DataFrame({"equity": [1500, 1500], "cash": [480, 480], "receivable": [20, 20]}, index=dates),
            "positions": pd.DataFrame([{"date": d, "code": "A", "shares": 100, "mark": 10, "stale_trading_days": 2} for d in dates]),
            "decisions": [{"date": "2026-01-02", "weights": {"A": .8}}, {"date": "2026-01-06", "weights": {"B": .6}}],
            "trades": pd.DataFrame([{"date": "20260105", "code": "A"}, {"date": "20260106", "code": "B"}]),
            "events": pd.DataFrame()}


def test_historical_holdings_use_only_known_targets_and_fills():
    view = snapshot(example(), "2026-01-05")
    assert view["decision_date"] == "2026-01-02"
    assert view["rows"][0]["target_weight"] == .8
    assert len(view["trades"]) == 1
    assert view["market_value"] + view["cash"] + view["receivable"] == view["equity"]


def test_target_only_and_retained_positions_are_both_visible():
    view = snapshot(example(), "2026-01-06")
    actual, target_only = view["rows"]
    assert actual["shares"] == 100 and actual["target_weight"] == 0
    assert "残留" in actual["status"] and "无报价" in actual["status"]
    assert target_only["shares"] == 0 and target_only["actual_weight"] == 0
    assert target_only["target_weight"] == .6
    assert target_only["mark"] is None
    assert view["held_count"] == 1 and view["target_count"] == 1


def test_holdings_reconciliation_fails_instead_of_displaying_inconsistent_totals():
    ledger = example()
    ledger["positions"]["mark"] = 11
    with pytest.raises(ValueError, match="reconcile"):
        snapshot(ledger, "2026-01-05")
