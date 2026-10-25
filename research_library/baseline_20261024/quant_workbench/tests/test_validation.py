import pandas as pd
import pytest
from quant_workbench.validation import holding_quality, index_reference, momentum_input_quality


def test_index_keeps_first_day_return():
    frame = pd.DataFrame({"trade_date": ["20240102", "20240103", "20240104"], "close": [100, 110, 99]})
    nav = index_reference(frame, pd.to_datetime(["20240103", "20240104"]), 1000)
    assert nav.equity.tolist() == [1100, 990]
    with pytest.raises(ValueError, match="missing"):
        index_reference(frame, pd.to_datetime(["20240105"]), 1000)


def test_issue_exposure_uses_previous_close_even_if_sold_on_event():
    dates = pd.to_datetime(["20240102", "20240103", "20240104"])
    result = {"nav": pd.DataFrame({"equity": [1000, 1000, 1000]}, index=dates),
              "positions": pd.DataFrame([{"date": dates[0], "code": "x", "shares": 10,
                                           "mark": 10, "weight": .1, "stale_trading_days": 0}])}
    quality = {"issues": [{"code": "x", "date": "20240103", "severity": "high", "type": "action_factor_mismatch"},
                           {"code": "x", "date": "20240104", "severity": "high", "type": "action_factor_mismatch"}]}
    audit = holding_quality(result, quality)
    assert len(audit["unresolved_events_held"]) == 1
    assert audit["unresolved_events_held"][0]["previous_close_weight"] == .1


def test_factor_gate_covers_unselected_rankable_candidates():
    dates = pd.bdate_range("2023-01-02", periods=80)
    prices = pd.DataFrame({"A": 10., "B": 20.}, index=dates)
    panels = {"adjusted_close": prices, "amount": prices * 2e6}
    membership = pd.DataFrame({"trade_date": ["20221230", "20221230"], "con_code": ["A", "B"]})
    spec = {"kind": "momentum", "lookback": 30, "skip": 5}
    quality = {"issues": [{"code": "A", "date": dates[60].strftime("%Y%m%d"), "severity": "high", "type": "unexplained_factor_change"}]}
    result = momentum_input_quality(panels, membership, spec, {dates[-1]: {"B": 1.0}}, quality)
    assert len(result["unresolved_candidate_windows"]) == 1
    assert result["unresolved_candidate_windows"][0]["selected"] is False
    quality["issues"][0]["date"] = dates[-1].strftime("%Y%m%d")
    assert not momentum_input_quality(panels, membership, spec, {dates[-1]: {"B": 1.0}}, quality)["unresolved_candidate_windows"]
