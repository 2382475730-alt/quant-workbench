import pandas as pd
import pytest
from quant_workbench.company import available_statements, cash_metrics, trailing_year


def test_later_actual_announcement_and_same_day_excluded():
    rows = pd.DataFrame([
        {"end_date": "20250630", "ann_date": "20250801", "f_ann_date": "20250810", "value": 10, "update_flag": "0"},
        {"end_date": "20250630", "ann_date": "20250801", "f_ann_date": "20250820", "value": 999, "update_flag": "1"},
    ])
    out, _ = available_statements(rows, "2025-08-20", ["value"])
    assert out.loc["20250630", "value"] == 10
    out, _ = available_statements(rows, "2025-08-10", ["value"])
    assert out.empty


def test_ttm_ytd_bridge_and_missing_not_zero():
    x = pd.DataFrame({"profit": [100, 45, 60]}, index=["20241231", "20240630", "20250630"])
    assert trailing_year(x, "20250630", "profit") == 115
    assert trailing_year(x.drop("20240630"), "20250630", "profit") is None


def test_conflicting_same_rank_statements_fail():
    rows = pd.DataFrame([{"end_date": "20241231", "ann_date": "20250301", "value": v} for v in [1, 2]])
    with pytest.raises(ValueError, match="Conflicting"):
        available_statements(rows, "2025-04-01", ["value"])


def test_financial_companies_do_not_get_industrial_fcf():
    assert cash_metrics(100, 5, 10, financial=True)["operating_cash_minus_capex"] is None
    assert cash_metrics(100, None, 10)["operating_cash_minus_capex"] is None
    assert cash_metrics(100, 5, 10)["operating_cash_minus_capex"] == 95
