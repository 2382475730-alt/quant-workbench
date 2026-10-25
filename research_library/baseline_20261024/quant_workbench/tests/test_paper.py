import pandas as pd
import pytest
from quant_workbench.paper import value_observation


def fixture():
    seed = {"cash": 1000, "holdings": [{"code": "000001.SZ", "shares": 100, "close": 10, "adj_factor": 2}]}
    quotes = pd.DataFrame([{"date": "2026-01-05", "code": "000001.SZ", "close": 11, "adj_factor": 2.0}])
    return seed, quotes


def test_forward_observation_counts_cash_and_refuses_rewrite_or_changed_factor():
    seed, quotes = fixture()
    result = value_observation(seed, quotes, "2026-01-02")
    assert result["equity"] == 2100
    assert result["mark_return_since_seed"] == pytest.approx(.05)
    with pytest.raises(ValueError, match="later"):
        value_observation(seed, quotes, "2026-01-05")
    quotes.loc[0, "adj_factor"] = 2.1
    with pytest.raises(ValueError, match="Corporate action"):
        value_observation(seed, quotes, "2026-01-02")


def test_missing_quotes_are_not_marked_at_stale_prices():
    seed, quotes = fixture()
    quotes.loc[0, "code"] = "different"
    with pytest.raises(ValueError, match="Every held"):
        value_observation(seed, quotes, "2026-01-02")
